"""src/bot/router.py 體態管理相關觸發詞與 flow 分派的端對端測試（對應 robinson SPEC.md
FR-45～FR-48，Step 2.2）。透過 `router.handle_message()` 整段串接驗證，跟
tests/bot/test_router.py 記帳模組測試同一套風格。
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

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "設定身高")
    assert "身高" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_height_value"

    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "173")
    assert "173.0 公分" in reply2
    assert store.get(FAMILY_ID) is None
    assert commands.body.get_height(fake_db, user_id) == 173.0


def test_log_weight_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "我要記錄體重")
    assert "體重" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_weight_value"

    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "75")
    assert "75.0 公斤" in reply2
    assert store.get(FAMILY_ID) is None


def test_backfill_weight_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "我要補記體重")
    assert "哪一天" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_weight_backfill_date"

    date_llm = _FakeLLMClient(response_text="STATUS: CLEAR\nDATE: 2026-08-01")
    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "8/1", llm_client=date_llm)
    assert store.get(FAMILY_ID)["weight_date"] == date(2026, 8, 1)

    reply3 = router.handle_message(fake_db, store, FAMILY_ID, "80")
    assert "80.0 公斤" in reply3
    assert store.get(FAMILY_ID) is None


def test_my_weight_logs_full_flow_update(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    log_id = commands.body.create_weight_log(fake_db, user_id, 80.0, date(2026, 8, 1))
    store = ConversationStateStore()

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "我的體重紀錄")
    assert "80.0 公斤" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_weight_list_action"

    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "1")
    assert store.get(FAMILY_ID)["flow"] == "pending_weight_action_choice"

    update_llm = _FakeLLMClient(response_text="UPDATE")
    reply3 = router.handle_message(fake_db, store, FAMILY_ID, "改一下", llm_client=update_llm)
    assert store.get(FAMILY_ID) == {
        "flow": "pending_weight_value", "target_user_id": user_id, "weight_date": date(2026, 8, 1), "weight_id": log_id,
    }

    reply4 = router.handle_message(fake_db, store, FAMILY_ID, "78")
    assert "78.0 公斤" in reply4
    row = fake_db.select("body_weight_logs", where="id = %s", params=(log_id,), fetch_one=True)
    assert row["weight_kg"] == 78.0


def test_log_exercise_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "我要記錄運動")
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_activity"

    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "跑步")
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_duration"

    reply3 = router.handle_message(fake_db, store, FAMILY_ID, "30")
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_heart_rate"

    calorie_llm = _FakeLLMClient(response_text="約 300 大卡")
    reply4 = router.handle_message(fake_db, store, FAMILY_ID, "沒有", llm_client=calorie_llm)
    assert "300 大卡" in reply4
    assert store.get(FAMILY_ID) is None


def test_my_exercise_logs_full_flow_delete(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    log_id = commands.body.create_exercise_log(fake_db, user_id, "跑步", 30, None, 300.0, date(2026, 8, 4))
    store = ConversationStateStore()

    router.handle_message(fake_db, store, FAMILY_ID, "我的運動紀錄")
    router.handle_message(fake_db, store, FAMILY_ID, "1")

    delete_llm = _FakeLLMClient(response_text="DELETE")
    reply = router.handle_message(fake_db, store, FAMILY_ID, "刪掉", llm_client=delete_llm)
    assert "沒辦法復原" in reply

    confirm_llm = _FakeLLMClient(response_text="CONFIRM")
    reply = router.handle_message(fake_db, store, FAMILY_ID, "對", llm_client=confirm_llm)
    assert "已經刪除" in reply
    assert fake_db.select("exercise_logs", where="id = %s", params=(log_id,), fetch_one=True) is None


def test_log_diet_food_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_message(fake_db, store, FAMILY_ID, "我要記錄飲食")
    assert store.get(FAMILY_ID)["flow"] == "pending_diet_entry_type"

    router.handle_message(fake_db, store, FAMILY_ID, "飲食")
    assert store.get(FAMILY_ID)["flow"] == "pending_diet_description"

    macro_llm = _FakeLLMClient(response_text="CALORIES: 320\nPROTEIN: 20\nCARBS: 40\nFAT: 10")
    reply = router.handle_message(fake_db, store, FAMILY_ID, "雞胸肉便當", llm_client=macro_llm)
    assert "熱量約 320 大卡" in reply
    row = fake_db.select("diet_logs", where="user_id = %s", params=(user_id,))[0]
    assert row["description"] == "雞胸肉便當"


def test_log_diet_water_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_message(fake_db, store, FAMILY_ID, "我要記錄飲食")
    router.handle_message(fake_db, store, FAMILY_ID, "飲水")
    reply = router.handle_message(fake_db, store, FAMILY_ID, "500")

    assert "500 毫升" in reply
    assert store.get(FAMILY_ID) is None


def test_set_body_goal_weight_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_message(fake_db, store, FAMILY_ID, "我要設定體態管理目標")
    assert store.get(FAMILY_ID)["flow"] == "pending_goal_type"

    router.handle_message(fake_db, store, FAMILY_ID, "體重")
    assert store.get(FAMILY_ID)["flow"] == "pending_goal_weight_value"

    router.handle_message(fake_db, store, FAMILY_ID, "60")
    assert store.get(FAMILY_ID)["flow"] == "pending_goal_deadline"

    deadline_llm = _FakeLLMClient(response_text="STATUS: NO_DEADLINE")
    reply = router.handle_message(fake_db, store, FAMILY_ID, "沒有", llm_client=deadline_llm)

    assert "目標體重 60.0 公斤" in reply
    assert store.get(FAMILY_ID) is None
    goal = fake_db.select("body_goals", where="user_id = %s", params=(user_id,))[0]
    assert goal["goal_type"] == "weight"


def test_my_body_goals_full_flow_cancel(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    goal_id = commands.body.create_goal(fake_db, user_id, "exercise", "累積運動 300 分鐘", target_value=300)
    store = ConversationStateStore()

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "我的體態目標")
    assert "累積運動 300 分鐘" in reply1

    router.handle_message(fake_db, store, FAMILY_ID, "1")
    assert store.get(FAMILY_ID)["flow"] == "pending_goal_cancel_confirm"

    confirm_llm = _FakeLLMClient(response_text="CONFIRM")
    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "對", llm_client=confirm_llm)

    assert "已經取消" in reply2
    goal = fake_db.select("body_goals", where="id = %s", params=(goal_id,), fetch_one=True)
    assert goal["status"] == "cancelled"
