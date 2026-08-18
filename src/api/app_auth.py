"""Mobile App 認證 HTTP API（FR-65）。"""

from __future__ import annotations

import logging
import os
from functools import wraps

from flask import Blueprint, Response, g, jsonify, request

from src.api.error_reporting import report_mobile_error
from src.services.app_auth import (
    AppAuthService,
    AuthSession,
    InvalidAccessTokenError,
    InvalidNewPasswordError,
    InvalidPasswordError,
    InvalidPreferenceError,
    InvalidRefreshTokenError,
    PasswordDeliveryError,
    ReusedPasswordError,
    UnknownUserError,
)
from submodules.cloudsql.client import CloudSQLClient
from submodules.telegram.client import TelegramClient

app_bp = Blueprint("app_api", __name__, url_prefix="/api/app")
logger = logging.getLogger("robinson.app_api.auth")

_GENERIC_BAD_REQUEST = "請確認輸入資料是否完整"
_GENERIC_UNAVAILABLE = "服務暫時無法使用，請稍後再試"
_DEFAULT_LOCAL_CORS_ORIGINS = "http://localhost:8081,http://127.0.0.1:8081"


def _build_service(db: CloudSQLClient) -> AppAuthService:
    secret = os.environ.get("APP_JWT_SECRET", "")
    bcrypt_rounds = int(os.environ.get("APP_BCRYPT_ROUNDS", "12"))
    return AppAuthService(db, jwt_secret=secret, bcrypt_rounds=bcrypt_rounds)


def _session_response(session: AuthSession, message: str) -> tuple[Response, int]:
    payload = {
        "message": message,
        "access_token": session.access_token,
        "access_token_expires_in": session.access_token_expires_in,
        "refresh_token": session.refresh_token,
        "user": session.user.to_dict(),
    }
    return jsonify(payload), 200


def _json_object() -> dict | None:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


def _unexpected_error(feature: str, db=None, affected_user_id: int | None = None) -> tuple[Response, int]:
    logger.exception("Mobile App 認證 API 發生未預期錯誤")
    report_mobile_error(db, feature, affected_user_id)
    return jsonify({"message": _GENERIC_UNAVAILABLE}), 503


def _allowed_origins() -> set[str]:
    configured = os.environ.get("APP_CORS_ORIGINS", _DEFAULT_LOCAL_CORS_ORIGINS)
    return {origin.strip() for origin in configured.split(",") if origin.strip()}


@app_bp.after_request
def add_cors_headers(response: Response) -> Response:
    """只允許明確列入白名單的 Expo Web origin；原生 App 請求不受 CORS 影響。"""
    origin = request.headers.get("Origin")
    if origin and origin in _allowed_origins():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


def require_access_token(handler):
    @wraps(handler)
    def wrapped(*args, **kwargs):
        authorization = request.headers.get("Authorization", "")
        scheme, _, access_token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not access_token:
            return jsonify({"message": "請先登入"}), 401

        db = None
        try:
            db = CloudSQLClient()
            g.app_user = _build_service(db).authenticate_access_token(access_token)
        except InvalidAccessTokenError:
            return jsonify({"message": "登入已過期，請重新登入"}), 401
        except Exception:  # noqa: BLE001 - HTTP 邊界需隔離技術錯誤，避免洩漏 Stack Trace
            return _unexpected_error("mobile_authenticate", db)
        finally:
            if db is not None:
                db.close()
        return handler(*args, **kwargs)

    return wrapped


@app_bp.post("/auth/login")
def login():
    payload = _json_object()
    if payload is None:
        return jsonify({"message": _GENERIC_BAD_REQUEST}), 400
    user_id = payload.get("user_id")
    password = payload.get("password")
    keep_logged_in = payload.get("keep_logged_in", False)
    if (
        not isinstance(user_id, str)
        or not user_id.strip()
        or not isinstance(password, str)
        or not password
        or not isinstance(keep_logged_in, bool)
    ):
        return jsonify({"message": _GENERIC_BAD_REQUEST}), 400

    db = None
    try:
        db = CloudSQLClient()
        session = _build_service(db).login(
            user_id,
            password,
            keep_logged_in=keep_logged_in,
        )
        return _session_response(session, "身份驗證成功，歡迎使用羅賓森")
    except UnknownUserError:
        return jsonify({"code": "UNKNOWN_USER", "message": "很抱歉，我無法辨識您"}), 401
    except InvalidPasswordError:
        return (
            jsonify(
                {
                    "code": "INVALID_PASSWORD",
                    "message": "很抱歉，您輸入的密碼有誤，若真的想不起來密碼，可以使用忘記密碼功能",
                }
            ),
            401,
        )
    except Exception:  # noqa: BLE001 - HTTP 邊界統一轉成安全錯誤訊息
        return _unexpected_error("mobile_login", db)
    finally:
        if db is not None:
            db.close()


@app_bp.post("/auth/identify")
def identify():
    payload = _json_object()
    user_id = payload.get("user_id") if payload else None
    if not isinstance(user_id, str) or not user_id.strip():
        return jsonify({"message": _GENERIC_BAD_REQUEST}), 400

    db = None
    try:
        db = CloudSQLClient()
        _build_service(db).identify_user(user_id)
        return jsonify({"recognized": True}), 200
    except UnknownUserError:
        return jsonify({"code": "UNKNOWN_USER", "message": "很抱歉，我無法辨識您"}), 401
    except Exception:  # noqa: BLE001 - HTTP 邊界統一轉成安全錯誤訊息
        return _unexpected_error("mobile_identify", db)
    finally:
        if db is not None:
            db.close()


@app_bp.post("/auth/forgot-password")
def forgot_password():
    payload = _json_object()
    user_id = payload.get("user_id") if payload else None
    if not isinstance(user_id, str) or not user_id.strip():
        return jsonify({"message": _GENERIC_BAD_REQUEST}), 400

    db = None
    try:
        db = CloudSQLClient()
        service = _build_service(db)
        telegram_client = TelegramClient(os.environ["TELEGRAM_BOT_TOKEN"])

        def deliver_password(chat_id: int, password: str) -> None:
            telegram_client.send_text(
                chat_id=chat_id,
                text=(
                    f"你的羅賓森 App 新密碼是：{password}\n"
                    "請登入後妥善保管；若不是你本人操作，請立即通知 Robin。"
                ),
            )

        service.reset_password(user_id, deliver_password)
        return jsonify({"message": "新密碼已透過 Telegram 傳送"}), 200
    except UnknownUserError:
        return jsonify({"code": "UNKNOWN_USER", "message": "很抱歉，我無法辨識您"}), 401
    except PasswordDeliveryError:
        return (
            jsonify(
                {
                    "code": "PASSWORD_DELIVERY_FAILED",
                    "message": "目前無法透過 Telegram 傳送新密碼，請聯絡 Robin",
                }
            ),
            503,
        )
    except Exception:  # noqa: BLE001 - HTTP 邊界統一轉成安全錯誤訊息
        return _unexpected_error("mobile_forgot_password", db)
    finally:
        if db is not None:
            db.close()


@app_bp.post("/auth/refresh")
def refresh():
    payload = _json_object()
    refresh_token = payload.get("refresh_token") if payload else None
    if not isinstance(refresh_token, str) or not refresh_token:
        return jsonify({"message": _GENERIC_BAD_REQUEST}), 400

    db = None
    try:
        db = CloudSQLClient()
        session = _build_service(db).refresh(refresh_token)
        return _session_response(session, "登入狀態已更新")
    except InvalidRefreshTokenError:
        return jsonify({"message": "登入已過期，請重新登入"}), 401
    except Exception:  # noqa: BLE001 - HTTP 邊界統一轉成安全錯誤訊息
        return _unexpected_error("mobile_refresh", db)
    finally:
        if db is not None:
            db.close()


@app_bp.get("/auth/me")
@require_access_token
def me():
    return jsonify({"user": g.app_user.to_dict()}), 200


@app_bp.post("/auth/change-password")
@require_access_token
def change_password():
    payload = _json_object()
    current_password = payload.get("current_password") if payload else None
    new_password = payload.get("new_password") if payload else None
    if (
        not isinstance(current_password, str)
        or not current_password
        or not isinstance(new_password, str)
        or not new_password
    ):
        return jsonify({"message": _GENERIC_BAD_REQUEST}), 400

    db = None
    try:
        db = CloudSQLClient()
        _build_service(db).change_password(
            g.app_user.database_id,
            current_password,
            new_password,
        )
        return jsonify({"message": "密碼修改成功，請使用新密碼重新登入"}), 200
    except InvalidPasswordError:
        return jsonify({"code": "INVALID_CURRENT_PASSWORD", "message": "目前密碼輸入錯誤"}), 400
    except InvalidNewPasswordError:
        return (
            jsonify(
                {
                    "code": "INVALID_NEW_PASSWORD",
                    "message": "新密碼須為 8～15 個字元，包含大小寫英文字母、數字及特殊符號，且不可含空白",
                }
            ),
            400,
        )
    except ReusedPasswordError:
        return jsonify({"code": "REUSED_PASSWORD", "message": "不能使用目前或曾經使用過的密碼"}), 409
    except Exception:  # noqa: BLE001 - HTTP 邊界統一轉成安全錯誤訊息
        return _unexpected_error("mobile_change_password", db, g.app_user.database_id)
    finally:
        if db is not None:
            db.close()


@app_bp.post("/auth/logout")
@require_access_token
def logout():
    db = None
    try:
        db = CloudSQLClient()
        _build_service(db).logout(g.app_user.database_id)
        return jsonify({"message": "已登出"}), 200
    except Exception:  # noqa: BLE001 - HTTP 邊界統一轉成安全錯誤訊息
        return _unexpected_error("mobile_logout", db, g.app_user.database_id)
    finally:
        if db is not None:
            db.close()


@app_bp.post("/auth/preferences")
@require_access_token
def update_preferences():
    payload = _json_object()
    theme_preference = payload.get("theme_preference") if payload else None
    font_size_preference = payload.get("font_size_preference") if payload else None
    privacy_mask_enabled = payload.get("privacy_mask_enabled") if payload else None

    db = None
    try:
        db = CloudSQLClient()
        user = _build_service(db).update_preferences(
            g.app_user.database_id,
            theme_preference=theme_preference,
            font_size_preference=font_size_preference,
            privacy_mask_enabled=privacy_mask_enabled,
        )
        return jsonify({"message": "APP 設定已儲存", "user": user.to_dict()}), 200
    except InvalidPreferenceError:
        return jsonify({"message": "請確認 APP 設定選項"}), 400
    except Exception:  # noqa: BLE001 - HTTP 邊界統一轉成安全錯誤訊息
        return _unexpected_error("mobile_preferences", db, g.app_user.database_id)
    finally:
        if db is not None:
            db.close()
