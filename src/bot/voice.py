"""語音與上傳音檔的辨識邏輯。

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

Telegram 長按語音以訊息內的 `duration` 在下載前檢查 10 分鐘上限；超時後用記憶體狀態鎖定
5 分鐘，避免浪費 Drive／Groq 額度。使用者上傳的 `audio` 音檔不套用這組時長與鎖定規則。
兩種輸入完成轉錄後都由 router 顯示文字並等待使用者確認；若有誤，可立即重新傳送或打字修正。
"""
from datetime import datetime, timedelta, timezone

from src.bot.media import save_media_upload
from src.bot.state import ConversationStateStore
from submodules.cloudsql.client import CloudSQLClient

_MAX_DURATION_SECONDS = 600  # FR-14：語音訊息超過 10 分鐘強制中斷處理
_DURATION_LOCKOUT_MINUTES = 5

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
    """是否仍在長按語音超過 10 分鐘所觸發的 5 分鐘鎖定內。"""
    state = lockout_store.get(telegram_user_id)
    if state is None:
        return False
    now = now or datetime.now(timezone.utc)
    return now - state["violated_at"] < timedelta(minutes=_DURATION_LOCKOUT_MINUTES)


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
    呼叫端會先完成適用的長按語音時長檢查；上傳音檔不套用該限制。
    """
    extension = _infer_extension(mime_type)
    gdrive_url = gdrive_client.upload_file(
        filename=build_upload_filename(user_role, extension=extension),
        content=audio_bytes,
        mime_type=mime_type,
    )
    save_media_upload(db, user_id, "audio", gdrive_url)

    return voice_client.transcribe(audio_bytes, filename=f"voice.{extension}", mime_type=mime_type)
