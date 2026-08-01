"""語音辨識邏輯（對應 docs/specs/robinson/SPEC.md FR-14、FR-15、ADR-12、ADR-13）。

處理使用者傳來的語音訊息：上傳原始檔到 Google Drive（不落地存壓縮版，語音本身不需要
壓縮，比照 ADR-13 圖片「只存原始檔」的作法）→ 記錄 media_uploads（`media_type='audio'`）
→ 呼叫 Groq Whisper 轉出文字。轉出來的文字會被呼叫端（router.py）當成使用者「打字輸入」，
比照一般文字訊息走完整的指令/對話流程分派，這裡不重複那套邏輯，只負責「把語音變成文字」
這件事本身。下載 Telegram 檔案屬於 I/O 邊界，由呼叫端（webhook.py）處理完、把原始 bytes
傳進來。

FR-14（10 分鐘上限）／FR-15（15 分鐘修正窗口）這兩項檢查刻意設計成「不需要下載語音檔、
不需要呼叫任何外部服務就能判斷」，比照 webhook.py 對不支援檔案格式的既有作法先擋下、
避免浪費 Drive／Groq 額度：FR-14 用 Telegram 訊息本身就帶的 `duration` 秒數判斷（呼叫端
負責在下載前先呼叫 `exceeds_duration_limit()`）；FR-15 用 `media_uploads` 裡該使用者最近
一筆 `audio` 記錄的時間判斷（`is_within_correction_window()`），不需要額外的資料表或
記憶體狀態。
"""
from datetime import datetime, timedelta, timezone

from src.bot.media import save_media_upload
from submodules.cloudsql.client import CloudSQLClient

_MAX_DURATION_SECONDS = 600  # FR-14：語音訊息超過 10 分鐘強制中斷處理
_CORRECTION_WINDOW_MINUTES = 15  # FR-15：語音送出後 15 分鐘內僅能用打字修正


def exceeds_duration_limit(duration_seconds: int | None) -> bool:
    """FR-14：語音長度是否超過 10 分鐘上限；缺少時長資訊時保守放行（不擋）。"""
    return duration_seconds is not None and duration_seconds > _MAX_DURATION_SECONDS


def is_within_correction_window(db: CloudSQLClient, user_id: int, now: datetime | None = None) -> bool:
    """FR-15：該使用者是否還在「上一則語音送出後 15 分鐘內」的修正窗口——
    這段期間內若再傳語音，要拒絕並提醒改用打字，強制使用者用免費的文字修正，
    不要每次都重新花一次 Groq 額度重新辨識。

    只看最近一筆成功處理（已寫入 media_uploads）的語音記錄；被這個檢查擋下的嘗試本身
    不會產生新的 media_uploads 記錄，不會延長窗口。
    """
    now = now or datetime.now(timezone.utc)
    rows = db.select("media_uploads", where="user_id = %s AND media_type = %s", params=(user_id, "audio"))
    if not rows:
        return False
    latest_created_at = max(row["created_at"] for row in rows)
    return now - latest_created_at < timedelta(minutes=_CORRECTION_WINDOW_MINUTES)


def build_upload_filename(user_role: str, purpose: str = "語音辨識", now: datetime | None = None) -> str:
    """依 ADR-13 命名規則：使用者稱呼＋當下時間戳記＋用途。"""
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")
    return f"{user_role}_{timestamp}_{purpose}.ogg"


def transcribe_and_upload(
    db: CloudSQLClient,
    gdrive_client,
    voice_client,
    user_id: int,
    user_role: str,
    voice_bytes: bytes,
) -> str:
    """上傳原始語音檔到 Drive、記錄 media_uploads，並呼叫 Groq Whisper 轉出文字。

    上傳／記錄動作本身就是 FR-15 修正窗口的起點（見 `is_within_correction_window`），
    所以這支函式只在「確定要處理」（已通過 FR-14／FR-15 檢查）的語音訊息上呼叫。
    """
    gdrive_url = gdrive_client.upload_file(
        filename=build_upload_filename(user_role),
        content=voice_bytes,
        mime_type="audio/ogg",
    )
    save_media_upload(db, user_id, "audio", gdrive_url)

    return voice_client.transcribe(voice_bytes, filename="voice.ogg", mime_type="audio/ogg")
