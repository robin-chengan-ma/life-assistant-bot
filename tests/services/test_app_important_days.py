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
            "users": [
                {"id": 1, "role": "Robin"},
                {"id": 10, "role": "爸爸"},
            ],
        }
        self.next_id = 1

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        rows = list(self.tables[table])
        if table == "important_days" and where:
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
    return AppImportantDayService(FakeDatabase())


def test_create_requires_name(service):
    with pytest.raises(ImportantDayValidationError):
        service.create(1, {"birth_month": 5, "birth_day": 1})


def test_create_requires_valid_month_and_day(service):
    with pytest.raises(ImportantDayValidationError):
        service.create(1, {"name": "媽媽", "birth_month": 13, "birth_day": 1})
    with pytest.raises(ImportantDayValidationError):
        service.create(1, {"name": "媽媽", "birth_month": 5, "birth_day": 32})


def test_create_and_list_round_trip(service):
    result = service.create(1, {"name": "媽媽", "birth_month": 5, "birth_day": 20})
    assert result["id"] == 1

    items = service.list_for_user(1)
    assert len(items) == 1
    assert items[0]["name"] == "媽媽"
    assert items[0]["birth_month"] == 5
    assert items[0]["birth_day"] == 20
    assert items[0]["owner_user_id"] == 1
    assert items[0]["can_edit"] is True


def test_list_includes_all_family_birthdays_not_only_own(service):
    # 2026-11-28：生日設定是全家共用清單，不分建立者；非建立者看到的項目 can_edit 應為 False。
    service.create(1, {"name": "媽媽", "birth_month": 5, "birth_day": 20})
    service.create(10, {"name": "爸爸的朋友", "birth_month": 1, "birth_day": 1})

    items = service.list_for_user(1)
    by_name = {item["name"]: item for item in items}
    assert set(by_name) == {"媽媽", "爸爸的朋友"}
    assert by_name["媽媽"]["can_edit"] is True
    assert by_name["爸爸的朋友"]["can_edit"] is False


def test_update_changes_fields(service):
    created = service.create(1, {"name": "媽媽", "birth_month": 5, "birth_day": 20})
    service.update(created["id"], 1, {"name": "媽咪", "birth_month": 6, "birth_day": 1})

    items = service.list_for_user(1)
    assert items[0]["name"] == "媽咪"
    assert items[0]["birth_month"] == 6
    assert items[0]["birth_day"] == 1


def test_other_user_cannot_update_or_delete(service):
    created = service.create(1, {"name": "媽媽", "birth_month": 5, "birth_day": 20})

    with pytest.raises(ImportantDayNotFoundError):
        service.update(created["id"], 10, {"name": "x", "birth_month": 1, "birth_day": 1})
    with pytest.raises(ImportantDayNotFoundError):
        service.delete(created["id"], 10)


def test_delete_removes_row(service):
    created = service.create(1, {"name": "媽媽", "birth_month": 5, "birth_day": 20})
    service.delete(created["id"], 1)
    assert service.list_for_user(1) == []


def test_create_defaults_remind_offsets_to_day_of(service):
    result = service.create(1, {"name": "媽媽", "birth_month": 5, "birth_day": 20})
    items = service.list_for_user(1)
    assert items[0]["remind_offsets"] == [0]
    assert result["id"] == 1


def test_create_accepts_multiple_remind_offsets_sorted_descending(service):
    service.create(1, {"name": "媽媽", "birth_month": 5, "birth_day": 20, "remind_offsets": [0, 14, 3]})
    items = service.list_for_user(1)
    assert items[0]["remind_offsets"] == [14, 3, 0]


def test_create_rejects_empty_remind_offsets(service):
    with pytest.raises(ImportantDayValidationError):
        service.create(1, {"name": "媽媽", "birth_month": 5, "birth_day": 20, "remind_offsets": []})


def test_create_rejects_disallowed_remind_offset_value(service):
    with pytest.raises(ImportantDayValidationError):
        service.create(1, {"name": "媽媽", "birth_month": 5, "birth_day": 20, "remind_offsets": [1]})


def test_create_defaults_audience_mode_to_self(service):
    service.create(1, {"name": "媽媽", "birth_month": 5, "birth_day": 20})
    items = service.list_for_user(1)
    assert items[0]["audience_mode"] == "self"
    assert items[0]["audience_user_ids"] == []


def test_create_accepts_everyone_audience_mode(service):
    service.create(1, {"name": "媽媽", "birth_month": 5, "birth_day": 20, "audience_mode": "everyone"})
    items = service.list_for_user(1)
    assert items[0]["audience_mode"] == "everyone"
    assert items[0]["audience_user_ids"] == []


def test_create_accepts_selected_audience_mode_with_existing_user_ids(service):
    service.create(
        1,
        {"name": "媽媽", "birth_month": 5, "birth_day": 20, "audience_mode": "selected", "audience_user_ids": [10, 1]},
    )
    items = service.list_for_user(1)
    assert items[0]["audience_mode"] == "selected"
    assert items[0]["audience_user_ids"] == [1, 10]


def test_create_rejects_invalid_audience_mode(service):
    with pytest.raises(ImportantDayValidationError):
        service.create(1, {"name": "媽媽", "birth_month": 5, "birth_day": 20, "audience_mode": "nope"})


def test_create_rejects_selected_audience_mode_without_user_ids(service):
    with pytest.raises(ImportantDayValidationError):
        service.create(1, {"name": "媽媽", "birth_month": 5, "birth_day": 20, "audience_mode": "selected"})


def test_create_rejects_selected_audience_mode_with_nonexistent_user_id(service):
    with pytest.raises(ImportantDayValidationError):
        service.create(
            1,
            {"name": "媽媽", "birth_month": 5, "birth_day": 20, "audience_mode": "selected", "audience_user_ids": [999]},
        )


def test_family_users_prefers_full_name_over_nickname_and_family_title():
    db = FakeDatabase()
    db.tables["users"] = [
        {"id": 1, "role": "Robin", "full_name": "馬承安", "nickname": "Robin", "family_title": None},
        {"id": 10, "role": "爸爸", "full_name": None, "nickname": "小馬", "family_title": "爸爸"},
        {"id": 20, "role": "媽媽", "full_name": None, "nickname": None, "family_title": "媽媽"},
        {"id": 30, "role": "弟弟", "full_name": None, "nickname": None, "family_title": None},
    ]
    service = AppImportantDayService(db)

    users = service.family_users()

    by_id = {user["id"]: user["display_name"] for user in users}
    assert by_id[1] == "馬承安"
    assert by_id[10] == "小馬"
    assert by_id[20] == "媽媽"
    assert by_id[30] == "弟弟"
