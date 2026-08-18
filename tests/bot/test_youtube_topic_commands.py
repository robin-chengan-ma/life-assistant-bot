"""src/bot/commands.py 的 YouTube 技術情報主題管理流程單元測試
（對應 robinson SPEC.md FR-57a、ADR-21，Step 3.4；2026-08-18 Youtube 技術分享設定選單化，見
docs/ADR/discuss/robinson.md、docs/ADR/discuss/youtube-intel.md 對應日期條目）。

主題新增/移除全面改選單觸發：新增維持單輪自由文字輸入（`youtube_settings:add` 進入、達
`youtube.MAX_TOPICS` 上限時擋下），移除比照 collections.py 改成「選主題→按鈕二次確認」，
不再是打編號直接刪除。測試風格沿用 tests/bot/test_collections.py：用共用的 `fake_db` fixture，
斷言 state_store 與 fake_db 資料列的變化。
"""
from src.bot import commands, youtube
from src.bot.state import ConversationStateStore

TELEGRAM_USER_ID = 999
USER_ID = 1


def _seed_topic(fake_db, **overrides):
    row = {"user_id": USER_ID, "topic": "AI Agent", "last_recommended_on": None}
    row.update(overrides)
    return fake_db.insert("youtube_topics", row)


# --- start_youtube_settings_menu（子選單首頁） ---


def test_start_youtube_settings_menu_empty_shows_add_only(fake_db):
    text, keyboard = commands.start_youtube_settings_menu(fake_db, USER_ID)

    assert "還沒有設定" in text
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "youtube_settings:add" in callback_datas
    assert "youtube_settings:remove" not in callback_datas


def test_start_youtube_settings_menu_lists_topics_with_numbers(fake_db):
    _seed_topic(fake_db, topic="後端架構")
    _seed_topic(fake_db, topic="DevOps")

    text, keyboard = commands.start_youtube_settings_menu(fake_db, USER_ID)

    assert "1. 後端架構" in text
    assert "2. DevOps" in text
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "youtube_settings:add" in callback_datas
    assert "youtube_settings:remove" in callback_datas


def test_start_youtube_settings_menu_only_this_user(fake_db):
    _seed_topic(fake_db, user_id=2, topic="別人的主題")

    text, _keyboard = commands.start_youtube_settings_menu(fake_db, USER_ID)

    assert "還沒有設定" in text


def test_start_youtube_settings_menu_hides_add_button_at_limit(fake_db):
    for index in range(youtube.MAX_TOPICS):
        _seed_topic(fake_db, topic=f"主題{index}")

    _text, keyboard = commands.start_youtube_settings_menu(fake_db, USER_ID)

    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "youtube_settings:add" not in callback_datas
    assert "youtube_settings:remove" in callback_datas


# --- start_youtube_topic_add / handle_youtube_topic_add_step ---


def test_start_youtube_topic_add_sets_state(fake_db):
    state_store = ConversationStateStore()

    reply, keyboard = commands.start_youtube_topic_add(fake_db, state_store, TELEGRAM_USER_ID, USER_ID)

    assert "主題" in reply
    assert keyboard is None
    assert state_store.get(TELEGRAM_USER_ID) == {"flow": "youtube_topic_add", "target_user_id": USER_ID}


def test_start_youtube_topic_add_blocked_at_limit(fake_db):
    for index in range(youtube.MAX_TOPICS):
        _seed_topic(fake_db, topic=f"主題{index}")
    state_store = ConversationStateStore()

    reply, _keyboard = commands.start_youtube_topic_add(fake_db, state_store, TELEGRAM_USER_ID, USER_ID)

    assert "已達上限" in reply
    assert state_store.get(TELEGRAM_USER_ID) is None


def test_handle_youtube_topic_add_step_empty_reprompts(fake_db):
    state_store = ConversationStateStore()
    commands.start_youtube_topic_add(fake_db, state_store, TELEGRAM_USER_ID, USER_ID)

    reply, keyboard = commands.handle_youtube_topic_add_step(fake_db, state_store, TELEGRAM_USER_ID, "   ")

    assert "沒看懂" in reply
    assert keyboard is None
    assert state_store.get(TELEGRAM_USER_ID)["flow"] == "youtube_topic_add"


def test_handle_youtube_topic_add_step_inserts_and_clears_state(fake_db):
    state_store = ConversationStateStore()
    commands.start_youtube_topic_add(fake_db, state_store, TELEGRAM_USER_ID, USER_ID)

    reply, _keyboard = commands.handle_youtube_topic_add_step(fake_db, state_store, TELEGRAM_USER_ID, "AI Agent")

    assert "AI Agent" in reply
    assert "新增" in reply
    assert state_store.get(TELEGRAM_USER_ID) is None
    rows = fake_db.select("youtube_topics", where="user_id = %s", params=(USER_ID,))
    assert [r["topic"] for r in rows] == ["AI Agent"]


def test_handle_youtube_topic_add_step_already_exists(fake_db):
    _seed_topic(fake_db, topic="AI Agent")
    state_store = ConversationStateStore()
    commands.start_youtube_topic_add(fake_db, state_store, TELEGRAM_USER_ID, USER_ID)

    reply, _keyboard = commands.handle_youtube_topic_add_step(fake_db, state_store, TELEGRAM_USER_ID, "AI Agent")

    assert "已經在" in reply
    assert len(fake_db.select("youtube_topics", where="user_id = %s", params=(USER_ID,))) == 1
    assert state_store.get(TELEGRAM_USER_ID) is None


def test_handle_youtube_topic_add_step_limit_reached_does_not_insert(fake_db):
    for index in range(youtube.MAX_TOPICS):
        _seed_topic(fake_db, topic=f"主題{index}")
    state_store = ConversationStateStore()
    # 直接把狀態設進去，模擬「新增流程開始後、其他管道把主題數量衝到上限」這個邊界情境，
    # 驗證 handle_youtube_topic_add_step 本身也會擋下（不是只有 start_youtube_topic_add 擋）。
    state_store.set(TELEGRAM_USER_ID, {"flow": "youtube_topic_add", "target_user_id": USER_ID})

    reply, _keyboard = commands.handle_youtube_topic_add_step(fake_db, state_store, TELEGRAM_USER_ID, "新主題")

    assert "已達上限" in reply
    assert state_store.get(TELEGRAM_USER_ID) is None
    rows = fake_db.select("youtube_topics", where="user_id = %s", params=(USER_ID,))
    assert len(rows) == youtube.MAX_TOPICS
    assert "新主題" not in [r["topic"] for r in rows]


# --- start_youtube_topic_remove_menu ---


def test_start_youtube_topic_remove_menu_empty(fake_db):
    reply, keyboard = commands.start_youtube_topic_remove_menu(fake_db, USER_ID)

    assert "沒有可以移除" in reply
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert callback_datas == ["menu:main"]


def test_start_youtube_topic_remove_menu_lists_select_buttons(fake_db):
    topic_id = _seed_topic(fake_db, topic="AI Agent")

    reply, keyboard = commands.start_youtube_topic_remove_menu(fake_db, USER_ID)

    assert "請選擇要移除的主題" in reply
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert f"youtube_settings:remove_select:{topic_id}" in callback_datas
    assert "youtube_settings:menu" in callback_datas


# --- start_youtube_topic_remove_confirm / handle_youtube_topic_remove_confirmed（二次確認）---


def test_start_youtube_topic_remove_confirm_sets_state_and_asks(fake_db):
    topic_id = _seed_topic(fake_db, topic="AI Agent")
    state_store = ConversationStateStore()

    reply, keyboard = commands.start_youtube_topic_remove_confirm(
        fake_db, state_store, TELEGRAM_USER_ID, USER_ID, topic_id
    )

    assert "確定要移除「AI Agent」嗎" in reply
    assert state_store.get(TELEGRAM_USER_ID) == {"flow": "youtube_topic_remove_confirm", "target_id": topic_id}
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert f"youtube_settings:confirm_remove:{topic_id}" in callback_datas
    assert "youtube_settings:menu" in callback_datas


def test_start_youtube_topic_remove_confirm_nonexistent_topic(fake_db):
    state_store = ConversationStateStore()

    reply, _keyboard = commands.start_youtube_topic_remove_confirm(
        fake_db, state_store, TELEGRAM_USER_ID, USER_ID, 999
    )

    assert "找不到" in reply
    assert state_store.get(TELEGRAM_USER_ID) is None


def test_handle_youtube_topic_remove_confirm_text_only_accepts_button_and_cancels(fake_db):
    topic_id = _seed_topic(fake_db, topic="AI Agent")
    state_store = ConversationStateStore()
    state_store.set(TELEGRAM_USER_ID, {"flow": "youtube_topic_remove_confirm", "target_id": topic_id})

    reply, _keyboard = commands.handle_youtube_topic_remove_confirm_text(state_store, TELEGRAM_USER_ID)

    assert "請用上面的按鈕" in reply
    assert state_store.get(TELEGRAM_USER_ID) is None
    # 打字視為取消，不應該真的刪除。
    assert len(fake_db.select("youtube_topics", where="user_id = %s", params=(USER_ID,))) == 1


def test_handle_youtube_topic_remove_confirmed_deletes_selected(fake_db):
    topic_id = _seed_topic(fake_db, topic="AI Agent")
    _seed_topic(fake_db, topic="DevOps")
    state_store = ConversationStateStore()
    commands.start_youtube_topic_remove_confirm(fake_db, state_store, TELEGRAM_USER_ID, USER_ID, topic_id)

    reply, keyboard = commands.handle_youtube_topic_remove_confirmed(
        fake_db, state_store, TELEGRAM_USER_ID, USER_ID, topic_id
    )

    assert "已移除主題：「AI Agent」" in reply
    assert state_store.get(TELEGRAM_USER_ID) is None
    remaining = fake_db.select("youtube_topics", where="user_id = %s", params=(USER_ID,))
    assert [r["topic"] for r in remaining] == ["DevOps"]
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "youtube_settings:remove" in callback_datas
