"""FR-64 Mobile App 唯讀分析資料聚合服務。"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from src.bot.notifications import FIXED_NOTIFICATIONS
from src.services.app_auth import AuthenticatedUser
from src.services.app_important_days import AppImportantDayService
from src.services.taiwan_calendar import TaiwanCalendarService

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
# 2026-08-24（見 docs/ADR/debug/job-search.md「推薦職缺不分青紅皂白」條目）：`jobs()` 推薦職缺
# 門檻，沿用既有 high/medium 分界（60 分）。
_RECOMMENDATION_MIN_SCORE = 60


class AnalyticsDatabase(Protocol):
    def execute(self, query: str, params: tuple | None = None) -> None: ...

    def select(
        self,
        table: str,
        columns=("*",),
        where: str | None = None,
        params: tuple | None = None,
        fetch_one: bool = False,
    ): ...

    def execute_query(self, query: str, params: tuple | None = None) -> list[dict[str, Any]]: ...


class AppAnalyticsError(Exception):
    """FR-64 分析服務可預期錯誤。"""


class DateRangeError(AppAnalyticsError):
    """日期格式或區間長度不符合規格。"""


class ForbiddenModuleError(AppAnalyticsError):
    """非 Robin 使用者嘗試存取 owner-only 模組。"""


class FeatureDisabledError(AppAnalyticsError):
    """使用者嘗試開啟已關閉的模組。"""


@dataclass(frozen=True)
class AnalyticsDateRange:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def parse_date_range(start: str, end: str, *, today: date | None = None) -> AnalyticsDateRange:
    """解析任意歷史區間；單次最少 1 天、最多 30 天（起訖日皆計入）。"""
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except (TypeError, ValueError) as exc:
        raise DateRangeError("日期格式必須為 YYYY-MM-DD") from exc

    current_date = today or datetime.now(_TAIWAN_TZ).date()
    selected = AnalyticsDateRange(start=start_date, end=end_date)
    if start_date > end_date:
        raise DateRangeError("開始日期不可晚於結束日期")
    if end_date > current_date:
        raise DateRangeError("不可查詢未來日期")
    if selected.days < 1 or selected.days > 30:
        raise DateRangeError("日期區間必須介於 1 到 30 天")
    return selected


def parse_todo_date_range(start: str, end: str) -> AnalyticsDateRange:
    """解析待辦事項任意日期區間；單次最少 1 天、最多 7 天，未來日期不設上限。"""
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except (TypeError, ValueError) as exc:
        raise DateRangeError("日期格式必須為 YYYY-MM-DD") from exc

    selected = AnalyticsDateRange(start=start_date, end=end_date)
    if start_date > end_date:
        raise DateRangeError("開始日期不可晚於結束日期")
    if selected.days < 1 or selected.days > 7:
        raise DateRangeError("日期區間必須介於 1 到 7 天")
    return selected


def parse_calendar_month(value: str) -> AnalyticsDateRange:
    """解析待辦月曆目前顯示月份，回傳該月完整起迄日。"""
    try:
        if len(value) != 7 or value[4] != "-":
            raise ValueError
        year = int(value[:4])
        month = int(value[5:])
        start_date = date(year, month, 1)
    except (TypeError, ValueError) as exc:
        raise DateRangeError("月份格式必須為 YYYY-MM") from exc
    return AnalyticsDateRange(
        start=start_date,
        end=date(year, month, monthrange(year, month)[1]),
    )


def parse_single_date(value: str, *, today: date | None = None) -> AnalyticsDateRange:
    """解析技術分享的單日查詢；不得選擇未來日期。"""
    try:
        selected_date = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise DateRangeError("日期格式必須為 YYYY-MM-DD") from exc
    current_date = today or datetime.now(_TAIWAN_TZ).date()
    if selected_date > current_date:
        raise DateRangeError("不可查詢未來日期")
    return AnalyticsDateRange(start=selected_date, end=selected_date)


_MODULES: dict[str, dict[str, Any]] = {
    "todos": {"label": "待辦事項", "feature_key": "todo", "owner_only": False, "color": "#3B82F6"},
    "body": {"label": "體態分析", "feature_key": "body", "owner_only": False, "color": "#2E9D74"},
    "finance": {"label": "記帳分析", "feature_key": "budget", "owner_only": False, "color": "#EB9741"},
    "mood": {"label": "心情小記", "feature_key": "mood_journal", "owner_only": False, "color": "#A56CC1"},
    "skills": {"label": "技術分享", "feature_key": "tech_intel", "owner_only": True, "color": "#D9544D"},
    "jobs": {"label": "求職分析", "feature_key": "job_search", "owner_only": True, "color": "#7656C9"},
    "exams": {"label": "考試成績", "feature_key": "certificate", "owner_only": True, "color": "#D89B20"},
}


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _json_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_value(value) for key, value in row.items()}


def _matches_calendar_name(day: dict[str, Any], label: str) -> bool:
    return label.strip() in {
        name.strip()
        for name in str(day.get("name") or "").split("／")
        if name.strip()
    }


class AppAnalyticsService:
    def __init__(self, db: AnalyticsDatabase, *, sync_calendar: bool = False, today: date | None = None):
        self._db = db
        self._calendar = TaiwanCalendarService(db, sync_missing=sync_calendar)
        self._today = today or datetime.now(_TAIWAN_TZ).date()

    def _normalized_goal(self, row: dict[str, Any]) -> dict[str, Any]:
        target = float(row["target_value"]) if row.get("target_value") is not None else None
        current = float(row["current_value"]) if row.get("current_value") is not None else None
        baseline = float(row["baseline_value"]) if row.get("baseline_value") is not None else None
        progress = None
        exceeded = False
        mode = row.get("progress_mode", "cumulative")
        if row.get("status") == "achieved":
            progress = 100.0
        elif mode == "improvement" and target is not None and current is not None and baseline != target:
            raw_progress = (current - baseline) / (target - baseline) * 100 if baseline is not None else 0
            exceeded = raw_progress > 100
            progress = round(max(0, min(raw_progress, 100)), 1)
        elif mode == "milestone":
            progress = 0.0
        elif mode == "cumulative" and target is not None and target > 0 and current is not None:
            raw_progress = current / target * 100
            exceeded = raw_progress > 100
            progress = round(max(0, min(raw_progress, 100)), 1)
        description = row.get("target_description") or row.get("exam_type") or "未命名目標"
        target_date = _json_value(row.get("target_date"))
        status = row.get("status", "active")
        if status == "active" and target_date and date.fromisoformat(str(target_date)[:10]) < self._today:
            status = "expired"
        return {
            "id": row.get("id"),
            "goal_type": row.get("goal_type") or row.get("module_key") or row.get("exam_type"),
            "description": description,
            "target_description": description,
            "status": status,
            "target_date": target_date,
            "target_value": target,
            "current_value": current,
            "unit": row.get("target_unit"),
            "progress_percent": progress,
            "progress_unavailable": progress is None,
            "is_exceeded": exceeded,
            "updated_at": _json_value(row.get("updated_at")),
            "completed_at": _json_value(row.get("completed_at")),
        }

    @staticmethod
    def _goal_summary(goals: list[dict[str, Any]]) -> dict[str, Any] | None:
        active = [goal for goal in goals if goal["status"] == "active"]
        if not active:
            return None
        dated = [goal for goal in active if goal["target_date"]]
        candidates = sorted(dated or active, key=lambda goal: str(goal.get("updated_at") or ""), reverse=True)
        if dated:
            candidates.sort(key=lambda goal: goal["target_date"])
        return candidates[0]

    def navigation(self, user: AuthenticatedUser) -> dict[str, dict[str, Any]]:
        rows = self._db.select(
            "feature_toggles",
            columns=("feature_key", "is_enabled"),
            where="user_id = %s",
            params=(user.database_id,),
        )
        toggle_values = {row["feature_key"]: bool(row["is_enabled"]) for row in rows}
        navigation: dict[str, dict[str, Any]] = {}
        for module_key, config in _MODULES.items():
            if config["owner_only"] and not user.is_owner:
                continue
            feature_key = config["feature_key"]
            navigation[module_key] = {
                "label": config["label"],
                "color": config["color"],
                "is_enabled": toggle_values.get(feature_key, True) if config["owner_only"] else True,
            }
        return navigation

    def _authorize(self, user: AuthenticatedUser, module_key: str) -> None:
        config = _MODULES[module_key]
        if config["owner_only"] and not user.is_owner:
            raise ForbiddenModuleError("您沒有權限查看此頁面")
        item = self.navigation(user).get(module_key)
        if item is not None and not item["is_enabled"]:
            raise FeatureDisabledError("請先把功能打開才能使用喔")

    def _has_user_data(self, table: str, user_id: int) -> bool:
        return self._db.select(
            table,
            columns=("id",),
            where="user_id = %s",
            params=(user_id,),
            fetch_one=True,
        ) is not None

    def _has_data(self, table: str) -> bool:
        return self._db.select(table, columns=("id",), fetch_one=True) is not None

    def dashboard(self, user: AuthenticatedUser, *, today: date | None = None) -> dict[str, Any]:
        target_date = today or datetime.now(_TAIWAN_TZ).date()
        navigation = self.navigation(user)
        rows = self._db.execute_query(
            """
            /* app_analytics:dashboard */
            SELECT
              (SELECT COUNT(*) FROM todos WHERE user_id = %s AND status = 'pending'
                AND DATE(due_at AT TIME ZONE 'Asia/Taipei') = %s) AS todo_count,
              (SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = %s
                AND type = 'expense' AND transaction_date = %s) AS expense_today,
              (SELECT COUNT(*) FROM transactions WHERE user_id = %s
                AND type = 'expense' AND transaction_date = %s) AS expense_count,
              (SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = %s
                AND type = 'income' AND transaction_date = %s) AS income_today,
              (SELECT COUNT(*) FROM transactions WHERE user_id = %s
                AND type = 'income' AND transaction_date = %s) AS income_count,
              (SELECT COALESCE(fat_g, 0) FROM diet_logs WHERE user_id = %s AND entry_date = %s AND entry_type = 'food' ORDER BY created_at DESC, id DESC LIMIT 1) AS fat_g,
              (SELECT COALESCE(protein_g, 0) FROM diet_logs WHERE user_id = %s AND entry_date = %s AND entry_type = 'food' ORDER BY created_at DESC, id DESC LIMIT 1) AS protein_g,
              (SELECT COALESCE(carbs_g, 0) FROM diet_logs WHERE user_id = %s AND entry_date = %s AND entry_type = 'food' ORDER BY created_at DESC, id DESC LIMIT 1) AS carbs_g,
              (SELECT COALESCE(estimated_calories, 0) FROM diet_logs WHERE user_id = %s AND entry_date = %s AND entry_type = 'food' ORDER BY created_at DESC, id DESC LIMIT 1) AS diet_calories,
              (SELECT CASE WHEN EXISTS (SELECT 1 FROM diet_logs WHERE user_id = %s AND entry_date = %s AND entry_type = 'food') THEN 1 ELSE 0 END) AS diet_count,
              (SELECT COALESCE(water_ml, 0) FROM diet_logs WHERE user_id = %s AND entry_date = %s AND entry_type = 'water' ORDER BY created_at DESC, id DESC LIMIT 1) AS water_ml,
              (SELECT COALESCE(SUM(estimated_calories), 0) FROM exercise_logs WHERE user_id = %s AND entry_date = %s) AS exercise_calories,
              (SELECT COUNT(*) FROM exercise_logs WHERE user_id = %s AND entry_date = %s) AS exercise_count,
              (SELECT STRING_AGG(DISTINCT activity, '、') FROM exercise_logs WHERE user_id = %s AND entry_date = %s) AS activities,
              (SELECT weight_kg FROM body_weight_logs WHERE user_id = %s ORDER BY entry_date DESC, created_at DESC LIMIT 1) AS latest_weight,
              (SELECT CASE WHEN EXISTS (SELECT 1 FROM body_weight_logs WHERE user_id = %s AND entry_date = %s) THEN 1 ELSE 0 END) AS weight_count,
              (SELECT mood_category FROM mood_journals WHERE user_id = %s AND entry_date = %s ORDER BY created_at DESC, id DESC LIMIT 1) AS latest_mood_category,
              (SELECT CASE WHEN EXISTS (SELECT 1 FROM mood_journals WHERE user_id = %s AND entry_date = %s) THEN 1 ELSE 0 END) AS mood_count
            """,
            (user.database_id, target_date) * 14
            + (user.database_id,)
            + (user.database_id, target_date) * 3,
        )
        summary = _json_row(rows[0]) if rows else {}
        return {
            "date": target_date.isoformat(),
            "navigation": navigation,
            "notifications": self._notifications_for_user(user, target_date),
            "important_days": self._important_day_summaries(user, target_date),
            "summary": summary,
        }

    def _important_day_summaries(self, user: AuthenticatedUser, target_date: date) -> list[str]:
        """回傳首頁使用的精簡重要日子列表，不沿用 Telegram 推播長文案。"""
        dated: list[tuple[date, str]] = []
        for item in AppImportantDayService(self._db).list_for_user(user.database_id, today=target_date):
            if not item["is_active"]:
                continue
            next_occurrence = item["next_occurrence"]
            if next_occurrence:
                dated.append((date.fromisoformat(next_occurrence), item["title"]))

        for entry in FIXED_NOTIFICATIONS:
            allowed_roles = entry["allowed_roles"]
            if allowed_roles is not None and user.role not in allowed_roles:
                continue
            event_date = entry["compute_date"](target_date.year)
            if event_date < target_date:
                event_date = entry["compute_date"](target_date.year + 1)
            dated.append((event_date, entry["calendar_summary"]))

        users = self._db.select(
            "users",
            columns=("id", "role", "birthday"),
            where="birthday IS NOT NULL",
        )
        for row in users:
            birthday = row.get("birthday")
            if not isinstance(birthday, date):
                continue
            try:
                event_date = birthday.replace(year=target_date.year)
            except ValueError:
                event_date = date(target_date.year, 2, 28)
            if event_date < target_date:
                try:
                    event_date = birthday.replace(year=target_date.year + 1)
                except ValueError:
                    event_date = date(target_date.year + 1, 2, 28)
            title = "我的生日" if row["id"] == user.database_id else f"{row['role']}生日"
            dated.append((event_date, title))

        messages: list[str] = []
        seen: set[tuple[date | None, str]] = set()
        week_start = target_date - timedelta(days=(target_date.weekday() + 1) % 7)
        week_end = week_start + timedelta(days=6)
        for event_date, title in sorted(dated, key=lambda item: (item[0], item[1])):
            if not week_start <= event_date <= week_end:
                continue
            key = (event_date, title)
            if key in seen:
                continue
            seen.add(key)
            days = (event_date - target_date).days
            prefix = "今天" if days == 0 else "3 天後" if days == 3 else "當周"
            messages.append(f"{prefix}：{title}")
        return messages

    def _notifications_for_user(self, user: AuthenticatedUser, target_date: date) -> list[str]:
        sent_rows = self._db.select(
            "important_notifications_log",
            columns=("notification_key",),
            where="year = %s AND DATE(sent_at AT TIME ZONE 'Asia/Taipei') = %s",
            params=(target_date.year, target_date),
        )
        sent_keys = {row["notification_key"] for row in sent_rows}
        messages: list[str] = []
        for entry in FIXED_NOTIFICATIONS:
            if entry["key"] not in sent_keys:
                continue
            allowed_roles = entry["allowed_roles"]
            if allowed_roles is not None and user.role not in allowed_roles:
                continue
            messages.append(
                entry["subject_message"]
                if entry["subject_role"] == user.role and entry["subject_message"]
                else entry["message"]
            )
        birthday_keys = [key for key in sent_keys if key.startswith("birthday_")]
        if birthday_keys:
            users = self._db.select("users", columns=("id", "role"), where="birthday IS NOT NULL")
            roles = {f"birthday_{row['id']}": row["role"] for row in users}
            for key in birthday_keys:
                birthday_id = int(key.removeprefix("birthday_"))
                if birthday_id == user.database_id:
                    messages.append("🎂 生日快樂！今天是你的生日，祝你新的一歲順心如意！")
                elif key in roles:
                    messages.append(f"🎂 提醒你，今天是 {roles[key]} 的生日，記得跟他/她說聲生日快樂！")
        return messages

    def _calendar_days_for_user(
        self,
        user: AuthenticatedUser,
        start: date,
        end: date,
    ) -> dict[str, dict[str, Any]]:
        """合併政府行事曆與使用者可見的重要通知日期。"""
        calendar_days = self._calendar.days(start, end)
        for year in range(start.year, end.year + 1):
            for entry in FIXED_NOTIFICATIONS:
                allowed_roles = entry["allowed_roles"]
                if allowed_roles is not None and user.role not in allowed_roles:
                    continue
                notification_date = entry["compute_date"](year)
                if start <= notification_date <= end:
                    day = calendar_days.setdefault(
                        notification_date.isoformat(),
                        {
                            "name": None,
                            "is_holiday": False,
                            "holiday_category": None,
                            "description": None,
                        },
                    )
                    notifications = day.setdefault("important_notifications", [])
                    summary = entry["calendar_summary"]
                    if summary not in notifications and not _matches_calendar_name(day, summary):
                        notifications.append(summary)

        users = self._db.select(
            "users",
            columns=("id", "role", "birthday"),
            where="birthday IS NOT NULL",
        )
        for row in users:
            birthday = row.get("birthday")
            if not isinstance(birthday, date):
                continue
            for year in range(start.year, end.year + 1):
                try:
                    notification_date = birthday.replace(year=year)
                except ValueError:
                    continue
                if start <= notification_date <= end:
                    day = calendar_days.setdefault(
                        notification_date.isoformat(),
                        {
                            "name": None,
                            "is_holiday": False,
                            "holiday_category": None,
                            "description": None,
                        },
                    )
                    notifications = day.setdefault("important_notifications", [])
                    summary = "我的生日" if row["id"] == user.database_id else f"{row['role']}生日"
                    if summary not in notifications and not _matches_calendar_name(day, summary):
                        notifications.append(summary)
        custom_events = AppImportantDayService(self._db).calendar_events(user.database_id, start, end)
        for event_date, titles in custom_events.items():
            day = calendar_days.setdefault(
                event_date,
                {
                    "name": None,
                    "is_holiday": False,
                    "holiday_category": None,
                    "description": None,
                },
            )
            notifications = day.setdefault("important_notifications", [])
            for title in titles:
                if title not in notifications and not _matches_calendar_name(day, title):
                    notifications.append(title)
        return calendar_days

    def todos(
        self,
        user: AuthenticatedUser,
        start: date,
        end: date,
        *,
        calendar_start: date,
        calendar_end: date,
    ) -> dict[str, Any]:
        self._authorize(user, "todos")
        rows = self._db.execute_query(
            """/* app_analytics:todos */ SELECT id, content, due_at, start_at, status, created_at
            FROM todos WHERE user_id = %s
              AND status = 'pending'
              AND DATE(due_at AT TIME ZONE 'Asia/Taipei') >= %s
              AND DATE(COALESCE(start_at, due_at) AT TIME ZONE 'Asia/Taipei') <= %s
              AND DATE(due_at AT TIME ZONE 'Asia/Taipei') >= %s
            ORDER BY due_at""",
            (user.database_id, self._today, end, start),
        )
        overdue_rows = self._db.execute_query(
            """/* app_analytics:todos_overdue */ SELECT id, content, due_at, start_at, status, created_at
            FROM todos WHERE user_id = %s AND status = 'pending'
              AND DATE(due_at AT TIME ZONE 'Asia/Taipei') < %s
            ORDER BY due_at DESC, created_at DESC, id DESC""",
            (user.database_id, self._today),
        )
        count_rows = self._db.execute_query(
            """/* app_analytics:todo_calendar_counts */
            SELECT day::date AS day, COUNT(*) AS count
            FROM todos t
            CROSS JOIN LATERAL GENERATE_SERIES(
              DATE(COALESCE(t.start_at, t.due_at) AT TIME ZONE 'Asia/Taipei'),
              DATE(t.due_at AT TIME ZONE 'Asia/Taipei'), INTERVAL '1 day'
            ) AS day
            WHERE t.user_id = %s AND t.status = 'pending' AND day::date BETWEEN %s AND %s
            GROUP BY day::date ORDER BY day::date""",
            (user.database_id, calendar_start, calendar_end),
        )
        calendar_counts = {str(_json_value(row["day"])): int(row["count"]) for row in count_rows}
        return {
            "has_any_data": self._has_user_data("todos", user.database_id),
            "items": [{**_json_row(row), "can_edit": True} for row in rows],
            "overdue_items": [{**_json_row(row), "can_edit": True} for row in overdue_rows],
            "overdue_count": len(overdue_rows),
            "calendar_counts": calendar_counts,
            "calendar_days": self._calendar_days_for_user(
                user,
                min(start, calendar_start),
                max(end, calendar_end),
            ),
        }

    def finance(self, user: AuthenticatedUser, start: date, end: date) -> dict[str, Any]:
        self._authorize(user, "finance")
        daily_rows = self._db.execute_query(
            """/* app_analytics:finance_daily */ SELECT transaction_date AS day, type, SUM(amount) AS amount
            FROM transactions WHERE user_id = %s AND transaction_date BETWEEN %s AND %s
            GROUP BY transaction_date, type ORDER BY transaction_date""",
            (user.database_id, start, end),
        )
        by_day: dict[str, dict[str, Any]] = {}
        for row in daily_rows:
            day = _json_value(row["day"])
            point = by_day.setdefault(day, {"date": day, "expense": 0.0, "income": 0.0})
            point[row["type"]] = float(row["amount"] or 0)
        category_rows = self._db.execute_query(
            """/* app_analytics:finance_categories */ SELECT category, SUM(amount) AS amount
            FROM transactions WHERE user_id = %s AND type = 'expense' AND transaction_date BETWEEN %s AND %s
            GROUP BY category ORDER BY amount DESC""",
            (user.database_id, start, end),
        )
        categories = [{"label": row["category"], "value": float(row["amount"])} for row in category_rows]
        records = self._db.execute_query(
            """/* app_analytics:finance_records */ SELECT id, type, category, amount, note,
            transaction_date AS date, created_at FROM transactions
            WHERE user_id = %s AND transaction_date BETWEEN %s AND %s
            ORDER BY transaction_date DESC, created_at DESC, id DESC""",
            (user.database_id, start, end),
        )
        latest_rows = self._db.execute_query(
            """/* app_analytics:finance_latest */ SELECT id, type, category, amount, note,
            transaction_date AS date, created_at FROM transactions
            WHERE user_id = %s ORDER BY transaction_date DESC, created_at DESC, id DESC LIMIT 1""",
            (user.database_id,),
        )
        goal_rows = self._db.execute_query(
            """/* app_analytics:finance_goals */ SELECT g.id, g.module_key, g.target_description,
            g.target_value, g.target_unit, g.baseline_value, g.target_date, g.status,
            g.created_at, g.updated_at, g.completed_at,
            CASE WHEN g.target_value IS NULL THEN NULL ELSE COALESCE((
              SELECT SUM(CASE WHEN t.type = 'income' THEN t.amount ELSE -t.amount END)
              FROM transactions t WHERE t.user_id = g.user_id
                AND t.transaction_date >= DATE(g.created_at AT TIME ZONE 'Asia/Taipei')
            ), 0) END AS current_value
            FROM module_goals g WHERE g.user_id = %s AND g.module_key = 'finance'
            ORDER BY g.updated_at DESC, g.id DESC""",
            (user.database_id,),
        )
        daily = list(by_day.values())
        goals = [self._normalized_goal(row) for row in goal_rows]
        latest_record = None
        if latest_rows:
            latest_record = {
                **_json_row(latest_rows[0]),
                "can_edit": latest_rows[0]["date"] == self._today,
            }
        return {
            "has_any_data": self._has_user_data("transactions", user.database_id),
            "daily": daily,
            "expense_categories": categories,
            "expense_total": sum(point["expense"] for point in daily),
            "income_total": sum(point["income"] for point in daily),
            "records": [{**_json_row(row), "can_edit": row["date"] == self._today} for row in records],
            "latest_record": latest_record,
            "goals": goals,
            "goal_summary": self._goal_summary(goals),
        }

    def body(self, user: AuthenticatedUser, start: date, end: date) -> dict[str, Any]:
        self._authorize(user, "body")
        weight_rows = self._db.execute_query(
            """/* app_analytics:body_weight */ SELECT DISTINCT ON (w.entry_date)
                w.entry_date AS day, w.weight_kg, w.waist_cm, u.height_cm
            FROM body_weight_logs w JOIN users u ON u.id = w.user_id
            WHERE w.user_id = %s AND w.entry_date BETWEEN %s AND %s
            ORDER BY w.entry_date, w.created_at DESC, w.id DESC""",
            (user.database_id, start, end),
        )
        weight = []
        for row in weight_rows:
            value = float(row["weight_kg"])
            height = float(row["height_cm"]) if row.get("height_cm") else None
            weight.append(
                {
                    "date": _json_value(row["day"]),
                    "weight": value,
                    "waist": float(row["waist_cm"]) if row.get("waist_cm") is not None else None,
                    "bmi": round(value / ((height / 100) ** 2), 2) if height else None,
                }
            )
        diet = []
        for row in self._db.execute_query(
            """/* app_analytics:body_diet */ SELECT entry_date AS date,
            COALESCE(MAX(water_ml) FILTER (WHERE entry_type = 'water'), 0) AS water_ml,
            COUNT(*) FILTER (WHERE entry_type = 'food' AND nutrition_source = 'ai') AS ai_count,
            COUNT(*) FILTER (WHERE entry_type = 'food' AND nutrition_source = 'manual') AS manual_count,
            COALESCE(SUM(fat_g) FILTER (WHERE entry_type = 'food' AND nutrition_source = 'ai'), 0) AS ai_fat_g,
            COALESCE(SUM(fat_g) FILTER (WHERE entry_type = 'food' AND nutrition_source = 'manual'), 0) AS manual_fat_g,
            COALESCE(SUM(protein_g) FILTER (WHERE entry_type = 'food' AND nutrition_source = 'ai'), 0) AS ai_protein_g,
            COALESCE(SUM(protein_g) FILTER (WHERE entry_type = 'food' AND nutrition_source = 'manual'), 0) AS manual_protein_g,
            COALESCE(SUM(carbs_g) FILTER (WHERE entry_type = 'food' AND nutrition_source = 'ai'), 0) AS ai_carbs_g,
            COALESCE(SUM(carbs_g) FILTER (WHERE entry_type = 'food' AND nutrition_source = 'manual'), 0) AS manual_carbs_g,
            COALESCE(SUM(estimated_calories) FILTER (WHERE entry_type = 'food' AND nutrition_source = 'ai'), 0) AS ai_calories,
            COALESCE(SUM(estimated_calories) FILTER (WHERE entry_type = 'food' AND nutrition_source = 'manual'), 0) AS manual_calories
            FROM diet_logs WHERE user_id = %s AND entry_date BETWEEN %s AND %s
            GROUP BY entry_date ORDER BY entry_date""",
            (user.database_id, start, end),
        ):
            item = _json_row(row)
            for nutrient in ("fat_g", "protein_g", "carbs_g", "calories"):
                item[f"total_{nutrient}"] = item[f"ai_{nutrient}"] + item[f"manual_{nutrient}"]
            diet.append(item)
        exercise = []
        for row in self._db.execute_query(
            """/* app_analytics:body_exercise */ SELECT entry_date AS date,
            COUNT(*) FILTER (WHERE calorie_source = 'ai') AS ai_count,
            COUNT(*) FILTER (WHERE calorie_source = 'manual') AS manual_count,
            COALESCE(SUM(estimated_calories) FILTER (WHERE calorie_source = 'ai'), 0) AS ai_calories,
            COALESCE(SUM(estimated_calories) FILTER (WHERE calorie_source = 'manual'), 0) AS manual_calories,
            COALESCE(SUM(duration_minutes), 0) AS minutes
            FROM exercise_logs WHERE user_id = %s AND entry_date BETWEEN %s AND %s
            GROUP BY entry_date ORDER BY entry_date""",
            (user.database_id, start, end),
        ):
            item = _json_row(row)
            item["total_calories"] = item["ai_calories"] + item["manual_calories"]
            exercise.append(item)
        latest_body_rows = self._db.execute_query(
            """/* app_analytics:body_latest */ SELECT w.*, u.height_cm
            FROM body_weight_logs w JOIN users u ON u.id = w.user_id
            WHERE w.user_id = %s
            ORDER BY w.entry_date DESC, w.created_at DESC, w.id DESC LIMIT 1""",
            (user.database_id,),
        )
        latest_body_record = None
        if latest_body_rows:
            latest_row = latest_body_rows[0]
            latest_weight = float(latest_row["weight_kg"])
            latest_height = float(latest_row["height_cm"]) if latest_row.get("height_cm") else None
            latest_body_record = {
                **_json_row(latest_row),
                "bmi": round(latest_weight / ((latest_height / 100) ** 2), 2) if latest_height else None,
                "can_edit": latest_row["entry_date"] == datetime.now(_TAIWAN_TZ).date(),
            }
        user_row = self._db.select(
            "users",
            columns=("height_cm",),
            where="id = %s",
            params=(user.database_id,),
            fetch_one=True,
        ) or {}
        weight_records = self._record_rows("body_weight_logs", "weight", user.database_id, start, end)
        diet_records = self._diet_record_rows(user.database_id, start, end)
        exercise_records = self._record_rows("exercise_logs", "exercise", user.database_id, start, end)
        latest_diet_records = self._diet_record_rows(user.database_id, date.min, date.max)
        latest_exercise_records = self._record_rows("exercise_logs", "exercise", user.database_id, date.min, date.max)
        goal_rows = self._db.execute_query(
            """/* app_analytics:body_goals */ SELECT g.id, g.goal_type, g.target_description,
            g.target_value, g.target_unit, g.baseline_value, g.target_date, g.status,
            g.progress_type, g.created_at, g.updated_at, g.completed_at,
            CASE
              WHEN g.goal_type = 'weight' THEN (SELECT w.weight_kg FROM body_weight_logs w
                WHERE w.user_id = g.user_id ORDER BY w.entry_date DESC, w.created_at DESC, w.id DESC LIMIT 1)
              WHEN g.goal_type = 'exercise' AND g.progress_type = 'numeric' THEN COALESCE((
                SELECT SUM(e.duration_minutes) FROM exercise_logs e WHERE e.user_id = g.user_id
                  AND e.entry_date >= DATE(g.created_at AT TIME ZONE 'Asia/Taipei')), 0)
              WHEN g.goal_type = 'diet' AND g.target_direction = 'min' THEN COALESCE((
                SELECT SUM(d.estimated_calories) FROM diet_logs d WHERE d.user_id = g.user_id
                  AND d.entry_type = 'food' AND d.entry_date >= DATE(g.created_at AT TIME ZONE 'Asia/Taipei')), 0)
              ELSE NULL
            END AS current_value,
            CASE
              WHEN g.goal_type = 'weight' THEN 'improvement'
              WHEN g.progress_type = 'milestone' THEN 'milestone'
              WHEN g.target_value IS NOT NULL AND (g.goal_type != 'diet' OR g.target_direction = 'min') THEN 'cumulative'
              ELSE 'unquantified'
            END AS progress_mode
            FROM body_goals g WHERE g.user_id = %s ORDER BY g.updated_at DESC, g.id DESC""",
            (user.database_id,),
        )
        goals = [self._normalized_goal(row) for row in goal_rows]
        return {
            "has_any_data": any(
                self._has_user_data(table, user.database_id)
                for table in ("body_weight_logs", "diet_logs", "exercise_logs")
            ),
            "weight": weight,
            "diet": diet,
            "exercise": exercise,
            "goals": goals,
            "goal_summary": self._goal_summary(goals),
            "body_defaults": {
                "height_cm": _json_value(user_row.get("height_cm")),
                "weight_kg": latest_body_record.get("weight_kg") if latest_body_record else None,
                "waist_cm": latest_body_record.get("waist_cm") if latest_body_record else None,
            },
            "latest_body_record": latest_body_record,
            "latest_records": {
                "weight": latest_body_record,
                "diet": latest_diet_records[0] if latest_diet_records else None,
                "exercise": latest_exercise_records[0] if latest_exercise_records else None,
            },
            "weight_records": weight_records,
            "diet_records": diet_records,
            "exercise_records": exercise_records,
        }

    def _record_rows(self, table: str, marker: str, user_id: int, start: date, end: date) -> list[dict[str, Any]]:
        rows = self._db.execute_query(
            f"""/* app_analytics:{marker}_records */ SELECT * FROM {table}
            WHERE user_id = %s AND entry_date BETWEEN %s AND %s
            ORDER BY entry_date DESC, created_at DESC, id DESC""",
            (user_id, start, end),
        )
        today = datetime.now(_TAIWAN_TZ).date()
        single_daily = table in {"body_weight_logs", "diet_logs"}
        latest_today_id = next((row["id"] for row in rows if row["entry_date"] == today), None)
        return [
            {
                **_json_row(row),
                "can_edit": row["entry_date"] == today
                and (not single_daily or row["id"] == latest_today_id),
            }
            for row in rows
        ]

    def _diet_record_rows(self, user_id: int, start: date, end: date) -> list[dict[str, Any]]:
        rows = self._db.execute_query(
            """/* app_analytics:diet_records */ SELECT food.*,
            water.water_ml
            FROM diet_logs food
            LEFT JOIN LATERAL (
              SELECT water_ml FROM diet_logs
              WHERE user_id = food.user_id AND entry_date = food.entry_date AND entry_type = 'water'
              ORDER BY created_at DESC, id DESC LIMIT 1
            ) water ON TRUE
            WHERE food.user_id = %s AND food.entry_date BETWEEN %s AND %s AND food.entry_type = 'food'
            ORDER BY food.entry_date DESC, food.created_at DESC, food.id DESC""",
            (user_id, start, end),
        )
        today = datetime.now(_TAIWAN_TZ).date()
        latest_today_id = next((row["id"] for row in rows if row["entry_date"] == today), None)
        return [
            {
                **_json_row(row),
                "can_edit": row["entry_date"] == today and row["id"] == latest_today_id,
            }
            for row in rows
        ]

    def mood(self, user: AuthenticatedUser, start: date, end: date) -> dict[str, Any]:
        self._authorize(user, "mood")
        rows = self._db.execute_query(
            """/* app_analytics:mood */ SELECT DISTINCT ON (entry_date) id, entry_date AS date, mood_category, content, achievement_note, created_at
            FROM mood_journals WHERE user_id = %s AND entry_date BETWEEN %s AND %s
            ORDER BY entry_date DESC, created_at DESC, id DESC""",
            (user.database_id, start, end),
        )
        latest_rows = self._db.execute_query(
            """/* app_analytics:mood_latest */ SELECT id, entry_date AS date, mood_category,
            content, achievement_note, created_at FROM mood_journals WHERE user_id = %s
            ORDER BY entry_date DESC, created_at DESC, id DESC LIMIT 1""",
            (user.database_id,),
        )
        latest_record = None
        if latest_rows:
            latest_record = {
                **_json_row(latest_rows[0]),
                "can_edit": latest_rows[0]["date"] == self._today,
            }
        return {
            "has_any_data": self._has_user_data("mood_journals", user.database_id),
            "items": [{**_json_row(row), "can_edit": row["date"] == self._today} for row in rows],
            "latest_record": latest_record,
        }

    def jobs(self, user: AuthenticatedUser, start: date, end: date) -> dict[str, Any]:
        self._authorize(user, "jobs")
        postings = self._db.execute_query(
            """/* app_analytics:jobs_postings */ SELECT p.job_id_104, p.title,
            c.company_name, p.region, p.source, p.url, p.score AS match_score,
            p.recommend_reason, p.skill_gap_note, p.first_seen_at, p.is_closed
            FROM job_postings p JOIN job_companies c ON c.company_id_104 = p.company_id_104
            WHERE DATE(p.first_seen_at AT TIME ZONE 'Asia/Taipei') BETWEEN %s AND %s
            ORDER BY match_score DESC NULLS LAST""",
            (start, end),
        )
        timeline = self._db.execute_query(
            """/* app_analytics:jobs_timeline */ SELECT a.job_id_104, p.title, a.status, a.created_at
            FROM job_applications a JOIN job_postings p ON p.job_id_104 = a.job_id_104
            WHERE DATE(a.created_at AT TIME ZONE 'Asia/Taipei') BETWEEN %s AND %s ORDER BY a.created_at DESC""",
            (start, end),
        )
        latest_status: dict[str, str] = {}
        for row in timeline:
            latest_status[row["job_id_104"]] = row["status"]
        funnel = {key: 0 for key in ("applied", "interview", "offer", "rejected")}
        for status in latest_status.values():
            if status in funnel:
                funnel[status] += 1
        distribution = {"high": 0, "medium": 0, "low": 0}
        for row in postings:
            score = float(row["match_score"]) if row.get("match_score") is not None else None
            if score is None:
                continue
            distribution["high" if score >= 80 else "medium" if score >= 60 else "low"] += 1
        open_postings = [row for row in postings if not row.get("is_closed", False)]
        # 2026-08-24（見 docs/ADR/debug/job-search.md「推薦職缺不分青紅皂白」條目）：契合度
        # 評分尚未執行時 `match_score` 為 NULL，過去沒有門檻，未評分／低分職缺也會被硬塞進推薦
        # 清單。只有真正評過分、且分數達到 `_RECOMMENDATION_MIN_SCORE`（沿用上方 medium/high
        # 分界＝60）的職缺才算「推薦」；找不到合適職缺時回傳空陣列，由前端顯示對應文案。
        recommended_postings = [
            row for row in open_postings
            if row.get("match_score") is not None and float(row["match_score"]) >= _RECOMMENDATION_MIN_SCORE
        ]
        return {
            "has_any_data": self._has_data("job_postings"),
            "funnel": funnel,
            "score_distribution": distribution,
            "recommendations": [_json_row(row) for row in recommended_postings[:10]],
            "timeline": [_json_row(row) for row in timeline],
        }

    def exams(self, user: AuthenticatedUser, start: date, end: date) -> dict[str, Any]:
        self._authorize(user, "exams")
        profiles = self._db.execute_query(
            """/* app_analytics:exam_profiles */ SELECT certificate_key, display_name, is_active
            FROM certificate_profiles WHERE user_id = %s AND is_active = TRUE
            ORDER BY is_builtin DESC, display_name""",
            (user.database_id,),
        )
        question_types = self._db.execute_query(
            """/* app_analytics:exam_question_types */ SELECT DISTINCT lower(exam_type) AS exam_type
            FROM certificate_questions"""
        )
        goals = self._db.execute_query(
            """/* app_analytics:exam_goals */ SELECT id, exam_type, target_date, target_score,
            status, completed_at, updated_at
            FROM certificate_goals WHERE user_id = %s ORDER BY exam_type""",
            (user.database_id,),
        )
        best_scores = self._db.execute_query(
            """/* app_analytics:exam_best_scores */ SELECT exam_type, score
            FROM exam_official_scores WHERE user_id = %s ORDER BY exam_date DESC, created_at DESC""",
            (user.database_id,),
        )
        scores = self._db.execute_query(
            """/* app_analytics:exam_scores */ SELECT exam_type, exam_date, score, note
            FROM exam_official_scores WHERE user_id = %s AND exam_date BETWEEN %s AND %s
            ORDER BY exam_date DESC, created_at DESC""",
            (user.database_id, start, end),
        )
        practice = self._db.execute_query(
            """/* app_analytics:exam_practice */ SELECT answered_on AS date, exam_type, question_type,
            COUNT(*) AS total, SUM(CASE WHEN is_correct THEN 1 ELSE 0 END) AS correct
            FROM answer_logs WHERE user_id = %s AND answered_on BETWEEN %s AND %s
            GROUP BY answered_on, exam_type, question_type ORDER BY answered_on DESC""",
            (user.database_id, start, end),
        )
        question_bank_types = {str(row["exam_type"]).strip().lower() for row in question_types}
        certificates = [
            {
                "key": str(row["certificate_key"]).strip().lower(),
                "display_name": row["display_name"],
                "has_question_bank": str(row["certificate_key"]).strip().lower() in question_bank_types,
            }
            for row in profiles
        ]
        current_scores: dict[str, float] = {}
        for row in best_scores:
            key = str(row["exam_type"]).strip().lower()
            try:
                score = float(str(row["score"]).strip())
            except (TypeError, ValueError):
                continue
            current_scores[key] = max(current_scores.get(key, score), score)
        normalized_goals = []
        for row in goals:
            key = str(row["exam_type"]).strip().lower()
            try:
                target = float(str(row["target_score"]).strip())
            except (TypeError, ValueError):
                target = None
            normalized_goals.append(self._normalized_goal({
                **row,
                "goal_type": key,
                "target_description": f"{row['exam_type']} 目標 {row.get('target_score') or '未設定'}",
                "target_value": target,
                "current_value": current_scores.get(key),
                "target_unit": "分" if target is not None else None,
                "progress_mode": "cumulative",
            }))
        goal_summaries = {
            certificate["key"]: self._goal_summary([
                goal for goal in normalized_goals if str(goal["goal_type"]).lower() == certificate["key"]
            ])
            for certificate in certificates
        }
        return {
            "has_any_data": any(
                self._has_user_data(table, user.database_id)
                for table in ("certificate_goals", "exam_official_scores", "answer_logs")
            ),
            "certificates": certificates,
            "goals": normalized_goals,
            "goal_summaries": goal_summaries,
            "official_scores": [_json_row(row) for row in scores],
            "practice": [_json_row(row) for row in practice],
        }

    def skills(self, user: AuthenticatedUser, start: date, end: date) -> dict[str, Any]:
        self._authorize(user, "skills")
        digests = self._db.execute_query(
            """/* app_analytics:skill_digests */ SELECT digest_date, source, summary_text
            FROM skill_growth_digests WHERE digest_date BETWEEN %s AND %s ORDER BY digest_date DESC, source""",
            (start, end),
        )
        videos = self._db.execute_query(
            """/* app_analytics:skill_videos */ SELECT pushed_on, topic, title, recommend_reason
            FROM youtube_pushed_videos WHERE user_id = %s AND pushed_on BETWEEN %s AND %s
            ORDER BY pushed_on DESC""",
            (user.database_id, start, end),
        )
        return {
            "has_any_data": self._has_data("skill_growth_digests")
            or self._has_user_data("youtube_pushed_videos", user.database_id),
            "digests": [_json_row(row) for row in digests],
            "videos": [_json_row(row) for row in videos],
        }
