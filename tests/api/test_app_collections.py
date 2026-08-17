import pytest
from flask import Flask

from src.services.app_auth import AuthenticatedUser
from src.services.app_collections import (
    CollectionNotFoundError,
    CollectionValidationError,
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
    from src.api import app_auth, app_collections

    monkeypatch.setattr(app_auth, "CloudSQLClient", FakeDatabase)
    monkeypatch.setattr(app_auth, "_build_service", lambda db: FakeAuthService())
    monkeypatch.setattr(app_collections, "CloudSQLClient", FakeDatabase)
    app = Flask(__name__)
    app.register_blueprint(app_auth.app_bp)
    app.register_blueprint(app_collections.app_collections_bp)
    return app.test_client(), app_collections


def headers():
    return {"Authorization": "Bearer valid-token"}


def test_list_passes_filters_to_service(client, monkeypatch):
    test_client, module = client
    captured = {}

    class Service:
        def list_for_user(self, user_id, **filters):
            captured.update(user_id=user_id, **filters)
            return {"items": [], "summary": {"total": 0}}

    monkeypatch.setattr(module, "_service", lambda db: Service())
    response = test_client.get(
        "/api/app/collections?country=JP&city=東京&type=restaurant&status=saved",
        headers=headers(),
    )

    assert response.status_code == 200
    assert captured == {
        "user_id": 1,
        "country_code": "JP",
        "city_name": "東京",
        "item_type": "restaurant",
        "status": "saved",
    }


def test_create_update_delete_and_restore_use_authenticated_user(client, monkeypatch):
    test_client, module = client
    calls = []

    class Service:
        def create(self, user_id, payload):
            calls.append(("create", user_id, payload))
            return {"id": 8, "message": "收藏項目已新增"}

        def update(self, item_id, user_id, payload):
            calls.append(("update", item_id, user_id, payload))
            return {"id": item_id, "message": "收藏項目已更新"}

        def delete(self, item_id, user_id):
            calls.append(("delete", item_id, user_id))
            return {"message": "收藏項目已刪除"}

        def restore(self, item_id, user_id):
            calls.append(("restore", item_id, user_id))
            return {"message": "收藏項目已復原"}

    monkeypatch.setattr(module, "_service", lambda db: Service())
    created = test_client.post("/api/app/collections", headers=headers(), json={"title": "餐廳"})
    updated = test_client.patch("/api/app/collections/8", headers=headers(), json={"title": "拉麵店"})
    deleted = test_client.delete("/api/app/collections/8", headers=headers())
    restored = test_client.post("/api/app/collections/8/restore", headers=headers())

    assert created.status_code == 201
    assert updated.status_code == 200
    assert deleted.status_code == 200
    assert restored.status_code == 200
    assert calls[0][:2] == ("create", 1)
    assert calls[1][:3] == ("update", 8, 1)
    assert calls[2] == ("delete", 8, 1)
    assert calls[3] == ("restore", 8, 1)


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (CollectionValidationError("請輸入收藏名稱"), 400),
        (CollectionNotFoundError("找不到指定的收藏項目"), 404),
    ],
)
def test_write_maps_expected_errors(client, monkeypatch, error, status):
    test_client, module = client

    class Service:
        def create(self, user_id, payload):
            raise error

    monkeypatch.setattr(module, "_service", lambda db: Service())
    response = test_client.post("/api/app/collections", headers=headers(), json={"title": "測試"})

    assert response.status_code == status
    assert response.get_json()["message"] == str(error)


def test_geocode_route_uses_authenticated_service(client, monkeypatch):
    test_client, module = client

    class Service:
        def geocode(self, payload):
            assert payload["address"] == "台北 101"
            return {"latitude": 25.033964, "longitude": 121.564468}

    monkeypatch.setattr(module, "_service", lambda db: Service())
    response = test_client.post(
        "/api/app/collections/geocode", headers=headers(),
        json={"address": "台北 101", "city_name": "台北", "country_name": "台灣"},
    )

    assert response.status_code == 200
    assert response.get_json()["longitude"] == 121.564468
