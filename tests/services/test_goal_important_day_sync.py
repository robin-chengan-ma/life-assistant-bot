from datetime import date

from src.services.goal_important_day_sync import sync_body_goal, sync_certificate_goal


class FakeDatabase:
    def __init__(self):
        self.tables = {
            "body_goals": [],
            "certificate_goals": [],
            "important_days": [],
            "important_day_recipients": [],
            "important_day_occurrences": [],
        }
        self.next_id = 1

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        rows = list(self.tables[table])
        if where == "id = %s":
            rows = [row for row in rows if row["id"] == params[0]]
        elif where == "id = %s AND owner_user_id = %s":
            rows = [row for row in rows if row["id"] == params[0] and row["owner_user_id"] == params[1]]
        elif where == "important_day_id = %s":
            rows = [row for row in rows if row["important_day_id"] == params[0]]
        if columns != ("*",):
            rows = [{column: row[column] for column in columns} for row in rows]
        return (rows[0] if rows else None) if fetch_one else rows

    def insert(self, table, data, returning="id"):
        row = dict(data)
        if table == "important_days":
            row["id"] = self.next_id
            self.next_id += 1
        self.tables[table].append(row)
        return row.get(returning)

    def update(self, table, data, where, params):
        rows = self.select(table, where=where, params=params)
        for row in rows:
            row.update(data)
        return len(rows)

    def delete(self, table, where, params):
        key = "important_day_id"
        before = len(self.tables[table])
        self.tables[table] = [row for row in self.tables[table] if row.get(key) != params[0]]
        return before - len(self.tables[table])


def test_body_goal_creates_important_day_with_default_settings():
    db = FakeDatabase()
    db.tables["body_goals"].append({
        "id": 10,
        "user_id": 1,
        "target_description": "瘦到 70 公斤",
        "target_date": date(2026, 12, 31),
        "status": "active",
        "important_day_id": None,
    })

    event_id = sync_body_goal(db, 10)

    assert event_id == 1
    assert db.tables["body_goals"][0]["important_day_id"] == 1
    assert db.tables["important_days"][0]["title"] == "體態目標：瘦到 70 公斤"
    assert db.tables["important_days"][0]["reminder_days_before"] == 1
    assert db.tables["important_days"][0]["show_on_todo_calendar"] is True


def test_cancelled_body_goal_disables_linked_important_day():
    db = FakeDatabase()
    db.tables["body_goals"].append({
        "id": 10,
        "user_id": 1,
        "target_description": "瘦到 70 公斤",
        "target_date": date(2026, 12, 31),
        "status": "cancelled",
        "important_day_id": 4,
    })
    db.tables["important_days"].append({"id": 4, "owner_user_id": 1, "is_active": True})

    sync_body_goal(db, 10)

    assert db.tables["important_days"][0]["is_active"] is False


def test_certificate_goal_update_preserves_reminder_settings():
    db = FakeDatabase()
    db.tables["certificate_goals"].append({
        "id": 20,
        "user_id": 1,
        "exam_type": "TOEIC",
        "target_score": "850",
        "target_date": date(2026, 12, 1),
        "important_day_id": 5,
    })
    db.tables["important_days"].append({
        "id": 5,
        "owner_user_id": 1,
        "reminder_days_before": 7,
        "audience_mode": "self",
        "show_on_todo_calendar": False,
    })

    sync_certificate_goal(db, 20)

    event = db.tables["important_days"][0]
    assert event["title"] == "TOEIC 考試目標（目標：850）"
    assert event["reminder_days_before"] == 7
    assert event["show_on_todo_calendar"] is False
