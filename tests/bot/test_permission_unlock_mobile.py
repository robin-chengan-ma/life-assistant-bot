"""權限管理選單「🔓 解鎖 Mobile App 帳號」（2026-08-23，見
docs/ADR/discuss/mobile-app.md）。
"""
from datetime import datetime, timezone

from src.bot import auth, commands
from src.bot.state import ConversationStateStore


def _seed_user(fake_db, *, user_id, nickname, locked=False):
    fake_db.insert(
        "users",
        {
            "id": user_id,
            "is_owner": False,
            "role": "家人",
            "nickname": nickname,
            "mobile_login_failed_attempts": 2 if locked else 0,
            "mobile_login_locked_at": datetime.now(timezone.utc) if locked else None,
        },
    )


def test_permission_menu_includes_unlock_mobile_button():
    _, keyboard = commands.start_permission_menu()
    buttons = [row[0]["callback_data"] for row in keyboard["inline_keyboard"]]
    assert "permission:unlock_mobile" in buttons


def test_unlock_mobile_action_lists_locked_users_only(fake_db):
    _seed_user(fake_db, user_id=2, nickname="媽媽", locked=True)
    _seed_user(fake_db, user_id=3, nickname="爸爸", locked=False)
    state_store = ConversationStateStore()

    text, keyboard = commands.handle_permission_callback(fake_db, state_store, 111, "unlock_mobile")

    buttons = [row[0] for row in keyboard["inline_keyboard"]]
    callback_targets = [b["callback_data"] for b in buttons if b["callback_data"].startswith("permission:unlock_mobile_confirm:")]
    assert callback_targets == ["permission:unlock_mobile_confirm:2"]
    assert "媽媽" in text or any("媽媽" in b["text"] for b in buttons)


def test_unlock_mobile_action_reports_when_nobody_is_locked(fake_db):
    _seed_user(fake_db, user_id=2, nickname="媽媽", locked=False)
    state_store = ConversationStateStore()

    text, keyboard = commands.handle_permission_callback(fake_db, state_store, 111, "unlock_mobile")

    assert "沒有帳號被鎖定" in text
    assert keyboard is not None


def test_unlock_mobile_confirm_clears_lock_and_resets_attempts(fake_db):
    _seed_user(fake_db, user_id=2, nickname="媽媽", locked=True)
    state_store = ConversationStateStore()

    text, keyboard = commands.handle_permission_callback(
        fake_db, state_store, 111, "unlock_mobile_confirm:2"
    )

    user = fake_db.select("users", where="id = %s", params=(2,), fetch_one=True)
    assert user["mobile_login_locked_at"] is None
    assert user["mobile_login_failed_attempts"] == 0
    assert "已解鎖" in text
    assert keyboard is not None


def test_list_mobile_login_locked_users_sorted_by_locked_time(fake_db):
    fake_db.insert(
        "users",
        {"id": 2, "is_owner": False, "role": "家人", "nickname": "後鎖", "mobile_login_locked_at": datetime(2026, 8, 20, tzinfo=timezone.utc)},
    )
    fake_db.insert(
        "users",
        {"id": 3, "is_owner": False, "role": "家人", "nickname": "先鎖", "mobile_login_locked_at": datetime(2026, 8, 18, tzinfo=timezone.utc)},
    )

    locked_users = auth.list_mobile_login_locked_users(fake_db)

    assert [u["id"] for u in locked_users] == [3, 2]
