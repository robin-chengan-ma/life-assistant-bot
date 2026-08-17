"""src/bot/commands.py 體態管理相關流程的整合測試（對應 docs/specs/SPEC.md FR-45／FR-45a／FR-46，
Phase 6 第二批 2h）。

不重複測試 src/bot/body.py 本身的純邏輯（已有 tests/bot/test_body.py 100% 覆蓋），這裡只驗證
commands.py 的對話狀態機串接是否正確（狀態轉移、反問文案、摘要→二次確認、最終寫入結果）。
"""
from datetime import date
from unittest.mock import MagicMock

from src.bot import commands
from src.bot.state import ConversationStateStore


class _FakeLLMClient:
    """模擬 LLMClient，依序回傳預先準備好的回覆，供多輪反問流程的測試使用。"""

    def __init__(self, response_text="CONFIRM"):
        self.response_text = response_text
        self.last_prompt = None

    def generate_text(self, prompt):
        self.last_prompt = prompt
        return self.response_text


# --- 體態子選單首頁 ---


def test_start_body_menu_lists_seven_buttons():
    text, keyboard = commands.start_body_menu()
    assert "體態" in text
    callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert callbacks == [
        "body:height", "body:waist", "body:weight_new", "body:weight_backfill",
        "body:summary", "body:goal", "menu:daily_log",
    ]


# --- 身高 ---


def test_start_body_height_asks_height(fake_db):
    store = ConversationStateStore()
    reply = commands.start_body_height(store, telegram_user_id=1, user_id=42)
    assert "身高" in reply
    assert "140" in reply and "200" in reply
    assert store.get(1) == {"flow": "pending_body_height_value", "target_user_id": 42}


def test_handle_body_height_value_step_unreasonable_reprompts(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_body_height_value", "target_user_id": 42})

    reply, keyboard = commands.handle_body_height_value_step(store, telegram_user_id=1, text="300")

    assert "不太合理" in reply
    assert keyboard is None
    assert store.get(1) == {"flow": "pending_body_height_value", "target_user_id": 42}


def test_handle_body_height_value_step_valid_asks_confirm(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_body_height_value", "target_user_id": 42})

    reply, keyboard = commands.handle_body_height_value_step(store, telegram_user_id=1, text="173")

    assert "173.0 公分" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "body:height_confirm_save"
    assert store.get(1)["flow"] == "pending_body_height_confirm"
    assert commands.body.get_height(fake_db, 42) is None


def test_handle_body_height_confirm_save_writes(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_body_height_confirm", "target_user_id": user_id, "height": 173.0})

    reply = commands.handle_body_height_confirm_save(fake_db, store, telegram_user_id=1)

    assert "173.0 公分" in reply
    assert store.get(1) is None
    assert commands.body.get_height(fake_db, user_id) == 173.0


def test_handle_body_height_confirm_save_without_pending_state_is_noop(fake_db):
    store = ConversationStateStore()
    reply = commands.handle_body_height_confirm_save(fake_db, store, telegram_user_id=1)
    assert "沒有進行中" in reply


# --- 腰圍 ---


def test_start_body_waist_asks_waist(fake_db):
    store = ConversationStateStore()
    reply = commands.start_body_waist(store, telegram_user_id=1, user_id=42)
    assert "腰圍" in reply
    assert "50" in reply and "150" in reply
    assert store.get(1) == {"flow": "pending_body_waist_value", "target_user_id": 42}


def test_handle_body_waist_value_step_unparseable_reprompts(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_body_waist_value", "target_user_id": 42})

    reply, keyboard = commands.handle_body_waist_value_step(store, telegram_user_id=1, text="不知道")

    assert "沒看懂" in reply
    assert keyboard is None
    assert store.get(1) == {"flow": "pending_body_waist_value", "target_user_id": 42}


def test_handle_body_waist_value_step_unreasonable_reprompts(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_body_waist_value", "target_user_id": 42})

    reply, keyboard = commands.handle_body_waist_value_step(store, telegram_user_id=1, text="300")

    assert "不太合理" in reply
    assert keyboard is None


def test_handle_body_waist_value_step_valid_asks_confirm(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_body_waist_value", "target_user_id": 42})

    reply, keyboard = commands.handle_body_waist_value_step(store, telegram_user_id=1, text="80")

    assert "80.0 公分" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "body:waist_confirm_save"
    assert store.get(1)["flow"] == "pending_body_waist_confirm"


def test_handle_body_waist_confirm_save_writes(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_body_waist_confirm", "target_user_id": user_id, "waist": 80.0})

    reply = commands.handle_body_waist_confirm_save(fake_db, store, telegram_user_id=1)

    assert "80.0 公分" in reply
    assert store.get(1) is None
    assert commands.body.get_waist(fake_db, user_id) == 80.0


def test_handle_body_waist_offer_step_valid_number_saves_waist(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_body_waist_offer", "target_user_id": user_id})

    reply = commands.handle_body_waist_offer_step(fake_db, store, telegram_user_id=1, text="85")

    assert "85.0 公分" in reply
    assert store.get(1) is None
    assert commands.body.get_waist(fake_db, user_id) == 85.0


def test_handle_body_waist_offer_step_unreasonable_number_reprompts(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_body_waist_offer", "target_user_id": user_id})

    reply = commands.handle_body_waist_offer_step(fake_db, store, telegram_user_id=1, text="5")

    assert "不太合理" in reply
    assert store.get(1) == {"flow": "pending_body_waist_offer", "target_user_id": user_id}


def test_handle_body_waist_offer_step_non_numeric_reply_skips(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_body_waist_offer", "target_user_id": user_id})

    reply = commands.handle_body_waist_offer_step(fake_db, store, telegram_user_id=1, text="跳過")

    assert "先不記錄腰圍" in reply
    assert store.get(1) is None
    assert commands.body.get_waist(fake_db, user_id) is None


# --- 體重 ---


def test_start_body_weight_new_sets_today_date(monkeypatch, fake_db):
    monkeypatch.setattr(commands, "_now", lambda: commands.datetime(2026, 8, 4, 9, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    reply = commands.start_body_weight_new(store, telegram_user_id=1, user_id=42)
    assert "體重" in reply
    assert store.get(1) == {
        "flow": "pending_body_weight_value", "target_user_id": 42, "weight_date": date(2026, 8, 4), "weight_id": None,
    }


def test_handle_body_weight_value_step_unreasonable_reprompts(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_body_weight_value", "target_user_id": 42, "weight_date": date(2026, 8, 4), "weight_id": None})

    reply, keyboard = commands.handle_body_weight_value_step(fake_db, store, telegram_user_id=1, text="10")

    assert "不太合理" in reply
    assert keyboard is None
    assert store.get(1) is not None


def test_handle_body_weight_value_step_valid_asks_confirm_with_bmi_preview(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False, "height_cm": 173.0})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_body_weight_value", "target_user_id": user_id, "weight_date": date(2026, 8, 4), "weight_id": None})

    reply, keyboard = commands.handle_body_weight_value_step(fake_db, store, telegram_user_id=1, text="77")

    assert "77.0 公斤" in reply
    assert "BMI" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "body:weight_confirm_save"
    assert store.get(1)["flow"] == "pending_body_weight_confirm"
    assert fake_db.select("body_weight_logs") == []


def test_handle_body_weight_confirm_save_creates_row_with_bmi_and_goal_message(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False, "height_cm": 173.0, "waist_cm": 80.0})
    commands.body.create_goal(fake_db, user_id, "weight", "瘦到 78 公斤", target_value=78, baseline_value=80)
    store = ConversationStateStore()
    store.set(1, {
        "flow": "pending_body_weight_confirm", "target_user_id": user_id,
        "weight_date": date(2026, 8, 4), "weight_id": None, "weight": 77.0,
    })

    reply, keyboard = commands.handle_body_weight_confirm_save(fake_db, store, telegram_user_id=1)

    assert "77.0 公斤" in reply
    assert "BMI" in reply
    assert "恭喜" in reply
    # 已經設定過腰圍，這次不會順便問腰圍。
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "body:menu"
    assert store.get(1) is None


def test_handle_body_weight_confirm_save_offers_waist_when_never_set(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {
        "flow": "pending_body_weight_confirm", "target_user_id": user_id,
        "weight_date": date(2026, 8, 4), "weight_id": None, "weight": 77.0,
    })

    reply, keyboard = commands.handle_body_weight_confirm_save(fake_db, store, telegram_user_id=1)

    assert "腰圍" in reply
    assert keyboard is None
    assert store.get(1) == {"flow": "pending_body_waist_offer", "target_user_id": user_id}


def test_handle_body_weight_confirm_save_edit_does_not_offer_waist(fake_db):
    """編輯既有紀錄（`weight_id` 非 None）不順便問腰圍，只有新增紀錄才問。"""
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    weight_id = commands.body.create_weight_log(fake_db, user_id, 80.0, date(2026, 8, 1))
    store = ConversationStateStore()
    store.set(1, {
        "flow": "pending_body_weight_confirm", "target_user_id": user_id,
        "weight_date": date(2026, 8, 1), "weight_id": weight_id, "weight": 78.0,
    })

    reply, keyboard = commands.handle_body_weight_confirm_save(fake_db, store, telegram_user_id=1)

    assert "腰圍" not in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "body:menu"
    assert store.get(1) is None
    row = fake_db.select("body_weight_logs", where="id = %s", params=(weight_id,), fetch_one=True)
    assert row["weight_kg"] == 78.0


def test_handle_body_weight_confirm_save_without_pending_state_is_noop(fake_db):
    store = ConversationStateStore()
    reply, keyboard = commands.handle_body_weight_confirm_save(fake_db, store, telegram_user_id=1)
    assert "沒有進行中" in reply
    assert keyboard is None


def test_handle_body_weight_backfill_date_step_clear_moves_to_weight_value(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: commands.datetime(2026, 8, 4, 9, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_body_weight_backfill_date", "target_user_id": 42})
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nDATE: 2026-08-01")

    reply = commands.handle_body_weight_backfill_date_step(llm_client, store, telegram_user_id=1, text="8/1")

    assert "體重" in reply
    assert store.get(1) == {
        "flow": "pending_body_weight_value", "target_user_id": 42, "weight_date": date(2026, 8, 1), "weight_id": None,
    }


def test_start_body_summary_shows_four_items(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False, "height_cm": 173.0})
    commands.body.create_weight_log(fake_db, user_id, 70.0, date(2026, 8, 1))

    text, keyboard = commands.start_body_summary(fake_db, user_id)

    assert "身高" in text and "173.0 公分" in text
    assert "體重" in text and "70.0 公斤" in text
    assert "腰圍" in text and "尚無紀錄" in text
    assert "BMI" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "body:weight_list"


def test_body_weight_list_edit_delete_flow(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    log_id = commands.body.create_weight_log(fake_db, user_id, 80.0, date(2026, 8, 1))
    store = ConversationStateStore()

    text, keyboard = commands.handle_body_weight_list(fake_db, user_id)
    assert "80.0 公斤" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == f"body:weight_edit:{log_id}"
    assert keyboard["inline_keyboard"][0][1]["callback_data"] == f"body:weight_delete:{log_id}"

    reply = commands.start_body_weight_edit(fake_db, store, telegram_user_id=1, user_id=user_id, weight_log_id=log_id)
    assert "重新輸入" in reply
    assert store.get(1) == {
        "flow": "pending_body_weight_value", "target_user_id": user_id, "weight_date": date(2026, 8, 1), "weight_id": log_id,
    }

    reply, keyboard = commands.start_body_weight_delete_confirm(fake_db, store, telegram_user_id=1, user_id=user_id, weight_log_id=log_id)
    assert "沒辦法復原" in reply
    assert store.get(1)["flow"] == "body_weight_delete_confirm"

    reply = commands.handle_body_weight_delete(fake_db, store, telegram_user_id=1, user_id=user_id, weight_log_id=log_id)
    assert "已經刪除" in reply
    assert fake_db.select("body_weight_logs", where="id = %s", params=(log_id,), fetch_one=True) is None
    assert store.get(1) is None


def test_start_body_weight_edit_rejects_other_users_log(fake_db):
    log_id = commands.body.create_weight_log(fake_db, 99, 80.0, date(2026, 8, 1))
    store = ConversationStateStore()
    reply = commands.start_body_weight_edit(fake_db, store, telegram_user_id=1, user_id=42, weight_log_id=log_id)
    assert "找不到" in reply


def test_handle_body_confirm_text_only_accepts_buttons(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_body_weight_confirm", "target_user_id": 42})
    reply, keyboard = commands.handle_body_confirm_text(store, telegram_user_id=1)
    assert "按鈕操作" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "body:menu"
    assert store.get(1) is None


# --- 運動 ---


def test_exercise_full_log_flow_with_calorie_estimate(fake_db):
    """2026-08-17（FR-47a，批次2）：運動改版後的完整流程——選類別（既有按鈕）→時長→心率
    （跳過）→補充內容（跳過）→AI 估算熱量→摘要→二次確認，實際寫入要等
    `handle_exercise_confirm_save`（`exercise:confirm_save` 按鈕），端對端串接見
    tests/bot/test_router.py test_exercise_new_flow_records_entry_with_confirm_gate。"""
    category_id = fake_db.insert("exercise_categories", {"name": "跑步", "normalized_name": "跑步"})
    store = ConversationStateStore()
    commands.start_exercise_log(fake_db, store, telegram_user_id=1, user_id=42)

    reply, _keyboard = commands.handle_exercise_category_choice(fake_db, store, telegram_user_id=1, category_id=category_id)
    assert "多久" in reply

    reply, _keyboard = commands.handle_exercise_duration_step(store, telegram_user_id=1, text="30")
    assert "心率" in reply

    reply, _keyboard = commands.handle_exercise_skip_heart_rate(store, telegram_user_id=1)
    assert "補充" in reply

    reply, keyboard = commands.handle_exercise_skip_note(store, telegram_user_id=1)
    assert "AI 估算" in keyboard["inline_keyboard"][0][0]["text"]

    llm_client = _FakeLLMClient(response_text="大約 300 大卡")
    reply, keyboard = commands.handle_exercise_calorie_ai_choice(llm_client, store, telegram_user_id=1)

    assert "300 大卡" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "exercise:confirm_save"
    assert store.get(1)["flow"] == "pending_exercise_confirm"
    assert fake_db.select("exercise_logs") == []

    reply = commands.handle_exercise_confirm_save(fake_db, store, telegram_user_id=1)

    assert "300 大卡" in reply
    assert store.get(1) is None
    row = fake_db.select("exercise_logs", where="user_id = %s", params=(42,))[0]
    assert row["activity"] == "跑步"
    assert row["category_id"] == category_id
    assert row["duration_minutes"] == 30
    assert row["heart_rate"] is None
    assert row["note"] is None
    assert row["calorie_source"] == "ai"
    assert row["estimated_calories"] == 300.0


def test_handle_exercise_duration_step_invalid_reprompts(fake_db):
    category_id = fake_db.insert("exercise_categories", {"name": "跑步", "normalized_name": "跑步"})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_exercise_category", "target_user_id": 42, "exercise_date": date(2026, 8, 4), "exercise_id": None})
    commands.handle_exercise_category_choice(fake_db, store, telegram_user_id=1, category_id=category_id)

    reply = commands.handle_exercise_duration_step(store, telegram_user_id=1, text="不知道")
    assert "正整數" in reply


def test_start_exercise_menu_includes_goal_button():
    _text, keyboard = commands.start_exercise_menu()
    callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "exercise:goal" in callbacks


# --- 飲食 ---


def test_handle_diet_backfill_date_step_clear_asks_water_for_that_date(fake_db, monkeypatch):
    """迴歸測試（見 docs/ADR/debug/robinson.md 2026-08-16「飲食補記日期解析 NameError」）：
    `handle_diet_backfill_date_step()` 原本呼叫不存在的 `_parse_date_description()`，實機補記
    「昨天」直接 500 例外；正確做法要比照 `handle_exercise_backfill_date_step()` 用
    `_parse_key_value_block(llm_client.generate_text(_BACKFILL_DATE_PARSE_PROMPT.format(...)))`。"""
    monkeypatch.setattr(commands, "_now", lambda: commands.datetime(2026, 8, 4, 9, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_diet_backfill_date", "target_user_id": 42})
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nDATE: 2026-08-03")

    reply, _keyboard = commands.handle_diet_backfill_date_step(fake_db, llm_client, store, telegram_user_id=1, text="昨天")

    assert "飲水" in reply
    assert store.get(1)["diet_date"] == date(2026, 8, 3)


def test_diet_food_flow_estimates_macros(fake_db):
    store = ConversationStateStore()
    reply, _keyboard = commands.start_diet_log(fake_db, store, telegram_user_id=1, user_id=42)
    assert "飲水" in reply

    reply, _keyboard = commands.handle_diet_water_choice_step(store, telegram_user_id=1, action="water_no")
    assert "食物" in reply

    reply, _keyboard = commands.handle_diet_food_choice_step(store, telegram_user_id=1, action="food_yes")
    assert "文字" in reply

    reply, _keyboard = commands.handle_diet_food_input_mode_step(store, telegram_user_id=1, action="food_text")
    assert "食物內容" in reply

    reply, _keyboard = commands.handle_diet_description_step(store, telegram_user_id=1, text="雞胸肉便當")
    assert "營養素" in reply

    llm_client = _FakeLLMClient(response_text="CALORIES: 320\nPROTEIN: 20\nCARBS: 40\nFAT: 10")
    reply, _keyboard = commands.handle_diet_nutrition_source_step(llm_client, store, telegram_user_id=1, action="nutrition_ai")
    assert "熱量約 320 大卡" in reply
    assert "估算值" in reply

    reply = commands.handle_diet_confirm_save(fake_db, store, telegram_user_id=1)
    assert "記錄好" in reply
    row = fake_db.select("diet_logs", where="user_id = %s", params=(42,))[0]
    assert row["description"] == "雞胸肉便當"
    assert row["estimated_calories"] == 320.0
    assert row["nutrition_source"] == "ai"


def test_diet_water_flow(fake_db):
    store = ConversationStateStore()
    commands.start_diet_log(fake_db, store, telegram_user_id=1, user_id=42)

    reply, _keyboard = commands.handle_diet_water_choice_step(store, telegram_user_id=1, action="water_yes")
    assert "毫升" in reply

    reply, _keyboard = commands.handle_diet_water_amount_step(store, telegram_user_id=1, text="500")
    assert "食物" in reply

    reply, _keyboard = commands.handle_diet_food_choice_step(store, telegram_user_id=1, action="food_no")
    assert "500 毫升" in reply

    reply = commands.handle_diet_confirm_save(fake_db, store, telegram_user_id=1)
    assert "記錄好" in reply
    row = fake_db.select("diet_logs", where="user_id = %s", params=(42,))[0]
    assert row["entry_type"] == "water"
    assert row["water_ml"] == 500


def test_start_diet_menu_includes_goal_button():
    _text, keyboard = commands.start_diet_menu()
    callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "diet:goal" in callbacks


# --- 體態目標（三個子功能共用，2026-08-17 改按鈕觸發＋多筆並存＋編輯/刪除）---


def test_start_body_goal_menu_new_and_list_buttons():
    text, keyboard = commands.start_body_goal_menu(None, "body")
    assert "目標" in text
    callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert callbacks == ["body:goal:new:-:body", "body:goal:list:-:body", "body:menu"]


def test_start_body_goal_menu_preset_type_encodes_source():
    _text, keyboard = commands.start_body_goal_menu("exercise", "exercise")
    callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert callbacks == ["body:goal:new:exercise:exercise", "body:goal:list:exercise:exercise", "exercise:menu"]


def test_start_body_goal_new_without_type_asks_type(fake_db):
    store = ConversationStateStore()
    reply = commands.start_body_goal_new(store, telegram_user_id=1, user_id=42, goal_type=None, source="body")
    assert "哪一種體態目標" in reply
    assert store.get(1) == {"flow": "pending_goal_type", "target_user_id": 42, "goal_source": "body"}


def test_start_body_goal_new_with_preset_type_skips_type_question(fake_db):
    store = ConversationStateStore()
    reply = commands.start_body_goal_new(store, telegram_user_id=1, user_id=42, goal_type="exercise", source="exercise")
    assert "累積運動分鐘數" in reply
    assert store.get(1) == {
        "target_user_id": 42, "goal_source": "exercise", "goal_type": "exercise", "goal_id": None,
        "flow": "pending_goal_exercise_minutes",
    }


def test_set_weight_goal_full_flow_with_deadline(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    commands.body.create_weight_log(fake_db, user_id, 80.0, date(2026, 8, 1))
    store = ConversationStateStore()
    commands.start_body_goal_new(store, telegram_user_id=1, user_id=user_id, goal_type=None, source="body")

    reply = commands.handle_goal_type_step(store, telegram_user_id=1, text="體重")
    assert "目標體重" in reply

    reply = commands.handle_goal_weight_value_step(fake_db, store, telegram_user_id=1, text="70")
    assert "完成時間" in reply
    assert store.get(1)["baseline_value"] == 80.0

    llm_client = _FakeLLMClient(response_text="STATUS: HAS_DEADLINE\nDATE: 2026-11-04")
    reply = commands.handle_goal_deadline_step(llm_client, store, telegram_user_id=1, text="三個月內")

    # 新增流程、有期限的目標會多問一輪是否同步，還不會直接寫入。
    assert "同步到 Google 家庭行事曆" in reply
    assert store.get(1)["flow"] == "pending_goal_calendar_sync"
    assert len(fake_db.select("body_goals", where="user_id = %s", params=(user_id,))) == 0

    llm_client.response_text = "CANCEL"
    reply, keyboard = commands.handle_goal_calendar_sync_step(llm_client, store, telegram_user_id=1, text="不用")

    assert "請確認以下內容" in reply
    assert "2026/11/04" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "body:goal:confirm_save"
    assert store.get(1)["flow"] == "pending_goal_confirm"
    assert len(fake_db.select("body_goals", where="user_id = %s", params=(user_id,))) == 0

    reply = commands.handle_goal_confirm_save(fake_db, store, telegram_user_id=1)

    assert "已經幫你記錄目標" in reply
    assert store.get(1) is None
    goal = fake_db.select("body_goals", where="user_id = %s", params=(user_id,))[0]
    assert goal["goal_type"] == "weight"
    assert goal["target_value"] == 70
    assert goal["baseline_value"] == 80.0
    assert goal["target_date"] == date(2026, 11, 4)
    assert goal["sync_to_calendar"] is False


def test_set_exercise_goal_no_deadline(fake_db):
    store = ConversationStateStore()
    commands.start_body_goal_new(store, telegram_user_id=1, user_id=42, goal_type="exercise", source="exercise")

    reply = commands.handle_goal_exercise_minutes_step(store, telegram_user_id=1, text="300")
    assert "完成時間" in reply

    llm_client = _FakeLLMClient(response_text="STATUS: NO_DEADLINE")
    reply, keyboard = commands.handle_goal_deadline_step(llm_client, store, telegram_user_id=1, text="沒有")

    assert "累積運動 300 分鐘" in reply
    # 沒有期限的目標跳過同步問句，直接進摘要確認；返回鍵導回運動子選單。
    assert keyboard["inline_keyboard"][1][0]["callback_data"] == "exercise:menu"

    reply = commands.handle_goal_confirm_save(fake_db, store, telegram_user_id=1)
    goal = fake_db.select("body_goals", where="user_id = %s", params=(42,))[0]
    assert goal["goal_type"] == "exercise"
    assert goal["target_value"] == 300
    assert goal["target_date"] is None


def test_goal_deadline_step_unclear_reprompts(fake_db):
    store = ConversationStateStore()
    store.set(1, {
        "flow": "pending_goal_deadline", "target_user_id": 42, "goal_source": "body", "goal_id": None,
        "goal_type": "diet", "target_value": None, "baseline_value": None, "target_description": "控制飲食",
    })
    llm_client = _FakeLLMClient(response_text="STATUS: UNCLEAR")

    reply = commands.handle_goal_deadline_step(llm_client, store, telegram_user_id=1, text="嗯…")

    assert "不太確定期限" in reply
    assert store.get(1) is not None


def test_body_goal_list_filters_by_type_and_edit_delete_flow(fake_db):
    weight_goal_id = commands.body.create_goal(fake_db, 42, "weight", "瘦到 60kg", target_value=60, baseline_value=75)
    commands.body.create_goal(fake_db, 42, "diet", "控制在每天 1800 大卡以內")
    store = ConversationStateStore()

    # 不篩選類型：兩筆都看得到。
    text, _keyboard = commands.start_body_goal_list(fake_db, 42, None, "body")
    assert "瘦到 60kg" in text and "控制在每天 1800 大卡以內" in text

    # 篩選成體重：只看得到體重那筆。
    text, keyboard = commands.start_body_goal_list(fake_db, 42, "weight", "body")
    assert "瘦到 60kg" in text
    assert "控制在每天 1800 大卡以內" not in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == f"body:goal:edit:{weight_goal_id}:body"

    # 編輯：重新走一次目標值/期限輸入。
    reply = commands.start_body_goal_edit(fake_db, store, telegram_user_id=1, user_id=42, goal_id=weight_goal_id, source="body")
    assert "目標體重" in reply
    assert store.get(1)["goal_id"] == weight_goal_id

    reply = commands.handle_goal_weight_value_step(fake_db, store, telegram_user_id=1, text="58")
    llm_client = _FakeLLMClient(response_text="STATUS: NO_DEADLINE")
    reply, keyboard = commands.handle_goal_deadline_step(llm_client, store, telegram_user_id=1, text="沒有")
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "body:goal:confirm_save"

    reply = commands.handle_goal_confirm_save(fake_db, store, telegram_user_id=1)
    assert "已經幫你更新目標" in reply
    goal = commands.body.get_goal(fake_db, weight_goal_id)
    assert goal["target_value"] == 58

    # 刪除（＝ cancel_goal，狀態改成 cancelled）。
    reply, keyboard = commands.start_body_goal_delete_confirm(fake_db, store, telegram_user_id=1, user_id=42, goal_id=weight_goal_id, source="body")
    assert "沒辦法復原" in reply
    assert store.get(1)["flow"] == "goal_delete_confirm"

    reply = commands.handle_goal_delete(fake_db, store, telegram_user_id=1, user_id=42, goal_id=weight_goal_id)
    assert "已經刪除" in reply
    goal = commands.body.get_goal(fake_db, weight_goal_id)
    assert goal["status"] == "cancelled"
    assert store.get(1) is None


def test_start_body_goal_edit_rejects_other_users_goal(fake_db):
    goal_id = commands.body.create_goal(fake_db, 99, "weight", "瘦到 60kg", target_value=60, baseline_value=75)
    store = ConversationStateStore()
    reply = commands.start_body_goal_edit(fake_db, store, telegram_user_id=1, user_id=42, goal_id=goal_id, source="body")
    assert "找不到" in reply


def test_handle_goal_confirm_text_only_accepts_buttons(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_goal_confirm", "target_user_id": 42, "goal_source": "exercise"})
    reply, keyboard = commands.handle_goal_confirm_text(store, telegram_user_id=1)
    assert "按鈕操作" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "exercise:menu"
    assert store.get(1) is None


def test_handle_goal_confirm_save_without_pending_state_is_noop(fake_db):
    store = ConversationStateStore()
    reply = commands.handle_goal_confirm_save(fake_db, store, telegram_user_id=1)
    assert "沒有進行中" in reply


# --- Google Calendar 同步（FR-66c，見 ADR-17） ---


def test_handle_goal_calendar_sync_step_creates_event_when_confirmed(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_goal_calendar_sync",
            "target_user_id": 42, "goal_source": "body", "goal_id": None,
            "goal_type": "weight",
            "target_description": "目標體重 70.0 公斤",
            "target_value": 70.0,
            "baseline_value": 80.0,
            "target_date": date(2026, 11, 4),
        },
    )
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    _reply, _keyboard = commands.handle_goal_calendar_sync_step(llm_client, store, telegram_user_id=1, text="要")
    assert store.get(1)["sync_to_calendar"] is True

    calendar_client = MagicMock()
    calendar_client.create_event.return_value = "event-abc123"
    commands.handle_goal_confirm_save(fake_db, store, telegram_user_id=1, calendar_client=calendar_client)

    goal = fake_db.select("body_goals", where="user_id = %s", params=(42,))[0]
    assert goal["sync_to_calendar"] is True
    assert goal["google_calendar_event_id"] == "event-abc123"
    calendar_client.create_event.assert_called_once_with(
        summary="目標體重 70.0 公斤", start="2026-11-04", end="2026-11-05",
        description="來自 Robinson 體態目標", all_day=True,
    )


def test_handle_goal_confirm_save_skips_event_creation_when_client_is_none(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_goal_confirm",
            "target_user_id": 42, "goal_source": "body", "goal_id": None,
            "goal_type": "weight", "target_description": "目標體重 70.0 公斤",
            "target_value": 70.0, "baseline_value": 80.0, "target_date": date(2026, 11, 4),
            "sync_to_calendar": True,
        },
    )

    commands.handle_goal_confirm_save(fake_db, store, telegram_user_id=1, calendar_client=None)

    goal = fake_db.select("body_goals", where="user_id = %s", params=(42,))[0]
    assert goal["sync_to_calendar"] is True
    assert goal.get("google_calendar_event_id") is None


def test_handle_goal_confirm_save_swallows_calendar_exception(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_goal_confirm",
            "target_user_id": 42, "goal_source": "body", "goal_id": None,
            "goal_type": "weight", "target_description": "目標體重 70.0 公斤",
            "target_value": 70.0, "baseline_value": 80.0, "target_date": date(2026, 11, 4),
            "sync_to_calendar": True,
        },
    )
    calendar_client = MagicMock()
    calendar_client.create_event.side_effect = RuntimeError("boom")

    commands.handle_goal_confirm_save(fake_db, store, telegram_user_id=1, calendar_client=calendar_client)

    goal = fake_db.select("body_goals", where="user_id = %s", params=(42,))[0]
    assert goal["sync_to_calendar"] is True
    assert goal.get("google_calendar_event_id") is None


def test_handle_goal_delete_deletes_calendar_event_when_synced(fake_db):
    goal_id = commands.body.create_goal(fake_db, 42, "weight", "瘦到 60kg", target_value=60, baseline_value=75)
    commands.body.set_calendar_event_id(fake_db, goal_id, "event-abc123")
    store = ConversationStateStore()
    calendar_client = MagicMock()

    commands.handle_goal_delete(fake_db, store, telegram_user_id=1, user_id=42, goal_id=goal_id, calendar_client=calendar_client)

    calendar_client.delete_event.assert_called_once_with(event_id="event-abc123")
