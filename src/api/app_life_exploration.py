"""Mobile App Phase 5：旅遊行程、探索地圖與成果展示 API。"""

from collections.abc import Callable
from typing import Any

from flask import Blueprint, Response, g, jsonify, request

from src.api.app_auth import _allowed_origins, require_access_token
from src.api.error_reporting import report_mobile_error
from src.services.app_life_exploration import (
    AppLifeExplorationService,
    LifeNotFoundError,
    LifeValidationError,
)
from src.services.geocoding import (
    GeocodingNotFoundError,
    GeocodingUnavailableError,
    GeocodingValidationError,
    NominatimGeocoder,
)
from submodules.cloudsql.client import CloudSQLClient

app_life_exploration_bp = Blueprint("app_life_exploration", __name__, url_prefix="/api/app/life")


def _service(db: CloudSQLClient) -> AppLifeExplorationService:
    return AppLifeExplorationService(db, NominatimGeocoder(db))


@app_life_exploration_bp.after_request
def add_cors_headers(response: Response) -> Response:
    origin = request.headers.get("Origin")
    if origin and origin in _allowed_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


def _payload() -> dict[str, Any]:
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise LifeValidationError("請確認輸入內容")
    return value


def _run(action: Callable[[AppLifeExplorationService], dict[str, Any]], *, created: bool = False):
    db = None
    try:
        db = CloudSQLClient()
        return jsonify(action(_service(db))), 201 if created else 200
    except LifeValidationError as exc:
        return jsonify({"message": str(exc)}), 400
    except LifeNotFoundError as exc:
        return jsonify({"message": str(exc)}), 404
    except GeocodingValidationError as exc:
        return jsonify({"message": str(exc)}), 400
    except GeocodingNotFoundError as exc:
        return jsonify({"message": str(exc)}), 404
    except GeocodingUnavailableError as exc:
        return jsonify({"message": str(exc)}), 503
    except Exception:  # noqa: BLE001
        report_mobile_error(db, "mobile_life_exploration", g.app_user.database_id)
        return jsonify({"message": "生活探索資料目前無法處理，請稍後再試"}), 503
    finally:
        if db is not None:
            db.close()


@app_life_exploration_bp.get("/trips")
@require_access_token
def list_trips():
    return _run(lambda service: service.list_trips(g.app_user.database_id))


@app_life_exploration_bp.post("/trips")
@require_access_token
def create_trip():
    return _run(lambda service: service.create_trip(g.app_user.database_id, _payload()), created=True)


@app_life_exploration_bp.patch("/trips/<int:trip_id>")
@require_access_token
def update_trip(trip_id: int):
    return _run(lambda service: service.update_trip(trip_id, g.app_user.database_id, _payload()))


@app_life_exploration_bp.delete("/trips/<int:trip_id>")
@require_access_token
def delete_trip(trip_id: int):
    return _run(lambda service: service.delete_trip(trip_id, g.app_user.database_id))


@app_life_exploration_bp.post("/trips/<int:trip_id>/restore")
@require_access_token
def restore_trip(trip_id: int):
    return _run(lambda service: service.restore_trip(trip_id, g.app_user.database_id))


@app_life_exploration_bp.post("/trips/<int:trip_id>/complete")
@require_access_token
def complete_trip(trip_id: int):
    return _run(lambda service: service.complete_trip(trip_id, g.app_user.database_id, _payload()))


@app_life_exploration_bp.post("/collections/<int:item_id>/visit")
@require_access_token
def visit_collection(item_id: int):
    return _run(lambda service: service.visit_collection(item_id, g.app_user.database_id, _payload()), created=True)


@app_life_exploration_bp.get("/exploration")
@require_access_token
def list_exploration():
    return _run(lambda service: service.list_exploration(
        g.app_user.database_id,
        country_name=request.args.get("country"),
        city_name=request.args.get("city"),
    ))


@app_life_exploration_bp.patch("/exploration/<int:event_id>")
@require_access_token
def update_exploration(event_id: int):
    return _run(lambda service: service.update_exploration(event_id, g.app_user.database_id, _payload()))


@app_life_exploration_bp.delete("/exploration/<int:event_id>")
@require_access_token
def delete_exploration(event_id: int):
    return _run(lambda service: service.delete_exploration(event_id, g.app_user.database_id))


@app_life_exploration_bp.post("/exploration/<int:event_id>/restore")
@require_access_token
def restore_exploration(event_id: int):
    return _run(lambda service: service.restore_exploration(event_id, g.app_user.database_id))


@app_life_exploration_bp.post("/exploration/<int:event_id>/relocate")
@require_access_token
def relocate_exploration(event_id: int):
    return _run(lambda service: service.relocate_exploration(event_id, g.app_user.database_id))


@app_life_exploration_bp.get("/achievements")
@require_access_token
def list_achievements():
    return _run(lambda service: service.list_achievements(g.app_user.database_id))


@app_life_exploration_bp.post("/achievements")
@require_access_token
def create_achievement():
    return _run(lambda service: service.create_achievement(g.app_user.database_id, _payload()), created=True)


@app_life_exploration_bp.delete("/achievements/<int:achievement_id>")
@require_access_token
def delete_achievement(achievement_id: int):
    return _run(lambda service: service.delete_achievement(achievement_id, g.app_user.database_id))


@app_life_exploration_bp.post("/achievements/<int:achievement_id>/restore")
@require_access_token
def restore_achievement(achievement_id: int):
    return _run(lambda service: service.restore_achievement(achievement_id, g.app_user.database_id))


@app_life_exploration_bp.post("/achievement-candidates/<int:candidate_id>/decision")
@require_access_token
def decide_achievement(candidate_id: int):
    payload = _payload()
    if not isinstance(payload.get("accept"), bool):
        return jsonify({"message": "請確認成果候選處理方式"}), 400
    return _run(lambda service: service.respond_candidate(
        candidate_id, g.app_user.database_id, payload["accept"]
    ))
