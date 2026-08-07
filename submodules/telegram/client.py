"""Telegram 通用 Client：封裝 Telegram Bot HTTP API 的請求與常用訊息發送方法。

刻意用 requests 直接呼叫 HTTP API，不使用 python-telegram-bot 這類
async-first SDK，避免把「發送訊息」這個最基礎的操作綁死在特定事件迴圈上。
Webhook 接收 / 訊息路由等較複雜的邏輯，交給 backend 層自行決定要用什麼框架。
"""
import requests

from submodules.retry.client import call_with_retry

_TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"
_TELEGRAM_FILE_BASE = "https://api.telegram.org/file/bot{token}/{file_path}"
_DEFAULT_TIMEOUT_SECONDS = 10
_FILE_DOWNLOAD_TIMEOUT_SECONDS = 30

# 2026-08-05：外部 API 重試機制（見 docs/specs/robinson/SPEC.md FR-19i、
# docs/specs/submodules-core/SPEC.md ADR-13）。只重試「暫時性錯誤」：連線失敗、逾時、
# HTTP 429（Rate Limit）與 5xx（Telegram 伺服器端問題）；其餘 4xx（例如 400 參數錯誤、
# 401 Token 失效）重試也沒用，直接往外拋，不浪費重試次數。
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


class TelegramClient:
    """封裝 Telegram Bot HTTP API 的請求與常用訊息發送方法。"""

    def __init__(self, bot_token: str):
        if not bot_token:
            raise ValueError("bot_token 不可為空")
        self._token = bot_token

    def call(self, method: str, payload: dict) -> dict:
        """呼叫 Telegram Bot API 的任意 method，回傳解析後的 JSON。

        範例：client.call("sendMessage", {"chat_id": 123, "text": "hi"})
        """
        url = _TELEGRAM_API_BASE.format(token=self._token, method=method)

        def _do_request():
            response = requests.post(url, json=payload, timeout=_DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response

        response = call_with_retry(_do_request, is_retryable=_is_retryable_requests_error)
        return response.json()

    def send_text(self, chat_id: int | str, text: str, parse_mode: str | None = None) -> dict:
        """發送文字訊息。

        2026-08-02：預設不帶 `parse_mode`（純文字）。原本預設 `"Markdown"`，但這則訊息的
        文字內容大多來自 LLM 自然語言生成，無法保證符合 Telegram 舊版 Markdown 語法（例如
        底線、星號沒有成對），一旦格式不符 Telegram 會整則拒收（400 Bad Request），使用者
        完全收不到回覆；純文字傳送不會有這個風險。呼叫端仍可視需要明確傳入 `parse_mode`
        （例如確定內容是自己手寫、格式受控的靜態文案時）。
        """
        payload = {"chat_id": chat_id, "text": text}
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        return self.call("sendMessage", payload)

    def send_photo(self, chat_id: int | str, photo: str, caption: str = "") -> dict:
        """發送圖片，photo 可傳圖片 URL 或 Telegram file_id。"""
        payload = {"chat_id": chat_id, "photo": photo, "caption": caption}
        return self.call("sendPhoto", payload)

    def send_chat_action(self, chat_id: int | str, action: str = "typing") -> dict:
        """發送「正在輸入…」等狀態提示，讓使用者知道 Robinson 正在處理。"""
        payload = {"chat_id": chat_id, "action": action}
        return self.call("sendChatAction", payload)

    def get_file_bytes(self, file_id: str) -> bytes:
        """下載使用者上傳的檔案（圖片/語音等），回傳原始 bytes。

        分兩步：先呼叫 `getFile` 用 `file_id` 換取 `file_path`，再從 Telegram 的
        檔案下載端點（跟一般 Bot API 端點不同網域路徑）實際抓取內容。
        """
        file_info = self.call("getFile", {"file_id": file_id})
        file_path = file_info["result"]["file_path"]
        url = _TELEGRAM_FILE_BASE.format(token=self._token, file_path=file_path)

        def _do_download():
            response = requests.get(url, timeout=_FILE_DOWNLOAD_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response

        response = call_with_retry(_do_download, is_retryable=_is_retryable_requests_error)
        return response.content
