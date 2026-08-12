"""Mobile App 重要日子設定、權限與行事曆整合服務。"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Protocol
from zoneinfo import ZoneInfo

_RECURRENCE_TYPES = {"fixed_annual", "flexible_annual", "one_time"}
_AUDIENCE_MODES = {"self", "specific", "all"}
_TAIWAN_TZ = ZoneInfo("Asia/Taipei")


class ImportantDaysDatabase(Protocol):
    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False): ...
    def insert(self, table, data, returning="id"): ...
    def update(self, table, data, where, params): ...
    def delete(self, table, where, params): ...
    def execute_query(self, query, params=None): ...


class ImportantDayError(Exception):
    """重要日子可預期錯誤。"""


class ImportantDayValidationError(ImportantDayError):
    """欄位不符合規則。"""


class ImportantDayNotFoundError(ImportantDayError):
    """事件不存在或不屬於目前使用者。"""


def _parse_date(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise ImportantDayValidationError(f"請選擇{label}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ImportantDayValidationError(f"{label}格式不正確") from exc


def _parse_time(value: Any, is_all_day: bool) -> time | None:
    if is_all_day:
        return None
    if not isinstance(value, str):
        raise ImportantDayValidationError("請選擇事件時間")
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ImportantDayValidationError("事件時間格式不正確") from exc


class AppImportantDayService:
    def __init__(self, db: ImportantDaysDatabase):
        self._db = db

    def family_users(self) -> list[dict[str, Any]]:
        rows = self._db.select("users", columns=("id", "role", "app_user_id"))
        return [{"id": row["id"], "role": row["role"], "user_id": row["app_user_id"]} for row in rows]

    def list_for_user(self, user_id: int, *, today: date | None = None) -> list[dict[str, Any]]:
        current = today or datetime.now(_TAIWAN_TZ).date()
        rows = self._db.execute_query(
            """/* app_important_days:list */
            SELECT d.*,
              COALESCE(ARRAY_AGG(DISTINCT r.user_id) FILTER (WHERE r.user_id IS NOT NULL), '{}') AS recipient_ids,
              o.occurrence_date AS current_year_date,
              o.occurrence_end_date AS current_year_end_date
            FROM important_days d
            LEFT JOIN important_day_recipients r ON r.important_day_id = d.id
            LEFT JOIN important_day_occurrences o ON o.important_day_id = d.id AND o.occurrence_year = %s
            WHERE d.owner_user_id = %s OR d.audience_mode = 'all'
              OR EXISTS (SELECT 1 FROM important_day_recipients visible
                         WHERE visible.important_day_id = d.id AND visible.user_id = %s)
            GROUP BY d.id, o.occurrence_date, o.occurrence_end_date
            ORDER BY d.is_active DESC, d.updated_at DESC, d.id DESC""",
            (current.year, user_id, user_id),
        )
        items = [self._serialize(row, user_id, current) for row in rows]
        return sorted(
            items,
            key=lambda item: (
                not item["is_active"],
                item["next_occurrence"] is None,
                item["next_occurrence"] or "9999-12-31",
                item["title"],
            ),
        )

    def create(self, owner_user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        data, occurrence_date, occurrence_end_date, recipient_ids = self._validate(payload, owner_user_id)
        important_day_id = self._db.insert("important_days", {"owner_user_id": owner_user_id, **data})
        self._replace_related(important_day_id, data["recurrence_type"], occurrence_date, occurrence_end_date, recipient_ids)
        return {"id": important_day_id, "message": "重要日子已新增"}

    def update(self, important_day_id: int, owner_user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._owned(important_day_id, owner_user_id)
        data, occurrence_date, occurrence_end_date, recipient_ids = self._validate(payload, owner_user_id)
        self._db.update(
            "important_days",
            {**data, "updated_at": datetime.now(_TAIWAN_TZ)},
            where="id = %s AND owner_user_id = %s",
            params=(important_day_id, owner_user_id),
        )
        self._replace_related(important_day_id, data["recurrence_type"], occurrence_date, occurrence_end_date, recipient_ids)
        return {"id": important_day_id, "message": "重要日子已更新"}

    def delete(self, important_day_id: int, owner_user_id: int) -> dict[str, str]:
        self._owned(important_day_id, owner_user_id)
        self._db.delete("important_days", where="id = %s AND owner_user_id = %s", params=(important_day_id, owner_user_id))
        return {"message": "重要日子已刪除"}

    def calendar_events(self, user_id: int, start: date, end: date) -> dict[str, list[str]]:
        rows = self.list_for_user(user_id, today=start)
        result: dict[str, list[str]] = {}
        for row in rows:
            if not row["is_active"] or not row["show_on_todo_calendar"]:
                continue
            if row["recurrence_type"] == "fixed_annual":
                for year in range(start.year, end.year + 1):
                    try:
                        event_date = date(year, row["event_month"], row["event_day"])
                    except ValueError:
                        continue
                    event_end = date(year, row.get("event_end_month") or row["event_month"], row.get("event_end_day") or row["event_day"])
                    for day in self._date_span(max(start, event_date), min(end, event_end)):
                        result.setdefault(day.isoformat(), []).append(row["title"])
            else:
                start_value = row["event_date"] if row["recurrence_type"] == "one_time" else row["current_year_date"]
                end_value = row.get("event_end_date") if row["recurrence_type"] == "one_time" else row.get("current_year_end_date")
                if start_value:
                    event_start = date.fromisoformat(start_value)
                    event_end = date.fromisoformat(end_value or start_value)
                    for day in self._date_span(max(start, event_start), min(end, event_end)):
                        result.setdefault(day.isoformat(), []).append(row["title"])
        return result

    def _owned(self, important_day_id: int, owner_user_id: int) -> dict[str, Any]:
        row = self._db.select(
            "important_days",
            where="id = %s AND owner_user_id = %s",
            params=(important_day_id, owner_user_id),
            fetch_one=True,
        )
        if row is None:
            raise ImportantDayNotFoundError("找不到指定的重要日子")
        return row

    def _validate(self, payload: dict[str, Any], owner_user_id: int) -> tuple[dict[str, Any], date | None, date | None, list[int]]:
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ImportantDayValidationError("請輸入重要日子名稱")
        if len(title.strip()) > 100:
            raise ImportantDayValidationError("重要日子名稱不可超過 100 個字元")
        recurrence_type = payload.get("recurrence_type")
        if recurrence_type not in _RECURRENCE_TYPES:
            raise ImportantDayValidationError("請選擇正確的重複方式")
        audience_mode = payload.get("audience_mode", "self")
        if audience_mode not in _AUDIENCE_MODES:
            raise ImportantDayValidationError("請選擇正確的通知對象")
        is_all_day = payload.get("is_all_day", True)
        if not isinstance(is_all_day, bool):
            raise ImportantDayValidationError("全天設定格式不正確")
        reminder_days = payload.get("reminder_days_before", 0)
        if isinstance(reminder_days, bool) or not isinstance(reminder_days, int) or not 0 <= reminder_days <= 365:
            raise ImportantDayValidationError("提前提醒天數必須介於 0 到 365 天")
        notes = payload.get("notes")
        if notes is not None and (not isinstance(notes, str) or len(notes) > 1000):
            raise ImportantDayValidationError("備註不可超過 1000 個字元")

        event_date = None
        event_month = None
        event_day = None
        event_end_date = None
        event_end_month = None
        event_end_day = None
        occurrence_date = None
        occurrence_end_date = None
        if recurrence_type == "fixed_annual":
            fixed_date = _parse_date(payload.get("event_date"), "日期")
            fixed_end = _parse_date(payload.get("event_end_date", payload.get("event_date")), "結束日期")
            if fixed_end.year != fixed_date.year or fixed_end < fixed_date:
                raise ImportantDayValidationError("每年固定日期區間不可跨年，且結束日期不可早於開始日期")
            event_month, event_day = fixed_date.month, fixed_date.day
            event_end_month, event_end_day = fixed_end.month, fixed_end.day
        elif recurrence_type == "one_time":
            event_date = _parse_date(payload.get("event_date"), "日期")
            event_end_date = _parse_date(payload.get("event_end_date", payload.get("event_date")), "結束日期")
            if event_end_date < event_date:
                raise ImportantDayValidationError("結束日期不可早於開始日期")
        else:
            occurrence_value = payload.get("occurrence_date")
            occurrence_date = _parse_date(occurrence_value, "日期") if occurrence_value else None
            occurrence_end_value = payload.get("occurrence_end_date", occurrence_value)
            occurrence_end_date = _parse_date(occurrence_end_value, "結束日期") if occurrence_end_value else None
            if occurrence_date and occurrence_end_date and occurrence_end_date < occurrence_date:
                raise ImportantDayValidationError("結束日期不可早於開始日期")

        recipient_values = payload.get("recipient_ids", [])
        if not isinstance(recipient_values, list) or any(isinstance(value, bool) or not isinstance(value, int) for value in recipient_values):
            raise ImportantDayValidationError("通知對象格式不正確")
        recipient_ids = sorted(set(recipient_values)) if audience_mode == "specific" else []
        if audience_mode == "specific" and not recipient_ids:
            raise ImportantDayValidationError("請至少選擇一位通知對象")
        if audience_mode == "self":
            recipient_ids = [owner_user_id]

        return {
            "title": title.strip(), "recurrence_type": recurrence_type, "event_date": event_date,
            "event_month": event_month, "event_day": event_day,
            "event_end_date": event_end_date, "event_end_month": event_end_month, "event_end_day": event_end_day,
            "event_time": _parse_time(payload.get("event_time"), is_all_day), "is_all_day": is_all_day,
            "reminder_days_before": reminder_days, "notes": notes.strip() if isinstance(notes, str) and notes.strip() else None,
            "audience_mode": audience_mode, "show_on_todo_calendar": bool(payload.get("show_on_todo_calendar", True)),
            "is_active": bool(payload.get("is_active", True)),
        }, occurrence_date, occurrence_end_date, recipient_ids

    def _replace_related(self, important_day_id: int, recurrence_type: str, occurrence_date: date | None, occurrence_end_date: date | None, recipient_ids: list[int]) -> None:
        self._db.delete("important_day_recipients", where="important_day_id = %s", params=(important_day_id,))
        for recipient_id in recipient_ids:
            self._db.insert("important_day_recipients", {"important_day_id": important_day_id, "user_id": recipient_id}, returning="user_id")
        self._db.delete("important_day_occurrences", where="important_day_id = %s", params=(important_day_id,))
        if recurrence_type == "flexible_annual" and occurrence_date is not None:
            self._db.insert("important_day_occurrences", {
                "important_day_id": important_day_id,
                "occurrence_year": occurrence_date.year,
                "occurrence_date": occurrence_date,
                "occurrence_end_date": occurrence_end_date or occurrence_date,
            })

    @staticmethod
    def _serialize(row: dict[str, Any], user_id: int, today: date) -> dict[str, Any]:
        result = dict(row)
        result["can_edit"] = row["owner_user_id"] == user_id
        for field in ("event_date", "event_end_date", "current_year_date", "current_year_end_date"):
            if isinstance(result.get(field), date):
                result[field] = result[field].isoformat()
        if isinstance(result.get("event_time"), time):
            result["event_time"] = result["event_time"].strftime("%H:%M")
        result["recipient_ids"] = list(result.get("recipient_ids") or [])
        result["current_year"] = today.year
        result["next_occurrence"] = AppImportantDayService._next_occurrence(result, today)
        return result

    @staticmethod
    def _date_span(start: date, end: date):
        current = start
        while current <= end:
            yield current
            current = date.fromordinal(current.toordinal() + 1)

    @staticmethod
    def _next_occurrence(item: dict[str, Any], today: date) -> str | None:
        if item["recurrence_type"] == "one_time":
            value = item.get("event_date")
            end_value = item.get("event_end_date") or value
            if value and end_value and date.fromisoformat(end_value) >= today:
                return max(date.fromisoformat(value), today).isoformat()
            return None
        if item["recurrence_type"] == "flexible_annual":
            value = item.get("current_year_date")
            end_value = item.get("current_year_end_date") or value
            if value and end_value and date.fromisoformat(end_value) >= today:
                return max(date.fromisoformat(value), today).isoformat()
            return None
        for year in (today.year, today.year + 1, today.year + 2):
            try:
                candidate = date(year, item["event_month"], item["event_day"])
            except ValueError:
                continue
            end_candidate = date(
                year,
                item.get("event_end_month") or item["event_month"],
                item.get("event_end_day") or item["event_day"],
            )
            if candidate <= today <= end_candidate:
                return today.isoformat()
            if candidate >= today:
                return candidate.isoformat()
        return None
