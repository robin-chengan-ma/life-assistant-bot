"""Mobile App 重要日子設定 HTTP API。"""

import logging

from flask import Blueprint, Response, g, jsonify, request

from src.api.app_auth import require_access_token
from src.services.app_important_days import (
    AppImportantDayService,
    ImportantDayNotFoundError,
    ImportantDayValidationError,
)
from submodules.cloudsql.client import CloudSQLClient

app_important_days_bp = Blueprint("app_important_days", __name__, url_prefix="/api/app/important-days")
_logger = logging.getLogger(__name__)


def _service(db: CloudSQLClient) -> AppImportantDayService:
    return AppImportantDayService(db)


@app_important_days_bp.after_request
def add_cors_headers(response: Response) -> Response:
    origin = request.headers.get("Origin")
    if origin in {"http://localhost:8081", "http://127.0.0.1:8081"}:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    return response


@app_important_days_bp.get("")
@require_access_token
def list_important_days():
    db = None
    try:
        db = CloudSQLClient()
        service = _service(db)
        return jsonify({"items": service.list_for_user(g.app_user.database_id), "users": service.family_users()}), 200
    except Exception:  # noqa: BLE001
        _logger.exception("載入 Mobile App 重要日子失敗")
        return jsonify({"message": "重要日子目前無法載入，請稍後再試"}), 503
    finally:
        if db is not None:
            db.close()


@app_important_days_bp.post("")
@require_access_token
def create_important_day():
    return _write(None)


@app_important_days_bp.patch("/<int:important_day_id>")
@require_access_token
def update_important_day(important_day_id: int):
    return _write(important_day_id)


def _write(important_day_id: int | None):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "請確認輸入內容"}), 400
    db = None
    try:
        db = CloudSQLClient()
        service = _service(db)
        result = service.create(g.app_user.database_id, payload) if important_day_id is None else service.update(important_day_id, g.app_user.database_id, payload)
        return jsonify(result), 201 if important_day_id is None else 200
    except ImportantDayValidationError as exc:
        return jsonify({"message": str(exc)}), 400
    except ImportantDayNotFoundError as exc:
        return jsonify({"message": str(exc)}), 404
    except Exception:  # noqa: BLE001
        return jsonify({"message": "重要日子目前無法儲存，請稍後再試"}), 503
    finally:
        if db is not None:
            db.close()


@app_important_days_bp.delete("/<int:important_day_id>")
@require_access_token
def delete_important_day(important_day_id: int):
    db = None
    try:
        db = CloudSQLClient()
        return jsonify(_service(db).delete(important_day_id, g.app_user.database_id)), 200
    except ImportantDayNotFoundError as exc:
        return jsonify({"message": str(exc)}), 404
    except Exception:  # noqa: BLE001
        return jsonify({"message": "重要日子目前無法刪除，請稍後再試"}), 503
    finally:
        if db is not None:
            db.close()
