from src.bot import chat
from src.bot.state import ConversationStateStore


class _FakeLLMClient:
    """模擬 submodules.llm.client.LLMClient，只實作 chat.py 會用到的 generate_with_search。"""

    def __init__(self, response_text="這是回答", used_search=False):
        self.response_text = response_text
        self.used_search = used_search
        self.last_prompt = None

    def generate_with_search(self, prompt):
        self.last_prompt = prompt
        return self.response_text, self.used_search


def _seed_general(fake_db):
    fake_db.insert("knowledge_base", {"category": "general_persona", "user_id": None, "content": "我是羅賓森"})
    fake_db.insert("knowledge_base", {"category": "general_family", "user_id": None, "content": "家人背景"})


def test_handle_chat_message_returns_reply_when_no_search_used(fake_db):
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="記帳功能可以記錄每日花費喔！", used_search=False)
    store = ConversationStateStore()

    reply = chat.handle_chat_message(fake_db, llm_client, store, telegram_user_id=1, user_id=1, text="記帳功能是什麼？")

    assert reply == "記帳功能可以記錄每日花費喔！"
    assert store.get(1) is None


def test_handle_chat_message_logs_user_and_assistant_turns(fake_db):
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="好的！", used_search=False)
    store = ConversationStateStore()

    chat.handle_chat_message(fake_db, llm_client, store, telegram_user_id=1, user_id=1, text="早安")

    logs = fake_db.select("conversation_logs", where="user_id = %s", params=(1,))
    assert len(logs) == 2
    assert logs[0]["role"] == "user"
    assert logs[0]["content"] == "早安"
    assert logs[1]["role"] == "assistant"
    assert logs[1]["content"] == "好的！"


def test_handle_chat_message_prompt_includes_persona_and_user_message(fake_db):
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(fake_db, llm_client, store, telegram_user_id=1, user_id=1, text="今天天氣如何？")

    assert "我是羅賓森" in llm_client.last_prompt
    assert "家人背景" in llm_client.last_prompt
    assert "今天天氣如何？" in llm_client.last_prompt


def test_handle_chat_message_appends_save_prompt_and_sets_pending_state_when_search_used(fake_db):
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="今天台北是晴天", used_search=True)
    store = ConversationStateStore()

    reply = chat.handle_chat_message(fake_db, llm_client, store, telegram_user_id=1, user_id=1, text="今天天氣如何？")

    assert "今天台北是晴天" in reply
    assert "記錄" in reply
    assert store.get(1) == {
        "flow": "pending_kb_save",
        "content": "今天台北是晴天",
        "target_user_id": 1,
    }


def test_handle_pending_kb_save_step_confirms_and_saves(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_kb_save", "content": "威靈頓牛排食譜", "target_user_id": 1})

    reply = chat.handle_pending_kb_save_step(fake_db, store, telegram_user_id=1, text="要")

    assert "記錄" in reply
    assert store.get(1) is None
    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))
    assert len(rows) == 1
    assert rows[0]["content"] == "威靈頓牛排食譜"


def test_handle_pending_kb_save_step_accepts_alternate_confirm_word(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_kb_save", "content": "答案", "target_user_id": 1})

    chat.handle_pending_kb_save_step(fake_db, store, telegram_user_id=1, text="好")

    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))
    assert len(rows) == 1


def test_handle_pending_kb_save_step_declines_when_not_confirm_word(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_kb_save", "content": "答案", "target_user_id": 1})

    reply = chat.handle_pending_kb_save_step(fake_db, store, telegram_user_id=1, text="不用了")

    assert store.get(1) is None
    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))
    assert len(rows) == 0
    assert "好的" in reply
