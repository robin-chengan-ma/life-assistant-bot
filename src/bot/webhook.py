"""Telegram Webhook 入口（對應 docs/specs/platform-auth/SPEC.md FR-1）。"""
import logging
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

_logger = logging.getLogger(__name__)

# Step 1.6（FR-19）完整版之前的暫時性安全網文案：任何未預期例外（例如 Gemini 429 額度超限）
# 都回這句，不揭露技術細節；正式的「生病了」人格化用語與 Robin 私訊通知留給 Step 1.6 一併做。
_UNEXPECTED_ERROR_REPLY = "羅賓森好像不太舒服，等一下再試試看喔！"


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
    except Exception:
        # 暫時性安全網（Step 1.6／FR-19a 完整版之前）：任何未預期例外（例如 Gemini 429 額度超限）
        # 都要在這裡吞掉，改回安全用語並仍然回 200——否則 Flask 會回 500，Telegram 收不到 200
        # 就會自動重送同一則訊息，變成「失敗 → 重試 → 再失敗」的迴圈，把 API 額度燒得更快。
        _logger.exception(
            "處理 Telegram 訊息時發生未預期例外（telegram_user_id=%s），已回覆安全用語並停止重試",
            telegram_user_id,
        )
        reply = _UNEXPECTED_ERROR_REPLY
    finally:
        db.close()

    if reply:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        telegram_client.send_text(chat_id=telegram_user_id, text=reply)

    return jsonify({"ok": True}), 200
