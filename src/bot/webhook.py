"""Telegram Webhook 入口（對應 docs/specs/platform-auth/SPEC.md FR-1）。"""
import logging
import os
from collections import OrderedDict

from flask import Blueprint, jsonify, request

from src.bot.router import handle_message, handle_photo_message, handle_voice_message
from src.bot.state import ConversationStateStore
from submodules.cloudsql.client import CloudSQLClient
from submodules.gdrive.client import GDriveClient
from submodules.llm.client import LLMClient
from submodules.telegram.client import TelegramClient
from submodules.voice.client import VoiceClient

bot_bp = Blueprint("bot", __name__)

# Owner /set_invite_codes 對話狀態，整個 process 生命週期內共用一份（ADR-2：僅存於記憶體）。
_state_store = ConversationStateStore()

# 2026-08-02（FR-14 規則 1）：語音超時鎖定的獨立記憶體儲存，與 `_state_store` 是不同用途、
# 不同生命週期概念的兩份資料，故意分開，避免跟對話流程的 `flow` 分派狀態混在一起。
_voice_lockout_store = ConversationStateStore()

_logger = logging.getLogger(__name__)

# Step 1.6（FR-19）完整版之前的暫時性安全網文案：任何未預期例外（例如 Gemini 429 額度超限）
# 都回這句，不揭露技術細節；正式的「生病了」人格化用語與 Robin 私訊通知留給 Step 1.6 一併做。
_UNEXPECTED_ERROR_REPLY = "羅賓森好像不太舒服，等一下再試試看喔！"

# 目前支援文字、圖片、語音（voice 與 audio 兩種訊息類型都算，見 _extract_voice），
# 收到其他格式（文件/影片/貼圖等）直接回這句拒絕，不進入 DB/Gemini 流程，符合 FR-17
# 「僅支援圖片與音檔兩種格式」的承諾。
_UNSUPPORTED_FORMAT_REPLY = "這個檔案格式我沒辦法處理喔，只能看懂圖片和音檔！"
_UNSUPPORTED_FILE_KEYS = ("document", "video", "video_note", "animation", "sticker")

# 見 docs/specs/platform-auth/SPEC.md FR-7a：Telegram 在沒收到 200 時會自動重送同一則
# update（不只發生在我們自己出錯的時候，網路延遲也可能讓 Telegram 誤判逾時而重送），
# 用一個有上限的 LRU 記錄最近處理過的 update_id，收到重複的直接短路回 200、不重跑任何邏輯，
# 避免同一則訊息被重複拿去打 Gemini。上限避免長時間運行下記憶體無限增長。
_PROCESSED_UPDATE_IDS_MAXLEN = 1000
_processed_update_ids: "OrderedDict[int, None]" = OrderedDict()


def _build_privacy_llm_client() -> LLMClient | None:
    """建立個資遮蔽語意層專用的 LLMClient（見 docs/specs/privacy-masking/SPEC.md ADR-1／ADR-2）。

    用獨立的 `GEMINI_API_PRIVACY_KEY`，不佔用聊天/長記憶/圖片辨識既有 Key 的配額。這把 Key
    是選配的：還沒設定環境變數時回傳 `None`，`privacy.mask_text()` 會優雅降級成只跑免費的
    Regex 層，不會讓整個訊息處理流程因為這把 Key 沒設好而失敗。
    """
    api_key = os.environ.get("GEMINI_API_PRIVACY_KEY")
    if not api_key:
        return None
    return LLMClient(api_key=api_key)


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


def _extract_photo(payload: dict) -> tuple[int, str, str | None] | None:
    """從 Telegram Update JSON 取出 (telegram_user_id, file_id, caption)。

    `message.photo` 是同一張圖多種解析度的陣列（由小到大排序），取最後一筆（解析度最高）
    的 file_id 送去做辨識；caption 是使用者隨圖片附帶的文字說明，可能沒有。
    """
    message = payload.get("message") or {}
    from_user = message.get("from") or {}
    telegram_user_id = from_user.get("id")
    photo_sizes = message.get("photo")
    if telegram_user_id is None or not photo_sizes:
        return None
    file_id = photo_sizes[-1].get("file_id")
    if not file_id:
        return None
    return telegram_user_id, file_id, message.get("caption")


def _extract_voice(payload: dict) -> tuple[int, str, int | None, str] | None:
    """從 Telegram Update JSON 取出 (telegram_user_id, file_id, duration_seconds, mime_type)。

    2026-08-01 修正（見 robinson SPEC.md FR-17）：涵蓋 `message.voice`（使用者按錄音鍵
    傳送的語音訊息，固定 OGG/OPUS）與 `message.audio`（使用者上傳的音檔，可能是
    MP3/M4A/WAV 等格式）——FR-17 承諾「圖片與音檔兩種格式都支援」，不是只有錄音鍵那種，
    先前只處理 `voice` 是範圍沒抓對，這裡補齊。兩者都帶 `duration`（秒），讓 FR-14 的
    10 分鐘上限判斷不需要先下載檔案就能做；`mime_type` 由 Telegram 回報，供
    `src/bot/voice.py` 決定正確的 Drive 副檔名與轉錄請求格式，`voice` 訊息缺少時
    fallback 為 `audio/ogg`。
    """
    message = payload.get("message") or {}
    from_user = message.get("from") or {}
    telegram_user_id = from_user.get("id")
    media = message.get("voice") or message.get("audio")
    if telegram_user_id is None or not media:
        return None
    file_id = media.get("file_id")
    if not file_id:
        return None
    mime_type = media.get("mime_type") or "audio/ogg"
    return telegram_user_id, file_id, media.get("duration"), mime_type


def _extract_unsupported_file(payload: dict) -> int | None:
    """偵測目前不支援的檔案類型（文件/影片/貼圖等），有的話回傳寄件者 telegram_user_id。

    2026-08-01（Step 1.4，後續修正涵蓋 `audio`）起 `voice`／`audio`（語音訊息與使用者
    上傳的音檔）都已正式支援，不再落在這個判斷內，見 `_extract_voice()`。
    """
    message = payload.get("message") or {}
    from_user = message.get("from") or {}
    telegram_user_id = from_user.get("id")
    if telegram_user_id is None:
        return None
    if any(key in message for key in _UNSUPPORTED_FILE_KEYS):
        return telegram_user_id
    return None


@bot_bp.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    payload = request.get_json(silent=True) or {}

    update_id = payload.get("update_id")
    if update_id is not None and _is_duplicate_update(update_id):
        return jsonify({"ok": True}), 200

    unsupported_user_id = _extract_unsupported_file(payload)
    photo_extracted = None if unsupported_user_id is not None else _extract_photo(payload)
    voice_extracted = (
        None if (unsupported_user_id is not None or photo_extracted is not None) else _extract_voice(payload)
    )
    text_extracted = (
        None
        if (unsupported_user_id is not None or photo_extracted is not None or voice_extracted is not None)
        else extract_message(payload)
    )

    if (
        unsupported_user_id is None
        and photo_extracted is None
        and voice_extracted is None
        and text_extracted is None
    ):
        return jsonify({"ok": True}), 200

    # 一旦決定要處理這則訊息，就先標記 update_id 已處理：無論後面成不成功，都不希望
    # Telegram 因為收不到 200（或單純網路延遲誤判逾時）而重送同一則訊息、重打一次 Gemini。
    if update_id is not None:
        _mark_update_processed(update_id)

    if unsupported_user_id is not None:
        try:
            telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
            telegram_client.send_text(chat_id=unsupported_user_id, text=_UNSUPPORTED_FORMAT_REPLY)
        except Exception:
            _logger.exception("傳送不支援格式提示失敗（telegram_user_id=%s）", unsupported_user_id)
        return jsonify({"ok": True}), 200

    if photo_extracted is not None:
        telegram_user_id = photo_extracted[0]
    elif voice_extracted is not None:
        telegram_user_id = voice_extracted[0]
    else:
        telegram_user_id = text_extracted[0]

    reply = _UNEXPECTED_ERROR_REPLY
    db = None
    try:
        db = CloudSQLClient()
        if photo_extracted is not None:
            _, file_id, caption = photo_extracted
            telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
            # 影像辨識用的兩把 Key（見 robinson SPEC.md ADR-13），隨機挑一把使用，分散額度消耗。
            gdrive_client = GDriveClient(
                key_file_path=os.environ["GDRIVE_KEY_FILE_PATH"], folder_id=os.environ["GDRIVE_FOLDER_ID"]
            )
            image_llm_clients = [
                LLMClient(api_key=os.environ["GEMINI_API_IMAGE_KEY1"]),
                LLMClient(api_key=os.environ["GEMINI_API_IMAGE_KEY2"]),
            ]
            reply = handle_photo_message(
                db,
                _state_store,
                telegram_user_id,
                file_id,
                caption,
                telegram_client,
                gdrive_client,
                image_llm_clients,
                privacy_llm_client=_build_privacy_llm_client(),
            )
        elif voice_extracted is not None:
            _, file_id, duration_seconds, mime_type = voice_extracted
            telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
            gdrive_client = GDriveClient(
                key_file_path=os.environ["GDRIVE_KEY_FILE_PATH"], folder_id=os.environ["GDRIVE_FOLDER_ID"]
            )
            voice_client = VoiceClient(api_key=os.environ["VOICE_API_KEY"])
            # 轉出來的文字會被當成一般文字訊息處理（見 router.handle_voice_message），
            # 所以也需要一般聊天核心用的兩把 Key（同下方文字分支）。
            llm_client = LLMClient(api_key=os.environ["GEMINI_API_BOT_KEY"])
            text_llm_client = LLMClient(api_key=os.environ["GEMINI_API_TEXT_KEY"])
            reply = handle_voice_message(
                db,
                _state_store,
                telegram_user_id,
                file_id,
                duration_seconds,
                telegram_client,
                gdrive_client,
                voice_client,
                llm_client=llm_client,
                text_llm_client=text_llm_client,
                mime_type=mime_type,
                voice_lockout_store=_voice_lockout_store,
                privacy_llm_client=_build_privacy_llm_client(),
            )
        else:
            _, text = text_extracted
            # 一般問答用的 Key（見 docs/specs/chat-core/SPEC.md ADR-12）與長記憶摘要用的 Key（ADR-3），
            # 只有訊息真的落入一般聊天核心時才會被呼叫；其餘指令/對話流程分支不會用到。
            llm_client = LLMClient(api_key=os.environ["GEMINI_API_BOT_KEY"])
            text_llm_client = LLMClient(api_key=os.environ["GEMINI_API_TEXT_KEY"])
            reply = handle_message(
                db, _state_store, telegram_user_id, text, llm_client=llm_client, text_llm_client=text_llm_client,
                privacy_llm_client=_build_privacy_llm_client(),
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
