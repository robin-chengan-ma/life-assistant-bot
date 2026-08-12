from datetime import date

from src.services.taiwan_calendar import TaiwanCalendarService


class FakeDatabase:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.executed = []

    def execute_query(self, query, params=None):
        return self.rows

    def execute(self, query, params=None):
        self.executed.append((query, params))


def test_cached_holiday_keeps_official_name_and_adds_christmas_alias():
    db = FakeDatabase([
        {
            "calendar_date": date(2026, 12, 25),
            "year": 2026,
            "name": "行憲紀念日",
            "is_holiday": True,
            "holiday_category": "放假之紀念日及節日",
            "description": "放假一日",
        }
    ])

    result = TaiwanCalendarService(db).days(date(2026, 12, 25), date(2026, 12, 25))

    assert result["2026-12-25"]["name"] == "行憲紀念日／聖誕節"
    assert result["2026-12-25"]["is_holiday"] is True


def test_weekend_fallback_is_available_when_official_year_is_not_cached():
    result = TaiwanCalendarService(FakeDatabase()).days(date(2028, 1, 1), date(2028, 1, 3))

    assert result["2028-01-01"]["is_holiday"] is True
    assert result["2028-01-02"]["holiday_category"] == "星期六、星期日"
    assert "2028-01-03" not in result
