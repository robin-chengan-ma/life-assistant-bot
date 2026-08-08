"""src/bot/certificate_stats.py 的單元測試（對應 robinson SPEC.md FR-29、ADR-19 決策 4、5）。"""
from datetime import date

from src.bot import certificate_stats


def _seed_answer(fake_db, **overrides):
    row = {
        "user_id": 1, "certificate_question_id": 1, "vocab_question_id": None,
        "exam_type": "toeic", "question_type": "write", "is_correct": True,
        "answered_on": date(2026, 8, 3), "assignment_id": None,
    }
    row.update(overrides)
    return fake_db.insert("answer_logs", row)


def _seed_score(fake_db, **overrides):
    row = {"user_id": 1, "exam_type": "toeic", "exam_date": date(2026, 8, 1), "score": "850"}
    row.update(overrides)
    return fake_db.insert("exam_official_scores", row)


# --- compute_daily_period_stats ---


def test_compute_daily_period_stats_counts_total_and_correct(fake_db):
    _seed_answer(fake_db, answered_on=date(2026, 8, 1), is_correct=True)
    _seed_answer(fake_db, answered_on=date(2026, 8, 1), is_correct=False)
    _seed_answer(fake_db, answered_on=date(2026, 8, 2), is_correct=True)

    stats = certificate_stats.compute_daily_period_stats(fake_db, 1, "toeic", date(2026, 8, 1), date(2026, 8, 7))

    assert stats["total_answered"] == 3
    assert stats["total_correct"] == 2
    assert stats["active_days"] == 2


def test_compute_daily_period_stats_excludes_out_of_range(fake_db):
    _seed_answer(fake_db, answered_on=date(2026, 7, 31))
    _seed_answer(fake_db, answered_on=date(2026, 8, 8))

    stats = certificate_stats.compute_daily_period_stats(fake_db, 1, "toeic", date(2026, 8, 1), date(2026, 8, 7))

    assert stats["total_answered"] == 0


def test_compute_daily_period_stats_excludes_other_exam_type(fake_db):
    _seed_answer(fake_db, exam_type="toeic")
    _seed_answer(fake_db, exam_type="gcp")

    stats = certificate_stats.compute_daily_period_stats(fake_db, 1, "toeic", date(2026, 8, 1), date(2026, 8, 7))

    assert stats["total_answered"] == 1


def test_compute_daily_period_stats_average_excludes_inactive_days(fake_db):
    # 8/1 答對 4 題，其餘 8/2~8/7 都沒作答；平均應該是 4 / 1（有作答天數），不是 4 / 7。
    for _ in range(4):
        _seed_answer(fake_db, answered_on=date(2026, 8, 1), is_correct=True)

    stats = certificate_stats.compute_daily_period_stats(fake_db, 1, "toeic", date(2026, 8, 1), date(2026, 8, 7))

    assert stats["avg_correct_per_active_day"] == 4.0
    assert stats["active_days"] == 1
    assert len(stats["inactive_dates"]) == 6
    assert date(2026, 8, 2) in stats["inactive_dates"]


def test_compute_daily_period_stats_no_data_returns_zero_average(fake_db):
    stats = certificate_stats.compute_daily_period_stats(fake_db, 1, "toeic", date(2026, 8, 1), date(2026, 8, 7))

    assert stats["avg_correct_per_active_day"] == 0.0
    assert stats["most_wrong_type"] is None
    assert stats["most_correct_type"] is None
    assert len(stats["inactive_dates"]) == 7


def test_compute_daily_period_stats_finds_most_wrong_and_correct_type(fake_db):
    _seed_answer(fake_db, question_type="write", is_correct=False)
    _seed_answer(fake_db, question_type="write", is_correct=False)
    _seed_answer(fake_db, question_type="listen", is_correct=False)
    _seed_answer(fake_db, question_type="vocab", is_correct=True)
    _seed_answer(fake_db, question_type="vocab", is_correct=True)
    _seed_answer(fake_db, question_type="write", is_correct=True)

    stats = certificate_stats.compute_daily_period_stats(fake_db, 1, "toeic", date(2026, 8, 1), date(2026, 8, 7))

    assert stats["most_wrong_type"] == "write"
    assert stats["most_correct_type"] == "vocab"


# --- format_daily_period_summary ---


def test_format_daily_period_summary_no_data():
    text = certificate_stats.format_daily_period_summary("toeic", date(2026, 8, 1), date(2026, 8, 7), {
        "total_answered": 0, "total_correct": 0, "active_days": 0, "inactive_dates": [],
        "avg_correct_per_active_day": 0.0, "most_wrong_type": None, "most_correct_type": None,
    })
    assert "沒有任何作答紀錄" in text


def test_format_daily_period_summary_includes_key_figures():
    stats = {
        "total_answered": 10, "total_correct": 7, "active_days": 5, "inactive_dates": [date(2026, 8, 6)],
        "avg_correct_per_active_day": 1.4, "most_wrong_type": "write", "most_correct_type": "vocab",
    }
    text = certificate_stats.format_daily_period_summary("toeic", date(2026, 8, 1), date(2026, 8, 7), stats)

    assert "10 題" in text
    assert "答對 7 題" in text
    assert "1.4 題" in text
    assert "填空題" in text
    assert "單字題" in text
    assert "8/6" in text


def test_format_daily_period_summary_no_inactive_dates_line_when_full_attendance():
    stats = {
        "total_answered": 5, "total_correct": 5, "active_days": 5, "inactive_dates": [],
        "avg_correct_per_active_day": 1.0, "most_wrong_type": None, "most_correct_type": "write",
    }
    text = certificate_stats.format_daily_period_summary("toeic", date(2026, 8, 1), date(2026, 8, 5), stats)

    assert "沒有作答的日子" not in text


# --- format_daily_period_comparison ---


def test_format_daily_period_comparison_shows_improvement():
    stats_a = {
        "total_answered": 10, "total_correct": 8, "active_days": 5, "inactive_dates": [],
        "avg_correct_per_active_day": 1.6, "most_wrong_type": "write", "most_correct_type": "vocab",
    }
    stats_b = {
        "total_answered": 10, "total_correct": 5, "active_days": 5, "inactive_dates": [],
        "avg_correct_per_active_day": 1.0, "most_wrong_type": "listen", "most_correct_type": "write",
    }
    text = certificate_stats.format_daily_period_comparison(
        "toeic", (date(2026, 8, 1), date(2026, 8, 7)), stats_a, (date(2026, 7, 25), date(2026, 7, 31)), stats_b
    )
    assert "進步了" in text
    assert "對照" in text


def test_format_daily_period_comparison_shows_regression():
    stats_a = {
        "total_answered": 5, "total_correct": 2, "active_days": 5, "inactive_dates": [],
        "avg_correct_per_active_day": 0.4, "most_wrong_type": "write", "most_correct_type": None,
    }
    stats_b = {
        "total_answered": 5, "total_correct": 4, "active_days": 5, "inactive_dates": [],
        "avg_correct_per_active_day": 0.8, "most_wrong_type": None, "most_correct_type": "write",
    }
    text = certificate_stats.format_daily_period_comparison(
        "toeic", (date(2026, 8, 1), date(2026, 8, 7)), stats_a, (date(2026, 7, 25), date(2026, 7, 31)), stats_b
    )
    assert "少答對" in text


def test_format_daily_period_comparison_shows_similar_when_close():
    stats_a = {
        "total_answered": 5, "total_correct": 4, "active_days": 5, "inactive_dates": [],
        "avg_correct_per_active_day": 0.8, "most_wrong_type": None, "most_correct_type": "write",
    }
    stats_b = dict(stats_a)
    text = certificate_stats.format_daily_period_comparison(
        "toeic", (date(2026, 8, 1), date(2026, 8, 7)), stats_a, (date(2026, 7, 25), date(2026, 7, 31)), stats_b
    )
    assert "差不多" in text


# --- compute_formal_period_scores ---


def test_compute_formal_period_scores_filters_and_sorts(fake_db):
    _seed_score(fake_db, exam_date=date(2026, 8, 5), score="900")
    _seed_score(fake_db, exam_date=date(2026, 8, 1), score="850")
    _seed_score(fake_db, exam_date=date(2026, 6, 1), score="700")

    rows = certificate_stats.compute_formal_period_scores(fake_db, 1, "toeic", date(2026, 8, 1), date(2026, 8, 31))

    assert [row["score"] for row in rows] == ["850", "900"]


def test_compute_formal_period_scores_excludes_other_exam_type(fake_db):
    _seed_score(fake_db, exam_type="gcp", exam_date=date(2026, 8, 1))

    rows = certificate_stats.compute_formal_period_scores(fake_db, 1, "toeic", date(2026, 8, 1), date(2026, 8, 31))

    assert rows == []


# --- format_formal_period_summary ---


def test_format_formal_period_summary_no_data():
    text = certificate_stats.format_formal_period_summary("toeic", date(2026, 8, 1), date(2026, 8, 31), [])
    assert "沒有正式應考紀錄" in text


def test_format_formal_period_summary_lists_rows():
    rows = [{"exam_type": "toeic", "exam_date": date(2026, 8, 5), "score": "900"}]
    text = certificate_stats.format_formal_period_summary("toeic", date(2026, 8, 1), date(2026, 8, 31), rows)
    assert "2026/8/5" in text
    assert "900" in text


# --- known_exam_types ---


def test_known_exam_types_merges_answer_and_score_sources(fake_db):
    _seed_answer(fake_db, exam_type="toeic")
    _seed_score(fake_db, exam_type="gcp")

    assert certificate_stats.known_exam_types(fake_db, 1) == ["gcp", "toeic"]


def test_known_exam_types_deduplicates(fake_db):
    _seed_answer(fake_db, exam_type="toeic")
    _seed_score(fake_db, exam_type="toeic")

    assert certificate_stats.known_exam_types(fake_db, 1) == ["toeic"]


def test_known_exam_types_empty(fake_db):
    assert certificate_stats.known_exam_types(fake_db, 1) == []
