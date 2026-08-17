"""src/bot/router.py 體態管理相關選單按鈕與 flow 分派的端對端測試（對應 docs/specs/SPEC.md
FR-45／FR-45a／FR-46，Phase 6 第二批 2h）。透過 `router.handle_callback_query()`／
`handle_message()` 整段串接驗證，跟 tests/bot/test_router.py 運動/飲食模組測試同一套風格。
"""
from datetime import date

from src.bot import commands, router
from src.bot.state import ConversationStateStore

FAMILY_ID = 555


class _FakeLLMClient:
    def __init__(self, response_text="這是聊天核心的回答"):
        self.response_text = response_text
        self.last_prompt = None

    def generate_text(self, prompt):
        self.last_prompt = prompt
        return self.response_text


def test_set_height_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "daily_log:body")
    reply1, _keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:height")
    assert "身高" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_body_height_value"

    reply2, keyboard2 = router.handle_message(fake_db, store, FAMILY_ID, "173")
    assert "173.0 公分" in reply2
    assert keyboard2["inline_keyboard"][0][0]["callback_data"] == "body:height_confirm_save"
    assert store.get(FAMILY_ID)["flow"] == "pending_body_height_confirm"

    reply3, _keyboard3 = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:height_confirm_save")
    assert "173.0 公分" in reply3
    assert store.get(FAMILY_ID) is None
    assert commands.body.get_height(fake_db, user_id) == 173.0


def test_set_waist_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply1, _keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:waist")
    assert "腰圍" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_body_waist_value"

    reply2, keyboard2 = router.handle_message(fake_db, store, FAMILY_ID, "80")
    assert "80.0 公分" in reply2
    assert keyboard2["inline_keyboard"][0][0]["callback_data"] == "body:waist_confirm_save"

    reply3, _keyboard3 = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:waist_confirm_save")
    assert "80.0 公分" in reply3
    assert store.get(FAMILY_ID) is None
    assert commands.body.get_waist(fake_db, user_id) == 80.0


def test_log_weight_offers_waist_then_records_it_full_flow(fake_db, monkeypatch):
    """記體重後順便問腰圍，回覆數字直接記錄（FR-46 擴充）。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "body:weight_new")
    router.handle_message(fake_db, store, FAMILY_ID, "75")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "body:weight_confirm_save")
    assert store.get(FAMILY_ID)["flow"] == "pending_body_waist_offer"

    reply = router.handle_message(fake_db, store, FAMILY_ID, "82")
    assert "82.0 公分" in reply
    assert store.get(FAMILY_ID) is None
    assert commands.body.get_waist(fake_db, user_id) == 82.0


def test_log_weight_offers_waist_then_skip_full_flow(fake_db, monkeypatch):
    """記體重後順便問腰圍，跳過不記錄；因為腰圍仍未設定，下次記體重會再問一次（判斷依據是
    「有沒有設定過」而不是「有沒有問過」，見 body.get_waist() 的用法，FR-46 擴充）。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "body:weight_new")
    router.handle_message(fake_db, store, FAMILY_ID, "75")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "body:weight_confirm_save")
    reply = router.handle_message(fake_db, store, FAMILY_ID, "跳過")
    assert "先不記錄腰圍" in reply
    assert store.get(FAMILY_ID) is None
    assert commands.body.get_waist(fake_db, user_id) is None

    # 腰圍仍未設定，再記一次體重會再順便問一次。
    router.handle_callback_query(fake_db, store, FAMILY_ID, "body:weight_new")
    router.handle_message(fake_db, store, FAMILY_ID, "76")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "body:weight_confirm_save")
    assert store.get(FAMILY_ID)["flow"] == "pending_body_waist_offer"


def test_log_weight_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False, "waist_cm": 80.0})
    store = ConversationStateStore()

    reply1, _keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:weight_new")
    assert "體重" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_body_weight_value"

    reply2, keyboard2 = router.handle_message(fake_db, store, FAMILY_ID, "75")
    assert "75.0 公斤" in reply2
    assert keyboard2["inline_keyboard"][0][0]["callback_data"] == "body:weight_confirm_save"

    reply3, keyboard3 = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:weight_confirm_save")
    assert "75.0 公斤" in reply3
    # 已設定腰圍，這次不會順便問腰圍，直接回到體態選單。
    assert keyboard3["inline_keyboard"][0][0]["callback_data"] == "body:menu"
    assert store.get(FAMILY_ID) is None


def test_backfill_weight_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False, "waist_cm": 80.0})
    store = ConversationStateStore()

    reply1, _keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:weight_backfill")
    assert "哪一天" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_body_weight_backfill_date"

    date_llm = _FakeLLMClient(response_text="STATUS: CLEAR\nDATE: 2026-08-01")
    router.handle_message(fake_db, store, FAMILY_ID, "8/1", llm_client=date_llm)
    assert store.get(FAMILY_ID)["weight_date"] == date(2026, 8, 1)

    router.handle_message(fake_db, store, FAMILY_ID, "80")
    reply4, _keyboard4 = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:weight_confirm_save")
    assert "80.0 公斤" in reply4
    assert store.get(FAMILY_ID) is None


def test_body_summary_and_weight_history_edit_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False, "height_cm": 173.0})
    log_id = commands.body.create_weight_log(fake_db, user_id, 80.0, date(2026, 8, 1))
    store = ConversationStateStore()

    reply1, _keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:summary")
    assert "身高" in reply1 and "173.0 公分" in reply1
    assert "體重" in reply1 and "80.0 公斤" in reply1

    reply2, keyboard2 = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:weight_list")
    assert "80.0 公斤" in reply2
    assert keyboard2["inline_keyboard"][0][0]["callback_data"] == f"body:weight_edit:{log_id}"

    router.handle_callback_query(fake_db, store, FAMILY_ID, f"body:weight_edit:{log_id}")
    assert store.get(FAMILY_ID) == {
        "flow": "pending_body_weight_value", "target_user_id": user_id, "weight_date": date(2026, 8, 1), "weight_id": log_id,
    }

    router.handle_message(fake_db, store, FAMILY_ID, "78")
    reply5, _keyboard5 = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:weight_confirm_save")
    assert "78.0 公斤" in reply5
    assert store.get(FAMILY_ID) is None
    row = fake_db.select("body_weight_logs", where="id = %s", params=(log_id,), fetch_one=True)
    assert row["weight_kg"] == 78.0


def test_weight_history_delete_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    log_id = commands.body.create_weight_log(fake_db, user_id, 80.0, date(2026, 8, 1))
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, f"body:weight_delete:{log_id}")
    assert "沒辦法復原" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == f"body:weight_confirm_delete:{log_id}"

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, f"body:weight_confirm_delete:{log_id}")
    assert "已經刪除" in reply
    assert fake_db.select("body_weight_logs", where="id = %s", params=(log_id,), fetch_one=True) is None


def test_body_voice_message_blocked_at_final_confirm_flows(fake_db, monkeypatch):
    """2026-08-17（Phase 6 第二批 2h）：體態摘要→二次確認關卡都要進 `_FINAL_CONFIRM_FLOWS`，
    語音在這幾個狀態下會被直接短路拒絕（見 router.handle_voice_message() 的說明），這裡只驗證
    `_FINAL_CONFIRM_FLOWS` 集合本身有正確涵蓋新增的體態 flow。"""
    for flow in (
        "pending_body_height_confirm", "pending_body_waist_confirm", "pending_body_weight_confirm",
        "body_weight_delete_confirm", "pending_goal_confirm", "goal_delete_confirm",
    ):
        assert flow in router._FINAL_CONFIRM_FLOWS


def test_log_exercise_full_flow(fake_db, monkeypatch):
    """2026-08-16（Phase 6 第二批 2c）：運動全面改選單按鈕觸發，舊文字觸發詞「我要記錄運動」已
    移除，入口改為「📝 日常紀錄」→「🏃 運動」子選單（`daily_log:exercise` → `exercise:new`），
    新增流程末端也改為摘要→二次確認（`exercise:confirm_save`）。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "daily_log:exercise")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "exercise:new")
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_activity"

    router.handle_message(fake_db, store, FAMILY_ID, "跑步")
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_duration"

    router.handle_message(fake_db, store, FAMILY_ID, "30")
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_heart_rate"

    calorie_llm = _FakeLLMClient(response_text="約 300 大卡")
    reply4, _keyboard4 = router.handle_message(fake_db, store, FAMILY_ID, "沒有", llm_client=calorie_llm)
    assert "300 大卡" in reply4
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_confirm"

    reply5, _keyboard5 = router.handle_callback_query(fake_db, store, FAMILY_ID, "exercise:confirm_save")
    assert "300 大卡" in reply5
    assert store.get(FAMILY_ID) is None


def test_my_exercise_logs_full_flow_delete(fake_db, monkeypatch):
    """2026-08-16（Phase 6 第二批 2c）：舊文字觸發詞「我的運動紀錄」已移除，改由
    「🏃 運動」子選單的「📋 查看清單」（`exercise:list`）進入，刪除也改為按鈕二次確認
    （`exercise:delete:<id>` → `exercise:confirm_delete:<id>`），不再走 LLM 對話式確認。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    log_id = commands.body.create_exercise_log(fake_db, user_id, "跑步", 30, None, 300.0, date(2026, 8, 4))
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "exercise:list")

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, f"exercise:delete:{log_id}")
    assert "沒辦法復原" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == f"exercise:confirm_delete:{log_id}"

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, f"exercise:confirm_delete:{log_id}")
    assert "已經刪除" in reply
    assert fake_db.select("exercise_logs", where="id = %s", params=(log_id,), fetch_one=True) is None


def test_log_diet_food_full_flow(fake_db, monkeypatch):
    """2026-08-16（Phase 6 第二批 2g）：飲食全面改選單按鈕觸發，舊文字觸發詞「我要記錄飲食」已
    移除，入口改為「📝 日常紀錄」→「🍚 飲食」子選單（`daily_log:diet` → `diet:new`），新增流程
    改成先問飲水（跳過）再問食物，末端也改為摘要→二次確認（`diet:confirm_save`）。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "daily_log:diet")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "diet:new")
    assert store.get(FAMILY_ID)["flow"] == "pending_diet_water_choice"

    router.handle_callback_query(fake_db, store, FAMILY_ID, "diet:water_no")
    assert store.get(FAMILY_ID)["flow"] == "pending_diet_food_choice"

    router.handle_callback_query(fake_db, store, FAMILY_ID, "diet:food_yes")
    assert store.get(FAMILY_ID)["flow"] == "pending_diet_food_input_mode"

    router.handle_callback_query(fake_db, store, FAMILY_ID, "diet:food_text")
    assert store.get(FAMILY_ID)["flow"] == "pending_diet_description"

    router.handle_message(fake_db, store, FAMILY_ID, "雞胸肉便當")
    assert store.get(FAMILY_ID)["flow"] == "pending_diet_nutrition_source"

    macro_llm = _FakeLLMClient(response_text="CALORIES: 320\nPROTEIN: 20\nCARBS: 40\nFAT: 10")
    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "diet:nutrition_ai", llm_client=macro_llm)
    assert "熱量約 320 大卡" in reply
    assert store.get(FAMILY_ID)["flow"] == "pending_diet_confirm"

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "diet:confirm_save")
    assert "記錄好" in reply
    assert store.get(FAMILY_ID) is None
    row = fake_db.select("diet_logs", where="user_id = %s", params=(user_id,))[0]
    assert row["description"] == "雞胸肉便當"


def test_log_diet_water_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "daily_log:diet")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "diet:new")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "diet:water_yes")
    assert store.get(FAMILY_ID)["flow"] == "pending_diet_water_amount"

    reply, _keyboard = router.handle_message(fake_db, store, FAMILY_ID, "500")
    assert store.get(FAMILY_ID)["flow"] == "pending_diet_food_choice"

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "diet:food_no")
    assert "500 毫升" in reply
    assert store.get(FAMILY_ID)["flow"] == "pending_diet_confirm"

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "diet:confirm_save")
    assert "記錄好" in reply
    assert store.get(FAMILY_ID) is None


def test_set_body_goal_weight_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "body:goal")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "body:goal:new:-:body")
    assert store.get(FAMILY_ID)["flow"] == "pending_goal_type"

    router.handle_message(fake_db, store, FAMILY_ID, "體重")
    assert store.get(FAMILY_ID)["flow"] == "pending_goal_weight_value"

    router.handle_message(fake_db, store, FAMILY_ID, "60")
    assert store.get(FAMILY_ID)["flow"] == "pending_goal_deadline"

    deadline_llm = _FakeLLMClient(response_text="STATUS: NO_DEADLINE")
    reply, keyboard = router.handle_message(fake_db, store, FAMILY_ID, "沒有", llm_client=deadline_llm)

    assert "目標體重 60.0 公斤" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "body:goal:confirm_save"
    assert store.get(FAMILY_ID)["flow"] == "pending_goal_confirm"

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:goal:confirm_save")
    assert "已經幫你記錄目標" in reply
    assert store.get(FAMILY_ID) is None
    goal = fake_db.select("body_goals", where="user_id = %s", params=(user_id,))[0]
    assert goal["goal_type"] == "weight"


def test_my_body_goals_list_edit_delete_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    goal_id = commands.body.create_goal(fake_db, user_id, "exercise", "累積運動 300 分鐘", target_value=300)
    store = ConversationStateStore()

    reply1, keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:goal:list:-:body")
    assert "累積運動 300 分鐘" in reply1
    assert keyboard1["inline_keyboard"][0][1]["callback_data"] == f"body:goal:delete:{goal_id}:body"

    reply2, keyboard2 = router.handle_callback_query(fake_db, store, FAMILY_ID, f"body:goal:delete:{goal_id}:body")
    assert "沒辦法復原" in reply2
    assert keyboard2["inline_keyboard"][0][0]["callback_data"] == f"body:goal:confirm_delete:{goal_id}:body"

    reply3, _keyboard3 = router.handle_callback_query(fake_db, store, FAMILY_ID, f"body:goal:confirm_delete:{goal_id}:body")
    assert "已經刪除" in reply3
    goal = fake_db.select("body_goals", where="id = %s", params=(goal_id,), fetch_one=True)
    assert goal["status"] == "cancelled"


def test_exercise_menu_goal_button_presets_exercise_type(fake_db, monkeypatch):
    """從「🏃 運動」子選單的「🎯 目標」按鈕點進來，`goal_type` 已預設，跳過選類型那題（見
    router._dispatch_body_goal_callback()）。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "exercise:goal")
    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:goal:new:exercise:exercise")
    assert "累積運動分鐘數" in reply
    assert store.get(FAMILY_ID)["goal_type"] == "exercise"

    router.handle_message(fake_db, store, FAMILY_ID, "300")
    deadline_llm = _FakeLLMClient(response_text="STATUS: NO_DEADLINE")
    reply, keyboard = router.handle_message(fake_db, store, FAMILY_ID, "沒有", llm_client=deadline_llm)
    # 返回鍵導回運動子選單，不是體態子選單。
    assert keyboard["inline_keyboard"][1][0]["callback_data"] == "exercise:menu"


def test_diet_menu_goal_button_presets_diet_type(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "diet:goal")
    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "body:goal:new:diet:diet")
    assert "飲食目標" in reply
    assert store.get(FAMILY_ID)["goal_type"] == "diet"
