"""批次3（FR-45a）記帳／收藏清單通用目標模組（`module_goals`）測試。"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.bot import goals

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")


class FakeDatabase:
    def __init__(self):
        self.tables = {
            "module_goals": [],
            "transactions": [],
            "collection_items": [],
            "users": [],
        }
        self.next_id = 1

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        rows = list(self.tables[table])
        if where == "id = %s":
            rows = [row for row in rows if row["id"] == params[0]]
        elif where == "user_id = %s AND module_key = %s AND status = %s":
            rows = [
                row for row in rows
                if row["user_id"] == params[0] and row["module_key"] == params[1] and row["status"] == params[2]
            ]
        elif where == "status = %s AND target_date IS NOT NULL":
            rows = [row for row in rows if row["status"] == params[0] and row.get("target_date") is not None]
        return (rows[0] if rows else None) if fetch_one else rows

    def insert(self, table, data, returning="id"):
        row = dict(data)
        row.setdefault("id", self.next_id)
        self.next_id += 1
        if table == "module_goals":
            row.setdefault("created_at", datetime.now(_TAIWAN_TZ))
        self.tables[table].append(row)
        return row.get(returning)

    def update(self, table, data, where, params):
        rows = self.select(table, where=where, params=params)
        for row in rows:
            row.update(data)
        return len(rows)

    def execute_query(self, query, params=None):
        if "FROM transactions" in query:
            user_id, start_date = params[0], params[1]
            totals: dict[str, float] = {}
            for row in self.tables["transactions"]:
                if row["user_id"] != user_id or row["transaction_date"] < start_date:
                    continue
                if len(params) > 2 and row["transaction_date"] > params[2]:
                    continue
                totals[row["type"]] = totals.get(row["type"], 0.0) + row["amount"]
            return [{"type": key, "total": value} for key, value in totals.items()]
        if "FROM collection_items" in query and "COUNT(*)" in query:
            user_id = params[0]
            count = sum(
                1 for row in self.tables["collection_items"]
                if row["user_id"] == user_id and row["status"] == "visited"
            )
            return [{"total": count}]
        raise NotImplementedError(f"FakeDatabase 尚未支援這段 execute_query：{query[:80]}")


@pytest.fixture
def db():
    return FakeDatabase()


def test_create_and_get_goal(db):
    goal_id = db.insert("users", {"telegram_user_id": 1}, returning="id")
    created_id = goals.create_goal(db, goal_id, "finance", "這個月想存5000", 5000.0, "TWD", 0, None)
    row = goals.get_goal(db, created_id)
    assert row["target_description"] == "這個月想存5000"
    assert row["target_value"] == 5000.0
    assert row["status"] == "active"
    assert row["sync_to_calendar"] is False


def test_create_goal_with_calendar_sync(db):
    """2026-08-17 補做（Robin 要求不得漏做）：`sync_to_calendar=True` 要如實寫入。"""
    goal_id = goals.create_goal(
        db, 1, "finance", "存錢", 5000.0, "TWD", 0, date(2026, 12, 31), sync_to_calendar=True
    )
    row = goals.get_goal(db, goal_id)
    assert row["sync_to_calendar"] is True


def test_set_calendar_event_id(db):
    goal_id = goals.create_goal(db, 1, "finance", "存錢", 5000.0, "TWD", 0, date(2026, 12, 31), sync_to_calendar=True)
    goals.set_calendar_event_id(db, goal_id, "event-123")
    row = goals.get_goal(db, goal_id)
    assert row["google_calendar_event_id"] == "event-123"


def test_update_goal_resets_reminder_flags(db):
    goal_id = goals.create_goal(db, 1, "finance", "存錢", 1000.0, "TWD", 0, None)
    db.update("module_goals", {"deadline_reminder_sent": True}, where="id = %s", params=(goal_id,))
    goals.update_goal(db, goal_id, "存更多錢", 2000.0, "TWD", date(2026, 12, 31))
    row = goals.get_goal(db, goal_id)
    assert row["target_description"] == "存更多錢"
    assert row["target_value"] == 2000.0
    assert row["deadline_reminder_sent"] is False


def test_list_active_goals_filters_by_module_and_status(db):
    goals.create_goal(db, 1, "finance", "存錢", None, None, None, None)
    goals.create_goal(db, 1, "collections", "收藏目標", None, None, 0, None)
    cancelled_id = goals.create_goal(db, 1, "finance", "取消的目標", None, None, None, None)
    goals.cancel_goal(db, cancelled_id)

    finance_goals = goals.list_active_goals(db, 1, "finance")
    assert len(finance_goals) == 1
    assert finance_goals[0]["target_description"] == "存錢"


def test_format_goal_list_empty():
    assert goals.format_goal_list([]) == "目前沒有進行中的目標。"


def test_format_goal_list_includes_deadline():
    rows = [{"target_description": "存錢", "target_date": date(2026, 12, 31)}]
    text = goals.format_goal_list(rows)
    assert "存錢" in text
    assert "2026/12/31" in text


def test_cancel_goal_marks_cancelled(db):
    goal_id = goals.create_goal(db, 1, "finance", "存錢", None, None, None, None)
    goals.cancel_goal(db, goal_id)
    assert goals.get_goal(db, goal_id)["status"] == "cancelled"


def test_check_finance_goal_achievement_marks_achieved_when_net_meets_target(db):
    db.insert("users", {"telegram_user_id": 1}, returning="id")
    goal_id = goals.create_goal(db, 1, "finance", "這個月想存5000", 5000.0, "TWD", 0, None)
    goal_row = goals.get_goal(db, goal_id)
    since_date = goal_row["created_at"].astimezone(_TAIWAN_TZ).date()
    db.insert("transactions", {"user_id": 1, "type": "income", "transaction_date": since_date, "amount": 8000})
    db.insert("transactions", {"user_id": 1, "type": "expense", "transaction_date": since_date, "amount": 2000})

    message = goals.check_finance_goal_achievement(db, 1)
    assert message is not None
    assert "這個月想存5000" in message
    assert goals.get_goal(db, goal_id)["status"] == "achieved"


def test_check_finance_goal_achievement_no_achievement_below_target(db):
    goal_id = goals.create_goal(db, 1, "finance", "存5000", 5000.0, "TWD", 0, None)
    goal_row = goals.get_goal(db, goal_id)
    since_date = goal_row["created_at"].astimezone(_TAIWAN_TZ).date()
    db.insert("transactions", {"user_id": 1, "type": "income", "transaction_date": since_date, "amount": 1000})

    assert goals.check_finance_goal_achievement(db, 1) is None
    assert goals.get_goal(db, goal_id)["status"] == "active"


def test_check_finance_goal_achievement_skips_free_text_goals(db):
    goals.create_goal(db, 1, "finance", "想變得更有錢", None, None, None, None)
    assert goals.check_finance_goal_achievement(db, 1) is None


def test_check_collections_goal_achievement_marks_achieved(db):
    goal_id = goals.create_goal(db, 1, "collections", "完成3個收藏", 3.0, "count", 0, None)
    for _ in range(3):
        db.insert("collection_items", {"user_id": 1, "status": "visited"})

    message = goals.check_collections_goal_achievement(db, 1)
    assert message is not None
    assert goals.get_goal(db, goal_id)["status"] == "achieved"

def test_check_collections_goal_achievement_respects_baseline(db):
    db.insert("collection_items", {"user_id": 1, "status": "visited"})
    baseline = goals.compute_collections_baseline(db, 1)
    assert baseline == 1
    goal_id = goals.create_goal(db, 1, "collections", "再完成2個收藏", 2.0, "count", baseline, None)

    db.insert("collection_items", {"user_id": 1, "status": "visited"})
    assert goals.check_collections_goal_achievement(db, 1) is None

    db.insert("collection_items", {"user_id": 1, "status": "visited"})
    message = goals.check_collections_goal_achievement(db, 1)
    assert message is not None
    assert goals.get_goal(db, goal_id)["status"] == "achieved"
