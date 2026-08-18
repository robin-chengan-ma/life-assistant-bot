from datetime import datetime, timedelta, timezone

from src.bot.state import ConversationStateStore


def test_get_returns_none_when_no_state_exists():
    store = ConversationStateStore()
    assert store.get(12345) is None


def test_set_then_get_returns_the_same_state():
    store = ConversationStateStore()
    store.set(12345, {"step": "awaiting_role"})
    assert store.get(12345) == {"step": "awaiting_role"}


def test_set_overwrites_previous_state_for_same_user():
    store = ConversationStateStore()
    store.set(12345, {"step": "awaiting_role"})
    store.set(12345, {"step": "awaiting_code", "role": "爸爸"})
    assert store.get(12345) == {"step": "awaiting_code", "role": "爸爸"}


def test_clear_removes_state_for_user():
    store = ConversationStateStore()
    store.set(12345, {"step": "awaiting_role"})
    store.clear(12345)
    assert store.get(12345) is None


def test_clear_on_user_with_no_state_does_not_raise():
    store = ConversationStateStore()
    store.clear(99999)  # 不應丟例外
    assert store.get(99999) is None


def test_states_are_isolated_between_different_users():
    store = ConversationStateStore()
    store.set(111, {"step": "awaiting_role"})
    store.set(222, {"step": "awaiting_code", "role": "媽媽"})
    assert store.get(111) == {"step": "awaiting_role"}
    assert store.get(222) == {"step": "awaiting_code", "role": "媽媽"}


def test_active_mode_expires_after_ten_minutes_but_preserves_draft():
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    store = ConversationStateStore(now=lambda: now)
    state = {"flow": "pending_transaction_amount", "transaction_type": "expense"}
    store.set(12345, state, feature="finance", is_draft=True)

    now += timedelta(minutes=10, seconds=1)

    assert store.get(12345) is None
    assert store.get_draft(12345, "finance") == state
    assert store.pop_expired_mode(12345) == {"feature": "finance", "had_draft": True}


def test_drafts_expire_independently_after_thirty_minutes():
    now = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
    store = ConversationStateStore(now=lambda: now)
    store.save_draft(12345, "finance", {"flow": "pending_transaction_amount", "amount": "100"})
    now += timedelta(minutes=5)
    store.save_draft(12345, "todo", {"flow": "pending_todo_time", "content": "交報告"})

    now += timedelta(minutes=25, seconds=1)

    assert store.get_draft(12345, "finance") is None
    assert store.get_draft(12345, "todo") == {"flow": "pending_todo_time", "content": "交報告"}


def test_one_draft_per_feature_and_different_features_can_coexist():
    store = ConversationStateStore()
    store.save_draft(12345, "finance", {"amount": "100"})
    store.save_draft(12345, "todo", {"content": "交報告"})
    store.save_draft(12345, "finance", {"amount": "200"})

    assert store.get_draft(12345, "finance") == {"amount": "200"}
    assert store.get_draft(12345, "todo") == {"content": "交報告"}


def test_clear_after_submit_or_cancel_discards_active_draft():
    store = ConversationStateStore()
    store.set(12345, {"flow": "pending_transaction_amount"}, feature="finance", is_draft=True)

    store.clear(12345)

    assert store.get(12345) is None
    assert store.get_draft(12345, "finance") is None


def test_clear_can_preserve_draft_for_explicit_feature_switch():
    store = ConversationStateStore()
    state = {"flow": "pending_transaction_amount", "transaction_type": "expense"}
    store.set(12345, state)

    store.clear(12345, preserve_draft=True)

    assert store.get(12345) is None
    assert store.get_draft(12345, "finance") == state


def test_discard_draft_only_removes_selected_feature():
    store = ConversationStateStore()
    store.save_draft(12345, "finance", {"amount": "100"})
    store.save_draft(12345, "todo", {"content": "交報告"})

    store.discard_draft(12345, "finance")

    assert store.get_draft(12345, "finance") is None
    assert store.get_draft(12345, "todo") == {"content": "交報告"}


def test_existing_feature_flow_is_classified_without_changing_all_callers():
    store = ConversationStateStore()
    state = {"flow": "pending_transaction_amount", "transaction_type": "expense"}

    store.set(12345, state)

    assert store.active_feature(12345) == "finance"
    assert store.get_draft(12345, "finance") == state


def test_menu_or_transient_state_does_not_become_draft():
    store = ConversationStateStore()
    store.set(12345, {"flow": "pending_voice_confirm", "transcribed_text": "我要記帳"})

    assert store.active_feature(12345) is None
    assert store.get_draft(12345, "finance") is None


def test_voice_confirmation_does_not_overwrite_existing_feature_draft():
    store = ConversationStateStore()
    draft = {"flow": "pending_transaction_amount", "transaction_type": "expense"}
    store.set(12345, draft)

    store.set(12345, {"flow": "pending_voice_confirm", "resume_state": draft, "transcribed_text": "120"})

    assert store.active_feature(12345) is None
    assert store.get_draft(12345, "finance") == draft
