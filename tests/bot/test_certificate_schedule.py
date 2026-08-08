"""src/bot/certificate_schedule.py 的單元測試（對應 robinson SPEC.md FR-26、ADR-20 決策 5、6）。"""
from datetime import date

from src.bot import certificate_schedule


def _seed_certificate_question(fake_db, **overrides):
    row = {
        "exam_type": "ielts", "question_type": "write", "test_id": "0001", "question_number": 1,
        "question_text": "題目", "options": ["A", "B", "C", "D"], "correct_answer": "A",
    }
    row.update(overrides)
    return fake_db.insert("certificate_questions", row)


def _seed_assignment(fake_db, **overrides):
    row = {
        "user_id": 1, "exam_type": "ielts", "assigned_date": date(2026, 8, 8),
        "certificate_question_id": None, "vocab_question_id": None, "is_review": False,
    }
    row.update(overrides)
    return fake_db.insert("certificate_daily_assignments", row)


def _seed_settings(fake_db, **overrides):
    row = {
        "user_id": 1, "exam_type": "ielts", "daily_question_count": 6,
        "review_ratio_new": 7, "review_ratio_review": 3,
    }
    row.update(overrides)
    return fake_db.insert("certificate_daily_settings", row)


# --- delete_unanswered_assignments ---


def test_delete_unanswered_assignments_removes_unanswered_only(fake_db):
    qid1 = _seed_certificate_question(fake_db, question_number=1)
    qid2 = _seed_certificate_question(fake_db, question_number=2)
    answered_id = _seed_assignment(fake_db, certificate_question_id=qid1)
    unanswered_id = _seed_assignment(fake_db, certificate_question_id=qid2)
    fake_db.insert(
        "answer_logs",
        {
            "user_id": 1, "certificate_question_id": qid1, "vocab_question_id": None,
            "exam_type": "ielts", "question_type": "write", "is_correct": True,
            "answered_on": date(2026, 8, 8), "assignment_id": answered_id,
        },
    )

    deleted = certificate_schedule.delete_unanswered_assignments(fake_db, 1, "ielts", date(2026, 8, 8))

    assert deleted == 1
    remaining = fake_db.select("certificate_daily_assignments")
    assert [row["id"] for row in remaining] == [answered_id]
    assert fake_db.select("certificate_daily_assignments", where="id = %s", params=(unanswered_id,), fetch_one=True) is None


def test_delete_unanswered_assignments_returns_zero_when_none_exist(fake_db):
    assert certificate_schedule.delete_unanswered_assignments(fake_db, 1, "ielts", date(2026, 8, 8)) == 0


# --- apply_cancel ---


def test_apply_cancel_deletes_today_and_sets_zero_override(fake_db):
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid)

    certificate_schedule.apply_cancel(fake_db, 1, "ielts", date(2026, 8, 8))

    assert fake_db.select("certificate_daily_assignments") == []
    override = fake_db.select("certificate_daily_schedule_overrides")[0]
    assert override["start_date"] == date(2026, 8, 8)
    assert override["end_date"] == date(2026, 8, 8)
    assert override["daily_question_count"] == 0


# --- apply_move ---


def test_apply_move_cancels_today_and_moves_count_to_target(fake_db):
    _seed_settings(fake_db, daily_question_count=6)
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid)

    certificate_schedule.apply_move(fake_db, 1, "ielts", date(2026, 8, 8), date(2026, 8, 10))

    assert fake_db.select("certificate_daily_assignments") == []
    overrides = fake_db.select("certificate_daily_schedule_overrides")
    today_override = next(o for o in overrides if o["start_date"] == date(2026, 8, 8))
    target_override = next(o for o in overrides if o["start_date"] == date(2026, 8, 10))
    assert today_override["daily_question_count"] == 0
    assert target_override["daily_question_count"] == 6


def test_apply_move_uses_current_effective_count_not_default(fake_db):
    fake_db.insert(
        "certificate_daily_schedule_overrides",
        {"user_id": 1, "exam_type": "ielts", "start_date": date(2026, 8, 8), "end_date": date(2026, 8, 8), "daily_question_count": 9},
    )

    certificate_schedule.apply_move(fake_db, 1, "ielts", date(2026, 8, 8), date(2026, 8, 10))

    overrides = fake_db.select("certificate_daily_schedule_overrides")
    target_override = next(o for o in overrides if o["start_date"] == date(2026, 8, 10))
    assert target_override["daily_question_count"] == 9


# --- apply_range_override ---


def test_apply_range_override_writes_override_row(fake_db):
    certificate_schedule.apply_range_override(fake_db, 1, "ielts", date(2026, 8, 1), date(2026, 8, 20), date(2026, 8, 25), 10)

    override = fake_db.select("certificate_daily_schedule_overrides")[0]
    assert override["start_date"] == date(2026, 8, 20)
    assert override["end_date"] == date(2026, 8, 25)
    assert override["daily_question_count"] == 10


def test_apply_range_override_cleans_up_today_when_range_covers_today(fake_db):
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid, assigned_date=date(2026, 8, 8))

    certificate_schedule.apply_range_override(fake_db, 1, "ielts", date(2026, 8, 8), date(2026, 8, 5), date(2026, 8, 10), 3)

    assert fake_db.select("certificate_daily_assignments") == []


def test_apply_range_override_does_not_touch_today_when_range_excludes_today(fake_db):
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid, assigned_date=date(2026, 8, 8))

    certificate_schedule.apply_range_override(fake_db, 1, "ielts", date(2026, 8, 8), date(2026, 8, 20), date(2026, 8, 25), 3)

    assert len(fake_db.select("certificate_daily_assignments")) == 1


# --- compute_spread_plan ---


def test_compute_spread_plan_returns_empty_when_nothing_to_spread(fake_db):
    fake_db.insert(
        "certificate_daily_schedule_overrides",
        {"user_id": 1, "exam_type": "ielts", "start_date": date(2026, 8, 8), "end_date": date(2026, 8, 8), "daily_question_count": 0},
    )

    assert certificate_schedule.compute_spread_plan(fake_db, 1, "ielts", date(2026, 8, 8)) == []


def test_compute_spread_plan_spreads_one_per_day_starting_tomorrow(fake_db):
    _seed_settings(fake_db, daily_question_count=3)

    plan = certificate_schedule.compute_spread_plan(fake_db, 1, "ielts", date(2026, 8, 8))

    assert plan == [
        {"date": date(2026, 8, 9), "new_count": 4},
        {"date": date(2026, 8, 10), "new_count": 4},
        {"date": date(2026, 8, 11), "new_count": 4},
    ]


def test_compute_spread_plan_skips_days_with_existing_override(fake_db):
    _seed_settings(fake_db, daily_question_count=3)
    fake_db.insert(
        "certificate_daily_schedule_overrides",
        {"user_id": 1, "exam_type": "ielts", "start_date": date(2026, 8, 9), "end_date": date(2026, 8, 9), "daily_question_count": 8},
    )

    plan = certificate_schedule.compute_spread_plan(fake_db, 1, "ielts", date(2026, 8, 8))

    dates = [item["date"] for item in plan]
    assert date(2026, 8, 9) not in dates
    assert dates == [date(2026, 8, 10), date(2026, 8, 11), date(2026, 8, 12)]


def test_compute_spread_plan_uses_default_count_when_no_settings(fake_db):
    plan = certificate_schedule.compute_spread_plan(fake_db, 1, "ielts", date(2026, 8, 8))
    assert len(plan) == 6  # 預設每日出題數量


def test_compute_spread_plan_with_custom_num_days_splits_evenly(fake_db):
    _seed_settings(fake_db, daily_question_count=7)

    plan = certificate_schedule.compute_spread_plan(fake_db, 1, "ielts", date(2026, 8, 8), num_days=3)

    # 7 題分 3 天：divmod(7, 3) = (2, 1)，餘數 1 個分給第一天，該天原本題數（7）+3=10。
    assert plan == [
        {"date": date(2026, 8, 9), "new_count": 10},
        {"date": date(2026, 8, 10), "new_count": 9},
        {"date": date(2026, 8, 11), "new_count": 9},
    ]


def test_compute_spread_plan_with_custom_num_days_skips_override_days(fake_db):
    _seed_settings(fake_db, daily_question_count=4)
    fake_db.insert(
        "certificate_daily_schedule_overrides",
        {"user_id": 1, "exam_type": "ielts", "start_date": date(2026, 8, 9), "end_date": date(2026, 8, 9), "daily_question_count": 8},
    )

    plan = certificate_schedule.compute_spread_plan(fake_db, 1, "ielts", date(2026, 8, 8), num_days=2)

    dates = [item["date"] for item in plan]
    assert date(2026, 8, 9) not in dates
    assert dates == [date(2026, 8, 10), date(2026, 8, 11)]


# --- apply_spread_plan ---


def test_apply_spread_plan_writes_all_overrides_and_cleans_today(fake_db):
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid)
    plan = [{"date": date(2026, 8, 9), "new_count": 4}, {"date": date(2026, 8, 10), "new_count": 4}]

    certificate_schedule.apply_spread_plan(fake_db, 1, "ielts", date(2026, 8, 8), plan)

    assert fake_db.select("certificate_daily_assignments") == []
    overrides = fake_db.select("certificate_daily_schedule_overrides")
    assert len(overrides) == 3  # 今天歸零 + plan 兩天
    today_override = next(o for o in overrides if o["start_date"] == date(2026, 8, 8))
    assert today_override["daily_question_count"] == 0
    for item in plan:
        matching = next(o for o in overrides if o["start_date"] == item["date"])
        assert matching["daily_question_count"] == item["new_count"]


# --- format_spread_proposal ---


def test_format_spread_proposal_lists_each_date():
    plan = [{"date": date(2026, 8, 9), "new_count": 4}, {"date": date(2026, 8, 10), "new_count": 4}]
    text = certificate_schedule.format_spread_proposal(plan)
    assert "8/9" in text
    assert "8/10" in text
    assert "+1 題" in text


def test_format_spread_proposal_empty_plan():
    text = certificate_schedule.format_spread_proposal([])
    assert "沒有題目可以分攤" in text
