"""語音辨識邏輯（對應 docs/specs/robinson/SPEC.md FR-14、FR-15、FR-17、ADR-12、ADR-13）。

處理使用者傳來的「語音內容」——涵蓋 Telegram 的 `voice`（錄音鍵語音訊息）與 `audio`
（使用者上傳的音樂/錄音檔）兩種訊息類型，FR-17 承諾「圖片與音檔兩種格式都支援」，
不限定只有錄音鍵那種；兩者對 Robinson 而言處理方式完全相同：上傳原始檔到 Google Drive
（不落地存壓縮版，語音本身不需要壓縮，比照 ADR-13 圖片「只存原始檔」的作法）→ 記錄
media_uploads（`media_type='audio'`）→ 呼叫 Groq Whisper 轉出文字。轉出來的文字會被
呼叫端（router.py）當成使用者「打字輸入」，比照一般文字訊息走完整的指令/對話流程分派，
這裡不重複那套邏輯，只負責「把語音變成文字」這件事本身。下載 Telegram 檔案屬於 I/O
邊界，由呼叫端（webhook.py）處理完、把原始 bytes 傳進來。

2026-08-01 追加（見下方 `_infer_extension`）：`voice` 訊息固定是 OGG/OPUS，但 `audio`
訊息可能是使用者上傳的 MP3／M4A／WAV 等各種格式，Telegram 本身會回報正確的 `mime_type`，
呼叫端把它一路透傳進來，用於 Drive 上傳、檔名副檔名、Groq 轉錄請求三處，避免把 MP3 檔案
誤標成 `.ogg`。

FR-14（10 分鐘上限）／FR-15（15 分鐘修正窗口）這兩項檢查刻意設計成「不需要下載語音檔、
不需要呼叫任何外部服務就能判斷」，比照 webhook.py 對不支援檔案格式的既有作法先擋下、
避免浪費 Drive／Groq 額度：FR-14 用 Telegram 訊息本身就帶的 `duration` 秒數判斷（呼叫端
負責在下載前先呼叫 `exceeds_duration_limit()`）；FR-15 用 `media_uploads` 裡該使用者最近
一筆 `audio` 記錄的時間判斷（`is_within_correction_window()`），不需要額外的資料表或
記憶體狀態。

2026-08-02 追加（Robin 釐清 FR-14／FR-15 其實是兩條獨立規則，都要做）：
1. **FR-14 規則 1**（`mark_duration_violation()`／`is_locked_out_from_duration_violation()`）：
   單次錄音「本身」超過 10 分鐘時，語音功能整體鎖定 15 分鐘——這段期間內任何語音訊息
   （不限於「修正」情境）都會被拒絕。因為超時的語音一開始就不會呼叫
   `transcribe_and_upload()`（不會寫入 `media_uploads`），無法沿用 FR-15 查 DB 時間戳記的
   作法，改用純記憶體儲存（比照 `src/bot/state.py` 的 `ConversationStateStore`／ADR-2 慣例：
   process 重啟會重置，可接受）記錄「最近一次超時的時間點」。
2. **FR-15**（既有）：只要成功轉出文字（代表這則語音本身沒超過 10 分鐘），15 分鐘內若使用者
   還想再用語音「修正」剛剛的結果，一樣要拒絕、提醒改用打字——語意上鎖定的是「修正這件事」，
   跟規則 1「單純因為太長而鎖」是兩個不同觸發條件，只是巧合都設定成 15 分鐘。
"""
from datetime import datetime, timedelta, timezone

from src.bot.media import save_media_upload
from src.bot.state import ConversationStateStore
from submodules.cloudsql.client import CloudSQLClient

_MAX_DURATION_SECONDS = 600  # FR-14：語音訊息超過 10 分鐘強制中斷處理
_CORRECTION_WINDOW_MINUTES = 15  # FR-15：語音送出後 15 分鐘內僅能用打字修正
_DURATION_LOCKOUT_MINUTES = 15  # FR-14 規則 1：單次錄音超過 10 分鐘時，語音功能整體鎖定 15 分鐘

# 依 Telegram 回報的 mime_type 決定存到 Drive 時用的副檔名；voice 訊息固定 audio/ogg，
# audio 訊息（使用者上傳的音檔）常見類型列在這裡，沒對應到的一律 fallback 成 ogg——
# 只影響 Drive 上的檔名好不好讀，不影響轉錄本身（轉錄一律用真正的 mime_type）。
_EXTENSION_BY_MIME_TYPE = {
    "audio/ogg": "ogg",
    "audio/opus": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}
_DEFAULT_EXTENSION = "ogg"


def _infer_extension(mime_type: str) -> str:
    return _EXTENSION_BY_MIME_TYPE.get(mime_type, _DEFAULT_EXTENSION)


def exceeds_duration_limit(duration_seconds: int | None) -> bool:
    """FR-14：語音長度是否超過 10 分鐘上限；缺少時長資訊時保守放行（不擋）。"""
    return duration_seconds is not None and duration_seconds > _MAX_DURATION_SECONDS


def mark_duration_violation(
    lockout_store: ConversationStateStore, telegram_user_id: int, now: datetime | None = None
) -> None:
    """FR-14 規則 1：記錄「這位使用者剛因單次語音超過 10 分鐘被擋下」的時間點，
    呼叫端在 `exceeds_duration_limit()` 判定為 True 時呼叫，供 `is_locked_out_from_duration_violation()` 判斷。
    """
    lockout_store.set(telegram_user_id, {"violated_at": now or datetime.now(timezone.utc)})


def is_locked_out_from_duration_violation(
    lockout_store: ConversationStateStore, telegram_user_id: int, now: datetime | None = None
) -> bool:
    """FR-14 規則 1：該使用者是否還在「上次因單次語音超過 10 分鐘」觸發的 15 分鐘全面鎖定內——
    這段期間語音功能整體關閉，跟 FR-15 的 `is_within_correction_window()`（只鎖「修正」情境）
    是兩條獨立規則。
    """
    state = lockout_store.get(telegram_user_id)
    if state is None:
        return False
    now = now or datetime.now(timezone.utc)
    return now - state["violated_at"] < timedelta(minutes=_DURATION_LOCKOUT_MINUTES)


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


def build_upload_filename(
    user_role: str, purpose: str = "語音辨識", extension: str = "ogg", now: datetime | None = None
) -> str:
    """依 ADR-13 命名規則：使用者稱呼＋當下時間戳記＋用途；副檔名依實際音檔格式決定
    （見 `_infer_extension`），不再固定寫死 `.ogg`（audio 訊息可能是 MP3/M4A/WAV 等）。
    """
    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")
    return f"{user_role}_{timestamp}_{purpose}.{extension}"


def transcribe_and_upload(
    db: CloudSQLClient,
    gdrive_client,
    voice_client,
    user_id: int,
    user_role: str,
    audio_bytes: bytes,
    mime_type: str = "audio/ogg",
) -> str:
    """上傳原始語音/音檔到 Drive、記錄 media_uploads，並呼叫 Groq Whisper 轉出文字。

    `mime_type` 由呼叫端依 Telegram 訊息類型（`voice` 固定 `audio/ogg`；`audio` 依
    Telegram 回報的實際類型）傳入，一路用於 Drive 上傳、檔名副檔名、Groq 轉錄請求三處。
    上傳／記錄動作本身就是 FR-15 修正窗口的起點（見 `is_within_correction_window`），
    所以這支函式只在「確定要處理」（已通過 FR-14／FR-15 檢查）的語音/音檔訊息上呼叫。
    """
    extension = _infer_extension(mime_type)
    gdrive_url = gdrive_client.upload_file(
        filename=build_upload_filename(user_role, extension=extension),
        content=audio_bytes,
        mime_type=mime_type,
    )
    save_media_upload(db, user_id, "audio", gdrive_url)

    return voice_client.transcribe(audio_bytes, filename=f"voice.{extension}", mime_type=mime_type)
