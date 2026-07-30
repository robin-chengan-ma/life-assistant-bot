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
