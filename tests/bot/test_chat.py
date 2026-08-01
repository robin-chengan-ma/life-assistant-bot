from datetime import datetime
from zoneinfo import ZoneInfo

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


def test_handle_chat_message_prompt_includes_real_current_date(fake_db, monkeypatch):
    # Robin 回報問「今天幾月幾號」時模型瞎掰錯誤日期＋編造生日，改為把伺服器算好的真實日期
    # 塞進 prompt，不讓模型自己憑印象亂猜（見 chat.py 模組 docstring 2026-07-31 追加修正）。
    fixed_now = datetime(2026, 7, 31, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    monkeypatch.setattr(chat, "_now", lambda: fixed_now)
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="今天幾月幾號？"
    )

    assert "2026年7月31日 星期五" in llm_client.last_prompt


def test_handle_chat_message_prompt_forbids_fabricating_facts(fake_db):
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="嗨")

    assert "絕對不能捏造任何具體事實" in llm_client.last_prompt


def test_handle_chat_message_prompt_includes_pronoun_resolution_rule(fake_db):
    # Robin 回報：問「小布丁是誰」後接著問「他大概幾歲」，Robinson 誤把「他」理解成
    # 上一輪回答裡順便提到的照顧者（爺爺），而不是真正在討論的小布丁；使用者糾正
    # 「我說小布丁啦」後，Robinson 又只是重複貼一模一樣的舊答案，沒有真的回答年齡。
    # 加一條代名詞指涉規則，避免同樣的誤判再發生。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="那他大概幾歲啊"
    )

    assert "不要因為上一輪回答內容裡「順便提到」了其他人名" in llm_client.last_prompt
    assert "不能只是重複貼上一輪答過的舊內容" in llm_client.last_prompt


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
    assert store.get(1) == {
        "flow": "pending_user_knowledge",
        "target_user_id": 1,
        "original_question": "國道現在塞車嗎？",
    }


def test_handle_chat_message_deduplicates_suggestion_when_model_already_echoed_it(fake_db):
    # Robin 實測遇過：模型看了對話紀錄裡自己之前回覆過的建議句，有樣學樣把同一句話
    # 也寫進這次的回答裡，導致 code 又補一次，使用者收到重複兩次的建議句。
    _seed_general(fake_db)
    echoed = "我不知道耶。\n\n你可以先自行上網查詢，查到後把答案打給我，我會幫你記錄到知識庫喔！【NOT_FOUND】"
    llm_client = _FakeLLMClient(response_text=echoed)
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    reply = chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="吳鎧吉是誰"
    )

    assert reply.count("你可以先自行上網查詢") == 1


def test_handle_chat_message_prompt_includes_fuzzy_name_matching_rule(fake_db):
    # Robin 回報：知識庫存的是「吳凱吉」，打成「吳鎧吉」（同音字誤植）就直接被判定不知道，
    # 正常人類看了也知道在找誰；prompt 要指示模型合理假設打字誤植、別急著說不知道。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="吳鎧吉是誰"
    )

    assert "打字誤植" in llm_client.last_prompt


def test_handle_chat_message_saves_answer_when_llm_returns_save_marker(fake_db):
    # ADR-6：pending_user_knowledge 狀態下，是否要存檔改由同一次 LLM 呼叫判斷，
    # 不再無條件把下一則訊息當成答案。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="【SAVE_ANSWER】")
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_user_knowledge", "target_user_id": 1, "original_question": "陳東東是誰"})

    reply = chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1,
        text="陳東東是我朋友，住台北", pending_question="陳東東是誰",
    )

    assert reply == "已經幫你記錄到知識庫囉！"
    assert store.get(1) is None
    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))
    assert len(rows) == 1
    assert rows[0]["content"] == "陳東東是我朋友，住台北"
    # prompt 必須把待確認的問題帶進去，模型才有判斷依據
    assert "陳東東是誰" in llm_client.last_prompt
    assert "【SAVE_ANSWER】" in llm_client.last_prompt


def test_handle_chat_message_declines_when_llm_returns_decline_marker(fake_db):
    # Robin 回報：明確說「不用紀錄啦」還是被存進知識庫，改由模型判斷拒絕意圖。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="【DECLINE_SAVE】")
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_user_knowledge", "target_user_id": 1, "original_question": "陳東東是誰"})

    reply = chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1,
        text="不用紀錄啦", pending_question="陳東東是誰",
    )

    assert reply == "好的，這次就不記錄囉！"
    assert store.get(1) is None
    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))
    assert len(rows) == 0


def test_handle_chat_message_treats_unrelated_new_question_normally_when_pending(fake_db):
    # Robin 回報：問「陳東東是誰」被回不知道後，換問「吳凱吉是誰」（全新問題），
    # 結果被無條件當成「陳東東」的答案存檔。模型若判斷是無關新問題，不應輸出任何標記，
    # 直接照一般規則回答，且不該把答案存錯地方，也要清掉舊的 pending 狀態。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="吳凱吉是 Robin 的妹夫喔！")
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_user_knowledge", "target_user_id": 1, "original_question": "陳東東是誰"})

    reply = chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1,
        text="吳凱吉是誰", pending_question="陳東東是誰",
    )

    assert reply == "吳凱吉是 Robin 的妹夫喔！"
    assert store.get(1) is None
    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))
    assert len(rows) == 0


def test_handle_chat_message_replaces_pending_state_when_still_unknown_while_pending(fake_db):
    # 使用者在 pending_user_knowledge 狀態下又問了另一個知識庫沒有的新問題，
    # 應該用新問題覆蓋舊的 pending 狀態，而不是卡在原本那題。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="這個也不知道耶【NOT_FOUND】")
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_user_knowledge", "target_user_id": 1, "original_question": "陳東東是誰"})

    chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1,
        text="林小明是誰", pending_question="陳東東是誰",
    )

    assert store.get(1) == {
        "flow": "pending_user_knowledge",
        "target_user_id": 1,
        "original_question": "林小明是誰",
    }


def test_build_prompt_includes_pending_question_block_only_when_provided(fake_db):
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="嗨")

    assert "特別狀況" not in llm_client.last_prompt


def test_handle_chat_message_prompt_includes_conciseness_rule(fake_db):
    # 2026-08-01（FR-3f）：Robin 回報問「Robin 幾歲」被複述整段生日與計算過程、問「牛牛是什麼顏色」
    # 被附加一整段外觀描述，實際上只需要回核心答案；prompt 要指示模型精簡直接。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="Robin 今年幾歲？"
    )

    assert "回答務必精簡直接" in llm_client.last_prompt


def test_handle_chat_message_sets_pending_name_confirm_state_when_llm_returns_confirm_marker(fake_db):
    # 2026-08-01（ADR-7）：打字誤植不再直接假設回答，改為輸出 CONFIRM_NAME 標記、先反問確認。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="你是說『吳凱吉』嗎？【CONFIRM_NAME】")
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    reply = chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="吳鎧吉是誰"
    )

    assert reply == "你是說『吳凱吉』嗎？"
    assert "【CONFIRM_NAME】" not in reply
    assert store.get(1) == {
        "flow": "pending_name_confirm",
        "target_user_id": 1,
        "original_question": "吳鎧吉是誰",
    }


def test_handle_chat_message_confirming_question_answers_directly_when_user_confirms(fake_db):
    # 使用者確認（或講出更明確的名字）後，這一輪應該針對原問題完整回答，不再輸出任何標記。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="吳凱吉是 Robin 的妹夫喔！")
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_name_confirm", "target_user_id": 1, "original_question": "吳鎧吉是誰"})

    reply = chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1,
        text="對啊", confirming_question="吳鎧吉是誰",
    )

    assert reply == "吳凱吉是 Robin 的妹夫喔！"
    assert store.get(1) is None
    # prompt 必須把原本疑似打字誤植的問題帶進去，模型才有判斷依據
    assert "吳鎧吉是誰" in llm_client.last_prompt
    assert "疑似打字誤植" in llm_client.last_prompt


def test_handle_chat_message_confirming_question_treats_denial_as_new_message(fake_db):
    # 使用者否認猜測、或其實在問別的事時，完全忽略這個特別狀況，照一般規則正常回答，
    # 不假設使用者在回答上一題，且要清除舊的 pending_name_confirm 狀態（不殘留卡住下一輪）。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="這個我目前不知道耶【NOT_FOUND】")
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_name_confirm", "target_user_id": 1, "original_question": "吳鎧吉是誰"})

    reply = chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1,
        text="不是啦，我問別的", confirming_question="吳鎧吉是誰",
    )

    assert "這個我目前不知道耶" in reply
    assert store.get(1) == {
        "flow": "pending_user_knowledge",
        "target_user_id": 1,
        "original_question": "不是啦，我問別的",
    }
