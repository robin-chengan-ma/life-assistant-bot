"""Mobile App 收藏清單 CRUD 與唯讀分析服務。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

_ITEM_TYPES = {"restaurant", "attraction", "mountain", "accommodation", "activity", "other"}
_PRIORITIES = {"low", "medium", "high"}
_STATUSES = {"saved", "added_to_trip", "visited", "cancelled"}
_TAIWAN_TZ = ZoneInfo("Asia/Taipei")


class CollectionDatabase(Protocol):
    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False): ...
    def insert(self, table, data, returning="id"): ...
    def update(self, table, data, where, params): ...
    def delete(self, table, where, params): ...
    def execute_query(self, query, params=None): ...


class CollectionError(Exception):
    """收藏清單可預期錯誤。"""


class CollectionValidationError(CollectionError):
    """欄位不符合產品規則。"""


class CollectionNotFoundError(CollectionError):
    """收藏不存在或不屬於目前使用者。"""


def _optional_text(value: Any, label: str, maximum: int) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise CollectionValidationError(f"{label}格式不正確")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise CollectionValidationError(f"{label}不可超過 {maximum} 個字元")
    return normalized


def _optional_decimal(value: Any, label: str, minimum: Decimal, maximum: Decimal) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise CollectionValidationError(f"{label}格式不正確")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CollectionValidationError(f"{label}格式不正確") from exc
    if not parsed.is_finite() or not minimum <= parsed <= maximum:
        raise CollectionValidationError(f"{label}超出允許範圍")
    return parsed


def _optional_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise CollectionValidationError("想去日期格式不正確")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CollectionValidationError("想去日期格式不正確") from exc


class AppCollectionService:
    def __init__(self, db: CollectionDatabase):
        self._db = db

    def list_for_user(
        self,
        user_id: int,
        *,
        country_code: str | None = None,
        city_name: str | None = None,
        item_type: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        clauses = ["user_id = %s"]
        params: list[Any] = [user_id]
        filters = (
            ("country_code", country_code),
            ("city_name", city_name),
            ("item_type", item_type),
            ("status", status),
        )
        for column, value in filters:
            if value:
                clauses.append(f"{column} = %s")
                params.append(value)
        rows = self._db.execute_query(
            f"""/* app_collections:list */
            SELECT * FROM collection_items
            WHERE {' AND '.join(clauses)}
            ORDER BY
              CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
              desired_date NULLS LAST, updated_at DESC, id DESC""",
            tuple(params),
        )
        items = [self._serialize(row) for row in rows]
        return {
            "items": items,
            "summary": {
                "total": len(items),
                "saved": sum(item["status"] == "saved" for item in items),
                "added_to_trip": sum(item["status"] == "added_to_trip" for item in items),
                "visited": sum(item["status"] == "visited" for item in items),
            },
            "filters": {
                "countries": sorted({item["country_name"] for item in items if item.get("country_name")}),
                "cities": sorted({item["city_name"] for item in items if item.get("city_name")}),
            },
        }

    def create(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._validate(payload, user_id)
        item_id = self._db.insert("collection_items", {"user_id": user_id, **data})
        return {"id": item_id, "message": "收藏項目已新增"}

    def update(self, item_id: int, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._owned(item_id, user_id)
        data = self._validate(payload, user_id)
        self._db.update(
            "collection_items",
            {**data, "updated_at": datetime.now(_TAIWAN_TZ)},
            where="id = %s AND user_id = %s",
            params=(item_id, user_id),
        )
        return {"id": item_id, "message": "收藏項目已更新"}

    def delete(self, item_id: int, user_id: int) -> dict[str, str]:
        self._owned(item_id, user_id)
        self._db.delete("collection_items", where="id = %s AND user_id = %s", params=(item_id, user_id))
        return {"message": "收藏項目已刪除"}

    def _owned(self, item_id: int, user_id: int) -> dict[str, Any]:
        row = self._db.select(
            "collection_items",
            where="id = %s AND user_id = %s",
            params=(item_id, user_id),
            fetch_one=True,
        )
        if row is None:
            raise CollectionNotFoundError("找不到指定的收藏項目")
        return row

    def _validate(self, payload: dict[str, Any], user_id: int) -> dict[str, Any]:
        title = _optional_text(payload.get("title"), "收藏名稱", 120)
        if title is None:
            raise CollectionValidationError("請輸入收藏名稱")
        item_type = payload.get("item_type")
        if item_type not in _ITEM_TYPES:
            raise CollectionValidationError("請選擇正確的收藏類型")
        priority = payload.get("priority", "medium")
        if priority not in _PRIORITIES:
            raise CollectionValidationError("請選擇正確的優先程度")
        status = payload.get("status", "saved")
        if status not in _STATUSES:
            raise CollectionValidationError("請選擇正確的收藏狀態")

        latitude = _optional_decimal(payload.get("latitude"), "緯度", Decimal("-90"), Decimal("90"))
        longitude = _optional_decimal(payload.get("longitude"), "經度", Decimal("-180"), Decimal("180"))
        if (latitude is None) != (longitude is None):
            raise CollectionValidationError("地圖座標必須同時包含緯度與經度")

        source_url = _optional_text(payload.get("source_url"), "網址", 2000)
        if source_url and urlparse(source_url).scheme not in {"http", "https"}:
            raise CollectionValidationError("網址必須以 http:// 或 https:// 開頭")

        trip_id = payload.get("trip_id")
        if trip_id is not None:
            if isinstance(trip_id, bool) or not isinstance(trip_id, int):
                raise CollectionValidationError("旅遊行程格式不正確")
            trip = self._db.select(
                "trips",
                where="id = %s AND user_id = %s",
                params=(trip_id, user_id),
                fetch_one=True,
            )
            if trip is None:
                raise CollectionValidationError("找不到可加入的旅遊行程")

        visited_at = None
        if status == "visited":
            raw_visited_at = payload.get("visited_at")
            if raw_visited_at:
                if not isinstance(raw_visited_at, str):
                    raise CollectionValidationError("造訪時間格式不正確")
                try:
                    visited_at = datetime.fromisoformat(raw_visited_at.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise CollectionValidationError("造訪時間格式不正確") from exc
            else:
                visited_at = datetime.now(_TAIWAN_TZ)

        return {
            "trip_id": trip_id,
            "item_type": item_type,
            "title": title,
            "country_code": _optional_text(payload.get("country_code"), "國家代碼", 3),
            "country_name": _optional_text(payload.get("country_name"), "國家名稱", 100),
            "administrative_area": _optional_text(payload.get("administrative_area"), "縣市", 100),
            "city_name": _optional_text(payload.get("city_name"), "城市", 100),
            "address": _optional_text(payload.get("address"), "地址", 500),
            "latitude": latitude,
            "longitude": longitude,
            "source_url": source_url,
            "estimated_cost": _optional_decimal(
                payload.get("estimated_cost"), "預估費用", Decimal("0"), Decimal("9999999999.99")
            ),
            "currency_code": (_optional_text(payload.get("currency_code", "TWD"), "幣別", 3) or "TWD").upper(),
            "priority": priority,
            "desired_date": _optional_date(payload.get("desired_date")),
            "notes": _optional_text(payload.get("notes"), "備註", 2000),
            "status": status,
            "visited_at": visited_at,
        }

    @staticmethod
    def _serialize(row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        for field in ("desired_date",):
            if isinstance(result.get(field), date):
                result[field] = result[field].isoformat()
        for field in ("visited_at", "created_at", "updated_at"):
            if isinstance(result.get(field), datetime):
                result[field] = result[field].isoformat()
        for field in ("latitude", "longitude", "estimated_cost"):
            if isinstance(result.get(field), Decimal):
                result[field] = float(result[field])
        return result
