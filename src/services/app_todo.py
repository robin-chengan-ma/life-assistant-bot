"""Mobile App 待辦事項 CRUD 服務。

2026-11（功能大幅精簡）：待辦事項是純粹的「一次性日期＋文字提醒」，不含完成/取消/逾期狀態。
新增/編輯/刪除全部在 Mobile App 做，Telegram 端只負責推播（見 `src/bot/todo.py`）。欄位假設
見 migration 0102。

2026-11-26（待辦改日期區間＋行事曆，見 migration 0106、docs/ADR/discuss/robinson.md）：
`remind_at`（單一時間點，固定 09:00）改成 `remind_start_date`／`remind_end_date` 兩個日期
（單日待辦 = 兩者相同），推播固定改成第一天早上 08:30（見 `src/bot/todo.py`）。

2026-11-26（待辦提前提醒，見 migration 0109）：新增 `remind_offsets`（可複選「14／7／3／當天」
天前推播，只允許 `{0,3,7,14}` 的非空子集合），邏輯跟生日設定的 `remind_offsets` 完全一樣，但
待辦不需要推播對象選擇，一律只推給建立者本人，所以不會有 `audience_mode`/`audience_user_ids`
這類欄位。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol


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


def _parse_date(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise TodoValidationError(f"請選擇{label}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise TodoValidationError(f"{label}格式不正確") from exc


def _parse_remind_date_range(payload: dict[str, Any]) -> tuple[date, date]:
    start = _parse_date(payload.get("remind_start_date"), "提醒開始日期")
    end_value = payload.get("remind_end_date", payload.get("remind_start_date"))
    end = _parse_date(end_value, "提醒結束日期")
    if end < start:
        raise TodoValidationError("提醒結束日期不可早於開始日期")
    return start, end


_ALLOWED_REMIND_OFFSETS = {0, 3, 7, 14}


def _parse_remind_offsets(value: Any) -> list[int]:
    if value is None:
        return [0]
    if not isinstance(value, list) or not value:
        raise TodoValidationError("請至少選擇一個提前提醒天數")
    offsets = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item not in _ALLOWED_REMIND_OFFSETS:
            raise TodoValidationError("提前提醒天數只能是 0、3、7 或 14 天")
        offsets.add(item)
    return sorted(offsets, reverse=True)


class AppTodoService:
    def __init__(self, db: TodoDatabase):
        self._db = db

    def list_for_user(self, user_id: int) -> list[dict[str, Any]]:
        rows = self._db.select("todos", where="user_id = %s", params=(user_id,))
        items = [self._serialize(row, user_id) for row in rows]
        return sorted(items, key=lambda item: item["remind_start_date"])

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
        start, end = _parse_remind_date_range(payload)
        return {
            "content": _parse_content(payload.get("content")),
            "remind_start_date": start,
            "remind_end_date": end,
            "remind_offsets": _parse_remind_offsets(payload.get("remind_offsets")),
            # 日期異動後，舊的「哪些 offset 已經推播過」紀錄就不再適用，新增／編輯都重置，
            # 讓新的日期重新走一輪完整的提前提醒。
            "reminded_offsets_sent": [],
        }

    @staticmethod
    def _serialize(row: dict[str, Any], user_id: int) -> dict[str, Any]:
        result = dict(row)
        result["owner_user_id"] = row["user_id"]
        result["can_edit"] = row["user_id"] == user_id
        for field in ("remind_start_date", "remind_end_date"):
            value = result.get(field)
            result[field] = value.isoformat() if isinstance(value, date) else value
        return result
