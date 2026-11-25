"""Telegram Webhook 入口（對應 docs/specs/platform-auth/SPEC.md FR-1）。

2026-11（功能大幅精簡）：機器人只剩下文字訊息（/start 綁定、Owner 權限管理）與按鈕
callback_query 兩種更新需要處理；圖片／語音／文件等其他訊息類型，以及 Gmail／Google Drive／
Google Calendar／語音轉錄等外部整合，隨對應功能一併移除。保留的核心基礎設施：
- `update_id` 去重（FR-7a：Telegram 沒收到 200 會自動重送同一則 update）。
- 包住 `handle_message()`／`handle_callback_query()` 的安全網，任何未預期例外都要吞掉、
  回安全用語並仍然回 200，避免 Telegram 判定逾時而觸發重試迴圈。
"""
import logging
import os
from collections import OrderedDict

from flask import Blueprint, jsonify, request

from src.bot.router import handle_callback_query, handle_message
from src.bot.state import ConversationStateStore
from submodules.cloudsql.client import CloudSQLClient
from submodules.telegram.client import TelegramClient

bot_bp = Blueprint("bot", __name__)

# 整個 process 生命週期內共用一份（ADR-2：僅存於記憶體）。
_state_store = ConversationStateStore()

_logger = logging.getLogger(__name__)

# 任何未預期例外都回這句固定安全用語，不經過 LLM 生成（機器人已不再呼叫一般聊天用的 LLM）。
_GENERAL_ERROR_REPLY = (
    "🤒 主任，我好像有點小感冒（系統暫時性異常），麻煩稍後再試一次，或聯絡 Robin 確認！"
)
_EMPTY_REPLY_FALLBACK = "不好意思，我剛剛好像沒接上你的話，可以再說一次或換個方式講講看嗎？"
_UNSUPPORTED_FORMAT_REPLY = "我只能處理文字訊息喔！其餘功能請到 App 操作。"

# 見 docs/specs/platform-auth/SPEC.md FR-7a：用一個有上限的 LRU 記錄最近處理過的 update_id，
# 收到重複的直接短路回 200、不重跑任何邏輯。上限避免長時間運行下記憶體無限增長。
_PROCESSED_UPDATE_IDS_MAXLEN = 1000
_processed_update_ids: "OrderedDict[int, None]" = OrderedDict()


def _notify_owner_of_error(feature: str, telegram_user_id: int | None) -> None:
    """未預期例外時，私訊 Robin 一句簡短通知（不含完整 Traceback 上傳／事故落地，那套機制
    隨 `system_errors.py`／`system_error_management.py` 一併移除）；送不出去只記 log，不往外拋。
    """
    owner_chat_id = os.environ.get("ROBIN_TELEGRAM_TOKEN")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not owner_chat_id or not bot_token:
        return
    try:
        TelegramClient(bot_token).send_text(
            chat_id=owner_chat_id,
            text=f"🐛 Telegram 機器人處理「{feature}」時發生未預期例外（telegram_user_id={telegram_user_id}），請查看伺服器 log。",
        )
    except Exception:
        _logger.exception("私訊 Robin 錯誤通知失敗")


def _is_duplicate_update(update_id: int) -> bool:
    return update_id in _processed_update_ids


def _mark_update_processed(update_id: int) -> None:
    _processed_update_ids[update_id] = None
    if len(_processed_update_ids) > _PROCESSED_UPDATE_IDS_MAXLEN:
        _processed_update_ids.popitem(last=False)


def extract_message(payload: dict) -> tuple[int, str] | None:
    """從 Telegram Update JSON 取出 (telegram_user_id, text)。

    只處理純文字訊息；缺少 message/from/id/text 任一欄位（例如貼圖、照片、edited_message
    等）一律回傳 None，交由呼叫端忽略。
    """
    message = payload.get("message") or {}
    from_user = message.get("from") or {}
    telegram_user_id = from_user.get("id")
    text = message.get("text")
    if telegram_user_id is None or text is None:
        return None
    return telegram_user_id, text


def _extract_callback_query(payload: dict) -> tuple[int, str, str] | None:
    """從 Telegram Update JSON 取出 (telegram_user_id, callback_query_id, data)。"""
    callback_query = payload.get("callback_query") or {}
    from_user = callback_query.get("from") or {}
    telegram_user_id = from_user.get("id")
    callback_query_id = callback_query.get("id")
    data = callback_query.get("data")
    if telegram_user_id is None or callback_query_id is None or data is None:
        return None
    return telegram_user_id, callback_query_id, data


def _extract_unsupported_update(payload: dict) -> int | None:
    """偵測既不是文字訊息、也不是 callback_query 的其他訊息類型（照片/語音/文件等），
    有的話回傳寄件者 telegram_user_id，供呼叫端回覆固定的「不支援」提示。
    """
    message = payload.get("message") or {}
    from_user = message.get("from") or {}
    telegram_user_id = from_user.get("id")
    if telegram_user_id is None:
        return None
    if "text" in message:
        return None
    return telegram_user_id


def _handle_callback_query_update(callback_extracted: tuple[int, str, str]):
    """處理按鈕按下的 callback_query 更新。一定要呼叫 `answerCallbackQuery`（見
    `submodules/telegram/client.py` docstring），否則使用者手機上的 Telegram 客戶端會卡在
    按鈕轉圈圈的 loading 狀態。失敗時只記錄 log，不觸發 Robin 錯誤私訊（callback_query
    處理不涉及外部服務呼叫，失敗模式單純很多）。
    """
    telegram_user_id, callback_query_id, data = callback_extracted
    db = None
    try:
        db = CloudSQLClient()
        reply, reply_markup = handle_callback_query(db, _state_store, telegram_user_id, data)
    except Exception:
        _logger.exception(
            "處理 callback_query 時發生未預期例外（telegram_user_id=%s，data=%s）", telegram_user_id, data
        )
        reply, reply_markup = _EMPTY_REPLY_FALLBACK, None
    finally:
        if db is not None:
            db.close()

    try:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        telegram_client.answer_callback_query(callback_query_id)
        if reply_markup is not None:
            telegram_client.send_text(chat_id=telegram_user_id, text=reply, reply_markup=reply_markup)
        else:
            telegram_client.send_text(chat_id=telegram_user_id, text=reply)
    except Exception:
        _logger.exception("回覆 callback_query 失敗（telegram_user_id=%s）", telegram_user_id)

    return jsonify({"ok": True}), 200


@bot_bp.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    payload = request.get_json(silent=True) or {}

    update_id = payload.get("update_id")
    if update_id is not None and _is_duplicate_update(update_id):
        return jsonify({"ok": True}), 200

    callback_extracted = _extract_callback_query(payload)
    if callback_extracted is not None:
        if update_id is not None:
            _mark_update_processed(update_id)
        return _handle_callback_query_update(callback_extracted)

    text_extracted = extract_message(payload)
    unsupported_user_id = None if text_extracted is not None else _extract_unsupported_update(payload)

    if text_extracted is None and unsupported_user_id is None:
        return jsonify({"ok": True}), 200

    if update_id is not None:
        _mark_update_processed(update_id)

    if unsupported_user_id is not None:
        try:
            telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
            telegram_client.send_text(chat_id=unsupported_user_id, text=_UNSUPPORTED_FORMAT_REPLY)
        except Exception:
            _logger.exception("傳送不支援格式提示失敗（telegram_user_id=%s）", unsupported_user_id)
        return jsonify({"ok": True}), 200

    telegram_user_id, text = text_extracted

    reply = _GENERAL_ERROR_REPLY
    reply_markup = None
    db = None
    try:
        db = CloudSQLClient()
        reply, reply_markup = handle_message(db, _state_store, telegram_user_id, text)
    except Exception:
        # 安全網：任何未預期例外都要在這裡吞掉，改回安全用語並仍然回 200——否則 Flask 會回
        # 500，Telegram 收不到 200 就會自動重送同一則訊息，變成「失敗 → 重試 → 再失敗」的迴圈。
        _logger.exception(
            "處理 Telegram 文字訊息時發生未預期例外（telegram_user_id=%s），已回覆安全用語並停止重試",
            telegram_user_id,
        )
        reply, reply_markup = _GENERAL_ERROR_REPLY, None
        _notify_owner_of_error("text", telegram_user_id)

    if not reply or not reply.strip():
        _logger.warning(
            "處理結果為空字串（telegram_user_id=%s），改用安全用語回覆，避免使用者完全收不到任何回應",
            telegram_user_id,
        )
        reply = _EMPTY_REPLY_FALLBACK
        reply_markup = None

    try:
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        if reply_markup is not None:
            telegram_client.send_text(chat_id=telegram_user_id, text=reply, reply_markup=reply_markup)
        else:
            telegram_client.send_text(chat_id=telegram_user_id, text=reply)
    except Exception:
        _logger.exception("傳送 Telegram 回覆失敗（telegram_user_id=%s）", telegram_user_id)

    if db is not None:
        db.close()

    return jsonify({"ok": True}), 200
