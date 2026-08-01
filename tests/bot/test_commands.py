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


def test_handle_clean_all_dialog_confirm_step_deletes_when_llm_confirms(fake_db):
    fake_db.insert("conversation_logs", {"user_id": 1, "role": "user", "content": "早安", "deleted_at": None})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_clean_all_dialog_confirm", "target_user_id": 1})
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_clean_all_dialog_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="對啊")

    assert reply == "已經幫你清除所有對話紀錄囉！你的知識庫內容不會受影響。"
    assert store.get(1) is None
    logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(1,))
    assert logs == []
    # prompt 必須把使用者的回覆帶進去，模型才有判斷依據
    assert "對啊" in llm_client.last_prompt


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
