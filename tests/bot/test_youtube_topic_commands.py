"""src/bot/commands.py 的 YouTube 技術情報主題管理流程單元測試
（對應 robinson SPEC.md FR-57a、ADR-21，Step 3.4）。"""
from src.bot import commands
from src.bot.state import ConversationStateStore


def _seed_topic(fake_db, **overrides):
    row = {"user_id": 1, "topic": "AI Agent", "last_recommended_on": None}
    row.update(overrides)
    return fake_db.insert("youtube_topics", row)


# --- handle_my_youtube_topics ---


def test_handle_my_youtube_topics_empty(fake_db):
    reply = commands.handle_my_youtube_topics(fake_db, 1)
    assert "還沒有設定" in reply


def test_handle_my_youtube_topics_lists_with_numbers(fake_db):
    _seed_topic(fake_db, topic="後端架構")
    _seed_topic(fake_db, topic="DevOps")

    reply = commands.handle_my_youtube_topics(fake_db, 1)

    assert "1. 後端架構" in reply
    assert "2. DevOps" in reply


def test_handle_my_youtube_topics_only_this_user(fake_db):
    _seed_topic(fake_db, user_id=2, topic="別人的主題")

    reply = commands.handle_my_youtube_topics(fake_db, 1)

    assert "還沒有設定" in reply


# --- start_add_youtube_topic / handle_youtube_topic_add_step ---


def test_start_add_youtube_topic_sets_state(fake_db):
    state_store = ConversationStateStore()
    reply = commands.start_add_youtube_topic(state_store, 999, 1)

    assert "主題" in reply
    assert state_store.get(999) == {"flow": "pending_youtube_topic_add", "target_user_id": 1}


def test_handle_youtube_topic_add_step_empty_reprompts(fake_db):
    state_store = ConversationStateStore()
    commands.start_add_youtube_topic(state_store, 999, 1)

    reply = commands.handle_youtube_topic_add_step(fake_db, state_store, 999, "   ")

    assert "沒看懂" in reply
    assert state_store.get(999)["flow"] == "pending_youtube_topic_add"


def test_handle_youtube_topic_add_step_inserts_and_clears_state(fake_db):
    state_store = ConversationStateStore()
    commands.start_add_youtube_topic(state_store, 999, 1)

    reply = commands.handle_youtube_topic_add_step(fake_db, state_store, 999, "AI Agent")

    assert "AI Agent" in reply
    assert "新增" in reply
    assert state_store.get(999) is None
    rows = fake_db.select("youtube_topics", where="user_id = %s", params=(1,))
    assert [r["topic"] for r in rows] == ["AI Agent"]


def test_handle_youtube_topic_add_step_already_exists(fake_db):
    _seed_topic(fake_db, topic="AI Agent")
    state_store = ConversationStateStore()
    commands.start_add_youtube_topic(state_store, 999, 1)

    reply = commands.handle_youtube_topic_add_step(fake_db, state_store, 999, "AI Agent")

    assert "已經在" in reply
    assert len(fake_db.select("youtube_topics", where="user_id = %s", params=(1,))) == 1


# --- start_remove_youtube_topic / handle_youtube_topic_remove_step ---


def test_start_remove_youtube_topic_empty(fake_db):
    state_store = ConversationStateStore()
    reply = commands.start_remove_youtube_topic(fake_db, state_store, 999, 1)

    assert "還沒有設定" in reply
    assert state_store.get(999) is None


def test_start_remove_youtube_topic_lists_and_sets_state(fake_db):
    topic_id = _seed_topic(fake_db, topic="AI Agent")
    state_store = ConversationStateStore()

    reply = commands.start_remove_youtube_topic(fake_db, state_store, 999, 1)

    assert "1. AI Agent" in reply
    assert "編號" in reply
    state = state_store.get(999)
    assert state["flow"] == "pending_youtube_topic_remove"
    assert state["topic_ids"] == [topic_id]


def test_handle_youtube_topic_remove_step_exit_phrase(fake_db):
    _seed_topic(fake_db)
    state_store = ConversationStateStore()
    commands.start_remove_youtube_topic(fake_db, state_store, 999, 1)

    reply = commands.handle_youtube_topic_remove_step(fake_db, state_store, 999, "結束")

    assert "結束" in reply
    assert state_store.get(999) is None
    assert len(fake_db.select("youtube_topics")) == 1


def test_handle_youtube_topic_remove_step_invalid_number_reprompts(fake_db):
    _seed_topic(fake_db)
    state_store = ConversationStateStore()
    commands.start_remove_youtube_topic(fake_db, state_store, 999, 1)

    reply = commands.handle_youtube_topic_remove_step(fake_db, state_store, 999, "9")

    assert "1～1" in reply
    assert state_store.get(999)["flow"] == "pending_youtube_topic_remove"


def test_handle_youtube_topic_remove_step_deletes_selected(fake_db):
    topic_id = _seed_topic(fake_db, topic="AI Agent")
    _seed_topic(fake_db, topic="DevOps")
    state_store = ConversationStateStore()
    commands.start_remove_youtube_topic(fake_db, state_store, 999, 1)

    reply = commands.handle_youtube_topic_remove_step(fake_db, state_store, 999, "1")

    assert "移除" in reply
    assert state_store.get(999) is None
    remaining = fake_db.select("youtube_topics", where="user_id = %s", params=(1,))
    assert [r["id"] for r in remaining] != [topic_id]
    assert len(remaining) == 1
