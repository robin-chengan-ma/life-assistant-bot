"""src/bot/todo.py 的單元測試（2026-11 大幅精簡＋2026-11-26 改日期區間／提前提醒，見模組 docstring）。"""
from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from src.bot import todo


def _row(
    user_id: int,
    content: str,
    start: date,
    end: date | None = None,
    remind_offsets: list[int] | None = None,
) -> dict:
    return {
        "user_id": user_id,
        "content": content,
        "recurrence_type": "once",
        "remind_start_date": start,
        "remind_end_date": end or start,
        "remind_offsets": remind_offsets or [0],
        "reminded_offsets_sent": [],
    }


def _monthly_row(user_id: int, content: str, recurrence_day: int, remind_offsets: list[int] | None = None) -> dict:
    return {
        "user_id": user_id,
        "content": content,
        "recurrence_type": "monthly",
        "recurrence_day": recurrence_day,
        "remind_start_date": None,
        "remind_end_date": None,
        "remind_offsets": remind_offsets or [0],
        "reminded_offsets_sent": [],
    }


def test_list_todos_sorted_by_remind_start_date(fake_db):
    fake_db.insert("todos", _row(1, "晚一點", date(2026, 8, 5)))
    fake_db.insert("todos", _row(1, "早一點", date(2026, 8, 2)))
    fake_db.insert("todos", _row(2, "別人的", date(2026, 8, 1)))

    result = todo.list_todos(fake_db, user_id=1)

    assert [item["content"] for item in result] == ["早一點", "晚一點"]


def test_format_todo_list_empty():
    assert todo.format_todo_list([]) == "目前沒有待辦提醒喔！"


def test_format_todo_list_single_day():
    todos = [_row(1, "買菜", date(2026, 8, 2))]
    text = todo.format_todo_list(todos)
    assert "1. 買菜（2026/08/02）" in text


def test_format_todo_list_date_range():
    todos = [_row(1, "出差", date(2026, 8, 2), date(2026, 8, 5))]
    text = todo.format_todo_list(todos)
    assert "1. 出差（2026/08/02～2026/08/05）" in text


def test_check_and_push_reminders_sends_when_due(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    todo_id = fake_db.insert("todos", _row(1, "買菜", date(2026, 8, 2)))
    telegram_client = MagicMock()
    now = datetime(2026, 8, 2, 0, 35, tzinfo=UTC)  # 台灣時間 08:35，落在 08:30 推播視窗內

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()
    assert telegram_client.send_text.call_args.kwargs["chat_id"] == 555
    assert "買菜" in telegram_client.send_text.call_args.kwargs["text"]
    row = fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)
    assert row["reminded_offsets_sent"] == [0]


def test_check_and_push_reminders_advance_notice_offset(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    todo_id = fake_db.insert("todos", _row(1, "買菜", date(2026, 8, 9), remind_offsets=[7, 0]))
    telegram_client = MagicMock()
    # 提前 7 天：2026/8/9 - 7 = 2026/8/2，台灣時間 08:35 落在推播視窗內。
    now = datetime(2026, 8, 2, 0, 35, tzinfo=UTC)

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()
    assert "7 天後" in telegram_client.send_text.call_args.kwargs["text"]
    assert "買菜" in telegram_client.send_text.call_args.kwargs["text"]
    row = fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)
    assert row["reminded_offsets_sent"] == [7]

    # 隔天（當天 offset）應該再推播一次，兩個 offset 各自獨立去重。
    todo.check_and_push_reminders(
        fake_db, telegram_client, now=datetime(2026, 8, 9, 0, 35, tzinfo=UTC)
    )
    assert telegram_client.send_text.call_count == 2
    row = fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)
    assert sorted(row["reminded_offsets_sent"]) == [0, 7]


def test_check_and_push_reminders_skips_outside_window(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    fake_db.insert("todos", _row(1, "買菜", date(2026, 8, 2)))
    telegram_client = MagicMock()
    now = datetime(2026, 8, 2, 5, 0, tzinfo=UTC)  # 台灣時間 13:00，不在推播視窗內

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_reminders_skips_different_date(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    fake_db.insert("todos", _row(1, "買菜", date(2026, 8, 3)))
    telegram_client = MagicMock()
    now = datetime(2026, 8, 2, 0, 35, tzinfo=UTC)

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_reminders_does_not_duplicate_after_sending(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    fake_db.insert("todos", _row(1, "買菜", date(2026, 8, 2)))
    telegram_client = MagicMock()
    now = datetime(2026, 8, 2, 0, 35, tzinfo=UTC)

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)
    todo.check_and_push_reminders(fake_db, telegram_client, now=datetime(2026, 8, 2, 0, 50, tzinfo=UTC))

    telegram_client.send_text.assert_called_once()


def test_check_and_push_reminders_skips_user_without_telegram_id(fake_db):
    fake_db.insert("users", {"telegram_user_id": None, "role": "家人", "is_owner": False})
    fake_db.insert("todos", _row(1, "買菜", date(2026, 8, 2)))
    telegram_client = MagicMock()
    now = datetime(2026, 8, 2, 0, 35, tzinfo=UTC)

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_monthly_reminder_sends_on_recurrence_day(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    fake_db.insert("todos", _monthly_row(1, "繳信用卡費", recurrence_day=5))
    telegram_client = MagicMock()
    now = datetime(2026, 8, 5, 0, 35, tzinfo=UTC)  # 台灣時間 08:35，8/5 當天

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()
    assert "繳信用卡費" in telegram_client.send_text.call_args.kwargs["text"]


def test_check_and_push_monthly_reminder_repeats_every_month(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    fake_db.insert("todos", _monthly_row(1, "繳信用卡費", recurrence_day=5))
    telegram_client = MagicMock()

    todo.check_and_push_reminders(fake_db, telegram_client, now=datetime(2026, 8, 5, 0, 35, tzinfo=UTC))
    # 同一天再檢查一次不應該重複推播。
    todo.check_and_push_reminders(fake_db, telegram_client, now=datetime(2026, 8, 5, 0, 50, tzinfo=UTC))
    assert telegram_client.send_text.call_count == 1

    # 下個月同一天應該重新推播一次（常態性待辦每個月都重複）。
    todo.check_and_push_reminders(fake_db, telegram_client, now=datetime(2026, 9, 5, 0, 35, tzinfo=UTC))
    assert telegram_client.send_text.call_count == 2


def test_check_and_push_monthly_reminder_clamps_to_last_day_of_short_month(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    fake_db.insert("todos", _monthly_row(1, "繳車貸", recurrence_day=31))
    telegram_client = MagicMock()
    # 2026 年 2 月只有 28 天，31 號應該退回 2/28。
    now = datetime(2026, 2, 28, 0, 35, tzinfo=UTC)

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()


def test_check_and_push_monthly_reminder_advance_offset(fake_db):
    fake_db.insert("users", {"telegram_user_id": 555, "role": "Robin", "is_owner": True})
    fake_db.insert("todos", _monthly_row(1, "繳信用卡費", recurrence_day=5, remind_offsets=[3]))
    telegram_client = MagicMock()
    # 提前 3 天：8/5 - 3 = 8/2。
    now = datetime(2026, 8, 2, 0, 35, tzinfo=UTC)

    todo.check_and_push_reminders(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()
    assert "3 天後" in telegram_client.send_text.call_args.kwargs["text"]
