from datetime import date
from decimal import Decimal

import pytest

from src.services.app_life_exploration import AppLifeExplorationService, LifeValidationError


class FakeDatabase:
    def __init__(self):
        self.tables = {
            "collection_items": [{"id": 2, "user_id": 1, "title": "拉麵店", "status": "saved"}],
            "trips": [], "trip_collection_items": [], "exploration_events": [],
            "user_achievements": [], "achievement_candidates": [],
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
        self.tables[table] = [row for row in self.tables[table] if row.get("trip_id") != params[0]]
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
    assert db.tables["trips"][0]["budget_amount"] == Decimal("3000")
    assert db.tables["trip_collection_items"][0]["collection_item_id"] == 2
    assert db.tables["collection_items"][0]["status"] == "added_to_trip"


def test_confirmed_trip_requires_dates_and_end_cannot_precede_start():
    service = AppLifeExplorationService(FakeDatabase())
    with pytest.raises(LifeValidationError, match="請設定日期"):
        service.create_trip(1, trip_payload(status="confirmed"))
    with pytest.raises(LifeValidationError, match="不可早於"):
        service.create_trip(1, trip_payload(start_date="2026-08-20", end_date="2026-08-19"))


@pytest.mark.parametrize(("score", "target", "expected"), [("850", "800", True), ("700", "800", False), ("通過", "合格", True)])
def test_score_target_comparison(score, target, expected):
    assert AppLifeExplorationService._score_reaches_target(score, target) is expected


def test_manual_achievement_requires_category_and_date():
    service = AppLifeExplorationService(FakeDatabase())
    with pytest.raises(LifeValidationError):
        service.create_achievement(1, {"category": "other", "title": "學會料理", "completed_on": "錯誤"})
    result = service.create_achievement(1, {"category": "other", "title": "學會料理", "completed_on": date.today().isoformat()})
    assert result["message"] == "成果已建立"
