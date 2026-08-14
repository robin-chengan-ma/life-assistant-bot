"""FR-75 地址定位服務：明確觸發、每秒一次、結果快取。"""

from __future__ import annotations

import os
import threading
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Protocol

import requests

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_REQUEST_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0


class GeocodingDatabase(Protocol):
    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False): ...
    def insert(self, table, data, returning="id"): ...


class GeocodingError(Exception):
    """地址定位可預期錯誤。"""


class GeocodingValidationError(GeocodingError):
    """地址內容不符合規則。"""


class GeocodingNotFoundError(GeocodingError):
    """Nominatim 找不到符合地址。"""


class GeocodingUnavailableError(GeocodingError):
    """Nominatim 或必要設定暫時不可用。"""


def _text(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GeocodingValidationError(f"請輸入{label}")
    normalized = " ".join(value.split())
    if len(normalized) > maximum:
        raise GeocodingValidationError(f"{label}不可超過 {maximum} 個字元")
    return normalized


class NominatimGeocoder:
    def __init__(
        self,
        db: GeocodingDatabase,
        *,
        http_get: Callable[..., Any] = requests.get,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        user_agent: str | None = None,
    ):
        self._db = db
        self._http_get = http_get
        self._monotonic = monotonic
        self._sleep = sleep
        self._user_agent = user_agent or os.environ.get("NOMINATIM_USER_AGENT", "").strip()

    def search(self, payload: dict[str, Any]) -> dict[str, Any]:
        address = _text(payload.get("address"), "地址", 500)
        city_name = _text(payload.get("city_name"), "區域／城市", 100)
        country_name = _text(payload.get("country_name"), "國家", 100)
        query_text = ", ".join((address, city_name, country_name))
        query_key = query_text.casefold()

        cached = self._db.select(
            "geocoding_cache", where="query_key = %s", params=(query_key,), fetch_one=True
        )
        if cached is not None:
            return self._serialize(cached, cached=True)
        if not self._user_agent:
            raise GeocodingUnavailableError("地址定位服務尚未完成識別設定")

        response = self._request(query_text)
        try:
            results = response.json()
        except (TypeError, ValueError) as exc:
            raise GeocodingUnavailableError("地址定位服務回傳格式不正確") from exc
        if not isinstance(results, list) or not results:
            raise GeocodingNotFoundError("找不到此地址，請補充更完整的地址後重試")
        first = results[0]
        if not isinstance(first, dict):
            raise GeocodingUnavailableError("地址定位服務回傳格式不正確")
        try:
            latitude = Decimal(str(first["lat"]))
            longitude = Decimal(str(first["lon"]))
        except (KeyError, InvalidOperation, ValueError) as exc:
            raise GeocodingUnavailableError("地址定位服務回傳座標不正確") from exc
        if not latitude.is_finite() or not Decimal("-90") <= latitude <= Decimal("90"):
            raise GeocodingUnavailableError("地址定位服務回傳座標不正確")
        if not longitude.is_finite() or not Decimal("-180") <= longitude <= Decimal("180"):
            raise GeocodingUnavailableError("地址定位服務回傳座標不正確")
        row = {
            "query_key": query_key,
            "query_text": query_text,
            "latitude": latitude.quantize(Decimal("0.000001")),
            "longitude": longitude.quantize(Decimal("0.000001")),
            "display_name": str(first.get("display_name") or query_text)[:1000],
            "provider": "nominatim",
        }
        self._db.insert("geocoding_cache", row)
        return self._serialize(row, cached=False)

    def _request(self, query_text: str):
        global _LAST_REQUEST_AT
        with _REQUEST_LOCK:
            wait_seconds = max(0.0, 1.0 - (self._monotonic() - _LAST_REQUEST_AT))
            if wait_seconds:
                self._sleep(wait_seconds)
            try:
                response = self._http_get(
                    _NOMINATIM_URL,
                    params={"q": query_text, "format": "jsonv2", "limit": 1, "addressdetails": 1},
                    headers={"User-Agent": self._user_agent, "Accept-Language": "zh-TW"},
                    timeout=10,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                raise GeocodingUnavailableError("地址定位服務目前無法連線，請稍後重試") from exc
            finally:
                _LAST_REQUEST_AT = self._monotonic()
        return response

    @staticmethod
    def _serialize(row: dict[str, Any], *, cached: bool) -> dict[str, Any]:
        return {
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "display_name": row["display_name"],
            "provider": "nominatim",
            "cached": cached,
            "attribution": "© OpenStreetMap contributors",
        }
