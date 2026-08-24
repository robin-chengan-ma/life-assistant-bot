"""批次3（FR-45a）🎯 目標追蹤每日摘要排程測試。"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.services import goal_summary_job

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")


class FakeDatabase:
    def __init__(self):
        self.tables = {
            "body_goals": [],
            "module_goals": [],
            "certificate_goals": [],
            "goal_summaries": [],
            "body_weight_logs": [],
            "exercise_logs": [],
            "diet_logs": [],
            "transactions": [],
            "collection_items": [],
            "answer_logs": [],
        }
        self.next_id = 1

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        rows = list(self.tables[table])
        if where == "status = %s":
            rows = [row for row in rows if row["status"] == params[0]]
        elif where == "goal_source = %s AND goal_id = %s AND generated_on = %s":
            rows = [
                row for row in rows
                if row["goal_source"] == params[0] and row["goal_id"] == params[1] and row["generated_on"] == params[2]
            ]
        elif where == "user_id = %s":
            rows = [row for row in rows if row["user_id"] == params[0]]
        return (rows[0] if rows else None) if fetch_one else rows

    def insert(self, table, data, returning="id"):
        row = dict(data)
        row.setdefault("id", self.next_id)
        self.next_id += 1
        self.tables[table].append(row)
        return row.get(returning)

    def update(self, table, data, where, params):
        rows = self.select(table, where=where, params=params)
        for row in rows:
            row.update(data)
        return len(rows)

    def execute_query(self, query, params=None):
        if "FROM transactions" in query:
            return []
        if "FROM collection_items" in query:
            return [{"total": 0}]
        return []


class _FakeLLMClient:
    def __init__(self, response_text="這是一段摘要文字！"):
        self.response_text = response_text
        self.calls = 0

    def generate_text(self, prompt):
        self.calls += 1
        return self.response_text


@pytest.fixture
def db():
    return FakeDatabase()


def test_generate_daily_goal_summaries_skips_outside_01_hour(db):
    db.insert("body_goals", {"user_id": 1, "goal_type": "weight", "status": "active", "target_description": "瘦身", "target_date": None})
    llm_client = _FakeLLMClient()
    now = datetime(2026, 8, 18, 9, 0, tzinfo=_TAIWAN_TZ)
    goal_summary_job.generate_daily_goal_summaries(db, llm_client, now=now)
    assert llm_client.calls == 0
    assert db.tables["goal_summaries"] == []


def test_generate_daily_goal_summaries_writes_summary_for_active_goals(db):
    db.insert(
        "body_goals",
        {"user_id": 1, "goal_type": "weight", "status": "active", "target_description": "瘦身", "target_date": None},
    )
    db.insert(
        "module_goals",
        {
            "user_id": 1, "module_key": "finance", "status": "active", "target_description": "存錢",
            "target_date": date(2026, 12, 31),
        },
    )
    llm_client = _FakeLLMClient()
    now = datetime(2026, 8, 18, 1, 0, tzinfo=_TAIWAN_TZ)
    goal_summary_job.generate_daily_goal_summaries(db, llm_client, now=now)

    assert llm_client.calls == 2
    assert len(db.tables["goal_summaries"]) == 2
    for row in db.tables["goal_summaries"]:
        assert row["summary_text"] == "這是一段摘要文字！"
        assert row["generated_on"] == date(2026, 8, 18)


def test_generate_daily_goal_summaries_upserts_same_day(db):
    db.insert(
        "body_goals",
        {"user_id": 1, "goal_type": "exercise", "status": "active", "target_description": "運動", "target_date": None},
    )
    llm_client = _FakeLLMClient()
    now = datetime(2026, 8, 18, 1, 0, tzinfo=_TAIWAN_TZ)
    goal_summary_job.generate_daily_goal_summaries(db, llm_client, now=now)
    goal_summary_job.generate_daily_goal_summaries(db, llm_client, now=now)

    assert len(db.tables["goal_summaries"]) == 1


def test_generate_daily_goal_summaries_llm_failure_skips_goal_without_crashing(db):
    db.insert(
        "body_goals",
        {"user_id": 1, "goal_type": "weight", "status": "active", "target_description": "瘦身", "target_date": None},
    )

    class _RaisingLLMClient:
        def generate_text(self, prompt):
            raise RuntimeError("boom")

    now = datetime(2026, 8, 18, 1, 0, tzinfo=_TAIWAN_TZ)
    goal_summary_job.generate_daily_goal_summaries(db, _RaisingLLMClient(), now=now)
    assert db.tables["goal_summaries"] == []


def test_gather_body_activity_text_weight_goal_combines_weight_exercise_and_diet(db):
    # 2026-08-24（Robin 反饋「體態目標摘要應該綜合評估，不能只看體重」）：weight 目標要同時看
    # 體重／運動／飲食三項資料，才能給出教練式的綜合建議。
    db.tables["body_weight_logs"].append({"user_id": 1, "entry_date": date(2026, 8, 15), "weight_kg": 70})
    db.tables["exercise_logs"].append({"user_id": 1, "entry_date": date(2026, 8, 15), "duration_minutes": 30})
    db.tables["diet_logs"].append({"user_id": 1, "entry_date": date(2026, 8, 15), "note": "早餐"})

    goal = {"user_id": 1, "goal_type": "weight"}
    text = goal_summary_job._gather_body_activity_text(db, goal, date(2026, 8, 1), date(2026, 8, 18))

    assert "體重" in text and "70" in text
    assert "運動" in text and "30 分鐘" in text
    assert "飲食" in text and "1 筆" in text


def test_gather_body_activity_text_exercise_goal_only_looks_at_exercise_logs(db):
    # exercise／飲食型目標本身就是在追蹤那件事有沒有做到，不需要參考體重或對方資料。
    db.tables["body_weight_logs"].append({"user_id": 1, "entry_date": date(2026, 8, 15), "weight_kg": 70})
    db.tables["exercise_logs"].append({"user_id": 1, "entry_date": date(2026, 8, 15), "duration_minutes": 30})
    db.tables["diet_logs"].append({"user_id": 1, "entry_date": date(2026, 8, 15), "note": "早餐"})

    goal = {"user_id": 1, "goal_type": "exercise"}
    text = goal_summary_job._gather_body_activity_text(db, goal, date(2026, 8, 1), date(2026, 8, 18))

    assert "體重" not in text
    assert "飲食" not in text
    assert "運動了 1 次" in text and "30 分鐘" in text


def test_gather_body_activity_text_diet_goal_only_looks_at_diet_logs(db):
    db.tables["body_weight_logs"].append({"user_id": 1, "entry_date": date(2026, 8, 15), "weight_kg": 70})
    db.tables["exercise_logs"].append({"user_id": 1, "entry_date": date(2026, 8, 15), "duration_minutes": 30})
    db.tables["diet_logs"].append({"user_id": 1, "entry_date": date(2026, 8, 15), "note": "早餐"})

    goal = {"user_id": 1, "goal_type": "diet"}
    text = goal_summary_job._gather_body_activity_text(db, goal, date(2026, 8, 1), date(2026, 8, 18))

    assert "體重" not in text
    assert "運動" not in text
    assert "1 筆飲食" in text


def test_deadline_text_no_target_date_returns_empty():
    assert goal_summary_job._deadline_text(None, date(2026, 8, 18)) == ""


def test_deadline_text_future_date_shows_days_left():
    text = goal_summary_job._deadline_text(date(2026, 8, 25), date(2026, 8, 18))
    assert "還有 7 天" in text


def test_deadline_text_past_date_shows_overdue():
    text = goal_summary_job._deadline_text(date(2026, 8, 10), date(2026, 8, 18))
    assert "已經超過期限" in text
