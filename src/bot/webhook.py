"""Telegram Webhook 入口（對應 docs/specs/platform-auth/SPEC.md FR-1）。"""
import logging
import os
import traceback
from collections import OrderedDict
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from google.genai import errors as genai_errors

from src.bot import system_errors
from src.bot.router import (
    handle_callback_query,
    handle_message,
    handle_photo_message,
    handle_voice_message,
)
from src.bot.state import ConversationStateStore
from submodules.calendar.client import CalendarClient
from submodules.cloudsql.client import CloudSQLClient
from submodules.email.client import EmailClient
from submodules.gdrive.client import GDriveClient
from submodules.llm.client import LLMClient, LLMQuotaGuardError
from submodules.telegram.client import TelegramClient
from submodules.voice.client import VoiceClient

bot_bp = Blueprint("bot", __name__)

# Owner /set_invite_codes 對話狀態，整個 process 生命週期內共用一份（ADR-2：僅存於記憶體）。
_state_store = ConversationStateStore()

# 2026-08-02（FR-14 規則 1）：語音超時鎖定的獨立記憶體儲存，與 `_state_store` 是不同用途、
# 不同生命週期概念的兩份資料，故意分開，避免跟對話流程的 `flow` 分派狀態混在一起。
_voice_lockout_store = ConversationStateStore()

_logger = logging.getLogger(__name__)

# 2026-08-07（Step 2.6，見 robinson SPEC.md FR-19f／FR-19g）：分級降級的兩句固定範本，
# 一律不經過 LLM 生成（節省 Token，也因為「重大疾病級」的定義就是 LLM 本身已經叫不動了）。
#
# 「一般感冒級」（FR-19f）：LLM API 本身仍可正常運作，只是其他元件（DB／GDrive／Calendar／
# Telegram 送出以外的其他呼叫等）暫時異常，且已用盡 FR-19i 的重試機制。
_GENERAL_COLD_REPLY = (
    "🤒 主任，我好像有點小感冒（系統暫時性異常），不過別擔心！"
    "我已經自動紀錄日誌通知 Robin 處理囉，請稍後再試一次！"
)

# 「重大疾病級」（FR-19g）：Try 區塊執行到呼叫 LLM API 本身直接拋出例外（Gemini 伺服器錯誤、
# API Key 失效、額度用罄、本地端節流保護觸發等，且已用盡 FR-19i 重試機制），代表 LLM 已完全
# 無法處理任何請求，此時完全繞過 LLM，直接回這句寫死在後端的靜態字串。
_MAJOR_ILLNESS_REPLY = (
    "🚨 主人與各位家人非常抱歉，我最近患上了重大的疾病（AI 核心服務暫時無法運作），"
    "目前無法回答任何問題。Robin 已收到緊急通知並正在全力搶救中！"
)

# 2026-08-02 追加修正（見 robinson SPEC.md FR-19，Robin 回報「打了訊息 Robinson 完全不理我」）：
# 根因是沒有拋出例外，但 Gemini 那次生成剛好回傳空字串，導致 `reply` 被覆寫成 ""，連預設的
# `_GENERAL_COLD_REPLY` 安全網都被蓋掉，下面 `if reply:` 判斷為 False、完全不送出任何
# Telegram 訊息——使用者只會看到已讀不回，連安全用語都收不到。用不同措辭跟例外安全網區分，
# 讓使用者知道是「這句沒接上」而不是「系統掛了」，鼓勵他換句話說再試一次。
_EMPTY_REPLY_FALLBACK = "不好意思，我剛剛好像沒接上你的話，可以再說一次或換個方式講講看嗎？"

# 目前支援文字、圖片、語音（voice 與 audio 兩種訊息類型都算，見 _extract_voice），
# 收到其他格式（文件/影片/貼圖等）直接回這句拒絕，不進入 DB/Gemini 流程，符合 FR-17
# 「僅支援圖片與音檔兩種格式」的承諾。
_UNSUPPORTED_FORMAT_REPLY = "我只能處理對話框文字、語音、圖片和音檔喔！"
_UNSUPPORTED_FILE_KEYS = ("document", "video", "video_note", "animation", "sticker")

# 見 docs/specs/platform-auth/SPEC.md FR-7a：Telegram 在沒收到 200 時會自動重送同一則
# update（不只發生在我們自己出錯的時候，網路延遲也可能讓 Telegram 誤判逾時而重送），
# 用一個有上限的 LRU 記錄最近處理過的 update_id，收到重複的直接短路回 200、不重跑任何邏輯，
# 避免同一則訊息被重複拿去打 Gemini。上限避免長時間運行下記憶體無限增長。
_PROCESSED_UPDATE_IDS_MAXLEN = 1000
_processed_update_ids: "OrderedDict[int, None]" = OrderedDict()


# 2026-08-02（Step 1.6，見 robinson SPEC.md FR-19a）：簡化版通知，Phase 1 不含 AI 自主診斷
# （那是 Step 2.4 的事），只把完整 Traceback 加上發生情境私訊給 Robin，讓他自己判斷原因。
# 2026-08-05（Step 2.4，見 FR-19b、ADR-15）：額外附上完整錯誤 log 的 Google Drive 連結
# （`{log_link_line}`，上傳失敗時這行會是空字串，優雅降級不影響訊息本身送出）。
_ROBIN_ERROR_NOTIFY_TEMPLATE = (
    "🐛 系統發生未預期例外\n"
    "{error_id_line}"
    "時間：{timestamp}\n"
    "觸發功能：{feature}\n"
    "使用者 Telegram ID：{telegram_user_id}\n"
    "輸入摘要：{input_summary}\n\n"
    "Traceback：\n{traceback_text}"
    "{log_link_line}"
)

# 2026-08-07（Step 2.6，見 FR-19g）：「重大疾病級」私訊 Robin 時，在既有通知內容前面
# 加這段最高等級告警橫幅，讓他一眼就能從眾多訊息中分辨這是「LLM 核心完全掛掉」而不是
# 一般的暫時性小問題（一般感冒級沒有這段橫幅，內容格式不變）。
_CRITICAL_SEVERITY_BANNER = "🚨🚨🚨 最高等級告警：LLM 核心服務故障（重大疾病級） 🚨🚨🚨\n\n"

# FR-19b：上傳到 Google Drive 的完整錯誤 log 檔案內容範本，跟 Telegram 訊息分開排版
# （這份不受 Telegram 4096 字元上限限制，Traceback 一律完整、不截斷）。
_ERROR_LOG_FILE_TEMPLATE = (
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


def _upload_error_log(filename: str, content: bytes) -> str | None:
    """FR-19b：把完整錯誤 log 上傳 Google Drive（複用 Step 1.3b 既有的 `GDriveClient`），
    回傳可分享的 `webViewLink`。

    任何失敗都回傳 `None`（環境變數未設定、Google Drive API 暫時性錯誤等），由呼叫端優雅降級成
    訊息中略過連結欄位——上傳失敗絕對不能影響「生病了」安全用語與私訊 Robin 這兩件事本身正常
    運作，這是 FR-19b 明確要求的優雅降級行為。
    """
    try:
        gdrive_client = GDriveClient(
            refresh_token=os.environ["GDRIVE_OAUTH_REFRESH_TOKEN"],
            client_id=os.environ["GDRIVE_OAUTH_CLIENT_ID"],
            client_secret=os.environ["GDRIVE_OAUTH_CLIENT_SECRET"],
            folder_id=os.environ["GDRIVE_FOLDER_ID"],
        )
        return gdrive_client.upload_file(filename, content, mime_type="text/plain")
    except Exception:
        _logger.exception("上傳錯誤 log 至 Google Drive 失敗，私訊 Robin 的訊息將略過連結")
        return None


def _send_email_fallback(subject: str, body: str) -> bool:
    """FR-19b 追加：Telegram 本身故障時的備援通知管道（見 robinson SPEC.md ADR-16）。

    Telegram 是 Robinson 唯一的對外管道，一旦 Telegram API 本身掛掉或 `TELEGRAM_BOT_TOKEN`
    失效，私訊 Robin 這件事本身就送不出去，連錯誤通知都收不到。這裡用完全獨立的 Gmail SMTP
    （`submodules/email/client.py`）當最後一道防線，只在 Telegram 送達失敗時才觸發。

    `GMAIL_USER`／`GMAIL_PASSWORD` 沒設定，或寄信本身也失敗（Gmail 也在鬧脾氣、App Password
    失效等），一律只記警告/例外 log、不往外拋——這是最後一道備援，沒有再下一層可以退了，失敗
    也不能讓呼叫端整個處理流程崩潰。
    """
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_PASSWORD")
    if not gmail_user or not gmail_password:
        _logger.warning("Telegram 私訊 Robin 失敗，且未設定 GMAIL_USER/GMAIL_PASSWORD，無法寄送備援 email 通知")
        return False
    try:
        EmailClient(username=gmail_user, password=gmail_password).send_text(
            to=gmail_user, subject=subject, body=body
        )
        return True
    except Exception:
        _logger.exception("備援 email 通知寄送失敗，Robin 這次完全沒有收到任何主動通知")
        return False


def _notify_robin_of_error(
    feature: str, telegram_user_id: int, input_summary: str, *, severity: str = "general", db=None
) -> int | None:
    """FR-19a／FR-19b：例外發生時，除了 log（見呼叫端的 `_logger.exception`），額外私訊 Robin
    完整原始 Traceback，並把完整錯誤 log 上傳 Google Drive、附上專屬連結（見 ADR-15，
    supersede 原本 Step 2.4 規劃的 AI 自主診斷／GitHub PR 機制），讓 Robin 自己判斷原因、決定
    要不要修復（甚至可另外請 Claude Code 協助排查）；修復後由 FR-20 Owner 選單
    選擇事故與收件人。Telegram 本身送達失敗時，改寄 email 備援通知。

    **這個函式只會私訊 Robin 一人**（`ROBIN_TELEGRAM_TOKEN`），觸發當下的一般使用者與其他家人
    完全不會看到這裡的任何內容——他們收到的是 `webhook.py` 主流程另外送出的 `_GENERAL_COLD_REPLY`
    或 `_MAJOR_ILLNESS_REPLY` 安全用語，兩者是完全獨立的兩條訊息路徑，任何情況下都不能混在一起。

    `severity`（2026-08-07，Step 2.6，見 FR-19g）：`"critical"` 時在通知內容前面加上
    `_CRITICAL_SEVERITY_BANNER` 最高等級告警橫幅，讓 Robin 一眼區分這是 LLM 核心完全掛掉
    （FR-19g 重大疾病級），還是其他元件的一般暫時性問題（FR-19f 一般感冒級，預設值
    `"general"`，不加橫幅）；除了這段前綴，其餘通知內容與送達邏輯完全相同。

    分兩段 try/except：第一段組裝通知內容（Traceback、log 上傳），失敗就直接放棄（沒有內容可
    寄，email 備援也無用武之地）；第二段專門負責「透過 Telegram 送達」，只有這段失敗才觸發
    email 備援——這樣才能準確分辨「是 Telegram 本身送不出去」還是「連內容都組不出來」兩種
    不同的失敗情境。整段任何失敗都絕對不能反過來讓這個「錯誤通知」本身變成另一個未被捕捉的
    例外，那樣就本末倒置了；沒設定必要環境變數時直接跳過，不視為錯誤。

    `db`（2026-08-09，見 FR-19j）：選配，提供時額外把這次錯誤寫入 `system_error_reports`
    （見 `src/bot/system_errors.py`），並在私訊內容前面附上「錯誤ID=N」，讓 Robin 之後可以用
    Telegram 指令「錯誤ID=N 已處理：{解法內容}」記錄解法；`db` 為 `None` 或寫入本身失敗時，
    優雅降級成不附這行、其餘通知流程完全不受影響（比照 FR-19b 既有的 Drive 上傳優雅降級精神）。
    """
    owner_chat_id = os.environ.get("ROBIN_TELEGRAM_TOKEN")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not owner_chat_id or not bot_token:
        return None

    report_id = None
    try:
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S UTC")
        traceback_text = traceback.format_exc()

        log_content = _ERROR_LOG_FILE_TEMPLATE.format(
            timestamp=timestamp,
            feature=feature,
            telegram_user_id=telegram_user_id,
            input_summary=input_summary,
            traceback_text=traceback_text,
        ).encode("utf-8")
        log_filename = f"error_log_{now.strftime('%Y%m%d_%H%M%S')}_{feature}.log"
        log_link = _upload_error_log(log_filename, log_content)
        log_link_line = f"\n\n📄 完整 log（含未截斷 Traceback）：{log_link}" if log_link else ""

        error_id_line = ""
        if db is not None:
            try:
                error_summary = traceback_text.strip().splitlines()[-1] if traceback_text.strip() else feature
                report_id = system_errors.record_error_report(
                    db,
                    severity=severity,
                    triggering_feature=feature,
                    error_summary=error_summary,
                    drive_log_url=log_link,
                )
                error_id_line = f"🔖 錯誤ID={report_id}（可用「錯誤ID={report_id} 已處理：...」記錄解法）\n"
            except Exception:
                _logger.exception("寫入 system_error_reports 失敗，私訊 Robin 的訊息將略過錯誤 ID")

        message = _ROBIN_ERROR_NOTIFY_TEMPLATE.format(
            error_id_line=error_id_line,
            timestamp=timestamp,
            feature=feature,
            telegram_user_id=telegram_user_id,
            input_summary=input_summary,
            # Telegram 訊息長度上限 4096 字元，扣掉模板其餘欄位後留給 Traceback 的緩衝空間；
            # 完整、不截斷的版本在上面已經上傳到 Google Drive，透過 log_link_line 提供連結。
            traceback_text=traceback_text[-3200:],
            log_link_line=log_link_line,
        )
        if severity == "critical":
            message = _CRITICAL_SEVERITY_BANNER + message
    except Exception:
        _logger.exception("組裝 Robin 錯誤通知內容失敗，無法送出任何通知（含 email 備援）")
        return report_id

    try:
        TelegramClient(bot_token).send_text(chat_id=owner_chat_id, text=message)
        if db is not None and report_id is not None:
            try:
                system_errors.update_owner_notification(db, report_id, "telegram", True)
            except Exception:
                _logger.exception("更新 Robin Telegram 通知送達狀態失敗")
    except Exception:
        _logger.exception("私訊 Robin 錯誤通知失敗（Telegram 本身可能故障），改嘗試 email 備援通知")
        email_delivered = _send_email_fallback(
            subject=f"🐛 Robinson 系統例外通知（Telegram 無法送達，觸發功能：{feature}）",
            body=message,
        )
        if db is not None and report_id is not None:
            try:
                system_errors.update_owner_notification(
                    db, report_id, "email" if email_delivered else None, email_delivered
                )
            except Exception:
                _logger.exception("更新 Robin 錯誤通知送達狀態失敗")
    return report_id


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


def _build_bot_llm_clients_optional() -> tuple[LLMClient | None, LLMClient | None, list[LLMClient]]:
    """建立 callback_query 分支選配的一般聊天／長記憶／影像辨識 Client（2026-08-16，全站語音
    確認機制）。

    比照 `_build_privacy_llm_client()`／`_build_gdrive_client_optional()` 的優雅降級慣例：
    絕大多數 callback（選單導覽、按鈕操作）完全用不到 LLM，只有 `voice_confirm:accept` 接回
    自由聊天或某些 pending flow 時才需要，所以不比照文字/語音訊息分支用 `os.environ[...]`
    強制要求，缺少對應環境變數時回傳 `None`／空清單，不會讓整個 callback_query 處理流程因為
    這幾把 Key 沒設好而失敗（`handle_callback_query()` 對應分支會再各自優雅降級）。
    """
    bot_key = os.environ.get("GEMINI_API_BOT_KEY")
    text_key = os.environ.get("GEMINI_API_TEXT_KEY")
    image_key1 = os.environ.get("GEMINI_API_IMAGE_KEY1")
    image_key2 = os.environ.get("GEMINI_API_IMAGE_KEY2")
    llm_client = LLMClient(api_key=bot_key) if bot_key else None
    text_llm_client = LLMClient(api_key=text_key) if text_key else None
    image_llm_clients = [LLMClient(api_key=key) for key in (image_key1, image_key2) if key]
    return llm_client, text_llm_client, image_llm_clients


def _build_gdrive_client_optional() -> GDriveClient | None:
    """建立文字訊息分支選配的 GDriveClient（見 robinson SPEC.md FR-35e）。

    跟 `_build_calendar_client()` 一樣是選配的：目前文字訊息只有「已上傳 XXX」這個罕見分支
    才需要 Drive 存取，絕大多數文字訊息（一般聊天、其他指令）完全用不到，所以刻意不比照
    photo/voice 分支用 `os.environ[...]` 強制要求，改成環境變數不完整時優雅降級回傳 `None`，
    不會讓整個文字訊息處理流程因為這組（其實已經在其他分支驗證過的）憑證缺漏而失敗。
    """
    refresh_token = os.environ.get("GDRIVE_OAUTH_REFRESH_TOKEN")
    client_id = os.environ.get("GDRIVE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GDRIVE_OAUTH_CLIENT_SECRET")
    folder_id = os.environ.get("GDRIVE_FOLDER_ID")
    if not (refresh_token and client_id and client_secret and folder_id):
        return None
    return GDriveClient(
        refresh_token=refresh_token, client_id=client_id, client_secret=client_secret, folder_id=folder_id,
    )


def _build_calendar_client() -> CalendarClient | None:
    """建立 Google Calendar 同步用的 CalendarClient（見 robinson SPEC.md FR-66、ADR-17）。

    跟 `_build_privacy_llm_client()` 一樣是選配的：`GOOGLE_CALENDAR_*` 四個環境變數還沒設定
    完整時回傳 `None`，`commands.py` 的待辦事項/體態目標同步流程會優雅降級成「照常記錄，但
    不會出現在 Calendar 上」，不會讓整個訊息處理流程失敗（這組憑證跟 `gdrive` 各自獨立，
    見 docs/specs/submodules-core/SPEC.md ADR-12）。
    """
    refresh_token = os.environ.get("GOOGLE_CALENDAR_OAUTH_REFRESH_TOKEN")
    client_id = os.environ.get("GOOGLE_CALENDAR_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET")
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID")
    if not (refresh_token and client_id and client_secret and calendar_id):
        return None
    return CalendarClient(
        refresh_token=refresh_token, client_id=client_id, client_secret=client_secret, calendar_id=calendar_id,
    )


def _is_llm_failure(exc: Exception) -> bool:
    """FR-19g（2026-08-07，Step 2.6）：判斷這次未預期例外是否屬於「LLM API 本身」失敗
    （Gemini 伺服器錯誤、API Key 失效、額度用罄、本地端節流保護觸發等，已用盡 FR-19i 的
    重試機制），而非其他元件（DB／GDrive／Calendar／Telegram 等）的暫時性問題（FR-19f）。

    `LLMQuotaGuardError`（`submodules/llm` 本地端節流保護，見 ADR-5）與
    `google.genai.errors.APIError`（涵蓋 `ServerError`／`ClientError`，即 Gemini 官方
    回傳的所有錯誤）是唯獨呼叫 LLM 才會拋出的例外型別，不會跟 `psycopg2`、
    `googleapiclient`、`requests` 等其他元件的例外混淆，用它們當分類依據最準確。
    """
    return isinstance(exc, (LLMQuotaGuardError, genai_errors.APIError))


def _broadcast_major_illness_to_family(
    db: CloudSQLClient | None, exclude_telegram_user_id: int, report_id: int | None = None
) -> None:
    """FR-19g：LLM 核心服務故障時，除了觸發當下的使用者已經透過主流程的 `reply` 收到
    `_MAJOR_ILLNESS_REPLY`，額外主動廣播同一句話給「所有已綁定的家人帳號」。

    刻意排除兩種人：① Robin 自己（`is_owner = TRUE`）——他走 `_notify_robin_of_error()`
    的最高等級 StackTrace 告警，不是這句給家人看的安全用語 ② 觸發當下的使用者
    （`exclude_telegram_user_id`）——他已經透過主流程另外收到同一句話，這裡不重複發送。

    這個函式發生的任何失敗（DB 查詢失敗、Telegram 送不出去）都只能記 log，絕對不能再往外
    拋出——它本身就是在處理另一個未預期例外的安全網內部，若這裡又炸出新的未預期例外，
    會讓整個安全網失去意義；單一家人傳送失敗不影響其他人，逐一 try/except 後繼續下一位
    每位收件人的送達結果獨立記錄，單一失敗不影響其他人。
    """
    if db is None:
        _logger.warning("重大疾病級廣播略過：db 連線不可用")
        return
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        _logger.warning("重大疾病級廣播略過：未設定 TELEGRAM_BOT_TOKEN")
        return

    try:
        family_users = db.select(
            "users",
            columns=("id", "telegram_user_id"),
            where="telegram_user_id IS NOT NULL AND is_owner = FALSE",
        )
    except Exception:
        _logger.exception("重大疾病級廣播查詢家人清單失敗")
        return

    telegram_client = TelegramClient(bot_token)
    for user in family_users:
        target_telegram_user_id = user["telegram_user_id"]
        if target_telegram_user_id == exclude_telegram_user_id:
            continue
        delivery_status = "sent"
        try:
            telegram_client.send_text(chat_id=target_telegram_user_id, text=_MAJOR_ILLNESS_REPLY)
        except Exception:
            delivery_status = "failed"
            _logger.exception("重大疾病級廣播給 telegram_user_id=%s 失敗", target_telegram_user_id)
        if report_id is not None and user.get("id") is not None:
            try:
                system_errors.record_notification_result(
                    db, report_id, user["id"], "incident", delivery_status
                )
            except Exception:
                _logger.exception("記錄重大疾病級廣播送達結果時發生錯誤")


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


def _extract_voice(payload: dict) -> tuple[int, str, int | None, str, bool] | None:
    """取出 (telegram_user_id, file_id, duration, mime_type, is_uploaded_audio)。

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
    is_uploaded_audio = "audio" in message and "voice" not in message
    media = message.get("voice") or message.get("audio")
    if telegram_user_id is None or not media:
        return None
    file_id = media.get("file_id")
    if not file_id:
        return None
    mime_type = media.get("mime_type") or "audio/ogg"
    return telegram_user_id, file_id, media.get("duration"), mime_type, is_uploaded_audio


def _extract_callback_query(payload: dict) -> tuple[int, str, str] | None:
    """從 Telegram Update JSON 取出 (telegram_user_id, callback_query_id, data)。

    2026-08-15（Phase 6 第二批 2a，按鈕基礎設施）：按下 Inline Keyboard 按鈕時，Telegram
    送來的是 `callback_query` 更新（不是 `message`），寫法比照 `extract_message()` 等既有
    parser：缺少任一必要欄位一律回傳 `None`，交由呼叫端忽略。
    """
    callback_query = payload.get("callback_query") or {}
    from_user = callback_query.get("from") or {}
    telegram_user_id = from_user.get("id")
    callback_query_id = callback_query.get("id")
    data = callback_query.get("data")
    if telegram_user_id is None or callback_query_id is None or data is None:
        return None
    return telegram_user_id, callback_query_id, data


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


def _handle_callback_query_update(callback_extracted: tuple[int, str, str]):
    """處理按鈕按下的 callback_query 更新（2026-08-15，Phase 6 第二批 2a）。

    跟文字/圖片/語音三種既有訊息類型分開處理：一定要呼叫 `answerCallbackQuery`（見
    `submodules/telegram/client.py` docstring），否則使用者手機上的 Telegram 客戶端會卡在
    按鈕轉圈圈的 loading 狀態。這裡刻意走獨立、精簡的 try/except，不重用文字訊息分支那套
    「一般感冒級／重大疾病級」分級安全網（callback_query 不會呼叫 LLM，失敗模式單純很多），
    失敗時只記錄 log 並盡量呼叫 answerCallbackQuery 讓按鈕停止轉圈，不觸發 Robin 錯誤私訊。

    2026-08-16（Phase 6 第二批 2f）起額外注入 `_build_calendar_client()`：待辦事項的
    「✅ 確認送出」／「✅ 完成」／「🚫 取消」這幾個 callback 需要建立/刪除 Google Calendar
    事件，是第一個需要在按鈕流程用到 Calendar 的批次，沿用既有 `_build_calendar_client()`
    的優雅降級（`None` 時待辦事項照常記錄/更新，只是不會出現在 Calendar 上）。

    2026-08-16（全站語音確認機制）起額外注入 `llm_client`／`text_llm_client`／`privacy_llm_client`／
    `telegram_client`／`gdrive_client`：`voice_confirm:accept` 這個 callback 要接回轉錄前原本
    卡在的任何流程（甚至是自由聊天），需要跟文字訊息分支同一套完整 Client；其餘既有 callback
    分支都不會用到這幾個參數，不影響原本的行為與失敗模式。
    """
    telegram_user_id, callback_query_id, data = callback_extracted
    db = None
    try:
        db = CloudSQLClient()
        llm_client, text_llm_client, image_llm_clients = _build_bot_llm_clients_optional()
        reply, reply_markup = handle_callback_query(
            db, _state_store, telegram_user_id, data,
            calendar_client=_build_calendar_client(),
            llm_client=llm_client,
            text_llm_client=text_llm_client,
            image_llm_clients=image_llm_clients,
            privacy_llm_client=_build_privacy_llm_client(),
            telegram_client=TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"]),
            gdrive_client=_build_gdrive_client_optional(),
        )
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

    reply = _GENERAL_COLD_REPLY
    reply_markup = None
    db = None
    incident_report_id = None
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
            _, file_id, duration_seconds, mime_type, is_uploaded_audio = voice_extracted
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
            voice_result = handle_voice_message(
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
                is_uploaded_audio=is_uploaded_audio,
                voice_lockout_store=_voice_lockout_store,
                privacy_llm_client=_build_privacy_llm_client(),
                calendar_client=_build_calendar_client(),
            )
            # 2026-08-16（全站語音確認機制）：轉錄成功時 `handle_voice_message()` 回傳
            # `(text, reply_markup)` 二元組（貼出轉錄文字＋確認按鈕），比照下方文字訊息分支
            # 同一套拆解方式；其餘提早擋下的分支仍是純 `str`。
            if isinstance(voice_result, tuple):
                reply, reply_markup = voice_result
            else:
                reply = voice_result
        else:
            _, text = text_extracted
            # 一般問答用的 Key（見 docs/specs/chat-core/SPEC.md ADR-12）與長記憶摘要用的 Key（ADR-3），
            # 只有訊息真的落入一般聊天核心時才會被呼叫；其餘指令/對話流程分支不會用到。
            llm_client = LLMClient(api_key=os.environ["GEMINI_API_BOT_KEY"])
            text_llm_client = LLMClient(api_key=os.environ["GEMINI_API_TEXT_KEY"])
            message_result = handle_message(
                db, _state_store, telegram_user_id, text, llm_client=llm_client, text_llm_client=text_llm_client,
                privacy_llm_client=_build_privacy_llm_client(), telegram_client=telegram_client,
                calendar_client=_build_calendar_client(), gdrive_client=_build_gdrive_client_optional(),
            )
            # 2026-08-15（Phase 6 第二批 2a）：`/start` 與部分選單導覽會回傳 `(text, reply_markup)`
            # 二元組，其餘既有指令/對話流程分支維持回傳純 `str`，這裡統一拆解成兩個區域變數，
            # 讓下面的空字串防呆與最終送出都只需要處理一種型別。
            if isinstance(message_result, tuple):
                reply, reply_markup = message_result
            else:
                reply = message_result
    except Exception as exc:
        # 安全網：任何未預期例外都要在這裡吞掉，改回安全用語並仍然回 200——否則 Flask 會回
        # 500，Telegram 收不到 200 就會自動重送同一則訊息，變成「失敗 → 重試 → 再失敗」的
        # 迴圈，把 API 額度燒得更快。FR-19i 的重試機制已經在各 submodules/*/client.py
        # 內建完成（見 submodules-core SPEC.md ADR-13），走到這裡代表 3 次重試已經全部
        # 用盡，正式判定這次 Request 失敗，才進入下面的分級降級。
        #
        # 2026-08-07（Step 2.6，見 FR-19f／FR-19g）：依錯誤來源分兩級——
        # 「重大疾病級」：LLM API 本身直接拋出例外（`_is_llm_failure()` 判定），代表 LLM
        # 已完全無法處理任何請求，完全繞過 LLM 回寫死的 `_MAJOR_ILLNESS_REPLY`，向 Robin
        # 推播最高等級告警，並廣播給所有已綁定家人。
        # 「一般感冒級」：其他情況（DB／GDrive／Calendar／解析邏輯等元件異常），回
        # `_GENERAL_COLD_REPLY`，私訊 Robin 完整錯誤詳情即可，不需要廣播全員。
        # FR-19a：兩種情況都會記錄完整 Traceback 與情境到 log，並私訊 Robin 原始內容
        # （簡化版通知，見 Step 2.4）。
        _logger.exception(
            "處理 Telegram 訊息時發生未預期例外（觸發功能=%s，telegram_user_id=%s），已回覆安全用語並停止重試",
            error_feature,
            telegram_user_id,
        )
        reply_markup = None
        if _is_llm_failure(exc):
            reply = _MAJOR_ILLNESS_REPLY
            incident_report_id = _notify_robin_of_error(
                error_feature, telegram_user_id, error_input_summary, severity="critical", db=db
            )
            _broadcast_major_illness_to_family(db, telegram_user_id, incident_report_id)
        else:
            reply = _GENERAL_COLD_REPLY
            incident_report_id = _notify_robin_of_error(
                error_feature, telegram_user_id, error_input_summary, severity="general", db=db
            )

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
        reply_markup = None

    if reply:
        reply_delivery_status = "sent"
        try:
            telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])
            # 2026-08-15（Phase 6 第二批 2a）：只有真的有選單按鈕時才多帶這個關鍵字參數，維持既有
            # 「純文字回覆」測試斷言 `send_text(chat_id=..., text=...)` 不需要跟著全部改寫。
            if reply_markup is not None:
                telegram_client.send_text(chat_id=telegram_user_id, text=reply, reply_markup=reply_markup)
            else:
                telegram_client.send_text(chat_id=telegram_user_id, text=reply)
        except Exception:
            reply_delivery_status = "failed"
            # 傳送失敗（例如 Telegram API 本身出問題）是另一個獨立的失敗模式，不影響前面
            # handle_message 的處理結果，一樣只記錄不往外拋，避免這裡也觸發 Telegram 重試。
            _logger.exception("傳送 Telegram 回覆失敗（telegram_user_id=%s）", telegram_user_id)
        if db is not None and incident_report_id is not None:
            try:
                user = db.select(
                    "users", where="telegram_user_id = %s", params=(telegram_user_id,), fetch_one=True
                )
                if user is not None and not user.get("is_owner"):
                    system_errors.record_notification_result(
                        db, incident_report_id, user["id"], "incident", reply_delivery_status
                    )
            except Exception:
                _logger.exception("記錄事故通知送達結果時發生錯誤")

    if db is not None:
        db.close()

    return jsonify({"ok": True}), 200
