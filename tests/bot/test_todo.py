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


# --- 區間待辦事項（FR-31b，2026-08-02，Robin 詢問是否支援時間區間） ---


def test_create_todo_with_start_at_inserts_range_row(fake_db):
    todo_id = todo.create_todo(
        fake_db, 1, "出差", _utc(2026, 8, 5, 9, 0), True, start_at=_utc(2026, 8, 2, 0, 0)
    )

    row = fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)
    assert row["start_at"] == _utc(2026, 8, 2, 0, 0)
    assert row["due_at"] == _utc(2026, 8, 5, 9, 0)


def test_format_todo_list_shows_range_when_start_at_present():
    todos = [
        {
            "content": "出差",
            "due_at": _utc(2026, 8, 5, 9, 0),  # 台灣 17:00
            "start_at": _utc(2026, 8, 2, 0, 0),  # 台灣 08:00
        }
    ]

    text = todo.format_todo_list(todos)

    assert "1. 出差（2026/08/02 08:00 ～ 2026/08/05 17:00）" in text


def test_check_and_push_reminders_range_todo_anchors_on_start_at(fake_db):
    # 區間待辦的「前 30 分鐘提醒」以 start_at（開始時間）為準，不是 due_at（結束時間）。
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    now = _utc(2026, 8, 2, 10, 0)
    todo.create_todo(
        fake_db, 1, "出差", due_at=_utc(2026, 8, 5, 9, 0), remind_before_30min=True,
        start_at=_utc(2026, 8, 2, 10, 20),
    )
    telegram_client = MagicMock()

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()
    text = telegram_client.send_text.call_args.kwargs["text"]
    assert "出差" in text
    assert "再過 30 分鐘就要開始囉" in text


def test_check_and_push_reminders_range_todo_ignores_due_at_within_window(fake_db):
    # due_at 落在 30 分鐘窗口內、但 start_at 還很遠，不該提前提醒。
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    now = _utc(2026, 8, 2, 10, 0)
    todo.create_todo(
        fake_db, 1, "出差", due_at=_utc(2026, 8, 2, 10, 20), remind_before_30min=True,
        start_at=_utc(2026, 8, 1, 0, 0),
    )
    telegram_client = MagicMock()

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_daily_digest_range_todo_appears_on_start_day(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    now = _utc(2026, 8, 2, 0, 5)  # 台灣 08:05，8/2
    todo.create_todo(
        fake_db, 1, "出差", due_at=_utc(2026, 8, 5, 9, 0), remind_before_30min=False,
        start_at=_utc(2026, 8, 1, 22, 0),  # 台灣 8/2 06:00
    )
    telegram_client = MagicMock()

    todo.check_and_push_daily_digest(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()
    text = telegram_client.send_text.call_args.kwargs["text"]
    assert "出差" in text
    assert "開始" in text


def test_check_and_push_daily_digest_range_todo_appears_again_on_due_day(fake_db):
    # 開始日已經推播過一次；到了結束那天（不同的一天）應該要能再推播一次，
    # 不能被「曾經推播過」擋住（這是這次改動的重點：去重改成「今天推播過沒」）。
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    start_day_now = _utc(2026, 8, 2, 0, 5)  # 台灣 8/2 08:05
    due_day_now = _utc(2026, 8, 5, 0, 5)  # 台灣 8/5 08:05
    todo.create_todo(
        fake_db, 1, "出差", due_at=_utc(2026, 8, 5, 9, 0), remind_before_30min=False,  # 台灣 8/5 17:00
        start_at=_utc(2026, 8, 1, 22, 0),  # 台灣 8/2 06:00
    )
    telegram_client = MagicMock()

    todo.check_and_push_daily_digest(fake_db, telegram_client, now=start_day_now)
    todo.check_and_push_daily_digest(fake_db, telegram_client, now=due_day_now)

    assert telegram_client.send_text.call_count == 2
    due_day_text = telegram_client.send_text.call_args.kwargs["text"]
    assert "出差" in due_day_text
    assert "截止" in due_day_text


def test_check_and_push_daily_digest_range_todo_not_repeated_same_day(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    now = _utc(2026, 8, 2, 0, 5)
    todo.create_todo(
        fake_db, 1, "出差", due_at=_utc(2026, 8, 5, 9, 0), remind_before_30min=False,
        start_at=_utc(2026, 8, 1, 22, 0),
    )
    telegram_client = MagicMock()

    todo.check_and_push_daily_digest(fake_db, telegram_client, now=now)
    todo.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 2, 0, 15))

    telegram_client.send_text.assert_called_once()


def test_check_and_push_daily_digest_range_todo_single_day_range_shows_both_times(fake_db):
    # 頭尾在同一天的「一日內區間」，摘要文字要同時帶出開始跟結束時間。
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    now = _utc(2026, 8, 2, 0, 5)  # 台灣 8/2 08:05
    todo.create_todo(
        fake_db, 1, "全天會議", due_at=_utc(2026, 8, 2, 9, 0), remind_before_30min=False,  # 台灣 17:00
        start_at=_utc(2026, 8, 2, 0, 0),  # 台灣 08:00
    )
    telegram_client = MagicMock()

    todo.check_and_push_daily_digest(fake_db, telegram_client, now=now)

    text = telegram_client.send_text.call_args.kwargs["text"]
    assert "08:00" in text
    assert "17:00" in text
