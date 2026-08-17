"""LLM 通用 Client：目前串接 Gemini API（官方 google-genai SDK）。

命名為 llm 而不是 gemini，是為了讓對外呼叫介面（generate_text /
generate_with_image）維持穩定；未來若要換成其他供應商或新增第二個供應商，
呼叫端的程式碼不需要跟著改，只有這個檔案內部的實作需要調整。

金鑰不寫死在程式碼中，一律由呼叫端在建立 Client 時傳入 api_key。
"""
import time
from collections import deque
from typing import ClassVar

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from submodules.retry.client import call_with_retry

_DEFAULT_MODEL = "gemini-3.5-flash-lite"

# 2026-08-05：外部 API 重試機制（見 docs/specs/robinson/SPEC.md FR-19i、
# docs/specs/submodules-core/SPEC.md ADR-13）。只重試「暫時性錯誤」：
# - ServerError（Gemini 5xx，伺服器端暫時性問題）
# - ClientError 且 code == 429（Rate Limit，等一下再送就有機會成功）
# - 連線/逾時類的底層例外（ConnectionError／TimeoutError）
# 其餘 ClientError（例如 400 參數錯誤、401/403 金鑰失效、404 模型不存在——見 ADR-8
# 排查過的實際案例）都是「重試也沒用」的永久性錯誤，直接往外拋，不浪費重試次數。
_RETRYABLE_CLIENT_ERROR_CODE = 429


def _is_retryable_genai_error(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError):
        return getattr(exc, "code", None) == _RETRYABLE_CLIENT_ERROR_CODE
    return isinstance(exc, (ConnectionError, TimeoutError))


# 2026-07-31：曾在 ADR-7 用 `gemini-2.5-flash` 做 Google Search grounding 的專屬模型，
# 但 Robin 排查一把新產生的 Gemini API Key 時發現該模型回傳 404
#「This model ... is no longer available to new users」——Gemini 2.5 世代已對新專案關閉存取，
# 不只是額度問題，整個世代都走不通。改為完全移除 grounding／`generate_with_search()`，
# 詳見 docs/specs/submodules-core/SPEC.md ADR-8（supersede ADR-7）。

# 本地端節流保護（非 Gemini 官方額度機制）：見 docs/specs/submodules-core/SPEC.md ADR-5。
# 2026-07-31 實測（AI Studio Rate Limit 頁面）：`gemini-flash-latest` 當時解析到的
# Gemini 3.6 Flash 免費層只有 RPM 5／RPD 20，遠低於原本假設的 10～15 次/分鐘、1500 次/天，
# 是造成頻繁 429 的主因；改用明確指定版本的 `gemini-3.5-flash-lite` 後實測為 RPM 15／RPD 500，
# 這裡的預設值刻意抓保守一點（低於官方 RPM 上限），目的是在明知道會被官方 429 拒絕之前
# 就先攔下來，避免白白浪費一次額度；注意這裡只防 RPM（每分鐘），還沒有防 RPD（每天）上限。
_DEFAULT_MAX_CALLS_PER_MINUTE = 8
_RATE_LIMIT_WINDOW_SECONDS = 60


class LLMQuotaGuardError(RuntimeError):
    """本地端節流門檻觸發時拋出（不是 Gemini 官方回傳的錯誤）。

    呼叫端（目前是 `src/bot/webhook.py` 的安全網）應該把這個例外當成一般的暫時性錯誤處理，
    回覆使用者安全用語即可，不需要特別區分。
    """


class LLMClient:
    """封裝官方 google-genai SDK 的最小 Client。

    節流計數以 `api_key` 為單位共用（class 層級的 `dict`，不是掛在單一 instance 上）：
    同一把 `api_key` 對應同一個 Google Cloud 專案、共用同一份 Gemini 官方額度（見
    docs/specs/robinson/SPEC.md ADR-12），即使呼叫端每次請求都重新 `LLMClient(...)`
    （目前 `webhook.py` 就是這樣用），只要 `api_key` 相同，節流計數仍會正確地跨請求累積。
    """

    _call_history_by_key: ClassVar[dict[str, "deque[float]"]] = {}

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        max_calls_per_minute: int = _DEFAULT_MAX_CALLS_PER_MINUTE,
    ):
        if not api_key:
            raise ValueError("api_key 不可為空")
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._api_key = api_key
        self._max_calls_per_minute = max_calls_per_minute

    def _guard_rate_limit(self) -> None:
        """呼叫真正的 Gemini API 之前先檢查本地端節流門檻，超過就直接拋例外、不送出請求。"""
        history = LLMClient._call_history_by_key.setdefault(self._api_key, deque())
        now = time.monotonic()
        while history and now - history[0] >= _RATE_LIMIT_WINDOW_SECONDS:
            history.popleft()
        if len(history) >= self._max_calls_per_minute:
            raise LLMQuotaGuardError(
                f"最近 {_RATE_LIMIT_WINDOW_SECONDS} 秒內已呼叫 {len(history)} 次，"
                f"超過本地端節流門檻（{self._max_calls_per_minute} 次/分鐘），暫緩呼叫避免浪費額度"
            )
        history.append(now)

    def generate_text(self, prompt: str) -> str:
        """純文字生成，回傳模型的文字回應。"""
        self._guard_rate_limit()
        response = call_with_retry(
            lambda: self._client.models.generate_content(
                model=self._model,
                contents=prompt,
            ),
            is_retryable=_is_retryable_genai_error,
        )
        return response.text

    def generate_with_image(
        self,
        prompt: str,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> str:
        """圖像 + 文字提示的生成呼叫（例如解析證照題目截圖）。"""
        self._guard_rate_limit()
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        response = call_with_retry(
            lambda: self._client.models.generate_content(
                model=self._model,
                contents=[image_part, prompt],
            ),
            is_retryable=_is_retryable_genai_error,
        )
        return response.text

