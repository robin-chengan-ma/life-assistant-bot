"""FR-75 地址定位服務：明確觸發、每秒一次、結果快取。"""

from __future__ import annotations

import os
import re
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


def _optional_text(value: Any, label: str, maximum: int) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise GeocodingValidationError(f"{label}格式不正確")
    normalized = " ".join(value.split())
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise GeocodingValidationError(f"{label}不可超過 {maximum} 個字元")
    return normalized


def _road_fallback(address: str, city_name: str, country_name: str) -> str | None:
    candidate = address.replace(country_name, "").replace(city_name, "").strip(" ,，")
    if not candidate:
        candidate = address
    parts = [part.strip(" ,，") for part in re.split(r"[縣市區鄉鎮村里]", candidate) if part.strip(" ,，")]
    if parts:
        candidate = parts[-1]
    candidate = re.sub(r"\s*\d+(?:[-之]\d+)?號.*$", "", candidate).strip(" ,，")
    return candidate or None


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
        address = _optional_text(payload.get("address"), "地址", 500)
        city_name = _text(payload.get("city_name"), "區域／城市", 100)
        country_name = _text(payload.get("country_name"), "國家", 100)
        attempts: list[tuple[str, str]] = []
        if address:
            attempts.append((", ".join((address, city_name, country_name)), "exact"))
            road = _road_fallback(address, city_name, country_name)
            if road:
                attempts.append((", ".join((road, city_name, country_name)), "road"))
        attempts.append((", ".join((city_name, country_name)), "city"))

        seen: set[str] = set()
        for query_text, precision in attempts:
            query_key = query_text.casefold()
            if query_key in seen:
                continue
            seen.add(query_key)
            cached = self._db.select(
                "geocoding_cache", where="query_key = %s", params=(query_key,), fetch_one=True
            )
            if cached is not None:
                return self._serialize(cached, cached=True, precision=precision)
            if not self._user_agent:
                raise GeocodingUnavailableError("地址定位服務尚未完成識別設定")
            first = self._first_result(query_text)
            if first is None:
                continue
            row = self._cache_row(query_key, query_text, first)
            self._db.insert("geocoding_cache", row)
            return self._serialize(row, cached=False, precision=precision)
        raise GeocodingNotFoundError("找不到可用位置，請確認國家與區域／城市後重試")

    def _first_result(self, query_text: str) -> dict[str, Any] | None:
        response = self._request(query_text)
        try:
            results = response.json()
        except (TypeError, ValueError) as exc:
            raise GeocodingUnavailableError("地址定位服務回傳格式不正確") from exc
        if not isinstance(results, list):
            raise GeocodingUnavailableError("地址定位服務回傳格式不正確")
        if not results:
            return None
        if not isinstance(results[0], dict):
            raise GeocodingUnavailableError("地址定位服務回傳格式不正確")
        return results[0]

    @staticmethod
    def _cache_row(query_key: str, query_text: str, result: dict[str, Any]) -> dict[str, Any]:
        try:
            latitude = Decimal(str(result["lat"]))
            longitude = Decimal(str(result["lon"]))
        except (KeyError, InvalidOperation, ValueError) as exc:
            raise GeocodingUnavailableError("地址定位服務回傳座標不正確") from exc
        if not latitude.is_finite() or not Decimal("-90") <= latitude <= Decimal("90"):
            raise GeocodingUnavailableError("地址定位服務回傳座標不正確")
        if not longitude.is_finite() or not Decimal("-180") <= longitude <= Decimal("180"):
            raise GeocodingUnavailableError("地址定位服務回傳座標不正確")
        return {
            "query_key": query_key,
            "query_text": query_text,
            "latitude": latitude.quantize(Decimal("0.000001")),
            "longitude": longitude.quantize(Decimal("0.000001")),
            "display_name": str(result.get("display_name") or query_text)[:1000],
            "provider": "nominatim",
        }

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
    def _serialize(row: dict[str, Any], *, cached: bool, precision: str = "exact") -> dict[str, Any]:
        precision_labels = {"exact": "精確地址", "road": "道路近似位置", "city": "城市近似位置"}
        return {
            "latitude": float(row["latitude"]),
            "longitude": float(row["longitude"]),
            "display_name": row["display_name"],
            "provider": "nominatim",
            "precision": precision,
            "precision_label": precision_labels[precision],
            "cached": cached,
            "attribution": "© OpenStreetMap contributors",
        }
