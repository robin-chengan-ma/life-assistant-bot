"""語音（Speech-to-Text）通用 Client：目前串接 Groq Whisper API。

命名為 voice 而不是 groq，是為了讓對外呼叫介面（transcribe）維持穩定；未來若要換成
其他語音轉文字供應商，呼叫端的程式碼不需要跟著改。刻意用 requests 直接呼叫 Groq 的
OpenAI 相容 REST API（比照 telegram/gdrive 子模組的做法，見 submodules-core SPEC.md
ADR-2），不額外安裝官方 groq SDK，避免為了單一端點多引入一個重量依賴。

金鑰不寫死在程式碼中，一律由呼叫端在建立 Client 時傳入 api_key。
"""
import requests

from submodules.retry.client import call_with_retry

_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_DEFAULT_MODEL = "whisper-large-v3"
_DEFAULT_TIMEOUT_SECONDS = 60

# 2026-08-05：外部 API 重試機制（見 docs/specs/robinson/SPEC.md FR-19i、
# docs/specs/submodules-core/SPEC.md ADR-13）。判斷邏輯比照 submodules/telegram：
# 只重試連線失敗、逾時、HTTP 429／5xx，其餘 4xx 直接往外拋。
_RETRYABLE_HTTP_STATUS_MIN = 500
_RETRYABLE_RATE_LIMIT_STATUS = 429


def _is_retryable_requests_error(exc: Exception) -> bool:
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code is None:
            return False
        return status_code == _RETRYABLE_RATE_LIMIT_STATUS or status_code >= _RETRYABLE_HTTP_STATUS_MIN
    return False


class VoiceClient:
    """封裝 Groq Whisper 語音轉文字 API 的最小 Client。"""

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL):
        if not api_key:
            raise ValueError("api_key 不可為空")
        self._api_key = api_key
        self._model = model

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.ogg", mime_type: str = "audio/ogg") -> str:
        """把語音檔轉成文字，回傳純文字結果（去除頭尾空白）。

        `response_format="text"` 讓 Groq 直接回傳純文字 body，不用另外解析 JSON。
        """
        headers = {"Authorization": f"Bearer {self._api_key}"}
        files = {"file": (filename, audio_bytes, mime_type)}
        data = {"model": self._model, "response_format": "text"}

        def _do_request():
            response = requests.post(
                _TRANSCRIPTION_URL, headers=headers, files=files, data=data, timeout=_DEFAULT_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            return response

        response = call_with_retry(_do_request, is_retryable=_is_retryable_requests_error)
        return response.text.strip()

    def transcribe_with_segments(
        self, audio_bytes: bytes, filename: str = "audio.mp3", mime_type: str = "audio/mpeg"
    ) -> list[dict]:
        """轉錄並回傳逐段時間軸（2026-08-07 新增，見 docs/specs/robinson/SPEC.md Step 3.2：
        TOEIC 整包聽力 MP3 需要依語句停頓自動切割成單題小檔）。

        用 `response_format=verbose_json` + `timestamp_granularities[]=segment`（Groq 相容
        OpenAI Whisper API 規格），只回傳呼叫端需要的 `start`／`end`／`text` 三個欄位。
        """
        headers = {"Authorization": f"Bearer {self._api_key}"}
        files = {"file": (filename, audio_bytes, mime_type)}
        data = {
            "model": self._model,
            "response_format": "verbose_json",
            "timestamp_granularities[]": "segment",
        }

        def _do_request():
            response = requests.post(
                _TRANSCRIPTION_URL, headers=headers, files=files, data=data, timeout=_DEFAULT_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            return response

        response = call_with_retry(_do_request, is_retryable=_is_retryable_requests_error)
        payload = response.json()
        return [
            {"start": segment["start"], "end": segment["end"], "text": segment["text"]}
            for segment in payload.get("segments", [])
        ]
