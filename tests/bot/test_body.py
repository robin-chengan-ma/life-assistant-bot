"""src/bot/body.py 的單元測試（對應 robinson SPEC.md FR-45～FR-48，Step 2.2）。"""
from datetime import date, datetime, timezone
from unittest.mock import Mock

from src.bot import body

# --- 身高 ---


def test_is_height_reasonable_boundaries():
    assert body.is_height_reasonable(140) is True
    assert body.is_height_reasonable(200) is True
    assert body.is_height_reasonable(139.9) is False
    assert body.is_height_reasonable(200.1) is False


def test_height_range_text():
    assert body.height_range_text() == "140～200 公分"


def test_get_height_returns_none_when_user_not_found(fake_db):
    assert body.get_height(fake_db, 9999) is None


def test_set_and_get_height(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    assert body.get_height(fake_db, user_id) is None

    body.set_height(fake_db, user_id, 173.0)

    assert body.get_height(fake_db, user_id) == 173.0


# --- 腰圍（2026-08-08 追加，FR-46 擴充）---


def test_is_waist_reasonable_boundaries():
    assert body.is_waist_reasonable(50) is True
    assert body.is_waist_reasonable(150) is True
    assert body.is_waist_reasonable(49.9) is False
    assert body.is_waist_reasonable(150.1) is False


def test_waist_range_text():
    assert body.waist_range_text() == "50～150 公分"


def test_get_waist_returns_none_when_user_not_found(fake_db):
    assert body.get_waist(fake_db, 9999) is None


def test_set_and_get_waist(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    assert body.get_waist(fake_db, user_id) is None

    body.set_waist(fake_db, user_id, 80.0)

    assert body.get_waist(fake_db, user_id) == 80.0


# --- 體重與 BMI ---


def test_is_weight_reasonable():
    assert body.is_weight_reasonable(40) is True
    assert body.is_weight_reasonable(150) is True
    assert body.is_weight_reasonable(39.9) is False
    assert body.is_weight_reasonable(150.1) is False


def test_weight_range_text():
    assert body.weight_range_text() == "40～150 公斤"


def test_calculate_bmi():
    assert round(body.calculate_bmi(80, 173), 1) == 26.7


def test_classify_bmi_boundaries():
    assert body.classify_bmi(18.0) == "過輕"
    assert body.classify_bmi(20.0) == "正常"
    assert body.classify_bmi(25.0) == "過重"
    assert body.classify_bmi(28.0) == "輕度肥胖"
    assert body.classify_bmi(32.0) == "中度肥胖"
    assert body.classify_bmi(36.0) == "重度肥胖"


def test_format_bmi_note_contains_value_and_category():
    text = body.format_bmi_note(80, 173)
    assert "26.7" in text
    assert "過重" in text


def test_create_update_delete_weight_log(fake_db):
    log_id = body.create_weight_log(fake_db, user_id=1, weight_kg=75.5, entry_date=date(2026, 8, 4))
    row = fake_db.select("body_weight_logs", where="id = %s", params=(log_id,), fetch_one=True)
    assert row["weight_kg"] == 75.5
    assert row["entry_date"] == date(2026, 8, 4)

    body.update_weight_log(fake_db, log_id, 74.0)
    row = fake_db.select("body_weight_logs", where="id = %s", params=(log_id,), fetch_one=True)
    assert row["weight_kg"] == 74.0

    body.delete_weight_log(fake_db, log_id)
    assert fake_db.select("body_weight_logs", where="id = %s", params=(log_id,), fetch_one=True) is None


def test_list_and_format_weight_logs(fake_db):
    body.create_weight_log(fake_db, 1, 80.0, date(2026, 8, 1))
    body.create_weight_log(fake_db, 1, 79.0, date(2026, 8, 3))

    logs = body.list_weight_logs(fake_db, 1)
    assert [row["entry_date"] for row in logs] == [date(2026, 8, 3), date(2026, 8, 1)]

    text = body.format_weight_log_list(logs)
    assert "79.0 公斤" in text
    assert "80.0 公斤" in text


def test_format_weight_log_list_empty():
    assert "還沒有體重紀錄" in body.format_weight_log_list([])


def test_latest_weight_returns_none_when_no_logs(fake_db):
    assert body.latest_weight(fake_db, 1) is None


def test_latest_weight_returns_most_recent(fake_db):
    body.create_weight_log(fake_db, 1, 80.0, date(2026, 8, 1))
    body.create_weight_log(fake_db, 1, 78.0, date(2026, 8, 5))
    assert body.latest_weight(fake_db, 1) == 78.0


# --- 我的體態紀錄摘要（2026-08-17，FR-46）---


def test_get_body_summary_all_missing(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    summary = body.get_body_summary(fake_db, user_id)
    assert summary == {
        "height_cm": None, "weight_kg": None, "waist_cm": None, "bmi": None, "bmi_category": None,
    }


def test_get_body_summary_full(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    body.set_height(fake_db, user_id, 173.0)
    body.set_waist(fake_db, user_id, 80.0)
    body.create_weight_log(fake_db, user_id, 70.0, date(2026, 8, 1))
    body.create_weight_log(fake_db, user_id, 68.0, date(2026, 8, 10))

    summary = body.get_body_summary(fake_db, user_id)
    assert summary["height_cm"] == 173.0
    assert summary["weight_kg"] == 68.0
    assert summary["waist_cm"] == 80.0
    assert round(summary["bmi"], 1) == round(body.calculate_bmi(68.0, 173.0), 1)
    assert summary["bmi_category"] == body.classify_bmi(summary["bmi"])


def test_get_body_summary_bmi_none_without_height(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    body.create_weight_log(fake_db, user_id, 68.0, date(2026, 8, 1))
    summary = body.get_body_summary(fake_db, user_id)
    assert summary["bmi"] is None


def test_format_body_summary_all_missing():
    text = body.format_body_summary(
        {"height_cm": None, "weight_kg": None, "waist_cm": None, "bmi": None, "bmi_category": None}
    )
    assert text.count("尚無紀錄") == 3
    assert "無法計算" in text


def test_format_body_summary_full():
    text = body.format_body_summary(
        {"height_cm": 173.0, "weight_kg": 68.0, "waist_cm": 80.0, "bmi": 22.7, "bmi_category": "正常"}
    )
    assert "173.0 公分" in text
    assert "68.0 公斤" in text
    assert "80.0 公分" in text
    assert "22.7（正常）" in text


# --- 運動 ---


def test_estimate_exercise_calories_parses_number():
    llm_client = Mock()
    llm_client.generate_text.return_value = "大約 318 大卡"
    calories = body.estimate_exercise_calories(llm_client, "跑步", 30, None)
    assert calories == 318.0


def test_estimate_exercise_calories_includes_note():
    llm_client = Mock()
    llm_client.generate_text.return_value = "320"

    body.estimate_exercise_calories(
        llm_client,
        "重訓",
        45,
        130,
        note="深蹲 60 公斤 5 組，每組 8 下",
    )

    prompt = llm_client.generate_text.call_args.args[0]
    assert "深蹲 60 公斤 5 組，每組 8 下" in prompt


def test_estimate_exercise_calories_returns_none_when_unparseable():
    llm_client = Mock()
    llm_client.generate_text.return_value = "不確定"
    assert body.estimate_exercise_calories(llm_client, "跑步", 30, 140) is None


def test_estimate_exercise_calories_returns_none_on_llm_error():
    llm_client = Mock()
    llm_client.generate_text.side_effect = RuntimeError("LLM 暫時錯誤")
    assert body.estimate_exercise_calories(llm_client, "跑步", 30, None) is None


def test_create_update_delete_exercise_log(fake_db):
    log_id = body.create_exercise_log(fake_db, 1, 10, "跑步", 30, 140, None, "ai", 300.0, date(2026, 8, 4))
    row = fake_db.select("exercise_logs", where="id = %s", params=(log_id,), fetch_one=True)
    assert row["activity"] == "跑步"
    assert row["category_id"] == 10
    assert row["duration_minutes"] == 30
    assert row["heart_rate"] == 140
    assert row["estimated_calories"] == 300.0
    assert row["calorie_source"] == "ai"

    body.update_exercise_log(fake_db, log_id, 11, "游泳", 45, None, "自由式", "manual", 400.0)
    row = fake_db.select("exercise_logs", where="id = %s", params=(log_id,), fetch_one=True)
    assert row["activity"] == "游泳"
    assert row["category_id"] == 11
    assert row["duration_minutes"] == 45
    assert row["heart_rate"] is None
    assert row["note"] == "自由式"
    assert row["calorie_source"] == "manual"

    body.delete_exercise_log(fake_db, log_id)
    assert fake_db.select("exercise_logs", where="id = %s", params=(log_id,), fetch_one=True) is None


def test_list_and_format_exercise_logs(fake_db):
    body.create_exercise_log(fake_db, 1, 10, "跑步", 30, None, None, "ai", 300.0, date(2026, 8, 4))
    body.create_exercise_log(fake_db, 1, 11, "重訓", 60, None, "深蹲 5 組", "manual", None, date(2026, 8, 2))

    logs = body.list_exercise_logs(fake_db, 1)
    text = body.format_exercise_log_list(logs)
    assert "跑步 30 分鐘" in text
    assert "約 300 大卡" in text
    assert "重訓 60 分鐘" in text


def test_format_exercise_log_list_empty():
    assert "還沒有運動紀錄" in body.format_exercise_log_list([])


def test_list_exercise_categories_and_find_or_create(fake_db):
    fake_db.insert("exercise_categories", {"name": "跑步", "normalized_name": "跑步"})
    fake_db.insert("exercise_categories", {"name": "重訓", "normalized_name": "重訓"})

    categories = body.list_exercise_categories(fake_db)
    assert [item["name"] for item in categories] == ["跑步", "重訓"]

    # 正規化比對命中既有類別（trim／全形轉半形／大小寫統一）。
    matched = body.find_or_create_exercise_category(fake_db, None, "  重訓  ")
    assert matched["name"] == "重訓"
    assert len(body.list_exercise_categories(fake_db)) == 2

    # 正規化沒命中、沒有 llm_client 時直接新增。
    created = body.find_or_create_exercise_category(fake_db, None, "拳擊")
    assert created["name"] == "拳擊"
    assert len(body.list_exercise_categories(fake_db)) == 3

    # 正規化沒命中，LLM 判斷為既有類別同義詞時沿用既有類別，不新增。
    llm_client = Mock()
    llm_client.generate_text.return_value = "重訓"
    synonym_matched = body.find_or_create_exercise_category(fake_db, llm_client, "重量訓練")
    assert synonym_matched["name"] == "重訓"
    assert len(body.list_exercise_categories(fake_db)) == 3

    # LLM 回 NONE 時新增一筆。
    llm_client.generate_text.return_value = "NONE"
    new_category = body.find_or_create_exercise_category(fake_db, llm_client, "飛盤")
    assert new_category["name"] == "飛盤"
    assert len(body.list_exercise_categories(fake_db)) == 4

    # LLM 呼叫失敗時降級為新增，不擋下流程。
    llm_client.generate_text.side_effect = RuntimeError("LLM 暫時錯誤")
    fallback_category = body.find_or_create_exercise_category(fake_db, llm_client, "壁球")
    assert fallback_category["name"] == "壁球"
    assert len(body.list_exercise_categories(fake_db)) == 5


# --- 飲食/飲水 ---


def test_estimate_diet_macros_parses_all_fields():
    llm_client = Mock()
    llm_client.generate_text.return_value = "CALORIES: 320\nPROTEIN: 20\nCARBS: 40\nFAT: 10"
    macros = body.estimate_diet_macros(llm_client, "雞胸肉便當")
    assert macros == {"estimated_calories": 320.0, "protein_g": 20.0, "carbs_g": 40.0, "fat_g": 10.0}


def test_estimate_diet_macros_returns_none_fields_when_unparseable():
    llm_client = Mock()
    llm_client.generate_text.return_value = "無法判斷"
    macros = body.estimate_diet_macros(llm_client, "神秘料理")
    assert macros == {"estimated_calories": None, "protein_g": None, "carbs_g": None, "fat_g": None}


def test_estimate_diet_macros_returns_none_fields_on_llm_error():
    llm_client = Mock()
    llm_client.generate_text.side_effect = RuntimeError("LLM 暫時錯誤")
    macros = body.estimate_diet_macros(llm_client, "雞胸肉便當")
    assert all(value is None for value in macros.values())


def test_create_and_delete_food_diet_log(fake_db):
    macros = {"estimated_calories": 320.0, "protein_g": 20.0, "carbs_g": 40.0, "fat_g": 10.0}
    log_id = body.create_diet_log(fake_db, 1, "food", "雞胸肉便當", date(2026, 8, 4), macros=macros)
    row = fake_db.select("diet_logs", where="id = %s", params=(log_id,), fetch_one=True)
    assert row["description"] == "雞胸肉便當"
    assert row["estimated_calories"] == 320.0

    body.delete_diet_log(fake_db, log_id)
    assert fake_db.select("diet_logs", where="id = %s", params=(log_id,), fetch_one=True) is None


def test_create_water_diet_log(fake_db):
    log_id = body.create_diet_log(fake_db, 1, "water", "飲水", date(2026, 8, 4), water_ml=500)
    row = fake_db.select("diet_logs", where="id = %s", params=(log_id,), fetch_one=True)
    assert row["water_ml"] == 500
    assert row["estimated_calories"] is None


def test_list_and_format_diet_logs(fake_db):
    body.create_diet_log(
        fake_db, 1, "food", "雞胸肉便當", date(2026, 8, 4),
        macros={"estimated_calories": 320.0, "protein_g": None, "carbs_g": None, "fat_g": None},
    )
    body.create_diet_log(fake_db, 1, "water", "飲水", date(2026, 8, 3), water_ml=500)

    logs = body.list_diet_logs(fake_db, 1)
    text = body.format_diet_log_list(logs)
    assert "雞胸肉便當" in text
    assert "約 320 大卡" in text
    assert "飲水 500 毫升" in text


def test_format_diet_log_list_empty():
    assert "還沒有飲食紀錄" in body.format_diet_log_list([])


def test_format_diet_macro_note_with_values():
    text = body.format_diet_macro_note({"estimated_calories": 320.0, "protein_g": 20.0, "carbs_g": 40.0, "fat_g": 10.0})
    assert "熱量約 320 大卡" in text
    assert "估算值" in text


def test_format_diet_macro_note_when_all_none():
    text = body.format_diet_macro_note({"estimated_calories": None, "protein_g": None, "carbs_g": None, "fat_g": None})
    assert "沒能順利估算" in text


# --- 體態目標 ---


def test_resolve_goal_type_accepts_index_and_label():
    assert body.resolve_goal_type("1") == "weight"
    assert body.resolve_goal_type("2") == "exercise"
    assert body.resolve_goal_type("3") == "diet"
    assert body.resolve_goal_type("體重") == "weight"
    assert body.resolve_goal_type("0") is None


def test_goal_type_label():
    assert body.goal_type_label("weight") == "體重"


def test_create_list_cancel_goal(fake_db):
    goal_id = body.create_goal(
        fake_db, 1, "weight", "三個月內瘦到 60 KG", target_value=60, baseline_value=75, target_date=date(2026, 11, 4)
    )
    goals = body.list_active_goals(fake_db, 1)
    assert len(goals) == 1
    assert goals[0]["id"] == goal_id

    text = body.format_goal_list(goals)
    assert "三個月內瘦到 60 KG" in text
    assert "2026/11/04" in text

    body.cancel_goal(fake_db, goal_id)
    assert body.list_active_goals(fake_db, 1) == []


def test_format_goal_list_empty():
    assert "還沒有設定中的體態目標" in body.format_goal_list([])


def test_get_goal_returns_row(fake_db):
    goal_id = body.create_goal(fake_db, 1, "weight", "瘦到 60kg", target_value=60, baseline_value=75)
    row = body.get_goal(fake_db, goal_id)
    assert row["id"] == goal_id
    assert row["target_description"] == "瘦到 60kg"


def test_get_goal_returns_none_when_missing(fake_db):
    assert body.get_goal(fake_db, 9999) is None


def test_update_goal_overwrites_fields_and_resets_deadline_reminder(fake_db):
    goal_id = body.create_goal(
        fake_db, 1, "weight", "瘦到 60kg", target_value=60, baseline_value=75, target_date=date(2026, 9, 1)
    )
    fake_db.update("body_goals", {"deadline_reminder_sent": True}, where="id = %s", params=(goal_id,))

    body.update_goal(fake_db, goal_id, "瘦到 58kg", target_value=58, baseline_value=75, target_date=date(2026, 10, 1))

    row = body.get_goal(fake_db, goal_id)
    assert row["target_description"] == "瘦到 58kg"
    assert float(row["target_value"]) == 58
    assert row["target_date"] == date(2026, 10, 1)
    assert row["deadline_reminder_sent"] is False


# --- Google Calendar 同步（FR-66c，2026-08-05，見 ADR-17） ---


def test_create_goal_defaults_sync_to_calendar_false(fake_db):
    goal_id = body.create_goal(fake_db, 1, "weight", "瘦到 60kg", target_value=60, baseline_value=75)
    goal = fake_db.select("body_goals", where="id = %s", params=(goal_id,), fetch_one=True)
    assert goal["sync_to_calendar"] is False


def test_set_calendar_event_id_updates_row(fake_db):
    goal_id = body.create_goal(fake_db, 1, "weight", "瘦到 60kg", target_value=60, baseline_value=75)

    body.set_calendar_event_id(fake_db, goal_id, "event-abc123")

    goal = fake_db.select("body_goals", where="id = %s", params=(goal_id,), fetch_one=True)
    assert goal["google_calendar_event_id"] == "event-abc123"


def test_cancel_goal_deletes_calendar_event_when_synced(fake_db):
    goal_id = body.create_goal(fake_db, 1, "weight", "瘦到 60kg", target_value=60, baseline_value=75)
    body.set_calendar_event_id(fake_db, goal_id, "event-abc123")
    calendar_client = Mock()

    body.cancel_goal(fake_db, goal_id, calendar_client=calendar_client, google_calendar_event_id="event-abc123")

    calendar_client.delete_event.assert_called_once_with(event_id="event-abc123")


def test_cancel_goal_skips_calendar_delete_when_not_synced(fake_db):
    goal_id = body.create_goal(fake_db, 1, "weight", "瘦到 60kg", target_value=60, baseline_value=75)
    calendar_client = Mock()

    body.cancel_goal(fake_db, goal_id, calendar_client=calendar_client, google_calendar_event_id=None)

    calendar_client.delete_event.assert_not_called()


def test_cancel_goal_swallows_calendar_delete_exception(fake_db):
    goal_id = body.create_goal(fake_db, 1, "weight", "瘦到 60kg", target_value=60, baseline_value=75)
    calendar_client = Mock()
    calendar_client.delete_event.side_effect = RuntimeError("boom")

    body.cancel_goal(fake_db, goal_id, calendar_client=calendar_client, google_calendar_event_id="event-abc123")

    goal = fake_db.select("body_goals", where="id = %s", params=(goal_id,), fetch_one=True)
    assert goal["status"] == "cancelled"


def test_check_weight_goal_achieved_losing_weight(fake_db):
    body.create_goal(fake_db, 1, "weight", "瘦到 60kg", target_value=60, baseline_value=75)

    assert body.check_weight_goal_achieved(fake_db, 1, 65.0) is None
    message = body.check_weight_goal_achieved(fake_db, 1, 59.0)
    assert message is not None
    assert "恭喜" in message

    goal = fake_db.select("body_goals", where="user_id = %s", params=(1,))[0]
    assert goal["status"] == "achieved"


def test_check_weight_goal_achieved_deletes_calendar_event_when_synced(fake_db):
    # 2026-08-05（FR-66c、ADR-17）：達成時如果有同步，要刪除對應的 Calendar 事件。
    goal_id = body.create_goal(fake_db, 1, "weight", "瘦到 60kg", target_value=60, baseline_value=75)
    body.set_calendar_event_id(fake_db, goal_id, "event-abc123")
    calendar_client = Mock()

    body.check_weight_goal_achieved(fake_db, 1, 59.0, calendar_client=calendar_client)

    calendar_client.delete_event.assert_called_once_with(event_id="event-abc123")


def test_check_weight_goal_achieved_gaining_weight(fake_db):
    body.create_goal(fake_db, 1, "weight", "增重到 70kg", target_value=70, baseline_value=60)

    assert body.check_weight_goal_achieved(fake_db, 1, 65.0) is None
    assert body.check_weight_goal_achieved(fake_db, 1, 71.0) is not None


def test_check_weight_goal_achieved_ignores_goals_without_target(fake_db):
    body.create_goal(fake_db, 1, "weight", "純紀錄，沒有明確目標值")
    assert body.check_weight_goal_achieved(fake_db, 1, 50.0) is None


def test_format_goal_type_prompt_lists_all_types():
    text = body.format_goal_type_prompt()
    assert "1. 體重" in text
    assert "3. 飲食" in text


def test_check_and_push_exercise_goal_achievements_skips_goal_without_target_value(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "測試家人", "is_owner": False})
    body.create_goal(fake_db, user_id, "exercise", "純紀錄，沒有明確目標")
    telegram_client = Mock()
    body.check_and_push_exercise_goal_achievements(fake_db, telegram_client)
    telegram_client.send_text.assert_not_called()


def test_check_and_push_exercise_goal_achievements_skips_unbound_user(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": None, "role": "待綁定", "is_owner": False})
    body.create_goal(fake_db, user_id, "exercise", "這個月運動滿 60 分鐘", target_value=60)
    telegram_client = Mock()
    body.check_and_push_exercise_goal_achievements(fake_db, telegram_client)
    telegram_client.send_text.assert_not_called()


def test_check_and_push_exercise_goal_achievements(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "測試家人", "is_owner": False})
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    goal_id = body.create_goal(fake_db, user_id, "exercise", "這個月運動滿 60 分鐘", target_value=60)
    fake_db.update("body_goals", {"created_at": now}, where="id = %s", params=(goal_id,))

    body.create_exercise_log(fake_db, user_id, 1, "跑步", 30, None, None, "ai", None, date(2026, 8, 4))
    telegram_client = Mock()
    body.check_and_push_exercise_goal_achievements(fake_db, telegram_client, now=now)
    telegram_client.send_text.assert_not_called()

    body.create_exercise_log(fake_db, user_id, 2, "游泳", 40, None, None, "ai", None, date(2026, 8, 4))
    body.check_and_push_exercise_goal_achievements(fake_db, telegram_client, now=now)
    telegram_client.send_text.assert_called_once()

    goal = fake_db.select("body_goals", where="id = %s", params=(goal_id,), fetch_one=True)
    assert goal["status"] == "achieved"


def test_check_and_push_exercise_goal_achievements_deletes_calendar_event_when_synced(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "測試家人", "is_owner": False})
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    goal_id = body.create_goal(fake_db, user_id, "exercise", "這個月運動滿 60 分鐘", target_value=60)
    fake_db.update("body_goals", {"created_at": now}, where="id = %s", params=(goal_id,))
    body.set_calendar_event_id(fake_db, goal_id, "event-xyz")

    body.create_exercise_log(fake_db, user_id, 1, "跑步", 60, None, None, "ai", None, date(2026, 8, 4))
    telegram_client = Mock()
    calendar_client = Mock()
    body.check_and_push_exercise_goal_achievements(fake_db, telegram_client, now=now, calendar_client=calendar_client)

    calendar_client.delete_event.assert_called_once_with(event_id="event-xyz")


def test_check_and_push_diet_goal_achievements_min_direction(fake_db):
    """2026-08-17 補做（Robin 要求不得漏做）：MIN 方向（至少要達到）目標隨時可以判斷。"""
    user_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "測試家人", "is_owner": False})
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    goal_id = body.create_goal(
        fake_db, user_id, "diet", "每週吃蔬菜5次", target_value=5, target_unit="次", target_direction="min"
    )
    fake_db.update("body_goals", {"created_at": now}, where="id = %s", params=(goal_id,))

    for _ in range(4):
        body.create_diet_log(fake_db, user_id, "food", "蔬菜", date(2026, 8, 4))
    telegram_client = Mock()
    body.check_and_push_diet_goal_achievements(fake_db, telegram_client, now=now)
    telegram_client.send_text.assert_not_called()

    body.create_diet_log(fake_db, user_id, "food", "蔬菜", date(2026, 8, 4))
    body.check_and_push_diet_goal_achievements(fake_db, telegram_client, now=now)
    telegram_client.send_text.assert_called_once()
    assert fake_db.select("body_goals", where="id = %s", params=(goal_id,), fetch_one=True)["status"] == "achieved"


def test_check_and_push_diet_goal_achievements_max_direction_requires_deadline(fake_db):
    """2026-08-17 補做：MAX 方向（不能超過）目標沒有期限時無法判斷（數學上沒有結束邊界），
    有期限但還沒到期也先不判斷；到期後才依累計值決定是否達成。"""
    user_id = fake_db.insert("users", {"telegram_user_id": 222, "role": "測試家人", "is_owner": False})
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    goal_id = body.create_goal(
        fake_db, user_id, "diet", "這週熱量控制在1000大卡以內", target_value=1000,
        target_unit="大卡", target_direction="max",
    )
    fake_db.update("body_goals", {"created_at": now}, where="id = %s", params=(goal_id,))
    body.create_diet_log(fake_db, user_id, "food", "沙拉", date(2026, 8, 4), macros={"estimated_calories": 500})

    telegram_client = Mock()
    body.check_and_push_diet_goal_achievements(fake_db, telegram_client, now=now)
    telegram_client.send_text.assert_not_called()  # 沒有 target_date，無法判斷

    fake_db.update("body_goals", {"target_date": date(2026, 8, 10)}, where="id = %s", params=(goal_id,))
    body.check_and_push_diet_goal_achievements(fake_db, telegram_client, now=now)
    telegram_client.send_text.assert_not_called()  # 還沒到期限

    later_now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    body.check_and_push_diet_goal_achievements(fake_db, telegram_client, now=later_now)
    telegram_client.send_text.assert_called_once()
    assert fake_db.select("body_goals", where="id = %s", params=(goal_id,), fetch_one=True)["status"] == "achieved"


def test_check_and_push_diet_goal_achievements_max_direction_exceeded(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 333, "role": "測試家人", "is_owner": False})
    now = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
    goal_id = body.create_goal(
        fake_db, user_id, "diet", "這週熱量控制在1000大卡以內", target_value=1000,
        target_unit="大卡", target_direction="max", target_date=date(2026, 8, 10),
    )
    fake_db.update("body_goals", {"created_at": now}, where="id = %s", params=(goal_id,))
    body.create_diet_log(fake_db, user_id, "food", "大餐", date(2026, 8, 4), macros={"estimated_calories": 1500})

    telegram_client = Mock()
    later_now = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    body.check_and_push_diet_goal_achievements(fake_db, telegram_client, now=later_now)
    telegram_client.send_text.assert_not_called()  # 超標，沒有達成


def test_check_and_push_diet_goal_achievements_skips_goal_without_direction(fake_db):
    """未經 LLM 解析出結構化數值（`target_value`／`target_direction` 為 None）的飲食目標維持
    純文字，不做自動判斷。"""
    user_id = fake_db.insert("users", {"telegram_user_id": 444, "role": "測試家人", "is_owner": False})
    body.create_goal(fake_db, user_id, "diet", "想吃得更健康")
    telegram_client = Mock()
    body.check_and_push_diet_goal_achievements(fake_db, telegram_client)
    telegram_client.send_text.assert_not_called()
