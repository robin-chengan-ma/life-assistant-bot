"""src/bot/certificate_answer.py 的單元測試（對應 robinson SPEC.md FR-27、FR-28，Step 3.3）。"""
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from src.bot import certificate_answer


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def _seed_owner(fake_db, **overrides):
    row = {"telegram_user_id": 999, "role": "Robin", "is_owner": True}
    row.update(overrides)
    return fake_db.insert("users", row)


def _seed_certificate_question(fake_db, **overrides):
    row = {
        "exam_type": "ielts", "question_type": "write", "test_id": "0001", "question_number": 1,
        "question_text": "What is the capital of France?",
        "options": ["A. Paris", "B. London", "C. Berlin", "D. Rome"],
        "correct_answer": "A", "explanation": "巴黎是法國首都。",
    }
    row.update(overrides)
    return fake_db.insert("certificate_questions", row)


def _seed_vocab_question(fake_db, **overrides):
    row = {
        "target_word": "abandon", "question_text": "abandon 中文意思是？",
        "option_a": "放棄", "option_b": "擁有", "option_c": "喜歡", "option_d": "討厭",
        "correct_option": "A", "example_sentence": "He abandoned the plan.",
        "example_sentence_translation": "他放棄了這個計畫。",
    }
    row.update(overrides)
    return fake_db.insert("toeic_vocab_questions", row)


def _seed_assignment(fake_db, **overrides):
    row = {
        "user_id": 1, "exam_type": "ielts", "assigned_date": date(2026, 8, 8),
        "certificate_question_id": None, "vocab_question_id": None, "is_review": False,
    }
    row.update(overrides)
    return fake_db.insert("certificate_daily_assignments", row)


# --- get_pending_assignments ---


def test_get_pending_assignments_returns_empty_when_none_assigned(fake_db):
    assert certificate_answer.get_pending_assignments(fake_db, 1) == []


def test_get_pending_assignments_excludes_answered(fake_db):
    qid = _seed_certificate_question(fake_db)
    a1 = _seed_assignment(fake_db, certificate_question_id=qid)
    fake_db.insert(
        "answer_logs",
        {
            "user_id": 1, "certificate_question_id": qid, "vocab_question_id": None,
            "exam_type": "ielts", "question_type": "write", "is_correct": True,
            "answered_on": date(2026, 8, 8), "assignment_id": a1,
        },
    )

    assert certificate_answer.get_pending_assignments(fake_db, 1) == []


def test_get_pending_assignments_includes_unanswered(fake_db):
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid)

    result = certificate_answer.get_pending_assignments(fake_db, 1)

    assert len(result) == 1
    assert result[0]["certificate_question_id"] == qid


def test_get_pending_assignments_excludes_superseded_batch(fake_db):
    """跨日晚補答（見模組 docstring）：新的一天推播建立新 assignment 後，前一批未作答的題目
    自動被視為跳過，不再出現在待作答清單。"""
    old_qid = _seed_certificate_question(fake_db, question_number=1)
    _seed_assignment(fake_db, certificate_question_id=old_qid, assigned_date=date(2026, 8, 7))
    new_qid = _seed_certificate_question(fake_db, question_number=2)
    _seed_assignment(fake_db, certificate_question_id=new_qid, assigned_date=date(2026, 8, 8))

    result = certificate_answer.get_pending_assignments(fake_db, 1)

    assert len(result) == 1
    assert result[0]["certificate_question_id"] == new_qid


def test_get_pending_assignments_allows_late_answer_before_superseded(fake_db):
    """23:00 靜默視為跳過不是硬性截止：只要還沒被新一天的 assignment 取代，仍算待作答。"""
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid, assigned_date=date(2026, 8, 7))

    result = certificate_answer.get_pending_assignments(fake_db, 1)

    assert len(result) == 1


def test_get_pending_assignments_orders_by_exam_type_then_id(fake_db):
    q_gcp = _seed_certificate_question(fake_db, exam_type="gcp")
    q_ielts = _seed_certificate_question(fake_db, exam_type="ielts")
    _seed_assignment(fake_db, exam_type="gcp", certificate_question_id=q_gcp)
    _seed_assignment(fake_db, exam_type="ielts", certificate_question_id=q_ielts)

    result = certificate_answer.get_pending_assignments(fake_db, 1)

    assert [row["exam_type"] for row in result] == ["gcp", "ielts"]


# --- _extract_answer_letter ---


def test_extract_answer_letter_handles_plain_letter():
    assert certificate_answer._extract_answer_letter("A") == "A"


def test_extract_answer_letter_handles_lowercase():
    assert certificate_answer._extract_answer_letter("b") == "B"


def test_extract_answer_letter_handles_dot_suffix():
    assert certificate_answer._extract_answer_letter("C. Berlin") == "C"


def test_extract_answer_letter_handles_parentheses():
    assert certificate_answer._extract_answer_letter("(D)") == "D"


def test_extract_answer_letter_returns_none_when_unparseable():
    assert certificate_answer._extract_answer_letter("無法辨識") is None
    assert certificate_answer._extract_answer_letter("") is None


# --- build_question_view ---


def test_build_question_view_for_certificate_question(fake_db):
    qid = _seed_certificate_question(fake_db, audio_gdrive_url=None, image_gdrive_url="https://drive/x.png")
    assignment = {"certificate_question_id": qid, "vocab_question_id": None}

    view = certificate_answer.build_question_view(fake_db, assignment)

    assert view["correct_letter"] == "A"
    assert view["question_type"] == "write"
    assert "What is the capital" in view["prompt"]
    assert "https://drive/x.png" in view["prompt"]
    assert view["explanation"] == "巴黎是法國首都。"


def test_build_question_view_includes_audio_link_for_listen_question(fake_db):
    qid = _seed_certificate_question(fake_db, question_type="listen", audio_gdrive_url="https://drive/x.mp3")
    assignment = {"certificate_question_id": qid, "vocab_question_id": None}

    view = certificate_answer.build_question_view(fake_db, assignment)

    assert "https://drive/x.mp3" in view["prompt"]


def test_build_question_view_returns_none_when_certificate_question_missing(fake_db):
    assignment = {"certificate_question_id": 9999, "vocab_question_id": None}
    assert certificate_answer.build_question_view(fake_db, assignment) is None


def test_build_question_view_returns_none_when_correct_answer_unparseable(fake_db):
    qid = _seed_certificate_question(fake_db, correct_answer="無法辨識")
    assignment = {"certificate_question_id": qid, "vocab_question_id": None}

    assert certificate_answer.build_question_view(fake_db, assignment) is None


def test_build_question_view_for_vocab_question(fake_db):
    qid = _seed_vocab_question(fake_db)
    assignment = {"certificate_question_id": None, "vocab_question_id": qid}

    view = certificate_answer.build_question_view(fake_db, assignment)

    assert view["correct_letter"] == "A"
    assert view["question_type"] == "vocab"
    assert "abandon 中文意思是" in view["prompt"]
    assert "He abandoned the plan." in view["explanation"]


def test_build_question_view_returns_none_when_vocab_question_missing(fake_db):
    assignment = {"certificate_question_id": None, "vocab_question_id": 9999}
    assert certificate_answer.build_question_view(fake_db, assignment) is None


# --- format helpers ---


def test_format_question_prompt_includes_position():
    view = {"prompt": "題目內容", "correct_letter": "A", "explanation": None, "question_type": "write"}
    text = certificate_answer.format_question_prompt(view, 2, 5)
    assert "2/5" in text
    assert "題目內容" in text
    assert "A/B/C/D" in text


def test_format_grading_feedback_correct_with_explanation():
    view = {"prompt": "x", "correct_letter": "A", "explanation": "詳解內容", "question_type": "write"}
    text = certificate_answer.format_grading_feedback(True, view)
    assert "答對了" in text
    assert "A" in text
    assert "詳解內容" in text


def test_format_grading_feedback_wrong_without_explanation():
    view = {"prompt": "x", "correct_letter": "B", "explanation": None, "question_type": "write"}
    text = certificate_answer.format_grading_feedback(False, view)
    assert "答錯了" in text
    assert "B" in text
    assert "詳解" not in text


# --- grade_answer / record_answer ---


def test_grade_answer_correct_case_insensitive():
    view = {"correct_letter": "A"}
    assert certificate_answer.grade_answer("a", view) is True
    assert certificate_answer.grade_answer("A", view) is True


def test_grade_answer_incorrect():
    view = {"correct_letter": "A"}
    assert certificate_answer.grade_answer("B", view) is False


def test_record_answer_writes_expected_row(fake_db):
    qid = _seed_certificate_question(fake_db)
    assignment_id = _seed_assignment(fake_db, certificate_question_id=qid)
    assignment = fake_db.select("certificate_daily_assignments", where="id = %s", params=(assignment_id,), fetch_one=True)
    view = {"prompt": "x", "correct_letter": "A", "explanation": None, "question_type": "write"}

    log_id = certificate_answer.record_answer(fake_db, 1, assignment, view, True, date(2026, 8, 8))

    row = fake_db.select("answer_logs", where="id = %s", params=(log_id,), fetch_one=True)
    assert row["user_id"] == 1
    assert row["certificate_question_id"] == qid
    assert row["vocab_question_id"] is None
    assert row["exam_type"] == "ielts"
    assert row["question_type"] == "write"
    assert row["is_correct"] is True
    assert row["answered_on"] == date(2026, 8, 8)
    assert row["assignment_id"] == assignment_id


# --- check_and_push_answer_reminders ---


def test_reminder_skips_outside_of_8pm_window(fake_db):
    _seed_owner(fake_db)
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid)
    telegram_client = MagicMock()

    certificate_answer.check_and_push_answer_reminders(fake_db, telegram_client, now=_utc(2026, 8, 8, 3, 0))

    telegram_client.send_text.assert_not_called()


def test_reminder_skips_when_no_owner_bound(fake_db):
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid)
    telegram_client = MagicMock()

    certificate_answer.check_and_push_answer_reminders(fake_db, telegram_client, now=_utc(2026, 8, 8, 12, 0))

    telegram_client.send_text.assert_not_called()


def test_reminder_skips_when_feature_toggle_disabled(fake_db):
    owner_id = _seed_owner(fake_db)
    fake_db.insert("feature_toggles", {"user_id": owner_id, "feature_key": "certificate", "is_enabled": False})
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid)
    telegram_client = MagicMock()

    certificate_answer.check_and_push_answer_reminders(fake_db, telegram_client, now=_utc(2026, 8, 8, 12, 0))

    telegram_client.send_text.assert_not_called()


def test_reminder_skips_when_nothing_pending(fake_db):
    _seed_owner(fake_db)
    telegram_client = MagicMock()

    certificate_answer.check_and_push_answer_reminders(fake_db, telegram_client, now=_utc(2026, 8, 8, 12, 0))

    telegram_client.send_text.assert_not_called()


def test_reminder_sends_message_with_pending_count(fake_db):
    _seed_owner(fake_db)
    qid1 = _seed_certificate_question(fake_db, question_number=1)
    qid2 = _seed_certificate_question(fake_db, question_number=2)
    _seed_assignment(fake_db, certificate_question_id=qid1)
    _seed_assignment(fake_db, certificate_question_id=qid2)
    telegram_client = MagicMock()

    certificate_answer.check_and_push_answer_reminders(fake_db, telegram_client, now=_utc(2026, 8, 8, 12, 0))

    telegram_client.send_text.assert_called_once()
    call_kwargs = telegram_client.send_text.call_args.kwargs
    assert call_kwargs["chat_id"] == 999
    assert "2 題" in call_kwargs["text"]


def test_reminder_does_not_repeat_within_same_day(fake_db):
    _seed_owner(fake_db)
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid)
    telegram_client = MagicMock()

    certificate_answer.check_and_push_answer_reminders(fake_db, telegram_client, now=_utc(2026, 8, 8, 12, 0))
    certificate_answer.check_and_push_answer_reminders(fake_db, telegram_client, now=_utc(2026, 8, 8, 12, 15))

    telegram_client.send_text.assert_called_once()
