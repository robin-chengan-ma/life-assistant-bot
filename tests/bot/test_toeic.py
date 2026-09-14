"""src/bot/toeic.py 的單元測試（對應 robinson SPEC.md FR-24、FR-25a～FR-25f，Step 3.2）。"""
import io
import json
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from pydub import AudioSegment
from pydub.generators import Sine

from src.bot import toeic
from submodules.llm.client import LLMQuotaGuardError


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


def _listen_answer_vision_reply(
    question_text="聽力題目逐字稿", options="A. 選項一|B. 選項二", correct_answer="B", explanation="因為 xxx 所以答案是 B"
):
    # 2026-08-24：聽力解答照片一次解析 QUESTION/OPTIONS/CORRECT_ANSWER/EXPLANATION 四項，
    # 見 `toeic._LISTEN_ANSWER_VISION_PARSE_PROMPT`。
    return (
        f"QUESTION: {question_text}\nOPTIONS: {options}\n"
        f"CORRECT_ANSWER: {correct_answer}\nEXPLANATION: {explanation}"
    )


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
        "is_answer_key": False,
        "cutoff_seconds": None,
    }


def test_parse_filename_listen_split_audio():
    parsed = toeic.parse_filename("toeic_0001_listen_3.mp3")
    assert parsed == {
        "exam_type": "toeic",
        "test_id": "0001",
        "type": "listen",
        "question_number": 3,
        "extension": "mp3",
        "is_answer_key": False,
        "cutoff_seconds": None,
    }


def test_parse_filename_listen_whole_audio_has_no_question_number():
    parsed = toeic.parse_filename("toeic_0001_listen.mp3")
    assert parsed == {
        "exam_type": "toeic",
        "test_id": "0001",
        "type": "listen",
        "question_number": None,
        "extension": "mp3",
        "is_answer_key": False,
        "cutoff_seconds": None,
    }


def test_parse_filename_listen_whole_audio_with_cutoff():
    # 2026-08-24 新增：整包聽力音檔可選加 cutoff 秒數後綴，只處理到指定秒數為止。
    parsed = toeic.parse_filename("toeic_0001_listen_cutoff1150.mp3")
    assert parsed == {
        "exam_type": "toeic",
        "test_id": "0001",
        "type": "listen",
        "question_number": None,
        "extension": "mp3",
        "is_answer_key": False,
        "cutoff_seconds": 1150,
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
        "is_answer_key": False,
        "cutoff_seconds": None,
    }


def test_parse_filename_returns_none_for_non_toeic_file():
    assert toeic.parse_filename("爸爸_20260731153000_飲食紀錄.jpg") is None


def test_parse_filename_returns_none_for_invalid_type():
    assert toeic.parse_filename("toeic_0001_speaking_1.png") is None


def test_parse_filename_answer_key_write():
    # 2026-08-07（Step 3.3，見 FR-27）：Robin 拍攝的測驗書解答/詳解照片，檔名多一段 `_ans` 後綴。
    parsed = toeic.parse_filename("toeic_0001_write_1_ans.png")
    assert parsed == {
        "exam_type": "toeic",
        "test_id": "0001",
        "type": "write",
        "question_number": 1,
        "extension": "png",
        "is_answer_key": True,
        "cutoff_seconds": None,
    }


def test_parse_filename_answer_key_listen():
    parsed = toeic.parse_filename("toeic_0001_listen_3_ans.png")
    assert parsed == {
        "exam_type": "toeic",
        "test_id": "0001",
        "type": "listen",
        "question_number": 3,
        "extension": "png",
        "is_answer_key": True,
        "cutoff_seconds": None,
    }


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
    assert classified["listen_whole_audio"] == {("toeic", "0002"): {"file": files[3], "cutoff_seconds": None}}
    assert classified["answer_keys"] == {}


def test_classify_drive_files_captures_cutoff_seconds_for_whole_audio():
    # 2026-08-24 新增：整包聽力音檔的 cutoff 秒數要一起存進 listen_whole_audio。
    files = [{"id": "f1", "name": "toeic_0003_listen_cutoff900.mp3", "mimeType": "audio/mpeg"}]

    classified = toeic.classify_drive_files(files)

    assert classified["listen_whole_audio"] == {("toeic", "0003"): {"file": files[0], "cutoff_seconds": 900}}


def test_classify_drive_files_buckets_answer_keys():
    # 2026-08-07（Step 3.3，見 FR-27）：`_ans` 檔名進 answer_keys，不會混進 write_images/listen_images。
    files = [
        {"id": "f1", "name": "toeic_0001_write_1_ans.png", "mimeType": "image/png"},
        {"id": "f2", "name": "toeic_0001_listen_2_ans.png", "mimeType": "image/png"},
    ]

    classified = toeic.classify_drive_files(files)

    assert classified["answer_keys"] == {
        ("toeic", "0001", "write", 1): files[0],
        ("toeic", "0001", "listen", 2): files[1],
    }
    assert classified["write_images"] == {}
    assert classified["listen_images"] == {}


def test_classify_drive_files_ignores_unmatched_files():
    files = [{"id": "f1", "name": "random.png", "mimeType": "image/png"}]

    classified = toeic.classify_drive_files(files)

    assert classified == {
        "write_images": {},
        "listen_images": {},
        "listen_audio_segments": {},
        "listen_whole_audio": {},
        "answer_keys": {},
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
    # 2026-08-24 起，聽力題內容來源改成解答照片（`_ans`），題目照片變成選填、不影響題目能否建立。
    files = [
        {"id": "f0", "name": "toeic_0001_listen_1_ans.png", "mimeType": "image/png", "webViewLink": "ans-url"},
        {"id": "f1", "name": "toeic_0001_listen_1.png", "mimeType": "image/png", "webViewLink": "image-url"},
        {"id": "f2", "name": "toeic_0001_listen_1.mp3", "mimeType": "audio/mpeg", "webViewLink": "audio-url"},
    ]
    gdrive_client = _make_gdrive_client(files, {"f0": b"answer-bytes"})
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.return_value = _listen_answer_vision_reply("聽力題目")
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    rows = fake_db.select("certificate_questions")
    assert len(rows) == 1
    assert rows[0]["question_type"] == "listen"
    assert rows[0]["question_text"] == "聽力題目"
    assert rows[0]["correct_answer"] == "B"
    assert rows[0]["image_gdrive_url"] == "image-url"
    assert rows[0]["audio_gdrive_url"] == "audio-url"
    assert rows[0]["source_image_filename"] == "toeic_0001_listen_1_ans.png"
    voice_client.transcribe_with_segments.assert_not_called()


def test_sync_listen_question_leaves_image_blank_when_no_question_photo(fake_db):
    # Part 2 這種完全沒有題目照片的題型：只要有解答照片＋音檔就能建立，image_gdrive_url 留空。
    files = [
        {"id": "f0", "name": "toeic_0001_listen_1_ans.png", "mimeType": "image/png", "webViewLink": "ans-url"},
        {"id": "f2", "name": "toeic_0001_listen_1.mp3", "mimeType": "audio/mpeg", "webViewLink": "audio-url"},
    ]
    gdrive_client = _make_gdrive_client(files, {"f0": b"answer-bytes"})
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.return_value = _listen_answer_vision_reply()
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    rows = fake_db.select("certificate_questions")
    assert len(rows) == 1
    assert rows[0]["image_gdrive_url"] is None
    assert rows[0]["audio_gdrive_url"] == "audio-url"


def test_sync_leaves_listen_question_pending_when_no_audio_available(fake_db):
    # 只有聽力解答照片、沒有現成單題音檔也沒有整包音檔：先跳過，下次排程重新掃描時再試。
    files = [{"id": "f0", "name": "toeic_0001_listen_1_ans.png", "mimeType": "image/png", "webViewLink": "ans-url"}]
    gdrive_client = _make_gdrive_client(files, {"f0": b"answer-bytes"})
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
        {"id": "ans1", "name": "toeic_0002_listen_1_ans.png", "mimeType": "image/png", "webViewLink": "ans-url-1"},
        {"id": "ans2", "name": "toeic_0002_listen_2_ans.png", "mimeType": "image/png", "webViewLink": "ans-url-2"},
        {"id": "audio", "name": "toeic_0002_listen.mp3", "mimeType": "audio/mpeg", "webViewLink": "whole-url"},
    ]
    downloads = {"ans1": b"answer-bytes-1", "ans2": b"answer-bytes-2", "audio": whole_audio_bytes}
    gdrive_client = _make_gdrive_client(files, downloads)
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.side_effect = [
        _listen_answer_vision_reply("聽力第一題"),
        _listen_answer_vision_reply("聽力第二題"),
    ]
    voice_client = MagicMock()
    voice_client.transcribe_with_segments.return_value = [
        {"start": 0.0, "end": 1.0, "text": "Number 1."},
        {"start": 4.5, "end": 5.5, "text": "Number 2."},
    ]

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    rows = fake_db.select("certificate_questions")
    assert len(rows) == 2
    texts = {row["question_number"]: row["question_text"] for row in rows}
    assert texts == {1: "聽力第一題", 2: "聽力第二題"}
    for row in rows:
        assert row["audio_gdrive_url"] == "https://drive.google.com/file/d/new-segment/view"
        assert row["correct_answer"] == "B"
        assert row["image_gdrive_url"] is None
    assert gdrive_client.upload_file.call_count == 2


def test_sync_splits_whole_audio_respects_cutoff_seconds(fake_db):
    # 2026-08-24 新增：整包音檔帶 cutoff 秒數時，只裁切前面那段送進切割演算法。
    whole_audio_bytes = _make_silent_mp3_bytes(6000)
    files = [
        {"id": "ans1", "name": "toeic_0003_listen_1_ans.png", "mimeType": "image/png", "webViewLink": "ans-url-1"},
        {"id": "audio", "name": "toeic_0003_listen_cutoff3.mp3", "mimeType": "audio/mpeg", "webViewLink": "whole-url"},
    ]
    downloads = {"ans1": b"answer-bytes-1", "audio": whole_audio_bytes}
    gdrive_client = _make_gdrive_client(files, downloads)
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.return_value = _listen_answer_vision_reply("聽力第一題")
    voice_client = MagicMock()
    voice_client.transcribe_with_segments.return_value = [
        {"start": 0.0, "end": 1.0, "text": "Number 1."},
        {"start": 4.5, "end": 5.5, "text": "Later part, should be ignored."},
    ]

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    rows = fake_db.select("certificate_questions")
    assert len(rows) == 1
    assert rows[0]["question_number"] == 1


def test_sync_records_failure_and_does_not_retry_question_with_missing_marker(fake_db):
    # 2026-09-13 新增（Robin 明確要求，見 docs/ADR/discuss/robinson.md 對應日期條目）：某一題
    # 找不到 100% 確定的切割邊界時，這次先跳過、記錄成放棄，「不是」下次排程自動重試——因為
    # 同一份錄音的轉錄結果基本上是固定的，重跑注定還是失敗，純粹浪費時間與 API 額度。
    whole_audio_bytes = _make_silent_mp3_bytes(6000)
    files = [
        {"id": "ans1", "name": "toeic_0004_listen_1_ans.png", "mimeType": "image/png", "webViewLink": "ans-url-1"},
        {"id": "ans2", "name": "toeic_0004_listen_2_ans.png", "mimeType": "image/png", "webViewLink": "ans-url-2"},
        {"id": "audio", "name": "toeic_0004_listen.mp3", "mimeType": "audio/mpeg", "webViewLink": "whole-url"},
    ]
    downloads = {"ans1": b"answer-bytes-1", "ans2": b"answer-bytes-2", "audio": whole_audio_bytes}
    gdrive_client = _make_gdrive_client(files, downloads)
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.return_value = _listen_answer_vision_reply("聽力第一題")
    voice_client = MagicMock()
    # 第 2 題的「Number 2.」標記完全沒有念出來／沒被 Whisper 辨識到，第 1 題(本批最後一個有標記的
    # 題號之前那題)因為抓不到「下一題」的標記，結束邊界也不確定，兩題本次都應該被跳過。
    voice_client.transcribe_with_segments.return_value = [{"start": 0.0, "end": 1.0, "text": "Number 1."}]

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    assert fake_db.select("certificate_questions") == []
    failures = fake_db.select("certificate_listen_split_failures")
    assert {(row["exam_type"], row["test_id"], row["question_number"]) for row in failures} == {
        ("toeic", "0004", 1),
        ("toeic", "0004", 2),
    }

    # 重新同步一次（模擬下週日排程再跑一次）：已經記錄放棄的題目不應該再被嘗試切割。
    voice_client.transcribe_with_segments.reset_mock()
    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    voice_client.transcribe_with_segments.assert_not_called()
    assert fake_db.select("certificate_questions") == []
    assert len(fake_db.select("certificate_listen_split_failures")) == 2  # 沒有重複寫入


def test_sync_recovers_from_transient_download_failure_on_one_answer_photo(fake_db):
    # 2026-09-14 新增（見 docs/ADR/debug/robinson.md 對應日期條目）：Robin 本機重跑測試時，第 1~3
    # 題完全「憑空消失」——兩張表都查不到，排查發現是下載解答照片時遇到暫時性網路中斷
    # （`IncompleteRead`），這行原本沒有包 try/except，例外會直接把整個 `sync_track1_from_drive()`
    # 中斷掉，讓「明明已經確定切出音檔」的題目連寫進資料庫或記錄失敗的機會都沒有。這裡驗證：
    # 其中一題下載解答照片失敗，不會拖累同一批次裡的其他題目，而且失敗的那題因為沒有寫入
    # `source_image_filename`，下次同步（不再模擬下載失敗）會自動重試成功。
    whole_audio_bytes = _make_silent_mp3_bytes(6000)
    files = [
        {"id": "ans1", "name": "toeic_0005_listen_1_ans.png", "mimeType": "image/png", "webViewLink": "ans-url-1"},
        {"id": "ans2", "name": "toeic_0005_listen_2_ans.png", "mimeType": "image/png", "webViewLink": "ans-url-2"},
        {"id": "audio", "name": "toeic_0005_listen.mp3", "mimeType": "audio/mpeg", "webViewLink": "whole-url"},
    ]
    downloads = {"ans1": b"answer-bytes-1", "ans2": b"answer-bytes-2", "audio": whole_audio_bytes}
    gdrive_client = _make_gdrive_client(files, downloads)

    def flaky_download(file_id):
        if file_id == "ans1":
            raise ConnectionError("IncompleteRead：模擬網路中斷")
        return downloads[file_id]

    gdrive_client.download_file.side_effect = flaky_download
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.return_value = _listen_answer_vision_reply("聽力第二題")
    voice_client = MagicMock()
    voice_client.transcribe_with_segments.return_value = [
        {"start": 0.0, "end": 1.0, "text": "Number 1."},
        {"start": 4.5, "end": 5.5, "text": "Number 2."},
    ]

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    # 第 1 題下載失敗，這次先跳過；第 2 題不受影響，正常寫入。兩張表都不該有第 1 題的紀錄——
    # 這是單純下載失敗，不是「切不出邊界」，不屬於永久放棄，應該保持可以自動重試的狀態。
    rows = fake_db.select("certificate_questions")
    assert {r["question_number"] for r in rows} == {2}
    failures = fake_db.select("certificate_listen_split_failures")
    assert failures == []

    # 下次同步（網路恢復正常）：第 1 題會自動重試成功。
    gdrive_client.download_file.side_effect = lambda file_id: downloads[file_id]
    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    rows = fake_db.select("certificate_questions")
    assert {r["question_number"] for r in rows} == {1, 2}


def test_split_whole_audio_transcribes_trimmed_bytes_not_the_full_file_when_cutoff_set():
    # 2026-09-06 新增（見 docs/ADR/debug/robinson.md 對應日期條目）：修正前是先把「整份沒剪過」
    # 的音檔送去 Groq 轉錄、事後才裁切，Robin 上傳的整份長錄音因此被 Groq 以 413 Payload Too
    # Large 拒絕，cutoff 完全沒發揮效果。這裡鎖定「有 cutoff_seconds 時，送進
    # transcribe_with_segments() 的音檔必須已經是剪過、比原始檔案小很多的那份」。
    whole_audio_bytes = _make_silent_mp3_bytes(6000)
    gdrive_client = MagicMock()
    gdrive_client.download_file.return_value = whole_audio_bytes
    voice_client = MagicMock()
    voice_client.transcribe_with_segments.return_value = [{"start": 0.0, "end": 1.0, "text": "Number 1."}]

    toeic._split_whole_audio(
        gdrive_client,
        voice_client,
        {"id": "audio", "name": "toeic_0003_listen_cutoff3.mp3"},
        question_numbers=[1],
        cutoff_seconds=3,
    )

    sent_bytes = voice_client.transcribe_with_segments.call_args[0][0]
    assert len(sent_bytes) < len(whole_audio_bytes)


def test_sync_skips_split_batch_when_whisper_fails(fake_db):
    files = [
        {"id": "ans1", "name": "toeic_0002_listen_1_ans.png", "mimeType": "image/png", "webViewLink": "ans-url-1"},
        {"id": "audio", "name": "toeic_0002_listen.mp3", "mimeType": "audio/mpeg", "webViewLink": "whole-url"},
    ]
    gdrive_client = _make_gdrive_client(files, {"ans1": b"answer-bytes", "audio": b"whole-audio-bytes"})
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


# --- sync_track1_from_drive：答案照片比對（Step 3.3，見 FR-27、ADR-19 決策 2） ---


def _answer_vision_reply(correct_answer="B", explanation="因為 xxx 所以答案是 B"):
    return f"CORRECT_ANSWER: {correct_answer}\nEXPLANATION: {explanation}"


def _seed_question(fake_db, **overrides):
    row = {
        "exam_type": "toeic",
        "test_id": "0001",
        "question_type": "write",
        "question_number": 1,
        "question_text": "題目",
        "options": "[]",
        "image_gdrive_url": "image-url",
        "audio_gdrive_url": None,
        "source_image_filename": "toeic_0001_write_1.png",
        "correct_answer": None,
        "explanation": None,
        "answer_source_filename": None,
    }
    row.update(overrides)
    return fake_db.insert("certificate_questions", row)


def test_sync_updates_existing_question_with_answer_key(fake_db):
    question_id = _seed_question(fake_db)
    files = [{"id": "a1", "name": "toeic_0001_write_1_ans.png", "mimeType": "image/png"}]
    gdrive_client = _make_gdrive_client(files, {"a1": b"answer-image-bytes"})
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.return_value = _answer_vision_reply()
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    row = fake_db.select("certificate_questions", where="id = %s", params=(question_id,), fetch_one=True)
    assert row["correct_answer"] == "B"
    assert row["explanation"] == "因為 xxx 所以答案是 B"
    assert row["answer_source_filename"] == "toeic_0001_write_1_ans.png"


def test_sync_processes_question_and_its_answer_key_in_same_batch(fake_db):
    # 題目照片跟答案照片同一批次一起上傳：sync_track1_from_drive 內部順序要確保答案能比對到。
    files = [
        {"id": "f1", "name": "toeic_0001_write_1.png", "mimeType": "image/png", "webViewLink": "url1"},
        {"id": "a1", "name": "toeic_0001_write_1_ans.png", "mimeType": "image/png"},
    ]
    gdrive_client = _make_gdrive_client(files, {"f1": b"image-bytes", "a1": b"answer-image-bytes"})
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.side_effect = [_vision_reply(), _answer_vision_reply()]
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    rows = fake_db.select("certificate_questions")
    assert len(rows) == 1
    assert rows[0]["correct_answer"] == "B"
    assert rows[0]["answer_source_filename"] == "toeic_0001_write_1_ans.png"


def test_sync_skips_answer_key_when_no_matching_question(fake_db):
    files = [{"id": "a1", "name": "toeic_9999_write_1_ans.png", "mimeType": "image/png"}]
    gdrive_client = _make_gdrive_client(files, {"a1": b"answer-image-bytes"})
    image_llm_clients = [MagicMock()]
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    gdrive_client.download_file.assert_not_called()
    image_llm_clients[0].generate_with_image.assert_not_called()


def test_sync_skips_already_processed_answer_key(fake_db):
    _seed_question(fake_db, correct_answer="A", explanation="舊詳解", answer_source_filename="toeic_0001_write_1_ans.png")
    files = [{"id": "a1", "name": "toeic_0001_write_1_ans.png", "mimeType": "image/png"}]
    gdrive_client = _make_gdrive_client(files, {"a1": b"answer-image-bytes"})
    image_llm_clients = [MagicMock()]
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    gdrive_client.download_file.assert_not_called()
    image_llm_clients[0].generate_with_image.assert_not_called()


def test_sync_skips_answer_key_when_vision_parse_fails(fake_db):
    question_id = _seed_question(fake_db)
    files = [{"id": "a1", "name": "toeic_0001_write_1_ans.png", "mimeType": "image/png"}]
    gdrive_client = _make_gdrive_client(files, {"a1": b"answer-image-bytes"})
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.return_value = "格式完全不對的回覆"
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    row = fake_db.select("certificate_questions", where="id = %s", params=(question_id,), fetch_one=True)
    assert row["correct_answer"] is None


def test_sync_skips_answer_key_when_vision_llm_raises(fake_db):
    question_id = _seed_question(fake_db)
    files = [{"id": "a1", "name": "toeic_0001_write_1_ans.png", "mimeType": "image/png"}]
    gdrive_client = _make_gdrive_client(files, {"a1": b"answer-image-bytes"})
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.side_effect = RuntimeError("Gemini 掛了")
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    row = fake_db.select("certificate_questions", where="id = %s", params=(question_id,), fetch_one=True)
    assert row["correct_answer"] is None


def test_sync_treats_unrecognized_answer_as_unresolved(fake_db):
    question_id = _seed_question(fake_db)
    files = [{"id": "a1", "name": "toeic_0001_write_1_ans.png", "mimeType": "image/png"}]
    gdrive_client = _make_gdrive_client(files, {"a1": b"answer-image-bytes"})
    image_llm_clients = [MagicMock()]
    image_llm_clients[0].generate_with_image.return_value = _answer_vision_reply(correct_answer="無法辨識")
    voice_client = MagicMock()

    toeic.sync_track1_from_drive(fake_db, gdrive_client, image_llm_clients, voice_client)

    row = fake_db.select("certificate_questions", where="id = %s", params=(question_id,), fetch_one=True)
    assert row["correct_answer"] is None


# --- _find_number_marker_starts ---


def test_find_number_marker_starts_uses_spoken_digit_markers():
    # 2026-09-07 新增：Robin 提出聽力錄音本來就會念題號（「Number 1」「Number 2」...），比停頓
    # 長度猜測可靠，優先掃描轉錄文字裡的題號標記直接切割。
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Number 1."},
        {"start": 1.2, "end": 5.0, "text": "Look at the picture."},
        {"start": 9.0, "end": 10.0, "text": "Number 2."},
        {"start": 10.2, "end": 14.0, "text": "Look at the picture again."},
        {"start": 18.0, "end": 19.0, "text": "Number 3."},
        {"start": 19.2, "end": 23.0, "text": "One more picture."},
    ]

    starts = toeic._find_number_marker_starts(segments, [1, 2, 3])

    assert starts == {1: 0.0, 2: 9.0, 3: 18.0}


def test_find_number_marker_starts_uses_spelled_out_words():
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Number One."},
        {"start": 8.0, "end": 9.0, "text": "Number Two."},
    ]

    starts = toeic._find_number_marker_starts(segments, [1, 2])

    assert starts == {1: 0.0, 2: 8.0}


def test_find_number_marker_starts_ignores_number_mentioned_early_in_content():
    # 2026-09-07 新增（Robin 提出疑慮）：內容裡提前出現「Number 2」字樣（例如題目內容剛好提到
    # 這個詞，或還沒輪到的題號被誤唸/誤辨識），但真正的第 2 題標記在後面才出現；依序往後掃描
    # 只會採用「輪到它時」找到的那次，不會被提前出現的誤判影響。
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Number 1."},
        {"start": 1.2, "end": 5.0, "text": "The flight departs, gate number 2, in ten minutes."},
        {"start": 9.0, "end": 10.0, "text": "Number 2."},
        {"start": 10.2, "end": 14.0, "text": "Look at the picture."},
    ]

    starts = toeic._find_number_marker_starts(segments, [1, 2])

    assert starts == {1: 0.0, 2: 9.0}


def test_find_number_marker_starts_handles_repeated_announcement_of_same_number():
    # 同一個題號被念了兩次（例如重複播報一次），採用第一次符合順序的那次，不會出錯。
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Number 1."},
        {"start": 1.2, "end": 2.0, "text": "Number 1, listen again."},
        {"start": 5.0, "end": 9.0, "text": "Look at the picture."},
        {"start": 15.0, "end": 16.0, "text": "Number 2."},
    ]

    starts = toeic._find_number_marker_starts(segments, [1, 2])

    assert starts == {1: 0.0, 2: 15.0}


def test_find_number_marker_starts_omits_missing_marker_instead_of_failing_whole_batch():
    # 2026-09-13 修改：只找到第 1、3 題的標記，第 2 題完全沒念出來（聽錯／口誤），不再是「整批
    # 放棄」，而是回傳部分結果——只有找得到標記的題號才會出現在回傳的 dict 裡。
    segments = [
        {"start": 0.0, "end": 1.0, "text": "Number 1."},
        {"start": 18.0, "end": 19.0, "text": "Number 3."},
    ]

    starts = toeic._find_number_marker_starts(segments, [1, 2, 3])

    assert starts == {1: 0.0, 3: 18.0}
    assert 2 not in starts


# --- split_audio_by_question_count ---


def test_split_audio_by_question_count_uses_number_markers():
    audio_bytes = _make_silent_mp3_bytes(12000)
    transcript_segments = [
        {"start": 0.0, "end": 1.0, "text": "Number 1."},
        {"start": 1.2, "end": 1.5, "text": "short question, tiny pause next"},
        {"start": 1.6, "end": 9.0, "text": "Number 2."},
        {"start": 9.2, "end": 11.9, "text": "a much longer second question"},
    ]

    result = toeic.split_audio_by_question_count(audio_bytes, [1, 2], transcript_segments)

    assert set(result.keys()) == {1, 2}
    q1 = AudioSegment.from_file(io.BytesIO(result[1]))
    q2 = AudioSegment.from_file(io.BytesIO(result[2]))
    # 第 1 題邊界＝自己的標記(0.0s)到下一題標記(1.6s)；第 2 題是它自己的標記(1.6s)到音檔結尾(12s)。
    assert abs(len(q1) - 1600) < 300
    assert abs(len(q2) - 10400) < 300


def test_split_audio_by_question_count_returns_correct_number_of_segments():
    audio_bytes = _make_silent_mp3_bytes(6000)
    transcript_segments = [
        {"start": 0.0, "end": 1.0, "text": "Number 1."},
        {"start": 4.5, "end": 5.5, "text": "Number 2."},
    ]

    result = toeic.split_audio_by_question_count(audio_bytes, [2, 1], transcript_segments)

    assert set(result.keys()) == {1, 2}
    for segment_bytes in result.values():
        assert isinstance(segment_bytes, bytes)
        assert len(segment_bytes) > 0
        # 確保每段都是可以被還原解析的合法音檔
        decoded = AudioSegment.from_file(io.BytesIO(segment_bytes))
        assert len(decoded) > 0


def test_split_audio_by_question_count_accepts_last_question_with_audio_end_boundary():
    # 最後一題只要找得到自己的開頭標記，結尾直接用音檔結尾即可，不需要「下一題」的標記。
    audio_bytes = _make_silent_mp3_bytes(6000)
    transcript_segments = [
        {"start": 0.0, "end": 1.0, "text": "Number 1."},
        {"start": 4.5, "end": 5.5, "text": "Number 2."},
    ]

    result = toeic.split_audio_by_question_count(audio_bytes, [1, 2], transcript_segments)

    assert set(result.keys()) == {1, 2}
    q2 = AudioSegment.from_file(io.BytesIO(result[2]))
    assert abs(len(q2) - 1500) < 300  # 4.5s ~ 6.0s（音檔結尾）


def test_split_audio_by_question_count_skips_question_missing_its_own_marker():
    # 2026-09-13 新增（Robin 明確要求「沒把握的題目就跳過，不要用猜的」）：第 2 題自己的標記
    # 完全找不到，不能用任何猜測法補上，這一題應該整個不出現在結果裡；第 1、3 題邊界仍然明確
    # （第 1 題：自己 -> 下一個找得到的標記其實是第 3 題？不行，因為 _find_number_marker_starts
    # 是依序掃描，找不到第 2 題不影響第 1 題「自己」的邊界判定，但第 1 題的「下一題」在
    # split_audio_by_question_count 是看 sorted_numbers 裡緊接著的題號（2），標記缺席時第 1
    # 題的結束邊界也無法確定，因此第 1 題也會被跳過；只有第 3 題（本批最後一題，只需要自己的
    # 標記）能確定。
    audio_bytes = _make_silent_mp3_bytes(18000)
    transcript_segments = [
        {"start": 0.0, "end": 1.0, "text": "Number 1."},
        {"start": 1.2, "end": 5.0, "text": "Look at the picture."},
        # 第 2 題的 "Number 2." 標記完全沒有念出來 / 沒被 Whisper 辨識到
        {"start": 14.0, "end": 15.0, "text": "Number 3."},
    ]

    result = toeic.split_audio_by_question_count(audio_bytes, [1, 2, 3], transcript_segments)

    assert 2 not in result
    assert 1 not in result  # 第 1 題找不到「下一題（第 2 題）」的標記，結束邊界不確定，一併跳過
    assert set(result.keys()) == {3}  # 只有最後一題，靠自己的標記＋音檔結尾，能 100% 確定


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


def test_generate_track2_waits_and_retries_on_quota_guard_error_without_wasting_attempt(fake_db):
    # 2026-08-24（見 docs/ADR/debug/skill-growth.md「TOEIC 單字題生成撞本地端節流上限」條目）：
    # 被本地端節流擋下時不該立刻放棄，應該等一下再試，且不該算浪費一次嘗試機會。
    llm_client = MagicMock()
    llm_client.generate_text.side_effect = [
        LLMQuotaGuardError("節流中"),
        LLMQuotaGuardError("節流中"),
        _vocab_reply("abundant"),
    ]
    sleep_calls = []

    generated = toeic.generate_track2_vocab_questions(
        fake_db, llm_client, count=1, sleep_func=sleep_calls.append
    )

    assert generated == 1
    assert llm_client.generate_text.call_count == 3
    assert sleep_calls == [toeic._QUOTA_GUARD_RETRY_DELAY_SECONDS] * 2


def test_generate_track2_quota_guard_retries_do_not_count_toward_max_attempts(fake_db):
    llm_client = MagicMock()
    # count=1 → max_attempts=3；被節流擋下 5 次不該算進 max_attempts，第 6 次才成功。
    llm_client.generate_text.side_effect = [LLMQuotaGuardError("節流中")] * 5 + [_vocab_reply("abundant")]

    generated = toeic.generate_track2_vocab_questions(
        fake_db, llm_client, count=1, sleep_func=lambda _seconds: None
    )

    assert generated == 1
    assert llm_client.generate_text.call_count == 6


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
