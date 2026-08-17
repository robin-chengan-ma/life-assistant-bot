"""Mobile App 收藏清單 CRUD 與唯讀分析服務。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

_ITEM_TYPES = {"restaurant", "attraction", "mountain", "accommodation", "activity", "other"}
_TAIWAN_TZ = ZoneInfo("Asia/Taipei")


class CollectionDatabase(Protocol):
    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False): ...
    def insert(self, table, data, returning="id"): ...
    def update(self, table, data, where, params): ...
    def delete(self, table, where, params): ...
    def execute_query(self, query, params=None): ...


class CollectionGeocoder(Protocol):
    def search(self, payload: dict[str, Any]) -> dict[str, Any]: ...


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


class AppCollectionService:
    def __init__(self, db: CollectionDatabase, geocoder: CollectionGeocoder | None = None):
        self._db = db
        self._geocoder = geocoder

    def geocode(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._geocoder is None:
            raise CollectionValidationError("地址定位服務尚未設定")
        return self._geocoder.search(payload)

    def list_for_user(
        self,
        user_id: int,
        *,
        country_code: str | None = None,
        city_name: str | None = None,
        item_type: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        clauses = ["user_id = %s", "deleted_at IS NULL"]
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
            ORDER BY updated_at DESC, id DESC""",
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
        data = self._validate(payload)
        item_id = self._db.insert(
            "collection_items",
            {"user_id": user_id, **data, "currency_code": "TWD", "status": "saved"},
        )
        return {"id": item_id, "message": "收藏項目已新增"}

    def update(self, item_id: int, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._owned(item_id, user_id)
        data = self._validate(payload)
        self._db.update(
            "collection_items",
            {**data, "updated_at": datetime.now(_TAIWAN_TZ)},
            where="id = %s AND user_id = %s",
            params=(item_id, user_id),
        )
        return {"id": item_id, "message": "收藏項目已更新"}

    def delete(self, item_id: int, user_id: int) -> dict[str, Any]:
        self._owned(item_id, user_id)
        self._db.execute_query(
            """/* app_collections:detach_active_trips */
            DELETE FROM trip_collection_items tci
            USING trips t
            WHERE tci.trip_id = t.id AND tci.collection_item_id = %s
              AND t.user_id = %s AND t.status IN ('planning', 'confirmed')
            RETURNING tci.id""",
            (item_id, user_id),
        )
        self._db.update(
            "collection_items",
            {"deleted_at": datetime.now(_TAIWAN_TZ)},
            where="id = %s AND user_id = %s",
            params=(item_id, user_id),
        )
        return {"id": item_id, "message": "收藏項目已刪除", "undo_seconds": 5}

    def restore(self, item_id: int, user_id: int) -> dict[str, Any]:
        self._owned(item_id, user_id)
        self._db.update(
            "collection_items",
            {"deleted_at": None, "updated_at": datetime.now(_TAIWAN_TZ)},
            where="id = %s AND user_id = %s",
            params=(item_id, user_id),
        )
        return {"id": item_id, "message": "收藏項目已復原"}

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

    def _validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        title = _optional_text(payload.get("title"), "收藏名稱", 120)
        if title is None:
            raise CollectionValidationError("請輸入收藏名稱")
        item_type = payload.get("item_type")
        if item_type not in _ITEM_TYPES:
            raise CollectionValidationError("請選擇正確的收藏類型")
        country_name = _optional_text(payload.get("country_name"), "國家", 100)
        if country_name is None:
            raise CollectionValidationError("請輸入國家")
        city_name = _optional_text(payload.get("city_name"), "區域／城市", 100)
        if city_name is None:
            raise CollectionValidationError("請輸入區域／城市")
        address = _optional_text(payload.get("address"), "地址", 500)

        latitude = _optional_decimal(payload.get("latitude"), "緯度", Decimal(-90), Decimal(90))
        longitude = _optional_decimal(payload.get("longitude"), "經度", Decimal(-180), Decimal(180))
        if (latitude is None) != (longitude is None):
            raise CollectionValidationError("地圖座標必須同時包含緯度與經度")

        source_url = _optional_text(payload.get("source_url"), "網址", 2000)
        if source_url and urlparse(source_url).scheme not in {"http", "https"}:
            raise CollectionValidationError("網址必須以 http:// 或 https:// 開頭")

        return {
            "item_type": item_type,
            "title": title,
            "country_code": _optional_text(payload.get("country_code"), "國家代碼", 3),
            "country_name": country_name,
            "city_name": city_name,
            "address": address,
            "latitude": latitude,
            "longitude": longitude,
            "source_url": source_url,
            "estimated_cost": _optional_decimal(
                payload.get("estimated_cost"), "預估費用", Decimal(0), Decimal("9999999999.99")
            ),
            "currency_code": "TWD",
            "notes": _optional_text(payload.get("notes"), "備註", 2000),
        }

    @staticmethod
    def _serialize(row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        for field in ("visited_at", "created_at", "updated_at"):
            if isinstance(result.get(field), datetime):
                result[field] = result[field].isoformat()
        for field in ("latitude", "longitude", "estimated_cost"):
            if isinstance(result.get(field), Decimal):
                result[field] = float(result[field])
        return result
