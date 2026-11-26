"""src/bot/commands.py（Owner 專屬「權限管理」流程）的單元測試。

2026-11（功能大幅精簡）：拿掉日常紀錄類功能（待辦/心情/運動/飲食/記帳/體態/求職/證照…）之後，
`commands.py` 只剩下權限管理，這裡的測試也一併精簡到只涵蓋這塊。
"""
from datetime import UTC, datetime

import pytest

from src.bot import commands
from src.bot.state import ConversationStateStore


def test_start_permission_menu_returns_fixed_keyboard():
    text, keyboard = commands.start_permission_menu()
    assert "請選擇" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "permission:create"


def test_start_permission_menu_includes_unlock_mobile_button():
    _, keyboard = commands.start_permission_menu()
    buttons = [row[0]["callback_data"] for row in keyboard["inline_keyboard"]]
    assert "permission:unlock_mobile" in buttons


def test_handle_permission_callback_create_sets_awaiting_family_title_state():
    store = ConversationStateStore()
    reply, keyboard = commands.handle_permission_callback(None, store, telegram_user_id=1, action="create")
    assert store.get(1) == {"flow": "permission_create", "step": "awaiting_family_title"}
    assert keyboard is None
    assert "稱謂" in reply


def test_handle_permission_callback_disable_lists_candidates(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "爸爸", "is_owner": False, "is_active": True})
    store = ConversationStateStore()

    reply, keyboard = commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="disable")

    assert keyboard is None
    assert "爸爸" in reply
    assert store.get(1)["flow"] == "permission_disable"


def test_handle_permission_callback_disable_with_no_candidates_returns_none_keyboard(fake_db):
    store = ConversationStateStore()

    reply, keyboard = commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="disable")

    assert "沒有" in reply
    assert keyboard is None
    assert store.get(1) is None


def test_permission_create_full_flow_creates_user_and_invite(fake_db):
    store = ConversationStateStore()
    commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="create")
    commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="爸爸")
    commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="王大明")
    reply = commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="略過")

    users = fake_db.select("users", where="family_title = %s", params=("爸爸",))
    assert len(users) == 1
    assert users[0]["telegram_user_id"] is None
    assert users[0]["full_name"] == "王大明"
    invite = fake_db.select("invite_codes", where="user_id = %s AND is_used = FALSE", params=(users[0]["id"],), fetch_one=True)
    assert invite is not None
    assert invite["expires_at"] is not None
    assert store.get(1) is None
    assert "已建立" in reply
    assert "王大明" in reply


def test_permission_create_full_flow_asks_for_full_name_before_nickname(fake_db):
    store = ConversationStateStore()
    commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="create")
    reply = commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="爸爸")

    assert "全名" in reply
    assert store.get(1) == {"flow": "permission_create", "step": "awaiting_full_name", "family_title": "爸爸"}


def test_permission_create_full_flow_rejects_blank_full_name(fake_db):
    store = ConversationStateStore()
    commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="create")
    commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="爸爸")
    reply = commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="   ")

    assert "空白" in reply
    assert store.get(1)["step"] == "awaiting_full_name"


def test_permission_create_flow_exit_phrase_clears_state(fake_db):
    store = ConversationStateStore()
    commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="create")

    reply = commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="沒有了")

    assert store.get(1) is None
    assert "結束" in reply


def test_permission_disable_flow_with_invalid_index_reprompts(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "爸爸", "is_owner": False, "is_active": True})
    store = ConversationStateStore()
    commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="disable")

    reply = commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="99")

    assert "編號" in reply
    assert store.get(1) is not None


def test_permission_enable_flow_reactivates_user(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "爸爸", "is_owner": False, "is_active": False})
    store = ConversationStateStore()
    commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="enable")

    reply = commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="1")

    updated = fake_db.select("users", where="telegram_user_id = %s", params=(555,), fetch_one=True)
    assert updated["is_active"] is True
    assert "恢復" in reply


def test_permission_resend_flow_generates_new_passcode(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": None, "role": "爸爸", "is_owner": False, "is_active": True})
    fake_db.insert("invite_codes", {"code": "old-code", "is_used": False, "user_id": user_id})
    store = ConversationStateStore()
    commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="resend")

    reply = commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="1")

    assert "已重發" in reply
    old_invite = fake_db.select("invite_codes", where="code = %s", params=("old-code",), fetch_one=True)
    assert old_invite["is_used"] is True


def test_handle_permission_step_raises_on_unknown_state(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "not_a_real_flow"})

    with pytest.raises(ValueError):
        commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="whatever")


# --- 🔓 解鎖 Mobile App 帳號（2026-08-23，見 docs/ADR/discuss/mobile-app.md） ---


def _seed_user(fake_db, *, user_id, nickname, locked=False):
    fake_db.insert(
        "users",
        {
            "id": user_id,
            "is_owner": False,
            "role": "家人",
            "nickname": nickname,
            "mobile_login_failed_attempts": 2 if locked else 0,
            "mobile_login_locked_at": datetime.now(UTC) if locked else None,
        },
    )


def test_unlock_mobile_action_lists_locked_users_only(fake_db):
    _seed_user(fake_db, user_id=2, nickname="媽媽", locked=True)
    _seed_user(fake_db, user_id=3, nickname="爸爸", locked=False)
    store = ConversationStateStore()

    text, keyboard = commands.handle_permission_callback(fake_db, store, 111, "unlock_mobile")

    buttons = [row[0] for row in keyboard["inline_keyboard"]]
    callback_targets = [b["callback_data"] for b in buttons if b["callback_data"].startswith("permission:unlock_mobile_confirm:")]
    assert callback_targets == ["permission:unlock_mobile_confirm:2"]
    assert "媽媽" in text or any("媽媽" in b["text"] for b in buttons)


def test_unlock_mobile_action_reports_when_nobody_is_locked(fake_db):
    _seed_user(fake_db, user_id=2, nickname="媽媽", locked=False)
    store = ConversationStateStore()

    text, keyboard = commands.handle_permission_callback(fake_db, store, 111, "unlock_mobile")

    assert "沒有帳號被鎖定" in text
    assert keyboard is not None


def test_unlock_mobile_confirm_clears_lock_and_resets_attempts(fake_db):
    _seed_user(fake_db, user_id=2, nickname="媽媽", locked=True)
    store = ConversationStateStore()

    text, keyboard = commands.handle_permission_callback(fake_db, store, 111, "unlock_mobile_confirm:2")

    user = fake_db.select("users", where="id = %s", params=(2,), fetch_one=True)
    assert user["mobile_login_locked_at"] is None
    assert user["mobile_login_failed_attempts"] == 0
    assert "已解鎖" in text
    assert keyboard is not None
