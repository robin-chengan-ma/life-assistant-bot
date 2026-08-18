"""批次4（FR-9c／FR-9d）「🔍 資料查詢」選單流程測試。

`AppAnalyticsService` 本身的查詢邏輯已在 tests/services/test_app_analytics.py 完整測試，這裡
用 monkeypatch 換掉 `query.AppAnalyticsService`，只驗證 query.py 自己的部分：狀態機（日期→
模組複選→查詢）、逐日含空日格式化、欄位不寫死、隱私數字遮罩，以及多模組分則訊息送出／
沒有 `telegram_client` 時優雅降級成單則訊息。
"""
from datetime import date

from src.bot import menu, query
from src.bot.state import ConversationStateStore

USER_ID = 42


class _FakeLLMClient:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.last_prompt = None

    def generate_text(self, prompt):
        self.last_prompt = prompt
        return self.response_text


class _FakeTelegramClient:
    def __init__(self):
        self.sent = []

    def send_text(self, chat_id, text, parse_mode=None, reply_markup=None):
        self.sent.append((chat_id, text))
        return {}


class _FakeAnalyticsService:
    """只回傳測試需要的固定資料，模組方法簽章比照真正的 AppAnalyticsService。"""

    def __init__(self, db):
        self.db = db

    def todos(self, user, start, end, *, calendar_start, calendar_end):
        return {"items": []}

    def body(self, user, start, end):
        return {
            "weight_records": [
                {
                    "id": 1,
                    "user_id": user.database_id,
                    "entry_date": "2026-08-12",
                    "weight_kg": 65.5,
                    "waist_cm": None,
                    "can_edit": True,
                }
            ],
            "diet_records": [],
            "exercise_records": [],
        }

    def finance(self, user, start, end):
        return {
            "records": [
                {
                    "id": 9,
                    "user_id": user.database_id,
                    "date": "2026-08-10",
                    "type": "expense",
                    "category": "餐飲",
                    "amount": 120,
                    "note": "早餐",
                    "created_at": "2026-08-10T08:00:00+08:00",
                    "can_edit": False,
                }
            ]
        }

    def mood(self, user, start, end):
        return {"items": []}


def _quick_select(state_store, is_owner=False, choice="today"):
    return query.handle_date_quick(state_store, USER_ID, is_owner=is_owner, choice=choice)


def test_visible_query_modules_hides_owner_only_for_non_owner():
    keys = {item["key"] for item in menu.visible_query_modules(is_owner=False)}
    assert keys == {"todos", "body", "finance", "mood"}

    owner_keys = {item["key"] for item in menu.visible_query_modules(is_owner=True)}
    assert owner_keys == {item["key"] for item in menu.QUERY_MODULES}


def test_start_query_menu_sets_pending_date_state():
    store = ConversationStateStore()
    text, keyboard = query.start_query_menu(store, USER_ID)

    assert store.get(USER_ID) == {"flow": "pending_query_date"}
    assert "資料查詢" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "query:date:today"


def test_handle_date_quick_enters_module_selection_with_seven_day_range():
    store = ConversationStateStore()
    text, keyboard = query.handle_date_quick(store, USER_ID, is_owner=False, choice="yesterday")

    state = store.get(USER_ID)
    assert state["flow"] == "pending_query_modules"
    end_date = date.fromisoformat(state["end_date"])
    start_date = end_date - __import__("datetime").timedelta(days=6)
    assert start_date.isoformat() in text
    assert end_date.isoformat() in text
    # 非 Owner 只看得到 4 個一般模組 + 開始查詢／重新選日期／回主選單 = 7 個按鈕列
    assert len(keyboard["inline_keyboard"]) == 4 + 3


def test_handle_date_text_without_llm_client_falls_back():
    store = ConversationStateStore()
    query.start_query_menu(store, USER_ID)

    text, keyboard = query.handle_date_text(store, USER_ID, "8/15", is_owner=False, llm_client=None)

    assert "無法使用" in text
    assert keyboard is None


def test_handle_date_text_unclear_reprompts_without_changing_state():
    store = ConversationStateStore()
    query.start_query_menu(store, USER_ID)
    llm = _FakeLLMClient("STATUS: UNCLEAR")

    text, keyboard = query.handle_date_text(store, USER_ID, "改天好了", is_owner=False, llm_client=llm)

    assert "不太確定" in text
    assert keyboard is None
    assert store.get(USER_ID)["flow"] == "pending_query_date"


def test_handle_date_text_clear_accepts_future_date():
    """FR-9c：最終日期可位於未來，不因為是未來就判定 UNCLEAR。"""
    store = ConversationStateStore()
    query.start_query_menu(store, USER_ID)
    llm = _FakeLLMClient("STATUS: CLEAR\nDATE: 2099-01-10")

    text, keyboard = query.handle_date_text(store, USER_ID, "2099/1/10", is_owner=False, llm_client=llm)

    state = store.get(USER_ID)
    assert state["flow"] == "pending_query_modules"
    assert state["end_date"] == "2099-01-10"
    assert "2099-01-10" in text
    assert keyboard is not None


def test_handle_module_toggle_adds_then_removes():
    store = ConversationStateStore()
    _quick_select(store)

    _text, keyboard = query.handle_module_toggle(store, USER_ID, is_owner=False, module_key="finance")
    assert store.get(USER_ID)["selected"] == ["finance"]
    assert "✅ 記帳" in [
        button["text"] for row in keyboard["inline_keyboard"] for button in row
    ]

    _text, keyboard = query.handle_module_toggle(store, USER_ID, is_owner=False, module_key="finance")
    assert store.get(USER_ID)["selected"] == []


def test_handle_module_toggle_rejects_owner_only_module_for_non_owner():
    store = ConversationStateStore()
    _quick_select(store, is_owner=False)

    query.handle_module_toggle(store, USER_ID, is_owner=False, module_key="jobs")

    assert store.get(USER_ID)["selected"] == []


def test_handle_run_without_any_module_selected_prompts_and_keeps_state():
    store = ConversationStateStore()
    _quick_select(store)

    text, _keyboard = query.handle_run({}, store, USER_ID, {"id": 1, "is_owner": False})

    assert "至少勾選一個模組" in text
    assert store.get(USER_ID)["flow"] == "pending_query_modules"


def test_handle_run_lists_every_day_in_range_including_missing_days(monkeypatch):
    """2026-08-18 與 Robin 確認的兩點：逐日含空日、欄位不寫死照實際資料顯示。"""
    monkeypatch.setattr(query, "AppAnalyticsService", _FakeAnalyticsService)
    store = ConversationStateStore()
    query.handle_date_quick(store, USER_ID, is_owner=False, choice="today")
    state = store.get(USER_ID)
    state["end_date"] = "2026-08-15"
    store.set(USER_ID, state)
    query.handle_module_toggle(store, USER_ID, is_owner=False, module_key="body")

    text, keyboard = query.handle_run({}, store, USER_ID, {"id": 7, "is_owner": False})

    # end_date=8/15 往前推 6 天 = 8/9～8/15 共 7 天，只有 8/12 有資料，其餘 6 天都要出現「查無紀錄」。
    for day in ("8/9", "8/10", "8/11", "8/13", "8/14", "8/15"):
        assert f"{day}：\n　　查無紀錄" in text
    assert "8/12：" in text
    assert "體重(公斤)：65.5" in text
    # waist_cm 是 None，依「格式不寫死」原則直接跳過，不會印出空白的「腰圍」欄位。
    assert "腰圍" not in text
    assert store.get(USER_ID) is None
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "menu:query"


def test_handle_run_masks_numeric_fields_when_privacy_enabled(monkeypatch):
    monkeypatch.setattr(query, "AppAnalyticsService", _FakeAnalyticsService)
    store = ConversationStateStore()
    query.handle_date_quick(store, USER_ID, is_owner=False, choice="today")
    state = store.get(USER_ID)
    state["end_date"] = "2026-08-15"
    store.set(USER_ID, state)
    query.handle_module_toggle(store, USER_ID, is_owner=False, module_key="body")

    text, _keyboard = query.handle_run(
        {}, store, USER_ID, {"id": 7, "is_owner": False, "privacy_mask_enabled": True}
    )

    assert "體重(公斤)：**.*" in text
    assert "65.5" not in text


def test_handle_run_sends_extra_modules_via_telegram_client_and_returns_last(monkeypatch):
    monkeypatch.setattr(query, "AppAnalyticsService", _FakeAnalyticsService)
    store = ConversationStateStore()
    query.handle_date_quick(store, USER_ID, is_owner=False, choice="today")
    state = store.get(USER_ID)
    state["end_date"] = "2026-08-15"
    state["selected"] = ["body", "finance"]
    store.set(USER_ID, state)
    telegram_client = _FakeTelegramClient()

    text, _keyboard = query.handle_run(
        {}, store, USER_ID, {"id": 7, "is_owner": False}, telegram_client=telegram_client
    )

    assert len(telegram_client.sent) == 1
    assert "體態分析" in telegram_client.sent[0][1]
    assert "記帳" in text


def test_handle_run_without_telegram_client_merges_into_one_message(monkeypatch):
    monkeypatch.setattr(query, "AppAnalyticsService", _FakeAnalyticsService)
    store = ConversationStateStore()
    query.handle_date_quick(store, USER_ID, is_owner=False, choice="today")
    state = store.get(USER_ID)
    state["end_date"] = "2026-08-15"
    state["selected"] = ["body", "finance"]
    store.set(USER_ID, state)

    text, _keyboard = query.handle_run({}, store, USER_ID, {"id": 7, "is_owner": False})

    assert "體態分析" in text
    assert "記帳" in text


def test_router_end_to_end_menu_to_run(fake_db, monkeypatch):
    """透過 router.py 完整走一次：主選單 → 資料查詢 → 今天 → 勾選記帳 → 開始查詢。"""
    from src.bot import query as query_module
    from src.bot import router

    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    monkeypatch.setattr(query_module, "AppAnalyticsService", _FakeAnalyticsService)
    telegram_user_id = 777
    fake_db.insert("users", {"telegram_user_id": telegram_user_id, "role": "媽媽", "is_owner": False})
    store = ConversationStateStore()

    text, _keyboard = router.handle_callback_query(fake_db, store, telegram_user_id, "menu:query")
    assert "資料查詢" in text
    assert store.get(telegram_user_id)["flow"] == "pending_query_date"

    text, _keyboard = router.handle_callback_query(fake_db, store, telegram_user_id, "query:date:today")
    assert store.get(telegram_user_id)["flow"] == "pending_query_modules"

    text, _keyboard = router.handle_callback_query(fake_db, store, telegram_user_id, "query:module:finance")
    assert store.get(telegram_user_id)["selected"] == ["finance"]

    text, _keyboard = router.handle_callback_query(fake_db, store, telegram_user_id, "query:run")
    assert "記帳" in text
    assert store.get(telegram_user_id) is None
