from src.bot import menu


def test_build_main_menu_keyboard_for_non_owner_excludes_owner_only_items():
    keyboard = menu.build_main_menu_keyboard(is_owner=False)
    keys = [button[0]["callback_data"] for button in keyboard["inline_keyboard"]]

    assert "menu:daily_log" in keys
    assert "menu:rule" in keys
    assert "menu:permission" not in keys
    assert "menu:tech_intel" not in keys
    assert "menu:job_search" not in keys
    assert "menu:certificate" not in keys
    assert "menu:recovered" not in keys


def test_build_main_menu_keyboard_for_owner_includes_all_items():
    keyboard = menu.build_main_menu_keyboard(is_owner=True)
    keys = [button[0]["callback_data"] for button in keyboard["inline_keyboard"]]

    assert keys == [f"menu:{item['key']}" for item in menu.MAIN_MENU_ITEMS]


def test_build_main_menu_keyboard_one_button_per_row():
    keyboard = menu.build_main_menu_keyboard(is_owner=True)
    assert all(len(row) == 1 for row in keyboard["inline_keyboard"])


def test_back_to_main_menu_keyboard_has_single_button():
    keyboard = menu.back_to_main_menu_keyboard()
    assert keyboard == {"inline_keyboard": [[{"text": "🔙 返回主選單", "callback_data": "menu:main"}]]}


def test_is_valid_menu_key():
    assert menu.is_valid_menu_key("permission") is True
    assert menu.is_valid_menu_key("not-a-real-key") is False


def test_is_owner_only_key():
    assert menu.is_owner_only_key("permission") is True
    assert menu.is_owner_only_key("daily_log") is False
    # 找不到的 key 保守視為需要授權，避免偽造 callback_data 繞過權限檢查
    assert menu.is_owner_only_key("not-a-real-key") is True


def test_is_not_yet_implemented():
    """2026-08-16（Phase 6 第二批 2c／2d）：daily_log、collections 已接上真正邏輯，從
    「開發中」名單移除。"""
    assert menu.is_not_yet_implemented("daily_log") is False
    assert menu.is_not_yet_implemented("collections") is False
    assert menu.is_not_yet_implemented("query") is True
    assert menu.is_not_yet_implemented("rule") is False
    assert menu.is_not_yet_implemented("permission") is False


def test_daily_log_menu_items_and_not_yet_implemented_split():
    assert [item["key"] for item in menu.DAILY_LOG_MENU_ITEMS] == ["mood", "exercise", "diet", "body", "finance"]
    assert menu.is_valid_daily_log_key("mood") is True
    assert menu.is_valid_daily_log_key("invalid_key") is False
    assert menu.is_daily_log_not_yet_implemented("mood") is False
    assert menu.is_daily_log_not_yet_implemented("exercise") is False
    for key in ("diet", "body", "finance"):
        assert menu.is_daily_log_not_yet_implemented(key) is True


def test_daily_log_not_yet_implemented_reply_points_back_to_daily_log_menu():
    text, keyboard = menu.daily_log_not_yet_implemented_reply()
    assert "開發中" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "menu:daily_log"


def test_not_yet_implemented_reply_includes_back_button():
    text, keyboard = menu.not_yet_implemented_reply()
    assert "開發中" in text
    assert keyboard == menu.back_to_main_menu_keyboard()
