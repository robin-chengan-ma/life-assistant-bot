from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from src.bot import commands, menu, templates, toggles
from src.bot.state import ConversationStateStore


class _FakeLLMClient:
    """模擬 submodules.llm.client.LLMClient 的 generate_text。"""

    def __init__(self, response_text="人格化後的功能總覽"):
        self.response_text = response_text
        self.last_prompt = None

    def generate_text(self, prompt):
        self.last_prompt = prompt
        return self.response_text


class _FakeTelegramClient:
    def __init__(self, fail_for_chat_ids=()):
        self.sent = []
        self._fail_for_chat_ids = set(fail_for_chat_ids)

    def send_text(self, chat_id, text):
        if chat_id in self._fail_for_chat_ids:
            raise RuntimeError("Telegram API 掛了")
        self.sent.append((chat_id, text))


def test_handle_rule_returns_appendix_a_text():
    assert commands.handle_rule() == templates.APPENDIX_A_TEXT


def test_start_permission_menu_returns_fixed_keyboard():
    text, keyboard = commands.start_permission_menu()
    assert "請選擇" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "permission:create"


def test_handle_permission_callback_create_sets_awaiting_family_title_state():
    store = ConversationStateStore()
    reply, keyboard = commands.handle_permission_callback(None, store, telegram_user_id=1, action="create")
    assert store.get(1) == {"flow": "permission_create", "step": "awaiting_family_title"}
    assert keyboard is None
    assert "稱謂" in reply


def test_handle_permission_callback_disable_lists_candidates(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "爸爸", "is_owner": False, "is_active": True})
    store = ConversationStateStore()

    reply, keyboard = commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="disable")

    assert keyboard is None
    assert "爸爸" in reply
    assert store.get(1)["flow"] == "permission_disable"


def test_handle_permission_callback_disable_with_no_candidates_returns_back_button(fake_db):
    store = ConversationStateStore()

    reply, keyboard = commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="disable")

    assert "沒有" in reply
    assert keyboard == menu.back_to_main_menu_keyboard()
    assert store.get(1) is None


def test_permission_create_full_flow_creates_user_and_invite(fake_db):
    store = ConversationStateStore()
    commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="create")
    commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="爸爸")
    reply = commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="略過")

    users = fake_db.select("users", where="family_title = %s", params=("爸爸",))
    assert len(users) == 1
    assert users[0]["telegram_user_id"] is None
    invite = fake_db.select("invite_codes", where="user_id = %s AND is_used = FALSE", params=(users[0]["id"],), fetch_one=True)
    assert invite is not None
    assert invite["expires_at"] is not None
    assert store.get(1) is None
    assert "已建立" in reply


def test_permission_create_flow_exit_phrase_clears_state(fake_db):
    store = ConversationStateStore()
    commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="create")

    reply = commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="沒有了")

    assert store.get(1) is None
    assert "結束" in reply


def test_permission_disable_flow_with_invalid_index_reprompts(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "爸爸", "is_owner": False, "is_active": True})
    store = ConversationStateStore()
    commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="disable")

    reply = commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="99")

    assert "編號" in reply
    assert store.get(1) is not None


def test_permission_enable_flow_reactivates_user(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "爸爸", "is_owner": False, "is_active": False})
    store = ConversationStateStore()
    commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="enable")

    reply = commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="1")

    updated = fake_db.select("users", where="telegram_user_id = %s", params=(555,), fetch_one=True)
    assert updated["is_active"] is True
    assert "恢復" in reply


def test_permission_resend_flow_generates_new_passcode(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": None, "role": "爸爸", "is_owner": False, "is_active": True})
    fake_db.insert("invite_codes", {"code": "old-code", "is_used": False, "user_id": user_id})
    store = ConversationStateStore()
    commands.handle_permission_callback(fake_db, store, telegram_user_id=1, action="resend")

    reply = commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="1")

    assert "已重發" in reply
    old_invite = fake_db.select("invite_codes", where="code = %s", params=("old-code",), fetch_one=True)
    assert old_invite["is_used"] is True


def test_handle_permission_step_raises_on_unknown_state(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "not_a_real_flow"})

    with pytest.raises(ValueError):
        commands.handle_permission_step(fake_db, store, telegram_user_id=1, text="whatever")


# --- /my_toggles、/set_toggle（docs/specs/feature-toggles/SPEC.md）---


def test_start_my_toggles_ensures_defaults_and_sets_awaiting_index_state(fake_db):
    store = ConversationStateStore()

    reply = commands.start_my_toggles(fake_db, store, telegram_user_id=1, user_id=42)

    assert store.get(1) == {"flow": "toggle", "step": "awaiting_index", "target_user_id": 42}
    assert "1. " in reply
    assert len(fake_db.select("feature_toggles", where="user_id = %s", params=(42,))) == 10


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
    assert len(fake_db.select("feature_toggles", where="user_id = %s", params=(dad_id,))) == 10


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


# --- 選單新增入口（2f，見 commands.py 待辦事項區塊說明） ---


def test_start_todo_menu_returns_submenu_keyboard():
    text, keyboard = commands.start_todo_menu()

    assert "待辦事項" in text
    callback_data = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert callback_data == ["todo:list", "todo:add", "menu:main"]


def test_start_todo_new_asks_content_and_sets_state():
    store = ConversationStateStore()

    reply = commands.start_todo_new(store, telegram_user_id=1, user_id=42)

    assert "要記什麼事" in reply
    assert store.get(1) == {"flow": "pending_todo_new_content", "target_user_id": 42}


def test_handle_todo_new_content_step_moves_to_time_step():
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_new_content", "target_user_id": 42})

    reply = commands.handle_todo_new_content_step(store, telegram_user_id=1, text="買菜")

    assert reply == "好的，請問是什麼時候呢？"
    assert store.get(1) == {"flow": "pending_todo_time", "target_user_id": 42, "original_text": "買菜"}


def test_handle_todo_new_content_step_rejects_blank_content():
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_new_content", "target_user_id": 42})

    reply = commands.handle_todo_new_content_step(store, telegram_user_id=1, text="   ")

    assert "不可以是空白" in reply
    assert store.get(1)["flow"] == "pending_todo_new_content"


# --- pending_todo_calendar_sync → pending_todo_confirm_save（2f，摘要→二次確認）---


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


def test_handle_todo_calendar_sync_step_moves_to_confirm_save_without_writing(fake_db):
    store = ConversationStateStore()
    _set_pending_todo_calendar_sync_state(store)
    llm_client = _FakeLLMClient(response_text="CANCEL")

    reply, keyboard = commands.handle_todo_calendar_sync_step(fake_db, llm_client, store, telegram_user_id=1, text="不用")

    assert "請確認以下待辦事項內容" in reply
    assert "買菜" in reply
    assert "同步 Google 家庭行事曆：不會" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "todo:confirm_save"
    state = store.get(1)
    assert state["flow"] == "pending_todo_confirm_save"
    assert state["sync_to_calendar"] is False
    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(42, "pending"))
    assert len(rows) == 0  # 還沒真正寫入，要等按下「✅ 確認送出」才寫入


def test_handle_todo_calendar_sync_step_records_confirmed_sync_choice(fake_db):
    store = ConversationStateStore()
    _set_pending_todo_calendar_sync_state(store)
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply, _keyboard = commands.handle_todo_calendar_sync_step(fake_db, llm_client, store, telegram_user_id=1, text="要")

    assert "同步 Google 家庭行事曆：會" in reply
    assert store.get(1)["sync_to_calendar"] is True


def test_handle_todo_confirm_save_text_cancels_and_clears_state():
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_todo_confirm_save", "target_user_id": 42, "content": "買菜"})

    reply, keyboard = commands.handle_todo_confirm_save_text(store, telegram_user_id=1)

    assert "先幫你取消了" in reply
    assert keyboard == menu.back_to_main_menu_keyboard()
    assert store.get(1) is None


def test_handle_todo_confirm_save_creates_todo_without_sync(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_todo_confirm_save", "target_user_id": 42, "content": "買菜",
            "due_at": commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ),
            "start_at": None, "remind_before_30min": True, "sync_to_calendar": False,
        },
    )

    reply, keyboard = commands.handle_todo_confirm_save(fake_db, store, telegram_user_id=1)

    assert reply == "好的，已經幫你記錄好了！"
    assert keyboard == menu.back_to_main_menu_keyboard()
    assert store.get(1) is None
    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(42, "pending"))
    assert len(rows) == 1
    assert rows[0]["sync_to_calendar"] is False
    assert rows[0].get("google_calendar_event_id") is None


def test_handle_todo_confirm_save_creates_event_when_synced(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_todo_confirm_save", "target_user_id": 42, "content": "買菜",
            "due_at": commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ),
            "start_at": None, "remind_before_30min": True, "sync_to_calendar": True,
        },
    )
    calendar_client = MagicMock()
    calendar_client.create_event.return_value = "event-abc123"

    reply, _keyboard = commands.handle_todo_confirm_save(fake_db, store, telegram_user_id=1, calendar_client=calendar_client)

    assert reply == "好的，已經幫你記錄好了！"
    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(42, "pending"))
    assert rows[0]["sync_to_calendar"] is True
    assert rows[0]["google_calendar_event_id"] == "event-abc123"
    calendar_client.create_event.assert_called_once()
    call_kwargs = calendar_client.create_event.call_args.kwargs
    assert call_kwargs["summary"] == "買菜"
    assert call_kwargs["start"] == "2026-08-02T15:00:00+08:00"
    assert call_kwargs["end"] == "2026-08-02T15:30:00+08:00"  # 單一時間點預設 30 分鐘時長


def test_handle_todo_confirm_save_uses_range_window_for_interval_todo(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_todo_confirm_save", "target_user_id": 42, "content": "出差",
            "due_at": commands.datetime(2026, 8, 5, 17, 0, tzinfo=commands._TAIWAN_TZ),
            "start_at": commands.datetime(2026, 8, 2, 8, 0, tzinfo=commands._TAIWAN_TZ),
            "remind_before_30min": True, "sync_to_calendar": True,
        },
    )
    calendar_client = MagicMock()
    calendar_client.create_event.return_value = "event-xyz"

    commands.handle_todo_confirm_save(fake_db, store, telegram_user_id=1, calendar_client=calendar_client)

    call_kwargs = calendar_client.create_event.call_args.kwargs
    assert call_kwargs["start"] == "2026-08-02T08:00:00+08:00"
    assert call_kwargs["end"] == "2026-08-05T17:00:00+08:00"


def test_handle_todo_confirm_save_skips_event_creation_when_client_is_none(fake_db):
    # calendar_client 為 None（環境變數未設定）時優雅降級：待辦仍成功記錄，只是不建立 Calendar 事件。
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_todo_confirm_save", "target_user_id": 42, "content": "買菜",
            "due_at": commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ),
            "start_at": None, "remind_before_30min": True, "sync_to_calendar": True,
        },
    )

    reply, _keyboard = commands.handle_todo_confirm_save(fake_db, store, telegram_user_id=1, calendar_client=None)

    assert reply == "好的，已經幫你記錄好了！"
    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(42, "pending"))
    assert rows[0]["sync_to_calendar"] is True
    assert rows[0].get("google_calendar_event_id") is None


def test_handle_todo_confirm_save_swallows_calendar_exception(fake_db):
    # Calendar API 呼叫失敗不該影響待辦事項已經成功記錄。
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_todo_confirm_save", "target_user_id": 42, "content": "買菜",
            "due_at": commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ),
            "start_at": None, "remind_before_30min": True, "sync_to_calendar": True,
        },
    )
    calendar_client = MagicMock()
    calendar_client.create_event.side_effect = RuntimeError("boom")

    reply, _keyboard = commands.handle_todo_confirm_save(fake_db, store, telegram_user_id=1, calendar_client=calendar_client)

    assert reply == "好的，已經幫你記錄好了！"
    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(42, "pending"))
    assert rows[0]["sync_to_calendar"] is True
    assert rows[0].get("google_calendar_event_id") is None


def test_handle_todo_confirm_save_without_pending_state_returns_guard_reply():
    store = ConversationStateStore()

    reply, keyboard = commands.handle_todo_confirm_save(None, store, telegram_user_id=1)

    assert reply == "目前沒有進行中的待辦事項設定。"
    assert keyboard == menu.back_to_main_menu_keyboard()


# --- 查詢清單＋按鈕標記完成/取消（2f，取代舊版編號輸入＋LLM 分類）---


def test_start_todo_list_reports_no_todos(fake_db):
    text, keyboard = commands.start_todo_list(fake_db, user_id=42)

    assert text == "目前沒有待辦事項喔！"
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "menu:todo"


def test_start_todo_list_shows_list_with_complete_and_cancel_buttons(fake_db):
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {"user_id": 42, "content": "買菜", "due_at": due_at, "remind_before_30min": False, "status": "pending"},
    )

    text, keyboard = commands.start_todo_list(fake_db, user_id=42)

    assert "買菜" in text
    buttons = keyboard["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == f"todo:complete:{todo_id}"
    assert buttons[1]["callback_data"] == f"todo:cancel:{todo_id}"
    assert keyboard["inline_keyboard"][-1][0]["callback_data"] == "menu:todo"


def test_handle_todo_status_action_marks_completed(fake_db):
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {"user_id": 42, "content": "買菜", "due_at": due_at, "remind_before_30min": False, "status": "pending"},
    )

    reply, keyboard = commands.handle_todo_status_action(fake_db, user_id=42, todo_id=todo_id, new_status="completed")

    assert "完成" in reply
    assert keyboard == menu.back_to_main_menu_keyboard()
    assert fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)["status"] == "completed"


def test_handle_todo_status_action_marks_cancelled(fake_db):
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {"user_id": 42, "content": "買菜", "due_at": due_at, "remind_before_30min": False, "status": "pending"},
    )

    reply, _keyboard = commands.handle_todo_status_action(fake_db, user_id=42, todo_id=todo_id, new_status="cancelled")

    assert "取消" in reply
    assert fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)["status"] == "cancelled"


def test_handle_todo_status_action_rejects_other_users_todo(fake_db):
    # FR-6c：重新查一次 user_id 比對，不假設清單畫面篩過就安全，避免偽造/過期 callback_data。
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {"user_id": 999, "content": "別人的待辦", "due_at": due_at, "remind_before_30min": False, "status": "pending"},
    )

    reply, keyboard = commands.handle_todo_status_action(fake_db, user_id=42, todo_id=todo_id, new_status="completed")

    assert "找不到" in reply
    assert keyboard == menu.back_to_main_menu_keyboard()
    assert fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)["status"] == "pending"


def test_handle_todo_status_action_deletes_calendar_event_when_synced(fake_db):
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {
            "user_id": 42, "content": "買菜", "due_at": due_at, "remind_before_30min": False,
            "status": "pending", "sync_to_calendar": True, "google_calendar_event_id": "event-abc123",
        },
    )
    calendar_client = MagicMock()

    commands.handle_todo_status_action(fake_db, user_id=42, todo_id=todo_id, new_status="completed", calendar_client=calendar_client)

    calendar_client.delete_event.assert_called_once_with(event_id="event-abc123")


def test_handle_todo_status_action_skips_calendar_delete_when_not_synced(fake_db):
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {"user_id": 42, "content": "買菜", "due_at": due_at, "remind_before_30min": False, "status": "pending"},
    )
    calendar_client = MagicMock()

    commands.handle_todo_status_action(fake_db, user_id=42, todo_id=todo_id, new_status="completed", calendar_client=calendar_client)

    calendar_client.delete_event.assert_not_called()


def test_handle_todo_status_action_swallows_calendar_delete_exception(fake_db):
    due_at = commands.datetime(2026, 8, 2, 15, 0, tzinfo=commands._TAIWAN_TZ)
    todo_id = fake_db.insert(
        "todos",
        {
            "user_id": 42, "content": "買菜", "due_at": due_at, "remind_before_30min": False,
            "status": "pending", "sync_to_calendar": True, "google_calendar_event_id": "event-abc123",
        },
    )
    calendar_client = MagicMock()
    calendar_client.delete_event.side_effect = RuntimeError("boom")

    reply, _keyboard = commands.handle_todo_status_action(fake_db, user_id=42, todo_id=todo_id, new_status="completed", calendar_client=calendar_client)

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


def test_handle_mood_content_step_builds_confirm_summary_without_writing(fake_db):
    """2026-08-16（Phase 6 第二批 2c）：`handle_mood_content_step` 只組摘要、轉進
    `pending_mood_confirm`，不在這一步直接寫入；實際寫入要等 `handle_mood_confirm_save`（見
    `mood:confirm_save` 按鈕，端對端串接見 tests/bot/test_router.py
    test_mood_journal_full_flow_records_entry_and_achievement）。"""
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

    reply, keyboard = commands.handle_mood_content_step(store, telegram_user_id=1, text="今天很開心")

    assert "請確認以下內容" in reply
    assert "今天很開心" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "mood:confirm_save"
    assert fake_db.select("mood_journals") == []
    state = store.get(1)
    assert state["flow"] == "pending_mood_confirm"
    assert state["masked_content"] == "今天很開心"
    assert state["entry_date"] == date(2026, 8, 2)


def test_handle_mood_confirm_save_backfill_uses_given_entry_date(fake_db):
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
    commands.handle_mood_content_step(store, telegram_user_id=1, text="補記昨天的心情")

    commands.handle_mood_confirm_save(fake_db, store, telegram_user_id=1)

    rows = fake_db.select("mood_journals")
    assert rows[0]["entry_date"] == date(2026, 7, 30)


def test_handle_mood_confirm_save_edit_mode_updates_existing_row(fake_db):
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
    commands.handle_mood_content_step(store, telegram_user_id=1, text="改過的內容")

    commands.handle_mood_confirm_save(fake_db, store, telegram_user_id=1)

    rows = fake_db.select("mood_journals")
    assert len(rows) == 1  # 沒有多新增一筆
    assert rows[0]["id"] == journal_id
    assert rows[0]["content"] == "改過的內容"
    assert rows[0]["mood_category"] == "happy_excited"


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

    reply, _keyboard = commands.handle_mood_content_step(store, telegram_user_id=1, text="我的手機是 0912345678")

    assert "提醒" in reply
    assert store.get(1)["masked_content"] == "我的手機是 [已遮蔽個資]"

    commands.handle_mood_confirm_save(fake_db, store, telegram_user_id=1)
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


# 2026-08-16 補述：`start_mood_list`／`handle_mood_list_action_step`／
# `handle_mood_action_choice_step`／`handle_mood_delete_confirm_step` 四個函式已在 Phase 6
# 第二批 2c（commit `8d0ba92`）正式移除，改由按鈕 callback（`mood:list`／`mood:edit:<id>`／
# `mood:delete:<id>`／`mood:confirm_delete:<id>`）取代；原本對應這四個函式的測試一併移除，
# 現行清單/更新/刪除流程的端對端覆蓋見 tests/bot/test_router.py
# test_mood_list_update_and_delete_full_flow()、test_mood_delete_only_owner_can_target_own_journal()。
# 詳見 docs/ADR/debug/robinson.md 2026-08-16「補述」段落。


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

    reply, keyboard = commands.handle_finance_budget_scope_step(fake_db, store, telegram_user_id=1, text="全部月份")

    assert "43000 元" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "finance:budget_confirm_save"
    assert store.get(1) == {
        "flow": "pending_finance_budget_global_confirm", "target_user_id": user_id,
    }


def test_handle_finance_budget_global_confirm_save_asks_amount(fake_db):
    user_id = 42
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_finance_budget_global_confirm", "target_user_id": user_id})

    reply = commands.handle_finance_budget_global_confirm_save(store, telegram_user_id=1)

    assert "多少" in reply
    assert store.get(1) == {
        "flow": "pending_finance_budget_amount", "target_user_id": user_id, "scope": "global",
    }


def test_handle_finance_confirm_text_rejects_budget_global_confirm():
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_finance_budget_global_confirm", "target_user_id": 42})

    reply, keyboard = commands.handle_finance_confirm_text(store, telegram_user_id=1)

    assert "按鈕" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "finance:menu"
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

    reply, keyboard = commands.handle_finance_budget_months_step(fake_db, store, telegram_user_id=1, text="8,9")

    assert "8月：43000 元" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "finance:budget_override_confirm_save"
    assert store.get(1) == {
        "flow": "pending_finance_budget_override_confirm", "target_user_id": 42,
        "months": [8, 9], "year": 2026,
    }


def test_handle_finance_budget_override_confirm_save_asks_amount(fake_db):
    store = ConversationStateStore()
    store.set(1, {
        "flow": "pending_finance_budget_override_confirm", "target_user_id": 42,
        "months": [8, 9], "year": 2026,
    })

    reply = commands.handle_finance_budget_override_confirm_save(store, telegram_user_id=1)

    assert "多少金額" in reply
    assert store.get(1) == {
        "flow": "pending_finance_budget_amount", "target_user_id": 42,
        "scope": "months", "months": [8, 9], "year": 2026,
    }


def test_handle_finance_confirm_text_rejects_budget_override_confirm():
    store = ConversationStateStore()
    store.set(1, {
        "flow": "pending_finance_budget_override_confirm", "target_user_id": 42,
        "months": [8, 9], "year": 2026,
    })

    reply, keyboard = commands.handle_finance_confirm_text(store, telegram_user_id=1)

    assert "按鈕" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "finance:menu"
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


def test_handle_transaction_note_step_asks_confirm_without_writing(fake_db):
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

    reply, keyboard = commands.handle_transaction_note_step(store, telegram_user_id=1, text="午餐")

    assert "請確認以下內容" in reply
    assert "午餐" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "finance:confirm_save"
    assert store.get(1)["flow"] == "pending_transaction_confirm"
    assert store.get(1)["note"] == "午餐"
    assert fake_db.select("transactions") == []  # 確認前不寫入


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

    commands.handle_transaction_note_step(store, telegram_user_id=1, text="沒有")

    assert store.get(1)["note"] is None


def test_handle_transaction_note_step_masks_pii_and_confirm_save_adds_reminder(fake_db):
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

    commands.handle_transaction_note_step(store, telegram_user_id=1, text="我的手機是 0912345678")
    reply, _ = commands.handle_transaction_confirm_save(fake_db, store, telegram_user_id=1)

    assert "提醒" in reply
    rows = fake_db.select("transactions")
    assert rows[0]["note"] == "我的手機是 [已遮蔽個資]"


def test_handle_transaction_confirm_save_creates_transaction(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_transaction_confirm",
            "target_user_id": 42,
            "transaction_date": date(2026, 8, 4),
            "transaction_id": None,
            "transaction_type": "expense",
            "category": "餐飲",
            "amount": 120.0,
            "note": "午餐",
            "pii_detected": False,
        },
    )

    reply, keyboard = commands.handle_transaction_confirm_save(fake_db, store, telegram_user_id=1)

    assert reply.startswith("已經幫你記錄好了！")
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "finance:menu"
    assert store.get(1) is None
    rows = fake_db.select("transactions")
    assert len(rows) == 1
    assert rows[0]["note"] == "午餐"
    assert rows[0]["transaction_date"] == date(2026, 8, 4)
    assert rows[0]["amount"] == 120.0


def test_handle_transaction_confirm_save_edit_mode_updates_existing_row(fake_db):
    transaction_id = commands.finance.create_transaction(
        fake_db, 42, "expense", "餐飲", 100.0, "原本備註", date(2026, 8, 1)
    )
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_transaction_confirm",
            "target_user_id": 42,
            "transaction_date": date(2026, 8, 1),
            "transaction_id": transaction_id,
            "transaction_type": "expense",
            "category": "交通",
            "amount": 50.0,
            "note": "改過的備註",
            "pii_detected": False,
        },
    )

    commands.handle_transaction_confirm_save(fake_db, store, telegram_user_id=1)

    rows = fake_db.select("transactions")
    assert len(rows) == 1  # 沒有多新增一筆
    assert rows[0]["id"] == transaction_id
    assert rows[0]["category"] == "交通"
    assert rows[0]["amount"] == 50.0
    assert rows[0]["note"] == "改過的備註"
    assert rows[0]["transaction_date"] == date(2026, 8, 1)  # 沿用原本的日期


def test_handle_finance_confirm_text_rejects_transaction_confirm():
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_transaction_confirm", "target_user_id": 42})

    reply, keyboard = commands.handle_finance_confirm_text(store, telegram_user_id=1)

    assert "按鈕" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "finance:menu"
    assert store.get(1) is None


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


def test_handle_finance_list_shows_entries_with_edit_delete_buttons(fake_db):
    transaction_id = commands.finance.create_transaction(fake_db, 42, "expense", "餐飲", 120, None, date(2026, 8, 4))

    reply, keyboard = commands.handle_finance_list(fake_db, user_id=42)

    assert "2026/08/04" in reply
    buttons = keyboard["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == f"finance:edit:{transaction_id}"
    assert buttons[1]["callback_data"] == f"finance:delete:{transaction_id}"
    assert keyboard["inline_keyboard"][-1][0]["callback_data"] == "finance:menu"


def test_handle_finance_list_empty_shows_back_button(fake_db):
    reply, keyboard = commands.handle_finance_list(fake_db, user_id=42)

    assert reply == "目前還沒有記帳紀錄喔！"
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "finance:menu"


def test_start_transaction_edit_reuses_transaction_date(fake_db):
    transaction_id = commands.finance.create_transaction(fake_db, 42, "expense", "餐飲", 100, None, date(2026, 7, 20))
    store = ConversationStateStore()

    reply = commands.start_transaction_edit(fake_db, store, telegram_user_id=1, user_id=42, transaction_id=transaction_id)

    assert "重新選一次交易類型" in reply
    assert store.get(1) == {
        "flow": "pending_transaction_type",
        "target_user_id": 42,
        "transaction_date": date(2026, 7, 20),
        "transaction_id": transaction_id,
    }


def test_start_transaction_edit_rejects_other_users_row(fake_db):
    transaction_id = commands.finance.create_transaction(fake_db, 42, "expense", "餐飲", 100, None, date(2026, 7, 20))
    store = ConversationStateStore()

    reply = commands.start_transaction_edit(fake_db, store, telegram_user_id=1, user_id=999, transaction_id=transaction_id)

    assert "找不到" in reply
    assert store.get(1) is None


def test_start_transaction_delete_confirm_asks_confirm(fake_db):
    transaction_id = commands.finance.create_transaction(fake_db, 42, "expense", "餐飲", 100, None, date(2026, 8, 1))
    store = ConversationStateStore()

    reply, keyboard = commands.start_transaction_delete_confirm(fake_db, store, telegram_user_id=1, user_id=42, transaction_id=transaction_id)

    assert "沒辦法復原" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == f"finance:confirm_delete:{transaction_id}"
    assert store.get(1) == {"flow": "finance_transaction_delete_confirm", "transaction_id": transaction_id}


def test_handle_finance_confirm_text_rejects_transaction_delete_confirm():
    store = ConversationStateStore()
    store.set(1, {"flow": "finance_transaction_delete_confirm", "transaction_id": 1})

    reply, keyboard = commands.handle_finance_confirm_text(store, telegram_user_id=1)

    assert "按鈕" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "finance:menu"
    assert store.get(1) is None


def test_handle_transaction_delete_removes_row(fake_db):
    transaction_id = commands.finance.create_transaction(fake_db, 42, "expense", "餐飲", 100, None, date(2026, 8, 1))
    store = ConversationStateStore()
    store.set(1, {"flow": "finance_transaction_delete_confirm", "transaction_id": transaction_id})

    reply = commands.handle_transaction_delete(fake_db, store, telegram_user_id=1, user_id=42, transaction_id=transaction_id)

    assert "已經刪除" in reply
    assert store.get(1) is None
    assert fake_db.select("transactions", where="id = %s", params=(transaction_id,), fetch_one=True) is None


def test_handle_transaction_delete_rejects_other_users_row(fake_db):
    transaction_id = commands.finance.create_transaction(fake_db, 42, "expense", "餐飲", 100, None, date(2026, 8, 1))
    store = ConversationStateStore()

    reply = commands.handle_transaction_delete(fake_db, store, telegram_user_id=1, user_id=999, transaction_id=transaction_id)

    assert "找不到" in reply
    assert fake_db.select("transactions", where="id = %s", params=(transaction_id,), fetch_one=True) is not None


def test_handle_finance_summary_returns_text_with_back_button(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: commands.datetime(2026, 8, 4, 9, 0, tzinfo=commands._TAIWAN_TZ))
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    commands.finance.create_transaction(fake_db, user_id, "expense", "餐飲", 100, None, date(2026, 8, 4))

    reply, keyboard = commands.handle_finance_summary(fake_db, user_id)

    assert "2026/8 記帳摘要" in reply
    assert "支出總計：100 元" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "finance:menu"


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
