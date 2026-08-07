"""src/bot/commands.py 體態管理相關流程的整合測試（對應 robinson SPEC.md FR-45～FR-48，Step 2.2）。

不重複測試 src/bot/body.py 本身的純邏輯（已有 tests/bot/test_body.py 100% 覆蓋），這裡只驗證
commands.py 的對話狀態機串接是否正確（狀態轉移、反問文案、最終寫入結果）。
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


# --- 身高 ---


def test_start_set_height_asks_height(fake_db):
    store = ConversationStateStore()
    reply = commands.start_set_height(store, telegram_user_id=1, user_id=42)
    assert "身高" in reply
    assert store.get(1) == {"flow": "pending_height_value", "target_user_id": 42}


def test_handle_height_value_step_unreasonable_reprompts(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_height_value", "target_user_id": 42})

    reply = commands.handle_height_value_step(fake_db, store, telegram_user_id=1, text="300")

    assert "不太合理" in reply
    assert store.get(1) == {"flow": "pending_height_value", "target_user_id": 42}


def test_handle_height_value_step_valid_saves_and_clears(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_height_value", "target_user_id": user_id})

    reply = commands.handle_height_value_step(fake_db, store, telegram_user_id=1, text="173")

    assert "173.0 公分" in reply
    assert store.get(1) is None
    assert commands.body.get_height(fake_db, user_id) == 173.0


# --- 體重 ---


def test_start_weight_log_sets_today_date(monkeypatch, fake_db):
    monkeypatch.setattr(commands, "_now", lambda: commands.datetime(2026, 8, 4, 9, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    reply = commands.start_weight_log(store, telegram_user_id=1, user_id=42)
    assert "體重" in reply
    assert store.get(1) == {
        "flow": "pending_weight_value", "target_user_id": 42, "weight_date": date(2026, 8, 4), "weight_id": None,
    }


def test_handle_weight_value_step_unreasonable_reprompts(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_weight_value", "target_user_id": 42, "weight_date": date(2026, 8, 4), "weight_id": None})

    reply = commands.handle_weight_value_step(fake_db, store, telegram_user_id=1, text="10")

    assert "不太合理" in reply
    assert store.get(1) is not None


def test_handle_weight_value_step_valid_creates_row_with_bmi_and_goal_message(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False, "height_cm": 173.0})
    commands.body.create_goal(fake_db, user_id, "weight", "瘦到 78 公斤", target_value=78, baseline_value=80)
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_weight_value", "target_user_id": user_id, "weight_date": date(2026, 8, 4), "weight_id": None})

    reply = commands.handle_weight_value_step(fake_db, store, telegram_user_id=1, text="77")

    assert "77.0 公斤" in reply
    assert "BMI" in reply
    assert "恭喜" in reply
    assert store.get(1) is None


def test_handle_weight_backfill_date_step_clear_moves_to_weight_value(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: commands.datetime(2026, 8, 4, 9, 0, tzinfo=commands._TAIWAN_TZ))
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_weight_backfill_date", "target_user_id": 42})
    llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nDATE: 2026-08-01")

    reply = commands.handle_weight_backfill_date_step(llm_client, store, telegram_user_id=1, text="8/1")

    assert "體重" in reply
    assert store.get(1) == {
        "flow": "pending_weight_value", "target_user_id": 42, "weight_date": date(2026, 8, 1), "weight_id": None,
    }


def test_weight_list_update_delete_flow(fake_db):
    log_id = commands.body.create_weight_log(fake_db, 42, 80.0, date(2026, 8, 1))
    store = ConversationStateStore()

    reply = commands.start_weight_list(fake_db, store, telegram_user_id=1, user_id=42)
    assert "80.0 公斤" in reply
    assert store.get(1)["flow"] == "pending_weight_list_action"

    reply = commands.handle_weight_list_action_step(store, telegram_user_id=1, text="1")
    assert "更新" in reply and "刪除" in reply
    assert store.get(1) == {"flow": "pending_weight_action_choice", "target_user_id": 42, "weight_log_id": log_id}

    llm_client = _FakeLLMClient(response_text="DELETE")
    reply = commands.handle_weight_action_choice_step(fake_db, llm_client, store, telegram_user_id=1, text="刪掉")
    assert "沒辦法復原" in reply

    llm_client = _FakeLLMClient(response_text="CONFIRM")
    reply = commands.handle_weight_delete_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="對")
    assert "已經刪除" in reply
    assert fake_db.select("body_weight_logs", where="id = %s", params=(log_id,), fetch_one=True) is None


# --- 運動 ---


def test_exercise_full_log_flow_with_calorie_estimate(fake_db):
    store = ConversationStateStore()
    commands.start_exercise_log(store, telegram_user_id=1, user_id=42)

    reply = commands.handle_exercise_activity_step(store, telegram_user_id=1, text="跑步")
    assert "多久" in reply

    reply = commands.handle_exercise_duration_step(store, telegram_user_id=1, text="30")
    assert "心率" in reply

    llm_client = _FakeLLMClient(response_text="大約 300 大卡")
    reply = commands.handle_exercise_heart_rate_step(fake_db, llm_client, store, telegram_user_id=1, text="沒有")

    assert "300 大卡" in reply
    assert store.get(1) is None
    row = fake_db.select("exercise_logs", where="user_id = %s", params=(42,))[0]
    assert row["activity"] == "跑步"
    assert row["duration_minutes"] == 30
    assert row["heart_rate"] is None
    assert row["estimated_calories"] == 300.0


def test_handle_exercise_duration_step_invalid_reprompts(fake_db):
    store = ConversationStateStore()
    store.set(1, {"flow": "pending_exercise_activity", "target_user_id": 42, "exercise_date": date(2026, 8, 4), "exercise_id": None})
    commands.handle_exercise_activity_step(store, telegram_user_id=1, text="跑步")

    reply = commands.handle_exercise_duration_step(store, telegram_user_id=1, text="不知道")
    assert "正整數" in reply


# --- 飲食 ---


def test_diet_food_flow_estimates_macros(fake_db):
    store = ConversationStateStore()
    commands.start_diet_log(store, telegram_user_id=1, user_id=42)

    reply = commands.handle_diet_entry_type_step(store, telegram_user_id=1, text="1")
    assert "食物內容" in reply

    llm_client = _FakeLLMClient(response_text="CALORIES: 320\nPROTEIN: 20\nCARBS: 40\nFAT: 10")
    reply = commands.handle_diet_description_step(fake_db, llm_client, store, telegram_user_id=1, text="雞胸肉便當")

    assert "熱量約 320 大卡" in reply
    assert "估算值" in reply
    row = fake_db.select("diet_logs", where="user_id = %s", params=(42,))[0]
    assert row["description"] == "雞胸肉便當"
    assert row["estimated_calories"] == 320.0


def test_diet_water_flow(fake_db):
    store = ConversationStateStore()
    commands.start_diet_log(store, telegram_user_id=1, user_id=42)
    commands.handle_diet_entry_type_step(store, telegram_user_id=1, text="2")

    reply = commands.handle_diet_water_amount_step(fake_db, store, telegram_user_id=1, text="500")

    assert "500 毫升" in reply
    row = fake_db.select("diet_logs", where="user_id = %s", params=(42,))[0]
    assert row["entry_type"] == "water"
    assert row["water_ml"] == 500


# --- 體態目標 ---


def test_set_weight_goal_full_flow_with_deadline(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "爸爸", "is_owner": False})
    commands.body.create_weight_log(fake_db, user_id, 80.0, date(2026, 8, 1))
    store = ConversationStateStore()
    commands.start_body_goal(store, telegram_user_id=1, user_id=user_id)

    reply = commands.handle_goal_type_step(store, telegram_user_id=1, text="體重")
    assert "目標體重" in reply

    reply = commands.handle_goal_weight_value_step(fake_db, store, telegram_user_id=1, text="70")
    assert "完成時間" in reply
    assert store.get(1)["baseline_value"] == 80.0

    llm_client = _FakeLLMClient(response_text="STATUS: HAS_DEADLINE\nDATE: 2026-11-04")
    reply = commands.handle_goal_deadline_step(fake_db, llm_client, store, telegram_user_id=1, text="三個月內")

    # 2026-08-05 起（FR-66c、ADR-17）：有期限的目標會多問一輪是否同步，還不會直接寫入。
    assert "同步到 Google 家庭行事曆" in reply
    assert store.get(1)["flow"] == "pending_goal_calendar_sync"
    assert len(fake_db.select("body_goals", where="user_id = %s", params=(user_id,))) == 0

    llm_client.response_text = "CANCEL"
    reply = commands.handle_goal_calendar_sync_step(fake_db, llm_client, store, telegram_user_id=1, text="不用")

    assert "2026/11/04" in reply
    assert store.get(1) is None
    goal = fake_db.select("body_goals", where="user_id = %s", params=(user_id,))[0]
    assert goal["goal_type"] == "weight"
    assert goal["target_value"] == 70
    assert goal["baseline_value"] == 80.0
    assert goal["target_date"] == date(2026, 11, 4)
    assert goal["sync_to_calendar"] is False


def test_set_exercise_goal_no_deadline(fake_db):
    store = ConversationStateStore()
    commands.start_body_goal(store, telegram_user_id=1, user_id=42)
    commands.handle_goal_type_step(store, telegram_user_id=1, text="運動")

    reply = commands.handle_goal_exercise_minutes_step(store, telegram_user_id=1, text="300")
    assert "完成時間" in reply

    llm_client = _FakeLLMClient(response_text="STATUS: NO_DEADLINE")
    reply = commands.handle_goal_deadline_step(fake_db, llm_client, store, telegram_user_id=1, text="沒有")

    assert "累積運動 300 分鐘" in reply
    goal = fake_db.select("body_goals", where="user_id = %s", params=(42,))[0]
    assert goal["goal_type"] == "exercise"
    assert goal["target_value"] == 300
    assert goal["target_date"] is None


def test_goal_deadline_step_unclear_reprompts(fake_db):
    store = ConversationStateStore()
    store.set(1, {
        "flow": "pending_goal_deadline", "target_user_id": 42, "goal_type": "diet",
        "target_value": None, "baseline_value": None, "target_description": "控制飲食",
    })
    llm_client = _FakeLLMClient(response_text="STATUS: UNCLEAR")

    reply = commands.handle_goal_deadline_step(fake_db, llm_client, store, telegram_user_id=1, text="嗯…")

    assert "不太確定期限" in reply
    assert store.get(1) is not None


def test_body_goal_list_and_cancel_flow(fake_db):
    goal_id = commands.body.create_goal(fake_db, 42, "diet", "控制在每天 1800 大卡以內")
    store = ConversationStateStore()

    reply = commands.start_body_goal_list(fake_db, store, telegram_user_id=1, user_id=42)
    assert "控制在每天 1800 大卡以內" in reply

    reply = commands.handle_goal_list_action_step(fake_db, store, telegram_user_id=1, text="1")
    assert "確定要取消" in reply
    assert store.get(1) == {
        "flow": "pending_goal_cancel_confirm", "goal_id": goal_id, "google_calendar_event_id": None,
    }

    llm_client = _FakeLLMClient(response_text="CONFIRM")
    reply = commands.handle_goal_cancel_confirm_step(fake_db, llm_client, store, telegram_user_id=1, text="對，取消")

    assert "已經取消" in reply
    goal = fake_db.select("body_goals", where="id = %s", params=(goal_id,), fetch_one=True)
    assert goal["status"] == "cancelled"


# --- Google Calendar 同步（FR-66c，2026-08-05，見 ADR-17） ---


def test_handle_goal_calendar_sync_step_creates_event_when_confirmed(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_goal_calendar_sync",
            "target_user_id": 42,
            "goal_type": "weight",
            "target_description": "目標體重 70.0 公斤",
            "target_value": 70.0,
            "baseline_value": 80.0,
            "target_date": date(2026, 11, 4),
        },
    )
    llm_client = _FakeLLMClient(response_text="CONFIRM")
    calendar_client = MagicMock()
    calendar_client.create_event.return_value = "event-abc123"

    reply = commands.handle_goal_calendar_sync_step(
        fake_db, llm_client, store, telegram_user_id=1, text="要", calendar_client=calendar_client
    )

    assert "2026/11/04" in reply
    assert store.get(1) is None
    goal = fake_db.select("body_goals", where="user_id = %s", params=(42,))[0]
    assert goal["sync_to_calendar"] is True
    assert goal["google_calendar_event_id"] == "event-abc123"
    calendar_client.create_event.assert_called_once_with(
        summary="目標體重 70.0 公斤", start="2026-11-04", end="2026-11-05",
        description="來自 Robinson 體態目標", all_day=True,
    )


def test_handle_goal_calendar_sync_step_skips_event_creation_when_client_is_none(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_goal_calendar_sync",
            "target_user_id": 42,
            "goal_type": "weight",
            "target_description": "目標體重 70.0 公斤",
            "target_value": 70.0,
            "baseline_value": 80.0,
            "target_date": date(2026, 11, 4),
        },
    )
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_goal_calendar_sync_step(
        fake_db, llm_client, store, telegram_user_id=1, text="要", calendar_client=None
    )

    assert "2026/11/04" in reply
    goal = fake_db.select("body_goals", where="user_id = %s", params=(42,))[0]
    assert goal["sync_to_calendar"] is True
    assert goal.get("google_calendar_event_id") is None


def test_handle_goal_calendar_sync_step_swallows_calendar_exception(fake_db):
    store = ConversationStateStore()
    store.set(
        1,
        {
            "flow": "pending_goal_calendar_sync",
            "target_user_id": 42,
            "goal_type": "weight",
            "target_description": "目標體重 70.0 公斤",
            "target_value": 70.0,
            "baseline_value": 80.0,
            "target_date": date(2026, 11, 4),
        },
    )
    llm_client = _FakeLLMClient(response_text="CONFIRM")
    calendar_client = MagicMock()
    calendar_client.create_event.side_effect = RuntimeError("boom")

    reply = commands.handle_goal_calendar_sync_step(
        fake_db, llm_client, store, telegram_user_id=1, text="要", calendar_client=calendar_client
    )

    assert "2026/11/04" in reply
    goal = fake_db.select("body_goals", where="user_id = %s", params=(42,))[0]
    assert goal["sync_to_calendar"] is True
    assert goal.get("google_calendar_event_id") is None


def test_handle_goal_cancel_confirm_step_deletes_calendar_event_when_synced(fake_db):
    goal_id = commands.body.create_goal(fake_db, 42, "weight", "瘦到 60kg", target_value=60, baseline_value=75)
    commands.body.set_calendar_event_id(fake_db, goal_id, "event-abc123")
    store = ConversationStateStore()
    store.set(
        1,
        {"flow": "pending_goal_cancel_confirm", "goal_id": goal_id, "google_calendar_event_id": "event-abc123"},
    )
    llm_client = _FakeLLMClient(response_text="CONFIRM")
    calendar_client = MagicMock()

    commands.handle_goal_cancel_confirm_step(
        fake_db, llm_client, store, telegram_user_id=1, text="對，取消", calendar_client=calendar_client
    )

    calendar_client.delete_event.assert_called_once_with(event_id="event-abc123")
