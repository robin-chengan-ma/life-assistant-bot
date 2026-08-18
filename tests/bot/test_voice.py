from datetime import datetime, timedelta, timezone

from src.bot import voice
from src.bot.state import ConversationStateStore


class _FakeVoiceClient:
    """模擬 submodules.voice.client.VoiceClient，只實作 voice.py 會用到的 transcribe。"""

    def __init__(self, response_text="今天天氣真好"):
        self.response_text = response_text
        self.last_audio_bytes = None
        self.last_filename = None
        self.last_mime_type = None

    def transcribe(self, audio_bytes, filename="audio.ogg", mime_type="audio/ogg"):
        self.last_audio_bytes = audio_bytes
        self.last_filename = filename
        self.last_mime_type = mime_type
        return self.response_text


class _FakeGDriveClient:
    def __init__(self, url="https://drive.google.com/file/d/fake-voice/view"):
        self.url = url
        self.last_upload = None

    def upload_file(self, filename, content, mime_type):
        self.last_upload = {"filename": filename, "content": content, "mime_type": mime_type}
        return self.url


# --- exceeds_duration_limit（FR-14）---


def test_exceeds_duration_limit_false_when_under_ten_minutes():
    assert voice.exceeds_duration_limit(599) is False


def test_exceeds_duration_limit_false_when_exactly_ten_minutes():
    assert voice.exceeds_duration_limit(600) is False


def test_exceeds_duration_limit_true_when_over_ten_minutes():
    assert voice.exceeds_duration_limit(601) is True


def test_exceeds_duration_limit_false_when_duration_missing():
    # 缺少時長資訊時保守放行，不無故擋下使用者
    assert voice.exceeds_duration_limit(None) is False


# --- mark_duration_violation／is_locked_out_from_duration_violation（FR-14 規則 1，2026-08-02 追加）---


def test_is_locked_out_from_duration_violation_false_when_no_prior_violation():
    lockout_store = ConversationStateStore()
    assert voice.is_locked_out_from_duration_violation(lockout_store, telegram_user_id=1) is False


def test_is_locked_out_from_duration_violation_true_within_five_minutes():
    lockout_store = ConversationStateStore()
    now = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)
    voice.mark_duration_violation(lockout_store, telegram_user_id=1, now=now - timedelta(minutes=4))

    assert voice.is_locked_out_from_duration_violation(lockout_store, telegram_user_id=1, now=now) is True


def test_is_locked_out_from_duration_violation_false_after_five_minutes():
    lockout_store = ConversationStateStore()
    now = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)
    voice.mark_duration_violation(lockout_store, telegram_user_id=1, now=now - timedelta(minutes=6))

    assert voice.is_locked_out_from_duration_violation(lockout_store, telegram_user_id=1, now=now) is False


def test_is_locked_out_from_duration_violation_ignores_other_users():
    lockout_store = ConversationStateStore()
    now = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)
    voice.mark_duration_violation(lockout_store, telegram_user_id=999, now=now - timedelta(minutes=1))

    assert voice.is_locked_out_from_duration_violation(lockout_store, telegram_user_id=1, now=now) is False


def test_mark_duration_violation_defaults_to_current_time():
    lockout_store = ConversationStateStore()
    voice.mark_duration_violation(lockout_store, telegram_user_id=1)

    assert voice.is_locked_out_from_duration_violation(lockout_store, telegram_user_id=1) is True


# --- build_upload_filename ---


def test_build_upload_filename_matches_adr13_format():
    fixed_time = datetime(2026, 8, 1, 15, 30, 0, tzinfo=timezone.utc)

    filename = voice.build_upload_filename("爸爸", now=fixed_time)

    assert filename == "爸爸_20260801153000_語音辨識.ogg"


def test_build_upload_filename_accepts_custom_purpose():
    fixed_time = datetime(2026, 8, 1, 15, 30, 0, tzinfo=timezone.utc)

    filename = voice.build_upload_filename("媽媽", purpose="待辦事項", now=fixed_time)

    assert filename == "媽媽_20260801153000_待辦事項.ogg"


def test_build_upload_filename_accepts_custom_extension():
    fixed_time = datetime(2026, 8, 1, 15, 30, 0, tzinfo=timezone.utc)

    filename = voice.build_upload_filename("爸爸", extension="mp3", now=fixed_time)

    assert filename == "爸爸_20260801153000_語音辨識.mp3"


# --- _infer_extension（2026-08-01 追加，FR-17：message.audio 可能是各種格式）---


def test_infer_extension_known_mime_types():
    assert voice._infer_extension("audio/ogg") == "ogg"
    assert voice._infer_extension("audio/mpeg") == "mp3"
    assert voice._infer_extension("audio/mp4") == "m4a"
    assert voice._infer_extension("audio/wav") == "wav"


def test_infer_extension_unknown_mime_type_falls_back_to_ogg():
    assert voice._infer_extension("audio/x-totally-unknown") == "ogg"


# --- transcribe_and_upload ---


def test_transcribe_and_upload_uploads_original_bytes_and_logs(fake_db):
    gdrive_client = _FakeGDriveClient(url="https://drive/original-voice")
    voice_client = _FakeVoiceClient()

    voice.transcribe_and_upload(fake_db, gdrive_client, voice_client, user_id=42, user_role="爸爸", audio_bytes=b"raw-ogg-bytes")

    assert gdrive_client.last_upload["content"] == b"raw-ogg-bytes"
    assert gdrive_client.last_upload["mime_type"] == "audio/ogg"
    assert gdrive_client.last_upload["filename"].endswith(".ogg")
    rows = fake_db.select("media_uploads", where="user_id = %s", params=(42,))
    assert len(rows) == 1
    assert rows[0]["gdrive_url"] == "https://drive/original-voice"
    assert rows[0]["media_type"] == "audio"


def test_transcribe_and_upload_sends_bytes_to_voice_client_and_returns_text(fake_db):
    gdrive_client = _FakeGDriveClient()
    voice_client = _FakeVoiceClient(response_text="幫我記一下明天要繳電費")

    result = voice.transcribe_and_upload(
        fake_db, gdrive_client, voice_client, user_id=1, user_role="爸爸", audio_bytes=b"raw-ogg-bytes"
    )

    assert result == "幫我記一下明天要繳電費"
    assert voice_client.last_audio_bytes == b"raw-ogg-bytes"
    assert voice_client.last_filename == "voice.ogg"
    assert voice_client.last_mime_type == "audio/ogg"


def test_transcribe_and_upload_uses_correct_extension_for_uploaded_mp3(fake_db):
    # message.audio 上傳的 MP3 檔案：不該被誤標成 .ogg
    gdrive_client = _FakeGDriveClient()
    voice_client = _FakeVoiceClient(response_text="這是一段錄音")

    voice.transcribe_and_upload(
        fake_db, gdrive_client, voice_client, user_id=1, user_role="爸爸",
        audio_bytes=b"raw-mp3-bytes", mime_type="audio/mpeg",
    )

    assert gdrive_client.last_upload["filename"].endswith(".mp3")
    assert gdrive_client.last_upload["mime_type"] == "audio/mpeg"
    assert voice_client.last_filename == "voice.mp3"
    assert voice_client.last_mime_type == "audio/mpeg"
