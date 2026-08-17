"""批次3（FR-45a）記帳／收藏清單「🎯 目標」子流程與🎯 目標追蹤主選單的路由整合測試。"""
from datetime import date

from src.bot import goals, menu, router
from src.bot.state import ConversationStateStore

FAMILY_ID = 555


class _FakeLLMClient:
    def __init__(self, response_text="這是聊天核心的回答"):
        self.response_text = response_text
        self.last_prompt = None

    def generate_text(self, prompt):
        self.last_prompt = prompt
        return self.response_text


def test_finance_goal_new_via_text_trigger_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "設定記帳目標")
    assert "記帳目標" in reply
    assert store.get(FAMILY_ID)["flow"] == "pending_module_goal_description"

    parse_llm = _FakeLLMClient(response_text="5000|TWD")
    reply = router.handle_message(fake_db, store, FAMILY_ID, "這個月想存5000", llm_client=parse_llm)
    assert "時間" in reply
    assert store.get(FAMILY_ID)["flow"] == "pending_module_goal_deadline"

    deadline_llm = _FakeLLMClient(response_text="STATUS: NO_DEADLINE")
    reply, keyboard = router.handle_message(fake_db, store, FAMILY_ID, "沒有", llm_client=deadline_llm)
    assert "5000.0" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "finance:goal:confirm_save"
    assert store.get(FAMILY_ID)["flow"] == "pending_module_goal_confirm"

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:goal:confirm_save")
    assert "已經幫你記下" in reply
    assert store.get(FAMILY_ID) is None

    goal = fake_db.select("module_goals", where="user_id = %s", params=(user_id,))[0]
    assert goal["module_key"] == "finance"
    assert goal["target_value"] == 5000.0
    assert goal["target_unit"] == "TWD"


def test_finance_goal_with_deadline_asks_calendar_sync_and_creates_event(fake_db, monkeypatch):
    """2026-08-17 補做（Robin 要求不得漏做）：新增流程且有期限時，要問一次 Calendar 同步，答
    「要」就要在確認送出後實際建立 Google Calendar 事件並存回 `google_calendar_event_id`。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_message(fake_db, store, FAMILY_ID, "設定記帳目標")
    parse_llm = _FakeLLMClient(response_text="5000|TWD")
    router.handle_message(fake_db, store, FAMILY_ID, "這個月想存5000", llm_client=parse_llm)

    deadline_llm = _FakeLLMClient(response_text="STATUS: HAS_DEADLINE\nDATE: 2026-12-31")
    reply = router.handle_message(fake_db, store, FAMILY_ID, "12月底", llm_client=deadline_llm)
    assert "Google 家庭行事曆" in reply
    assert store.get(FAMILY_ID)["flow"] == "pending_module_goal_calendar_sync"

    sync_llm = _FakeLLMClient(response_text="CONFIRM")
    reply, keyboard = router.handle_message(fake_db, store, FAMILY_ID, "要", llm_client=sync_llm)
    assert "將同步到 Google 家庭行事曆" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "finance:goal:confirm_save"

    class _FakeCalendarClient:
        def create_event(self, **kwargs):
            self.kwargs = kwargs
            return "event-finance-1"

    calendar_client = _FakeCalendarClient()
    reply, _keyboard = router.handle_callback_query(
        fake_db, store, FAMILY_ID, "finance:goal:confirm_save", calendar_client=calendar_client
    )
    assert "已經幫你記下" in reply

    goal = fake_db.select("module_goals", where="user_id = %s", params=(user_id,))[0]
    assert goal["sync_to_calendar"] is True
    assert goal["google_calendar_event_id"] == "event-finance-1"


def test_finance_goal_description_llm_none_response_degrades_to_free_text(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_message(fake_db, store, FAMILY_ID, "設定記帳目標")
    parse_llm = _FakeLLMClient(response_text="NONE")
    router.handle_message(fake_db, store, FAMILY_ID, "我想變得更有錢", llm_client=parse_llm)

    state = store.get(FAMILY_ID)
    assert state["target_value"] is None
    assert state["target_unit"] is None


def test_finance_goal_list_edit_delete_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    goal_id = goals.create_goal(fake_db, user_id, "finance", "存5000", 5000.0, "TWD", 0, None)
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:goal:list")
    assert "存5000" in reply
    assert any(f"finance:goal:edit:{goal_id}" in button["callback_data"] for row in keyboard["inline_keyboard"] for button in row)

    router.handle_callback_query(fake_db, store, FAMILY_ID, f"finance:goal:delete:{goal_id}")
    assert store.get(FAMILY_ID)["flow"] == "module_goal_delete_confirm"

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, f"finance:goal:confirm_delete:{goal_id}")
    assert "已經幫你刪除" in reply
    assert goals.get_goal(fake_db, goal_id)["status"] == "cancelled"


def test_collections_goal_new_via_button_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "collections:goal:menu")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "collections:goal:new")
    assert store.get(FAMILY_ID)["flow"] == "pending_module_goal_description"

    parse_llm = _FakeLLMClient(response_text="3|count")
    router.handle_message(fake_db, store, FAMILY_ID, "這個月完成3個收藏", llm_client=parse_llm)
    assert store.get(FAMILY_ID)["flow"] == "pending_module_goal_deadline"

    deadline_llm = _FakeLLMClient(response_text="STATUS: NO_DEADLINE")
    reply, keyboard = router.handle_message(fake_db, store, FAMILY_ID, "沒有", llm_client=deadline_llm)
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "collections:goal:confirm_save"

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "collections:goal:confirm_save")
    assert "已經幫你記下" in reply

    goal = fake_db.select("module_goals", where="user_id = %s", params=(user_id,))[0]
    assert goal["module_key"] == "collections"
    assert goal["target_value"] == 3.0
    assert goal["baseline_value"] == 0


def test_module_goal_confirm_only_accepts_button(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(FAMILY_ID, {"flow": "pending_module_goal_confirm", "module_key": "finance"})

    reply, keyboard = router.handle_message(fake_db, store, FAMILY_ID, "隨便打字")
    assert "按鈕" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "finance:goal:menu"


def test_goal_tracking_menu_navigation(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "menu:goal_tracking")
    assert reply == menu.GOAL_TRACKING_MENU_TEXT
    assert any(
        button["callback_data"] == "goal_tracking:module:finance"
        for row in keyboard["inline_keyboard"] for button in row
    )

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "goal_tracking:module:finance")
    assert reply == "查無資料"

    goal_id = goals.create_goal(fake_db, user_id, "finance", "存5000", 5000.0, "TWD", 0, None)
    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "goal_tracking:module:finance")
    assert any(
        button["callback_data"] == f"goal_tracking:goal:module_goals:{goal_id}"
        for row in keyboard["inline_keyboard"] for button in row
    )

    reply, keyboard = router.handle_callback_query(
        fake_db, store, FAMILY_ID, f"goal_tracking:goal:module_goals:{goal_id}"
    )
    assert "摘要生成中" in reply
    assert keyboard["inline_keyboard"] == [[{"text": "🔙 返回主頁面", "callback_data": "menu:main"}]]

    fake_db.insert(
        "goal_summaries",
        {
            "goal_source": "module_goals", "goal_id": goal_id, "user_id": user_id,
            "summary_text": "加油，你這週存了不少錢！", "generated_on": date(2026, 8, 18),
        },
    )
    reply, _keyboard = router.handle_callback_query(
        fake_db, store, FAMILY_ID, f"goal_tracking:goal:module_goals:{goal_id}"
    )
    assert reply == "加油，你這週存了不少錢！"


def test_goal_tracking_module_hides_expired_goals(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    goals.create_goal(fake_db, user_id, "finance", "過期目標", None, None, None, date(2020, 1, 1))
    store = ConversationStateStore()

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "goal_tracking:module:finance")
    assert reply == "查無資料"
