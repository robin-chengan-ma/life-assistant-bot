"""中華民國政府行政機關辦公日曆年度快取服務。"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date, timedelta
from typing import Any, Protocol
from urllib.request import urlopen

_LOGGER = logging.getLogger(__name__)
_OFFICIAL_CSV_URL = (
    "https://data.ntpc.gov.tw/api/datasets/308dcd75-6434-45bc-a95f-584da4fed251/csv/file"
)
_DISPLAY_ALIASES = {(12, 25): "聖誕節"}


class CalendarDatabase(Protocol):
    def execute(self, query: str, params: tuple | None = None) -> None: ...

    def execute_query(self, query: str, params: tuple | None = None) -> list[dict[str, Any]]: ...


def _display_name(day: date, official_name: str | None) -> str | None:
    names = [value for value in (official_name, _DISPLAY_ALIASES.get((day.month, day.day))) if value]
    return "／".join(dict.fromkeys(names)) or None


class TaiwanCalendarService:
    def __init__(self, db: CalendarDatabase, *, sync_missing: bool = False):
        self._db = db
        self._sync_missing = sync_missing

    def days(self, start: date, end: date) -> dict[str, dict[str, Any]]:
        try:
            rows = self._cached_days(start, end)
        except Exception:
            _LOGGER.warning("辦公日曆快取表尚未就緒，改用即時官方資料", exc_info=True)
            rows = []
        cached_years = {int(row["year"]) for row in rows}
        requested_years = set(range(start.year, end.year + 1))
        if self._sync_missing and requested_years - cached_years:
            downloaded_rows = self._download_years(requested_years - cached_years)
            if downloaded_rows:
                self._cache_rows(downloaded_rows)
                rows = [
                    row for row in downloaded_rows
                    if start <= row["calendar_date"] <= end
                ] or rows

        result = {
            str(row["calendar_date"]): {
                "name": _display_name(row["calendar_date"], row.get("name")),
                "is_holiday": bool(row["is_holiday"]),
                "holiday_category": row.get("holiday_category"),
                "description": row.get("description"),
            }
            for row in rows
        }
        cursor = start
        while cursor <= end:
            key = cursor.isoformat()
            if key not in result and cursor.weekday() >= 5:
                result[key] = {
                    "name": _display_name(cursor, None),
                    "is_holiday": True,
                    "holiday_category": "星期六、星期日",
                    "description": None,
                }
            cursor += timedelta(days=1)
        return result

    def _cached_days(self, start: date, end: date) -> list[dict[str, Any]]:
        return self._db.execute_query(
            """/* taiwan_calendar:cached_days */
            SELECT calendar_date, year, name, is_holiday, holiday_category, description
            FROM taiwan_calendar_days WHERE calendar_date BETWEEN %s AND %s ORDER BY calendar_date""",
            (start, end),
        )

    def _download_years(self, years: set[int]) -> list[dict[str, Any]]:
        try:
            with urlopen(_OFFICIAL_CSV_URL, timeout=12) as response:
                content = response.read().decode("utf-8-sig")
            rows = []
            for row in csv.DictReader(io.StringIO(content)):
                year = int(row["year"])
                if year not in years:
                    continue
                day = date.fromisoformat(f"{row['date'][:4]}-{row['date'][4:6]}-{row['date'][6:]}")
                rows.append(
                    {
                        "calendar_date": day,
                        "year": year,
                        "name": row["name"].strip() or None,
                        "is_holiday": row["isholiday"].strip() == "是",
                        "holiday_category": row["holidaycategory"].strip() or None,
                        "description": row["description"].strip() or None,
                    }
                )
            return rows
        except Exception:
            _LOGGER.warning("政府辦公日曆下載失敗，暫時只顯示可計算的週末假日", exc_info=True)
            return []

    def _cache_rows(self, rows: list[dict[str, Any]]) -> None:
        serialized_rows = [{**row, "calendar_date": row["calendar_date"].isoformat()} for row in rows]
        try:
            self._db.execute(
                """INSERT INTO taiwan_calendar_days
                (calendar_date, year, name, is_holiday, holiday_category, description)
                SELECT calendar_date::date, year, name, is_holiday, holiday_category, description
                FROM json_to_recordset(%s::json) AS source(
                    calendar_date text, year integer, name text, is_holiday boolean,
                    holiday_category text, description text
                )
                ON CONFLICT (calendar_date) DO UPDATE SET
                    year = EXCLUDED.year,
                    name = EXCLUDED.name,
                    is_holiday = EXCLUDED.is_holiday,
                    holiday_category = EXCLUDED.holiday_category,
                    description = EXCLUDED.description,
                    source_updated_at = NOW()""",
                (json.dumps(serialized_rows, ensure_ascii=False),),
            )
        except Exception:
            _LOGGER.warning("政府辦公日曆已下載但暫時無法寫入快取表", exc_info=True)
