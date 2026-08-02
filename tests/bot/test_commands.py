import pytest

from src.bot import commands, templates, toggles
from src.bot.state import ConversationStateStore


class _FakeLLMClient:
    """模擬 submodules.llm.client.LLMClient，只實作 handle_function 會用到的 generate_text。"""

    def __init__(self, response_text="人格化後的功能總覽"):
        self.response_text = response_text
        self.last_prompt = None

    def generate_text(self, prompt):
        self.last_prompt = prompt
        return self.response_text


def test_handle_rule_returns_appendix_a_text():
    assert commands.handle_rule() == templates.APPENDIX_A_TEXT


# --- handle_recovered（FR-20，Step 1.6）---


class _FakeTelegramClient:
    """模擬 submodules.telegram.client.TelegramClient，只實作 handle_recovered 會用到的 send_text。"""

    def __init__(self, fail_for_chat_ids=()):
        self.sent = []
        self._fail_for_chat_ids = set(fail_for_chat_ids)

    def send_text(self, chat_id, text):
        if chat_id in self._fail_for_chat_ids:
            raise RuntimeError("Telegram API 掛了")
        self.sent.append((chat_id, text))


def test_handle_recovered_broadcasts_to_all_bound_non_owner_users(fake_db):
    fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    fake_db.insert("users", {"telegram_user_id": 2, "role": "媽媽", "is_owner": False})
    fake_db.insert("users", {"telegram_user_id": 3, "role": "爸爸", "is_owner": False})
    telegram_client = _FakeTelegramClient()

    reply = commands.handle_recovered(fake_db, telegram_client)

    assert {chat_id for chat_id, _ in telegram_client.sent} == {2, 3}
    assert all(text == commands._RECOVERED_BROADCAST_TEXT for _, text in telegram_client.sent)
    assert "2 位家人" in reply


def test_handle_recovered_excludes_unbound_users(fake_db):
    fake_db.insert("users", {"telegram_user_id": None, "role": "妹妹", "is_owner": False})
    telegram_client = _FakeTelegramClient()

    reply = commands.handle_recovered(fake_db, telegram_client)

    assert telegram_client.sent == []
    assert "0 位家人" in reply


def test_handle_recovered_continues_after_one_send_failure(fake_db):
    fake_db.insert("users", {"telegram_user_id": 2, "role": "媽媽", "is_owner": False})
    fake_db.insert("users", {"telegram_user_id": 3, "role": "爸爸", "is_owner": False})
    telegram_client = _FakeTelegramClient(fail_for_chat_ids={2})

    reply = commands.handle_recovered(fake_db, telegram_client)

    assert telegram_client.sent == [(3, commands._RECOVERED_BROADCAST_TEXT)]
    assert "1 位家人" in reply


def test_start_clean_all_dialog_confirm_reports_count_and_sets_pending_state(fake_db):
    fake_db.insert("conversation_logs", {"user_id": 1, "role": "user", "content": "早安", "deleted_at": None})
    fake_db.insert("conversation_logs", {"user_id": 1, "role": "assistant", "content": "早安！", "deleted_at": None})
    store = ConversationStateStore()

    reply = commands.start_clean_all_dialog_confirm(fake_db, store, telegram_user_id=1, user_id=1)

    assert "2 筆對話紀錄" in reply
    assert "確定要清除嗎" in reply
    assert store.get(1) == {"flow": "pending_clean_all_dialog_confirm", "target_user_id": 1}


def test_start_clean_all_dialog_confirm_reports_zero_when_no_logs(fake_db):
    store = ConversationStateStore()

    reply = commands.start_clean_all_dialog_confirm(fake_db, store, telegram_user_id=1, user_id=1)

    assert "0 筆對話紀錄" in reply


def test_handle_clean_all_dialog_confirm_step_moves_to_final_confirm_when_llm_confirms(fake_db):
    # 2026-08-02（FR-16a）：LLM 判定 CONFIRM 後不會馬上刪除，要先進入最終確認狀態。
    fake_db.insert("conversation_logs", {"user_id": 1, "role": "user", "content": "早安", "deleted_at": None})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_clean_all_dialog_confirm", "target_user_id": 1})
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_clean_all_dialog_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="對啊")

    assert "確認執行" in reply
    assert store.get(1) == {"flow": "pending_clean_all_dialog_final_confirm", "target_user_id": 1}
    logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(1,))
    assert len(logs) == 1  # 還沒真的刪除
    # prompt 必須把使用者的回覆帶進去，模型才有判斷依據
    assert "對啊" in llm_client.last_prompt


def test_handle_clean_all_dialog_final_confirm_step_deletes_when_keyword_typed(fake_db):
    fake_db.insert("conversation_logs", {"user_id": 1, "role": "user", "content": "早安", "deleted_at": None})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_clean_all_dialog_final_confirm", "target_user_id": 1})

    reply = commands.handle_clean_all_dialog_final_confirm_step(fake_db, store, telegram_user_id=1, text="確認執行")

    assert reply == "已經幫你清除所有對話紀錄囉！你的知識庫內容不會受影響。"
    assert store.get(1) is None
    logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(1,))
    assert logs == []


def test_handle_clean_all_dialog_final_confirm_step_cancels_on_wrong_text(fake_db):
    fake_db.insert("conversation_logs", {"user_id": 1, "role": "user", "content": "早安", "deleted_at": None})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_clean_all_dialog_final_confirm", "target_user_id": 1})

    reply = commands.handle_clean_all_dialog_final_confirm_step(fake_db, store, telegram_user_id=1, text="確定")

    assert reply == "好的，先不清除，你的對話紀錄都還在喔！"
    assert store.get(1) is None
    logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(1,))
    assert len(logs) == 1


def test_handle_clean_all_dialog_final_confirm_step_rejects_voice_and_keeps_state(fake_db):
    # 語音轉出來的文字即使剛好是「確認執行」也一律拒絕，且不清除狀態，讓使用者可以直接補打字重試。
    fake_db.insert("conversation_logs", {"user_id": 1, "role": "user", "content": "早安", "deleted_at": None})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_clean_all_dialog_final_confirm", "target_user_id": 1})

    reply = commands.handle_clean_all_dialog_final_confirm_step(
        fake_db, store, telegram_user_id=1, text="確認執行", via_voice=True
    )

    assert "打字" in reply
    assert store.get(1) == {"flow": "pending_clean_all_dialog_final_confirm", "target_user_id": 1}
    logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(1,))
    assert len(logs) == 1


def test_handle_clean_all_dialog_confirm_step_cancels_on_any_non_confirm_reply(fake_db):
    fake_db.insert("conversation_logs", {"user_id": 1, "role": "user", "content": "早安", "deleted_at": None})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_clean_all_dialog_confirm", "target_user_id": 1})
    llm_client = _FakeLLMClient(response_text="CANCEL")

    reply = commands.handle_clean_all_dialog_confirm_step(
        fake_db, llm_client, store, telegram_user_id=1, text="算了不要好了"
    )

    assert reply == "好的，先不清除，你的對話紀錄都還在喔！"
    assert store.get(1) is None
    logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(1,))
    assert len(logs) == 1


def test_handle_clean_all_dialog_soft_deletes_logs_resets_summary_and_keeps_knowledge_base(fake_db):
    fake_db.insert("conversation_logs", {"user_id": 1, "role": "user", "content": "早安", "deleted_at": None})
    fake_db.insert("conversation_logs", {"user_id": 1, "role": "assistant", "content": "早安！", "deleted_at": None})
    fake_db.insert("conversation_logs", {"user_id": 2, "role": "user", "content": "別人的訊息", "deleted_at": None})
    fake_db.insert(
        "conversation_summaries",
        {"user_id": 1, "summary": "很久以前提過喜歡打籃球", "summarized_up_to_log_id": 5},
    )
    fake_db.insert("knowledge_base", {"category": "custom", "user_id": 1, "content": "陳東東是我朋友"})

    reply = commands.handle_clean_all_dialog(fake_db, user_id=1)

    assert reply == "已經幫你清除所有對話紀錄囉！你的知識庫內容不會受影響。"

    remaining_logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(1,))
    assert remaining_logs == []
    # 只清自己的，其他使用者的對話紀錄不受影響（資安隔離）
    other_user_logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(2,))
    assert len(other_user_logs) == 1

    summary_row = fake_db.select("conversation_summaries", where="user_id = %s", params=(1,), fetch_one=True)
    assert summary_row["summary"] == ""
    assert summary_row["summarized_up_to_log_id"] == 0

    # 刻意不動知識庫內容（與規劃中的 /clean-target-dialog 不同）
    kb_rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))
    assert len(kb_rows) == 1


def test_handle_save_knowledge_confirm_step_moves_to_final_confirm_for_non_owner(fake_db, monkeypatch):
    # 2026-08-02（FR-16a）：DECISION=CONFIRM 後不會馬上寫入，權限強制（category 改回 custom）
    # 已經在這一步做完，狀態直接進入最終確認。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_save_knowledge_confirm", "target_user_id": 42, "original_request": "幫我存補胎SOP"})
    llm_client = _FakeLLMClient(
        # 中間刻意留一個空白行、以及一行沒有冒號的雜訊，涵蓋 _parse_key_value_block 的略過分支。
        response_text=(
            "DECISION: CONFIRM\n\n這是一行沒有冒號的雜訊\nCATEGORY: custom\nLABEL: SOP\nCONTENT: 補胎流程：先拆輪胎"
        )
    )

    reply = commands.handle_save_knowledge_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="對")

    assert "確認執行" in reply
    assert "補胎流程：先拆輪胎" in reply
    assert store.get(1) == {
        "flow": "pending_save_knowledge_final_confirm",
        "category": "custom",
        "label": "SOP",
        "content": "補胎流程：先拆輪胎",
        "row_user_id": 42,
    }
    assert fake_db.select("knowledge_base") == []  # 還沒真的寫入
    assert "使用者不是 Owner，CATEGORY 一律只能填 custom" in llm_client.last_prompt


def test_handle_save_knowledge_confirm_step_forces_custom_even_if_model_suggests_shared_for_non_owner(fake_db, monkeypatch):
    # 伺服器端最後一道防線：即使模型（可能被誘導）回傳 general_family，非 Owner 也一律強制改回 custom
    # ——這個判斷發生在轉入最終確認「之前」，所以最終確認狀態裡存的 category 一定已經是 custom。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_save_knowledge_confirm", "target_user_id": 42, "original_request": "幫我存家人背景"})
    llm_client = _FakeLLMClient(
        response_text="DECISION: CONFIRM\nCATEGORY: general_family\nLABEL: 家人\nCONTENT: 測試內容"
    )

    commands.handle_save_knowledge_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="對")

    assert store.get(1)["category"] == "custom"
    assert store.get(1)["row_user_id"] == 42


def test_handle_save_knowledge_confirm_step_allows_owner_to_save_to_general_family(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "1")
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_save_knowledge_confirm", "target_user_id": 1, "original_request": "新增家庭成員"})
    llm_client = _FakeLLMClient(
        response_text="DECISION: CONFIRM\nCATEGORY: general_family\nLABEL: 寵物\nCONTENT: 阿旺是一隻貓"
    )

    reply = commands.handle_save_knowledge_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="對")

    assert "Robin 與家人背景知識庫" in reply
    assert "阿旺是一隻貓" in reply
    assert store.get(1)["category"] == "general_family"
    assert store.get(1)["row_user_id"] is None
    assert "使用者是 Robin（Owner）" in llm_client.last_prompt


def test_handle_save_knowledge_final_confirm_step_saves_when_keyword_typed(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_save_knowledge_final_confirm",
            "category": "custom",
            "label": "SOP",
            "content": "補胎流程：先拆輪胎",
            "row_user_id": 42,
        },
    )

    reply = commands.handle_save_knowledge_final_confirm_step(fake_db, store, telegram_user_id=1, text="確認執行")

    assert reply == "已經幫你存到你的個人知識庫囉！「SOP」分類、內容是：補胎流程：先拆輪胎"
    assert store.get(1) is None
    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 42))
    assert len(rows) == 1
    assert rows[0]["content"] == "補胎流程：先拆輪胎"
    assert rows[0]["label"] == "SOP"


def test_handle_save_knowledge_final_confirm_step_cancels_on_wrong_text(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_save_knowledge_final_confirm",
            "category": "custom",
            "label": None,
            "content": "測試內容",
            "row_user_id": 42,
        },
    )

    reply = commands.handle_save_knowledge_final_confirm_step(fake_db, store, telegram_user_id=1, text="好啊")

    assert reply == "好的，先不儲存這筆資訊！"
    assert store.get(1) is None
    assert fake_db.select("knowledge_base") == []


def test_handle_save_knowledge_final_confirm_step_rejects_voice_and_keeps_state(fake_db):
    store = ConversationStateStore()
    state = {
        "flow": "pending_save_knowledge_final_confirm",
        "category": "custom",
        "label": None,
        "content": "測試內容",
        "row_user_id": 42,
    }
    store.set(1, state)

    reply = commands.handle_save_knowledge_final_confirm_step(
        fake_db, store, telegram_user_id=1, text="確認執行", via_voice=True
    )

    assert "打字" in reply
    assert store.get(1) == state
    assert fake_db.select("knowledge_base") == []


def test_handle_save_knowledge_confirm_step_cancels_and_writes_nothing(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_save_knowledge_confirm", "target_user_id": 42, "original_request": "幫我存"})
    llm_client = _FakeLLMClient(response_text="DECISION: CANCEL")

    reply = commands.handle_save_knowledge_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="不用了")

    assert reply == "好的，先不儲存這筆資訊！"
    assert store.get(1) is None
    assert fake_db.select("knowledge_base") == []


def test_start_clean_target_dialog_confirm_reports_no_data_when_nothing_exists(fake_db):
    llm_client = _FakeLLMClient()
    store = ConversationStateStore()

    reply = commands.start_clean_target_dialog_confirm(
        fake_db, llm_client, store, telegram_user_id=1, user_id=1, is_owner=False, topic="范麗芳"
    )

    assert reply == "目前沒有任何對話紀錄或知識庫資料，不需要清除喔！"
    assert store.get(1) is None


def test_start_clean_target_dialog_confirm_reports_no_match_found(fake_db):
    fake_db.insert("conversation_logs", {"user_id": 1, "role": "user", "content": "今天天氣真好", "deleted_at": None})
    llm_client = _FakeLLMClient(response_text="NONE")
    store = ConversationStateStore()

    reply = commands.start_clean_target_dialog_confirm(
        fake_db, llm_client, store, telegram_user_id=1, user_id=1, is_owner=False, topic="范麗芳"
    )

    assert reply == "目前沒有找到任何跟「范麗芳」有關的對話紀錄或知識庫資料喔！"
    assert store.get(1) is None


def test_start_clean_target_dialog_confirm_non_owner_excludes_shared_knowledge(fake_db):
    fake_db.insert("conversation_logs", {"user_id": 1, "role": "user", "content": "范麗芳人很好", "deleted_at": None})
    fake_db.insert("knowledge_base", {"category": "custom", "user_id": 1, "content": "范麗芳的電話", "label": None})
    fake_db.insert("knowledge_base", {"category": "general_family", "user_id": None, "content": "范麗芳是媽媽"})
    llm_client = _FakeLLMClient(response_text="1,2")
    store = ConversationStateStore()

    reply = commands.start_clean_target_dialog_confirm(
        fake_db, llm_client, store, telegram_user_id=1, user_id=1, is_owner=False, topic="范麗芳"
    )

    assert "范麗芳是媽媽" not in llm_client.last_prompt  # 非 Owner 看不到共用知識庫候選
    assert "1 則對話紀錄" in reply
    assert "1 筆知識庫資料" in reply
    assert store.get(1)["kb_ids"] == [
        fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))[0]["id"]
    ]


def test_start_clean_target_dialog_confirm_owner_includes_shared_knowledge(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "1")
    fake_db.insert("knowledge_base", {"category": "general_family", "user_id": None, "content": "范麗芳是媽媽"})
    fake_db.insert("knowledge_base", {"category": "general_persona", "user_id": None, "content": "范麗芳也認識羅賓森"})
    llm_client = _FakeLLMClient(response_text="1,2")
    store = ConversationStateStore()

    reply = commands.start_clean_target_dialog_confirm(
        fake_db, llm_client, store, telegram_user_id=1, user_id=1, is_owner=True, topic="范麗芳"
    )

    assert "范麗芳是媽媽" in llm_client.last_prompt
    assert "范麗芳也認識羅賓森" in llm_client.last_prompt  # 涵蓋 general_persona 候選也一併納入
    assert "2 筆知識庫資料" in reply


def test_handle_clean_target_dialog_confirm_step_moves_to_final_confirm_when_confirmed(fake_db):
    log_id = fake_db.insert(
        "conversation_logs", {"user_id": 1, "role": "user", "content": "范麗芳人很好", "deleted_at": None}
    )
    kb_id = fake_db.insert("knowledge_base", {"category": "custom", "user_id": 1, "content": "范麗芳的電話"})
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_clean_target_dialog_confirm",
            "target_user_id": 1,
            "topic": "范麗芳",
            "log_ids": [log_id],
            "kb_ids": [kb_id],
        },
    )
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_clean_target_dialog_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="對")

    assert "跟「范麗芳」有關的 1 則對話紀錄與 1 筆知識庫資料" in reply
    assert "確認執行" in reply
    assert store.get(1) == {
        "flow": "pending_clean_target_dialog_final_confirm",
        "topic": "范麗芳",
        "log_ids": [log_id],
        "kb_ids": [kb_id],
    }
    remaining_logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(1,))
    assert len(remaining_logs) == 1  # 還沒真的刪除
    remaining_kb = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))
    assert len(remaining_kb) == 1


def test_handle_clean_target_dialog_final_confirm_step_deletes_when_keyword_typed(fake_db):
    log_id = fake_db.insert(
        "conversation_logs", {"user_id": 1, "role": "user", "content": "范麗芳人很好", "deleted_at": None}
    )
    kb_id = fake_db.insert("knowledge_base", {"category": "custom", "user_id": 1, "content": "范麗芳的電話"})
    store = ConversationStateStore()
    store.set(
        1,
        {"flow": "pending_clean_target_dialog_final_confirm", "topic": "范麗芳", "log_ids": [log_id], "kb_ids": [kb_id]},
    )

    reply = commands.handle_clean_target_dialog_final_confirm_step(
        fake_db, store, telegram_user_id=1, text="確認執行"
    )

    assert reply == "已經幫你清除跟「范麗芳」有關的 1 則對話紀錄與 1 筆知識庫資料囉！"
    assert store.get(1) is None
    remaining_logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(1,))
    assert remaining_logs == []
    remaining_kb = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))
    assert remaining_kb == []


def test_handle_clean_target_dialog_final_confirm_step_cancels_on_wrong_text(fake_db):
    log_id = fake_db.insert(
        "conversation_logs", {"user_id": 1, "role": "user", "content": "范麗芳人很好", "deleted_at": None}
    )
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_clean_target_dialog_final_confirm", "topic": "范麗芳", "log_ids": [log_id], "kb_ids": []})

    reply = commands.handle_clean_target_dialog_final_confirm_step(fake_db, store, telegram_user_id=1, text="嗯")

    assert reply == "好的，先不清除，這些資料都還在喔！"
    assert store.get(1) is None
    remaining_logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(1,))
    assert len(remaining_logs) == 1


def test_handle_clean_target_dialog_final_confirm_step_rejects_voice_and_keeps_state(fake_db):
    log_id = fake_db.insert(
        "conversation_logs", {"user_id": 1, "role": "user", "content": "范麗芳人很好", "deleted_at": None}
    )
    store = ConversationStateStore()
    state = {"flow": "pending_clean_target_dialog_final_confirm", "topic": "范麗芳", "log_ids": [log_id], "kb_ids": []}
    store.set(1, state)

    reply = commands.handle_clean_target_dialog_final_confirm_step(
        fake_db, store, telegram_user_id=1, text="確認執行", via_voice=True
    )

    assert "打字" in reply
    assert store.get(1) == state
    remaining_logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(1,))
    assert len(remaining_logs) == 1


def test_handle_clean_target_dialog_confirm_step_keeps_data_when_cancelled(fake_db):
    log_id = fake_db.insert(
        "conversation_logs", {"user_id": 1, "role": "user", "content": "范麗芳人很好", "deleted_at": None}
    )
    kb_id = fake_db.insert("knowledge_base", {"category": "custom", "user_id": 1, "content": "范麗芳的電話"})
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_clean_target_dialog_confirm",
            "target_user_id": 1,
            "topic": "范麗芳",
            "log_ids": [log_id],
            "kb_ids": [kb_id],
        },
    )
    llm_client = _FakeLLMClient(response_text="CANCEL")

    reply = commands.handle_clean_target_dialog_confirm_step(
        fake_db, llm_client, store, telegram_user_id=1, text="算了"
    )

    assert reply == "好的，先不清除，這些資料都還在喔！"
    assert store.get(1) is None
    remaining_logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(1,))
    assert len(remaining_logs) == 1
    remaining_kb = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))
    assert len(remaining_kb) == 1


def test_handle_function_returns_llm_generated_overview(fake_db):
    llm_client = _FakeLLMClient(response_text="這是總覽")

    reply = commands.handle_function(fake_db, llm_client)

    assert reply == "這是總覽"


def test_handle_function_prompt_includes_persona_and_raw_overview(fake_db):
    fake_db.insert("knowledge_base", {"category": "general_persona", "user_id": None, "content": "我是羅賓森"})
    llm_client = _FakeLLMClient()

    commands.handle_function(fake_db, llm_client)

    assert "我是羅賓森" in llm_client.last_prompt
    for feature in templates.FEATURE_LIST:
        assert feature["name"] in llm_client.last_prompt


def test_start_set_invite_codes_sets_awaiting_role_state():
    store = ConversationStateStore()
    reply = commands.start_set_invite_codes(store, telegram_user_id=1)
    assert store.get(1) == {"flow": "set_invite_codes", "step": "awaiting_role"}
    assert "稱謂" in reply


def test_awaiting_role_step_with_role_text_moves_to_awaiting_code(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "set_invite_codes", "step": "awaiting_role"})

    reply = commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="爸爸")

    assert store.get(1) == {"flow": "set_invite_codes", "step": "awaiting_code", "role": "爸爸"}
    assert "爸爸" in reply
    assert "通關密碼" in reply
    # 這個步驟只暫存稱謂，還不該寫進資料庫（因為 code 還沒收到）
    assert fake_db.select("users") == []
    assert fake_db.select("invite_codes") == []


def test_awaiting_role_step_with_exit_phrase_clears_state(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "set_invite_codes", "step": "awaiting_role"})

    reply = commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="沒有了")

    assert store.get(1) is None
    assert "結束" in reply


def test_awaiting_role_step_with_alternate_exit_phrase_clears_state(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "set_invite_codes", "step": "awaiting_role"})

    commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="結束")

    assert store.get(1) is None


def test_awaiting_code_step_creates_user_and_invite_code(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "set_invite_codes", "step": "awaiting_code", "role": "爸爸"})

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
    store.set(1, {"flow": "set_invite_codes", "step": "awaiting_code", "role": "爸爸"})

    commands.handle_set_invite_codes_step(fake_db, store, telegram_user_id=1, text="dad-code-1")

    assert store.get(1) == {"flow": "set_invite_codes", "step": "awaiting_role"}


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


# --- /my_toggles、/set_toggle（docs/specs/feature-toggles/SPEC.md）---


def test_start_my_toggles_ensures_defaults_and_sets_awaiting_index_state(fake_db):
    store = ConversationStateStore()

    reply = commands.start_my_toggles(fake_db, store, telegram_user_id=1, user_id=42)

    assert store.get(1) == {"flow": "toggle", "step": "awaiting_index", "target_user_id": 42}
    assert "1. " in reply
    assert len(fake_db.select("feature_toggles", where="user_id = %s", params=(42,))) == 8


def test_handle_toggle_step_awaiting_index_toggles_and_shows_updated_list(fake_db):
    toggles.ensure_default_toggles(fake_db, user_id=42)
    store = ConversationStateStore()
    store.set(1, {"flow": "toggle", "step": "awaiting_index", "target_user_id": 42})

    reply = commands.handle_toggle_step(fake_db, store, telegram_user_id=1, text="1")

    assert "切換為關閉" in reply
    assert store.get(1) == {"flow": "toggle", "step": "awaiting_index", "target_user_id": 42}


def test_handle_toggle_step_awaiting_index_invalid_number_reprompts(fake_db):
    toggles.ensure_default_toggles(fake_db, user_id=42)
    store = ConversationStateStore()
    store.set(1, {"flow": "toggle", "step": "awaiting_index", "target_user_id": 42})

    reply = commands.handle_toggle_step(fake_db, store, telegram_user_id=1, text="99")

    assert "編號不存在" in reply
    # 狀態仍停留在 awaiting_index，讓使用者可以重新輸入
    assert store.get(1) == {"flow": "toggle", "step": "awaiting_index", "target_user_id": 42}


def test_handle_toggle_step_awaiting_index_non_numeric_reprompts(fake_db):
    toggles.ensure_default_toggles(fake_db, user_id=42)
    store = ConversationStateStore()
    store.set(1, {"flow": "toggle", "step": "awaiting_index", "target_user_id": 42})

    reply = commands.handle_toggle_step(fake_db, store, telegram_user_id=1, text="不是數字")

    assert "數字編號" in reply


def test_handle_toggle_step_awaiting_index_exit_phrase_clears_state(fake_db):
    toggles.ensure_default_toggles(fake_db, user_id=42)
    store = ConversationStateStore()
    store.set(1, {"flow": "toggle", "step": "awaiting_index", "target_user_id": 42})

    reply = commands.handle_toggle_step(fake_db, store, telegram_user_id=1, text="沒有了")

    assert store.get(1) is None
    assert "結束" in reply


def test_start_set_toggle_with_no_candidates_returns_message_without_state(fake_db):
    store = ConversationStateStore()

    reply = commands.start_set_toggle(fake_db, store, telegram_user_id=1)

    assert "沒有" in reply
    assert store.get(1) is None


def test_start_set_toggle_lists_bound_non_owner_users_only(fake_db):
    fake_db.insert("users", {"telegram_user_id": 100, "role": "Robin", "is_owner": True})
    fake_db.insert("users", {"telegram_user_id": 200, "role": "爸爸", "is_owner": False})
    fake_db.insert("users", {"telegram_user_id": None, "role": "媽媽", "is_owner": False})  # 尚未綁定
    store = ConversationStateStore()

    reply = commands.start_set_toggle(fake_db, store, telegram_user_id=1)

    assert "爸爸" in reply
    assert "媽媽" not in reply
    assert "Robin" not in reply
    assert store.get(1)["flow"] == "set_toggle"
    assert store.get(1)["step"] == "awaiting_user_selection"


def test_handle_toggle_step_awaiting_user_selection_valid_index_moves_to_awaiting_index(fake_db):
    dad_id = fake_db.insert("users", {"telegram_user_id": 200, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "set_toggle", "step": "awaiting_user_selection", "candidates": [dad_id]})

    reply = commands.handle_toggle_step(fake_db, store, telegram_user_id=1, text="1")

    assert store.get(1) == {"flow": "set_toggle", "step": "awaiting_index", "target_user_id": dad_id}
    assert "1. " in reply
    assert len(fake_db.select("feature_toggles", where="user_id = %s", params=(dad_id,))) == 8


def test_handle_toggle_step_awaiting_user_selection_invalid_index_reprompts(fake_db):
    dad_id = fake_db.insert("users", {"telegram_user_id": 200, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "set_toggle", "step": "awaiting_user_selection", "candidates": [dad_id]})

    reply = commands.handle_toggle_step(fake_db, store, telegram_user_id=1, text="5")

    assert "編號" in reply
    assert store.get(1)["step"] == "awaiting_user_selection"


def test_handle_toggle_step_awaiting_user_selection_exit_phrase_clears_state(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "set_toggle", "step": "awaiting_user_selection", "candidates": [42]})

    reply = commands.handle_toggle_step(fake_db, store, telegram_user_id=1, text="結束")

    assert store.get(1) is None
    assert "結束" in reply


def test_handle_toggle_step_raises_on_unknown_state(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "toggle", "step": "some_unexpected_step"})

    with pytest.raises(ValueError):
        commands.handle_toggle_step(fake_db, store, telegram_user_id=1, text="whatever")


# --- 待辦事項（FR-31、FR-31a、FR-32，Step 1.7）---


def test_handle_todo_confirm_step_moves_to_time_step_when_llm_confirms(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_confirm", "target_user_id": 42, "original_text": "我下午要去買菜"})
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_todo_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="好")

    assert reply == "好的，請問是什麼時候呢？"
    assert store.get(1) == {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "我下午要去買菜"}


def test_handle_todo_confirm_step_cancels_on_non_confirm(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_confirm", "target_user_id": 42, "original_text": "我下午要去買菜"})
    llm_client = _FakeLLMClient(response_text="CANCEL")

    reply = commands.handle_todo_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="不用")

    assert reply == "好的，這次就不記錄囉！"
    assert store.get(1) is None


def test_handle_todo_time_step_moves_to_reminder_step_when_clear(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "我下午要去買菜"})
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nCONTENT: 買菜\nDUE_AT: 2026-08-02 15:00")

    reply = commands.handle_todo_time_step(fake_db, llm_client, store, telegram_user_id=1, text="三點")

    assert "2026/08/02 15:00" in reply
    assert "提醒" in reply
    state = store.get(1)
    assert state["flow"] == "pending_todo_reminder"
    assert state["target_user_id"] == 42
    assert state["content"] == "買菜"
    assert state["due_at"].strftime("%Y-%m-%d %H:%M") == "2026-08-02 15:00"


def test_handle_todo_time_step_stays_when_unclear(fake_db):
    store = ConversationStateStore()
    original_state = {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "我要做事"}
    store.set(1, original_state)
    llm_client = _FakeLLMClient(response_text="STATUS: UNCLEAR")

    reply = commands.handle_todo_time_step(fake_db, llm_client, store, telegram_user_id=1, text="呃再說")

    assert "不太確定時間" in reply
    assert store.get(1) == original_state


def test_handle_todo_time_step_stays_when_due_at_unparseable(fake_db):
    store = ConversationStateStore()
    original_state = {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "我要做事"}
    store.set(1, original_state)
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nCONTENT: 做事\nDUE_AT: 不知道幾點")

    reply = commands.handle_todo_time_step(fake_db, llm_client, store, telegram_user_id=1, text="怪怪的回覆")

    assert "不太確定時間" in reply
    assert store.get(1) == original_state


def test_handle_todo_reminder_step_creates_todo_with_reminder_when_confirmed(fake_db):
    store = ConversationStateStore()
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    store.set(1, {"flow": "pending_todo_reminder", "target_user_id": 42, "content": "買菜", "due_at": due_at})
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_todo_reminder_step(fake_db, llm_client, store, telegram_user_id=1, text="好")

    assert reply == "好的，已經幫你記錄好了！"
    assert store.get(1) is None
    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(42, "pending"))
    assert len(rows) == 1
    assert rows[0]["content"] == "買菜"
    assert rows[0]["remind_before_30min"] is True


def test_handle_todo_reminder_step_creates_todo_without_reminder_when_declined(fake_db):
    store = ConversationStateStore()
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    store.set(1, {"flow": "pending_todo_reminder", "target_user_id": 42, "content": "買菜", "due_at": due_at})
    llm_client = _FakeLLMClient(response_text="CANCEL")

    commands.handle_todo_reminder_step(fake_db, llm_client, store, telegram_user_id=1, text="不用")

    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(42, "pending"))
    assert rows[0]["remind_before_30min"] is False


def test_start_todo_list_reports_no_todos_and_does_not_set_state(fake_db):
    store = ConversationStateStore()

    reply = commands.start_todo_list(fake_db, store, telegram_user_id=1, user_id=42)

    assert reply == "目前沒有待辦事項喔！"
    assert store.get(1) is None


def test_start_todo_list_shows_list_and_sets_pending_action_state(fake_db):
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {"user_id": 42, "content": "買菜", "due_at": due_at, "remind_before_30min": False, "status": "pending"},
    )
    store = ConversationStateStore()

    reply = commands.start_todo_list(fake_db, store, telegram_user_id=1, user_id=42)

    assert "買菜" in reply
    assert "結束" in reply
    assert store.get(1) == {"flow": "pending_todo_list_action", "target_user_id": 42, "todo_ids": [todo_id]}


def test_handle_todo_list_action_step_exit_phrase_clears_state(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_list_action", "target_user_id": 42, "todo_ids": [1]})

    reply = commands.handle_todo_list_action_step(fake_db, store, telegram_user_id=1, text="結束")

    assert store.get(1) is None
    assert "結束" in reply


def test_handle_todo_list_action_step_invalid_index_reprompts(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_list_action", "target_user_id": 42, "todo_ids": [1]})

    reply = commands.handle_todo_list_action_step(fake_db, store, telegram_user_id=1, text="99")

    assert "編號" in reply
    assert store.get(1)["flow"] == "pending_todo_list_action"


def test_handle_todo_list_action_step_valid_index_moves_to_action_confirm(fake_db):
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {"user_id": 42, "content": "買菜", "due_at": due_at, "remind_before_30min": False, "status": "pending"},
    )
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_list_action", "target_user_id": 42, "todo_ids": [todo_id]})

    reply = commands.handle_todo_list_action_step(fake_db, store, telegram_user_id=1, text="1")

    assert "買菜" in reply
    assert store.get(1) == {
        "flow": "pending_todo_action_confirm",
        "target_user_id": 42,
        "todo_id": todo_id,
        "content": "買菜",
    }


def test_handle_todo_action_confirm_step_marks_completed(fake_db):
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {"user_id": 42, "content": "買菜", "due_at": due_at, "remind_before_30min": False, "status": "pending"},
    )
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_action_confirm", "target_user_id": 42, "todo_id": todo_id, "content": "買菜"})
    llm_client = _FakeLLMClient(response_text="COMPLETE")

    reply = commands.handle_todo_action_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="做完了")

    assert "完成" in reply
    assert store.get(1) is None
    assert fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)["status"] == "completed"


def test_handle_todo_action_confirm_step_marks_cancelled(fake_db):
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {"user_id": 42, "content": "買菜", "due_at": due_at, "remind_before_30min": False, "status": "pending"},
    )
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_action_confirm", "target_user_id": 42, "todo_id": todo_id, "content": "買菜"})
    llm_client = _FakeLLMClient(response_text="CANCEL")

    reply = commands.handle_todo_action_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="不用了")

    assert "取消" in reply
    assert fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)["status"] == "cancelled"


def test_handle_todo_action_confirm_step_keeps_status_when_unclassifiable(fake_db):
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {"user_id": 42, "content": "買菜", "due_at": due_at, "remind_before_30min": False, "status": "pending"},
    )
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_action_confirm", "target_user_id": 42, "todo_id": todo_id, "content": "買菜"})
    llm_client = _FakeLLMClient(response_text="OTHER")

    reply = commands.handle_todo_action_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="嗯？")

    assert "不太確定" in reply
    assert fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)["status"] == "pending"
