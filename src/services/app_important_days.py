"""Mobile App 生日設定服務。

2026-11（功能大幅精簡，Robin 明確決策）：「重要日子」改名為「生日設定」，拿掉單次事件、浮動
（農曆）日期、通知對象、備註、跟行程或目標連動等舊概念，只剩下「誰的生日、國曆幾月幾號」。
欄位假設見 `src/bot/important_days.py` 檔頭與 migration 0103。
"""

from __future__ import annotations

from typing import Any, Protocol


class ImportantDaysDatabase(Protocol):
    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False): ...
    def insert(self, table, data, returning="id"): ...
    def update(self, table, data, where, params): ...
    def delete(self, table, where, params): ...


class ImportantDayError(Exception):
    """生日設定可預期錯誤。"""


class ImportantDayValidationError(ImportantDayError):
    """欄位不符合規則。"""


class ImportantDayNotFoundError(ImportantDayError):
    """事件不存在或不屬於目前使用者。"""


def _parse_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImportantDayValidationError("請輸入姓名")
    name = value.strip()
    if len(name) > 100:
        raise ImportantDayValidationError("姓名不可超過 100 個字元")
    return name


def _parse_month(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 12:
        raise ImportantDayValidationError("請選擇正確的月份")
    return value


def _parse_day(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 31:
        raise ImportantDayValidationError("請選擇正確的日期")
    return value


class AppImportantDayService:
    def __init__(self, db: ImportantDaysDatabase):
        self._db = db

    def family_users(self) -> list[dict[str, Any]]:
        rows = self._db.select("users", columns=("id", "role"))
        return [
            {
                "id": row["id"],
                "role": row["role"],
                "user_id": f"user{row['id']:02d}",
            }
            for row in rows
        ]

    def list_for_user(self, user_id: int) -> list[dict[str, Any]]:
        rows = self._db.select("important_days", where="user_id = %s", params=(user_id,))
        items = [self._serialize(row, user_id) for row in rows]
        return sorted(items, key=lambda item: (item["birth_month"], item["birth_day"], item["name"]))

    def create(self, owner_user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._validate(payload)
        important_day_id = self._db.insert("important_days", {"user_id": owner_user_id, **data})
        return {"id": important_day_id, "message": "生日已新增"}

    def update(self, important_day_id: int, owner_user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._owned(important_day_id, owner_user_id)
        data = self._validate(payload)
        self._db.update(
            "important_days",
            data,
            where="id = %s AND user_id = %s",
            params=(important_day_id, owner_user_id),
        )
        return {"id": important_day_id, "message": "生日已更新"}

    def delete(self, important_day_id: int, owner_user_id: int) -> dict[str, str]:
        self._owned(important_day_id, owner_user_id)
        self._db.delete("important_days", where="id = %s AND user_id = %s", params=(important_day_id, owner_user_id))
        return {"message": "生日已刪除"}

    def _owned(self, important_day_id: int, owner_user_id: int) -> dict[str, Any]:
        row = self._db.select(
            "important_days",
            where="id = %s AND user_id = %s",
            params=(important_day_id, owner_user_id),
            fetch_one=True,
        )
        if row is None:
            raise ImportantDayNotFoundError("找不到指定的生日設定")
        return row

    def _validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": _parse_name(payload.get("name")),
            "birth_month": _parse_month(payload.get("birth_month")),
            "birth_day": _parse_day(payload.get("birth_day")),
        }

    @staticmethod
    def _serialize(row: dict[str, Any], user_id: int) -> dict[str, Any]:
        result = dict(row)
        result["owner_user_id"] = row["user_id"]
        result["can_edit"] = row["user_id"] == user_id
        return result
