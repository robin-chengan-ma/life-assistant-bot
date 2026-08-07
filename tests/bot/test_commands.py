from datetime import date, datetime, timezone
from unittest.mock import MagicMock

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


def test_handle_todo_time_step_moves_to_reminder_step_when_clear(fake_db, monkeypatch):
    # 2026-08-02 追加：due_at 是「今天」但現在還沒到早上 8 點，8 點提醒的承諾仍然成立。
    monkeypatch.setattr(commands, "_now", lambda: datetime(2026, 8, 2, 7, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "我下午要去買菜"})
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nCONTENT: 買菜\nDUE_AT: 2026-08-02 15:00")

    reply = commands.handle_todo_time_step(fake_db, llm_client, store, telegram_user_id=1, text="下午三點")

    assert "2026/08/02 15:00" in reply
    assert "早上 8 點會主動提醒你一次" in reply
    state = store.get(1)
    assert state["flow"] == "pending_todo_reminder"
    assert state["target_user_id"] == 42
    assert state["content"] == "買菜"
    assert state["due_at"].strftime("%Y-%m-%d %H:%M") == "2026-08-02 15:00"


def test_handle_todo_time_step_skips_digest_promise_when_8am_already_passed(fake_db, monkeypatch):
    # Robin 實測回報：中午設定當天下午才要執行的待辦，卻還是收到「當天早上 8 點會提醒你」——
    # 這句話是不可能發生的事，因為當下 8 點早就過了；改用另一句話講清楚不會收到今天的早上摘要。
    monkeypatch.setattr(commands, "_now", lambda: datetime(2026, 8, 2, 12, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "下午要載妹妹到水里"})
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nCONTENT: 載妹妹到水里\nDUE_AT: 2026-08-02 17:30")

    reply = commands.handle_todo_time_step(fake_db, llm_client, store, telegram_user_id=1, text="下午5:30")

    assert "已經過了今天的早上 8 點" in reply
    assert "不會收到當天早上的提醒摘要" in reply
    assert "早上 8 點會主動提醒你一次" not in reply


def test_handle_todo_time_step_keeps_digest_promise_for_future_due_date(fake_db, monkeypatch):
    # due_at 是「明天」，即使現在已經是今天晚上（早就過了今天的 8 點），明天的 8 點摘要仍然會發生。
    monkeypatch.setattr(commands, "_now", lambda: datetime(2026, 8, 2, 20, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "明天要交報告"})
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nCONTENT: 交報告\nDUE_AT: 2026-08-03 09:00")

    reply = commands.handle_todo_time_step(fake_db, llm_client, store, telegram_user_id=1, text="明天上午九點")

    assert "早上 8 點會主動提醒你一次" in reply
    assert "已經過了" not in reply


def test_handle_todo_time_step_parses_range_and_stores_start_at(fake_db, monkeypatch):
    # FR-31b：Robin 詢問「待辦事項是不是只能存單一時間點」後新增的區間支援。
    monkeypatch.setattr(commands, "_now", lambda: datetime(2026, 8, 1, 20, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "我要出差"})
    llm_client = _FakeLLMClient(
        response_text="STATUS: CLEAR\nCONTENT: 出差\nSTART_AT: 2026-08-02 08:00\nDUE_AT: 2026-08-05 17:00"
    )

    reply = commands.handle_todo_time_step(
        fake_db, llm_client, store, telegram_user_id=1, text="8/2早上8點到8/5下午5點"
    )

    assert "2026/08/02 08:00 ～ 2026/08/05 17:00" in reply
    assert "開始那天跟結束那天的早上 8 點都會主動提醒你一次" in reply
    state = store.get(1)
    assert state["start_at"].strftime("%Y-%m-%d %H:%M") == "2026-08-02 08:00"
    assert state["due_at"].strftime("%Y-%m-%d %H:%M") == "2026-08-05 17:00"


def test_handle_todo_time_step_range_start_day_digest_already_passed(fake_db, monkeypatch):
    # 現在是 8/2 中午，區間開始日就是今天、8 點早就過了；結束日還沒到，只會在結束日提醒。
    monkeypatch.setattr(commands, "_now", lambda: datetime(2026, 8, 2, 12, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "我要出差"})
    llm_client = _FakeLLMClient(
        response_text="STATUS: CLEAR\nCONTENT: 出差\nSTART_AT: 2026-08-02 06:00\nDUE_AT: 2026-08-05 17:00"
    )

    reply = commands.handle_todo_time_step(
        fake_db, llm_client, store, telegram_user_id=1, text="今天早上6點到8/5下午5點"
    )

    assert "已經過了開始那天的早上 8 點" in reply
    assert "只會在結束那天的早上 8 點提醒你一次" in reply


def test_handle_todo_time_step_range_both_digest_windows_passed(fake_db, monkeypatch):
    # 開始日、結束日都已經過了今天的 8 點（極端 edge case，仍要能講得通、不誤報）。
    monkeypatch.setattr(commands, "_now", lambda: datetime(2026, 8, 5, 20, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "我要出差"})
    llm_client = _FakeLLMClient(
        response_text="STATUS: CLEAR\nCONTENT: 出差\nSTART_AT: 2026-08-02 06:00\nDUE_AT: 2026-08-05 17:00"
    )

    reply = commands.handle_todo_time_step(
        fake_db, llm_client, store, telegram_user_id=1, text="8/2早上6點到今天下午5點"
    )

    assert "開始跟結束那天的早上 8 點都已經過了" in reply
    assert "不會收到早上的提醒摘要" in reply


def test_handle_todo_time_step_range_single_day_uses_point_in_time_logic(fake_db, monkeypatch):
    # 開始日跟結束日是同一天（一日內區間），跟單一時間點待辦一樣只判斷一次。
    monkeypatch.setattr(commands, "_now", lambda: datetime(2026, 8, 2, 7, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "全天會議"})
    llm_client = _FakeLLMClient(
        response_text="STATUS: CLEAR\nCONTENT: 全天會議\nSTART_AT: 2026-08-02 08:00\nDUE_AT: 2026-08-02 17:00"
    )

    reply = commands.handle_todo_time_step(
        fake_db, llm_client, store, telegram_user_id=1, text="今天早上8點到今天下午5點"
    )

    assert "到時候開始那天跟結束那天的早上 8 點都會主動提醒你一次" in reply


def test_handle_todo_time_step_ignores_unparseable_start_at_as_point_in_time(fake_db, monkeypatch):
    # START_AT 格式壞掉時不該讓整輪打回 UNCLEAR，退化成只看 DUE_AT 的單一時間點待辦。
    monkeypatch.setattr(commands, "_now", lambda: datetime(2026, 8, 2, 7, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "買菜"})
    llm_client = _FakeLLMClient(
        response_text="STATUS: CLEAR\nCONTENT: 買菜\nSTART_AT: 亂七八糟\nDUE_AT: 2026-08-02 15:00"
    )

    reply = commands.handle_todo_time_step(fake_db, llm_client, store, telegram_user_id=1, text="下午三點")

    assert "2026/08/02 15:00" in reply
    assert "～" not in reply
    assert store.get(1)["start_at"] is None


def test_handle_todo_time_step_stays_when_unclear(fake_db):
    store = ConversationStateStore()
    original_state = {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "我要做事"}
    store.set(1, original_state)
    llm_client = _FakeLLMClient(response_text="STATUS: UNCLEAR")

    reply = commands.handle_todo_time_step(fake_db, llm_client, store, telegram_user_id=1, text="呃再說")

    assert "不太確定時間" in reply
    assert store.get(1) == original_state


def test_handle_todo_time_step_stays_when_due_at_missing_entirely(fake_db):
    # 防呆：即使模型宣稱 CLEAR，但漏輸出 DUE_AT 這個必要欄位（格式不對的另一種情況：完全沒有，
    # 不是格式錯誤），一樣要當成 UNCLEAR 處理，不能讓 due_at 是 None 卻繼續往下走。
    store = ConversationStateStore()
    original_state = {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "我要做事"}
    store.set(1, original_state)
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nCONTENT: 做事")

    reply = commands.handle_todo_time_step(fake_db, llm_client, store, telegram_user_id=1, text="怪怪的回覆")

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


def test_handle_todo_reminder_step_moves_to_calendar_sync_step_when_confirmed(fake_db):
    # 2026-08-05 起（FR-66a、ADR-17）：這一步不再直接寫入 todos，改成再多問一輪同步詢問。
    store = ConversationStateStore()
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    store.set(1, {"flow": "pending_todo_reminder", "target_user_id": 42, "content": "買菜", "due_at": due_at})
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_todo_reminder_step(fake_db, llm_client, store, telegram_user_id=1, text="好")

    assert "同步到 Google 家庭行事曆" in reply
    state = store.get(1)
    assert state["flow"] == "pending_todo_calendar_sync"
    assert state["target_user_id"] == 42
    assert state["content"] == "買菜"
    assert state["due_at"] == due_at
    assert state["remind_before_30min"] is True
    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(42, "pending"))
    assert len(rows) == 0  # 還沒真正寫入，要等 pending_todo_calendar_sync 這一步確認後才寫入


def test_handle_todo_reminder_step_records_declined_reminder_in_state(fake_db):
    store = ConversationStateStore()
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    store.set(1, {"flow": "pending_todo_reminder", "target_user_id": 42, "content": "買菜", "due_at": due_at})
    llm_client = _FakeLLMClient(response_text="CANCEL")

    commands.handle_todo_reminder_step(fake_db, llm_client, store, telegram_user_id=1, text="不用")

    assert store.get(1)["remind_before_30min"] is False


def test_handle_todo_reminder_step_passes_start_at_to_state(fake_db):
    # FR-31b：pending_todo_reminder 狀態帶著 start_at 時，要一併帶到下一個狀態。
    store = ConversationStateStore()
    start_at = commands.datetime(2026, 8, 2, 8, 0, tzinfo=commands._TAIWAN_TZ)
    due_at = commands.datetime(2026, 8, 5, 17, 0, tzinfo=commands._TAIWAN_TZ)
    store.set(
        1,
        {
            "flow": "pending_todo_reminder",
            "target_user_id": 42,
            "content": "出差",
            "due_at": due_at,
            "start_at": start_at,
        },
    )
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    commands.handle_todo_reminder_step(fake_db, llm_client, store, telegram_user_id=1, text="好")

    state = store.get(1)
    assert state["start_at"] == start_at
    assert state["due_at"] == due_at


# --- pending_todo_calendar_sync（FR-66a，2026-08-05，見 ADR-17） ---


def _set_pending_todo_calendar_sync_state(store, **overrides):
    state = {
        "flow": "pending_todo_calendar_sync",
        "target_user_id": 42,
        "content": "買菜",
        "due_at": commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ),
        "start_at": None,
        "remind_before_30min": True,
    }
    state.update(overrides)
    store.set(1, state)
    return state


def test_handle_todo_calendar_sync_step_creates_todo_without_sync_when_declined(fake_db):
    store = ConversationStateStore()
    _set_pending_todo_calendar_sync_state(store)
    llm_client = _FakeLLMClient(response_text="CANCEL")

    reply = commands.handle_todo_calendar_sync_step(fake_db, llm_client, store, telegram_user_id=1, text="不用")

    assert reply == "好的，已經幫你記錄好了！"
    assert store.get(1) is None
    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(42, "pending"))
    assert len(rows) == 1
    assert rows[0]["sync_to_calendar"] is False
    assert rows[0].get("google_calendar_event_id") is None


def test_handle_todo_calendar_sync_step_creates_event_when_confirmed(fake_db):
    store = ConversationStateStore()
    _set_pending_todo_calendar_sync_state(store)
    llm_client = _FakeLLMClient(response_text="CONFIRM")
    calendar_client = MagicMock()
    calendar_client.create_event.return_value = "event-abc123"

    reply = commands.handle_todo_calendar_sync_step(
        fake_db, llm_client, store, telegram_user_id=1, text="要", calendar_client=calendar_client
    )

    assert reply == "好的，已經幫你記錄好了！"
    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(42, "pending"))
    assert rows[0]["sync_to_calendar"] is True
    assert rows[0]["google_calendar_event_id"] == "event-abc123"
    calendar_client.create_event.assert_called_once()
    call_kwargs = calendar_client.create_event.call_args.kwargs
    assert call_kwargs["summary"] == "買菜"
    assert call_kwargs["start"] == "2026-08-02T15:00:00+08:00"
    assert call_kwargs["end"] == "2026-08-02T15:30:00+08:00"  # 單一時間點預設 30 分鐘時長


def test_handle_todo_calendar_sync_step_uses_range_window_for_interval_todo(fake_db):
    store = ConversationStateStore()
    start_at = commands.datetime(2026, 8, 2, 8, 0, tzinfo=commands._TAIWAN_TZ)
    due_at = commands.datetime(2026, 8, 5, 17, 0, tzinfo=commands._TAIWAN_TZ)
    _set_pending_todo_calendar_sync_state(store, content="出差", due_at=due_at, start_at=start_at)
    llm_client = _FakeLLMClient(response_text="CONFIRM")
    calendar_client = MagicMock()
    calendar_client.create_event.return_value = "event-xyz"

    commands.handle_todo_calendar_sync_step(
        fake_db, llm_client, store, telegram_user_id=1, text="要", calendar_client=calendar_client
    )

    call_kwargs = calendar_client.create_event.call_args.kwargs
    assert call_kwargs["start"] == "2026-08-02T08:00:00+08:00"
    assert call_kwargs["end"] == "2026-08-05T17:00:00+08:00"


def test_handle_todo_calendar_sync_step_skips_event_creation_when_client_is_none(fake_db):
    # calendar_client 為 None（環境變數未設定）時優雅降級：待辦仍成功記錄，只是不建立 Calendar 事件。
    store = ConversationStateStore()
    _set_pending_todo_calendar_sync_state(store)
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_todo_calendar_sync_step(
        fake_db, llm_client, store, telegram_user_id=1, text="要", calendar_client=None
    )

    assert reply == "好的，已經幫你記錄好了！"
    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(42, "pending"))
    assert rows[0]["sync_to_calendar"] is True
    assert rows[0].get("google_calendar_event_id") is None


def test_handle_todo_calendar_sync_step_swallows_calendar_exception(fake_db):
    # Calendar API 呼叫失敗不該影響待辦事項已經成功記錄。
    store = ConversationStateStore()
    _set_pending_todo_calendar_sync_state(store)
    llm_client = _FakeLLMClient(response_text="CONFIRM")
    calendar_client = MagicMock()
    calendar_client.create_event.side_effect = RuntimeError("boom")

    reply = commands.handle_todo_calendar_sync_step(
        fake_db, llm_client, store, telegram_user_id=1, text="要", calendar_client=calendar_client
    )

    assert reply == "好的，已經幫你記錄好了！"
    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(42, "pending"))
    assert rows[0]["sync_to_calendar"] is True
    assert rows[0].get("google_calendar_event_id") is None


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
        "google_calendar_event_id": None,
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


def test_handle_todo_action_confirm_step_deletes_calendar_event_when_synced(fake_db):
    # 2026-08-05（FR-66a、ADR-17）：標記完成/取消時，如果這筆待辦當初有同步，要刪除對應事件。
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {
            "user_id": 42, "content": "買菜", "due_at": due_at, "remind_before_30min": False,
            "status": "pending", "sync_to_calendar": True, "google_calendar_event_id": "event-abc123",
        },
    )
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_todo_action_confirm", "target_user_id": 42, "todo_id": todo_id,
            "content": "買菜", "google_calendar_event_id": "event-abc123",
        },
    )
    llm_client = _FakeLLMClient(response_text="COMPLETE")
    calendar_client = MagicMock()

    commands.handle_todo_action_confirm_step(
        fake_db, llm_client, store, telegram_user_id=1, text="做完了", calendar_client=calendar_client
    )

    calendar_client.delete_event.assert_called_once_with(event_id="event-abc123")


def test_handle_todo_action_confirm_step_skips_calendar_delete_when_not_synced(fake_db):
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {"user_id": 42, "content": "買菜", "due_at": due_at, "remind_before_30min": False, "status": "pending"},
    )
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_action_confirm", "target_user_id": 42, "todo_id": todo_id, "content": "買菜"})
    llm_client = _FakeLLMClient(response_text="COMPLETE")
    calendar_client = MagicMock()

    commands.handle_todo_action_confirm_step(
        fake_db, llm_client, store, telegram_user_id=1, text="做完了", calendar_client=calendar_client
    )

    calendar_client.delete_event.assert_not_called()


def test_handle_todo_action_confirm_step_swallows_calendar_delete_exception(fake_db):
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {
            "user_id": 42, "content": "買菜", "due_at": due_at, "remind_before_30min": False,
            "status": "pending", "sync_to_calendar": True, "google_calendar_event_id": "event-abc123",
        },
    )
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_todo_action_confirm", "target_user_id": 42, "todo_id": todo_id,
            "content": "買菜", "google_calendar_event_id": "event-abc123",
        },
    )
    llm_client = _FakeLLMClient(response_text="COMPLETE")
    calendar_client = MagicMock()
    calendar_client.delete_event.side_effect = RuntimeError("boom")

    reply = commands.handle_todo_action_confirm_step(
        fake_db, llm_client, store, telegram_user_id=1, text="做完了", calendar_client=calendar_client
    )

    assert "完成" in reply
    assert fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)["status"] == "completed"


def test_start_mood_journal_asks_category_and_sets_state(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: datetime(2026, 8, 2, 9, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()

    reply = commands.start_mood_journal(store, telegram_user_id=1, user_id=42)

    assert "請幫我選一個" in reply
    assert "6. 高興/興奮" in reply
    assert store.get(1) == {
        "flow": "pending_mood_category",
        "target_user_id": 42,
        "entry_date": date(2026, 8, 2),
        "journal_id": None,
    }


def test_handle_mood_category_step_valid_index_moves_to_content_step(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_mood_category", "target_user_id": 42, "entry_date": date(2026, 8, 2), "journal_id": None})

    reply = commands.handle_mood_category_step(store, telegram_user_id=1, text="6")

    assert reply == "給我完整的日記內容："
    assert store.get(1) == {
        "flow": "pending_mood_content",
        "target_user_id": 42,
        "entry_date": date(2026, 8, 2),
        "journal_id": None,
        "mood_category": "happy_excited",
    }


def test_handle_mood_category_step_invalid_reprompts(fake_db):
    store = ConversationStateStore()
    original_state = {"flow": "pending_mood_category", "target_user_id": 42, "entry_date": date(2026, 8, 2), "journal_id": None}
    store.set(1, original_state)

    reply = commands.handle_mood_category_step(store, telegram_user_id=1, text="超級開心")

    assert "沒看懂" in reply
    assert store.get(1) == original_state


def test_handle_mood_content_step_creates_journal_and_asks_achievement(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_mood_content",
            "target_user_id": 42,
            "entry_date": date(2026, 8, 2),
            "journal_id": None,
            "mood_category": "happy_excited",
        },
    )

    reply = commands.handle_mood_content_step(fake_db, store, telegram_user_id=1, text="今天很開心")

    assert "已經紀錄了" in reply
    assert "完成了什麼一句話總結" in reply
    rows = fake_db.select("mood_journals")
    assert len(rows) == 1
    assert rows[0]["content"] == "今天很開心"
    assert rows[0]["achievement_note"] is None
    assert rows[0]["entry_date"] == date(2026, 8, 2)
    state = store.get(1)
    assert state["flow"] == "pending_mood_achievement"
    assert state["target_user_id"] == 42
    assert state["journal_id"] == rows[0]["id"]


def test_handle_mood_content_step_backfill_uses_given_entry_date(fake_db):
    """補記流程：entry_date 是過去日期，寫入時要用這個日期，不是今天。"""
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_mood_content",
            "target_user_id": 42,
            "entry_date": date(2026, 7, 30),
            "journal_id": None,
            "mood_category": "sad_down",
        },
    )

    commands.handle_mood_content_step(fake_db, store, telegram_user_id=1, text="補記昨天的心情")

    rows = fake_db.select("mood_journals")
    assert rows[0]["entry_date"] == date(2026, 7, 30)


def test_handle_mood_content_step_edit_mode_updates_existing_row(fake_db):
    """journal_id 非 None 代表編輯既有紀錄，要 UPDATE 而不是新增一筆。"""
    journal_id = commands.mood.create_mood_journal(fake_db, 42, "sad_down", "原本內容", date(2026, 8, 1))
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_mood_content",
            "target_user_id": 42,
            "entry_date": date(2026, 8, 1),
            "journal_id": journal_id,
            "mood_category": "happy_excited",
        },
    )

    commands.handle_mood_content_step(fake_db, store, telegram_user_id=1, text="改過的內容")

    rows = fake_db.select("mood_journals")
    assert len(rows) == 1  # 沒有多新增一筆
    assert rows[0]["id"] == journal_id
    assert rows[0]["content"] == "改過的內容"
    assert rows[0]["mood_category"] == "happy_excited"
    assert store.get(1)["journal_id"] == journal_id


def test_handle_mood_content_step_masks_pii_and_adds_reminder(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_mood_content",
            "target_user_id": 42,
            "entry_date": date(2026, 8, 2),
            "journal_id": None,
            "mood_category": "sad_down",
        },
    )

    reply = commands.handle_mood_content_step(fake_db, store, telegram_user_id=1, text="我的手機是 0912345678")

    assert "提醒" in reply
    rows = fake_db.select("mood_journals")
    assert rows[0]["content"] == "我的手機是 [已遮蔽個資]"


def test_handle_mood_achievement_step_skips_on_exit_phrase(fake_db):
    journal_id = fake_db.insert(
        "mood_journals",
        {
            "user_id": 42,
            "mood_category": "happy_excited",
            "content": "今天很開心",
            "achievement_note": None,
            "entry_date": date(2026, 8, 2),
        },
    )
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_mood_achievement", "target_user_id": 42, "journal_id": journal_id})

    reply = commands.handle_mood_achievement_step(fake_db, store, telegram_user_id=1, text="結束")

    assert reply == "好的，那先這樣吧！"
    assert store.get(1) is None
    row = fake_db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True)
    assert row["achievement_note"] is None


def test_handle_mood_achievement_step_saves_answer(fake_db):
    journal_id = fake_db.insert(
        "mood_journals",
        {
            "user_id": 42,
            "mood_category": "happy_excited",
            "content": "今天很開心",
            "achievement_note": None,
            "entry_date": date(2026, 8, 2),
        },
    )
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_mood_achievement", "target_user_id": 42, "journal_id": journal_id})

    reply = commands.handle_mood_achievement_step(fake_db, store, telegram_user_id=1, text="完成了一份報告")

    assert reply == "已經幫你記錄好了！"
    assert store.get(1) is None
    row = fake_db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True)
    assert row["achievement_note"] == "完成了一份報告"


# --- 心情小記補記（2026-08-02 追加，FR-49 補記擴充）---


def test_start_mood_backfill_asks_which_day():
    store = ConversationStateStore()

    reply = commands.start_mood_backfill(store, telegram_user_id=1, user_id=42)

    assert "哪一天" in reply
    assert store.get(1) == {"flow": "pending_mood_backfill_date", "target_user_id": 42}


def test_handle_mood_backfill_date_step_clear_moves_to_category_step(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: datetime(2026, 8, 2, 9, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_mood_backfill_date", "target_user_id": 42})
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nDATE: 2026-08-01")

    reply = commands.handle_mood_backfill_date_step(llm_client, store, telegram_user_id=1, text="昨天")

    assert "請幫我選一個" in reply
    assert store.get(1) == {
        "flow": "pending_mood_category",
        "target_user_id": 42,
        "entry_date": date(2026, 8, 1),
        "journal_id": None,
    }


def test_handle_mood_backfill_date_step_unclear_stays(fake_db):
    store = ConversationStateStore()
    original_state = {"flow": "pending_mood_backfill_date", "target_user_id": 42}
    store.set(1, original_state)
    llm_client = _FakeLLMClient(response_text="STATUS: UNCLEAR")

    reply = commands.handle_mood_backfill_date_step(llm_client, store, telegram_user_id=1, text="之前")

    assert "不太確定" in reply
    assert store.get(1) == original_state


def test_handle_mood_backfill_date_step_unparseable_date_stays(fake_db):
    store = ConversationStateStore()
    original_state = {"flow": "pending_mood_backfill_date", "target_user_id": 42}
    store.set(1, original_state)
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nDATE: 不是日期")

    reply = commands.handle_mood_backfill_date_step(llm_client, store, telegram_user_id=1, text="怪怪的回覆")

    assert "不太確定" in reply
    assert store.get(1) == original_state


def test_handle_mood_backfill_date_step_stays_when_date_missing_entirely(fake_db):
    """防禦性處理：LLM 聲稱 CLEAR 卻沒有輸出 DATE 欄位（理論上不該發生），一樣視為 UNCLEAR。"""
    store = ConversationStateStore()
    original_state = {"flow": "pending_mood_backfill_date", "target_user_id": 42}
    store.set(1, original_state)
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR")

    reply = commands.handle_mood_backfill_date_step(llm_client, store, telegram_user_id=1, text="怪怪的回覆")

    assert "不太確定" in reply
    assert store.get(1) == original_state


def test_handle_mood_backfill_date_step_rejects_future_date(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: datetime(2026, 8, 2, 9, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    original_state = {"flow": "pending_mood_backfill_date", "target_user_id": 42}
    store.set(1, original_state)
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nDATE: 2026-08-05")

    reply = commands.handle_mood_backfill_date_step(llm_client, store, telegram_user_id=1, text="這週五")

    assert "未來" in reply
    assert store.get(1) == original_state


# --- 心情小記查詢/更新/刪除（2026-08-02 追加，FR-49 更新/刪除擴充）---


def test_start_mood_list_shows_entries_and_sets_state(fake_db):
    journal_id = commands.mood.create_mood_journal(fake_db, 42, "happy_excited", "今天很開心", date(2026, 8, 2))
    store = ConversationStateStore()

    reply = commands.start_mood_list(fake_db, store, telegram_user_id=1, user_id=42)

    assert "2026/08/02" in reply
    assert "更新或刪除" in reply
    assert store.get(1) == {"flow": "pending_mood_list_action", "target_user_id": 42, "journal_ids": [journal_id]}


def test_start_mood_list_empty_does_not_set_state(fake_db):
    store = ConversationStateStore()

    reply = commands.start_mood_list(fake_db, store, telegram_user_id=1, user_id=42)

    assert reply == "目前還沒有心情小記紀錄喔！"
    assert store.get(1) is None


def test_handle_mood_list_action_step_exit_phrase_clears_state(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_mood_list_action", "target_user_id": 42, "journal_ids": [1]})

    reply = commands.handle_mood_list_action_step(store, telegram_user_id=1, text="結束")

    assert "結束" in reply
    assert store.get(1) is None


def test_handle_mood_list_action_step_invalid_number_reprompts(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_mood_list_action", "target_user_id": 42, "journal_ids": [1, 2]})

    reply = commands.handle_mood_list_action_step(store, telegram_user_id=1, text="9")

    assert "1～2" in reply
    assert store.get(1)["flow"] == "pending_mood_list_action"


def test_handle_mood_list_action_step_valid_number_asks_update_or_delete(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_mood_list_action", "target_user_id": 42, "journal_ids": [11, 22]})

    reply = commands.handle_mood_list_action_step(store, telegram_user_id=1, text="2")

    assert "更新" in reply and "刪除" in reply
    assert store.get(1) == {"flow": "pending_mood_action_choice", "target_user_id": 42, "journal_id": 22}


def test_handle_mood_action_choice_step_update_reuses_entry_date(fake_db):
    journal_id = commands.mood.create_mood_journal(fake_db, 42, "sad_down", "原本內容", date(2026, 7, 20))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_mood_action_choice", "target_user_id": 42, "journal_id": journal_id})
    llm_client = _FakeLLMClient(response_text="UPDATE")

    reply = commands.handle_mood_action_choice_step(fake_db, llm_client, store, telegram_user_id=1, text="我要改內容")

    assert "重新選一次心情分類" in reply
    assert store.get(1) == {
        "flow": "pending_mood_category",
        "target_user_id": 42,
        "entry_date": date(2026, 7, 20),
        "journal_id": journal_id,
    }


def test_handle_mood_action_choice_step_update_falls_back_to_created_at_when_entry_date_missing(fake_db):
    journal_id = fake_db.insert(
        "mood_journals",
        {
            "user_id": 42,
            "mood_category": "neutral",
            "content": "舊資料",
            "achievement_note": None,
            "entry_date": None,
            "created_at": datetime(2026, 7, 1, 3, 0, tzinfo=timezone.utc),  # 台灣時區 7/1 11:00
        },
    )
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_mood_action_choice", "target_user_id": 42, "journal_id": journal_id})
    llm_client = _FakeLLMClient(response_text="UPDATE")

    commands.handle_mood_action_choice_step(fake_db, llm_client, store, telegram_user_id=1, text="我要改內容")

    assert store.get(1)["entry_date"] == date(2026, 7, 1)


def test_handle_mood_action_choice_step_delete_asks_confirm(fake_db):
    journal_id = commands.mood.create_mood_journal(fake_db, 42, "sad_down", "要刪除的內容", date(2026, 8, 1))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_mood_action_choice", "target_user_id": 42, "journal_id": journal_id})
    llm_client = _FakeLLMClient(response_text="DELETE")

    reply = commands.handle_mood_action_choice_step(fake_db, llm_client, store, telegram_user_id=1, text="刪掉")

    assert "沒辦法復原" in reply
    assert store.get(1) == {"flow": "pending_mood_delete_confirm", "target_user_id": 42, "journal_id": journal_id}


def test_handle_mood_action_choice_step_other_clears_state(fake_db):
    journal_id = commands.mood.create_mood_journal(fake_db, 42, "sad_down", "內容", date(2026, 8, 1))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_mood_action_choice", "target_user_id": 42, "journal_id": journal_id})
    llm_client = _FakeLLMClient(response_text="OTHER")

    reply = commands.handle_mood_action_choice_step(fake_db, llm_client, store, telegram_user_id=1, text="呃我不確定")

    assert "不太確定" in reply
    assert store.get(1) is None


def test_handle_mood_delete_confirm_step_confirm_deletes_row(fake_db):
    journal_id = commands.mood.create_mood_journal(fake_db, 42, "sad_down", "要刪除的內容", date(2026, 8, 1))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_mood_delete_confirm", "target_user_id": 42, "journal_id": journal_id})
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_mood_delete_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="對，刪掉")

    assert "已經刪除" in reply
    assert store.get(1) is None
    assert fake_db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True) is None


def test_handle_mood_delete_confirm_step_cancel_keeps_row(fake_db):
    journal_id = commands.mood.create_mood_journal(fake_db, 42, "sad_down", "保留的內容", date(2026, 8, 1))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_mood_delete_confirm", "target_user_id": 42, "journal_id": journal_id})
    llm_client = _FakeLLMClient(response_text="CANCEL")

    reply = commands.handle_mood_delete_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="不要好了")

    assert "保留" in reply
    assert store.get(1) is None
    assert fake_db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True) is not None


def test_start_complaint_asks_fixed_text_without_llm(fake_db):
    store = ConversationStateStore()

    reply = commands.start_complaint(store, telegram_user_id=1, user_id=42)

    assert reply == "請問你覺得哪個地方需要改進呢？"
    assert store.get(1) == {"flow": "pending_complaint_content", "target_user_id": 42}


def test_handle_complaint_content_step_records_and_notifies_robin(fake_db):
    fake_db.insert("users", {"telegram_user_id": 999, "role": "Robin", "is_owner": True})
    fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False}, )
    target_user_id = fake_db.select("users", where="telegram_user_id = %s", params=(1,), fetch_one=True)["id"]
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_complaint_content", "target_user_id": target_user_id})
    llm_client = _FakeLLMClient(response_text="1. 可能的問題點：xxx\n2. 修正/優化建議：yyy")
    telegram_client = _FakeTelegramClient()

    reply = commands.handle_complaint_content_step(fake_db, llm_client, telegram_client, store, telegram_user_id=1, text="客服態度不好")

    assert "已經收到你的意見了" in reply
    assert store.get(1) is None
    rows = fake_db.select("complaints")
    assert len(rows) == 1
    assert rows[0]["content"] == "客服態度不好"
    assert len(telegram_client.sent) == 1
    notified_chat_id, notified_text = telegram_client.sent[0]
    assert notified_chat_id == 999
    assert "客服態度不好" in notified_text
    assert "可能的問題點" in notified_text


def test_handle_complaint_content_step_masks_pii_and_adds_reminder(fake_db):
    fake_db.insert("users", {"telegram_user_id": 999, "role": "Robin", "is_owner": True})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_complaint_content", "target_user_id": 42})
    llm_client = _FakeLLMClient(response_text="分析內容")
    telegram_client = _FakeTelegramClient()

    reply = commands.handle_complaint_content_step(
        fake_db, llm_client, telegram_client, store, telegram_user_id=1, text="我的手機是 0912345678"
    )

    assert "提醒" in reply
    rows = fake_db.select("complaints")
    assert rows[0]["content"] == "我的手機是 [已遮蔽個資]"


def test_handle_complaint_content_step_still_records_when_robin_not_found(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_complaint_content", "target_user_id": 42})
    llm_client = _FakeLLMClient(response_text="分析內容")
    telegram_client = _FakeTelegramClient()

    reply = commands.handle_complaint_content_step(fake_db, llm_client, telegram_client, store, telegram_user_id=1, text="客服態度不好")

    assert "已經收到你的意見了" in reply
    assert len(fake_db.select("complaints")) == 1
    assert telegram_client.sent == []


def test_handle_complaint_content_step_still_records_when_notify_fails(fake_db):
    fake_db.insert("users", {"telegram_user_id": 999, "role": "Robin", "is_owner": True})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_complaint_content", "target_user_id": 42})
    llm_client = _FakeLLMClient(response_text="分析內容")
    telegram_client = _FakeTelegramClient(fail_for_chat_ids={999})

    reply = commands.handle_complaint_content_step(fake_db, llm_client, telegram_client, store, telegram_user_id=1, text="客服態度不好")

    assert "已經收到你的意見了" in reply
    assert len(fake_db.select("complaints")) == 1


def test_handle_mood_achievement_step_masks_pii_and_adds_reminder(fake_db):
    journal_id = fake_db.insert(
        "mood_journals",
        {"user_id": 42, "mood_category": "happy_excited", "content": "今天很開心", "achievement_note": None},
    )
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_mood_achievement", "target_user_id": 42, "journal_id": journal_id})

    reply = commands.handle_mood_achievement_step(fake_db, store, telegram_user_id=1, text="打給我 0912345678")

    assert "提醒" in reply
    row = fake_db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True)
    assert row["achievement_note"] == "打給我 [已遮蔽個資]"


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


# --- 記帳（2026-08-04，Step 2.1，見 robinson SPEC.md FR-41～FR-44）---


def test_start_finance_budget_asks_scope():
    store = ConversationStateStore()

    reply = commands.start_finance_budget(store, telegram_user_id=1, user_id=42)

    assert "全部月份" in reply
    assert store.get(1) == {"flow": "pending_finance_budget_scope", "target_user_id": 42}


# --- FR-41a：選「全部月份」，沒有舊值時直接問金額 ---


def test_handle_finance_budget_scope_step_global_without_existing_asks_amount(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_finance_budget_scope", "target_user_id": user_id})

    reply = commands.handle_finance_budget_scope_step(fake_db, store, telegram_user_id=1, text="1")

    assert "每月支出預算上限" in reply
    assert store.get(1) == {
        "flow": "pending_finance_budget_amount", "target_user_id": user_id, "scope": "global",
    }


def test_handle_finance_budget_scope_step_unrecognized_reprompts(fake_db):
    store = ConversationStateStore()
    original_state = {"flow": "pending_finance_budget_scope", "target_user_id": 42}
    store.set(1, original_state)

    reply = commands.handle_finance_budget_scope_step(fake_db, store, telegram_user_id=1, text="不知道")

    assert "沒看懂" in reply
    assert store.get(1) == original_state


def test_handle_finance_budget_scope_step_global_with_existing_asks_confirm(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    commands.finance.set_monthly_budget(fake_db, user_id, 43000)
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_finance_budget_scope", "target_user_id": user_id})

    reply = commands.handle_finance_budget_scope_step(fake_db, store, telegram_user_id=1, text="全部月份")

    assert "43000 元" in reply
    assert store.get(1) == {
        "flow": "pending_finance_budget_global_confirm", "target_user_id": user_id,
    }


def test_handle_finance_budget_global_confirm_step_confirm_asks_amount(fake_db):
    user_id = 42
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_finance_budget_global_confirm", "target_user_id": user_id})
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_finance_budget_global_confirm_step(llm_client, store, telegram_user_id=1, text="好")

    assert "多少" in reply
    assert store.get(1) == {
        "flow": "pending_finance_budget_amount", "target_user_id": user_id, "scope": "global",
    }


def test_handle_finance_budget_global_confirm_step_cancel_clears_state(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_finance_budget_global_confirm", "target_user_id": 42})
    llm_client = _FakeLLMClient(response_text="CANCEL")

    reply = commands.handle_finance_budget_global_confirm_step(llm_client, store, telegram_user_id=1, text="不用了")

    assert "維持原本" in reply
    assert store.get(1) is None


# --- FR-41a：選「只套用某幾個月」---


def test_handle_finance_budget_scope_step_months_asks_which_months(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_finance_budget_scope", "target_user_id": user_id})

    reply = commands.handle_finance_budget_scope_step(fake_db, store, telegram_user_id=1, text="2")

    assert "幾月" in reply
    assert store.get(1) == {"flow": "pending_finance_budget_months", "target_user_id": user_id}


def test_handle_finance_budget_months_step_without_conflict_asks_amount(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: datetime(2026, 8, 4, 9, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_finance_budget_months", "target_user_id": 42})

    reply = commands.handle_finance_budget_months_step(fake_db, store, telegram_user_id=1, text="8,9")

    assert "多少金額" in reply
    assert store.get(1) == {
        "flow": "pending_finance_budget_amount", "target_user_id": 42,
        "scope": "months", "months": [8, 9], "year": 2026,
    }


def test_handle_finance_budget_months_step_unrecognized_reprompts(fake_db):
    store = ConversationStateStore()
    original_state = {"flow": "pending_finance_budget_months", "target_user_id": 42}
    store.set(1, original_state)

    reply = commands.handle_finance_budget_months_step(fake_db, store, telegram_user_id=1, text="不知道")

    assert "沒看懂月份" in reply
    assert store.get(1) == original_state


def test_handle_finance_budget_months_step_with_conflict_asks_confirm(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: datetime(2026, 8, 4, 9, 0, tzinfo=commands._TAIWAN_TZ))
    commands.finance.set_budget_override(fake_db, 42, 2026, 8, 43000)
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_finance_budget_months", "target_user_id": 42})

    reply = commands.handle_finance_budget_months_step(fake_db, store, telegram_user_id=1, text="8,9")

    assert "8月：43000 元" in reply
    assert store.get(1) == {
        "flow": "pending_finance_budget_override_confirm", "target_user_id": 42,
        "months": [8, 9], "year": 2026,
    }


def test_handle_finance_budget_override_confirm_step_confirm_asks_amount(fake_db):
    store = ConversationStateStore()
    store.set(1, {
        "flow": "pending_finance_budget_override_confirm", "target_user_id": 42,
        "months": [8, 9], "year": 2026,
    })
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_finance_budget_override_confirm_step(llm_client, store, telegram_user_id=1, text="好")

    assert "多少金額" in reply
    assert store.get(1) == {
        "flow": "pending_finance_budget_amount", "target_user_id": 42,
        "scope": "months", "months": [8, 9], "year": 2026,
    }


def test_handle_finance_budget_override_confirm_step_cancel_clears_state(fake_db):
    store = ConversationStateStore()
    store.set(1, {
        "flow": "pending_finance_budget_override_confirm", "target_user_id": 42,
        "months": [8, 9], "year": 2026,
    })
    llm_client = _FakeLLMClient(response_text="CANCEL")

    reply = commands.handle_finance_budget_override_confirm_step(llm_client, store, telegram_user_id=1, text="算了")

    assert "維持原本" in reply
    assert store.get(1) is None


# --- FR-41a：最後一步，輸入金額並寫入 ---


def test_handle_finance_budget_amount_step_global_sets_default_budget(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_finance_budget_amount", "target_user_id": user_id, "scope": "global"})

    reply = commands.handle_finance_budget_amount_step(fake_db, store, telegram_user_id=1, text="15000")

    assert "15000 元" in reply
    assert store.get(1) is None
    assert commands.finance.get_monthly_budget(fake_db, user_id) == 15000.0


def test_handle_finance_budget_amount_step_accepts_amount_with_symbols(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_finance_budget_amount", "target_user_id": user_id, "scope": "global"})

    commands.handle_finance_budget_amount_step(fake_db, store, telegram_user_id=1, text="NT$15,000元")

    assert commands.finance.get_monthly_budget(fake_db, user_id) == 15000.0


def test_handle_finance_budget_amount_step_invalid_amount_reprompts(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    original_state = {"flow": "pending_finance_budget_amount", "target_user_id": user_id, "scope": "global"}
    store.set(1, original_state)

    reply = commands.handle_finance_budget_amount_step(fake_db, store, telegram_user_id=1, text="不知道")

    assert "沒看懂金額" in reply
    assert store.get(1) == original_state


def test_handle_finance_budget_amount_step_months_sets_override_for_each_month(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {
        "flow": "pending_finance_budget_amount", "target_user_id": user_id,
        "scope": "months", "months": [8, 9], "year": 2026,
    })

    reply = commands.handle_finance_budget_amount_step(fake_db, store, telegram_user_id=1, text="43000")

    assert "8月、9月" in reply
    assert "43000 元" in reply
    assert store.get(1) is None
    assert commands.finance.get_budget_override(fake_db, user_id, 2026, 8) == 43000.0
    assert commands.finance.get_budget_override(fake_db, user_id, 2026, 9) == 43000.0


def test_start_finance_add_asks_type_and_sets_state(monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: commands.datetime(2026, 8, 4, 9, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()

    reply = commands.start_finance_add(store, telegram_user_id=1, user_id=42)

    assert "1. 支出" in reply
    assert store.get(1) == {
        "flow": "pending_transaction_type",
        "target_user_id": 42,
        "transaction_date": date(2026, 8, 4),
        "transaction_id": None,
    }


def test_handle_transaction_type_step_valid_moves_to_category(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {"flow": "pending_transaction_type", "target_user_id": 42, "transaction_date": date(2026, 8, 4), "transaction_id": None},
    )

    reply = commands.handle_transaction_type_step(store, telegram_user_id=1, text="支出")

    assert "1. 餐飲" in reply
    assert store.get(1) == {
        "flow": "pending_transaction_category",
        "target_user_id": 42,
        "transaction_date": date(2026, 8, 4),
        "transaction_id": None,
        "transaction_type": "expense",
    }


def test_handle_transaction_type_step_invalid_reprompts(fake_db):
    store = ConversationStateStore()
    original_state = {
        "flow": "pending_transaction_type", "target_user_id": 42, "transaction_date": date(2026, 8, 4), "transaction_id": None,
    }
    store.set(1, original_state)

    reply = commands.handle_transaction_type_step(store, telegram_user_id=1, text="不知道")

    assert "沒看懂" in reply
    assert store.get(1) == original_state


def test_handle_transaction_category_step_valid_moves_to_amount(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_transaction_category",
            "target_user_id": 42,
            "transaction_date": date(2026, 8, 4),
            "transaction_id": None,
            "transaction_type": "expense",
        },
    )

    reply = commands.handle_transaction_category_step(store, telegram_user_id=1, text="1")

    assert reply == "請問金額是多少呢？（例如：120）"
    state = store.get(1)
    assert state["flow"] == "pending_transaction_amount"
    assert state["category"] == "餐飲"


def test_handle_transaction_category_step_invalid_reprompts(fake_db):
    store = ConversationStateStore()
    original_state = {
        "flow": "pending_transaction_category",
        "target_user_id": 42,
        "transaction_date": date(2026, 8, 4),
        "transaction_id": None,
        "transaction_type": "expense",
    }
    store.set(1, original_state)

    reply = commands.handle_transaction_category_step(store, telegram_user_id=1, text="不知道")

    assert "沒看懂" in reply
    assert store.get(1) == original_state


def test_handle_transaction_amount_step_valid_moves_to_note(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_transaction_amount",
            "target_user_id": 42,
            "transaction_date": date(2026, 8, 4),
            "transaction_id": None,
            "transaction_type": "expense",
            "category": "餐飲",
        },
    )

    reply = commands.handle_transaction_amount_step(store, telegram_user_id=1, text="120")

    assert "備註" in reply
    state = store.get(1)
    assert state["flow"] == "pending_transaction_note"
    assert state["amount"] == 120.0


def test_handle_transaction_amount_step_invalid_reprompts(fake_db):
    store = ConversationStateStore()
    original_state = {
        "flow": "pending_transaction_amount",
        "target_user_id": 42,
        "transaction_date": date(2026, 8, 4),
        "transaction_id": None,
        "transaction_type": "expense",
        "category": "餐飲",
    }
    store.set(1, original_state)

    reply = commands.handle_transaction_amount_step(store, telegram_user_id=1, text="很多")

    assert "沒看懂金額" in reply
    assert store.get(1) == original_state


def test_handle_transaction_note_step_creates_transaction(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_transaction_note",
            "target_user_id": 42,
            "transaction_date": date(2026, 8, 4),
            "transaction_id": None,
            "transaction_type": "expense",
            "category": "餐飲",
            "amount": 120.0,
        },
    )

    reply = commands.handle_transaction_note_step(fake_db, store, telegram_user_id=1, text="午餐")

    assert reply == "已經幫你記錄好了！"
    assert store.get(1) is None
    rows = fake_db.select("transactions")
    assert len(rows) == 1
    assert rows[0]["note"] == "午餐"
    assert rows[0]["transaction_date"] == date(2026, 8, 4)
    assert rows[0]["amount"] == 120.0


def test_handle_transaction_note_step_skips_note_on_exit_phrase(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_transaction_note",
            "target_user_id": 42,
            "transaction_date": date(2026, 8, 4),
            "transaction_id": None,
            "transaction_type": "expense",
            "category": "餐飲",
            "amount": 120.0,
        },
    )

    commands.handle_transaction_note_step(fake_db, store, telegram_user_id=1, text="沒有")

    rows = fake_db.select("transactions")
    assert rows[0]["note"] is None


def test_handle_transaction_note_step_masks_pii_and_adds_reminder(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_transaction_note",
            "target_user_id": 42,
            "transaction_date": date(2026, 8, 4),
            "transaction_id": None,
            "transaction_type": "expense",
            "category": "其他",
            "amount": 100.0,
        },
    )

    reply = commands.handle_transaction_note_step(fake_db, store, telegram_user_id=1, text="我的手機是 0912345678")

    assert "提醒" in reply
    rows = fake_db.select("transactions")
    assert rows[0]["note"] == "我的手機是 [已遮蔽個資]"


def test_handle_transaction_note_step_edit_mode_updates_existing_row(fake_db):
    transaction_id = commands.finance.create_transaction(
        fake_db, 42, "expense", "餐飲", 100.0, "原本備註", date(2026, 8, 1)
    )
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_transaction_note",
            "target_user_id": 42,
            "transaction_date": date(2026, 8, 1),
            "transaction_id": transaction_id,
            "transaction_type": "expense",
            "category": "交通",
            "amount": 50.0,
        },
    )

    commands.handle_transaction_note_step(fake_db, store, telegram_user_id=1, text="改過的備註")

    rows = fake_db.select("transactions")
    assert len(rows) == 1  # 沒有多新增一筆
    assert rows[0]["id"] == transaction_id
    assert rows[0]["category"] == "交通"
    assert rows[0]["amount"] == 50.0
    assert rows[0]["note"] == "改過的備註"
    assert rows[0]["transaction_date"] == date(2026, 8, 1)  # 沿用原本的日期


def test_start_finance_backfill_asks_which_day():
    store = ConversationStateStore()

    reply = commands.start_finance_backfill(store, telegram_user_id=1, user_id=42)

    assert "哪一天" in reply
    assert store.get(1) == {"flow": "pending_transaction_backfill_date", "target_user_id": 42}


def test_handle_transaction_backfill_date_step_clear_moves_to_type_step(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: commands.datetime(2026, 8, 4, 9, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_transaction_backfill_date", "target_user_id": 42})
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nDATE: 2026-08-01")

    reply = commands.handle_transaction_backfill_date_step(llm_client, store, telegram_user_id=1, text="8/1")

    assert "1. 支出" in reply
    assert store.get(1) == {
        "flow": "pending_transaction_type",
        "target_user_id": 42,
        "transaction_date": date(2026, 8, 1),
        "transaction_id": None,
    }


def test_handle_transaction_backfill_date_step_unclear_stays(fake_db):
    store = ConversationStateStore()
    original_state = {"flow": "pending_transaction_backfill_date", "target_user_id": 42}
    store.set(1, original_state)
    llm_client = _FakeLLMClient(response_text="STATUS: UNCLEAR")

    reply = commands.handle_transaction_backfill_date_step(llm_client, store, telegram_user_id=1, text="之前")

    assert "不太確定" in reply
    assert store.get(1) == original_state


def test_handle_transaction_backfill_date_step_unparseable_date_stays(fake_db):
    store = ConversationStateStore()
    original_state = {"flow": "pending_transaction_backfill_date", "target_user_id": 42}
    store.set(1, original_state)
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nDATE: 不是日期")

    reply = commands.handle_transaction_backfill_date_step(llm_client, store, telegram_user_id=1, text="怪怪的回覆")

    assert "不太確定" in reply
    assert store.get(1) == original_state


def test_handle_transaction_backfill_date_step_stays_when_date_missing_entirely(fake_db):
    store = ConversationStateStore()
    original_state = {"flow": "pending_transaction_backfill_date", "target_user_id": 42}
    store.set(1, original_state)
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR")

    reply = commands.handle_transaction_backfill_date_step(llm_client, store, telegram_user_id=1, text="怪怪的回覆")

    assert "不太確定" in reply
    assert store.get(1) == original_state


def test_handle_transaction_backfill_date_step_rejects_future_date(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: commands.datetime(2026, 8, 4, 9, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    original_state = {"flow": "pending_transaction_backfill_date", "target_user_id": 42}
    store.set(1, original_state)
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nDATE: 2026-08-10")

    reply = commands.handle_transaction_backfill_date_step(llm_client, store, telegram_user_id=1, text="這週五")

    assert "未來" in reply
    assert store.get(1) == original_state


def test_start_finance_list_shows_entries_and_sets_state(fake_db):
    transaction_id = commands.finance.create_transaction(fake_db, 42, "expense", "餐飲", 120, None, date(2026, 8, 4))
    store = ConversationStateStore()

    reply = commands.start_finance_list(fake_db, store, telegram_user_id=1, user_id=42)

    assert "2026/08/04" in reply
    assert "更新或刪除" in reply
    assert store.get(1) == {"flow": "pending_transaction_list_action", "target_user_id": 42, "transaction_ids": [transaction_id]}


def test_start_finance_list_empty_does_not_set_state(fake_db):
    store = ConversationStateStore()

    reply = commands.start_finance_list(fake_db, store, telegram_user_id=1, user_id=42)

    assert reply == "目前還沒有記帳紀錄喔！"
    assert store.get(1) is None


def test_handle_transaction_list_action_step_exit_phrase_clears_state(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_transaction_list_action", "target_user_id": 42, "transaction_ids": [1]})

    reply = commands.handle_transaction_list_action_step(store, telegram_user_id=1, text="結束")

    assert "結束" in reply
    assert store.get(1) is None


def test_handle_transaction_list_action_step_invalid_number_reprompts(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_transaction_list_action", "target_user_id": 42, "transaction_ids": [1, 2]})

    reply = commands.handle_transaction_list_action_step(store, telegram_user_id=1, text="9")

    assert "1～2" in reply
    assert store.get(1)["flow"] == "pending_transaction_list_action"


def test_handle_transaction_list_action_step_valid_number_asks_update_or_delete(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_transaction_list_action", "target_user_id": 42, "transaction_ids": [11, 22]})

    reply = commands.handle_transaction_list_action_step(store, telegram_user_id=1, text="2")

    assert "更新" in reply and "刪除" in reply
    assert store.get(1) == {"flow": "pending_transaction_action_choice", "target_user_id": 42, "transaction_id": 22}


def test_handle_transaction_action_choice_step_update_reuses_transaction_date(fake_db):
    transaction_id = commands.finance.create_transaction(fake_db, 42, "expense", "餐飲", 100, None, date(2026, 7, 20))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_transaction_action_choice", "target_user_id": 42, "transaction_id": transaction_id})
    llm_client = _FakeLLMClient(response_text="UPDATE")

    reply = commands.handle_transaction_action_choice_step(fake_db, llm_client, store, telegram_user_id=1, text="我要改內容")

    assert "重新選一次交易類型" in reply
    assert store.get(1) == {
        "flow": "pending_transaction_type",
        "target_user_id": 42,
        "transaction_date": date(2026, 7, 20),
        "transaction_id": transaction_id,
    }


def test_handle_transaction_action_choice_step_delete_asks_confirm(fake_db):
    transaction_id = commands.finance.create_transaction(fake_db, 42, "expense", "餐飲", 100, None, date(2026, 8, 1))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_transaction_action_choice", "target_user_id": 42, "transaction_id": transaction_id})
    llm_client = _FakeLLMClient(response_text="DELETE")

    reply = commands.handle_transaction_action_choice_step(fake_db, llm_client, store, telegram_user_id=1, text="刪掉")

    assert "沒辦法復原" in reply
    assert store.get(1) == {"flow": "pending_transaction_delete_confirm", "target_user_id": 42, "transaction_id": transaction_id}


def test_handle_transaction_action_choice_step_other_clears_state(fake_db):
    transaction_id = commands.finance.create_transaction(fake_db, 42, "expense", "餐飲", 100, None, date(2026, 8, 1))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_transaction_action_choice", "target_user_id": 42, "transaction_id": transaction_id})
    llm_client = _FakeLLMClient(response_text="OTHER")

    reply = commands.handle_transaction_action_choice_step(fake_db, llm_client, store, telegram_user_id=1, text="呃我不確定")

    assert "不太確定" in reply
    assert store.get(1) is None


def test_handle_transaction_delete_confirm_step_confirm_deletes_row(fake_db):
    transaction_id = commands.finance.create_transaction(fake_db, 42, "expense", "餐飲", 100, None, date(2026, 8, 1))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_transaction_delete_confirm", "target_user_id": 42, "transaction_id": transaction_id})
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_transaction_delete_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="對，刪掉")

    assert "已經刪除" in reply
    assert store.get(1) is None
    assert fake_db.select("transactions", where="id = %s", params=(transaction_id,), fetch_one=True) is None


def test_handle_transaction_delete_confirm_step_cancel_keeps_row(fake_db):
    transaction_id = commands.finance.create_transaction(fake_db, 42, "expense", "餐飲", 100, None, date(2026, 8, 1))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_transaction_delete_confirm", "target_user_id": 42, "transaction_id": transaction_id})
    llm_client = _FakeLLMClient(response_text="CANCEL")

    reply = commands.handle_transaction_delete_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="不要好了")

    assert "保留" in reply
    assert store.get(1) is None
    assert fake_db.select("transactions", where="id = %s", params=(transaction_id,), fetch_one=True) is not None


def test_handle_finance_summary_returns_text(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: commands.datetime(2026, 8, 4, 9, 0, tzinfo=commands._TAIWAN_TZ))
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    commands.finance.create_transaction(fake_db, user_id, "expense", "餐飲", 100, None, date(2026, 8, 4))

    reply = commands.handle_finance_summary(fake_db, user_id)

    assert "2026/8 記帳摘要" in reply
    assert "支出總計：100 元" in reply


# --- 設定家人生日（FR-53，Step 2.3）---


def test_start_set_family_birthday_with_no_members_returns_message_without_state(fake_db):
    store = ConversationStateStore()

    reply = commands.start_set_family_birthday(fake_db, store, telegram_user_id=1)

    assert "還沒有任何已綁定的使用者" in reply
    assert store.get(1) is None


def test_start_set_family_birthday_lists_bound_members(fake_db):
    fake_db.insert("users", {"telegram_user_id": 100, "role": "Robin", "is_owner": True, "birthday": None})
    fake_db.insert(
        "users", {"telegram_user_id": 200, "role": "爸爸", "is_owner": False, "birthday": date(1970, 8, 1)}
    )
    store = ConversationStateStore()

    reply = commands.start_set_family_birthday(fake_db, store, telegram_user_id=1)

    assert "1. Robin（尚未設定）" in reply
    assert "2. 爸爸（目前：08/01）" in reply
    assert store.get(1)["flow"] == "pending_family_birthday_select"
    assert len(store.get(1)["candidates"]) == 2


def test_handle_family_birthday_select_step_valid_index_moves_to_date_step(fake_db):
    sister_id = fake_db.insert("users", {"telegram_user_id": 300, "role": "大妹", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_family_birthday_select", "candidates": [sister_id]})

    reply = commands.handle_family_birthday_select_step(fake_db, store, telegram_user_id=1, text="1")

    assert "幾月幾號" in reply
    assert store.get(1) == {"flow": "pending_family_birthday_date", "target_user_id": sister_id}


def test_handle_family_birthday_select_step_invalid_index_reprompts(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_family_birthday_select", "candidates": [42]})

    reply = commands.handle_family_birthday_select_step(fake_db, store, telegram_user_id=1, text="99")

    assert "編號" in reply
    assert store.get(1)["flow"] == "pending_family_birthday_select"


def test_handle_family_birthday_select_step_non_numeric_reprompts(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_family_birthday_select", "candidates": [42]})

    reply = commands.handle_family_birthday_select_step(fake_db, store, telegram_user_id=1, text="不是數字")

    assert "編號" in reply


def test_handle_family_birthday_select_step_exit_phrase_clears_state(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_family_birthday_select", "candidates": [42]})

    reply = commands.handle_family_birthday_select_step(fake_db, store, telegram_user_id=1, text="沒有了")

    assert store.get(1) is None
    assert "結束" in reply


def test_handle_family_birthday_date_step_valid_input_saves_and_clears_state(fake_db):
    sister_id = fake_db.insert("users", {"telegram_user_id": 300, "role": "大妹婿", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_family_birthday_date", "target_user_id": sister_id})

    reply = commands.handle_family_birthday_date_step(fake_db, store, telegram_user_id=1, text="1999-10-06")

    assert "大妹婿" in reply
    assert store.get(1) is None
    row = fake_db.select("users", where="id = %s", params=(sister_id,), fetch_one=True)
    assert row["birthday"] == date(1999, 10, 6)


def test_handle_family_birthday_date_step_month_day_only_uses_placeholder_year(fake_db):
    aunt_id = fake_db.insert("users", {"telegram_user_id": 400, "role": "阿姨", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_family_birthday_date", "target_user_id": aunt_id})

    commands.handle_family_birthday_date_step(fake_db, store, telegram_user_id=1, text="10/6")

    row = fake_db.select("users", where="id = %s", params=(aunt_id,), fetch_one=True)
    assert row["birthday"] == date(1900, 10, 6)


def test_handle_family_birthday_date_step_invalid_input_reprompts_and_keeps_state(fake_db):
    sister_id = fake_db.insert("users", {"telegram_user_id": 300, "role": "小妹婿", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_family_birthday_date", "target_user_id": sister_id})

    reply = commands.handle_family_birthday_date_step(fake_db, store, telegram_user_id=1, text="不知道")

    assert "格式看不懂" in reply
    assert store.get(1) == {"flow": "pending_family_birthday_date", "target_user_id": sister_id}
    row = fake_db.select("users", where="id = %s", params=(sister_id,), fetch_one=True)
    assert row.get("birthday") is None


def test_handle_family_birthday_date_step_exit_phrase_clears_state(fake_db):
    sister_id = fake_db.insert("users", {"telegram_user_id": 300, "role": "弟媳", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_family_birthday_date", "target_user_id": sister_id})

    reply = commands.handle_family_birthday_date_step(fake_db, store, telegram_user_id=1, text="結束")

    assert store.get(1) is None
    assert "結束" in reply
