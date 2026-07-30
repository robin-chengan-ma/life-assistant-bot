"""Telegram 通用 Client：封裝 Telegram Bot HTTP API 的請求與常用訊息發送方法。

刻意用 requests 直接呼叫 HTTP API，不使用 python-telegram-bot 這類
async-first SDK，避免把「發送訊息」這個最基礎的操作綁死在特定事件迴圈上。
Webhook 接收 / 訊息路由等較複雜的邏輯，交給 backend 層自行決定要用什麼框架。
"""
import requests

_TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"
_DEFAULT_TIMEOUT_SECONDS = 10


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
        response = requests.post(url, json=payload, timeout=_DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()

    def send_text(self, chat_id: int | str, text: str, parse_mode: str = "Markdown") -> dict:
        """發送文字訊息。"""
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        return self.call("sendMessage", payload)

    def send_photo(self, chat_id: int | str, photo: str, caption: str = "") -> dict:
        """發送圖片，photo 可傳圖片 URL 或 Telegram file_id。"""
        payload = {"chat_id": chat_id, "photo": photo, "caption": caption}
        return self.call("sendPhoto", payload)

    def send_chat_action(self, chat_id: int | str, action: str = "typing") -> dict:
        """發送「正在輸入…」等狀態提示，讓使用者知道 Robinson 正在處理。"""
        payload = {"chat_id": chat_id, "action": action}
        return self.call("sendChatAction", payload)
