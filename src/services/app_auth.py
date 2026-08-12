"""Mobile App 帳密登入與 Token 商業邏輯（FR-65）。"""

from __future__ import annotations

import re
import secrets
import string
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

import bcrypt
import jwt

_APP_USER_ID_PATTERN = re.compile(r"^user(\d{2,})$")
_JWT_ALGORITHM = "HS256"
_JWT_AUDIENCE = "robinson-mobile-app"
_JWT_ISSUER = "robinson-api"
_TEMPORARY_PASSWORD_ALPHABET = string.ascii_letters + string.digits


class DatabaseClient(Protocol):
    def select(
        self,
        table: str,
        columns: tuple[str, ...] = ("*",),
        where: str | None = None,
        params: tuple | None = None,
        fetch_one: bool = False,
    ) -> list[dict] | dict | None: ...

    def insert(self, table: str, data: dict, returning: str = "id"): ...

    def update(self, table: str, data: dict, where: str, params: tuple) -> int: ...


class AppAuthError(Exception):
    """App 認證流程的可預期錯誤基底類別。"""


class UnknownUserError(AppAuthError):
    """使用者 ID 格式錯誤或查無使用者。"""


class InvalidPasswordError(AppAuthError):
    """使用者存在，但尚未設定密碼或密碼錯誤。"""


class InvalidNewPasswordError(AppAuthError):
    """新密碼不符合使用者確認的強度規則。"""


class ReusedPasswordError(AppAuthError):
    """新密碼與目前或任一歷史密碼相同。"""


class InvalidPreferenceError(AppAuthError):
    """APP 偏好值不在 FR-72 允許的白名單內。"""


class InvalidAccessTokenError(AppAuthError):
    """Access Token 缺失、過期或內容不合法。"""


class InvalidRefreshTokenError(AppAuthError):
    """Refresh Token 缺失、過期、遭撤銷或內容不合法。"""


class PasswordDeliveryError(AppAuthError):
    """新密碼無法透過 Telegram 送達。"""

    def __init__(self) -> None:
        super().__init__("新密碼目前無法送達")


@dataclass(frozen=True)
class AuthenticatedUser:
    database_id: int
    app_user_id: str
    role: str
    is_owner: bool
    gender: str | None = None
    previous_login_at: datetime | None = None
    current_login_at: datetime | None = None
    password_changed_at: datetime | None = None
    theme_preference: str = "light"
    font_size_preference: str = "medium"
    privacy_mask_enabled: bool = False

    def to_dict(self) -> dict:
        return {
            "database_id": self.database_id,
            "user_id": self.app_user_id,
            "role": self.role,
            "is_owner": self.is_owner,
            "gender": self.gender,
            "previous_login_at": self.previous_login_at.isoformat()
            if self.previous_login_at
            else None,
            "current_login_at": self.current_login_at.isoformat()
            if self.current_login_at
            else None,
            "password_changed_at": self.password_changed_at.isoformat()
            if self.password_changed_at
            else None,
            "theme_preference": self.theme_preference,
            "font_size_preference": self.font_size_preference,
            "privacy_mask_enabled": self.privacy_mask_enabled,
        }


@dataclass(frozen=True)
class AuthSession:
    user: AuthenticatedUser
    access_token: str
    access_token_expires_in: int
    refresh_token: str | None


def _generate_temporary_password() -> str:
    """產生 16 碼英數密碼；僅回傳給 Telegram 發送流程，不寫入 log 或資料庫明碼。"""
    return "".join(secrets.choice(_TEMPORARY_PASSWORD_ALPHABET) for _ in range(16))


class AppAuthService:
    """封裝 FR-65 密碼驗證、JWT 與 Rolling Refresh Token。"""

    def __init__(
        self,
        db: DatabaseClient,
        *,
        jwt_secret: str,
        access_token_ttl: timedelta = timedelta(minutes=30),
        refresh_token_ttl: timedelta = timedelta(days=30),
        bcrypt_rounds: int = 12,
        now_factory: Callable[[], datetime] | None = None,
        temporary_password_factory: Callable[[], str] | None = None,
    ) -> None:
        if len(jwt_secret) < 32:
            raise ValueError("jwt_secret 長度至少需要 32 個字元")
        if not 4 <= bcrypt_rounds <= 16:
            raise ValueError("bcrypt_rounds 必須介於 4 到 16")

        self._db = db
        self._jwt_secret = jwt_secret
        self._access_token_ttl = access_token_ttl
        self._refresh_token_ttl = refresh_token_ttl
        self._bcrypt_rounds = bcrypt_rounds
        self._now_factory = now_factory or (lambda: datetime.now(timezone.utc))
        self._temporary_password_factory = temporary_password_factory or _generate_temporary_password

    @staticmethod
    def format_app_user_id(database_id: int) -> str:
        """把 users.id 轉成 Robin 指定的 App ID，例如 1→user01、10→user10。"""
        if database_id < 1:
            raise ValueError("database_id 必須大於 0")
        return f"user{database_id:02d}"

    def identify_user(self, app_user_id: str) -> None:
        """只確認 App 使用者 ID 是否存在，不讀取或驗證密碼。"""
        self._find_user(app_user_id)

    def login(self, app_user_id: str, password: str, *, keep_logged_in: bool) -> AuthSession:
        user = self._find_user(app_user_id)
        password_hash = user.get("password_hash")
        if not password_hash or not self._password_matches(password, password_hash):
            raise InvalidPasswordError

        login_at = self._now()
        login_times = {
            "previous_login_at": user.get("current_login_at"),
            "current_login_at": login_at,
        }
        self._db.update("users", login_times, where="id = %s", params=(user["id"],))
        user = {**user, **login_times}

        refresh_token = None
        if keep_logged_in:
            refresh_token = self._issue_and_store_refresh_token(user["id"])

        return AuthSession(
            user=self._identity_from_row(user),
            access_token=self._issue_jwt(user["id"], token_type="access", ttl=self._access_token_ttl),
            access_token_expires_in=int(self._access_token_ttl.total_seconds()),
            refresh_token=refresh_token,
        )

    def reset_password(
        self,
        app_user_id: str,
        deliver_password: Callable[[int, str], None],
    ) -> None:
        user = self._find_user(app_user_id)
        telegram_user_id = user.get("telegram_user_id")
        if telegram_user_id is None:
            raise PasswordDeliveryError

        temporary_password = self._temporary_password_factory()
        password_hash = self._hash_value(temporary_password)
        self._archive_password(user)
        self._db.update(
            "users",
            {
                "password_hash": password_hash,
                "password_changed_at": self._now(),
                "refresh_token_hash": None,
                "refresh_token_expires_at": None,
            },
            where="id = %s",
            params=(user["id"],),
        )
        try:
            deliver_password(telegram_user_id, temporary_password)
        except Exception as exc:
            raise PasswordDeliveryError from exc

    def change_password(
        self,
        database_id: int,
        current_password: str,
        new_password: str,
    ) -> None:
        """驗證並更新密碼，保存永久歷程且撤銷所有 Refresh Token。"""
        user = self._db.select(
            "users", where="id = %s", params=(database_id,), fetch_one=True
        )
        if not user:
            raise InvalidAccessTokenError
        current_hash = user.get("password_hash")
        if not current_hash or not self._password_matches(current_password, current_hash):
            raise InvalidPasswordError
        self._validate_new_password(new_password)
        if self._password_matches(new_password, current_hash):
            raise ReusedPasswordError
        history = self._db.select(
            "user_password_history", where="user_id = %s", params=(database_id,)
        )
        if any(
            self._password_matches(new_password, row.get("password_hash"))
            for row in (history or [])
        ):
            raise ReusedPasswordError

        self._archive_password(user)
        self._db.update(
            "users",
            {
                "password_hash": self._hash_value(new_password),
                "password_changed_at": self._now(),
                "refresh_token_hash": None,
                "refresh_token_expires_at": None,
            },
            where="id = %s",
            params=(database_id,),
        )

    def refresh(self, refresh_token: str) -> AuthSession:
        database_id = self._refresh_token_user_id(refresh_token)
        user = self._db.select(
            "users",
            where="id = %s",
            params=(database_id,),
            fetch_one=True,
        )
        if not user:
            raise InvalidRefreshTokenError

        stored_hash = user.get("refresh_token_hash")
        expires_at = user.get("refresh_token_expires_at")
        if (
            not stored_hash
            or not expires_at
            or expires_at <= self._now()
            or not self._password_matches(refresh_token, stored_hash)
        ):
            raise InvalidRefreshTokenError

        rotated_refresh_token = self._issue_and_store_refresh_token(user["id"])
        return AuthSession(
            user=self._identity_from_row(user),
            access_token=self._issue_jwt(user["id"], token_type="access", ttl=self._access_token_ttl),
            access_token_expires_in=int(self._access_token_ttl.total_seconds()),
            refresh_token=rotated_refresh_token,
        )

    def authenticate_access_token(self, access_token: str) -> AuthenticatedUser:
        claims = self._decode_access_jwt(access_token)
        user = self._db.select(
            "users",
            where="id = %s",
            params=(self._claim_user_id(claims, InvalidAccessTokenError),),
            fetch_one=True,
        )
        if not user:
            raise InvalidAccessTokenError
        return self._identity_from_row(user)

    def logout(self, database_id: int) -> None:
        self._db.update(
            "users",
            {"refresh_token_hash": None, "refresh_token_expires_at": None},
            where="id = %s",
            params=(database_id,),
        )

    def update_preferences(
        self,
        database_id: int,
        *,
        theme_preference: str,
        font_size_preference: str,
        privacy_mask_enabled: bool,
    ) -> AuthenticatedUser:
        """驗證並保存 FR-72 使用者個人 APP 偏好。"""
        if (
            theme_preference not in {"light", "dark"}
            or font_size_preference not in {"small", "medium", "large"}
            or not isinstance(privacy_mask_enabled, bool)
        ):
            raise InvalidPreferenceError
        user = self._db.select(
            "users", where="id = %s", params=(database_id,), fetch_one=True
        )
        if not user:
            raise InvalidAccessTokenError
        preferences = {
            "theme_preference": theme_preference,
            "font_size_preference": font_size_preference,
            "privacy_mask_enabled": privacy_mask_enabled,
        }
        self._db.update("users", preferences, where="id = %s", params=(database_id,))
        return self._identity_from_row({**user, **preferences})

    def _find_user(self, app_user_id: str) -> dict:
        if not isinstance(app_user_id, str):
            raise UnknownUserError
        normalized = app_user_id.strip().lower()
        match = _APP_USER_ID_PATTERN.fullmatch(normalized)
        if not match:
            raise UnknownUserError

        database_id = int(match.group(1))
        if database_id < 1 or normalized != self.format_app_user_id(database_id):
            raise UnknownUserError
        user = self._db.select(
            "users", where="id = %s", params=(database_id,), fetch_one=True
        )
        if not user:
            raise UnknownUserError
        return user

    def _identity_from_row(self, user: dict) -> AuthenticatedUser:
        database_id = int(user["id"])
        return AuthenticatedUser(
            database_id=database_id,
            app_user_id=self.format_app_user_id(database_id),
            role=str(user["role"]),
            is_owner=bool(user.get("is_owner")),
            gender=user.get("gender"),
            previous_login_at=self._as_aware_datetime(user.get("previous_login_at")),
            current_login_at=self._as_aware_datetime(user.get("current_login_at")),
            password_changed_at=self._as_aware_datetime(user.get("password_changed_at")),
            theme_preference=str(user.get("theme_preference") or "light"),
            font_size_preference=str(user.get("font_size_preference") or "medium"),
            privacy_mask_enabled=bool(user.get("privacy_mask_enabled", False)),
        )

    def _archive_password(self, user: dict) -> None:
        password_hash = user.get("password_hash")
        if not password_hash:
            return
        self._db.insert(
            "user_password_history",
            {
                "user_id": user["id"],
                "password_hash": password_hash,
                "created_at": self._now(),
            },
        )

    @staticmethod
    def _validate_new_password(password: str) -> None:
        valid = (
            isinstance(password, str)
            and 8 <= len(password) <= 15
            and not any(character.isspace() for character in password)
            and re.search(r"[A-Z]", password) is not None
            and re.search(r"[a-z]", password) is not None
            and re.search(r"[0-9]", password) is not None
            and any(not character.isalnum() for character in password)
        )
        if not valid:
            raise InvalidNewPasswordError

    @staticmethod
    def _as_aware_datetime(value: object) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    def _issue_and_store_refresh_token(self, database_id: int) -> str:
        # Refresh Token 採短長度 opaque token，避免把長 JWT 直接交給 bcrypt 時撞到 72-byte
        # 上限；前綴只用來定位 users.id，真正驗證仍以資料庫內 bcrypt 雜湊為準。
        refresh_token = f"{database_id}.{secrets.token_urlsafe(32)}"
        self._db.update(
            "users",
            {
                "refresh_token_hash": self._hash_value(refresh_token),
                "refresh_token_expires_at": self._now() + self._refresh_token_ttl,
            },
            where="id = %s",
            params=(database_id,),
        )
        return refresh_token

    def _issue_jwt(self, database_id: int, *, token_type: str, ttl: timedelta) -> str:
        now = self._now()
        return jwt.encode(
            {
                "sub": str(database_id),
                "type": token_type,
                "iat": now,
                "exp": now + ttl,
                "iss": _JWT_ISSUER,
                "aud": _JWT_AUDIENCE,
                "jti": secrets.token_urlsafe(24),
            },
            self._jwt_secret,
            algorithm=_JWT_ALGORITHM,
        )

    def _decode_access_jwt(self, token: str) -> dict:
        if not isinstance(token, str) or not token:
            raise InvalidAccessTokenError
        try:
            claims = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=[_JWT_ALGORITHM],
                audience=_JWT_AUDIENCE,
                issuer=_JWT_ISSUER,
                options={"require": ["sub", "type", "iat", "exp", "jti"]},
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidAccessTokenError from exc
        if claims.get("type") != "access":
            raise InvalidAccessTokenError
        return claims

    @staticmethod
    def _refresh_token_user_id(refresh_token: str) -> int:
        if not isinstance(refresh_token, str) or not refresh_token:
            raise InvalidRefreshTokenError
        database_id_text, separator, secret = refresh_token.partition(".")
        if not separator or not database_id_text.isdigit() or not secret:
            raise InvalidRefreshTokenError
        database_id = int(database_id_text)
        if database_id < 1:
            raise InvalidRefreshTokenError
        return database_id

    @staticmethod
    def _claim_user_id(claims: dict, error_type: type[AppAuthError]) -> int:
        try:
            database_id = int(claims["sub"])
        except (KeyError, TypeError, ValueError) as exc:
            raise error_type from exc
        if database_id < 1:
            raise error_type
        return database_id

    def _hash_value(self, value: str) -> str:
        return bcrypt.hashpw(
            value.encode("utf-8"), bcrypt.gensalt(rounds=self._bcrypt_rounds)
        ).decode("utf-8")

    @staticmethod
    def _password_matches(value: str, encoded_hash: str) -> bool:
        if not isinstance(value, str) or not isinstance(encoded_hash, str):
            return False
        try:
            return bcrypt.checkpw(value.encode("utf-8"), encoded_hash.encode("utf-8"))
        except (ValueError, TypeError):
            return False

    def _now(self) -> datetime:
        value = self._now_factory()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
