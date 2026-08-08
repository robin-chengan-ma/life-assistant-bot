"""src/bot/certificate_quiz.py 的單元測試（對應 robinson SPEC.md FR-26、ADR-20，Step 3.3）。"""
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from src.bot import certificate_quiz


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def _seed_owner(fake_db, **overrides):
    row = {"telegram_user_id": 999, "role": "Robin", "is_owner": True}
    row.update(overrides)
    return fake_db.insert("users", row)


def _seed_certificate_question(fake_db, **overrides):
    row = {
        "exam_type": "ielts",
        "question_type": "write",
        "test_id": "0001",
        "question_number": 1,
        "question_text": "題目",
        "options": ["A", "B", "C", "D"],
        "correct_answer": "A",
        "explanation": "詳解",
    }
    row.update(overrides)
    return fake_db.insert("certificate_questions", row)


def _seed_vocab_question(fake_db, **overrides):
    row = {
        "target_word": "abandon",
        "question_text": "題目",
        "option_a": "a",
        "option_b": "b",
        "option_c": "c",
        "option_d": "d",
        "correct_option": "A",
        "example_sentence": "e",
        "example_sentence_translation": "t",
    }
    row.update(overrides)
    return fake_db.insert("toeic_vocab_questions", row)


def _seed_answer_log(fake_db, *, user_id, exam_type, question_type, is_correct, created_at, **overrides):
    row = {
        "user_id": user_id,
        "exam_type": exam_type,
        "question_type": question_type,
        "certificate_question_id": None,
        "vocab_question_id": None,
        "is_correct": is_correct,
        "answered_on": created_at.date(),
        "created_at": created_at,
    }
    row.update(overrides)
    return fake_db.insert("answer_logs", row)


# --- _split_by_ratio ---


def test_split_by_ratio_splits_evenly_with_no_remainder():
    assert certificate_quiz._split_by_ratio(6, [1, 2, 3]) == [1, 2, 3]


def test_split_by_ratio_distributes_remainder_to_earlier_items():
    assert certificate_quiz._split_by_ratio(7, [1, 2, 3]) == [2, 2, 3]


def test_split_by_ratio_returns_zeros_when_total_is_zero():
    assert certificate_quiz._split_by_ratio(0, [1, 2, 3]) == [0, 0, 0]


def test_split_by_ratio_returns_zeros_when_ratio_sum_is_zero():
    assert certificate_quiz._split_by_ratio(6, [0, 0]) == [0, 0]


# --- get_active_schedule_override / effective_daily_question_count ---


def testget_active_schedule_override_returns_none_when_no_overrides(fake_db):
    assert certificate_quiz.get_active_schedule_override(fake_db, 1, "ielts", date(2026, 8, 8)) is None


def testget_active_schedule_override_returns_matching_range(fake_db):
    fake_db.insert(
        "certificate_daily_schedule_overrides",
        {
            "user_id": 1, "exam_type": "ielts", "start_date": date(2026, 8, 1), "end_date": date(2026, 8, 5),
            "daily_question_count": 0,
        },
    )
    fake_db.insert(
        "certificate_daily_schedule_overrides",
        {
            "user_id": 1, "exam_type": "ielts", "start_date": date(2026, 8, 8), "end_date": date(2026, 8, 10),
            "daily_question_count": 8,
        },
    )

    result = certificate_quiz.get_active_schedule_override(fake_db, 1, "ielts", date(2026, 8, 9))

    assert result["daily_question_count"] == 8


def test_effective_count_uses_default_when_nothing_configured(fake_db):
    assert certificate_quiz.effective_daily_question_count(fake_db, 1, "ielts", date(2026, 8, 8)) == 6


def test_effective_count_uses_settings_when_no_override(fake_db):
    fake_db.insert(
        "certificate_daily_settings",
        {
            "user_id": 1, "exam_type": "ielts", "daily_question_count": 10,
            "review_ratio_new": 7, "review_ratio_review": 3,
        },
    )

    assert certificate_quiz.effective_daily_question_count(fake_db, 1, "ielts", date(2026, 8, 8)) == 10


def test_effective_count_uses_override_when_date_in_range(fake_db):
    fake_db.insert(
        "certificate_daily_settings",
        {
            "user_id": 1, "exam_type": "ielts", "daily_question_count": 10,
            "review_ratio_new": 7, "review_ratio_review": 3,
        },
    )
    fake_db.insert(
        "certificate_daily_schedule_overrides",
        {
            "user_id": 1, "exam_type": "ielts", "start_date": date(2026, 8, 8), "end_date": date(2026, 8, 10),
            "daily_question_count": 0,
        },
    )

    assert certificate_quiz.effective_daily_question_count(fake_db, 1, "ielts", date(2026, 8, 9)) == 0


def test_effective_count_falls_back_to_settings_when_override_out_of_range(fake_db):
    fake_db.insert(
        "certificate_daily_settings",
        {
            "user_id": 1, "exam_type": "ielts", "daily_question_count": 10,
            "review_ratio_new": 7, "review_ratio_review": 3,
        },
    )
    fake_db.insert(
        "certificate_daily_schedule_overrides",
        {
            "user_id": 1, "exam_type": "ielts", "start_date": date(2026, 8, 8), "end_date": date(2026, 8, 10),
            "daily_question_count": 0,
        },
    )

    assert certificate_quiz.effective_daily_question_count(fake_db, 1, "ielts", date(2026, 8, 20)) == 10


# --- distinct_exam_types_with_questions ---


def testdistinct_exam_types_with_questions_excludes_questions_without_correct_answer(fake_db):
    _seed_certificate_question(fake_db, exam_type="ielts", correct_answer=None)
    _seed_certificate_question(fake_db, exam_type="gcp", correct_answer="A")

    assert certificate_quiz.distinct_exam_types_with_questions(fake_db) == ["gcp"]


# --- assign_daily_questions ---


def test_assign_returns_empty_list_when_effective_count_is_zero(fake_db):
    fake_db.insert(
        "certificate_daily_schedule_overrides",
        {
            "user_id": 1, "exam_type": "ielts", "start_date": date(2026, 8, 8), "end_date": date(2026, 8, 8),
            "daily_question_count": 0,
        },
    )

    result = certificate_quiz.assign_daily_questions(fake_db, 1, "ielts", date(2026, 8, 8))

    assert result == []


def test_assign_is_idempotent_within_same_day(fake_db):
    for i in range(6):
        _seed_certificate_question(fake_db, exam_type="ielts", question_number=i)

    first = certificate_quiz.assign_daily_questions(fake_db, 1, "ielts", date(2026, 8, 8))
    second = certificate_quiz.assign_daily_questions(fake_db, 1, "ielts", date(2026, 8, 8))

    assert first == second
    assert len(fake_db.select("certificate_daily_assignments")) == len(first)


def test_assign_picks_new_questions_for_non_toeic_exam_type(fake_db):
    ids = {_seed_certificate_question(fake_db, exam_type="ielts", question_number=i) for i in range(6)}

    result = certificate_quiz.assign_daily_questions(fake_db, 1, "ielts", date(2026, 8, 8))

    assert len(result) == 6
    assert all(a["is_review"] is False for a in result)
    assert all(a["vocab_question_id"] is None for a in result)
    assert {a["certificate_question_id"] for a in result} == ids


def test_assign_splits_toeic_tracks_by_default_ratio(fake_db):
    listen_ids = {
        _seed_certificate_question(fake_db, exam_type="toeic", question_type="listen", question_number=i)
        for i in range(3)
    }
    write_ids = {
        _seed_certificate_question(fake_db, exam_type="toeic", question_type="write", question_number=i)
        for i in range(6)
    }
    for i in range(9):
        _seed_vocab_question(fake_db, target_word=f"word{i}")

    result = certificate_quiz.assign_daily_questions(fake_db, 1, "toeic", date(2026, 8, 8))

    assert len(result) == 6
    listen_count = sum(1 for a in result if a["certificate_question_id"] in listen_ids)
    write_count = sum(1 for a in result if a["certificate_question_id"] in write_ids)
    vocab_count = sum(1 for a in result if a["vocab_question_id"] is not None)
    assert (listen_count, write_count, vocab_count) == (1, 2, 3)


def test_assign_uses_custom_toeic_track_ratios_from_settings(fake_db):
    fake_db.insert(
        "certificate_daily_settings",
        {
            "user_id": 1, "exam_type": "toeic", "daily_question_count": 4,
            "review_ratio_new": 7, "review_ratio_review": 3,
            "listen_ratio": 2, "write_ratio": 1, "vocab_ratio": 1,
        },
    )
    listen_ids = {
        _seed_certificate_question(fake_db, exam_type="toeic", question_type="listen", question_number=i)
        for i in range(2)
    }
    write_ids = {_seed_certificate_question(fake_db, exam_type="toeic", question_type="write", question_number=1)}
    _seed_vocab_question(fake_db)

    result = certificate_quiz.assign_daily_questions(fake_db, 1, "toeic", date(2026, 8, 8))

    assert len(result) == 4
    listen_count = sum(1 for a in result if a["certificate_question_id"] in listen_ids)
    write_count = sum(1 for a in result if a["certificate_question_id"] in write_ids)
    vocab_count = sum(1 for a in result if a["vocab_question_id"] is not None)
    assert (listen_count, write_count, vocab_count) == (2, 1, 1)


def test_assign_prioritizes_review_pool_for_wrongly_answered_questions(fake_db):
    wrong_id = _seed_certificate_question(fake_db, exam_type="ielts", question_number=1)
    new_ids = {_seed_certificate_question(fake_db, exam_type="ielts", question_number=i) for i in range(2, 5)}
    _seed_answer_log(
        fake_db, user_id=1, exam_type="ielts", question_type="write", certificate_question_id=wrong_id,
        is_correct=False, created_at=_utc(2026, 8, 7, 10, 0),
    )
    fake_db.insert(
        "certificate_daily_settings",
        {
            "user_id": 1, "exam_type": "ielts", "daily_question_count": 4,
            "review_ratio_new": 3, "review_ratio_review": 1,
        },
    )

    result = certificate_quiz.assign_daily_questions(fake_db, 1, "ielts", date(2026, 8, 8))

    assert len(result) == 4
    review_ids = {a["certificate_question_id"] for a in result if a["is_review"]}
    new_result_ids = {a["certificate_question_id"] for a in result if not a["is_review"]}
    assert review_ids == {wrong_id}
    assert new_result_ids == new_ids


def test_assign_backfills_with_new_questions_when_review_pool_insufficient(fake_db):
    new_ids = {_seed_certificate_question(fake_db, exam_type="ielts", question_number=i) for i in range(1, 5)}
    fake_db.insert(
        "certificate_daily_settings",
        {
            "user_id": 1, "exam_type": "ielts", "daily_question_count": 4,
            "review_ratio_new": 3, "review_ratio_review": 1,
        },
    )

    result = certificate_quiz.assign_daily_questions(fake_db, 1, "ielts", date(2026, 8, 8))

    assert len(result) == 4
    assert all(a["is_review"] is False for a in result)
    assert {a["certificate_question_id"] for a in result} == new_ids


def test_assign_excludes_questions_already_answered_correctly(fake_db):
    correct_id = _seed_certificate_question(fake_db, exam_type="ielts", question_number=1)
    other_ids = {_seed_certificate_question(fake_db, exam_type="ielts", question_number=i) for i in range(2, 5)}
    _seed_answer_log(
        fake_db, user_id=1, exam_type="ielts", question_type="write", certificate_question_id=correct_id,
        is_correct=True, created_at=_utc(2026, 8, 7, 10, 0),
    )
    fake_db.insert(
        "certificate_daily_settings",
        {
            "user_id": 1, "exam_type": "ielts", "daily_question_count": 3,
            "review_ratio_new": 1, "review_ratio_review": 0,
        },
    )

    result = certificate_quiz.assign_daily_questions(fake_db, 1, "ielts", date(2026, 8, 8))

    result_ids = {a["certificate_question_id"] for a in result}
    assert correct_id not in result_ids
    assert result_ids == other_ids


def test_assign_uses_latest_answer_when_question_answered_multiple_times(fake_db):
    qid = _seed_certificate_question(fake_db, exam_type="ielts", question_number=1)
    other_ids = {_seed_certificate_question(fake_db, exam_type="ielts", question_number=i) for i in range(2, 5)}
    _seed_answer_log(
        fake_db, user_id=1, exam_type="ielts", question_type="write", certificate_question_id=qid,
        is_correct=False, created_at=_utc(2026, 8, 6, 10, 0),
    )
    _seed_answer_log(
        fake_db, user_id=1, exam_type="ielts", question_type="write", certificate_question_id=qid,
        is_correct=True, created_at=_utc(2026, 8, 7, 10, 0),
    )
    fake_db.insert(
        "certificate_daily_settings",
        {
            "user_id": 1, "exam_type": "ielts", "daily_question_count": 3,
            "review_ratio_new": 1, "review_ratio_review": 1,
        },
    )

    result = certificate_quiz.assign_daily_questions(fake_db, 1, "ielts", date(2026, 8, 8))

    result_ids = {a["certificate_question_id"] for a in result}
    assert qid not in result_ids
    assert result_ids == other_ids


def test_assign_skips_toeic_tracks_with_zero_count(fake_db):
    """total 太小時，依比例算出來某幾軌可能是 0 題，這幾軌要整個跳過，不查詢/不指派（決策 1）。"""
    fake_db.insert(
        "certificate_daily_settings",
        {
            "user_id": 1, "exam_type": "toeic", "daily_question_count": 1,
            "review_ratio_new": 7, "review_ratio_review": 3,
        },
    )
    listen_id = _seed_certificate_question(fake_db, exam_type="toeic", question_type="listen", question_number=1)

    result = certificate_quiz.assign_daily_questions(fake_db, 1, "toeic", date(2026, 8, 8))

    assert len(result) == 1
    assert result[0]["certificate_question_id"] == listen_id
    assert result[0]["vocab_question_id"] is None


def test_assign_uses_default_review_ratio_when_no_settings(fake_db):
    wrong_id = _seed_certificate_question(fake_db, exam_type="toefl", question_number=1)
    for i in range(2, 7):
        _seed_certificate_question(fake_db, exam_type="toefl", question_number=i)
    _seed_answer_log(
        fake_db, user_id=1, exam_type="toefl", question_type="write", certificate_question_id=wrong_id,
        is_correct=False, created_at=_utc(2026, 8, 7, 10, 0),
    )

    result = certificate_quiz.assign_daily_questions(fake_db, 1, "toefl", date(2026, 8, 8))

    assert len(result) == 6
    review_ids = {a["certificate_question_id"] for a in result if a["is_review"]}
    assert review_ids == {wrong_id}


# --- check_and_push_daily_quiz ---


def test_push_skips_outside_of_8am_window(fake_db):
    _seed_owner(fake_db)
    for i in range(6):
        _seed_certificate_question(fake_db, exam_type="ielts", question_number=i)
    telegram_client = MagicMock()

    certificate_quiz.check_and_push_daily_quiz(fake_db, telegram_client, now=_utc(2026, 8, 8, 3, 0))

    telegram_client.send_text.assert_not_called()


def test_push_skips_when_no_owner_bound(fake_db):
    for i in range(6):
        _seed_certificate_question(fake_db, exam_type="ielts", question_number=i)
    telegram_client = MagicMock()

    certificate_quiz.check_and_push_daily_quiz(fake_db, telegram_client, now=_utc(2026, 8, 8, 0, 0))

    telegram_client.send_text.assert_not_called()


def test_push_skips_when_feature_toggle_disabled(fake_db):
    owner_id = _seed_owner(fake_db)
    fake_db.insert("feature_toggles", {"user_id": owner_id, "feature_key": "certificate", "is_enabled": False})
    for i in range(6):
        _seed_certificate_question(fake_db, exam_type="ielts", question_number=i)
    telegram_client = MagicMock()

    certificate_quiz.check_and_push_daily_quiz(fake_db, telegram_client, now=_utc(2026, 8, 8, 0, 0))

    telegram_client.send_text.assert_not_called()


def test_push_skips_when_no_exam_types_have_answered_questions(fake_db):
    _seed_owner(fake_db)
    _seed_certificate_question(fake_db, exam_type="ielts", correct_answer=None)
    telegram_client = MagicMock()

    certificate_quiz.check_and_push_daily_quiz(fake_db, telegram_client, now=_utc(2026, 8, 8, 0, 0))

    telegram_client.send_text.assert_not_called()


def test_push_sends_message_with_question_counts(fake_db):
    _seed_owner(fake_db)
    for i in range(6):
        _seed_certificate_question(fake_db, exam_type="ielts", question_number=i)
    telegram_client = MagicMock()

    certificate_quiz.check_and_push_daily_quiz(fake_db, telegram_client, now=_utc(2026, 8, 8, 0, 0))

    telegram_client.send_text.assert_called_once()
    call_kwargs = telegram_client.send_text.call_args.kwargs
    assert call_kwargs["chat_id"] == 999
    assert "ielts" in call_kwargs["text"]
    assert "6 題" in call_kwargs["text"]


def test_push_writes_assignments_that_answering_flow_can_read_later(fake_db):
    _seed_owner(fake_db)
    for i in range(6):
        _seed_certificate_question(fake_db, exam_type="ielts", question_number=i)
    telegram_client = MagicMock()

    certificate_quiz.check_and_push_daily_quiz(fake_db, telegram_client, now=_utc(2026, 8, 8, 0, 0))

    rows = fake_db.select(
        "certificate_daily_assignments",
        where="user_id = %s AND exam_type = %s AND assigned_date = %s",
        params=(1, "ielts", date(2026, 8, 8)),
    )
    assert len(rows) == 6


def test_push_does_not_repeat_within_same_hour(fake_db):
    _seed_owner(fake_db)
    for i in range(6):
        _seed_certificate_question(fake_db, exam_type="ielts", question_number=i)
    telegram_client = MagicMock()

    certificate_quiz.check_and_push_daily_quiz(fake_db, telegram_client, now=_utc(2026, 8, 8, 0, 0))
    certificate_quiz.check_and_push_daily_quiz(fake_db, telegram_client, now=_utc(2026, 8, 8, 0, 15))

    telegram_client.send_text.assert_called_once()
    assert len(fake_db.select("certificate_daily_assignments")) == 6


def test_push_sends_separate_message_per_exam_type(fake_db):
    _seed_owner(fake_db)
    for i in range(6):
        _seed_certificate_question(fake_db, exam_type="ielts", question_number=i)
    for i in range(6):
        _seed_certificate_question(fake_db, exam_type="gcp", question_number=i)
    telegram_client = MagicMock()

    certificate_quiz.check_and_push_daily_quiz(fake_db, telegram_client, now=_utc(2026, 8, 8, 0, 0))

    assert telegram_client.send_text.call_count == 2


def test_push_continues_with_other_exam_types_when_one_fails(fake_db, monkeypatch):
    """某個 exam_type 出題失敗（例如題庫資料異常）不該擋住其他證照類型的推播（見模組 docstring）。"""
    _seed_owner(fake_db)
    for i in range(6):
        _seed_certificate_question(fake_db, exam_type="ielts", question_number=i)
    for i in range(6):
        _seed_certificate_question(fake_db, exam_type="gcp", question_number=i)
    telegram_client = MagicMock()

    original_assign = certificate_quiz.assign_daily_questions

    def _flaky_assign(db, user_id, exam_type, target_date):
        if exam_type == "gcp":
            raise RuntimeError("題庫資料異常")
        return original_assign(db, user_id, exam_type, target_date)

    monkeypatch.setattr(certificate_quiz, "assign_daily_questions", _flaky_assign)

    certificate_quiz.check_and_push_daily_quiz(fake_db, telegram_client, now=_utc(2026, 8, 8, 0, 0))

    telegram_client.send_text.assert_called_once()
    assert "ielts" in telegram_client.send_text.call_args.kwargs["text"]


def test_push_skips_exam_type_with_zero_effective_count(fake_db):
    _seed_owner(fake_db)
    for i in range(6):
        _seed_certificate_question(fake_db, exam_type="ielts", question_number=i)
    fake_db.insert(
        "certificate_daily_schedule_overrides",
        {
            "user_id": 1, "exam_type": "ielts", "start_date": date(2026, 8, 8), "end_date": date(2026, 8, 8),
            "daily_question_count": 0,
        },
    )
    telegram_client = MagicMock()

    certificate_quiz.check_and_push_daily_quiz(fake_db, telegram_client, now=_utc(2026, 8, 8, 0, 0))

    telegram_client.send_text.assert_not_called()
