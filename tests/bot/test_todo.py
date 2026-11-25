"""src/bot/todo.py 的單元測試。

2026-11（功能大幅精簡）：待辦事項改為純粹的一次性日期＋文字提醒，沒有 status／完成/取消/逾期，
這裡只測試清單查詢、格式化、以及推播去重邏輯。
"""
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from src.bot import todo


def _insert_todo(fake_db, user_id, content, remind_at, reminded_sent_at=None):
    return fake_db.insert(
        "todos",
        {
            "user_id": user_id,
            "content": content,
            "remind_at": remind_at,
            "reminded_sent_at": reminded_sent_at,
        },
    )


def test_list_todos_sorted_by_remind_at(fake_db):
    _insert_todo(fake_db, 1, "晚一點的", datetime(2026, 8, 5, tzinfo=UTC))
    _insert_todo(fake_db, 1, "早一點的", datetime(2026, 8, 1, tzinfo=UTC))

    rows = todo.list_todos(fake_db, 1)

    assert [row["content"] for row in rows] == ["早一點的", "晚一點的"]


def test_format_todo_list_empty():
    assert "沒有待辦提醒" in todo.format_todo_list([])


def test_format_todo_list_includes_content_and_time():
    text = todo.format_todo_list([{"content": "買菜", "remind_at": datetime(2026, 8, 1, 15, 0, tzinfo=UTC)}])
    assert "買菜" in text


def test_check_and_push_reminders_sends_when_due(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "測試家人", "is_owner": False})
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    _insert_todo(fake_db, user_id, "買菜", now + timedelta(minutes=10))
    telegram_client = Mock()

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()
    _, kwargs = telegram_client.send_text.call_args
    assert kwargs["chat_id"] == 111
    assert "買菜" in kwargs["text"]


def test_check_and_push_reminders_skips_already_sent(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "測試家人", "is_owner": False})
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    _insert_todo(fake_db, user_id, "買菜", now + timedelta(minutes=10), reminded_sent_at=now - timedelta(hours=1))
    telegram_client = Mock()

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_reminders_skips_not_due_yet(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "測試家人", "is_owner": False})
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    _insert_todo(fake_db, user_id, "買菜", now + timedelta(hours=5))
    telegram_client = Mock()

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_reminders_skips_unbound_user(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": None, "role": "待綁定", "is_owner": False})
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    _insert_todo(fake_db, user_id, "買菜", now + timedelta(minutes=10))
    telegram_client = Mock()

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_reminders_does_not_duplicate_after_sending(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "測試家人", "is_owner": False})
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    _insert_todo(fake_db, user_id, "買菜", now + timedelta(minutes=10))
    telegram_client = Mock()

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)
    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()
