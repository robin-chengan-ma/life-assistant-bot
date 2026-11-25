"""Mobile App 待辦事項 HTTP API。"""

import logging

from flask import Blueprint, Response, g, jsonify, request

from src.api.app_auth import require_access_token
from src.api.error_reporting import report_mobile_error
from src.services.app_todo import (
    AppTodoService,
    TodoNotFoundError,
    TodoValidationError,
)
from submodules.cloudsql.client import CloudSQLClient

app_todo_bp = Blueprint("app_todo", __name__, url_prefix="/api/app/todos")
_logger = logging.getLogger(__name__)


def _service(db: CloudSQLClient) -> AppTodoService:
    return AppTodoService(db)


@app_todo_bp.after_request
def add_cors_headers(response: Response) -> Response:
    origin = request.headers.get("Origin")
    if origin in {"http://localhost:8081", "http://127.0.0.1:8081"}:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    return response


@app_todo_bp.get("")
@require_access_token
def list_todos():
    db = None
    try:
        db = CloudSQLClient()
        service = _service(db)
        return jsonify({"items": service.list_for_user(g.app_user.database_id)}), 200
    except Exception:
        _logger.exception("載入 Mobile App 待辦事項失敗")
        report_mobile_error(db, "mobile_todos_list", g.app_user.database_id)
        return jsonify({"message": "待辦事項目前無法載入，請稍後再試"}), 503
    finally:
        if db is not None:
            db.close()


@app_todo_bp.post("")
@require_access_token
def create_todo():
    return _write(None)


@app_todo_bp.patch("/<int:todo_id>")
@require_access_token
def update_todo(todo_id: int):
    return _write(todo_id)


def _write(todo_id: int | None):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "請確認輸入內容"}), 400
    db = None
    try:
        db = CloudSQLClient()
        service = _service(db)
        result = service.create(g.app_user.database_id, payload) if todo_id is None else service.update(todo_id, g.app_user.database_id, payload)
        return jsonify(result), 201 if todo_id is None else 200
    except TodoValidationError as exc:
        return jsonify({"message": str(exc)}), 400
    except TodoNotFoundError as exc:
        return jsonify({"message": str(exc)}), 404
    except Exception:  # noqa: BLE001
        report_mobile_error(db, "mobile_todos_write", g.app_user.database_id)
        return jsonify({"message": "待辦事項目前無法儲存，請稍後再試"}), 503
    finally:
        if db is not None:
            db.close()


@app_todo_bp.delete("/<int:todo_id>")
@require_access_token
def delete_todo(todo_id: int):
    db = None
    try:
        db = CloudSQLClient()
        return jsonify(_service(db).delete(todo_id, g.app_user.database_id)), 200
    except TodoNotFoundError as exc:
        return jsonify({"message": str(exc)}), 404
    except Exception:  # noqa: BLE001
        report_mobile_error(db, "mobile_todos_delete", g.app_user.database_id)
        return jsonify({"message": "待辦事項目前無法刪除，請稍後再試"}), 503
    finally:
        if db is not None:
            db.close()
