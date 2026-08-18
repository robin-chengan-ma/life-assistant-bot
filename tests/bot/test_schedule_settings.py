from src.bot import schedule_settings


def _callbacks(keyboard):
    return [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]


def test_general_user_only_sees_own_schedule_entry():
    text, keyboard = schedule_settings.start_menu(is_owner=False)

    assert "功能開關與排程設定" in text
    assert _callbacks(keyboard) == ["schedule:notifications", "menu:main"]


def test_owner_sees_feature_notifications_and_system_jobs():
    _text, keyboard = schedule_settings.start_menu(is_owner=True)

    assert _callbacks(keyboard) == [
        "schedule:features",
        "schedule:notifications",
        "schedule:system",
        "menu:main",
    ]


def test_feature_menu_only_contains_three_owner_features(fake_db):
    fake_db.insert("users", {"id": 1, "is_owner": True})

    text, keyboard = schedule_settings.feature_menu(fake_db, 1)

    assert "技術分享：✅ 開啟" in text
    assert "求職設定：✅ 開啟" in text
    assert "考試設定：✅ 開啟" in text
    assert _callbacks(keyboard)[:3] == [
        "schedule:feature:tech_intel",
        "schedule:feature:job_search",
        "schedule:feature:certificate",
    ]


def test_toggle_feature_updates_existing_owner_toggle(fake_db):
    fake_db.insert("feature_toggles", {"user_id": 1, "feature_key": "tech_intel", "is_enabled": True})

    schedule_settings.toggle_feature(fake_db, 1, "tech_intel")

    row = fake_db.select(
        "feature_toggles", where="user_id = %s AND feature_key = %s", params=(1, "tech_intel"), fetch_one=True
    )
    assert row["is_enabled"] is False


def test_system_jobs_are_owner_read_only():
    text, keyboard = schedule_settings.system_jobs_menu()

    assert "Neon 容量監控：每 10 分鐘" in text
    assert "目標摘要生成：每日 01:00" in text
    assert "未記帳提醒" not in text
    assert "未完成考題提醒" not in text
    assert _callbacks(keyboard) == ["menu:schedule"]


def test_general_notification_menu_excludes_owner_only_schedules(fake_db):
    text, keyboard = schedule_settings.notification_menu(fake_db, 1, is_owner=False)

    assert "待辦提醒" in text
    assert "重要日子（含目標與旅遊日期）" in text
    assert "技術摘要推播" not in text
    assert "求職分析通知" not in text
    assert "考試出題通知" not in text
    assert "schedule:notification:todo" in _callbacks(keyboard)


def test_owner_notification_menu_includes_owner_schedules(fake_db):
    text, _keyboard = schedule_settings.notification_menu(fake_db, 1, is_owner=True)

    assert "技術摘要推播" in text
    assert "Youtube 推薦" in text
    assert "求職分析通知" in text
    assert "考試出題通知" in text


def test_notification_defaults_enabled_and_toggle_persists(fake_db):
    assert schedule_settings.is_notification_enabled(fake_db, 1, "monthly_report") is True

    schedule_settings.toggle_notification(fake_db, 1, "monthly_report", is_owner=False)

    assert schedule_settings.is_notification_enabled(fake_db, 1, "monthly_report") is False
