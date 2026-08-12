from datetime import date

import pytest

from src.services.app_important_days import (
    AppImportantDayService,
    ImportantDayNotFoundError,
    ImportantDayValidationError,
)


class FakeDatabase:
    def __init__(self):
        self.tables = {
            "important_days": [],
            "important_day_recipients": [],
            "important_day_occurrences": [],
            "users": [
                {"id": 1, "role": "Robin", "app_user_id": "user01"},
                {"id": 2, "role": "爸爸", "app_user_id": "user02"},
            ],
        }
        self.next_id = 1

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        rows = list(self.tables[table])
        if table == "important_days" and where:
            rows = [row for row in rows if row["id"] == params[0] and row["owner_user_id"] == params[1]]
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
        key = "id" if table == "important_days" else "important_day_id"
        before = len(self.tables[table])
        self.tables[table] = [row for row in self.tables[table] if row[key] != params[0]]
        return before - len(self.tables[table])

    def execute_query(self, query, params=None):
        return []


def payload(**overrides):
    value = {
        "title": "同學婚禮",
        "recurrence_type": "one_time",
        "event_date": "2026-12-20",
        "event_time": "18:00",
        "is_all_day": False,
        "reminder_days_before": 7,
        "notes": "台北",
        "audience_mode": "self",
        "recipient_ids": [],
        "show_on_todo_calendar": True,
        "is_active": True,
    }
    value.update(overrides)
    return value


def test_create_self_event_only_assigns_owner_as_recipient():
    db = FakeDatabase()

    result = AppImportantDayService(db).create(1, payload())

    assert result["id"] == 1
    assert db.tables["important_days"][0]["audience_mode"] == "self"
    assert db.tables["important_day_recipients"] == [{"important_day_id": 1, "user_id": 1}]


def test_specific_audience_requires_at_least_one_recipient():
    with pytest.raises(ImportantDayValidationError, match="至少選擇一位"):
        AppImportantDayService(FakeDatabase()).create(1, payload(audience_mode="specific"))


def test_flexible_annual_event_stores_current_year_occurrence():
    db = FakeDatabase()

    AppImportantDayService(db).create(1, payload(
        recurrence_type="flexible_annual",
        event_date=None,
        occurrence_date="2026-04-03",
    ))

    assert db.tables["important_day_occurrences"][0]["occurrence_year"] == 2026
    assert db.tables["important_day_occurrences"][0]["occurrence_date"] == date(2026, 4, 3)


def test_one_time_range_expands_every_calendar_day():
    db = FakeDatabase()
    service = AppImportantDayService(db)
    service.create(1, payload(event_date="2026-12-20", event_end_date="2026-12-22"))
    row = db.tables["important_days"][0]
    row.update(recipient_ids=[1], current_year_date=None, current_year_end_date=None)
    service.list_for_user = lambda user_id, today=None: [service._serialize(row, user_id, today or date(2026, 12, 1))]

    events = service.calendar_events(1, date(2026, 12, 19), date(2026, 12, 23))

    assert set(events) == {"2026-12-20", "2026-12-21", "2026-12-22"}


def test_fixed_annual_range_cannot_cross_year():
    with pytest.raises(ImportantDayValidationError, match="不可跨年"):
        AppImportantDayService(FakeDatabase()).create(
            1,
            payload(
                recurrence_type="fixed_annual",
                event_date="2026-12-30",
                event_end_date="2027-01-02",
            ),
        )


def test_other_user_cannot_update_or_delete_event():
    db = FakeDatabase()
    service = AppImportantDayService(db)
    event_id = service.create(1, payload())["id"]

    with pytest.raises(ImportantDayNotFoundError):
        service.update(event_id, 2, payload(title="不是我的事件"))
    with pytest.raises(ImportantDayNotFoundError):
        service.delete(event_id, 2)
