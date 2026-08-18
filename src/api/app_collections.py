"""Mobile App 收藏清單 HTTP API。"""

from flask import Blueprint, Response, g, jsonify, request

from src.api.app_auth import _allowed_origins, require_access_token
from src.api.error_reporting import report_mobile_error
from src.services.app_collections import (
    AppCollectionService,
    CollectionNotFoundError,
    CollectionValidationError,
)
from src.services.geocoding import (
    GeocodingNotFoundError,
    GeocodingUnavailableError,
    GeocodingValidationError,
    NominatimGeocoder,
)
from submodules.cloudsql.client import CloudSQLClient

app_collections_bp = Blueprint("app_collections", __name__, url_prefix="/api/app/collections")


def _report(db, feature: str) -> None:
    report_mobile_error(db, feature, g.app_user.database_id)


def _service(db: CloudSQLClient) -> AppCollectionService:
    return AppCollectionService(db, NominatimGeocoder(db))


@app_collections_bp.after_request
def add_cors_headers(response: Response) -> Response:
    origin = request.headers.get("Origin")
    if origin and origin in _allowed_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


@app_collections_bp.get("")
@require_access_token
def list_collection_items():
    db = None
    try:
        db = CloudSQLClient()
        result = _service(db).list_for_user(
            g.app_user.database_id,
            country_code=request.args.get("country"),
            city_name=request.args.get("city"),
            item_type=request.args.get("type"),
            status=request.args.get("status"),
        )
        return jsonify(result), 200
    except Exception:  # noqa: BLE001
        _report(db, "mobile_collections_list")
        return jsonify({"message": "收藏清單目前無法載入，請稍後再試"}), 503
    finally:
        if db is not None:
            db.close()


@app_collections_bp.post("")
@require_access_token
def create_collection_item():
    return _write(None)


@app_collections_bp.post("/geocode")
@require_access_token
def geocode_collection_address():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "請確認輸入內容"}), 400
    db = None
    try:
        db = CloudSQLClient()
        return jsonify(_service(db).geocode(payload)), 200
    except GeocodingValidationError as exc:
        return jsonify({"message": str(exc)}), 400
    except GeocodingNotFoundError as exc:
        return jsonify({"message": str(exc)}), 404
    except GeocodingUnavailableError as exc:
        return jsonify({"message": str(exc)}), 503
    except Exception:  # noqa: BLE001
        _report(db, "mobile_collections_geocode")
        return jsonify({"message": "地址定位服務目前無法使用，請稍後再試"}), 503
    finally:
        if db is not None:
            db.close()


@app_collections_bp.patch("/<int:item_id>")
@require_access_token
def update_collection_item(item_id: int):
    return _write(item_id)


def _write(item_id: int | None):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"message": "請確認輸入內容"}), 400
    db = None
    try:
        db = CloudSQLClient()
        service = _service(db)
        result = (
            service.create(g.app_user.database_id, payload)
            if item_id is None
            else service.update(item_id, g.app_user.database_id, payload)
        )
        return jsonify(result), 201 if item_id is None else 200
    except CollectionValidationError as exc:
        return jsonify({"message": str(exc)}), 400
    except CollectionNotFoundError as exc:
        return jsonify({"message": str(exc)}), 404
    except Exception:  # noqa: BLE001
        _report(db, "mobile_collections_write")
        return jsonify({"message": "收藏項目目前無法儲存，請稍後再試"}), 503
    finally:
        if db is not None:
            db.close()


@app_collections_bp.delete("/<int:item_id>")
@require_access_token
def delete_collection_item(item_id: int):
    db = None
    try:
        db = CloudSQLClient()
        return jsonify(_service(db).delete(item_id, g.app_user.database_id)), 200
    except CollectionNotFoundError as exc:
        return jsonify({"message": str(exc)}), 404
    except Exception:  # noqa: BLE001
        _report(db, "mobile_collections_delete")
        return jsonify({"message": "收藏項目目前無法刪除，請稍後再試"}), 503
    finally:
        if db is not None:
            db.close()


@app_collections_bp.post("/<int:item_id>/restore")
@require_access_token
def restore_collection_item(item_id: int):
    db = None
    try:
        db = CloudSQLClient()
        return jsonify(_service(db).restore(item_id, g.app_user.database_id)), 200
    except CollectionNotFoundError as exc:
        return jsonify({"message": str(exc)}), 404
    except Exception:  # noqa: BLE001
        _report(db, "mobile_collections_restore")
        return jsonify({"message": "收藏項目目前無法復原，請稍後再試"}), 503
    finally:
        if db is not None:
            db.close()
