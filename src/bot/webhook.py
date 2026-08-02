"""Telegram Webhook 入口（對應 docs/specs/platform-auth/SPEC.md FR-1）。"""
import logging
import os
import traceback
from collections import OrderedDict
from datetime import datetime, timezone

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

# FR-19：對外一律回這句安全用語，不揭露技術細節（Traceback 只私訊 Robin，見 FR-19a）。
# 完整的「一般感冒級／重大疾病級」分級降級（FR-19f/FR-19g，需要區分是不是 LLM 本身掛掉）
# 留待 Phase 2 Step 2.6，Phase 1 先用同一句安全用語涵蓋所有未預期例外。
_UNEXPECTED_ERROR_REPLY = "羅賓森好像不太舒服，等一下再試試看喔！"

# 2026-08-02 追加修正（見 robinson SPEC.md FR-19，Robin 回報「打了訊息 Robinson 完全不理我」）：
# 根因是沒有拋出例外，但 Gemini 那次生成剛好回傳空字串，導致 `reply` 被覆寫成 ""，連預設的
# `_UNEXPECTED_ERROR_REPLY` 安全網都被蓋掉，下面 `if reply:` 判斷為 False、完全不送出任何
# Telegram 訊息——使用者只會看到已讀不回，連安全用語都收不到。用不同措辭跟例外安全網區分，
# 讓使用者知道是「這句沒接上」而不是「系統掛了」，鼓勵他換句話說再試一次。
_EMPTY_REPLY_FALLBACK = "不好意思，我剛剛好像沒接上你的話，可以再說一次或換個方式講講看嗎？"

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


# 2026-08-02（Step 1.6，見 robinson SPEC.md FR-19a）：簡化版通知，Phase 1 不含 AI 自主診斷
# （那是 Step 2.4 的事），只把完整 Traceback 加上發生情境私訊給 Robin，讓他自己判斷原因。
_ROBIN_ERROR_NOTIFY_TEMPLATE = (
    "🐛 系統發生未預期例外\n"
    "時間：{timestamp}\n"
    "觸發功能：{feature}\n"
    "使用者 Telegram ID：{telegram_user_id}\n"
    "輸入摘要：{input_summary}\n\n"
    "Traceback：\n{traceback_text}"
)


def _summarize_user_input(text: str | None, max_len: int = 300) -> str:
    """FR-19a：私訊 Robin 的錯誤通知裡附上「使用者輸入摘要」，過長時截斷，避免整則訊息
    （摘要 + Traceback）超過 Telegram 單則訊息 4096 字元上限。
    """
    if not text:
        return "(無文字內容)"
    text = text.strip()
    if len(text) > max_len:
        return text[:max_len] + "...（已截斷）"
    return text


def _notify_robin_of_error(feature: str, telegram_user_id: int, input_summary: str) -> None:
    """FR-19a 簡化版通知：例外發生時，除了 log（見呼叫端的 `_logger.exception`），額外私訊
    Robin 完整原始 Traceback，讓他自己判斷原因並決定要不要修復；修復後可用 `/recovered`
    （FR-20）廣播給所有人。

    整段包在 try/except 裡：私訊失敗（例如 Telegram API 本身也在鬧脾氣、或
    `ROBIN_TELEGRAM_TOKEN`／`TELEGRAM_BOT_TOKEN` 沒設定）絕對不能反過來讓這個「錯誤通知」
    本身變成另一個未被捕捉的例外，那樣就本末倒置了；沒設定必要環境變數時直接跳過，不視為錯誤。
    """
    owner_chat_id = os.environ.get("ROBIN_TELEGRAM_TOKEN")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not owner_chat_id or not bot_token:
        return
    try:
        message = _ROBIN_ERROR_NOTIFY_TEMPLATE.format(
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            feature=feature,
            telegram_user_id=telegram_user_id,
            input_summary=input_summary,
            # Telegram 訊息長度上限 4096 字元，扣掉模板其餘欄位後留給 Traceback 的緩衝空間。
            traceback_text=traceback.format_exc()[-3200:],
        )
        TelegramClient(bot_token).send_text(chat_id=owner_chat_id, text=message)
    except Exception:
        _logger.exception("私訊 Robin 錯誤通知失敗")


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

    # 2026-08-02（Step 1.6，見 FR-19a）：先把「觸發功能」與「使用者輸入摘要」算出來，不論後面
    # 哪個分支拋例外，except 區塊都能直接拿來組私訊 Robin 的錯誤通知內容。
    if photo_extracted is not None:
        telegram_user_id = photo_extracted[0]
        error_feature = "photo"
        error_input_summary = _summarize_user_input(photo_extracted[2])
    elif voice_extracted is not None:
        telegram_user_id = voice_extracted[0]
        error_feature = "voice"
        error_input_summary = f"語音/音檔訊息（duration={voice_extracted[2]}s, mime_type={voice_extracted[3]}）"
    else:
        telegram_user_id = text_extracted[0]
        error_feature = "text"
        error_input_summary = _summarize_user_input(text_extracted[1])

    reply = _UNEXPECTED_ERROR_REPLY
    db = None
    try:
        db = CloudSQLClient()
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
        if photo_extracted is not None:
            _, file_id, caption = photo_extracted
            # 影像辨識用的兩把 Key（見 robinson SPEC.md ADR-13），隨機挑一把使用，分散額度消耗。
            # gdrive 認證方式見 docs/specs/submodules-core/SPEC.md ADR-10（OAuth 2.0，真人帳號身分）。
            gdrive_client = GDriveClient(
                refresh_token=os.environ["GDRIVE_OAUTH_REFRESH_TOKEN"],
                client_id=os.environ["GDRIVE_OAUTH_CLIENT_ID"],
                client_secret=os.environ["GDRIVE_OAUTH_CLIENT_SECRET"],
                folder_id=os.environ["GDRIVE_FOLDER_ID"],
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
            gdrive_client = GDriveClient(
                refresh_token=os.environ["GDRIVE_OAUTH_REFRESH_TOKEN"],
                client_id=os.environ["GDRIVE_OAUTH_CLIENT_ID"],
                client_secret=os.environ["GDRIVE_OAUTH_CLIENT_SECRET"],
                folder_id=os.environ["GDRIVE_FOLDER_ID"],
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
                privacy_llm_client=_build_privacy_llm_client(), telegram_client=telegram_client,
            )
    except Exception:
        # 安全網（見 FR-19f/FR-19g，Phase 2 才會做完整的分級降級）：任何未預期例外（例如 Gemini
        # 429 額度超限、本地端節流保護 LLMQuotaGuardError、DB 連線失敗等）都要在這裡吞掉，改回
        # 安全用語並仍然回 200——否則 Flask 會回 500，Telegram 收不到 200 就會自動重送同一則
        # 訊息，變成「失敗 → 重試 → 再失敗」的迴圈，把 API 額度燒得更快。
        # FR-19a：除了記錄完整 Traceback 與情境到 log，額外私訊 Robin 原始 log（簡化版通知，
        # Phase 1 不含 AI 自主診斷，見 Step 2.4）。
        _logger.exception(
            "處理 Telegram 訊息時發生未預期例外（觸發功能=%s，telegram_user_id=%s），已回覆安全用語並停止重試",
            error_feature,
            telegram_user_id,
        )
        reply = _UNEXPECTED_ERROR_REPLY
        _notify_robin_of_error(error_feature, telegram_user_id, error_input_summary)
    finally:
        if db is not None:
            db.close()

    if not reply or not reply.strip():
        # 沒有例外、純粹是這次處理結果剛好是空字串（例如 Gemini 生成回傳空內容）：
        # 沒有 Traceback 可以私訊 Robin，先記警告 log 方便事後排查，並改用專屬的空字串安全網，
        # 避免使用者收到完全的已讀不回（見上方 `_EMPTY_REPLY_FALLBACK` 定義的說明）。
        _logger.warning(
            "處理結果為空字串（觸發功能=%s，telegram_user_id=%s），改用安全用語回覆，避免使用者完全收不到任何回應",
            error_feature,
            telegram_user_id,
        )
        reply = _EMPTY_REPLY_FALLBACK

    if reply:
        try:
            telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
            telegram_client.send_text(chat_id=telegram_user_id, text=reply)
        except Exception:
            # 傳送失敗（例如 Telegram API 本身出問題）是另一個獨立的失敗模式，不影響前面
            # handle_message 的處理結果，一樣只記錄不往外拋，避免這裡也觸發 Telegram 重試。
            _logger.exception("傳送 Telegram 回覆失敗（telegram_user_id=%s）", telegram_user_id)

    return jsonify({"ok": True}), 200
