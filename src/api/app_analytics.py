"""FR-64 Mobile App Dashboard 與唯讀分析 HTTP API。"""

import logging
import math
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, g, jsonify, request

from src.api.app_auth import require_access_token
from src.bot import body, system_errors
from src.services.app_analytics import (
    AppAnalyticsService,
    DateRangeError,
    FeatureDisabledError,
    ForbiddenModuleError,
    parse_calendar_month,
    parse_date_range,
    parse_single_date,
    parse_todo_date_range,
)
from src.services.app_diet_photo import (
    DietPhotoError,
    calculate_diet_nutrition,
    recognize_diet_photo,
)
from src.services.app_records import (
    AppRecordService,
    DuplicateRecordError,
    HistoricalRecordError,
    RecordNotFoundError,
    RecordValidationError,
)
from submodules.cloudsql.client import CloudSQLClient
from submodules.llm.client import LLMClient

app_analytics_bp = Blueprint("app_analytics", __name__, url_prefix="/api/app")
_logger = logging.getLogger(__name__)
_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_ANALYTICS_METHODS = {
    "todos": "todos",
    "body": "body",
    "finance": "finance",
    "mood": "mood",
    "jobs": "jobs",
    "exams": "exams",
    "skills": "skills",
    "complaints": "complaints",
}


def _allowed_origins() -> set[str]:
    configured = os.getenv("APP_CORS_ORIGINS", "http://localhost:8081,http://127.0.0.1:8081")
    return {origin.strip() for origin in configured.split(",") if origin.strip()}


@app_analytics_bp.after_request
def add_cors_headers(response: Response) -> Response:
    origin = request.headers.get("Origin")
    if origin and origin in _allowed_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


def _build_analytics(db: CloudSQLClient) -> AppAnalyticsService:
    return AppAnalyticsService(db, sync_calendar=True)


def _unexpected_error() -> tuple[Response, int]:
    return jsonify({"message": "資料目前無法載入，請稍後再試"}), 503


def _build_records(db: CloudSQLClient) -> AppRecordService:
    api_key = os.environ.get("GEMINI_API_BOT_KEY")
    return AppRecordService(db, llm_client=LLMClient(api_key=api_key) if api_key else None)


def _build_llm() -> LLMClient:
    api_key = os.environ.get("GEMINI_API_BOT_KEY")
    if not api_key:
        raise DietPhotoError("飲食辨識功能尚未設定")
    return LLMClient(api_key=api_key)


@app_analytics_bp.get("/dashboard")
@require_access_token
def dashboard():
    db = None
    try:
        db = CloudSQLClient()
        return jsonify(_build_analytics(db).dashboard(g.app_user)), 200
    except Exception:  # noqa: BLE001 - HTTP 邊界不得洩漏資料庫或程式細節
        _logger.exception("載入 Mobile App 首頁資料失敗")
        return _unexpected_error()
    finally:
        if db is not None:
            db.close()


@app_analytics_bp.get("/analytics/<module_key>")
@require_access_token
def analytics(module_key: str):
    method_name = _ANALYTICS_METHODS.get(module_key)
    if method_name is None:
        return jsonify({"message": "找不到指定頁面"}), 404

    try:
        if module_key == "skills":
            selected = parse_single_date(
                request.args.get("date", ""),
                today=datetime.now(_TAIWAN_TZ).date(),
            )
        elif module_key == "todos":
            selected = parse_todo_date_range(
                request.args.get("start", ""),
                request.args.get("end", ""),
            )
            calendar_range = parse_calendar_month(request.args.get("calendar_month", ""))
        else:
            selected = parse_date_range(
                request.args.get("start", ""),
                request.args.get("end", ""),
                today=datetime.now(_TAIWAN_TZ).date(),
            )
    except DateRangeError as exc:
        return jsonify({"message": str(exc)}), 400

    db = None
    try:
        db = CloudSQLClient()
        service = _build_analytics(db)
        if module_key == "todos":
            payload = service.todos(
                g.app_user,
                selected.start,
                selected.end,
                calendar_start=calendar_range.start,
                calendar_end=calendar_range.end,
            )
        else:
            payload = getattr(service, method_name)(g.app_user, selected.start, selected.end)
        return jsonify({"range": {"start": selected.start.isoformat(), "end": selected.end.isoformat()}, **payload}), 200
    except FeatureDisabledError as exc:
        return jsonify({"message": str(exc)}), 409
    except ForbiddenModuleError as exc:
        return jsonify({"message": str(exc)}), 403
    except Exception:  # noqa: BLE001 - HTTP 邊界不得洩漏資料庫或程式細節
        _logger.exception("載入 Mobile App %s 分析失敗", module_key)
        return _unexpected_error()
    finally:
        if db is not None:
            db.close()


@app_analytics_bp.patch("/system-errors/<int:report_id>/resolution")
@require_access_token
def update_error_resolution(report_id: int):
    if not g.app_user.is_owner:
        return jsonify({"message": "您沒有權限執行此操作"}), 403

    payload = request.get_json(silent=True)
    resolution = payload.get("resolution", "").strip() if isinstance(payload, dict) else ""
    if not resolution:
        return jsonify({"message": "請輸入解法"}), 400
    if len(resolution) > 2000:
        return jsonify({"message": "解法不可超過 2000 個字元"}), 400

    db = None
    try:
        db = CloudSQLClient()
        updated = system_errors.update_resolution(db, report_id, resolution)
        if not updated:
            return jsonify({"message": "找不到指定錯誤紀錄"}), 404
        return jsonify({"message": "解法已更新"}), 200
    except Exception:  # noqa: BLE001 - HTTP 邊界不得洩漏資料庫或程式細節
        return _unexpected_error()
    finally:
        if db is not None:
            db.close()


@app_analytics_bp.post("/body/weight-logs")
@require_access_token
def create_weight_log():
    payload = request.get_json(silent=True)
    value = payload.get("weight_kg") if isinstance(payload, dict) else None
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        return jsonify({"message": "未取得有效的體重值"}), 400

    if value < 40 or value > 150:
        return jsonify({"message": "體重僅能輸入 40.0 到 150.0 公斤"}), 400

    weight_kg = round(float(value) + 1e-9, 1)
    db = None
    try:
        db = CloudSQLClient()
        log_id = body.create_weight_log(
            db,
            g.app_user.database_id,
            weight_kg,
            datetime.now(_TAIWAN_TZ).date(),
        )
        return jsonify({"id": log_id, "message": f"已記錄 {weight_kg:.1f} 公斤", "weight_kg": weight_kg}), 201
    except Exception:  # noqa: BLE001 - HTTP 邊界不得洩漏資料庫或程式細節
        return _unexpected_error()
    finally:
        if db is not None:
            db.close()


@app_analytics_bp.post("/diet/recognize-photo")
@require_access_token
def recognize_diet_image():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "請先拍照或選擇照片"}), 400
    try:
        return jsonify(recognize_diet_photo(_build_llm(), payload.get("image_base64"), payload.get("mime_type"))), 200
    except DietPhotoError as exc:
        return jsonify({"message": str(exc)}), 400


@app_analytics_bp.post("/diet/calculate-nutrition")
@require_access_token
def calculate_diet_image_nutrition():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "請先確認飲食內容"}), 400
    try:
        return jsonify(calculate_diet_nutrition(
            _build_llm(),
            payload.get("confirmed_description"),
            existing_description=payload.get("existing_description"),
            mode=payload.get("mode", "replace"),
        )), 200
    except DietPhotoError as exc:
        return jsonify({"message": str(exc)}), 400


@app_analytics_bp.post("/records/<kind>")
@require_access_token
def create_record(kind: str):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "請輸入紀錄內容"}), 400
    db = None
    try:
        db = CloudSQLClient()
        result = _build_records(db).create(
            kind,
            g.app_user.database_id,
            payload,
            allow_duplicate=payload.get("allow_duplicate") is True,
        )
        return jsonify(result), 201
    except DuplicateRecordError as exc:
        return jsonify({"code": "DUPLICATE_RECORD", "message": str(exc)}), 409
    except RecordValidationError as exc:
        return jsonify({"message": str(exc)}), 400
    except Exception:  # noqa: BLE001
        return _unexpected_error()
    finally:
        if db is not None:
            db.close()


@app_analytics_bp.patch("/records/<kind>/<int:record_id>")
@require_access_token
def update_record(kind: str, record_id: int):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "請輸入紀錄內容"}), 400
    return _mutate_record(kind, record_id, payload)


@app_analytics_bp.delete("/records/<kind>/<int:record_id>")
@require_access_token
def delete_record(kind: str, record_id: int):
    return _mutate_record(kind, record_id, None)


def _mutate_record(kind: str, record_id: int, payload: dict | None):
    db = None
    try:
        db = CloudSQLClient()
        service = _build_records(db)
        result = (
            service.delete(kind, record_id, g.app_user.database_id)
            if payload is None
            else service.update(
                kind,
                record_id,
                g.app_user.database_id,
                payload,
                allow_duplicate=payload.get("allow_duplicate") is True,
            )
        )
        return jsonify(result), 200
    except DuplicateRecordError as exc:
        return jsonify({"code": "DUPLICATE_RECORD", "message": str(exc)}), 409
    except RecordValidationError as exc:
        return jsonify({"message": str(exc)}), 400
    except HistoricalRecordError as exc:
        return jsonify({"message": str(exc)}), 403
    except RecordNotFoundError as exc:
        return jsonify({"message": str(exc)}), 404
    except Exception:  # noqa: BLE001
        return _unexpected_error()
    finally:
        if db is not None:
            db.close()
