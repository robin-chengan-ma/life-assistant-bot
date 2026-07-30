import pytest

from src.bot import auth


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


def test_get_or_create_owner_returns_existing_without_duplicating(fake_db):
    first = auth.get_or_create_owner(fake_db, 8263904025)
    second = auth.get_or_create_owner(fake_db, 8263904025)
    assert first["id"] == second["id"]
    assert len(fake_db.select("users")) == 1


# --- try_bind_invite_code ---

def _seed_pending_invite(fake_db, role="爸爸", code="secret123"):
    user_id = fake_db.insert("users", {"telegram_user_id": None, "role": role, "is_owner": False})
    fake_db.insert("invite_codes", {"code": code, "is_used": False, "user_id": user_id})
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
