import pytest
from flask import Flask

from src.services.app_auth import AuthenticatedUser
from src.services.app_important_days import (
    ImportantDayNotFoundError,
    ImportantDayValidationError,
)


class FakeDatabase:
    def close(self):
        return None


class FakeAuthService:
    def authenticate_access_token(self, token):
        assert token == "valid-token"
        return AuthenticatedUser(1, "user01", "Robin", True)


@pytest.fixture()
def client(monkeypatch):
    from src.api import app_auth, app_important_days

    monkeypatch.setattr(app_auth, "CloudSQLClient", FakeDatabase)
    monkeypatch.setattr(app_auth, "_build_service", lambda db: FakeAuthService())
    monkeypatch.setattr(app_important_days, "CloudSQLClient", FakeDatabase)
    app = Flask(__name__)
    app.register_blueprint(app_auth.app_bp)
    app.register_blueprint(app_important_days.app_important_days_bp)
    return app.test_client(), app_important_days


def headers():
    return {"Authorization": "Bearer valid-token"}


def test_list_returns_visible_items_and_family_users(client, monkeypatch):
    test_client, module = client

    class Service:
        def list_for_user(self, user_id):
            assert user_id == 1
            return [{"id": 7, "title": "婚禮"}]

        def family_users(self):
            return [{"id": 1, "role": "Robin", "user_id": "user01"}]

    monkeypatch.setattr(module, "_service", lambda db: Service())
    response = test_client.get("/api/app/important-days", headers=headers())

    assert response.status_code == 200
    assert response.get_json()["items"][0]["title"] == "婚禮"


def test_create_and_update_use_authenticated_owner(client, monkeypatch):
    test_client, module = client
    calls = []

    class Service:
        def create(self, owner_id, payload):
            calls.append(("create", owner_id, payload))
            return {"id": 8, "message": "重要日子已新增"}

        def update(self, event_id, owner_id, payload):
            calls.append(("update", event_id, owner_id, payload))
            return {"id": event_id, "message": "重要日子已更新"}

    monkeypatch.setattr(module, "_service", lambda db: Service())
    created = test_client.post("/api/app/important-days", headers=headers(), json={"title": "婚禮"})
    updated = test_client.patch("/api/app/important-days/8", headers=headers(), json={"title": "婚宴"})

    assert created.status_code == 201
    assert updated.status_code == 200
    assert calls[0][:2] == ("create", 1)
    assert calls[1][:3] == ("update", 8, 1)


@pytest.mark.parametrize(
    ("error", "status"),
    [(ImportantDayValidationError("請輸入名稱"), 400), (ImportantDayNotFoundError("找不到指定的重要日子"), 404)],
)
def test_write_maps_expected_errors(client, monkeypatch, error, status):
    test_client, module = client

    class Service:
        def create(self, owner_id, payload):
            raise error

    monkeypatch.setattr(module, "_service", lambda db: Service())
    response = test_client.post("/api/app/important-days", headers=headers(), json={"title": "測試"})

    assert response.status_code == status
    assert response.get_json()["message"] == str(error)
