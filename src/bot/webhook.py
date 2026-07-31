"""Telegram Webhook 入口（對應 docs/specs/platform-auth/SPEC.md FR-1）。"""
import logging
import os
from collections import OrderedDict

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

# 見 docs/specs/platform-auth/SPEC.md FR-7a：Telegram 在沒收到 200 時會自動重送同一則
# update（不只發生在我們自己出錯的時候，網路延遲也可能讓 Telegram 誤判逾時而重送），
# 用一個有上限的 LRU 記錄最近處理過的 update_id，收到重複的直接短路回 200、不重跑任何邏輯，
# 避免同一則訊息被重複拿去打 Gemini。上限避免長時間運行下記憶體無限增長。
_PROCESSED_UPDATE_IDS_MAXLEN = 1000
_processed_update_ids: "OrderedDict[int, None]" = OrderedDict()


def _is_duplicate_update(update_id: int) -> bool:
    return update_id in _processed_update_ids


def _mark_update_processed(update_id: int) -> None:
    _processed_update_ids[update_id] = None
    if len(_processed_update_ids) > _PROCESSED_UPDATE_IDS_MAXLEN:
        _processed_update_ids.popitem(last=False)


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

    update_id = payload.get("update_id")
    if update_id is not None and _is_duplicate_update(update_id):
        return jsonify({"ok": True}), 200

    extracted = extract_message(payload)
    if extracted is None:
        return jsonify({"ok": True}), 200

    if update_id is not None:
        _mark_update_processed(update_id)

    telegram_user_id, text = extracted

    # 一旦決定要處理這則訊息，就先標記 update_id 已處理：無論後面成不成功，都不希望
    # Telegram 因為收不到 200（或單純網路延遲誤判逾時）而重送同一則訊息、重打一次 Gemini。
    if update_id is not None:
        _mark_update_processed(update_id)

    reply = _UNEXPECTED_ERROR_REPLY
    db = None
    try:
        db = CloudSQLClient()
        # 一般問答用的 Key（見 docs/specs/chat-core/SPEC.md ADR-12）與長記憶摘要用的 Key（ADR-3），
        # 只有訊息真的落入一般聊天核心時才會被呼叫；其餘指令/對話流程分支不會用到。
        llm_client = LLMClient(api_key=os.environ["GEMINI_API_BOT_KEY"])
        text_llm_client = LLMClient(api_key=os.environ["GEMINI_API_TEXT_KEY"])
        reply = handle_message(
            db, _state_store, telegram_user_id, text, llm_client=llm_client, text_llm_client=text_llm_client
        )
    except Exception:
        # 暫時性安全網（Step 1.6／FR-19a 完整版之前）：任何未預期例外（例如 Gemini 429 額度超限、
        # 本地端節流保護 LLMQuotaGuardError、DB 連線失敗等）都要在這裡吞掉，改回安全用語並仍然
        # 回 200——否則 Flask 會回 500，Telegram 收不到 200 就會自動重送同一則訊息，變成
        # 「失敗 → 重試 → 再失敗」的迴圈，把 API 額度燒得更快。
        _logger.exception(
            "處理 Telegram 訊息時發生未預期例外（telegram_user_id=%s），已回覆安全用語並停止重試",
            telegram_user_id,
        )
        reply = _UNEXPECTED_ERROR_REPLY
    finally:
        if db is not None:
            db.close()

    if reply:
        try:
            telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
            telegram_client.send_text(chat_id=telegram_user_id, text=reply)
        except Exception:
            # 傳送失敗（例如 Telegram API 本身出問題）是另一個獨立的失敗模式，不影響前面
            # handle_message 的處理結果，一樣只記錄不往外拋，避免這裡也觸發 Telegram 重試。
            _logger.exception("傳送 Telegram 回覆失敗（telegram_user_id=%s）", telegram_user_id)

    return jsonify({"ok": True}), 200
