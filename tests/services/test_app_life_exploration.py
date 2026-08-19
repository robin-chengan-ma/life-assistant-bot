from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from src.services.app_life_exploration import (
    AppLifeExplorationService,
    LifeNotFoundError,
    LifeValidationError,
)


class FakeDatabase:
    def __init__(self):
        self.tables = {
            "collection_items": [{
                "id": 2, "user_id": 1, "title": "拉麵店", "status": "saved",
                "country_name": "日本", "city_name": "東京",
            }],
            "trips": [], "trip_collection_items": [], "exploration_events": [],
            "user_achievements": [], "achievement_candidates": [], "important_days": [],
            "important_day_recipients": [], "important_day_occurrences": [],
        }
        self.next_id = 10

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        rows = list(self.tables[table])
        if where and "id = %s AND user_id = %s" in where:
            rows = [row for row in rows if row["id"] == params[0] and row["user_id"] == params[1]]
        elif where == "trip_id = %s":
            rows = [row for row in rows if row["trip_id"] == params[0]]
        elif where and "candidate_key = %s" in where:
            rows = [row for row in rows if row["user_id"] == params[0] and row["candidate_key"] == params[1]]
        return (rows[0] if rows else None) if fetch_one else rows

    def insert(self, table, data, returning="id"):
        row = {"id": self.next_id, **data}; self.next_id += 1; self.tables[table].append(row); return row[returning]

    def update(self, table, data, where, params):
        rows = self.select(table, where=where, params=params)
        for row in rows: row.update(data)
        return len(rows)

    def delete(self, table, where, params):
        key = "trip_id" if "trip_id" in (where or "") else "important_day_id"
        self.tables[table] = [row for row in self.tables[table] if row.get(key) != params[0]]
        return 1

    def execute_query(self, query, params=None):
        if "list_trips" in query: return []
        if "exam_goal_candidates" in query: return []
        if "COUNT" in query: return [{"todo_count": 0, "exercise_count": 0, "exploration_count": 0, "country_count": 0}]
        return []


def trip_payload(**overrides):
    value = {"title": "東京三日", "country_name": "日本", "city_name": "東京", "status": "planning", "collection_item_ids": [2], "estimated_food": 3000}
    value.update(overrides); return value


def test_create_trip_links_collection_and_derives_total_budget():
    db = FakeDatabase()
    result = AppLifeExplorationService(db).create_trip(1, trip_payload())
    assert result["id"] == 10
    assert db.tables["trips"][0]["budget_amount"] == Decimal(3000)
    assert db.tables["trip_collection_items"][0]["collection_item_id"] == 2
    assert db.tables["collection_items"][0]["status"] == "added_to_trip"


def test_confirmed_trip_requires_dates_and_end_cannot_precede_start():
    service = AppLifeExplorationService(FakeDatabase())
    with pytest.raises(LifeValidationError, match="請設定日期"):
        service.create_trip(1, trip_payload(status="confirmed"))
    with pytest.raises(LifeValidationError, match="不可早於"):
        service.create_trip(1, trip_payload(start_date="2026-08-20", end_date="2026-08-19"))


def test_trip_rejects_collection_from_other_destination():
    service = AppLifeExplorationService(FakeDatabase())
    with pytest.raises(LifeValidationError, match="必須與行程"):
        service.create_trip(1, trip_payload(city_name="大阪"))


def test_dated_trip_creates_linked_important_day_with_defaults():
    db = FakeDatabase()
    result = AppLifeExplorationService(db).create_trip(
        1, trip_payload(start_date="2026-08-11", end_date="2026-08-15"),
    )
    trip = db.tables["trips"][0]
    important_day = db.tables["important_days"][0]
    assert result["id"] == trip["id"]
    assert trip["important_day_id"] == important_day["id"]
    assert important_day["event_date"] == date(2026, 8, 11)
    assert important_day["event_end_date"] == date(2026, 8, 15)
    assert important_day["reminder_days_before"] == 1
    assert important_day["audience_mode"] == "self"


@pytest.mark.parametrize(("score", "target", "expected"), [("850", "800", True), ("700", "800", False), ("通過", "合格", True)])
def test_score_target_comparison(score, target, expected):
    assert AppLifeExplorationService._score_reaches_target(score, target) is expected


def test_manual_achievement_requires_category_and_date():
    service = AppLifeExplorationService(FakeDatabase())
    with pytest.raises(LifeValidationError):
        service.create_achievement(1, {"category": "other", "title": "學會料理", "completed_on": "錯誤"})
    result = service.create_achievement(
        1, {"category": "other", "title": "學會料理", "completed_on": datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()}
    )
    assert result["message"] == "成果已建立"


def test_achievements_sort_pinned_first_and_unpin_restores_date_order():
    db = FakeDatabase()
    db.tables["user_achievements"] = [
        {"id": 1, "user_id": 1, "unlocked_on": "2026-08-18", "pinned_at": None, "deleted_at": None},
        {"id": 2, "user_id": 1, "unlocked_on": "2026-08-10", "pinned_at": "2026-08-19T08:00:00+08:00", "deleted_at": None},
        {"id": 3, "user_id": 1, "unlocked_on": "2026-08-12", "pinned_at": "2026-08-19T09:00:00+08:00", "deleted_at": None},
    ]
    service = AppLifeExplorationService(db)

    assert [row["id"] for row in service.list_achievements(1)["achievements"]] == [3, 2, 1]

    service.set_achievement_pinned(3, 1, False)
    assert [row["id"] for row in service.list_achievements(1)["achievements"]] == [2, 1, 3]


def test_achievement_pinning_requires_ownership():
    service = AppLifeExplorationService(FakeDatabase())
    with pytest.raises(LifeNotFoundError):
        service.set_achievement_pinned(999, 1, True)


def test_relocate_exploration_updates_coordinates_and_address_change_clears_them():
    db = FakeDatabase()
    db.tables["exploration_events"].append({
        "id": 8, "user_id": 1, "start_date": "2026-08-14", "end_date": "2026-08-14",
        "address": "舊地址", "city_name": "台北", "country_name": "台灣",
        "latitude": Decimal("25.0"), "longitude": Decimal("121.0"), "notes": None,
    })

    class Geocoder:
        def search(self, value):
            assert value["address"] == "新地址"
            return {"latitude": 25.033964, "longitude": 121.564468, "display_name": "新位置"}

    service = AppLifeExplorationService(db, Geocoder())
    service.update_exploration(8, 1, {"visited_on": "2026-08-14", "address": "新地址"})
    assert db.tables["exploration_events"][0]["latitude"] is None

    result = service.relocate_exploration(8, 1)
    assert result["latitude"] == 25.033964
    assert db.tables["exploration_events"][0]["longitude"] == 121.564468
