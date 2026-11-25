"""Mobile App 待辦事項 CRUD 服務。

2026-11（功能大幅精簡）：待辦事項是純粹的「一次性日期＋文字提醒」，不含完成/取消/逾期狀態。
新增/編輯/刪除全部在 Mobile App 做，Telegram 端只負責推播（見 `src/bot/todo.py`）。欄位假設
見 migration 0102。
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Protocol
from zoneinfo import ZoneInfo

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")


class TodoDatabase(Protocol):
    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False): ...
    def insert(self, table, data, returning="id"): ...
    def update(self, table, data, where, params): ...
    def delete(self, table, where, params): ...


class TodoError(Exception):
    """待辦事項可預期錯誤。"""


class TodoValidationError(TodoError):
    """欄位不符合規則。"""


class TodoNotFoundError(TodoError):
    """待辦事項不存在或不屬於目前使用者。"""


def _parse_content(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TodoValidationError("請輸入待辦內容")
    content = value.strip()
    if len(content) > 1000:
        raise TodoValidationError("待辦內容不可超過 1000 個字元")
    return content


def _parse_remind_date(value: Any) -> datetime:
    if not isinstance(value, str):
        raise TodoValidationError("請選擇提醒日期")
    try:
        day = date.fromisoformat(value)
    except ValueError as exc:
        raise TodoValidationError("提醒日期格式不正確") from exc
    return datetime.combine(day, time(9, 0), tzinfo=_TAIWAN_TZ)


class AppTodoService:
    def __init__(self, db: TodoDatabase):
        self._db = db

    def list_for_user(self, user_id: int) -> list[dict[str, Any]]:
        rows = self._db.select("todos", where="user_id = %s", params=(user_id,))
        items = [self._serialize(row, user_id) for row in rows]
        return sorted(items, key=lambda item: item["remind_date"])

    def create(self, owner_user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._validate(payload)
        todo_id = self._db.insert("todos", {"user_id": owner_user_id, **data})
        return {"id": todo_id, "message": "待辦事項已新增"}

    def update(self, todo_id: int, owner_user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._owned(todo_id, owner_user_id)
        data = self._validate(payload)
        self._db.update(
            "todos",
            data,
            where="id = %s AND user_id = %s",
            params=(todo_id, owner_user_id),
        )
        return {"id": todo_id, "message": "待辦事項已更新"}

    def delete(self, todo_id: int, owner_user_id: int) -> dict[str, str]:
        self._owned(todo_id, owner_user_id)
        self._db.delete("todos", where="id = %s AND user_id = %s", params=(todo_id, owner_user_id))
        return {"message": "待辦事項已刪除"}

    def _owned(self, todo_id: int, owner_user_id: int) -> dict[str, Any]:
        row = self._db.select(
            "todos",
            where="id = %s AND user_id = %s",
            params=(todo_id, owner_user_id),
            fetch_one=True,
        )
        if row is None:
            raise TodoNotFoundError("找不到指定的待辦事項")
        return row

    def _validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "content": _parse_content(payload.get("content")),
            "remind_at": _parse_remind_date(payload.get("remind_date")),
        }

    @staticmethod
    def _serialize(row: dict[str, Any], user_id: int) -> dict[str, Any]:
        result = dict(row)
        result["owner_user_id"] = row["user_id"]
        result["can_edit"] = row["user_id"] == user_id
        remind_at = row["remind_at"]
        result["remind_date"] = remind_at.astimezone(_TAIWAN_TZ).date().isoformat() if isinstance(remind_at, datetime) else remind_at
        return result
