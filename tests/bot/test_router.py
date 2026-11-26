"""src/bot/router.py 的端對端測試。

2026-11（功能大幅精簡）：只剩下三種分派——`/start` 綁定、Owner 權限管理（文字觸發
`/permission` ＋ `permission:*` callback_query）、以及一般使用者綁定後的固定回覆。
"""
from src.bot import router
from src.bot.state import ConversationStateStore

OWNER_ID = 999
FAMILY_ID = 555


def _set_owner(monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(OWNER_ID))


# --- /start ---


def test_start_as_owner_returns_welcome_and_creates_owner_row(fake_db, monkeypatch):
    _set_owner(monkeypatch)
    store = ConversationStateStore()

    reply, keyboard = router.handle_message(fake_db, store, OWNER_ID, "/start")

    assert "Robin" in reply
    assert keyboard is None
    owner = fake_db.select("users", where="telegram_user_id = %s", params=(OWNER_ID,), fetch_one=True)
    assert owner is not None
    assert owner["is_owner"] is True


def test_start_as_unbound_family_member_sets_awaiting_passcode(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    reply, _keyboard = router.handle_message(fake_db, store, FAMILY_ID, "/start")

    assert "通關密碼" in reply
    assert store.get(FAMILY_ID) == {"flow": "awaiting_passcode"}


def test_start_as_already_bound_family_member_returns_already_bound_reply(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply, _keyboard = router.handle_message(fake_db, store, FAMILY_ID, "/start")

    assert "App" in reply


# --- 通關密碼綁定 ---


def test_passcode_binding_success_returns_appendix_text(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": None, "role": "爸爸", "is_owner": False})
    fake_db.insert("invite_codes", {"code": "123456", "is_used": False, "user_id": user_id})
    store = ConversationStateStore()
    store.set(FAMILY_ID, {"flow": "awaiting_passcode"})

    reply, _keyboard = router.handle_message(fake_db, store, FAMILY_ID, "123456")

    assert "綁定成功" in reply
    bound = fake_db.select("users", where="telegram_user_id = %s", params=(FAMILY_ID,), fetch_one=True)
    assert bound is not None
    assert store.get(FAMILY_ID) is None


def test_passcode_binding_failure_keeps_awaiting_state(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()
    store.set(FAMILY_ID, {"flow": "awaiting_passcode"})

    reply, _keyboard = router.handle_message(fake_db, store, FAMILY_ID, "000000")

    assert "不正確" in reply
    assert store.get(FAMILY_ID) == {"flow": "awaiting_passcode"}


def test_unbound_user_without_awaiting_state_gets_not_bound_reply(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    reply, _keyboard = router.handle_message(fake_db, store, FAMILY_ID, "隨便說點什麼")

    assert "/start" in reply


# --- Owner 權限管理 ---


def test_permission_trigger_opens_permission_menu(fake_db, monkeypatch):
    _set_owner(monkeypatch)
    store = ConversationStateStore()

    reply, keyboard = router.handle_message(fake_db, store, OWNER_ID, "/permission")

    assert "權限管理" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "permission:create"


def test_permission_callback_requires_owner(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "permission:create")

    assert "只有 Robin" in reply
    assert keyboard is None


def test_permission_callback_create_then_step_full_flow(fake_db, monkeypatch):
    _set_owner(monkeypatch)
    store = ConversationStateStore()

    reply, _keyboard = router.handle_callback_query(fake_db, store, OWNER_ID, "permission:create")
    assert "稱謂" in reply

    router.handle_message(fake_db, store, OWNER_ID, "媽媽")
    router.handle_message(fake_db, store, OWNER_ID, "陳美麗")
    reply, _keyboard = router.handle_message(fake_db, store, OWNER_ID, "略過")

    assert "已建立" in reply
    created = fake_db.select("users", where="family_title = %s", params=("媽媽",))
    assert len(created) == 1


def test_unknown_callback_data_raises(fake_db, monkeypatch):
    _set_owner(monkeypatch)
    store = ConversationStateStore()

    import pytest

    with pytest.raises(ValueError):
        router.handle_callback_query(fake_db, store, OWNER_ID, "not_a_real_prefix:foo")
