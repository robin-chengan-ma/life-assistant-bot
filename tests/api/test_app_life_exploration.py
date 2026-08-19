import pytest
from flask import Flask

from src.services.app_auth import AuthenticatedUser
from src.services.app_life_exploration import LifeNotFoundError, LifeValidationError


class FakeDatabase:
    def close(self):
        return None


class FakeAuthService:
    def authenticate_access_token(self, token):
        assert token == "valid-token"
        return AuthenticatedUser(1, "user01", "Robin", True)


@pytest.fixture()
def client(monkeypatch):
    from src.api import app_auth, app_life_exploration

    monkeypatch.setattr(app_auth, "CloudSQLClient", FakeDatabase)
    monkeypatch.setattr(app_auth, "_build_service", lambda db: FakeAuthService())
    monkeypatch.setattr(app_life_exploration, "CloudSQLClient", FakeDatabase)
    app = Flask(__name__)
    app.register_blueprint(app_auth.app_bp)
    app.register_blueprint(app_life_exploration.app_life_exploration_bp)
    return app.test_client(), app_life_exploration


def headers():
    return {"Authorization": "Bearer valid-token"}


def test_trip_routes_use_authenticated_user(client, monkeypatch):
    test_client, module = client
    calls = []

    class Service:
        def list_trips(self, user_id):
            calls.append(("list", user_id)); return {"trips": []}

        def create_trip(self, user_id, payload):
            calls.append(("create", user_id, payload)); return {"id": 7, "message": "旅遊行程已建立"}

        def complete_trip(self, trip_id, user_id, payload):
            calls.append(("complete", trip_id, user_id, payload)); return {"id": trip_id}

    monkeypatch.setattr(module, "_service", lambda db: Service())
    assert test_client.get("/api/app/life/trips", headers=headers()).status_code == 200
    assert test_client.post("/api/app/life/trips", headers=headers(), json={"title": "東京"}).status_code == 201
    assert test_client.post("/api/app/life/trips/7/complete", headers=headers(), json={"visited_collection_ids": [2]}).status_code == 200
    assert calls == [("list", 1), ("create", 1, {"title": "東京"}), ("complete", 7, 1, {"visited_collection_ids": [2]})]


@pytest.mark.parametrize(("error", "status"), [(LifeValidationError("錯誤"), 400), (LifeNotFoundError("找不到"), 404)])
def test_expected_errors_are_mapped(client, monkeypatch, error, status):
    test_client, module = client

    class Service:
        def create_achievement(self, user_id, payload):
            raise error

    monkeypatch.setattr(module, "_service", lambda db: Service())
    response = test_client.post("/api/app/life/achievements", headers=headers(), json={"title": "測試"})
    assert response.status_code == status
    assert response.get_json()["message"] == str(error)


def test_candidate_decision_requires_boolean(client):
    test_client, _module = client
    response = test_client.post(
        "/api/app/life/achievement-candidates/3/decision",
        headers=headers(),
        json={"accept": "yes"},
    )
    assert response.status_code == 400


def test_achievement_pin_route_uses_authenticated_user(client, monkeypatch):
    test_client, module = client
    calls = []

    class Service:
        def set_achievement_pinned(self, achievement_id, user_id, pinned):
            calls.append((achievement_id, user_id, pinned))
            return {"id": achievement_id, "pinned": pinned}

    monkeypatch.setattr(module, "_service", lambda db: Service())
    response = test_client.patch(
        "/api/app/life/achievements/8/pin", headers=headers(), json={"pinned": True}
    )

    assert response.status_code == 200
    assert calls == [(8, 1, True)]


def test_achievement_pin_route_requires_boolean(client):
    test_client, _module = client
    response = test_client.patch(
        "/api/app/life/achievements/8/pin", headers=headers(), json={"pinned": "yes"}
    )
    assert response.status_code == 400


def test_relocate_exploration_route_uses_authenticated_user(client, monkeypatch):
    test_client, module = client
    calls = []

    class Service:
        def relocate_exploration(self, event_id, user_id):
            calls.append((event_id, user_id))
            return {"id": event_id, "latitude": 25.0, "longitude": 121.0}

    monkeypatch.setattr(module, "_service", lambda db: Service())
    response = test_client.post("/api/app/life/exploration/8/relocate", headers=headers())

    assert response.status_code == 200
    assert calls == [(8, 1)]
