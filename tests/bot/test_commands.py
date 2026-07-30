import pytest

from src.bot import commands, templates
from src.bot.state import ConversationStateStore


def test_handle_rule_returns_appendix_a_text():
    assert commands.handle_rule() == templates.APPENDIX_A_TEXT


def test_handle_function_returns_function_list_text():
    assert commands.handle_function() == templates.build_function_list_text()


def test_start_set_invite_codes_sets_awaiting_role_state():
    store = ConversationStateStore()
    reply = commands.start_set_invite_codes(store, telegram_user_id=1)
    assert store.get(1) == {"step": "awaiting_role"}
    assert "稱謂" in reply


def test_awaiting_role_step_with_role_text_moves_to_awaiting_code(fake_db):
    store = ConversationStateStore()
    store.set(1, {"step": "awaiting_role"})

    reply = commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="爸爸")

    assert store.get(1) == {"step": "awaiting_code", "role": "爸爸"}
    assert "爸爸" in reply
    assert "通關密碼" in reply
    # 這個步驟只暫存稱謂，還不該寫進資料庫（因為 code 還沒收到）
    assert fake_db.select("users") == []
    assert fake_db.select("invite_codes") == []


def test_awaiting_role_step_with_exit_phrase_clears_state(fake_db):
    store = ConversationStateStore()
    store.set(1, {"step": "awaiting_role"})

    reply = commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="沒有了")

    assert store.get(1) is None
    assert "結束" in reply


def test_awaiting_role_step_with_alternate_exit_phrase_clears_state(fake_db):
    store = ConversationStateStore()
    store.set(1, {"step": "awaiting_role"})

    commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="結束")

    assert store.get(1) is None


def test_awaiting_code_step_creates_user_and_invite_code(fake_db):
    store = ConversationStateStore()
    store.set(1, {"step": "awaiting_code", "role": "爸爸"})

    reply = commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="dad-code-1")

    users = fake_db.select("users")
    invite_codes = fake_db.select("invite_codes")
    assert len(users) == 1
    assert users[0]["role"] == "爸爸"
    assert users[0]["telegram_user_id"] is None
    assert len(invite_codes) == 1
    assert invite_codes[0]["code"] == "dad-code-1"
    assert invite_codes[0]["is_used"] is False
    assert invite_codes[0]["user_id"] == users[0]["id"]
    assert "已寫入" in reply


def test_awaiting_code_step_loops_back_to_awaiting_role(fake_db):
    store = ConversationStateStore()
    store.set(1, {"step": "awaiting_code", "role": "爸爸"})

    commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="dad-code-1")

    assert store.get(1) == {"step": "awaiting_role"}


def test_full_two_family_members_setup_flow(fake_db):
    store = ConversationStateStore()
    commands.start_set_invite_codes(store, telegram_user_id=1)
    commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="爸爸")
    commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="dad-code")
    commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="媽媽")
    commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="mom-code")
    final_reply = commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="沒有了")

    invite_codes = fake_db.select("invite_codes")
    assert {i["code"] for i in invite_codes} == {"dad-code", "mom-code"}
    assert store.get(1) is None
    assert "結束" in final_reply


def test_handle_set_invite_codes_step_raises_on_unknown_state(fake_db):
    # 防呆：state 內容不是預期的兩種 step 之一時，明確拋錯而不是悄悄吞掉或亂猜
    store = ConversationStateStore()
    store.set(1, {"step": "some_unexpected_step"})

    with pytest.raises(ValueError):
        commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="whatever")
