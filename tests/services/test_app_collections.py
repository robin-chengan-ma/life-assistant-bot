from decimal import Decimal

import pytest

from src.services.app_collections import (
    AppCollectionService,
    CollectionNotFoundError,
    CollectionValidationError,
)


class FakeDatabase:
    def __init__(self):
        self.tables = {
            "collection_items": [],
            "trips": [{"id": 9, "user_id": 1, "title": "東京行"}],
        }
        self.next_id = 1

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        rows = list(self.tables[table])
        if where == "id = %s AND user_id = %s":
            rows = [row for row in rows if row["id"] == params[0] and row["user_id"] == params[1]]
        return (rows[0] if rows else None) if fetch_one else rows

    def insert(self, table, data, returning="id"):
        row = {"id": self.next_id, **data}
        self.next_id += 1
        self.tables[table].append(row)
        return row[returning]

    def update(self, table, data, where, params):
        row = self.select(table, where=where, params=params, fetch_one=True)
        if row is None:
            return 0
        row.update(data)
        return 1

    def delete(self, table, where, params):
        before = len(self.tables[table])
        self.tables[table] = [
            row for row in self.tables[table]
            if not (row["id"] == params[0] and row["user_id"] == params[1])
        ]
        return before - len(self.tables[table])

    def execute_query(self, query, params=None):
        return list(self.tables["collection_items"])


def payload(**overrides):
    value = {
        "item_type": "restaurant",
        "title": "東京拉麵",
        "country_code": "JP",
        "country_name": "日本",
        "city_name": "東京",
        "address": "東京都千代田區",
        "latitude": 35.681236,
        "longitude": 139.767125,
        "estimated_cost": 1200,
    }
    value.update(overrides)
    return value


def test_create_normalizes_collection_values_and_uses_fixed_defaults():
    db = FakeDatabase()

    result = AppCollectionService(db).create(1, payload())

    assert result == {"id": 1, "message": "收藏項目已新增"}
    row = db.tables["collection_items"][0]
    assert row["user_id"] == 1
    assert row["currency_code"] == "TWD"
    assert row["status"] == "saved"
    assert row["estimated_cost"] == Decimal("1200")
    assert "priority" not in row
    assert "desired_date" not in row
    assert "administrative_area" not in row
    assert "trip_id" not in row


def test_coordinates_must_be_provided_as_a_pair():
    with pytest.raises(CollectionValidationError, match="同時包含"):
        AppCollectionService(FakeDatabase()).create(1, payload(longitude=None))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"country_name": ""}, "請輸入國家"),
        ({"city_name": ""}, "請輸入區域／城市"),
        ({"address": ""}, "請輸入地址"),
    ],
)
def test_location_collection_requires_country_city_and_address(overrides, message):
    with pytest.raises(CollectionValidationError, match=message):
        AppCollectionService(FakeDatabase()).create(1, payload(**overrides))


@pytest.mark.parametrize("item_type", ["activity", "other"])
def test_non_location_activity_can_omit_address(item_type):
    db = FakeDatabase()

    AppCollectionService(db).create(1, payload(item_type=item_type, address=""))

    assert db.tables["collection_items"][0]["address"] is None


def test_client_cannot_set_visited_status_directly():
    db = FakeDatabase()
    AppCollectionService(db).create(1, payload(status="visited"))

    assert db.tables["collection_items"][0]["status"] == "saved"
    assert "visited_at" not in db.tables["collection_items"][0]


def test_list_returns_summary_and_serializable_numbers():
    db = FakeDatabase()
    db.tables["collection_items"] = [
        {
            "id": 1, "user_id": 1, "title": "餐廳", "status": "saved",
            "country_name": "日本", "city_name": "東京",
            "estimated_cost": Decimal("1000.50"),
        },
        {
            "id": 2, "user_id": 1, "title": "富士山", "status": "visited",
            "country_name": "日本", "city_name": "富士吉田",
        },
    ]

    result = AppCollectionService(db).list_for_user(1)

    assert result["summary"] == {"total": 2, "saved": 1, "added_to_trip": 0, "visited": 1}
    assert result["filters"]["countries"] == ["日本"]
    assert result["items"][0]["estimated_cost"] == 1000.5


def test_update_does_not_overwrite_derived_status():
    db = FakeDatabase()
    item_id = AppCollectionService(db).create(1, payload())["id"]
    db.tables["collection_items"][0]["status"] = "visited"

    AppCollectionService(db).update(item_id, 1, payload(title="更新名稱", status="cancelled"))

    assert db.tables["collection_items"][0]["status"] == "visited"


def test_other_user_cannot_update_or_delete_collection_item():
    db = FakeDatabase()
    service = AppCollectionService(db)
    item_id = service.create(1, payload())["id"]

    with pytest.raises(CollectionNotFoundError):
        service.update(item_id, 2, payload(title="不是我的收藏"))
    with pytest.raises(CollectionNotFoundError):
        service.delete(item_id, 2)


def test_delete_is_soft_delete_and_restore_recovers_item():
    db = FakeDatabase()
    service = AppCollectionService(db)
    item_id = service.create(1, payload())["id"]

    deleted = service.delete(item_id, 1)

    assert deleted["undo_seconds"] == 5
    assert db.tables["collection_items"][0]["deleted_at"] is not None

    service.restore(item_id, 1)

    assert db.tables["collection_items"][0]["deleted_at"] is None
