"""src/api/app_calendar.py 的 HTTP 層測試（2026-11-26，待辦改日期區間＋行事曆，見
docs/ADR/discuss/robinson.md）。"""
import pytest
from flask import Flask

from src.services.app_auth import AuthenticatedUser


class FakeDatabase:
    def close(self):
        return None


class FakeAuthService:
    def authenticate_access_token(self, token):
        assert token == "valid-token"
        return AuthenticatedUser(1, "user01", "Robin", True)


@pytest.fixture()
def client(monkeypatch):
    from src.api import app_auth, app_calendar

    monkeypatch.setattr(app_auth, "CloudSQLClient", FakeDatabase)
    monkeypatch.setattr(app_auth, "_build_service", lambda db: FakeAuthService())
    monkeypatch.setattr(app_calendar, "CloudSQLClient", FakeDatabase)
    monkeypatch.setattr(app_calendar, "report_mobile_error", lambda db, feature, user_id: None)

    app = Flask(__name__)
    app.register_blueprint(app_auth.app_bp)
    app.register_blueprint(app_calendar.app_calendar_bp)
    return app.test_client(), app_calendar


def auth_headers():
    return {"Authorization": "Bearer valid-token"}


def test_get_calendar_month_requires_bearer_token(client):
    test_client, _ = client

    response = test_client.get("/api/app/calendar?year=2026&month=8")

    assert response.status_code == 401


def test_get_calendar_month_returns_days_from_service(client, monkeypatch):
    test_client, module = client

    class Service:
        def __init__(self, db, sync_missing=False):
            pass

        def days(self, start, end):
            assert start.isoformat() == "2026-08-01"
            assert end.isoformat() == "2026-08-31"
            return {"2026-08-08": {"name": "父親節", "is_holiday": False, "holiday_category": None, "description": None}}

    monkeypatch.setattr(module, "TaiwanCalendarService", Service)

    response = test_client.get("/api/app/calendar?year=2026&month=8", headers=auth_headers())

    assert response.status_code == 200
    body = response.get_json()
    assert body["year"] == 2026
    assert body["month"] == 8
    assert body["days"]["2026-08-08"]["name"] == "父親節"


@pytest.mark.parametrize("query", ["", "?year=2026", "?month=8", "?year=abc&month=8", "?year=2026&month=13", "?year=2026&month=0"])
def test_get_calendar_month_rejects_invalid_query(client, query):
    test_client, _ = client

    response = test_client.get(f"/api/app/calendar{query}", headers=auth_headers())

    assert response.status_code == 400


def test_get_calendar_month_maps_service_exception_to_503(client, monkeypatch):
    test_client, module = client

    class Service:
        def __init__(self, db, sync_missing=False):
            pass

        def days(self, start, end):
            raise RuntimeError("boom")

    monkeypatch.setattr(module, "TaiwanCalendarService", Service)

    response = test_client.get("/api/app/calendar?year=2026&month=8", headers=auth_headers())

    assert response.status_code == 503
