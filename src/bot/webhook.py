"""Telegram Webhook 入口（對應 docs/specs/platform-auth/SPEC.md FR-1）。"""
import os

from flask import Blueprint, jsonify, request

from src.bot.router import handle_message
from src.bot.state import ConversationStateStore
from submodules.cloudsql.client import CloudSQLClient
from submodules.llm.client import LLMClient
from submodules.telegram.client import TelegramClient

bot_bp = Blueprint("bot", __name__)

# Owner /set_invite_codes 對話狀態，整個 process 生命週期內共用一份（ADR-2：僅存於記憶體）。
_state_store = ConversationStateStore()


def extract_message(payload: dict) -> tuple[int, str] | None:
    """從 Telegram Update JSON 取出 (telegram_user_id, text)。

    只處理純文字訊息；缺少 message/from/id/text 任一欄位（例如貼圖、照片、edited_message
    等非文字更新）一律回傳 None，交由呼叫端忽略，避免 Step 1.1 範圍外的訊息類型讓 process 出錯。
    """
    message = payload.get("message") or {}
    from_user = message.get("from") or {}
    telegram_user_id = from_user.get("id")
    text = message.get("text")
    if telegram_user_id is None or text is None:
        return None
    return telegram_user_id, text


@bot_bp.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    payload = request.get_json(silent=True) or {}
    extracted = extract_message(payload)
    if extracted is None:
        return jsonify({"ok": True}), 200

    telegram_user_id, text = extracted

    db = CloudSQLClient()
    # 一般問答用的 Key（見 docs/specs/chat-core/SPEC.md ADR-12）與長記憶摘要用的 Key（ADR-3），
    # 只有訊息真的落入一般聊天核心時才會被呼叫；其餘指令/對話流程分支不會用到。
    llm_client = LLMClient(api_key=os.environ["GEMINI_API_BOT_KEY"])
    text_llm_client = LLMClient(api_key=os.environ["GEMINI_API_TEXT_KEY"])
    try:
        reply = handle_message(
            db, _state_store, telegram_user_id, text, llm_client=llm_client, text_llm_client=text_llm_client
        )
    finally:
        db.close()

    if reply:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        telegram_client.send_text(chat_id=telegram_user_id, text=reply)

    return jsonify({"ok": True}), 200
