from datetime import datetime, timedelta, timezone

import pytest

from src.bot import auth


@pytest.fixture(autouse=True)
def _reset_verification_attempts():
    """auth._verification_attempts 是 module 層級的記憶體狀態（FR-4b／FR-4c 鎖定計數），
    每個測試前後都要清空，避免不同測試案例互相汙染（尤其都用同一個假 telegram_user_id）。
    """
    auth._verification_attempts.clear()
    yield
    auth._verification_attempts.clear()


# --- is_owner ---

def test_is_owner_true_when_matches_env(monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "8263904025")
    assert auth.is_owner(8263904025) is True


def test_is_owner_false_when_not_matching(monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "8263904025")
    assert auth.is_owner(999999) is False


def test_is_owner_false_when_env_not_set(monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    assert auth.is_owner(8263904025) is False


# --- find_user_by_telegram_id ---

def test_find_user_by_telegram_id_returns_none_when_not_found(fake_db):
    assert auth.find_user_by_telegram_id(fake_db, 111) is None


def test_find_user_by_telegram_id_returns_the_row(fake_db):
    fake_db.insert("users", {"telegram_user_id": 111, "role": "Robin", "is_owner": True})
    user = auth.find_user_by_telegram_id(fake_db, 111)
    assert user["telegram_user_id"] == 111
    assert user["role"] == "Robin"


# --- get_or_create_owner ---

def test_get_or_create_owner_creates_when_missing(fake_db):
    user = auth.get_or_create_owner(fake_db, 8263904025)
    assert user["telegram_user_id"] == 8263904025
    assert user["role"] == "Robin"
    assert user["is_owner"] is True
    assert user["nickname"] == "Robin"
    assert user["is_active"] is True


def test_get_or_create_owner_returns_existing_without_duplicating(fake_db):
    first = auth.get_or_create_owner(fake_db, 8263904025)
    second = auth.get_or_create_owner(fake_db, 8263904025)
    assert first["id"] == second["id"]
    assert len(fake_db.select("users")) == 1


# --- generate_passcode ---

def test_generate_passcode_is_six_digits():
    code = auth.generate_passcode()
    assert len(code) == 6
    assert code.isdigit()


# --- create_user_and_invite（FR-4）---

def test_create_user_and_invite_creates_user_and_pending_invite(fake_db):
    result = auth.create_user_and_invite(fake_db, family_title="爸爸", nickname="小馬")

    user = fake_db.select("users", where="id = %s", params=(result["user_id"],), fetch_one=True)
    assert user["telegram_user_id"] is None
    assert user["family_title"] == "爸爸"
    assert user["nickname"] == "小馬"
    assert user["is_owner"] is False
    assert user["is_active"] is True

    invite = fake_db.select("invite_codes", where="user_id = %s AND is_used = FALSE",
                             params=(result["user_id"],), fetch_one=True)
    assert invite["code"] == result["passcode"]
    assert invite["is_used"] is False
    assert invite["expires_at"] > datetime.now(timezone.utc)


def test_create_user_and_invite_returns_mobile_user_id_from_users_id(fake_db):
    result = auth.create_user_and_invite(fake_db, family_title="媽媽")
    user = fake_db.select("users", where="id = %s", params=(result["user_id"],), fetch_one=True)
    assert result["mobile_user_id"] == f"user{user['id']:02d}"


# --- resend_passcode（FR-4c）---

def test_resend_passcode_invalidates_old_code_and_issues_new_one(fake_db):
    created = auth.create_user_and_invite(fake_db, family_title="爸爸")
    old_code = created["passcode"]

    new_code = auth.resend_passcode(fake_db, created["user_id"])

    assert new_code != old_code
    old_invite = fake_db.select("invite_codes", where="code = %s", params=(old_code,), fetch_one=True)
    assert old_invite["is_used"] is True
    new_invite = fake_db.select("invite_codes", where="code = %s", params=(new_code,), fetch_one=True)
    assert new_invite["is_used"] is False


# --- try_bind_invite_code ---

def _seed_pending_invite(fake_db, role="爸爸", code="secret123", expires_at=None):
    user_id = fake_db.insert("users", {"telegram_user_id": None, "role": role, "is_owner": False})
    fake_db.insert("invite_codes", {
        "code": code,
        "is_used": False,
        "user_id": user_id,
        "expires_at": expires_at,
    })
    return user_id


def test_try_bind_invite_code_succeeds_with_correct_unused_code(fake_db):
    user_id = _seed_pending_invite(fake_db, code="secret123")

    result = auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="secret123")

    assert result is True
    bound_user = fake_db.select("users", where="id = %s", params=(user_id,), fetch_one=True)
    assert bound_user["telegram_user_id"] == 555


def test_try_bind_invite_code_marks_code_as_used(fake_db):
    _seed_pending_invite(fake_db, code="secret123")
    auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="secret123")

    invite = fake_db.select("invite_codes")[0]
    assert invite["is_used"] is True


def test_try_bind_invite_code_fails_when_code_does_not_exist(fake_db):
    result = auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="not-a-real-code")
    assert result is False


def test_try_bind_invite_code_fails_when_code_already_used(fake_db):
    _seed_pending_invite(fake_db, code="secret123")
    first = auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="secret123")
    second = auth.try_bind_invite_code(fake_db, telegram_user_id=666, code="secret123")

    assert first is True
    assert second is False


@pytest.mark.parametrize("empty_code", ["", None])
def test_try_bind_invite_code_fails_for_empty_input(fake_db, empty_code):
    result = auth.try_bind_invite_code(fake_db, telegram_user_id=555, code=empty_code)
    assert result is False


def test_try_bind_invite_code_fails_when_race_lost_between_select_and_update(fake_db, monkeypatch):
    """模擬 race condition：SELECT 當下密碼還沒被用掉，但接下來的原子性 UPDATE 卻搶輸了
    （被另一個並行請求先一步標記為 is_used）。這是 ADR-10 風險表列出的「極低機率」情境，
    但既然是身分驗證邏輯，仍要覆蓋這條防護分支（AGENTS.md 要求認證邏輯 100% 覆蓋率）。
    """
    _seed_pending_invite(fake_db, code="secret123")

    original_update = fake_db.update

    def update_that_loses_the_race(table, data, where, params):
        if table == "invite_codes":
            return 0  # 模擬已經被別的請求搶先標記為 is_used
        return original_update(table, data, where, params)

    monkeypatch.setattr(fake_db, "update", update_that_loses_the_race)

    result = auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="secret123")

    assert result is False
    # 輸掉競爭時不應該繼續去更新 users 表
    assert fake_db.select("users", where="telegram_user_id = %s", params=(555,), fetch_one=True) is None


# --- try_bind_invite_code：FR-4b 到期檢查 ---

def test_try_bind_invite_code_fails_when_code_expired(fake_db):
    expired_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    _seed_pending_invite(fake_db, code="secret123", expires_at=expired_at)

    result = auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="secret123")

    assert result is False
    assert fake_db.select("users", where="telegram_user_id = %s", params=(555,), fetch_one=True) is None


def test_try_bind_invite_code_succeeds_when_not_yet_expired(fake_db):
    not_yet_expired = datetime.now(timezone.utc) + timedelta(hours=1)
    _seed_pending_invite(fake_db, code="secret123", expires_at=not_yet_expired)

    result = auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="secret123")

    assert result is True


def test_try_bind_invite_code_treats_missing_expires_at_as_not_expired(fake_db):
    """歷史資料相容：expires_at 為 None（理論上 migration 已補齊，這裡防呆）時不擋成功綁定。"""
    _seed_pending_invite(fake_db, code="secret123", expires_at=None)

    result = auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="secret123")

    assert result is True


# --- try_bind_invite_code：FR-4b／FR-4c 連續錯誤鎖定 ---

def test_try_bind_invite_code_locks_after_five_consecutive_failures(fake_db):
    _seed_pending_invite(fake_db, code="secret123")

    for _ in range(5):
        result = auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="wrong-code")
        assert result is False

    # 第 6 次即使密碼正確，也因為已鎖定而直接失敗
    locked_result = auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="secret123")
    assert locked_result is False
    assert fake_db.select("users", where="telegram_user_id = %s", params=(555,), fetch_one=True) is None


def test_try_bind_invite_code_lockout_is_scoped_per_telegram_user(fake_db):
    _seed_pending_invite(fake_db, code="secret123")

    for _ in range(5):
        auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="wrong-code")

    # 555 被鎖定，但另一個 Telegram 使用者不受影響
    other_result = auth.try_bind_invite_code(fake_db, telegram_user_id=999, code="secret123")
    assert other_result is True


def test_try_bind_invite_code_success_resets_failed_attempts(fake_db):
    _seed_pending_invite(fake_db, code="first-code")
    auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="wrong-1")
    auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="wrong-2")
    auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="first-code")

    # 成功後計數應重置；就算再錯 4 次（未達 5 次新門檻）也不會被鎖定
    _seed_pending_invite(fake_db, code="second-code")
    for _ in range(4):
        auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="wrong-again")

    result = auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="second-code")
    assert result is True


def test_try_bind_invite_code_expired_code_does_not_count_as_failed_attempt(fake_db):
    """密碼本身過期不算「猜錯」，不應該推進鎖定計數。"""
    expired_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    _seed_pending_invite(fake_db, code="expired-code", expires_at=expired_at)

    for _ in range(5):
        auth.try_bind_invite_code(fake_db, telegram_user_id=555, code="expired-code")

    assert auth._is_locked(555) is False


# --- set_user_active（FR-4d）---

def test_set_user_active_false_disables_user_and_revokes_refresh_token(fake_db):
    user_id = fake_db.insert("users", {
        "telegram_user_id": 555,
        "role": "爸爸",
        "is_owner": False,
        "is_active": True,
        "refresh_token_hash": "some-hash",
        "refresh_token_expires_at": datetime.now(timezone.utc) + timedelta(days=30),
    })

    auth.set_user_active(fake_db, user_id, active=False)

    user = fake_db.select("users", where="id = %s", params=(user_id,), fetch_one=True)
    assert user["is_active"] is False
    assert user["refresh_token_hash"] is None
    assert user["refresh_token_expires_at"] is None


def test_set_user_active_true_restores_without_touching_refresh_token_fields(fake_db):
    user_id = fake_db.insert("users", {
        "telegram_user_id": 555,
        "role": "爸爸",
        "is_owner": False,
        "is_active": False,
    })

    auth.set_user_active(fake_db, user_id, active=True)

    user = fake_db.select("users", where="id = %s", params=(user_id,), fetch_one=True)
    assert user["is_active"] is True
