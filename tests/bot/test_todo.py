"""src/bot/todo.py 的單元測試（對應 robinson SPEC.md FR-31、FR-31a、FR-32，Step 1.7）。"""
from datetime import datetime, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from src.bot import todo

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def test_create_todo_inserts_pending_row(fake_db):
    todo_id = todo.create_todo(fake_db, user_id=1, content="買菜", due_at=_utc(2026, 8, 2, 7, 0), remind_before_30min=True)

    row = fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)
    assert row["user_id"] == 1
    assert row["content"] == "買菜"
    assert row["status"] == "pending"
    assert row["remind_before_30min"] is True


def test_list_pending_todos_only_returns_pending_sorted_by_due_at(fake_db):
    todo.create_todo(fake_db, 1, "晚一點", _utc(2026, 8, 2, 12, 0), False)
    todo.create_todo(fake_db, 1, "早一點", _utc(2026, 8, 2, 6, 0), False)
    cancelled_id = todo.create_todo(fake_db, 1, "已取消", _utc(2026, 8, 2, 5, 0), False)
    todo.mark_status(fake_db, cancelled_id, "cancelled")
    todo.create_todo(fake_db, 2, "別人的", _utc(2026, 8, 2, 1, 0), False)

    result = todo.list_pending_todos(fake_db, user_id=1)

    assert [item["content"] for item in result] == ["早一點", "晚一點"]


def test_format_todo_list_empty():
    assert todo.format_todo_list([]) == "目前沒有待辦事項喔！"


def test_format_todo_list_includes_index_and_local_time():
    todos = [{"content": "買菜", "due_at": _utc(2026, 8, 2, 7, 0)}]  # 台灣時間 15:00

    text = todo.format_todo_list(todos)

    assert "1. 買菜（2026/08/02 15:00）" in text


def test_mark_status_updates_row(fake_db):
    todo_id = todo.create_todo(fake_db, 1, "買菜", _utc(2026, 8, 2, 7, 0), False)

    todo.mark_status(fake_db, todo_id, "completed")

    row = fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)
    assert row["status"] == "completed"


def test_mark_overdue_as_expired_only_affects_pending_rows_past_due(fake_db):
    now = _utc(2026, 8, 2, 10, 0)
    overdue_id = todo.create_todo(fake_db, 1, "已過期", _utc(2026, 8, 2, 9, 0), False)
    future_id = todo.create_todo(fake_db, 1, "還沒到", _utc(2026, 8, 2, 11, 0), False)
    already_done_id = todo.create_todo(fake_db, 1, "已完成", _utc(2026, 8, 2, 8, 0), False)
    todo.mark_status(fake_db, already_done_id, "completed")

    affected = todo.mark_overdue_as_expired(fake_db, now=now)

    assert affected == 1
    assert fake_db.select("todos", where="id = %s", params=(overdue_id,), fetch_one=True)["status"] == "expired"
    assert fake_db.select("todos", where="id = %s", params=(future_id,), fetch_one=True)["status"] == "pending"
    assert fake_db.select("todos", where="id = %s", params=(already_done_id,), fetch_one=True)["status"] == "completed"


def test_check_and_push_reminders_sends_and_marks_reminded(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    now = _utc(2026, 8, 2, 10, 0)
    due_soon_id = todo.create_todo(fake_db, 1, "買菜", _utc(2026, 8, 2, 10, 20), True)
    telegram_client = MagicMock()

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()
    assert telegram_client.send_text.call_args.kwargs["chat_id"] == 555
    row = fake_db.select("todos", where="id = %s", params=(due_soon_id,), fetch_one=True)
    assert row["reminded_30min_sent_at"] == now


def test_check_and_push_reminders_skips_when_not_opted_in(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    now = _utc(2026, 8, 2, 10, 0)
    todo.create_todo(fake_db, 1, "買菜", _utc(2026, 8, 2, 10, 20), False)
    telegram_client = MagicMock()

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_reminders_skips_when_not_within_window(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    now = _utc(2026, 8, 2, 10, 0)
    todo.create_todo(fake_db, 1, "太早", _utc(2026, 8, 2, 15, 0), True)
    telegram_client = MagicMock()

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_reminders_does_not_repeat(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    now = _utc(2026, 8, 2, 10, 0)
    todo.create_todo(fake_db, 1, "買菜", _utc(2026, 8, 2, 10, 20), True)
    telegram_client = MagicMock()

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)
    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()


def test_check_and_push_reminders_skips_user_without_telegram_id(fake_db):
    fake_db.insert("users", {"telegram_user_id": None, "role": "家人", "is_owner": False})
    now = _utc(2026, 8, 2, 10, 0)
    todo.create_todo(fake_db, 1, "買菜", _utc(2026, 8, 2, 10, 20), True)
    telegram_client = MagicMock()

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_daily_digest_skips_outside_of_8am_window(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    # 台灣時間 09:00（UTC 01:00），不是 08 點這個小時
    now = _utc(2026, 8, 2, 1, 0)
    todo.create_todo(fake_db, 1, "買菜", _utc(2026, 8, 2, 2, 0), False)
    telegram_client = MagicMock()

    todo.check_and_push_daily_digest(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_daily_digest_sends_summary_and_marks_pushed(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    # 台灣時間 08:05（UTC 00:05）
    now = _utc(2026, 8, 2, 0, 5)
    due_today_id = todo.create_todo(fake_db, 1, "買菜", _utc(2026, 8, 2, 6, 0), False)  # 台灣 14:00
    todo.create_todo(fake_db, 1, "明天的事", _utc(2026, 8, 3, 6, 0), False)  # 不是今天
    telegram_client = MagicMock()

    todo.check_and_push_daily_digest(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()
    call_kwargs = telegram_client.send_text.call_args.kwargs
    assert call_kwargs["chat_id"] == 555
    assert "買菜" in call_kwargs["text"]
    assert "明天的事" not in call_kwargs["text"]
    row = fake_db.select("todos", where="id = %s", params=(due_today_id,), fetch_one=True)
    assert row["daily_pushed_on"] == datetime(2026, 8, 2, tzinfo=_TAIWAN_TZ).date()


def test_check_and_push_daily_digest_does_not_repeat_within_same_hour(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    now = _utc(2026, 8, 2, 0, 5)
    todo.create_todo(fake_db, 1, "買菜", _utc(2026, 8, 2, 6, 0), False)
    telegram_client = MagicMock()

    todo.check_and_push_daily_digest(fake_db, telegram_client, now=now)
    todo.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 2, 0, 15))

    telegram_client.send_text.assert_called_once()


def test_check_and_push_daily_digest_skips_user_without_telegram_id(fake_db):
    fake_db.insert("users", {"telegram_user_id": None, "role": "家人", "is_owner": False})
    now = _utc(2026, 8, 2, 0, 5)
    todo.create_todo(fake_db, 1, "買菜", _utc(2026, 8, 2, 6, 0), False)
    telegram_client = MagicMock()

    todo.check_and_push_daily_digest(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_daily_digest_noop_when_nothing_due_today(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    now = _utc(2026, 8, 2, 0, 5)
    telegram_client = MagicMock()

    todo.check_and_push_daily_digest(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()
