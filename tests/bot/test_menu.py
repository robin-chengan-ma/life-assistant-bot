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
    assert menu.is_not_yet_implemented("daily_log") is True
    assert menu.is_not_yet_implemented("rule") is False
    assert menu.is_not_yet_implemented("permission") is False


def test_not_yet_implemented_reply_includes_back_button():
    text, keyboard = menu.not_yet_implemented_reply()
    assert "開發中" in text
    assert keyboard == menu.back_to_main_menu_keyboard()
