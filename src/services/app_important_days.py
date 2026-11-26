"""Mobile App 生日設定服務。

2026-11（功能大幅精簡，Robin 明確決策）：「重要日子」改名為「生日設定」，拿掉單次事件、浮動
（農曆）日期、通知對象、備註、跟行程或目標連動等舊概念，只剩下「誰的生日、國曆幾月幾號」。
欄位假設見 `src/bot/important_days.py` 檔頭與 migration 0103。

2026-11-26（生日多選提前提醒，見 migration 0105）：新增 `remind_offsets`（可複選「14／7／3／
當天」天前推播），只允許 `{0,3,7,14}` 的非空子集合。

2026-11-26（推播對象可選，見 migration 0107）：新增 `audience_mode`（self／selected／everyone）
與 `audience_user_ids`（僅 selected 模式有意義，完全照勾選名單，不自動包含建立者本人）。
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


_ALLOWED_REMIND_OFFSETS = {0, 3, 7, 14}
_ALLOWED_AUDIENCE_MODES = {"self", "selected", "everyone"}


def _parse_remind_offsets(value: Any) -> list[int]:
    if value is None:
        return [0]
    if not isinstance(value, list) or not value:
        raise ImportantDayValidationError("請至少選擇一個提前提醒天數")
    offsets = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item not in _ALLOWED_REMIND_OFFSETS:
            raise ImportantDayValidationError("提前提醒天數只能是 0、3、7 或 14 天")
        offsets.add(item)
    return sorted(offsets, reverse=True)


def _parse_audience(payload: dict[str, Any], db: ImportantDaysDatabase) -> tuple[str, list[int]]:
    mode = payload.get("audience_mode", "self")
    if mode is None:
        mode = "self"
    if mode not in _ALLOWED_AUDIENCE_MODES:
        raise ImportantDayValidationError("推播對象設定不正確")
    if mode != "selected":
        return mode, []
    raw_ids = payload.get("audience_user_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise ImportantDayValidationError("請至少選擇一位要推播的對象")
    user_ids = []
    for item in raw_ids:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ImportantDayValidationError("推播對象設定不正確")
        user_ids.append(item)
    existing_rows = db.select("users", columns=("id",))
    existing_ids = {row["id"] for row in existing_rows}
    unique_ids = sorted(set(user_ids))
    if not set(unique_ids).issubset(existing_ids):
        raise ImportantDayValidationError("推播對象包含不存在的使用者")
    return mode, unique_ids


class AppImportantDayService:
    def __init__(self, db: ImportantDaysDatabase):
        self._db = db

    def family_users(self) -> list[dict[str, Any]]:
        """供「自行選擇」推播對象 UI 使用。

        2026-11-26（Robin 反饋第一版）：原本只回傳 `user_id`（如 `user01`）給前端顯示，使用者
        完全看不出對應到誰；改成一併回傳 `display_name`。

        2026-11-26（同日再修正，Robin 指出暱稱可能重複）：暱稱／家庭稱謂可能無法分辨真實身份
        （例如弟媳的父母雙方都被稱作「媽媽」），改為優先顯示 `full_name`（全名，見 migration
        0108），只有既有使用者尚未補齊全名時才退回 `nickname`／`family_title`／`role`／
        `user_id` 其中第一個非空值，確保一定有可讀的顯示文字。
        """
        rows = self._db.select("users", columns=("id", "role", "nickname", "family_title", "full_name"))
        return [
            {
                "id": row["id"],
                "role": row["role"],
                "user_id": f"user{row['id']:02d}",
                "display_name": (
                    row.get("full_name")
                    or row.get("nickname")
                    or row.get("family_title")
                    or row.get("role")
                    or f"user{row['id']:02d}"
                ),
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
        audience_mode, audience_user_ids = _parse_audience(payload, self._db)
        return {
            "name": _parse_name(payload.get("name")),
            "birth_month": _parse_month(payload.get("birth_month")),
            "birth_day": _parse_day(payload.get("birth_day")),
            "remind_offsets": _parse_remind_offsets(payload.get("remind_offsets")),
            "audience_mode": audience_mode,
            "audience_user_ids": audience_user_ids,
        }

    @staticmethod
    def _serialize(row: dict[str, Any], user_id: int) -> dict[str, Any]:
        result = dict(row)
        result["owner_user_id"] = row["user_id"]
        result["can_edit"] = row["user_id"] == user_id
        return result
