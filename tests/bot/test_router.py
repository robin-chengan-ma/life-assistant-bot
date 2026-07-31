from src.bot import router, templates
from src.bot.state import ConversationStateStore


ROBIN_ID = 8263904025
FAMILY_ID = 555
FAMILY_ID_2 = 556


class _FakeLLMClient:
    """模擬 submodules.llm.client.LLMClient，只實作 chat.py 會用到的 generate_with_search。"""

    def __init__(self, response_text="這是聊天核心的回答", used_search=False):
        self.response_text = response_text
        self.used_search = used_search

    def generate_with_search(self, prompt):
        return self.response_text, self.used_search


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
    """權限邊界測試：家人輸入 Owner 專屬指令，不應該被授予設定通關密碼的能力（改落入一般聊天核心）。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="我不太懂這個指令耶！")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "/set_invite_codes", llm_client=llm_client)

    assert reply == "我不太懂這個指令耶！"
    assert store.get(FAMILY_ID) is None


def test_known_family_member_other_text_gets_chat_core_reply(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="今天台北是晴天喔！")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "今天天氣如何", llm_client=llm_client)

    assert reply == "今天台北是晴天喔！"
    logs = fake_db.select("conversation_logs", where="user_id = %s", params=(1,))
    assert len(logs) == 2


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

    assert store.get(ROBIN_ID) == {"flow": "set_invite_codes", "step": "awaiting_role"}
    assert "稱謂" in reply


def test_owner_mid_setup_flow_continues_state_machine(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()
    store.set(ROBIN_ID, {"flow": "set_invite_codes", "step": "awaiting_role"})

    reply = router.handle_message(fake_db, store, ROBIN_ID, "媽媽")

    assert store.get(ROBIN_ID) == {"flow": "set_invite_codes", "step": "awaiting_code", "role": "媽媽"}
    assert "媽媽" in reply


def test_owner_finishing_setup_writes_to_db_via_router(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()
    store.set(ROBIN_ID, {"flow": "set_invite_codes", "step": "awaiting_code", "role": "媽媽"})

    router.handle_message(fake_db, store, ROBIN_ID, "mom-code")

    invite = fake_db.select("invite_codes", where="code = %s AND is_used = FALSE", params=("mom-code",), fetch_one=True)
    assert invite is not None


# --- 功能開關（docs/specs/feature-toggles/SPEC.md）---


def test_family_member_binding_auto_creates_default_toggles(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    _seed_pending_invite(fake_db, code="secret123")
    store = ConversationStateStore()

    router.handle_message(fake_db, store, FAMILY_ID, "secret123")

    bound = fake_db.select("users", where="telegram_user_id = %s", params=(FAMILY_ID,), fetch_one=True)
    rows = fake_db.select("feature_toggles", where="user_id = %s", params=(bound["id"],))
    assert len(rows) == 8


def test_known_family_member_can_trigger_my_toggles(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "我的功能設定")

    assert "1. " in reply
    assert store.get(FAMILY_ID)["flow"] == "toggle"


def test_known_family_member_toggle_flow_continues_via_router(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    router.handle_message(fake_db, store, FAMILY_ID, "/my_toggles")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "1")

    assert "切換為" in reply
    assert store.get(FAMILY_ID) == {"flow": "toggle", "step": "awaiting_index", "target_user_id": user_id}


def test_known_family_member_cannot_trigger_owner_only_set_toggle(fake_db, monkeypatch):
    """權限邊界測試：家人輸入 Owner 專屬 /set_toggle，不應被授予代管他人開關的能力（改落入一般聊天核心）。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="我不太懂這個指令耶！")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "/set_toggle", llm_client=llm_client)

    assert reply == "我不太懂這個指令耶！"
    assert store.get(FAMILY_ID) is None


def test_owner_can_trigger_my_toggles_for_self(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, ROBIN_ID, "/my_toggles")

    assert "1. " in reply
    owner_row = fake_db.select("users", where="telegram_user_id = %s", params=(ROBIN_ID,), fetch_one=True)
    assert store.get(ROBIN_ID) == {"flow": "toggle", "step": "awaiting_index", "target_user_id": owner_row["id"]}


def test_owner_set_toggle_with_no_family_bound_yet(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, ROBIN_ID, "/set_toggle")

    assert "沒有" in reply
    assert store.get(ROBIN_ID) is None


def test_owner_can_delegate_toggle_for_family_member(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    dad_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    select_reply = router.handle_message(fake_db, store, ROBIN_ID, "/set_toggle")
    list_reply = router.handle_message(fake_db, store, ROBIN_ID, "1")
    toggle_reply = router.handle_message(fake_db, store, ROBIN_ID, "1")

    assert "爸爸" in select_reply
    assert "1. " in list_reply
    assert "切換為" in toggle_reply
    rows = fake_db.select("feature_toggles", where="user_id = %s", params=(dad_id,))
    assert any(not r["is_enabled"] for r in rows)


# --- 一般聊天核心（docs/specs/chat-core/SPEC.md）---


def test_known_family_member_general_message_routes_to_chat_core(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="記帳功能可以幫你記錄每天的花費喔！", used_search=False)

    reply = router.handle_message(fake_db, store, FAMILY_ID, "記帳功能是什麼？", llm_client=llm_client)

    assert reply == "記帳功能可以幫你記錄每天的花費喔！"
    assert store.get(FAMILY_ID) is None


def test_owner_general_message_routes_to_chat_core(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="早安！", used_search=False)

    reply = router.handle_message(fake_db, store, ROBIN_ID, "早安", llm_client=llm_client)

    assert reply == "早安！"


def test_chat_core_search_reply_sets_pending_kb_save_state(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="今天台北是晴天", used_search=True)

    reply = router.handle_message(fake_db, store, FAMILY_ID, "今天天氣如何？", llm_client=llm_client)

    assert "今天台北是晴天" in reply
    assert store.get(FAMILY_ID) == {"flow": "pending_kb_save", "content": "今天台北是晴天", "target_user_id": user_id}


def test_pending_kb_save_flow_continues_via_router(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(FAMILY_ID, {"flow": "pending_kb_save", "content": "今天台北是晴天", "target_user_id": user_id})

    reply = router.handle_message(fake_db, store, FAMILY_ID, "要")

    assert "記錄" in reply
    assert store.get(FAMILY_ID) is None
    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", user_id))
    assert len(rows) == 1


def test_owner_pending_kb_save_flow_continues_via_router(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()
    store.set(ROBIN_ID, {"flow": "pending_kb_save", "content": "答案", "target_user_id": 1})

    reply = router.handle_message(fake_db, store, ROBIN_ID, "不用了")

    assert store.get(ROBIN_ID) is None
    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))
    assert len(rows) == 0
