from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import bcrypt
import pytest
from flask import Flask

from src.api import app_auth
from src.services.app_auth import (
    AppAuthService,
    InvalidAccessTokenError,
    InvalidNewPasswordError,
    InvalidPasswordError,
    InvalidPreferenceError,
    InvalidRefreshTokenError,
    PasswordDeliveryError,
    ReusedPasswordError,
    UnknownUserError,
)
from tests.bot.conftest import FakeCloudSQLClient

JWT_SECRET = "test-secret-that-is-at-least-32-bytes-long"


@pytest.fixture
def fake_db():
    return FakeCloudSQLClient()


def _service(fake_db, **overrides):
    return AppAuthService(
        fake_db,
        jwt_secret=JWT_SECRET,
        bcrypt_rounds=4,
        **overrides,
    )


def _seed_user(fake_db, *, user_id=1, password=None, telegram_user_id=1001):
    data = {
        "id": user_id,
        "telegram_user_id": telegram_user_id,
        "role": "Robin" if user_id == 1 else "爸爸",
        "is_owner": user_id == 1,
        "password_hash": None,
        "password_changed_at": None,
        "refresh_token_hash": None,
        "refresh_token_expires_at": None,
        "gender": "male" if user_id == 1 else None,
        "previous_login_at": None,
        "current_login_at": None,
        "theme_preference": "light",
        "font_size_preference": "medium",
        "privacy_mask_enabled": False,
    }
    if password is not None:
        data["password_hash"] = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()
    fake_db.insert("users", data)
    return data


@pytest.mark.parametrize(
    ("database_id", "expected"),
    [(1, "user01"), (9, "user09"), (10, "user10"), (123, "user123")],
)
def test_format_app_user_id_uses_user_prefix_and_two_digit_minimum(database_id, expected):
    assert AppAuthService.format_app_user_id(database_id) == expected


def test_service_rejects_weak_jwt_secret_and_invalid_bcrypt_rounds(fake_db):
    with pytest.raises(ValueError):
        AppAuthService(fake_db, jwt_secret="too-short")
    with pytest.raises(ValueError):
        AppAuthService(fake_db, jwt_secret=JWT_SECRET, bcrypt_rounds=3)


def test_format_app_user_id_rejects_non_positive_database_id():
    with pytest.raises(ValueError):
        AppAuthService.format_app_user_id(0)


@pytest.mark.parametrize("app_user_id", ["", "user1", "user001", "admin01", "user-1", "userAA"])
def test_unknown_or_noncanonical_app_user_id_is_rejected(fake_db, app_user_id):
    with pytest.raises(UnknownUserError):
        _service(fake_db).login(app_user_id, "anything", keep_logged_in=False)


def test_non_string_app_user_id_is_rejected(fake_db):
    with pytest.raises(UnknownUserError):
        _service(fake_db).login(1, "anything", keep_logged_in=False)


def test_login_rejects_unknown_user_with_identity_error(fake_db):
    with pytest.raises(UnknownUserError):
        _service(fake_db).login("user99", "anything", keep_logged_in=False)


def test_identify_user_accepts_existing_user_without_requiring_password(fake_db):
    _seed_user(fake_db)

    _service(fake_db).identify_user("user01")


def test_identify_user_rejects_unknown_user(fake_db):
    with pytest.raises(UnknownUserError):
        _service(fake_db).identify_user("user99")


def test_login_rejects_user_without_initial_password(fake_db):
    _seed_user(fake_db)

    with pytest.raises(InvalidPasswordError):
        _service(fake_db).login("user01", "anything", keep_logged_in=False)


def test_login_rejects_wrong_password(fake_db):
    _seed_user(fake_db, password="correct-password")

    with pytest.raises(InvalidPasswordError):
        _service(fake_db).login("user01", "wrong-password", keep_logged_in=False)


def test_login_without_keep_logged_in_returns_only_access_token(fake_db):
    _seed_user(fake_db, password="correct-password")
    service = _service(fake_db)

    session = service.login("USER01", "correct-password", keep_logged_in=False)

    assert session.user.app_user_id == "user01"
    assert session.user.role == "Robin"
    assert session.user.gender == "male"
    assert session.user.previous_login_at is None
    assert session.user.current_login_at is not None
    assert session.access_token
    assert session.refresh_token is None
    authenticated = service.authenticate_access_token(session.access_token)
    assert authenticated.database_id == 1


def test_login_with_keep_logged_in_stores_hashed_refresh_token_for_30_days(fake_db):
    _seed_user(fake_db, password="correct-password")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    service = _service(fake_db, now_factory=lambda: now)

    session = service.login("user01", "correct-password", keep_logged_in=True)

    assert session.refresh_token
    stored = fake_db.select("users", where="id = %s", params=(1,), fetch_one=True)
    assert stored["refresh_token_hash"] != session.refresh_token
    assert bcrypt.checkpw(
        session.refresh_token.encode(), stored["refresh_token_hash"].encode()
    )
    assert stored["refresh_token_expires_at"] == now + timedelta(days=30)
    assert stored["previous_login_at"] is None
    assert stored["current_login_at"] == now


def test_login_rotates_previous_and_current_login_times_without_refresh_changes(fake_db):
    _seed_user(fake_db, password="correct-password")
    first_login = datetime(2026, 8, 10, 1, 2, 3, tzinfo=timezone.utc)
    second_login = datetime(2026, 8, 11, 4, 5, 6, tzinfo=timezone.utc)
    now_values = iter((first_login, first_login, second_login, second_login))
    service = _service(fake_db, now_factory=lambda: next(now_values))

    first = service.login("user01", "correct-password", keep_logged_in=False)
    second = service.login("user01", "correct-password", keep_logged_in=False)

    assert first.user.previous_login_at is None
    assert first.user.current_login_at == first_login
    assert second.user.previous_login_at == first_login
    assert second.user.current_login_at == second_login


def test_access_token_rejects_refresh_token(fake_db):
    _seed_user(fake_db, password="correct-password")
    service = _service(fake_db)
    session = service.login("user01", "correct-password", keep_logged_in=True)

    with pytest.raises(InvalidAccessTokenError):
        service.authenticate_access_token(session.refresh_token)

    wrong_type_jwt = service._issue_jwt(1, token_type="refresh", ttl=timedelta(minutes=1))
    with pytest.raises(InvalidAccessTokenError):
        service.authenticate_access_token(wrong_type_jwt)


def test_refresh_rotates_both_tokens_and_invalidates_previous_refresh_token(fake_db):
    _seed_user(fake_db, password="correct-password")
    service = _service(fake_db)
    first = service.login("user01", "correct-password", keep_logged_in=True)

    second = service.refresh(first.refresh_token)

    assert second.access_token != first.access_token
    assert second.refresh_token != first.refresh_token
    assert service.authenticate_access_token(second.access_token).database_id == 1
    with pytest.raises(InvalidRefreshTokenError):
        service.refresh(first.refresh_token)


def test_refresh_rejects_database_expiration_even_when_jwt_is_still_valid(fake_db):
    _seed_user(fake_db, password="correct-password")
    service = _service(fake_db)
    session = service.login("user01", "correct-password", keep_logged_in=True)
    fake_db.update(
        "users",
        {"refresh_token_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)},
        where="id = %s",
        params=(1,),
    )

    with pytest.raises(InvalidRefreshTokenError):
        service.refresh(session.refresh_token)


def test_refresh_rejects_token_for_deleted_user(fake_db):
    _seed_user(fake_db, password="correct-password")
    service = _service(fake_db)
    session = service.login("user01", "correct-password", keep_logged_in=True)
    fake_db.delete("users", where="id = %s", params=(1,))

    with pytest.raises(InvalidRefreshTokenError):
        service.refresh(session.refresh_token)


@pytest.mark.parametrize("refresh_token", [None, "", "abc", "abc.secret", "0.secret", "1."])
def test_refresh_rejects_malformed_token(fake_db, refresh_token):
    with pytest.raises(InvalidRefreshTokenError):
        _service(fake_db).refresh(refresh_token)


def test_access_token_rejects_empty_or_deleted_user(fake_db):
    _seed_user(fake_db, password="correct-password")
    service = _service(fake_db)
    session = service.login("user01", "correct-password", keep_logged_in=False)

    with pytest.raises(InvalidAccessTokenError):
        service.authenticate_access_token("")

    fake_db.delete("users", where="id = %s", params=(1,))
    with pytest.raises(InvalidAccessTokenError):
        service.authenticate_access_token(session.access_token)


def test_access_token_rejects_non_positive_subject(fake_db):
    service = _service(fake_db)
    token = service._issue_jwt(0, token_type="access", ttl=timedelta(minutes=1))

    with pytest.raises(InvalidAccessTokenError):
        service.authenticate_access_token(token)


def test_claim_user_id_rejects_missing_subject():
    with pytest.raises(InvalidAccessTokenError):
        AppAuthService._claim_user_id({}, InvalidAccessTokenError)


def test_password_match_handles_invalid_types_and_invalid_hash():
    assert AppAuthService._password_matches(None, "hash") is False
    assert AppAuthService._password_matches("password", "not-bcrypt") is False


def test_naive_now_factory_is_normalized_to_utc(fake_db):
    naive_now = datetime(2026, 8, 10, 12, 0, 0)  # noqa: DTZ001 - 刻意測試 naive datetime
    service = _service(fake_db, now_factory=lambda: naive_now)
    _seed_user(fake_db)

    service.reset_password("user01", MagicMock())

    stored = fake_db.select("users", where="id = %s", params=(1,), fetch_one=True)
    assert stored["password_changed_at"] == naive_now.replace(tzinfo=timezone.utc)


def test_logout_revokes_stored_refresh_token(fake_db):
    _seed_user(fake_db, password="correct-password")
    service = _service(fake_db)
    session = service.login("user01", "correct-password", keep_logged_in=True)

    service.logout(1)

    stored = fake_db.select("users", where="id = %s", params=(1,), fetch_one=True)
    assert stored["refresh_token_hash"] is None
    assert stored["refresh_token_expires_at"] is None
    with pytest.raises(InvalidRefreshTokenError):
        service.refresh(session.refresh_token)


def test_update_preferences_persists_and_returns_updated_identity(fake_db):
    _seed_user(fake_db, password="Current1!")

    user = _service(fake_db).update_preferences(
        1,
        theme_preference="dark",
        font_size_preference="large",
        privacy_mask_enabled=True,
    )

    stored = fake_db.select("users", where="id = %s", params=(1,), fetch_one=True)
    assert stored["theme_preference"] == "dark"
    assert stored["font_size_preference"] == "large"
    assert stored["privacy_mask_enabled"] is True
    assert user.theme_preference == "dark"
    assert user.font_size_preference == "large"
    assert user.privacy_mask_enabled is True


@pytest.mark.parametrize(
    ("theme", "font_size", "privacy_mask"),
    [("system", "medium", False), ("light", "huge", False), ("light", "medium", 1)],
)
def test_update_preferences_rejects_values_outside_whitelist(
    fake_db, theme, font_size, privacy_mask
):
    _seed_user(fake_db)

    with pytest.raises(InvalidPreferenceError):
        _service(fake_db).update_preferences(
            1,
            theme_preference=theme,
            font_size_preference=font_size,
            privacy_mask_enabled=privacy_mask,
        )


def test_reset_password_updates_hash_and_sends_plaintext_only_to_telegram(fake_db):
    _seed_user(fake_db)
    sent = []
    now = datetime.now(timezone.utc).replace(microsecond=0)
    service = _service(
        fake_db,
        now_factory=lambda: now,
        temporary_password_factory=lambda: "TempPass9347",
    )

    service.reset_password("user01", lambda chat_id, password: sent.append((chat_id, password)))

    assert sent == [(1001, "TempPass9347")]
    stored = fake_db.select("users", where="id = %s", params=(1,), fetch_one=True)
    assert stored["password_hash"] != "TempPass9347"
    assert bcrypt.checkpw(b"TempPass9347", stored["password_hash"].encode())
    assert stored["password_changed_at"] == now
    assert stored["refresh_token_hash"] is None
    assert stored["refresh_token_expires_at"] is None


@pytest.mark.parametrize(
    "new_password",
    [
        "Short1!",
        "toolongPassword1!",
        "lowercase1!",
        "UPPERCASE1!",
        "NoNumber!",
        "NoSpecial1",
        "Has Space1!",
    ],
)
def test_change_password_rejects_passwords_outside_confirmed_strength_rules(
    fake_db, new_password
):
    _seed_user(fake_db, password="Current1!")

    with pytest.raises(InvalidNewPasswordError):
        _service(fake_db).change_password(1, "Current1!", new_password)


def test_change_password_rejects_wrong_current_and_reused_passwords(fake_db):
    _seed_user(fake_db, password="Current1!")
    old_hash = bcrypt.hashpw(b"OlderPass1!", bcrypt.gensalt(rounds=4)).decode()
    fake_db.insert(
        "user_password_history",
        {"user_id": 1, "password_hash": old_hash, "created_at": datetime.now(timezone.utc)},
    )
    service = _service(fake_db)

    with pytest.raises(InvalidPasswordError):
        service.change_password(1, "WrongPass1!", "BrandNew1!")
    with pytest.raises(ReusedPasswordError):
        service.change_password(1, "Current1!", "Current1!")
    with pytest.raises(ReusedPasswordError):
        service.change_password(1, "Current1!", "OlderPass1!")


def test_change_password_saves_history_updates_timestamp_and_revokes_refresh(fake_db):
    user = _seed_user(fake_db, password="Current1!")
    now = datetime(2026, 8, 11, 8, 0, tzinfo=timezone.utc)
    fake_db.update(
        "users",
        {"refresh_token_hash": "stored", "refresh_token_expires_at": now},
        where="id = %s",
        params=(1,),
    )

    _service(fake_db, now_factory=lambda: now).change_password(1, "Current1!", "BrandNew1!")

    stored = fake_db.select("users", where="id = %s", params=(1,), fetch_one=True)
    history = fake_db.select("user_password_history", where="user_id = %s", params=(1,))
    assert bcrypt.checkpw(b"BrandNew1!", stored["password_hash"].encode())
    assert stored["password_changed_at"] == now
    assert stored["refresh_token_hash"] is None
    assert stored["refresh_token_expires_at"] is None
    assert len(history) == 1
    assert history[0]["password_hash"] == user["password_hash"]


def test_reset_password_archives_previous_password_for_future_reuse_checks(fake_db):
    user = _seed_user(fake_db, password="Current1!")
    service = _service(fake_db, temporary_password_factory=lambda: "TempPass9347")

    service.reset_password("user01", MagicMock())

    history = fake_db.select("user_password_history", where="user_id = %s", params=(1,))
    assert history[0]["password_hash"] == user["password_hash"]


def test_reset_password_rejects_user_without_bound_telegram(fake_db):
    _seed_user(fake_db, telegram_user_id=None)

    with pytest.raises(PasswordDeliveryError):
        _service(fake_db).reset_password("user01", MagicMock())


def test_reset_password_wraps_telegram_failure_without_exposing_details(fake_db):
    _seed_user(fake_db)

    def fail_delivery(_chat_id, _password):
        raise RuntimeError("Telegram API internals")

    with pytest.raises(PasswordDeliveryError) as raised:
        _service(fake_db).reset_password("user01", fail_delivery)

    assert "Telegram API internals" not in str(raised.value)


@pytest.fixture
def api_client(monkeypatch):
    fake_db = FakeCloudSQLClient()
    telegram = MagicMock()
    monkeypatch.setenv("APP_JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-telegram-token")
    monkeypatch.setenv("APP_BCRYPT_ROUNDS", "4")
    monkeypatch.setattr(app_auth, "CloudSQLClient", lambda: fake_db)
    monkeypatch.setattr(app_auth, "TelegramClient", lambda _token: telegram)
    flask_app = Flask(__name__)
    flask_app.register_blueprint(app_auth.app_bp)
    flask_app.testing = True
    return flask_app.test_client(), fake_db, telegram


def test_forgot_password_and_login_api_use_required_fr65_messages(api_client):
    client, fake_db, telegram = api_client
    _seed_user(fake_db)

    forgot_response = client.post("/api/app/auth/forgot-password", json={"user_id": "user01"})
    assert forgot_response.status_code == 200
    assert forgot_response.get_json() == {"message": "新密碼已透過 Telegram 傳送"}
    temporary_password = telegram.send_text.call_args.kwargs["text"].split("：", 1)[1].splitlines()[0]

    wrong_response = client.post(
        "/api/app/auth/login",
        json={"user_id": "user01", "password": "wrong", "keep_logged_in": False},
    )
    assert wrong_response.status_code == 401
    assert wrong_response.get_json() == {
        "code": "INVALID_PASSWORD",
        "message": "很抱歉，您輸入的密碼有誤，若真的想不起來密碼，可以使用忘記密碼功能",
    }

    success_response = client.post(
        "/api/app/auth/login",
        json={
            "user_id": "user01",
            "password": temporary_password,
            "keep_logged_in": True,
        },
    )
    assert success_response.status_code == 200
    payload = success_response.get_json()
    assert payload["message"] == "身份驗證成功，歡迎使用羅賓森"
    assert payload["access_token"]
    assert payload["refresh_token"]
    assert payload["user"]["user_id"] == "user01"


def test_login_api_distinguishes_unknown_identity(api_client):
    client, _fake_db, _telegram = api_client

    response = client.post(
        "/api/app/auth/login",
        json={"user_id": "user99", "password": "anything", "keep_logged_in": False},
    )

    assert response.status_code == 401
    assert response.get_json() == {
        "code": "UNKNOWN_USER",
        "message": "很抱歉，我無法辨識您",
    }


def test_identify_api_checks_user_before_password_entry(api_client):
    client, fake_db, _telegram = api_client
    _seed_user(fake_db)

    known = client.post("/api/app/auth/identify", json={"user_id": "user01"})
    unknown = client.post("/api/app/auth/identify", json={"user_id": "user10"})

    assert known.status_code == 200
    assert known.get_json() == {"recognized": True}
    assert unknown.status_code == 401
    assert unknown.get_json() == {
        "code": "UNKNOWN_USER",
        "message": "很抱歉，我無法辨識您",
    }


def test_forgot_password_api_handles_unknown_user_and_delivery_failure(api_client):
    client, fake_db, telegram = api_client
    unknown = client.post("/api/app/auth/forgot-password", json={"user_id": "user99"})
    assert unknown.status_code == 401
    assert unknown.get_json() == {
        "code": "UNKNOWN_USER",
        "message": "很抱歉，我無法辨識您",
    }

    _seed_user(fake_db)
    telegram.send_text.side_effect = RuntimeError("delivery internals")
    unavailable = client.post("/api/app/auth/forgot-password", json={"user_id": "user01"})
    assert unavailable.status_code == 503
    assert unavailable.get_json() == {
        "code": "PASSWORD_DELIVERY_FAILED",
        "message": "目前無法透過 Telegram 傳送新密碼，請聯絡 Robin",
    }


def test_forgot_password_api_handles_missing_telegram_configuration(api_client, monkeypatch):
    client, fake_db, _telegram = api_client
    _seed_user(fake_db)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")

    response = client.post("/api/app/auth/forgot-password", json={"user_id": "user01"})

    assert response.status_code == 503
    assert response.get_json() == {"message": "服務暫時無法使用，請稍後再試"}


def test_refresh_me_and_logout_api_flow(api_client):
    client, fake_db, _telegram = api_client
    _seed_user(fake_db, password="correct-password")
    login_payload = client.post(
        "/api/app/auth/login",
        json={"user_id": "user01", "password": "correct-password", "keep_logged_in": True},
    ).get_json()

    refresh_response = client.post(
        "/api/app/auth/refresh", json={"refresh_token": login_payload["refresh_token"]}
    )
    assert refresh_response.status_code == 200
    rotated = refresh_response.get_json()
    me_response = client.get(
        "/api/app/auth/me",
        headers={"Authorization": f"Bearer {rotated['access_token']}"},
    )
    assert me_response.status_code == 200
    assert me_response.get_json()["user"] == {
        "database_id": 1,
        "current_login_at": login_payload["user"]["current_login_at"],
        "gender": "male",
        "font_size_preference": "medium",
        "is_owner": True,
        "password_changed_at": None,
        "previous_login_at": None,
        "privacy_mask_enabled": False,
        "role": "Robin",
        "theme_preference": "light",
        "user_id": "user01",
    }

    logout_response = client.post(
        "/api/app/auth/logout",
        headers={"Authorization": f"Bearer {rotated['access_token']}"},
    )
    assert logout_response.status_code == 200
    rejected = client.post(
        "/api/app/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    )
    assert rejected.status_code == 401
    assert rejected.get_json() == {"message": "登入已過期，請重新登入"}


def test_change_password_api_validates_rules_and_revokes_refresh(api_client):
    client, fake_db, _telegram = api_client
    _seed_user(fake_db, password="Current1!")
    login_payload = client.post(
        "/api/app/auth/login",
        json={"user_id": "user01", "password": "Current1!", "keep_logged_in": True},
    ).get_json()
    headers = {"Authorization": f"Bearer {login_payload['access_token']}"}

    weak = client.post(
        "/api/app/auth/change-password",
        headers=headers,
        json={"current_password": "Current1!", "new_password": "weak"},
    )
    wrong_current = client.post(
        "/api/app/auth/change-password",
        headers=headers,
        json={"current_password": "WrongPass1!", "new_password": "BrandNew1!"},
    )
    success = client.post(
        "/api/app/auth/change-password",
        headers=headers,
        json={"current_password": "Current1!", "new_password": "BrandNew1!"},
    )

    assert weak.status_code == 400
    assert weak.get_json()["code"] == "INVALID_NEW_PASSWORD"
    assert wrong_current.status_code == 400
    assert wrong_current.get_json()["code"] == "INVALID_CURRENT_PASSWORD"
    assert success.status_code == 200
    assert success.get_json() == {"message": "密碼修改成功，請使用新密碼重新登入"}
    stored = fake_db.select("users", where="id = %s", params=(1,), fetch_one=True)
    assert stored["refresh_token_hash"] is None


def test_change_password_api_rejects_reused_and_incomplete_passwords(api_client):
    client, fake_db, _telegram = api_client
    _seed_user(fake_db, password="Current1!")
    login_payload = client.post(
        "/api/app/auth/login",
        json={"user_id": "user01", "password": "Current1!", "keep_logged_in": False},
    ).get_json()
    headers = {"Authorization": f"Bearer {login_payload['access_token']}"}

    reused = client.post(
        "/api/app/auth/change-password",
        headers=headers,
        json={"current_password": "Current1!", "new_password": "Current1!"},
    )
    missing = client.post("/api/app/auth/change-password", headers=headers, json={})

    assert reused.status_code == 409
    assert reused.get_json()["code"] == "REUSED_PASSWORD"
    assert missing.status_code == 400


def test_preferences_api_updates_authenticated_user(api_client):
    client, fake_db, _telegram = api_client
    _seed_user(fake_db, password="Current1!")
    login_payload = client.post(
        "/api/app/auth/login",
        json={"user_id": "user01", "password": "Current1!", "keep_logged_in": False},
    ).get_json()
    headers = {"Authorization": f"Bearer {login_payload['access_token']}"}

    response = client.post(
        "/api/app/auth/preferences",
        headers=headers,
        json={
            "theme_preference": "dark",
            "font_size_preference": "large",
            "privacy_mask_enabled": True,
        },
    )

    assert response.status_code == 200
    assert response.get_json()["message"] == "APP 設定已儲存"
    assert response.get_json()["user"]["theme_preference"] == "dark"
    assert response.get_json()["user"]["font_size_preference"] == "large"
    assert response.get_json()["user"]["privacy_mask_enabled"] is True


def test_preferences_api_rejects_invalid_or_unauthenticated_request(api_client):
    client, fake_db, _telegram = api_client
    _seed_user(fake_db, password="Current1!")
    login_payload = client.post(
        "/api/app/auth/login",
        json={"user_id": "user01", "password": "Current1!", "keep_logged_in": False},
    ).get_json()
    headers = {"Authorization": f"Bearer {login_payload['access_token']}"}

    invalid = client.post(
        "/api/app/auth/preferences",
        headers=headers,
        json={
            "theme_preference": "system",
            "font_size_preference": "medium",
            "privacy_mask_enabled": False,
        },
    )
    unauthorized = client.post("/api/app/auth/preferences", json={})

    assert invalid.status_code == 400
    assert invalid.get_json() == {"message": "請確認 APP 設定選項"}
    assert unauthorized.status_code == 401


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("post", "/api/app/auth/login", {}),
        ("post", "/api/app/auth/identify", {}),
        ("post", "/api/app/auth/forgot-password", {}),
        ("post", "/api/app/auth/refresh", {}),
    ],
)
def test_auth_api_rejects_missing_required_fields(api_client, method, path, json_body):
    client, _fake_db, _telegram = api_client

    response = getattr(client, method)(path, json=json_body)

    assert response.status_code == 400
    assert response.get_json() == {"message": "請確認輸入資料是否完整"}


def test_protected_api_rejects_missing_bearer_token(api_client):
    client, _fake_db, _telegram = api_client

    response = client.get("/api/app/auth/me")

    assert response.status_code == 401
    assert response.get_json() == {"message": "請先登入"}


def test_protected_api_rejects_invalid_token(api_client):
    client, _fake_db, _telegram = api_client

    response = client.get(
        "/api/app/auth/me", headers={"Authorization": "Bearer invalid-token"}
    )

    assert response.status_code == 401
    assert response.get_json() == {"message": "登入已過期，請重新登入"}


def test_protected_api_handles_database_failure(api_client, monkeypatch):
    client, _fake_db, _telegram = api_client
    monkeypatch.setattr(app_auth, "CloudSQLClient", MagicMock(side_effect=RuntimeError("db")))

    response = client.get(
        "/api/app/auth/me", headers={"Authorization": "Bearer token"}
    )

    assert response.status_code == 503
    assert response.get_json() == {"message": "服務暫時無法使用，請稍後再試"}


def test_cors_headers_are_only_added_for_allowlisted_origin(api_client, monkeypatch):
    client, _fake_db, _telegram = api_client
    monkeypatch.setenv("APP_CORS_ORIGINS", "http://localhost:8081, https://app.example")

    allowed = client.options(
        "/api/app/auth/login", headers={"Origin": "http://localhost:8081"}
    )
    rejected = client.options(
        "/api/app/auth/login", headers={"Origin": "https://evil.example"}
    )

    assert allowed.headers["Access-Control-Allow-Origin"] == "http://localhost:8081"
    assert "Access-Control-Allow-Origin" not in rejected.headers


def test_login_api_rejects_non_json_payload(api_client):
    client, _fake_db, _telegram = api_client

    response = client.post(
        "/api/app/auth/login", data="not-json", content_type="text/plain"
    )

    assert response.status_code == 400
    assert response.get_json() == {"message": "請確認輸入資料是否完整"}


def test_refresh_and_logout_api_handle_unexpected_failures(api_client, monkeypatch):
    client, fake_db, _telegram = api_client
    _seed_user(fake_db, password="correct-password")
    login_payload = client.post(
        "/api/app/auth/login",
        json={"user_id": "user01", "password": "correct-password", "keep_logged_in": True},
    ).get_json()

    original_build_service = app_auth._build_service

    def fail_build(_db):
        raise RuntimeError("service internals")

    monkeypatch.setattr(app_auth, "_build_service", fail_build)
    refresh_response = client.post(
        "/api/app/auth/refresh", json={"refresh_token": login_payload["refresh_token"]}
    )
    assert refresh_response.status_code == 503

    monkeypatch.setattr(app_auth, "_build_service", original_build_service)
    database_calls = iter([fake_db, RuntimeError("logout db")])

    def db_factory():
        next_value = next(database_calls)
        if isinstance(next_value, Exception):
            raise next_value
        return next_value

    monkeypatch.setattr(app_auth, "CloudSQLClient", db_factory)
    logout_response = client.post(
        "/api/app/auth/logout",
        headers={"Authorization": f"Bearer {login_payload['access_token']}"},
    )
    assert logout_response.status_code == 503


def test_api_error_response_does_not_expose_stack_trace(api_client, monkeypatch):
    client, _fake_db, _telegram = api_client
    monkeypatch.setattr(app_auth, "CloudSQLClient", MagicMock(side_effect=RuntimeError("/secret/path")))

    response = client.post(
        "/api/app/auth/login",
        json={"user_id": "user01", "password": "password", "keep_logged_in": False},
    )

    assert response.status_code == 503
    assert response.get_json() == {"message": "服務暫時無法使用，請稍後再試"}
    assert b"/secret/path" not in response.data
