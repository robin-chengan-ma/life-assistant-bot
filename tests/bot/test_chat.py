from src.bot import chat
from src.bot.state import ConversationStateStore


class _FakeLLMClient:
    """模擬 submodules.llm.client.LLMClient，只實作 chat.py 會用到的 generate_text
    （2026-07-31 移除 generate_with_search，見 chat-core SPEC.md ADR-5）。"""

    def __init__(self, response_text="這是回答"):
        self.response_text = response_text
        self.last_prompt = None

    def generate_text(self, prompt):
        self.last_prompt = prompt
        return self.response_text


class _FakeTextLLMClient:
    """模擬長記憶摘要用的 LLMClient，記錄呼叫次數供測試斷言。"""

    def __init__(self, response_text="摘要"):
        self.response_text = response_text
        self.call_count = 0

    def generate_text(self, prompt):
        self.call_count += 1
        return self.response_text


def _seed_general(fake_db):
    fake_db.insert("knowledge_base", {"category": "general_persona", "user_id": None, "content": "我是羅賓森"})
    fake_db.insert("knowledge_base", {"category": "general_family", "user_id": None, "content": "家人背景"})


def test_handle_chat_message_returns_reply_when_answer_known(fake_db):
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="記帳功能可以記錄每日花費喔！")
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    reply = chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="記帳功能是什麼？"
    )

    assert reply == "記帳功能可以記錄每日花費喔！"
    assert store.get(1) is None


def test_handle_chat_message_logs_user_and_assistant_turns(fake_db):
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="好的！")
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="早安")

    logs = fake_db.select("conversation_logs", where="user_id = %s", params=(1,))
    assert len(logs) == 2
    assert logs[0]["role"] == "user"
    assert logs[0]["content"] == "早安"
    assert logs[1]["role"] == "assistant"
    assert logs[1]["content"] == "好的！"


def test_handle_chat_message_prompt_includes_persona_and_user_message(fake_db):
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="今天天氣如何？"
    )

    assert "我是羅賓森" in llm_client.last_prompt
    assert "家人背景" in llm_client.last_prompt
    assert "今天天氣如何？" in llm_client.last_prompt


def test_handle_chat_message_prompt_states_no_web_search_capability(fake_db):
    # ADR-5：Gemini 2.5 世代對新 Key 關閉存取，grounding 整個移除，prompt 必須明確告知模型
    # 自己沒有查網路的能力，不知道就要誠實回報（透過固定標記讓程式碼判斷）。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="嗨")

    assert "沒有查詢網路的能力" in llm_client.last_prompt
    assert "【NOT_FOUND】" in llm_client.last_prompt


def test_handle_chat_message_prompt_includes_function_manual(fake_db):
    # FR-56a／b：使用者追問特定功能細節時，聊天核心要能依此回答並附範例（見 chat-core SPEC.md ADR-4）
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="記帳功能可以做什麼？"
    )

    assert "早餐花80元" in llm_client.last_prompt  # 記帳功能情境範例（FR-56d）


def test_handle_chat_message_prompt_includes_long_memory_summary(fake_db):
    _seed_general(fake_db)
    fake_db.insert(
        "conversation_summaries",
        {"user_id": 1, "summary": "很久以前提過喜歡打籃球", "summarized_up_to_log_id": 3},
    )
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="嗨")

    assert "很久以前提過喜歡打籃球" in llm_client.last_prompt


def test_handle_chat_message_triggers_memory_update_after_reply(fake_db):
    _seed_general(fake_db)
    # 先塞 19 則舊對話，這次對話會補上第 20 則使用者訊息 + 第 21 則回覆，backlog 應達門檻觸發摘要
    from datetime import datetime, timedelta, timezone

    base = datetime.now(timezone.utc)
    for i in range(19):
        fake_db.insert(
            "conversation_logs",
            {
                "user_id": 1,
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"msg-{i}",
                "created_at": base + timedelta(seconds=i),
                "deleted_at": None,
            },
        )
    llm_client = _FakeLLMClient(response_text="回覆")
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="嗨")

    assert text_llm_client.call_count == 1


def test_handle_chat_message_appends_self_search_suggestion_and_sets_pending_state_when_unknown(fake_db):
    # ADR-5：模型誠實回報不知道（回覆帶固定標記）時，附加建議文字並進入 pending_user_knowledge 狀態
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="這個我目前不知道耶【NOT_FOUND】")
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    reply = chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="國道現在塞車嗎？"
    )

    assert "這個我目前不知道耶" in reply
    assert "【NOT_FOUND】" not in reply  # 標記不應該外露給使用者
    assert "自行上網查詢" in reply
    assert store.get(1) == {"flow": "pending_user_knowledge", "target_user_id": 1}


def test_handle_pending_user_knowledge_step_saves_user_provided_answer(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_user_knowledge", "target_user_id": 1})

    reply = chat.handle_pending_user_knowledge_step(fake_db, store, telegram_user_id=1, text="威靈頓牛排食譜是...")

    assert "記錄" in reply
    assert store.get(1) is None
    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))
    assert len(rows) == 1
    assert rows[0]["content"] == "威靈頓牛排食譜是..."
