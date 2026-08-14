import pytest
from flask import Flask

from src.services.app_analytics import FeatureDisabledError, ForbiddenModuleError
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
    from src.api import app_analytics, app_auth

    monkeypatch.setattr(app_auth, "CloudSQLClient", FakeDatabase)
    monkeypatch.setattr(app_auth, "_build_service", lambda db: FakeAuthService())
    monkeypatch.setattr(app_analytics, "CloudSQLClient", FakeDatabase)

    app = Flask(__name__)
    app.register_blueprint(app_auth.app_bp)
    app.register_blueprint(app_analytics.app_analytics_bp)
    return app.test_client(), app_analytics


def auth_headers():
    return {"Authorization": "Bearer valid-token"}


def test_dashboard_requires_bearer_token(client):
    test_client, _ = client

    response = test_client.get("/api/app/dashboard")

    assert response.status_code == 401


def test_dashboard_returns_navigation_and_summary(client, monkeypatch):
    test_client, module = client

    class Service:
        def dashboard(self, user):
            return {"date": "2026-08-11", "navigation": {}, "summary": {}, "notifications": [], "important_days": []}

    monkeypatch.setattr(module, "_build_analytics", lambda db: Service())

    response = test_client.get("/api/app/dashboard", headers=auth_headers())

    assert response.status_code == 200
    assert response.get_json()["date"] == "2026-08-11"


def test_analytics_rejects_range_shorter_than_seven_days(client):
    test_client, _ = client

    response = test_client.get(
        "/api/app/analytics/finance?start=2026-08-01&end=2026-08-03",
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.get_json() == {"message": "日期區間必須介於 7 到 30 天"}


def test_todo_analytics_accepts_single_future_date(client, monkeypatch):
    test_client, module = client

    class Service:
        def todos(self, user, start, end, *, calendar_start, calendar_end):
            assert start == end
            assert calendar_start.isoformat() == "2027-01-01"
            assert calendar_end.isoformat() == "2027-01-31"
            return {"has_any_data": False, "items": [], "calendar_counts": {}}

    monkeypatch.setattr(module, "_build_analytics", lambda db: Service())
    response = test_client.get(
        "/api/app/analytics/todos?start=2027-01-01&end=2027-01-01&calendar_month=2027-01",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.get_json()["range"] == {"start": "2027-01-01", "end": "2027-01-01"}


def test_todo_analytics_rejects_range_longer_than_seven_days(client):
    test_client, _ = client

    response = test_client.get(
        "/api/app/analytics/todos?start=2026-08-01&end=2026-08-08",
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.get_json() == {"message": "日期區間必須介於 1 到 7 天"}


def test_todo_analytics_requires_valid_calendar_month(client):
    test_client, _ = client

    response = test_client.get(
        "/api/app/analytics/todos?start=2026-08-01&end=2026-08-01&calendar_month=invalid",
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.get_json() == {"message": "月份格式必須為 YYYY-MM"}


@pytest.mark.parametrize(
    ("error", "status"),
    [(FeatureDisabledError("請先把功能打開才能使用喔"), 409), (ForbiddenModuleError("您沒有權限查看此頁面"), 403)],
)
def test_analytics_maps_access_errors_to_safe_http_responses(client, monkeypatch, error, status):
    test_client, module = client

    class Service:
        def finance(self, user, start, end):
            raise error

    monkeypatch.setattr(module, "_build_analytics", lambda db: Service())

    response = test_client.get(
        "/api/app/analytics/finance?start=2026-08-01&end=2026-08-07",
        headers=auth_headers(),
    )

    assert response.status_code == status
    assert response.get_json() == {"message": str(error)}


def test_resolution_update_reuses_system_error_service(client, monkeypatch):
    test_client, module = client
    called = {}

    monkeypatch.setattr(
        module.system_errors,
        "update_resolution",
        lambda db, report_id, resolution: called.update(id=report_id, resolution=resolution) or True,
    )

    response = test_client.patch(
        "/api/app/system-errors/7/resolution",
        headers=auth_headers(),
        json={"resolution": "更新套件後恢復"},
    )

    assert response.status_code == 200
    assert called == {"id": 7, "resolution": "更新套件後恢復"}


def test_create_weight_log_reuses_body_service_and_rounds_to_one_decimal(client, monkeypatch):
    test_client, module = client
    called = {}

    monkeypatch.setattr(
        module.body,
        "create_weight_log",
        lambda db, user_id, weight_kg, entry_date: called.update(
            user_id=user_id,
            weight_kg=weight_kg,
            entry_date=entry_date,
        ) or 18,
    )

    response = test_client.post(
        "/api/app/body/weight-logs",
        headers=auth_headers(),
        json={"weight_kg": 95.05},
    )

    assert response.status_code == 201
    assert response.get_json() == {"id": 18, "message": "已記錄 95.1 公斤", "weight_kg": 95.1}
    assert called["user_id"] == 1
    assert called["weight_kg"] == 95.1


def test_create_record_maps_duplicate_to_conflict(client, monkeypatch):
    test_client, module = client

    class Records:
        def create(self, kind, user_id, payload, *, allow_duplicate):
            from src.services.app_records import DuplicateRecordError
            raise DuplicateRecordError("發現一筆可能重複的紀錄，確定仍要新增嗎？")

    monkeypatch.setattr(module, "_build_records", lambda db: Records())
    response = test_client.post("/api/app/records/finance", headers=auth_headers(), json={"amount": 100})

    assert response.status_code == 409
    assert response.get_json()["code"] == "DUPLICATE_RECORD"


def test_create_record_passes_manual_nutrition_payload_to_service(client, monkeypatch):
    test_client, module = client
    called = {}

    class Records:
        def create(self, kind, user_id, payload, *, allow_duplicate):
            called.update(
                kind=kind,
                user_id=user_id,
                payload=payload,
                allow_duplicate=allow_duplicate,
            )
            return {"id": 21, "message": "飲食紀錄已新增"}

    monkeypatch.setattr(module, "_build_records", lambda db: Records())
    payload = {
        "description": "雞胸肉便當",
        "water_ml": 800,
        "nutrition_source": "manual",
        "nutrition": {
            "fat_g": 12.34,
            "carbs_g": 65.55,
            "protein_g": 42.04,
            "estimated_calories": 620.5,
        },
    }

    response = test_client.post(
        "/api/app/records/diet",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 201
    assert response.get_json()["id"] == 21
    assert called == {
        "kind": "diet",
        "user_id": 1,
        "payload": payload,
        "allow_duplicate": False,
    }


def test_diet_photo_endpoints_return_recognition_and_nutrition(client, monkeypatch):
    test_client, module = client
    monkeypatch.setattr(module, "_build_llm", lambda: object())
    monkeypatch.setattr(
        module,
        "recognize_diet_photo",
        lambda llm, image_base64, mime_type: {"description": "雞胸肉便當", "uncertain_items": []},
    )
    monkeypatch.setattr(
        module,
        "calculate_diet_nutrition",
        lambda llm, confirmed_description, existing_description, mode: {
            "description": confirmed_description,
            "nutrition": {"estimated_calories": 500},
        },
    )

    recognized = test_client.post(
        "/api/app/diet/recognize-photo",
        headers=auth_headers(),
        json={"image_base64": "abc", "mime_type": "image/jpeg"},
    )
    calculated = test_client.post(
        "/api/app/diet/calculate-nutrition",
        headers=auth_headers(),
        json={"confirmed_description": "雞胸肉便當", "mode": "replace"},
    )

    assert recognized.status_code == 200
    assert recognized.get_json()["description"] == "雞胸肉便當"
    assert calculated.status_code == 200
    assert calculated.get_json()["nutrition"]["estimated_calories"] == 500


def test_update_and_delete_record_use_authenticated_user(client, monkeypatch):
    test_client, module = client
    calls = []

    class Records:
        def update(self, kind, record_id, user_id, payload, *, allow_duplicate):
            calls.append(("update", kind, record_id, user_id, payload))
            return {"id": record_id, "message": "紀錄已更新"}

        def delete(self, kind, record_id, user_id):
            calls.append(("delete", kind, record_id, user_id))
            return {"message": "紀錄已刪除"}

    monkeypatch.setattr(module, "_build_records", lambda db: Records())
    updated = test_client.patch("/api/app/records/mood/8", headers=auth_headers(), json={"content": "今天很好"})
    deleted = test_client.delete("/api/app/records/mood/8", headers=auth_headers())

    assert updated.status_code == 200
    assert deleted.status_code == 200
    assert calls[0][:4] == ("update", "mood", 8, 1)
    assert calls[1] == ("delete", "mood", 8, 1)


@pytest.mark.parametrize("payload", [{}, {"weight_kg": None}, {"weight_kg": "95.1"}, {"weight_kg": 0}, {"weight_kg": -1}, {"weight_kg": float("nan")}])
def test_create_weight_log_rejects_invalid_values(client, payload):
    test_client, _ = client

    response = test_client.post(
        "/api/app/body/weight-logs",
        headers=auth_headers(),
        json=payload,
    )

    assert response.status_code == 400
    assert response.get_json() == {"message": "未取得有效的體重值"}


@pytest.mark.parametrize("weight_kg", [39.9, 150.1])
def test_create_weight_log_rejects_values_outside_allowed_range(client, weight_kg):
    test_client, _ = client

    response = test_client.post(
        "/api/app/body/weight-logs",
        headers=auth_headers(),
        json={"weight_kg": weight_kg},
    )

    assert response.status_code == 400
    assert response.get_json() == {"message": "體重僅能輸入 40.0 到 150.0 公斤"}


def test_analytics_success_and_unknown_module(client, monkeypatch):
    test_client, module = client

    class Service:
        def finance(self, user, start, end):
            return {"has_any_data": False, "daily": []}

    monkeypatch.setattr(module, "_build_analytics", lambda db: Service())
    success = test_client.get(
        "/api/app/analytics/finance?start=2026-08-01&end=2026-08-07",
        headers=auth_headers(),
    )
    missing = test_client.get(
        "/api/app/analytics/unknown?start=2026-08-01&end=2026-08-07",
        headers=auth_headers(),
    )

    assert success.status_code == 200
    assert success.get_json()["range"] == {"start": "2026-08-01", "end": "2026-08-07"}
    assert missing.status_code == 404


def test_technical_sharing_uses_single_date_instead_of_range(client, monkeypatch):
    test_client, module = client

    class Service:
        def skills(self, user, start, end):
            assert start == end
            return {"has_any_data": False, "digests": [], "videos": []}

    monkeypatch.setattr(module, "_build_analytics", lambda db: Service())
    response = test_client.get(
        "/api/app/analytics/skills?date=2026-08-01",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.get_json()["range"] == {"start": "2026-08-01", "end": "2026-08-01"}


def test_resolution_validation_not_found_and_cors(client, monkeypatch):
    test_client, module = client
    monkeypatch.setattr(module.system_errors, "update_resolution", lambda db, report_id, resolution: False)

    empty = test_client.patch(
        "/api/app/system-errors/7/resolution", headers=auth_headers(), json={"resolution": ""}
    )
    too_long = test_client.patch(
        "/api/app/system-errors/7/resolution", headers=auth_headers(), json={"resolution": "a" * 2001}
    )
    missing = test_client.patch(
        "/api/app/system-errors/7/resolution",
        headers={**auth_headers(), "Origin": "http://localhost:8081"},
        json={"resolution": "解法"},
    )

    assert empty.status_code == 400
    assert too_long.status_code == 400
    assert missing.status_code == 404
    assert missing.headers["Access-Control-Allow-Origin"] == "http://localhost:8081"
