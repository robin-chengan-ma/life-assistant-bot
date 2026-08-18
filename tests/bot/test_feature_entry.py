from src.bot import feature_entry, router
from src.bot.state import ConversationStateStore

FAMILY_ID = 22222


def test_detects_fixed_alias_without_llm_guessing():
    entry = feature_entry.detect("我要記帳", is_owner=False)
    assert entry is not None
    assert entry.callback_data == "daily_log:finance"


def test_does_not_fuzzily_match_unregistered_sentence():
    assert feature_entry.detect("我最近好像花太多錢了", is_owner=False) is None


def test_owner_only_alias_is_hidden_from_regular_user():
    assert feature_entry.detect("求職設定", is_owner=False) is None
    assert feature_entry.detect("求職設定", is_owner=True).key == "job_search"


def test_confirmation_only_opens_menu_after_button_click():
    entry = feature_entry.detect("新增待辦", is_owner=False)
    text, keyboard = feature_entry.confirmation(entry)

    assert "要進入" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "feature_entry:open:todo"


def test_natural_language_entry_asks_before_opening_menu(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    text, keyboard = router.handle_message(fake_db, store, FAMILY_ID, "我要記帳")

    assert text == "要進入「記帳」功能嗎？"
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "feature_entry:open:finance"
    assert store.get(FAMILY_ID) is None


def test_switching_feature_with_draft_requires_three_way_choice(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(
        FAMILY_ID,
        {"flow": "pending_transaction_amount", "transaction_type": "expense"},
    )

    text, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "menu:todo")

    assert "未送出草稿" in text
    callbacks = [row[0]["callback_data"] for row in keyboard["inline_keyboard"]]
    assert callbacks == ["draft:switch_keep", "draft:switch_discard", "draft:switch_continue"]
    assert store.get_draft(FAMILY_ID, "finance") is not None


def test_reentering_feature_shows_draft_summary_and_resume_choice(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.save_draft(FAMILY_ID, "finance", {"flow": "pending_transaction_amount", "amount": "120"})

    text, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "daily_log:finance")

    assert "amount: 120" in text
    callbacks = [row[0]["callback_data"] for row in keyboard["inline_keyboard"]]
    assert callbacks == ["draft:resume", "draft:discard"]
