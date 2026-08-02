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


# --- 個資遮蔽整合（2026-08-02，見 docs/specs/privacy-masking/SPEC.md FR-4） ---

def test_handle_chat_message_masks_pii_before_prompt_and_log(fake_db):
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="收到！")
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    reply = chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store,
        telegram_user_id=1, user_id=1, text="我的手機是 0912345678",
    )

    assert "0912345678" not in llm_client.last_prompt
    assert "[已遮蔽個資]" in llm_client.last_prompt
    logs = fake_db.select("conversation_logs", where="user_id = %s", params=(1,))
    assert logs[0]["content"] == "我的手機是 [已遮蔽個資]"
    assert "0912345678" not in logs[0]["content"]
    assert "提醒" in reply
    assert reply.startswith("收到！")


def test_handle_chat_message_no_reminder_when_no_pii_detected(fake_db):
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="收到！")
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    reply = chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="早安",
    )

    assert reply == "收到！"


def test_handle_chat_message_privacy_llm_client_none_only_runs_regex_layer(fake_db):
    """`privacy_llm_client` 預設 None，不影響既有呼叫端（webhook.py 未設定 GEMINI_API_PRIVACY_KEY
    時的優雅降級行為，見 privacy-masking SPEC.md ADR-2）。"""
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="收到！")
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    reply = chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store,
        telegram_user_id=1, user_id=1, text="我的手機是 0912345678",
        privacy_llm_client=None,
    )

    assert "提醒" in reply


def test_handle_chat_message_uses_dedicated_privacy_llm_client_for_semantic_layer(fake_db):
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(response_text="收到！")
    text_llm_client = _FakeTextLLMClient()
    privacy_llm_client = _FakeLLMClient(response_text="今天天氣真好")
    store = ConversationStateStore()

    chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store,
        telegram_user_id=1, user_id=1, text="今天天氣真好",
        privacy_llm_client=privacy_llm_client,
    )

    # 語意層真的有被呼叫到（用獨立的 privacy_llm_client，不是聊天用的 llm_client）。
    assert privacy_llm_client.last_prompt is not None
    assert llm_client.last_prompt is not None


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


def test_handle_chat_message_prompt_includes_pronoun_recency_and_confirm_when_unsure_rule(fake_db):
    # Robin 回報：問「小雯有養動物嗎」→（中間插入不相關問題）→「范麗芳是誰」→「她老公是誰」，
    # Robinson 誤把「她」理解成更早之前提過的小雯，而不是最近一次才明確點名問過的范麗芳。
    # prompt 要明確規定以「最近一次明確點名」為準，且沒把握就要反問，不要用假設硬答。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="她老公是誰"
    )

    assert "以那之後最新一次明確點名的對象為準，不可以跳回更早之前提過的人" in llm_client.last_prompt
    assert "只要你自己沒有百分之百把握代名詞指的是誰" in llm_client.last_prompt
    assert "絕對不要用可能錯誤的假設硬答" in llm_client.last_prompt


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


def test_handle_chat_message_prompt_forbids_falsely_claiming_knowledge_was_saved(fake_db):
    # Robin 回報：請 Robinson 把家庭成員背景「新增到知識庫」，Robinson 回覆已經新增，但當時
    # 完全沒有對應的寫入路徑，等於謊報成功；prompt 要明確禁止這種說法（2026-08-01 新增
    # REQUEST_SAVE 流程後，唯一合法的寫入時機是使用者確認之後的下一輪，不是這一輪）。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1,
        text="幫我把這個家庭成員的背景新增到知識庫",
    )

    assert "都絕對不能宣稱『已經記錄』" in llm_client.last_prompt
    assert "資料庫的實際寫入只會發生在使用者對上述反問句" in llm_client.last_prompt


def test_handle_chat_message_prompt_includes_request_save_rule_and_marker(fake_db):
    # 2026-08-01（FR-11）：使用者主動要求記住/新增知識時，prompt 要指示模型先反問確認
    # 內容與分類標籤，並輸出 REQUEST_SAVE 標記，而不是直接回答或假裝已經存了。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1,
        text="幫我存『補胎 SOP』：先拆輪胎、找到破洞、打磨、上膠、補片",
    )

    assert "【REQUEST_SAVE】" in llm_client.last_prompt
    assert "分類/標籤" in llm_client.last_prompt


def test_handle_chat_message_prompt_lets_owner_choose_shared_or_personal_scope(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "1")
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1,
        text="幫我新增一個家庭成員背景",
    )

    assert "使用者是 Robin（Owner）" in llm_client.last_prompt
    assert "全家共用的『Robin 與家人背景』" in llm_client.last_prompt


def test_handle_chat_message_prompt_restricts_non_owner_to_personal_scope(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "999")  # 跟 telegram_user_id=1 不同，代表非 Owner
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="幫我記住這件事"
    )

    assert "這位使用者不是 Robin（Owner）" in llm_client.last_prompt
    assert "只會存到使用者自己的個人知識庫" in llm_client.last_prompt


def test_handle_chat_message_sets_pending_save_knowledge_confirm_state_when_llm_returns_request_save_marker(fake_db):
    _seed_general(fake_db)
    llm_client = _FakeLLMClient(
        response_text="好的，我要把這個存到你的個人知識庫，分類是「SOP」，確定要儲存嗎？【REQUEST_SAVE】"
    )
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    reply = chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1,
        text="幫我存『補胎 SOP』：先拆輪胎、找到破洞、打磨、上膠、補片",
    )

    assert reply == "好的，我要把這個存到你的個人知識庫，分類是「SOP」，確定要儲存嗎？"
    assert "【REQUEST_SAVE】" not in reply
    assert store.get(1) == {
        "flow": "pending_save_knowledge_confirm",
        "target_user_id": 1,
        "original_request": "幫我存『補胎 SOP』：先拆輪胎、找到破洞、打磨、上膠、補片",
    }


def test_handle_chat_message_prompt_requires_real_similar_name_for_confirm_name_and_falls_back_to_unknown(fake_db):
    # Robin 回報：問「阿牛是誰」（知識庫裡當時沒有這個人/寵物）卻被反問「你是說『吳凱吉』嗎？」，
    # 兩者毫無相似之處；原因是舊 prompt 範例寫死了真實姓名，模型照抄範例而非真的比對知識庫。
    # 新規則要求反問一定要帶出資料中真實存在的相似人名，且沒有相似人名時要直接走「不知道」規則。
    _seed_general(fake_db)
    llm_client = _FakeLLMClient()
    text_llm_client = _FakeTextLLMClient()
    store = ConversationStateStore()

    chat.handle_chat_message(
        fake_db, llm_client, text_llm_client, store, telegram_user_id=1, user_id=1, text="阿牛是誰"
    )

    assert "反問句裡一定要帶出以上資料中真實存在的那個人名" in llm_client.last_prompt
    assert "絕對不可以套用其他" in llm_client.last_prompt
    assert "如果以上資料裡根本沒有任何跟使用者打的名字相似的人名，代表這是真的不知道" in llm_client.last_prompt


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
