"""src/bot/certificate_goals.py 的單元測試（對應 robinson SPEC.md FR-24、ADR-19）。"""
from datetime import date

from src.bot import certificate_goals

# --- get_goal / set_goal ---


def test_get_goal_returns_none_when_not_set(fake_db):
    assert certificate_goals.get_goal(fake_db, 1, "toeic") is None


def test_set_goal_inserts_new_row(fake_db):
    result = certificate_goals.set_goal(fake_db, 1, "toeic", date(2026, 12, 1), "850")

    assert result["previous"] is None
    row = certificate_goals.get_goal(fake_db, 1, "toeic")
    assert row["target_date"] == date(2026, 12, 1)
    assert row["target_score"] == "850"


def test_set_goal_overwrites_existing_row_not_duplicate(fake_db):
    certificate_goals.set_goal(fake_db, 1, "toeic", date(2026, 12, 1), "850")
    result = certificate_goals.set_goal(fake_db, 1, "toeic", date(2027, 1, 1), "900")

    assert result["previous"]["target_score"] == "850"
    rows = fake_db.select("certificate_goals", where="user_id = %s AND exam_type = %s", params=(1, "toeic"))
    assert len(rows) == 1
    assert rows[0]["target_date"] == date(2027, 1, 1)
    assert rows[0]["target_score"] == "900"


def test_set_goal_allows_none_date_and_score(fake_db):
    result = certificate_goals.set_goal(fake_db, 1, "toeic", None, None)
    assert result["target_date"] is None
    assert result["target_score"] is None


def test_set_goal_different_exam_types_independent(fake_db):
    certificate_goals.set_goal(fake_db, 1, "toeic", date(2026, 12, 1), "850")
    certificate_goals.set_goal(fake_db, 1, "gcp", None, "通過")

    assert len(fake_db.select("certificate_goals")) == 2


# --- list_goals ---


def test_list_goals_sorted_by_exam_type(fake_db):
    certificate_goals.set_goal(fake_db, 1, "toeic", date(2026, 12, 1), "850")
    certificate_goals.set_goal(fake_db, 1, "gcp", None, "通過")

    rows = certificate_goals.list_goals(fake_db, 1)
    assert [row["exam_type"] for row in rows] == ["gcp", "toeic"]


def test_list_goals_empty(fake_db):
    assert certificate_goals.list_goals(fake_db, 1) == []


def test_list_goals_only_this_user(fake_db):
    certificate_goals.set_goal(fake_db, 1, "toeic", None, "850")
    certificate_goals.set_goal(fake_db, 2, "toeic", None, "700")

    assert len(certificate_goals.list_goals(fake_db, 1)) == 1


# --- format_goal_set_reply ---


def test_format_goal_set_reply_new_goal():
    result = {"previous": None, "target_date": date(2026, 12, 1), "target_score": "850"}
    text = certificate_goals.format_goal_set_reply("toeic", result)
    assert "記下" in text
    assert "2026/12/1" in text
    assert "850" in text


def test_format_goal_set_reply_overwrite():
    result = {"previous": {"target_score": "700"}, "target_date": None, "target_score": "850"}
    text = certificate_goals.format_goal_set_reply("toeic", result)
    assert "更新" in text


def test_format_goal_set_reply_no_date_or_score():
    result = {"previous": None, "target_date": None, "target_score": None}
    text = certificate_goals.format_goal_set_reply("toeic", result)
    assert "沒有設定時間或分數" in text


# --- format_goals_summary ---


def test_format_goals_summary_empty():
    text = certificate_goals.format_goals_summary([])
    assert "還沒有設定" in text


def test_format_goals_summary_lists_all():
    rows = [
        {"exam_type": "gcp", "target_date": None, "target_score": "通過"},
        {"exam_type": "toeic", "target_date": date(2026, 12, 1), "target_score": "850"},
    ]
    text = certificate_goals.format_goals_summary(rows)
    assert "gcp" in text
    assert "toeic" in text
    assert "2026/12/1" in text
    assert "850" in text
    assert "通過" in text


# --- build_advice_prompt ---


def test_build_advice_prompt_includes_exam_type():
    prompt = certificate_goals.build_advice_prompt("toeic", None, None, date(2026, 8, 8))
    assert "toeic" in prompt
    assert "尚未設定目標" in prompt
    assert "沒有任何作答紀錄" in prompt


def test_build_advice_prompt_includes_goal_days_left():
    goal = {"target_date": date(2026, 12, 1), "target_score": "850"}
    prompt = certificate_goals.build_advice_prompt("toeic", goal, None, date(2026, 8, 8))
    assert "850" in prompt
    assert "還有" in prompt
    assert "天" in prompt


def test_build_advice_prompt_includes_past_goal_date():
    goal = {"target_date": date(2026, 1, 1), "target_score": "850"}
    prompt = certificate_goals.build_advice_prompt("toeic", goal, None, date(2026, 8, 8))
    assert "已經過了" in prompt


def test_build_advice_prompt_includes_stats():
    stats = {
        "total_answered": 20, "total_correct": 15, "active_days": 5,
        "avg_correct_per_active_day": 3.0, "most_wrong_type": "write",
    }
    prompt = certificate_goals.build_advice_prompt("toeic", None, stats, date(2026, 8, 8))
    assert "20 題" in prompt
    assert "15 題" in prompt
    assert "write" in prompt


# --- check_score_achievement（2026-08-17 補做，Robin 要求「輸入實際分數就要能自動判斷」）---


def test_check_score_achievement_no_goal_returns_none(fake_db):
    assert certificate_goals.check_score_achievement(fake_db, 1, "toeic", "900") is None


def test_check_score_achievement_goal_without_target_score_returns_none(fake_db):
    certificate_goals.set_goal(fake_db, 1, "toeic", date(2026, 12, 1), None)
    assert certificate_goals.check_score_achievement(fake_db, 1, "toeic", "900") is None


def test_check_score_achievement_reaches_target(fake_db):
    certificate_goals.set_goal(fake_db, 1, "toeic", date(2026, 12, 1), "850")
    result = certificate_goals.check_score_achievement(fake_db, 1, "toeic", "900")
    assert result is not None
    assert "toeic" in result
    assert "850" in result


def test_check_score_achievement_exactly_meets_target(fake_db):
    certificate_goals.set_goal(fake_db, 1, "toeic", date(2026, 12, 1), "850")
    assert certificate_goals.check_score_achievement(fake_db, 1, "toeic", "850") is not None


def test_check_score_achievement_below_target_returns_none(fake_db):
    certificate_goals.set_goal(fake_db, 1, "toeic", date(2026, 12, 1), "850")
    assert certificate_goals.check_score_achievement(fake_db, 1, "toeic", "700") is None


def test_check_score_achievement_non_numeric_target_returns_none(fake_db):
    """有些證照沒有量化分數（例如「通過／未通過」），抽不出數字就不誤判。"""
    certificate_goals.set_goal(fake_db, 1, "gcp", date(2026, 12, 1), "通過")
    assert certificate_goals.check_score_achievement(fake_db, 1, "gcp", "通過") is None


def test_check_score_achievement_non_numeric_score_returns_none(fake_db):
    certificate_goals.set_goal(fake_db, 1, "toeic", date(2026, 12, 1), "850")
    assert certificate_goals.check_score_achievement(fake_db, 1, "toeic", "未知") is None
