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
    assert parsed == {
        "exam_type": "toeic",
        "test_id": "0001",
        "type": "write",
        "question_number": 1,
        "extension": "png",
    }


def test_parse_filename_listen_split_audio():
    parsed = toeic.parse_filename("toeic_0001_listen_3.mp3")
    assert parsed == {
        "exam_type": "toeic",
        "test_id": "0001",
        "type": "listen",
        "question_number": 3,
        "extension": "mp3",
    }


def test_parse_filename_listen_whole_audio_has_no_question_number():
    parsed = toeic.parse_filename("toeic_0001_listen.mp3")
    assert parsed == {
        "exam_type": "toeic",
        "test_id": "0001",
        "type": "listen",
        "question_number": None,
        "extension": "mp3",
    }


def test_parse_filename_supports_other_exam_types():
    # 2026-08-07 追加：exam_type 泛用化，開放任意證照類型（不寫死 toeic/gcp/aws 清單）。
    parsed = toeic.parse_filename("gcp_0002_write_1.png")
    assert parsed == {
        "exam_type": "gcp",
        "test_id": "0002",
        "type": "write",
        "question_number": 1,
        "extension": "png",
    }


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

    assert classified["write_images"] == {("toeic", "0001", 1): files[0]}
    assert classified["listen_images"] == {("toeic", "0001", 1): files[1]}
    assert classified["listen_audio_segments"] == {("toeic", "0001", 1): files[2]}
    assert classified["listen_whole_audio"] == {("toeic", "0002"): files[3]}


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

    rows = fake_db.select("certificate_questions")
    assert len(rows) == 1
    row = rows[0]
    assert row["exam_type"] == "toeic"
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
        "certificate_questions",
        {
            "exam_type": "toeic",
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

    assert len(fake_db.select("certificate_questions")) == 1
    gdrive_client.download_file.assert_not_called()
    image_llm_clients[0].generate_with_image.assert_not_called()


def test_sync_skips_when_vision_parse_fails(fake_db):
    files = [{"id": "f1", "name": "toeic_0001_write_1.png", "mimeType": "image/png", "webViewLink": "url1"}]
    gdrive_client = _make_gdrive_client(files, {"f1": b"image-bytes"})
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.return_value = "格式完全不對的回覆"
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    assert fake_db.select("certificate_questions") == []


def test_sync_skips_when_vision_llm_raises(fake_db):
    files = [{"id": "f1", "name": "toeic_0001_write_1.png", "mimeType": "image/png", "webViewLink": "url1"}]
    gdrive_client = _make_gdrive_client(files, {"f1": b"image-bytes"})
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.side_effect = RuntimeError("Gemini 掛了")
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    assert fake_db.select("certificate_questions") == []


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

    rows = fake_db.select("certificate_questions")
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

    assert fake_db.select("certificate_questions") == []
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

    rows = fake_db.select("certificate_questions")
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

    assert fake_db.select("certificate_questions") == []
    image_llm_clients[0].generate_with_image.assert_not_called()


def test_sync_processes_non_toeic_exam_type_and_scans_whole_folder(fake_db):
    # 2026-08-07 追加：exam_type 泛用化，驗證非 TOEIC 證照（例如 GCP）也能走同一套流程，
    # 且 Drive 掃描不再用檔名關鍵字過濾（list_files 呼叫不帶 name_contains）。
    files = [{"id": "f1", "name": "gcp_0002_write_1.png", "mimeType": "image/png", "webViewLink": "url1"}]
    gdrive_client = _make_gdrive_client(files, {"f1": b"image-bytes"})
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.return_value = _vision_reply("GCP 考題")
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    gdrive_client.list_files.assert_called_once_with()
    rows = fake_db.select("certificate_questions")
    assert len(rows) == 1
    assert rows[0]["exam_type"] == "gcp"
    assert rows[0]["test_id"] == "0002"
    assert rows[0]["question_text"] == "GCP 考題"


# --- _segment_length_variance / _split_points_for_target_length ---


def test_segment_length_variance_is_zero_for_perfectly_even_segments():
    variance = toeic._segment_length_variance(0.0, [10.0, 20.0], 30.0)
    assert variance == 0.0


def test_segment_length_variance_is_higher_for_uneven_segments():
    even = toeic._segment_length_variance(0.0, [10.0, 20.0], 30.0)
    uneven = toeic._segment_length_variance(0.0, [2.0, 4.0], 30.0)
    assert uneven > even


def test_segment_length_variance_returns_infinity_for_non_positive_length():
    assert toeic._segment_length_variance(0.0, [5.0, 5.0], 5.0) == float("inf")


def test_split_points_for_target_length_picks_nearest_candidates():
    points = toeic._split_points_for_target_length([13.2, 29.5], 2, 0.0, 15.0)
    assert points == [13.2, 29.5]


def test_split_points_for_target_length_falls_back_to_ideal_position_when_no_candidates():
    points = toeic._split_points_for_target_length([], 2, 0.0, 10.0)
    assert points == [10.0, 20.0]


def test_split_points_for_target_length_does_not_reuse_same_candidate():
    points = toeic._split_points_for_target_length([15.0], 2, 0.0, 10.0)
    assert points[0] == 15.0
    assert points[1] != 15.0  # 第二個切割點的候選點已被用掉，應該退回理想位置


# --- _find_split_plan ---


def test_find_split_plan_evenly_divides_when_no_intro_detected():
    # 3 題，題目之間有明顯大停頓（6s），題目內部只有小停頓（0.3s）雜訊，且不像有說明語音
    segments = [
        {"start": 0.0, "end": 5.0, "text": "q1a"},
        {"start": 5.3, "end": 10.0, "text": "q1b"},
        {"start": 16.0, "end": 21.0, "text": "q2a"},
        {"start": 21.3, "end": 26.0, "text": "q2b"},
        {"start": 32.0, "end": 37.0, "text": "q3a"},
        {"start": 37.3, "end": 42.0, "text": "q3b"},
    ]

    start_offset, points = toeic._find_split_plan(segments, 3, 42.0)

    assert start_offset == 0.0
    assert points == [13.0, 29.0]


def test_find_split_plan_detects_leading_instructions_and_excludes_them():
    # 模擬「開頭有一段作答說明語音」的情境：說明語音本身內部只有小停頓（不該被誤判成題目邊界），
    # 說明語音結尾與 3 題題目之間的停頓（6s）明顯比說明語音內部的停頓（0.3s）長很多
    segments = [
        {"start": 0.0, "end": 5.0, "text": "intro-a"},
        {"start": 5.3, "end": 10.0, "text": "intro-b"},
        {"start": 10.3, "end": 15.0, "text": "intro-c"},  # 說明語音結束於 15.0
        {"start": 21.0, "end": 26.0, "text": "q1"},  # 說明語音 -> 第一題，停頓 6s
        {"start": 32.0, "end": 37.0, "text": "q2"},  # 第一題 -> 第二題，停頓 6s
        {"start": 43.0, "end": 48.0, "text": "q3"},  # 第二題 -> 第三題，停頓 6s
    ]
    total_duration = 53.0

    start_offset, points = toeic._find_split_plan(segments, 3, total_duration)

    assert start_offset == 18.0  # (15.0 + 21.0) / 2，說明語音結尾與第一題之間的停頓中點
    assert points == [29.0, 40.0]


def test_find_split_plan_returns_empty_when_only_one_question():
    segments = [{"start": 0.0, "end": 1.0, "text": "a"}, {"start": 2.0, "end": 3.0, "text": "b"}]

    start_offset, points = toeic._find_split_plan(segments, 1, 3.0)

    assert start_offset == 0.0
    assert points == []


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


def test_split_audio_by_question_count_excludes_leading_instructions_regression():
    """迴歸測試：2026-08-07 用 Robin 提供的真實錄音 Test01_Part1.mp3 實測時發現，音檔開頭若有
    一段作答說明語音，早期版本的切割邏輯會把整段說明語音併入第一題（導致第一段長度是其他題目
    的 5 倍以上）；這裡用合成音檔重現同樣的「開頭有一段明顯比題目間停頓更長的說明語音」結構，
    確保修正後的邏輯會正確排除說明語音、6 段長度彼此相近。
    """
    intro_ms = 15000
    gap_ms = 3000
    question_ms = 5000
    segments_meta = []
    # 說明語音本身在時間軸上不需要精確模擬語句，只要整體時長跟後面題目的停頓比起來夠長即可
    audio = Sine(220).to_audio_segment(duration=intro_ms).apply_gain(-20)
    cursor = intro_ms

    for _ in range(6):
        audio += AudioSegment.silent(duration=gap_ms)
        question_start = cursor + gap_ms
        audio += Sine(440).to_audio_segment(duration=question_ms).apply_gain(-20)
        segments_meta.append((question_start / 1000, (question_start + question_ms) / 1000))
        cursor = question_start + question_ms

    buffer = io.BytesIO()
    audio.export(buffer, format="mp3")
    audio_bytes = buffer.getvalue()

    # 模擬 Whisper 回傳的逐句 timestamp：說明語音當一個大區塊，後面 6 題各自獨立一段
    transcript_segments = [{"start": 0.0, "end": intro_ms / 1000, "text": "intro"}]
    transcript_segments += [{"start": s, "end": e, "text": "q"} for s, e in segments_meta]

    result = toeic.split_audio_by_question_count(audio_bytes, [1, 2, 3, 4, 5, 6], transcript_segments)

    assert set(result.keys()) == {1, 2, 3, 4, 5, 6}
    lengths_ms = [len(AudioSegment.from_file(io.BytesIO(result[q]))) for q in range(1, 7)]
    # 說明語音（15 秒）應該被排除，不應該有任何一段長度接近或超過說明語音本身
    assert max(lengths_ms) < intro_ms
    # 6 段長度應該彼此相近（允許誤差），不應該出現某一段特別長/特別短的離群值
    assert max(lengths_ms) - min(lengths_ms) < question_ms


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
