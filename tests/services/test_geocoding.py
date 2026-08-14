from decimal import Decimal

import pytest
import requests

import src.services.geocoding as geocoding_module
from src.services.geocoding import (
    GeocodingNotFoundError,
    GeocodingUnavailableError,
    NominatimGeocoder,
)


class FakeDatabase:
    def __init__(self):
        self.rows = []

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        assert table == "geocoding_cache"
        rows = [row for row in self.rows if row["query_key"] == params[0]]
        return (rows[0] if rows else None) if fetch_one else rows

    def insert(self, table, data, returning="id"):
        assert table == "geocoding_cache"
        self.rows.append({"id": 1, **data})
        return 1


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


@pytest.fixture(autouse=True)
def reset_rate_limit():
    geocoding_module._LAST_REQUEST_AT = 0.0


def test_search_calls_nominatim_with_identity_and_caches_result():
    db = FakeDatabase()
    calls = []

    def http_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse([{"lat": "25.033964", "lon": "121.564468", "display_name": "台北 101"}])

    geocoder = NominatimGeocoder(
        db,
        http_get=http_get,
        user_agent="RobinsonLifeAssistant/1.0 (contact: test@example.com)",
        monotonic=lambda: 10.0,
    )
    payload = {"address": "信義路五段7號", "city_name": "台北市信義區", "country_name": "台灣"}

    first = geocoder.search(payload)
    second = geocoder.search(payload)

    assert len(calls) == 1
    assert calls[0][0] == "https://nominatim.openstreetmap.org/search"
    assert calls[0][1]["params"] == {
        "q": "信義路五段7號, 台北市信義區, 台灣",
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 1,
    }
    assert calls[0][1]["headers"]["User-Agent"].startswith("RobinsonLifeAssistant/")
    assert first["latitude"] == 25.033964
    assert first["cached"] is False
    assert second["cached"] is True
    assert db.rows[0]["latitude"] == Decimal("25.033964")


def test_search_enforces_one_request_per_second():
    sleeps = []
    times = iter((10.0, 10.0, 10.25, 11.0))
    geocoder = NominatimGeocoder(
        FakeDatabase(),
        http_get=lambda *_args, **_kwargs: FakeResponse([{"lat": "25", "lon": "121"}]),
        user_agent="RobinsonLifeAssistant/1.0 (contact: test@example.com)",
        monotonic=lambda: next(times),
        sleep=sleeps.append,
    )

    geocoder.search({"address": "地址一", "city_name": "台北", "country_name": "台灣"})
    geocoder.search({"address": "地址二", "city_name": "台北", "country_name": "台灣"})

    assert sleeps == [pytest.approx(0.75)]


def test_search_requires_identifying_user_agent():
    with pytest.raises(GeocodingUnavailableError, match="識別設定"):
        NominatimGeocoder(FakeDatabase(), user_agent="").search(
            {"address": "地址", "city_name": "台北", "country_name": "台灣"}
        )


def test_search_reports_not_found_and_network_failure():
    payload = {"address": "不存在", "city_name": "未知", "country_name": "台灣"}
    geocoder = NominatimGeocoder(
        FakeDatabase(), http_get=lambda *_args, **_kwargs: FakeResponse([]), user_agent="app/contact"
    )
    with pytest.raises(GeocodingNotFoundError):
        geocoder.search(payload)

    def fail(*_args, **_kwargs):
        raise requests.ConnectionError("offline")

    geocoder = NominatimGeocoder(FakeDatabase(), http_get=fail, user_agent="app/contact")
    with pytest.raises(GeocodingUnavailableError, match="無法連線"):
        geocoder.search(payload)
