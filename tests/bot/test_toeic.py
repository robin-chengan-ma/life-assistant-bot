"""src/bot/toeic.py 的單元測試（對應 robinson SPEC.md FR-24、FR-25a～FR-25f，Step 3.2）。"""
import io
import json
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from pydub import AudioSegment
from pydub.generators import Sine

from src.bot import toeic


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def _seed_owner(fake_db, **overrides):
    row = {
        "telegram_user_id": 999,
        "role": "Robin",
        "is_owner": True,
        "toeic_weekly_question_count": 21,
        "toeic_pipeline_last_run_on": None,
    }
    row.update(overrides)
    return fake_db.insert("users", row)


def _vision_reply(question_text="這是題目", options="A. 選項一|B. 選項二"):
    return f"QUESTION: {question_text}\nOPTIONS: {options}"


def _vocab_reply(word="abundant", correct="A"):
    return (
        f"WORD: {word}\n"
        "QUESTION: 這個字最接近下列何者意思？\n"
        "OPTION_A: 豐富的\n"
        "OPTION_B: 稀少的\n"
        "OPTION_C: 昂貴的\n"
        "OPTION_D: 便宜的\n"
        f"CORRECT: {correct}\n"
        f"EXAMPLE: There is an {word} supply of food.\n"
        "EXAMPLE_ZH: 食物供應充足。"
    )


# --- parse_filename ---


def test_parse_filename_write_question():
    parsed = toeic.parse_filename("toeic_0001_write_1.png")
    assert parsed == {"test_id": "0001", "type": "write", "question_number": 1, "extension": "png"}


def test_parse_filename_listen_split_audio():
    parsed = toeic.parse_filename("toeic_0001_listen_3.mp3")
    assert parsed == {"test_id": "0001", "type": "listen", "question_number": 3, "extension": "mp3"}


def test_parse_filename_listen_whole_audio_has_no_question_number():
    parsed = toeic.parse_filename("toeic_0001_listen.mp3")
    assert parsed == {"test_id": "0001", "type": "listen", "question_number": None, "extension": "mp3"}


def test_parse_filename_returns_none_for_non_toeic_file():
    assert toeic.parse_filename("爸爸_20260731153000_飲食紀錄.jpg") is None


def test_parse_filename_returns_none_for_invalid_type():
    assert toeic.parse_filename("toeic_0001_speaking_1.png") is None


# --- classify_drive_files ---


def test_classify_drive_files_buckets_correctly():
    files = [
        {"id": "f1", "name": "toeic_0001_write_1.png", "mimeType": "image/png"},
        {"id": "f2", "name": "toeic_0001_listen_1.png", "mimeType": "image/png"},
        {"id": "f3", "name": "toeic_0001_listen_1.mp3", "mimeType": "audio/mpeg"},
        {"id": "f4", "name": "toeic_0002_listen.mp3", "mimeType": "audio/mpeg"},
        {"id": "f5", "name": "not_a_toeic_file.jpg", "mimeType": "image/jpeg"},
    ]

    classified = toeic.classify_drive_files(files)

    assert classified["write_images"] == {("0001", 1): files[0]}
    assert classified["listen_images"] == {("0001", 1): files[1]}
    assert classified["listen_audio_segments"] == {("0001", 1): files[2]}
    assert classified["listen_whole_audio"] == {"0002": files[3]}


def test_classify_drive_files_ignores_unmatched_files():
    files = [{"id": "f1", "name": "random.png", "mimeType": "image/png"}]

    classified = toeic.classify_drive_files(files)

    assert classified == {
        "write_images": {},
        "listen_images": {},
        "listen_audio_segments": {},
        "listen_whole_audio": {},
    }


# --- sync_track1_from_drive ---


def _make_gdrive_client(files, downloads):
    gdrive_client = MagicMock()
    gdrive_client.list_files.return_value = files
    gdrive_client.download_file.side_effect = lambda file_id: downloads[file_id]
    gdrive_client.upload_file.return_value = "https://drive.google.com/file/d/new-segment/view"
    return gdrive_client


def test_sync_processes_new_write_question(fake_db):
    files = [{"id": "f1", "name": "toeic_0001_write_1.png", "mimeType": "image/png", "webViewLink": "url1"}]
    gdrive_client = _make_gdrive_client(files, {"f1": b"image-bytes"})
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.return_value = _vision_reply()
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    rows = fake_db.select("toeic_questions")
    assert len(rows) == 1
    row = rows[0]
    assert row["test_id"] == "0001"
    assert row["question_type"] == "write"
    assert row["question_number"] == 1
    assert row["question_text"] == "這是題目"
    assert json.loads(row["options"]) == ["A. 選項一", "B. 選項二"]
    assert row["image_gdrive_url"] == "url1"
    assert row["audio_gdrive_url"] is None
    assert row["source_image_filename"] == "toeic_0001_write_1.png"


def test_sync_skips_already_processed_write_question(fake_db):
    fake_db.insert(
        "toeic_questions",
        {
            "test_id": "0001",
            "question_type": "write",
            "question_number": 1,
            "question_text": "舊題目",
            "options": "[]",
            "image_gdrive_url": "old-url",
            "audio_gdrive_url": None,
            "source_image_filename": "toeic_0001_write_1.png",
        },
    )
    files = [{"id": "f1", "name": "toeic_0001_write_1.png", "mimeType": "image/png", "webViewLink": "url1"}]
    gdrive_client = _make_gdrive_client(files, {"f1": b"image-bytes"})
    image_llm_clients = [MagicMock()]
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    assert len(fake_db.select("toeic_questions")) == 1
    gdrive_client.download_file.assert_not_called()
    image_llm_clients[0].generate_with_image.assert_not_called()


def test_sync_skips_when_vision_parse_fails(fake_db):
    files = [{"id": "f1", "name": "toeic_0001_write_1.png", "mimeType": "image/png", "webViewLink": "url1"}]
    gdrive_client = _make_gdrive_client(files, {"f1": b"image-bytes"})
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.return_value = "格式完全不對的回覆"
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    assert fake_db.select("toeic_questions") == []


def test_sync_skips_when_vision_llm_raises(fake_db):
    files = [{"id": "f1", "name": "toeic_0001_write_1.png", "mimeType": "image/png", "webViewLink": "url1"}]
    gdrive_client = _make_gdrive_client(files, {"f1": b"image-bytes"})
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.side_effect = RuntimeError("Gemini 掛了")
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    assert fake_db.select("toeic_questions") == []


def test_sync_processes_listen_question_with_existing_split_audio(fake_db):
    files = [
        {"id": "f1", "name": "toeic_0001_listen_1.png", "mimeType": "image/png", "webViewLink": "image-url"},
        {"id": "f2", "name": "toeic_0001_listen_1.mp3", "mimeType": "audio/mpeg", "webViewLink": "audio-url"},
    ]
    gdrive_client = _make_gdrive_client(files, {"f1": b"image-bytes"})
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.return_value = _vision_reply("聽力題目")
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    rows = fake_db.select("toeic_questions")
    assert len(rows) == 1
    assert rows[0]["question_type"] == "listen"
    assert rows[0]["image_gdrive_url"] == "image-url"
    assert rows[0]["audio_gdrive_url"] == "audio-url"
    voice_client.transcribe_with_segments.assert_not_called()


def test_sync_leaves_listen_question_pending_when_no_audio_available(fake_db):
    files = [{"id": "f1", "name": "toeic_0001_listen_1.png", "mimeType": "image/png", "webViewLink": "image-url"}]
    gdrive_client = _make_gdrive_client(files, {"f1": b"image-bytes"})
    image_llm_clients = [MagicMock()]
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    assert fake_db.select("toeic_questions") == []
    gdrive_client.download_file.assert_not_called()


def _make_silent_mp3_bytes(duration_ms: int) -> bytes:
    audio = Sine(440).to_audio_segment(duration=duration_ms).apply_gain(-30)
    buffer = io.BytesIO()
    audio.export(buffer, format="mp3")
    return buffer.getvalue()


def test_sync_splits_whole_audio_and_processes_listen_questions(fake_db):
    whole_audio_bytes = _make_silent_mp3_bytes(6000)
    files = [
        {"id": "img1", "name": "toeic_0002_listen_1.png", "mimeType": "image/png", "webViewLink": "image-url-1"},
        {"id": "img2", "name": "toeic_0002_listen_2.png", "mimeType": "image/png", "webViewLink": "image-url-2"},
        {"id": "audio", "name": "toeic_0002_listen.mp3", "mimeType": "audio/mpeg", "webViewLink": "whole-url"},
    ]
    downloads = {"img1": b"image-bytes-1", "img2": b"image-bytes-2", "audio": whole_audio_bytes}
    gdrive_client = _make_gdrive_client(files, downloads)
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.side_effect = [
        _vision_reply("聽力第一題"),
        _vision_reply("聽力第二題"),
    ]
    voice_client = MagicMock()
    voice_client.transcribe_with_segments.return_value = [
        {"start": 0.0, "end": 1.0, "text": "Question one."},
        {"start": 4.5, "end": 5.5, "text": "Question two."},
    ]

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    rows = fake_db.select("toeic_questions")
    assert len(rows) == 2
    texts = {row["question_number"]: row["question_text"] for row in rows}
    assert texts == {1: "聽力第一題", 2: "聽力第二題"}
    for row in rows:
        assert row["audio_gdrive_url"] == "https://drive.google.com/file/d/new-segment/view"
    assert gdrive_client.upload_file.call_count == 2


def test_sync_skips_split_batch_when_whisper_fails(fake_db):
    files = [
        {"id": "img1", "name": "toeic_0002_listen_1.png", "mimeType": "image/png", "webViewLink": "image-url-1"},
        {"id": "audio", "name": "toeic_0002_listen.mp3", "mimeType": "audio/mpeg", "webViewLink": "whole-url"},
    ]
    gdrive_client = _make_gdrive_client(files, {"img1": b"image-bytes", "audio": b"whole-audio-bytes"})
    image_llm_clients = [MagicMock()]
    voice_client = MagicMock()
    voice_client.transcribe_with_segments.side_effect = RuntimeError("Groq 掛了")

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    assert fake_db.select("toeic_questions") == []
    image_llm_clients[0].generate_with_image.assert_not_called()


# --- _find_split_points / split_audio_by_question_count ---


def test_find_split_points_picks_largest_gaps():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "a"},
        {"start": 1.2, "end": 2.0, "text": "b"},  # 小停頓 0.2s
        {"start": 10.0, "end": 11.0, "text": "c"},  # 大停頓 8.0s
    ]

    split_points = toeic._find_split_points(segments, 1)

    assert split_points == [6.0]  # (2.0 + 10.0) / 2


def test_find_split_points_returns_empty_when_no_splits_needed():
    segments = [{"start": 0.0, "end": 1.0, "text": "a"}, {"start": 2.0, "end": 3.0, "text": "b"}]

    assert toeic._find_split_points(segments, 0) == []


def test_split_audio_by_question_count_returns_correct_number_of_segments():
    audio_bytes = _make_silent_mp3_bytes(6000)
    transcript_segments = [
        {"start": 0.0, "end": 1.0, "text": "Question one."},
        {"start": 4.5, "end": 5.5, "text": "Question two."},
    ]

    result = toeic.split_audio_by_question_count(audio_bytes, [2, 1], transcript_segments)

    assert set(result.keys()) == {1, 2}
    for segment_bytes in result.values():
        assert isinstance(segment_bytes, bytes)
        assert len(segment_bytes) > 0
        # 確保每段都是可以被還原解析的合法音檔
        decoded = AudioSegment.from_file(io.BytesIO(segment_bytes))
        assert len(decoded) > 0


# --- generate_track2_vocab_questions ---


def test_generate_track2_creates_requested_count(fake_db):
    llm_client = MagicMock()
    llm_client.generate_text.side_effect = [_vocab_reply("abundant"), _vocab_reply("diligent")]

    generated = toeic.generate_track2_vocab_questions(fake_db, llm_client, count=2)

    assert generated == 2
    rows = fake_db.select("toeic_vocab_questions")
    assert len(rows) == 2
    assert {row["target_word"] for row in rows} == {"abundant", "diligent"}
    assert rows[0]["correct_option"] == "A"


def test_generate_track2_returns_zero_when_count_is_zero(fake_db):
    llm_client = MagicMock()

    generated = toeic.generate_track2_vocab_questions(fake_db, llm_client, count=0)

    assert generated == 0
    llm_client.generate_text.assert_not_called()


def test_generate_track2_skips_words_already_in_db(fake_db):
    fake_db.insert(
        "toeic_vocab_questions",
        {
            "target_word": "abundant",
            "question_text": "q",
            "option_a": "a",
            "option_b": "b",
            "option_c": "c",
            "option_d": "d",
            "correct_option": "A",
            "example_sentence": "e",
            "example_sentence_translation": "e-zh",
        },
    )
    llm_client = MagicMock()
    llm_client.generate_text.side_effect = [_vocab_reply("abundant"), _vocab_reply("diligent")]

    generated = toeic.generate_track2_vocab_questions(fake_db, llm_client, count=1)

    assert generated == 1
    rows = fake_db.select("toeic_vocab_questions")
    assert len(rows) == 2
    assert rows[-1]["target_word"] == "diligent"


def test_generate_track2_skips_malformed_llm_reply(fake_db):
    llm_client = MagicMock()
    llm_client.generate_text.side_effect = ["格式不對的回覆", _vocab_reply("diligent")]

    generated = toeic.generate_track2_vocab_questions(fake_db, llm_client, count=1)

    assert generated == 1
    assert fake_db.select("toeic_vocab_questions")[0]["target_word"] == "diligent"


def test_generate_track2_stops_after_max_attempts(fake_db):
    llm_client = MagicMock()
    llm_client.generate_text.return_value = "永遠格式不對"

    generated = toeic.generate_track2_vocab_questions(fake_db, llm_client, count=3)

    assert generated == 0
    assert llm_client.generate_text.call_count == 9  # count * 3


def test_generate_track2_degrades_gracefully_when_llm_raises(fake_db):
    llm_client = MagicMock()
    llm_client.generate_text.side_effect = [RuntimeError("Gemini 掛了"), _vocab_reply("diligent")]

    generated = toeic.generate_track2_vocab_questions(fake_db, llm_client, count=1)

    assert generated == 1


# --- run_weekly_pipeline ---


def _make_pipeline_clients():
    gdrive_client = MagicMock()
    gdrive_client.list_files.return_value = []
    image_llm_clients = [MagicMock()]
    voice_client = MagicMock()
    text_llm_client = MagicMock()
    text_llm_client.generate_text.return_value = _vocab_reply("abundant")
    return gdrive_client, image_llm_clients, voice_client, text_llm_client


def test_run_weekly_pipeline_skips_outside_sunday_22(fake_db):
    _seed_owner(fake_db)
    clients = _make_pipeline_clients()

    toeic.run_weekly_pipeline(fake_db, *clients, now=_utc(2026, 8, 8, 22, 0))  # 週一

    clients[0].list_files.assert_not_called()


def test_run_weekly_pipeline_skips_outside_22_hour_on_sunday(fake_db):
    _seed_owner(fake_db)
    clients = _make_pipeline_clients()

    toeic.run_weekly_pipeline(fake_db, *clients, now=_utc(2026, 8, 9, 10, 0))  # 週日但不是 22 點

    clients[0].list_files.assert_not_called()


def test_run_weekly_pipeline_skips_when_no_owner_bound(fake_db):
    clients = _make_pipeline_clients()

    toeic.run_weekly_pipeline(fake_db, *clients, now=_utc(2026, 8, 9, 14, 0))  # 台灣時間週日 22:00

    clients[0].list_files.assert_not_called()


def test_run_weekly_pipeline_skips_when_feature_toggle_disabled(fake_db):
    owner_id = _seed_owner(fake_db)
    fake_db.insert("feature_toggles", {"user_id": owner_id, "feature_key": "certificate", "is_enabled": False})
    clients = _make_pipeline_clients()

    toeic.run_weekly_pipeline(fake_db, *clients, now=_utc(2026, 8, 9, 14, 0))

    clients[0].list_files.assert_not_called()


def test_run_weekly_pipeline_skips_when_already_run_today(fake_db):
    _seed_owner(fake_db, toeic_pipeline_last_run_on=date(2026, 8, 9))
    clients = _make_pipeline_clients()

    toeic.run_weekly_pipeline(fake_db, *clients, now=_utc(2026, 8, 9, 14, 0))

    clients[0].list_files.assert_not_called()


def test_run_weekly_pipeline_runs_both_tracks_and_marks_dedup(fake_db):
    owner_id = _seed_owner(fake_db, toeic_weekly_question_count=1)
    clients = _make_pipeline_clients()

    toeic.run_weekly_pipeline(fake_db, *clients, now=_utc(2026, 8, 9, 14, 0))  # 台灣時間週日 22:00

    clients[0].list_files.assert_called_once()
    assert len(fake_db.select("toeic_vocab_questions")) == 1
    owner = fake_db.select("users", where="id = %s", params=(owner_id,), fetch_one=True)
    assert owner["toeic_pipeline_last_run_on"] == date(2026, 8, 9)


def test_run_weekly_pipeline_does_not_repeat_within_same_hour(fake_db):
    _seed_owner(fake_db, toeic_weekly_question_count=1)
    clients = _make_pipeline_clients()

    toeic.run_weekly_pipeline(fake_db, *clients, now=_utc(2026, 8, 9, 14, 0))
    toeic.run_weekly_pipeline(fake_db, *clients, now=_utc(2026, 8, 9, 14, 20))

    assert clients[0].list_files.call_count == 1
    assert len(fake_db.select("toeic_vocab_questions")) == 1


def test_run_weekly_pipeline_defaults_weekly_count_when_not_set(fake_db):
    _seed_owner(fake_db, toeic_weekly_question_count=None)
    gdrive_client, image_llm_clients, voice_client, text_llm_client = _make_pipeline_clients()
    text_llm_client.generate_text.side_effect = lambda *_: _vocab_reply(f"word{text_llm_client.generate_text.call_count}")

    toeic.run_weekly_pipeline(fake_db, gdrive_client, image_llm_clients, voice_client, text_llm_client, now=_utc(2026, 8, 9, 14, 0))

    assert len(fake_db.select("toeic_vocab_questions")) == 21


def test_run_weekly_pipeline_track1_failure_does_not_block_track2(fake_db):
    owner_id = _seed_owner(fake_db, toeic_weekly_question_count=1)
    gdrive_client, image_llm_clients, voice_client, text_llm_client = _make_pipeline_clients()
    gdrive_client.list_files.side_effect = RuntimeError("Drive 掛了")

    toeic.run_weekly_pipeline(fake_db, gdrive_client, image_llm_clients, voice_client, text_llm_client, now=_utc(2026, 8, 9, 14, 0))

    assert len(fake_db.select("toeic_vocab_questions")) == 1
    owner = fake_db.select("users", where="id = %s", params=(owner_id,), fetch_one=True)
    assert owner["toeic_pipeline_last_run_on"] == date(2026, 8, 9)
