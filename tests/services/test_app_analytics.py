from datetime import date

import pytest

from src.services.app_analytics import (
    AppAnalyticsService,
    DateRangeError,
    _matches_calendar_name,
    parse_calendar_month,
    parse_date_range,
    parse_single_date,
)
from src.services.app_auth import AuthenticatedUser


class FakeDatabase:
    def __init__(self, *, toggles=None, query_rows=None, users=None, select_rows=None):
        self.toggles = toggles or []
        self.query_rows = query_rows or {}
        self.users = users or []
        self.select_rows = select_rows or {}
        self.executed_queries = []

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        if table == "feature_toggles":
            rows = self.toggles
        elif table == "users":
            rows = self.users
        else:
            rows = self.select_rows.get(table, [])
        if fetch_one:
            return rows[0] if rows else None
        return rows

    def execute_query(self, query, params=None):
        self.executed_queries.append(query)
        for marker, rows in self.query_rows.items():
            if marker in query:
                return rows
        return []


def user(*, is_owner=False):
    return AuthenticatedUser(
        database_id=1,
        app_user_id="user01",
        role="Robin" if is_owner else "家人",
        is_owner=is_owner,
    )


def test_technical_sharing_accepts_exactly_one_historical_date():
    selected = parse_single_date("2026-06-11", today=date(2026, 8, 11))

    assert selected.start == date(2026, 6, 11)
    assert selected.end == date(2026, 6, 11)


@pytest.mark.parametrize("value", ["", "invalid", "2026-08-12"])
def test_technical_sharing_rejects_invalid_or_future_date(value):
    with pytest.raises(DateRangeError):
        parse_single_date(value, today=date(2026, 8, 11))


def test_date_range_accepts_arbitrary_historical_one_to_thirty_day_window():
    single = parse_date_range("2026-06-11", "2026-06-11", today=date(2026, 8, 11))
    selected = parse_date_range("2026-06-11", "2026-06-17", today=date(2026, 8, 11))

    assert single.days == 1
    assert selected.start == date(2026, 6, 11)
    assert selected.end == date(2026, 6, 17)
    assert selected.days == 7


def test_calendar_month_returns_complete_visible_month():
    selected = parse_calendar_month("2026-08")

    assert selected.start == date(2026, 8, 1)
    assert selected.end == date(2026, 8, 31)


def test_calendar_notification_deduplicates_existing_holiday_name():
    assert _matches_calendar_name({"name": "中秋節"}, "中秋節") is True
    assert _matches_calendar_name({"name": "國慶日／連假"}, "國慶日") is True
    assert _matches_calendar_name({"name": "中秋節"}, "家族聚餐") is False


@pytest.mark.parametrize("value", ["", "2026-8", "2026-13", "invalid"])
def test_calendar_month_rejects_invalid_values(value):
    with pytest.raises(DateRangeError):
        parse_calendar_month(value)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-06-11", "2026-07-11"),
        ("invalid", "2026-06-17"),
        ("2026-06-17", "2026-06-11"),
        ("2026-08-06", "2026-08-12"),
    ],
)
def test_date_range_rejects_invalid_short_long_reversed_or_future_ranges(start, end):
    with pytest.raises(DateRangeError):
        parse_date_range(start, end, today=date(2026, 8, 11))


def test_legacy_general_feature_toggle_does_not_disable_mobile_module():
    # 2026-11（功能大幅精簡，見 ADR-33）：`feature_toggles` 表已隨功能開關整批移除，分析頁
    # 現在只剩待辦事項／體態／記帳三項，一律開放，不再有 owner_only 的灰階/隱藏頁面。
    db = FakeDatabase(toggles=[{"feature_key": "budget", "is_enabled": False}])
    service = AppAnalyticsService(db)

    navigation = service.navigation(user())

    assert navigation["finance"]["is_enabled"] is True


def test_navigation_uses_confirmed_mobile_drawer_order():
    # 2026-11（功能大幅精簡，見 ADR-33）：待辦事項改走 `src/services/app_todo.py`，不再透過
    # 這支分析服務的 navigation／todos()，分析頁只剩體態／記帳。
    navigation = AppAnalyticsService(FakeDatabase()).navigation(user())

    assert list(navigation) == ["body", "finance"]
    assert navigation["finance"]["label"] == "記帳分析"


def test_finance_returns_chart_ready_daily_category_and_income_data():
    db = FakeDatabase(
        toggles=[{"feature_key": "budget", "is_enabled": True}],
        query_rows={
            "app_analytics:finance_daily": [
                {"day": date(2026, 8, 1), "type": "expense", "amount": 120},
                {"day": date(2026, 8, 1), "type": "income", "amount": 500},
            ],
            "app_analytics:finance_categories": [{"category": "餐飲", "amount": 120}],
        },
    )

    result = AppAnalyticsService(db).finance(user(), date(2026, 8, 1), date(2026, 8, 7))

    assert result["daily"][0] == {"date": "2026-08-01", "expense": 120.0, "income": 500.0}
    assert result["expense_categories"] == [{"label": "餐飲", "value": 120.0}]
    assert result["income_total"] == 500.0


def test_finance_returns_latest_record_outside_selected_range():
    # 2026-11（功能大幅精簡，見 ADR-33）：記帳目標依附的 `module_goals` 表已隨目標追蹤功能
    # 整批移除，`finance()` 不再回傳 `goals`／`goal_summary`。
    db = FakeDatabase(
        users=[{"id": 1}],
        select_rows={"transactions": [{"id": 3}]},
        query_rows={
            "app_analytics:finance_daily": [],
            "app_analytics:finance_categories": [],
            "app_analytics:finance_records": [],
            "app_analytics:finance_latest": [{
                "id": 3, "type": "income", "category": "其他", "amount": 500,
                "note": None, "date": date(2026, 8, 10), "created_at": "2026-08-10T08:00:00",
            }],
        },
    )

    result = AppAnalyticsService(db, today=date(2026, 8, 11)).finance(
        user(), date(2026, 8, 1), date(2026, 8, 7)
    )

    assert result["latest_record"]["id"] == 3
    assert result["latest_record"]["can_edit"] is False
    assert "goals" not in result
    assert "goal_summary" not in result


def test_body_keeps_missing_days_absent_so_line_chart_breaks_the_line():
    db = FakeDatabase(
        toggles=[{"feature_key": "body", "is_enabled": True}],
        query_rows={
            "app_analytics:body_weight": [
                {"day": date(2026, 8, 1), "weight_kg": 70, "waist_cm": 82, "height_cm": 175},
                {"day": date(2026, 8, 3), "weight_kg": 69.5, "waist_cm": None, "height_cm": 175},
            ],
            "app_analytics:body_diet": [],
            "app_analytics:body_exercise": [],
            "app_analytics:body_goals": [],
        },
    )

    result = AppAnalyticsService(db).body(user(), date(2026, 8, 1), date(2026, 8, 7))

    assert [point["date"] for point in result["weight"]] == ["2026-08-01", "2026-08-03"]
    assert result["weight"][0]["bmi"] == 22.86
    assert result["weight"][0]["waist"] == 82.0
    assert result["weight"][1]["waist"] is None
    weight_query = next(query for query in db.executed_queries if "app_analytics:body_weight" in query)
    assert "DISTINCT ON (w.entry_date)" in weight_query
    assert "w.created_at DESC, w.id DESC" in weight_query


def test_body_splits_diet_and_exercise_totals_by_ai_and_manual_source():
    db = FakeDatabase(
        toggles=[{"feature_key": "body", "is_enabled": True}],
        query_rows={
            "app_analytics:body_weight": [],
            "app_analytics:body_diet": [{
                "date": date(2026, 8, 1),
                "water_ml": 1200,
                "ai_count": 1,
                "manual_count": 1,
                "ai_fat_g": 10,
                "manual_fat_g": 5,
                "ai_protein_g": 30,
                "manual_protein_g": 20,
                "ai_carbs_g": 40,
                "manual_carbs_g": 15,
                "ai_calories": 500,
                "manual_calories": 300,
            }],
            "app_analytics:body_exercise": [{
                "date": date(2026, 8, 1),
                "ai_count": 1,
                "manual_count": 1,
                "ai_calories": 250,
                "manual_calories": 120,
                "minutes": 45,
            }],
            "app_analytics:body_goals": [],
        },
    )

    result = AppAnalyticsService(db).body(user(), date(2026, 8, 1), date(2026, 8, 7))

    assert result["diet"][0]["ai_calories"] == 500.0
    assert result["diet"][0]["manual_calories"] == 300.0
    assert result["diet"][0]["total_calories"] == 800.0
    assert result["exercise"][0] == {
        "date": "2026-08-01",
        "ai_count": 1,
        "manual_count": 1,
        "ai_calories": 250.0,
        "manual_calories": 120.0,
        "total_calories": 370.0,
        "minutes": 45.0,
    }


def test_body_returns_latest_record_defaults_bmi_and_no_goal_fields():
    # 2026-11-26（ADR 再修正）：`body_goals` 表與對應的「設定體態目標」功能已確認零入口並整批
    # 移除，`body()` 不再回傳 `goals`／`goal_summary`。
    db = FakeDatabase(
        toggles=[{"feature_key": "body", "is_enabled": True}],
        users=[{"id": 1, "height_cm": 175}],
        query_rows={
            "app_analytics:body_weight": [],
            "app_analytics:body_diet": [],
            "app_analytics:body_exercise": [],
            "app_analytics:body_latest": [{
                "id": 9, "user_id": 1, "entry_date": date(2026, 8, 11),
                "weight_kg": 70, "waist_cm": 82, "height_cm": 175,
            }],
        },
    )

    result = AppAnalyticsService(db).body(user(), date(2026, 8, 1), date(2026, 8, 11))

    assert result["latest_body_record"]["id"] == 9
    assert result["latest_body_record"]["bmi"] == 22.86
    assert result["body_defaults"] == {"height_cm": 175, "weight_kg": 70.0, "waist_cm": 82}
    assert "goals" not in result
    assert "goal_summary" not in result


def test_dashboard_returns_summary_and_role_specific_sent_notifications():
    # 2026-11-26（ADR 再修正）：首頁通知不再查詢已死欄位 `users.birthday`，改用
    # `important_days`（透過 `check_and_push_birthdays()` 寫入的
    # `birthday_important_day_{id}_offset_{offset}` key），且只有 offset == 0（當天）才會出現
    # 在首頁，見 `_notifications_for_user()` docstring。
    # 2026-11-26（首頁改行事曆）：`important_days` 回傳欄位已移除（首頁改用月曆呈現，見
    # mobile/src/components/HomeCalendar.tsx），這裡只驗證 `notifications`（生日快樂訊息）。
    db = FakeDatabase(
        query_rows={"app_analytics:dashboard": [{"todo_count": 2, "expense_today": 300}]},
        select_rows={
            "important_notifications_log": [
                {"notification_key": "birthday_important_day_1_offset_0"},
            ],
            "important_days": [
                {"id": 1, "user_id": 1, "name": "我", "birth_month": 8, "birth_day": 8},
            ],
        },
    )

    result = AppAnalyticsService(db).dashboard(user(is_owner=True), today=date(2026, 8, 8))

    assert result["summary"]["todo_count"] == 2
    assert result["date"] == "2026-08-08"
    assert any("生日快樂" in message for message in result["notifications"])
    assert "important_days" not in result


def test_dashboard_sql_does_not_reference_dropped_todo_columns():
    """2026-11 兩次 production 事故（dashboard() 裡的待辦子查詢分別殘留過舊版 `due_at`／
    `status`、以及 migration 0106 改名前的 `remind_at`）都是同一種 bug：既有 FakeDatabase 只用
    marker 字串比對回傳假資料，不會真的驗證 SQL 本身的欄位名稱是否還存在，所以兩次都沒被測試
    抓到。這裡直接檢查實際送出的 SQL 字串，確保不會再度引用已經被 migration 刪除／改名的欄位。
    """
    db = FakeDatabase(query_rows={"app_analytics:dashboard": [{"todo_count": 0, "expense_today": 0}]})

    AppAnalyticsService(db).dashboard(user(is_owner=True), today=date(2026, 8, 8))

    dashboard_query = next(query for query in db.executed_queries if "app_analytics:dashboard" in query)
    assert "due_at" not in dashboard_query
    assert "status = 'pending'" not in dashboard_query
    assert "remind_at" not in dashboard_query
    assert "remind_start_date" in dashboard_query
    assert "remind_end_date" in dashboard_query
