import pytest

from src.services.app_todo import (
    AppTodoService,
    TodoNotFoundError,
    TodoValidationError,
)


class FakeDatabase:
    def __init__(self):
        self.tables = {"todos": []}
        self.next_id = 1

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        rows = list(self.tables[table])
        if where:
            if "user_id = %s" in where and len(params) == 1:
                rows = [row for row in rows if row["user_id"] == params[0]]
            else:
                rows = [row for row in rows if row["id"] == params[0] and row["user_id"] == params[1]]
        return (rows[0] if rows else None) if fetch_one else rows

    def insert(self, table, data, returning="id"):
        row = dict(data)
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
        before = len(self.tables[table])
        self.tables[table] = [row for row in self.tables[table] if row["id"] != params[0]]
        return before - len(self.tables[table])


@pytest.fixture()
def service():
    return AppTodoService(FakeDatabase())


def test_create_requires_content(service):
    with pytest.raises(TodoValidationError):
        service.create(1, {"remind_start_date": "2026-12-25"})


def test_create_requires_valid_date(service):
    with pytest.raises(TodoValidationError):
        service.create(1, {"content": "買禮物", "remind_start_date": "not-a-date"})


def test_create_rejects_end_before_start(service):
    with pytest.raises(TodoValidationError):
        service.create(1, {"content": "買禮物", "remind_start_date": "2026-12-25", "remind_end_date": "2026-12-20"})


def test_create_and_list_round_trip(service):
    result = service.create(1, {"content": "買禮物", "remind_start_date": "2026-12-25"})
    assert result["id"] == 1

    items = service.list_for_user(1)
    assert len(items) == 1
    assert items[0]["content"] == "買禮物"
    assert items[0]["remind_start_date"] == "2026-12-25"
    assert items[0]["remind_end_date"] == "2026-12-25"
    assert items[0]["owner_user_id"] == 1
    assert items[0]["can_edit"] is True
    assert items[0]["remind_offsets"] == [0]


def test_create_with_remind_offsets(service):
    service.create(
        1,
        {
            "content": "繳帳單",
            "remind_start_date": "2026-12-25",
            "remind_offsets": [0, 3, 14],
        },
    )
    items = service.list_for_user(1)
    assert items[0]["remind_offsets"] == [14, 3, 0]


def test_create_rejects_invalid_remind_offset(service):
    with pytest.raises(TodoValidationError):
        service.create(
            1,
            {"content": "買禮物", "remind_start_date": "2026-12-25", "remind_offsets": [5]},
        )


def test_create_rejects_empty_remind_offsets(service):
    with pytest.raises(TodoValidationError):
        service.create(
            1,
            {"content": "買禮物", "remind_start_date": "2026-12-25", "remind_offsets": []},
        )


def test_create_with_date_range(service):
    result = service.create(
        1, {"content": "出差", "remind_start_date": "2026-12-20", "remind_end_date": "2026-12-25"}
    )
    items = service.list_for_user(1)
    assert items[0]["remind_start_date"] == "2026-12-20"
    assert items[0]["remind_end_date"] == "2026-12-25"
    assert result["id"] == 1


def test_list_only_returns_own_todos(service):
    service.create(1, {"content": "買禮物", "remind_start_date": "2026-12-25"})
    service.create(2, {"content": "別人的事", "remind_start_date": "2026-12-01"})

    items = service.list_for_user(1)
    assert [item["content"] for item in items] == ["買禮物"]


def test_update_changes_fields(service):
    created = service.create(1, {"content": "買禮物", "remind_start_date": "2026-12-25"})
    service.update(created["id"], 1, {"content": "買蛋糕", "remind_start_date": "2026-12-24"})

    items = service.list_for_user(1)
    assert items[0]["content"] == "買蛋糕"
    assert items[0]["remind_start_date"] == "2026-12-24"
    assert items[0]["remind_end_date"] == "2026-12-24"


def test_other_user_cannot_update_or_delete(service):
    created = service.create(1, {"content": "買禮物", "remind_start_date": "2026-12-25"})

    with pytest.raises(TodoNotFoundError):
        service.update(created["id"], 2, {"content": "x", "remind_start_date": "2026-12-25"})
    with pytest.raises(TodoNotFoundError):
        service.delete(created["id"], 2)


def test_delete_removes_row(service):
    created = service.create(1, {"content": "買禮物", "remind_start_date": "2026-12-25"})
    service.delete(created["id"], 1)
    assert service.list_for_user(1) == []


def test_create_monthly_recurring_todo(service):
    result = service.create(
        1,
        {"content": "繳信用卡費", "recurrence_type": "monthly", "recurrence_day": 5, "remind_offsets": [0]},
    )
    items = service.list_for_user(1)
    assert result["id"] == 1
    assert items[0]["recurrence_type"] == "monthly"
    assert items[0]["recurrence_day"] == 5
    assert items[0]["remind_start_date"] is None
    assert items[0]["remind_end_date"] is None


def test_create_monthly_recurring_todo_rejects_invalid_day(service):
    with pytest.raises(TodoValidationError):
        service.create(1, {"content": "繳費", "recurrence_type": "monthly", "recurrence_day": 32})


def test_create_monthly_recurring_todo_requires_day(service):
    with pytest.raises(TodoValidationError):
        service.create(1, {"content": "繳費", "recurrence_type": "monthly"})


def test_create_rejects_invalid_recurrence_type(service):
    with pytest.raises(TodoValidationError):
        service.create(1, {"content": "繳費", "recurrence_type": "weekly"})


def test_list_sorts_once_before_monthly(service):
    service.create(1, {"content": "常態性", "recurrence_type": "monthly", "recurrence_day": 5})
    service.create(1, {"content": "一次性", "remind_start_date": "2026-12-25"})
    items = service.list_for_user(1)
    assert [item["content"] for item in items] == ["一次性", "常態性"]
