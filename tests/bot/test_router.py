from src.bot import router, templates
from src.bot.state import ConversationStateStore


ROBIN_ID = 8263904025
FAMILY_ID = 555


def _seed_pending_invite(fake_db, role="爸爸", code="secret123"):
    user_id = fake_db.insert("users", {"telegram_user_id": None, "role": role, "is_owner": False})
    fake_db.insert("invite_codes", {"code": code, "is_used": False, "user_id": user_id})
    return user_id


# --- 未知使用者 ---

def test_unknown_user_with_correct_code_gets_welcome_message(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    _seed_pending_invite(fake_db, code="secret123")
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "secret123")

    assert reply == templates.APPENDIX_A_TEXT
    bound = fake_db.select("users", where="telegram_user_id = %s", params=(FAMILY_ID,), fetch_one=True)
    assert bound is not None


def test_unknown_user_with_wrong_code_gets_prompt(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "wrong-code")

    assert "通關密碼" in reply


def test_unknown_user_with_empty_text_gets_prompt(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "")

    assert "通關密碼" in reply


# --- 已綁定的一般使用者 ---

def test_known_family_member_can_trigger_rule(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "/rule")

    assert reply == templates.APPENDIX_A_TEXT


def test_known_family_member_can_trigger_function_by_natural_language(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "我要看所有功能")

    assert reply == templates.build_function_list_text()


def test_known_family_member_cannot_trigger_owner_only_setup_flow(fake_db, monkeypatch):
    """權限邊界測試：家人輸入 Owner 專屬指令，不應該被授予設定通關密碼的能力。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "/set_invite_codes")

    assert reply == router._PLACEHOLDER_REPLY
    assert store.get(FAMILY_ID) is None


def test_known_family_member_other_text_gets_placeholder(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "今天天氣如何")

    assert reply == router._PLACEHOLDER_REPLY


# --- Owner（Robin） ---

def test_owner_first_message_creates_owner_row(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, ROBIN_ID, "/rule")

    assert reply == templates.APPENDIX_A_TEXT
    owner_row = fake_db.select("users", where="telegram_user_id = %s", params=(ROBIN_ID,), fetch_one=True)
    assert owner_row is not None
    assert owner_row["is_owner"] is True


def test_owner_can_trigger_set_invite_codes(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, ROBIN_ID, "/set_invite_codes")

    assert store.get(ROBIN_ID) == {"step": "awaiting_role"}
    assert "稱謂" in reply


def test_owner_mid_setup_flow_continues_state_machine(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()
    store.set(ROBIN_ID, {"step": "awaiting_role"})

    reply = router.handle_message(fake_db, store, ROBIN_ID, "媽媽")

    assert store.get(ROBIN_ID) == {"step": "awaiting_code", "role": "媽媽"}
    assert "媽媽" in reply


def test_owner_finishing_setup_writes_to_db_via_router(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()
    store.set(ROBIN_ID, {"step": "awaiting_code", "role": "媽媽"})

    router.handle_message(fake_db, store, ROBIN_ID, "mom-code")

    invite = fake_db.select("invite_codes", where="code = %s AND is_used = FALSE", params=("mom-code",), fetch_one=True)
    assert invite is not None
