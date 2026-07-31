"""LLM 通用 Client：目前串接 Gemini API（官方 google-genai SDK）。

命名為 llm 而不是 gemini，是為了讓對外呼叫介面（generate_text /
generate_with_image）維持穩定；未來若要換成其他供應商或新增第二個供應商，
呼叫端的程式碼不需要跟著改，只有這個檔案內部的實作需要調整。

金鑰不寫死在程式碼中，一律由呼叫端在建立 Client 時傳入 api_key。
"""
import time
from collections import deque

from google import genai
from google.genai import types

_DEFAULT_MODEL = "gemini-3.5-flash-lite"

# `generate_with_search()` 專用模型：見 docs/specs/submodules-core/SPEC.md ADR-7。
# 2026-07-31 實測（AI Studio Rate Limit 頁面「Tools」區塊）：Google Search grounding 的免費額度
# 是「依模型世代」分桶計算，不是每個模型都有——Gemini 3 世代（含 `gemini-3.5-flash-lite`）免費
# grounding 額度是 0（官方定價頁：Gemini 3 使用 grounding 一律計費，免費層不提供），但 Gemini 2.5
# 世代有 1,500 次/天免費額度。因此帶 Google Search 工具的呼叫必須指定 Gemini 2.5 世代的模型，
# 其餘不需要查網路的呼叫（純文字/圖片）維持用 `_DEFAULT_MODEL`（額度更好、非停用倒數中的世代）。
# 原本選 `gemini-2.5-flash-lite`，但 Robin 於 AI Studio 實際測試時這個模型不可選，改用同世代
# 的 `gemini-2.5-flash`（`gemini-2.5-pro` 較重，非必要不選）。
# 注意：Gemini 2.5 系列預計 2026-10-16 停用，屆時須重新評估這個模型是否要換。
_SEARCH_MODEL = "gemini-2.5-flash"

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

    _call_history_by_key: dict[str, "deque[float]"] = {}

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
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
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
        response = self._client.models.generate_content(
            model=self._model,
            contents=[image_part, prompt],
        )
        return response.text

    def generate_with_search(self, prompt: str) -> tuple[str, bool]:
        """帶 Google Search 工具的生成呼叫，回傳 (回應文字, 是否實際使用了 Google Search)。

        是否要查網路由模型自行判斷（見 docs/specs/chat-core/SPEC.md ADR-1），本方法只負責
        從回應的 grounding_metadata 判讀這次有沒有真的觸發搜尋，不自己額外呼叫第二次 API。

        刻意不用 `self._model`（見 ADR-7）：Google Search grounding 的免費額度依模型世代分桶，
        `_DEFAULT_MODEL` 所屬的 Gemini 3 世代免費額度是 0，這裡固定改用有免費額度的
        `_SEARCH_MODEL`（Gemini 2.5 世代），避免每次掛搜尋工具都直接被 Google 判 429。
        """
        self._guard_rate_limit()
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        config = types.GenerateContentConfig(tools=[grounding_tool])
        response = self._client.models.generate_content(
            model=_SEARCH_MODEL,
            contents=prompt,
            config=config,
        )
        return response.text, self._used_search(response)

    @staticmethod
    def _used_search(response) -> bool:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return False
        metadata = getattr(candidates[0], "grounding_metadata", None)
        if metadata is None:
            return False
        return bool(getattr(metadata, "web_search_queries", None))
