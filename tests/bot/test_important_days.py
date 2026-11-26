"""src/bot/important_days.py（「生日設定」）的單元測試。

2026-11（功能大幅精簡）：舊版多步驟新增/編輯對話流程已整個移除（改到 Mobile App），這裡只測試
Telegram 端僅存的兩件事：查清單、每日排程推播生日提醒。
"""
from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from src.bot import important_days

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")


def test_list_birthdays_sorted_by_month_day(fake_db):
    important_days.list_birthdays  # noqa: B018 - 確認模組正確匯出
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})
    fake_db.insert("important_days", {"user_id": user_id, "name": "弟弟", "birth_month": 12, "birth_day": 1})
    fake_db.insert("important_days", {"user_id": user_id, "name": "媽媽", "birth_month": 3, "birth_day": 20})

    rows = important_days.list_birthdays(fake_db, user_id)

    assert [row["name"] for row in rows] == ["媽媽", "弟弟"]


def test_format_birthday_list_empty():
    assert "還沒有" in important_days.format_birthday_list([])


def test_format_birthday_list_includes_month_day():
    text = important_days.format_birthday_list([{"name": "媽媽", "birth_month": 3, "birth_day": 20}])
    assert "媽媽" in text
    assert "3/20" in text


def test_check_and_push_birthdays_sends_to_owner_on_matching_date(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "Robin", "is_owner": True})
    fake_db.insert("important_days", {"user_id": user_id, "name": "媽媽", "birth_month": 3, "birth_day": 20})
    telegram_client = Mock()
    now = datetime(2026, 3, 20, 9, 0, tzinfo=_TAIWAN_TZ)

    important_days.check_and_push_birthdays(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()
    _, kwargs = telegram_client.send_text.call_args
    assert kwargs["chat_id"] == 111
    assert "媽媽" in kwargs["text"]


def test_check_and_push_birthdays_skips_non_matching_date(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "Robin", "is_owner": True})
    fake_db.insert("important_days", {"user_id": user_id, "name": "媽媽", "birth_month": 3, "birth_day": 20})
    telegram_client = Mock()
    now = datetime(2026, 3, 21, 9, 0, tzinfo=_TAIWAN_TZ)

    important_days.check_and_push_birthdays(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_birthdays_does_not_duplicate_same_year(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "Robin", "is_owner": True})
    fake_db.insert("important_days", {"user_id": user_id, "name": "媽媽", "birth_month": 3, "birth_day": 20})
    telegram_client = Mock()
    now = datetime(2026, 3, 20, 9, 0, tzinfo=_TAIWAN_TZ)

    important_days.check_and_push_birthdays(fake_db, telegram_client, now=now)
    important_days.check_and_push_birthdays(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()


def test_check_and_push_birthdays_skips_unbound_user(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": None, "role": "待綁定", "is_owner": False})
    fake_db.insert("important_days", {"user_id": user_id, "name": "媽媽", "birth_month": 3, "birth_day": 20})
    telegram_client = Mock()
    now = datetime(2026, 3, 20, 9, 0, tzinfo=_TAIWAN_TZ)

    important_days.check_and_push_birthdays(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_birthdays_sends_advance_offset_reminder(fake_db):
    # 2026-11-26（多選提前提醒，見 migration 0105）：14/7/3 天前也要推播，文案與當天不同。
    user_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "Robin", "is_owner": True})
    fake_db.insert(
        "important_days",
        {"user_id": user_id, "name": "媽媽", "birth_month": 3, "birth_day": 27, "remind_offsets": [0, 7]},
    )
    telegram_client = Mock()
    now = datetime(2026, 3, 20, 9, 0, tzinfo=_TAIWAN_TZ)  # 提前 7 天

    important_days.check_and_push_birthdays(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_called_once()
    _, kwargs = telegram_client.send_text.call_args
    assert "媽媽" in kwargs["text"]
    assert "7 天後" in kwargs["text"]


def test_check_and_push_birthdays_sends_each_selected_offset_independently(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "Robin", "is_owner": True})
    fake_db.insert(
        "important_days",
        {"user_id": user_id, "name": "媽媽", "birth_month": 3, "birth_day": 20, "remind_offsets": [0, 3, 7, 14]},
    )
    telegram_client = Mock()

    # 提前 14 天跟當天都要各推播一次，彼此不互相去重（notification_key 帶 offset）。
    important_days.check_and_push_birthdays(fake_db, telegram_client, now=datetime(2026, 3, 6, 9, 0, tzinfo=_TAIWAN_TZ))
    important_days.check_and_push_birthdays(fake_db, telegram_client, now=datetime(2026, 3, 20, 9, 0, tzinfo=_TAIWAN_TZ))

    assert telegram_client.send_text.call_count == 2


def test_check_and_push_birthdays_defaults_to_day_of_offset_when_unset(fake_db):
    # 沒有 remind_offsets 欄位（理論上有 DB 預設值 '{0}'，這裡防禦性測試 Python 端的 fallback）。
    user_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "Robin", "is_owner": True})
    fake_db.insert("important_days", {"user_id": user_id, "name": "媽媽", "birth_month": 3, "birth_day": 20})
    telegram_client = Mock()

    important_days.check_and_push_birthdays(
        fake_db, telegram_client, now=datetime(2026, 3, 13, 9, 0, tzinfo=_TAIWAN_TZ)
    )
    telegram_client.send_text.assert_not_called()

    important_days.check_and_push_birthdays(
        fake_db, telegram_client, now=datetime(2026, 3, 20, 9, 0, tzinfo=_TAIWAN_TZ)
    )
    telegram_client.send_text.assert_called_once()


def test_check_and_push_birthdays_self_mode_only_sends_to_owner(fake_db):
    owner_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "Robin", "is_owner": True})
    fake_db.insert("users", {"telegram_user_id": 222, "role": "弟弟", "is_owner": False})
    fake_db.insert(
        "important_days",
        {"user_id": owner_id, "name": "媽媽", "birth_month": 3, "birth_day": 20, "audience_mode": "self"},
    )
    telegram_client = Mock()

    important_days.check_and_push_birthdays(fake_db, telegram_client, now=datetime(2026, 3, 20, 9, 0, tzinfo=_TAIWAN_TZ))

    telegram_client.send_text.assert_called_once()
    _, kwargs = telegram_client.send_text.call_args
    assert kwargs["chat_id"] == 111


def test_check_and_push_birthdays_everyone_mode_sends_to_all_bound_users(fake_db):
    owner_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "Robin", "is_owner": True})
    fake_db.insert("users", {"telegram_user_id": 222, "role": "弟弟", "is_owner": False})
    fake_db.insert("users", {"telegram_user_id": None, "role": "待綁定", "is_owner": False})
    fake_db.insert(
        "important_days",
        {"user_id": owner_id, "name": "媽媽", "birth_month": 3, "birth_day": 20, "audience_mode": "everyone"},
    )
    telegram_client = Mock()

    important_days.check_and_push_birthdays(fake_db, telegram_client, now=datetime(2026, 3, 20, 9, 0, tzinfo=_TAIWAN_TZ))

    assert telegram_client.send_text.call_count == 2
    chat_ids = {call.kwargs["chat_id"] for call in telegram_client.send_text.call_args_list}
    assert chat_ids == {111, 222}


def test_check_and_push_birthdays_selected_mode_sends_only_to_picked_users_not_owner(fake_db):
    owner_id = fake_db.insert("users", {"telegram_user_id": 111, "role": "Robin", "is_owner": True})
    picked_id = fake_db.insert("users", {"telegram_user_id": 222, "role": "弟弟", "is_owner": False})
    fake_db.insert("users", {"telegram_user_id": 333, "role": "弟媳", "is_owner": False})
    fake_db.insert(
        "important_days",
        {
            "user_id": owner_id,
            "name": "媽媽",
            "birth_month": 3,
            "birth_day": 20,
            "audience_mode": "selected",
            "audience_user_ids": [picked_id],
        },
    )
    telegram_client = Mock()

    important_days.check_and_push_birthdays(fake_db, telegram_client, now=datetime(2026, 3, 20, 9, 0, tzinfo=_TAIWAN_TZ))

    telegram_client.send_text.assert_called_once()
    _, kwargs = telegram_client.send_text.call_args
    assert kwargs["chat_id"] == 222
