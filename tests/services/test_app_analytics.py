from datetime import date

import pytest

from src.services.app_analytics import (
    AppAnalyticsService,
    DateRangeError,
    FeatureDisabledError,
    ForbiddenModuleError,
    _matches_calendar_name,
    parse_calendar_month,
    parse_date_range,
    parse_single_date,
    parse_todo_date_range,
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


@pytest.mark.parametrize(
    ("start", "end", "expected_days"),
    [
        ("2026-08-05", "2026-08-05", 1),
        ("2026-08-11", "2026-08-17", 7),
        ("2027-01-01", "2027-01-03", 3),
    ],
)
def test_todo_date_range_accepts_one_to_seven_days_including_future(start, end, expected_days):
    selected = parse_todo_date_range(start, end)

    assert selected.days == expected_days


@pytest.mark.parametrize(
    ("start", "end"),
    [("2026-08-01", "2026-08-08"), ("2026-08-02", "2026-08-01"), ("invalid", "2026-08-01")],
)
def test_todo_date_range_rejects_long_reversed_or_invalid_ranges(start, end):
    with pytest.raises(DateRangeError):
        parse_todo_date_range(start, end)


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
    db = FakeDatabase(toggles=[{"feature_key": "budget", "is_enabled": False}])
    service = AppAnalyticsService(db)

    navigation = service.navigation(user())

    assert navigation["finance"]["is_enabled"] is True


def test_disabled_owner_feature_is_returned_for_grey_ui_but_cannot_be_opened():
    db = FakeDatabase(toggles=[{"feature_key": "job_search", "is_enabled": False}])
    service = AppAnalyticsService(db)

    navigation = service.navigation(user(is_owner=True))

    assert navigation["jobs"]["is_enabled"] is False
    with pytest.raises(FeatureDisabledError):
        service.jobs(user(is_owner=True), date(2026, 8, 1), date(2026, 8, 7))


def test_owner_only_modules_are_hidden_from_family_and_protected_on_backend():
    service = AppAnalyticsService(FakeDatabase())

    assert "jobs" not in service.navigation(user())
    with pytest.raises(ForbiddenModuleError):
        service.jobs(user(), date(2026, 8, 1), date(2026, 8, 7))
    assert "jobs" in service.navigation(user(is_owner=True))


def test_owner_navigation_uses_confirmed_mobile_drawer_order():
    navigation = AppAnalyticsService(FakeDatabase()).navigation(user(is_owner=True))

    assert list(navigation) == ["todos", "body", "finance", "mood", "skills", "jobs", "exams"]
    assert navigation["mood"]["label"] == "心情小記"


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


def test_finance_returns_latest_record_outside_selected_range_and_normalized_goal():
    db = FakeDatabase(
        users=[{"id": 1}],
        select_rows={"transactions": [{"id": 3}], "module_goals": [{"id": 2}]},
        query_rows={
            "app_analytics:finance_daily": [],
            "app_analytics:finance_categories": [],
            "app_analytics:finance_records": [],
            "app_analytics:finance_latest": [{
                "id": 3, "type": "income", "category": "其他", "amount": 500,
                "note": None, "date": date(2026, 8, 10), "created_at": "2026-08-10T08:00:00",
            }],
            "app_analytics:finance_goals": [{
                "id": 2, "module_key": "finance", "target_description": "存下 1000 元",
                "target_value": 1000, "target_unit": "TWD", "baseline_value": 0,
                "target_date": date(2026, 12, 31), "status": "active",
                "created_at": "2026-08-01T00:00:00", "updated_at": "2026-08-01T00:00:00",
                "completed_at": None, "current_value": 500,
            }],
        },
    )

    result = AppAnalyticsService(db, today=date(2026, 8, 11)).finance(
        user(), date(2026, 8, 1), date(2026, 8, 7)
    )

    assert result["latest_record"]["id"] == 3
    assert result["latest_record"]["can_edit"] is False
    assert result["goal_summary"]["id"] == 2
    assert result["goal_summary"]["progress_percent"] == 50
    assert result["goals"] == [result["goal_summary"]]


def test_mood_returns_latest_record_outside_selected_range():
    db = FakeDatabase(
        select_rows={"mood_journals": [{"id": 7}]},
        query_rows={
            "app_analytics:mood */": [{
                "id": 6,
                "date": date(2026, 8, 10),
                "mood_category": "calm_relaxed",
                "content": "區間內紀錄",
                "achievement_note": None,
                "created_at": "2026-08-10T08:00:00",
            }],
            "app_analytics:mood_latest": [{
                "id": 7,
                "date": date(2026, 8, 11),
                "mood_category": "happy_excited",
                "content": "最新紀錄",
                "achievement_note": "完成測試",
                "created_at": "2026-08-11T09:00:00",
            }],
        },
    )

    result = AppAnalyticsService(db, today=date(2026, 8, 11)).mood(
        user(), date(2026, 8, 1), date(2026, 8, 10)
    )

    assert result["items"][0]["can_edit"] is False
    assert result["latest_record"]["id"] == 7
    assert result["latest_record"]["can_edit"] is True


def test_goal_normalization_handles_improvement_milestone_and_expired_status():
    service = AppAnalyticsService(FakeDatabase(), today=date(2026, 8, 11))

    improvement = service._normalized_goal({
        "id": 1, "goal_type": "weight", "target_description": "降到 60 公斤",
        "baseline_value": 70, "target_value": 60, "current_value": 65,
        "progress_mode": "improvement", "status": "active", "target_date": date(2026, 12, 1),
    })
    milestone = service._normalized_goal({
        "id": 2, "goal_type": "exercise", "target_description": "完成三鐵",
        "target_value": None, "current_value": None, "progress_mode": "milestone",
        "status": "active", "target_date": None,
    })
    expired = service._normalized_goal({
        "id": 3, "module_key": "finance", "target_description": "存錢",
        "target_value": 1000, "current_value": 200, "status": "active",
        "target_date": date(2026, 8, 10),
    })

    assert improvement["progress_percent"] == 50
    assert milestone["progress_percent"] == 0
    assert expired["status"] == "expired"
    assert service._goal_summary([expired, improvement]) == improvement


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


def test_body_returns_latest_record_defaults_bmi_and_goal_description():
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
            "app_analytics:body_goals": [{
                "goal_type": "weight", "target_description": "減重至 65 公斤",
                "target_value": 65, "baseline_value": 70, "target_date": date(2026, 12, 31),
            }],
        },
    )

    result = AppAnalyticsService(db).body(user(), date(2026, 8, 1), date(2026, 8, 11))

    assert result["latest_body_record"]["id"] == 9
    assert result["latest_body_record"]["bmi"] == 22.86
    assert result["body_defaults"] == {"height_cm": 175, "weight_kg": 70.0, "waist_cm": 82}
    assert result["goals"][0]["target_description"] == "減重至 65 公斤"


def test_dashboard_returns_summary_and_role_specific_sent_notifications():
    db = FakeDatabase(
        query_rows={"app_analytics:dashboard": [{"todo_count": 2, "expense_today": 300}]},
        select_rows={
            "important_notifications_log": [
                {"notification_key": "fathers_day"},
                {"notification_key": "birthday_1"},
            ]
        },
        users=[{"id": 1, "role": "Robin", "birthday": date(1990, 8, 8)}],
    )

    result = AppAnalyticsService(db).dashboard(user(is_owner=True), today=date(2026, 8, 8))

    assert result["summary"]["todo_count"] == 2
    assert result["date"] == "2026-08-08"
    assert any("父親節" in message for message in result["notifications"])
    assert any("生日快樂" in message for message in result["notifications"])
    assert "今天：父親節" in result["important_days"]
    assert "今天：我的生日" in result["important_days"]


def test_dashboard_important_days_only_include_current_sunday_to_saturday():
    db = FakeDatabase(users=[])

    result = AppAnalyticsService(db).dashboard(user(is_owner=True), today=date(2026, 8, 5))

    assert "3 天後：父親節" in result["important_days"]
    assert all(message.startswith(("今天：", "3 天後：", "當周：")) for message in result["important_days"])
    assert not any("中秋節" in message for message in result["important_days"])


def test_remaining_analysis_modules_return_chart_ready_payloads():
    db = FakeDatabase(
        toggles=[
            {"feature_key": key, "is_enabled": True}
            for key in ("todo", "mood_journal", "job_search", "certificate", "tech_intel")
        ],
        select_rows={
            "todos": [{"id": 1}],
            "mood_journals": [{"id": 1}],
            "job_postings": [{"id": 1}],
            "certificate_goals": [{"id": 1}],
            "skill_growth_digests": [{"id": 1}],
        },
        query_rows={
            "app_analytics:todo_calendar_counts": [{"day": date(2026, 8, 2), "count": 2}],
            "app_analytics:todos */": [{"id": 1, "content": "待辦", "due_at": "2026-08-02", "start_at": None, "status": "pending"}],
            "app_analytics:mood": [{"id": 1, "date": date(2026, 8, 2), "mood_category": "happy_excited", "content": "很好", "achievement_note": None}],
            "app_analytics:jobs_postings": [
                {"job_id_104": "a", "title": "工程師", "company_name": "範例公司", "region": "台北", "source": "104", "url": "https://example.com/a", "match_score": 85, "recommend_reason": "適合", "skill_gap_note": None, "first_seen_at": "2026-08-01"},
                {"job_id_104": "b", "title": "後端", "match_score": 65, "recommend_reason": "可考慮", "skill_gap_note": None, "first_seen_at": "2026-08-01"},
                {"job_id_104": "c", "title": "前端", "match_score": 50, "recommend_reason": "較低", "skill_gap_note": None, "first_seen_at": "2026-08-01"},
            ],
            "app_analytics:jobs_timeline": [
                {"job_id_104": "a", "title": "工程師", "status": "applied", "created_at": "2026-08-02"},
                {"job_id_104": "a", "title": "工程師", "status": "interview", "created_at": "2026-08-03"},
            ],
            "app_analytics:exam_goals": [{"exam_type": "TOEIC", "target_date": date(2026, 12, 1), "target_score": "850"}],
            "app_analytics:exam_profiles": [{"certificate_key": "toeic", "display_name": "TOEIC", "is_active": True}],
            "app_analytics:exam_question_types": [{"exam_type": "toeic"}],
            "app_analytics:exam_best_scores": [{"exam_type": "TOEIC", "score": "700"}],
            "app_analytics:exam_scores": [{"exam_type": "TOEIC", "exam_date": date(2026, 8, 1), "score": "700", "note": "第一次正式應考"}],
            "app_analytics:exam_practice": [{"date": date(2026, 8, 2), "exam_type": "TOEIC", "question_type": "listen", "total": 2, "correct": 1}],
            "app_analytics:skill_digests": [{"digest_date": date(2026, 8, 1), "source": "ithome", "summary_text": "摘要"}],
            "app_analytics:skill_videos": [{"pushed_on": date(2026, 8, 1), "topic": "AI", "title": "影片", "recommend_reason": "推薦"}],
        },
    )
    service = AppAnalyticsService(db)
    start, end = date(2026, 8, 1), date(2026, 8, 7)

    todos = service.todos(user(), start, end, calendar_start=start, calendar_end=date(2026, 8, 31))
    assert todos["items"][0]["content"] == "待辦"
    assert todos["calendar_counts"] == {"2026-08-02": 2}
    assert service.mood(user(), start, end)["items"][0]["date"] == "2026-08-02"
    jobs = service.jobs(user(is_owner=True), start, end)
    jobs_query = next(query for query in db.executed_queries if "app_analytics:jobs_postings" in query)
    assert "score AS match_score" in jobs_query
    assert "title, match_score" not in jobs_query
    assert jobs["funnel"]["interview"] == 1
    assert jobs["score_distribution"] == {"high": 1, "medium": 1, "low": 1}
    assert jobs["recommendations"][0]["company_name"] == "範例公司"
    exams = service.exams(user(is_owner=True), start, end)
    exam_scores_query = next(query for query in db.executed_queries if "app_analytics:exam_scores" in query)
    assert "score, note" in exam_scores_query
    assert exams["practice"][0]["correct"] == 1
    assert exams["official_scores"][0]["note"] == "第一次正式應考"
    assert exams["certificates"] == [{"key": "toeic", "display_name": "TOEIC", "has_question_bank": True}]
    assert exams["goals"][0]["progress_percent"] == 82.4
    assert exams["goal_summaries"]["toeic"]["description"] == "TOEIC 目標 850"
    assert service.skills(user(is_owner=True), start, end)["videos"][0]["title"] == "影片"


def test_todos_separates_pending_current_and_overdue_items():
    db = FakeDatabase(
        select_rows={"todos": [{"id": 1}]},
        query_rows={
            "app_analytics:todos */": [{
                "id": 1, "content": "今天處理", "due_at": "2026-08-11T18:00:00+08:00",
                "start_at": None, "status": "pending", "created_at": "2026-08-10T00:00:00",
            }],
            "app_analytics:todos_overdue": [{
                "id": 2, "content": "已逾期", "due_at": "2026-08-10T18:00:00+08:00",
                "start_at": None, "status": "pending", "created_at": "2026-08-09T00:00:00",
            }],
            "app_analytics:todo_calendar_counts": [],
        },
    )

    result = AppAnalyticsService(db, today=date(2026, 8, 11)).todos(
        user(), date(2026, 8, 11), date(2026, 8, 11),
        calendar_start=date(2026, 8, 1), calendar_end=date(2026, 8, 31),
    )

    assert [item["id"] for item in result["items"]] == [1]
    assert [item["id"] for item in result["overdue_items"]] == [2]
    assert result["overdue_count"] == 1
    assert result["overdue_items"][0]["can_edit"] is True


def test_jobs_excludes_closed_postings_from_recommendations_but_keeps_distribution():
    db = FakeDatabase(
        toggles=[{"feature_key": "job_search", "is_enabled": True}],
        select_rows={"job_postings": [{"id": 1}]},
        query_rows={
            "app_analytics:jobs_postings": [
                {"job_id_104": "open", "title": "開放職缺", "match_score": 85, "is_closed": False},
                {"job_id_104": "closed", "title": "關閉職缺", "match_score": 90, "is_closed": True},
            ],
            "app_analytics:jobs_timeline": [],
        },
    )

    result = AppAnalyticsService(db).jobs(user(is_owner=True), date(2026, 8, 1), date(2026, 8, 7))

    assert [row["job_id_104"] for row in result["recommendations"]] == ["open"]
    assert result["score_distribution"] == {"high": 2, "medium": 0, "low": 0}


def test_jobs_recommendations_exclude_unscored_and_low_score_postings():
    # 2026-08-24（見 docs/ADR/debug/job-search.md「推薦職缺不分青紅皂白」條目）：契合度評分
    # 尚未執行（match_score 為 NULL）或分數未達 60 分門檻的職缺，不該被硬塞進推薦清單。
    db = FakeDatabase(
        toggles=[{"feature_key": "job_search", "is_enabled": True}],
        select_rows={"job_postings": [{"id": 1}]},
        query_rows={
            "app_analytics:jobs_postings": [
                {"job_id_104": "unscored", "title": "尚未評分職缺", "match_score": None, "is_closed": False},
                {"job_id_104": "too_low", "title": "分數太低職缺", "match_score": 1, "is_closed": False},
                {"job_id_104": "just_enough", "title": "剛好達標職缺", "match_score": 60, "is_closed": False},
            ],
            "app_analytics:jobs_timeline": [],
        },
    )

    result = AppAnalyticsService(db).jobs(user(is_owner=True), date(2026, 8, 1), date(2026, 8, 7))

    assert [row["job_id_104"] for row in result["recommendations"]] == ["just_enough"]


def test_jobs_recommendations_empty_when_nothing_meets_threshold():
    db = FakeDatabase(
        toggles=[{"feature_key": "job_search", "is_enabled": True}],
        select_rows={"job_postings": [{"id": 1}]},
        query_rows={
            "app_analytics:jobs_postings": [
                {"job_id_104": "unscored", "title": "尚未評分職缺", "match_score": None, "is_closed": False},
            ],
            "app_analytics:jobs_timeline": [],
        },
    )

    result = AppAnalyticsService(db).jobs(user(is_owner=True), date(2026, 8, 1), date(2026, 8, 7))

    assert result["recommendations"] == []


def test_todo_calendar_days_include_role_visible_important_notifications_and_birthdays():
    db = FakeDatabase(
        users=[
            {"id": 1, "role": "Robin", "birthday": date(1990, 8, 12)},
            {"id": 2, "role": "爸爸", "birthday": date(1960, 8, 13)},
        ],
    )

    result = AppAnalyticsService(db).todos(
        user(is_owner=True),
        date(2026, 8, 8),
        date(2026, 8, 14),
        calendar_start=date(2026, 8, 1),
        calendar_end=date(2026, 8, 31),
    )

    assert "父親節" in result["calendar_days"]["2026-08-08"]["important_notifications"]
    assert "我的生日" in result["calendar_days"]["2026-08-12"]["important_notifications"]
    assert "爸爸生日" in result["calendar_days"]["2026-08-13"]["important_notifications"]
