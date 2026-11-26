"""src/bot/national_holidays.py（父親節／母親節／中秋／端午推播）的單元測試。"""
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from src.bot import national_holidays

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")


def _bound_user(fake_db, telegram_user_id):
    return fake_db.insert(
        "users", {"telegram_user_id": telegram_user_id, "role": "家人", "is_owner": False}
    )


def test_fathers_day_is_fixed_august_8th():
    assert national_holidays._fathers_day(2026) == national_holidays.date(2026, 8, 8)
    assert national_holidays._fathers_day(2027) == national_holidays.date(2027, 8, 8)


def test_mothers_day_is_second_sunday_of_may():
    # 2026/5/1 是星期五，第一個星期日是 5/3，第二個星期日是 5/10。
    assert national_holidays._mothers_day(2026) == national_holidays.date(2026, 5, 10)
    # 2027/5/1 是星期六，第一個星期日是 5/2，第二個星期日是 5/9。
    assert national_holidays._mothers_day(2027) == national_holidays.date(2027, 5, 9)


def test_fathers_day_pushes_seven_days_before_to_all_bound_users(fake_db):
    _bound_user(fake_db, 111)
    _bound_user(fake_db, 222)
    telegram_client = Mock()
    now = datetime(2026, 8, 1, 9, 0, tzinfo=_TAIWAN_TZ)

    national_holidays.check_and_push_fixed_holidays(fake_db, telegram_client, now=now)

    assert telegram_client.send_text.call_count == 2
    chat_ids = {call.kwargs["chat_id"] for call in telegram_client.send_text.call_args_list}
    assert chat_ids == {111, 222}
    assert "父親節" in telegram_client.send_text.call_args_list[0].kwargs["text"]
    assert "7 天後" in telegram_client.send_text.call_args_list[0].kwargs["text"]


def test_fathers_day_pushes_on_the_day_with_different_wording(fake_db):
    _bound_user(fake_db, 111)
    telegram_client = Mock()
    now = datetime(2026, 8, 8, 9, 0, tzinfo=_TAIWAN_TZ)

    national_holidays.check_and_push_fixed_holidays(fake_db, telegram_client, now=now)

    text = telegram_client.send_text.call_args.kwargs["text"]
    assert "今天是父親節" in text
    assert "天後" not in text


def test_fathers_day_does_not_duplicate_within_same_year(fake_db):
    _bound_user(fake_db, 111)
    telegram_client = Mock()
    now = datetime(2026, 8, 8, 9, 0, tzinfo=_TAIWAN_TZ)

    national_holidays.check_and_push_fixed_holidays(fake_db, telegram_client, now=now)
    national_holidays.check_and_push_fixed_holidays(fake_db, telegram_client, now=now)

    assert telegram_client.send_text.call_count == 1


def test_mothers_day_pushes_on_the_day(fake_db):
    _bound_user(fake_db, 333)
    telegram_client = Mock()
    now = datetime(2026, 5, 10, 9, 0, tzinfo=_TAIWAN_TZ)

    national_holidays.check_and_push_fixed_holidays(fake_db, telegram_client, now=now)

    assert telegram_client.send_text.call_count == 1
    assert "母親節" in telegram_client.send_text.call_args.kwargs["text"]


def test_lunar_holiday_pushes_on_matching_calendar_day(fake_db):
    _bound_user(fake_db, 444)
    telegram_client = Mock()
    now = datetime(2026, 9, 25, 9, 0, tzinfo=_TAIWAN_TZ)
    fake_days = {"2026-09-25": {"name": "中秋節", "is_holiday": True}}

    with patch.object(national_holidays, "TaiwanCalendarService") as mock_service_cls:
        mock_service_cls.return_value.days.return_value = fake_days
        national_holidays.check_and_push_lunar_holidays(fake_db, telegram_client, now=now)

    assert telegram_client.send_text.call_count == 1
    assert "中秋節" in telegram_client.send_text.call_args.kwargs["text"]


def test_lunar_holiday_does_not_push_when_not_matching_day(fake_db):
    _bound_user(fake_db, 444)
    telegram_client = Mock()
    now = datetime(2026, 9, 24, 9, 0, tzinfo=_TAIWAN_TZ)
    fake_days = {"2026-09-25": {"name": "中秋節", "is_holiday": True}}

    with patch.object(national_holidays, "TaiwanCalendarService") as mock_service_cls:
        mock_service_cls.return_value.days.return_value = fake_days
        national_holidays.check_and_push_lunar_holidays(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_lunar_holiday_does_not_duplicate_within_same_year(fake_db):
    _bound_user(fake_db, 444)
    telegram_client = Mock()
    now = datetime(2026, 6, 19, 9, 0, tzinfo=_TAIWAN_TZ)
    fake_days = {"2026-06-19": {"name": "端午節", "is_holiday": True}}

    with patch.object(national_holidays, "TaiwanCalendarService") as mock_service_cls:
        mock_service_cls.return_value.days.return_value = fake_days
        national_holidays.check_and_push_lunar_holidays(fake_db, telegram_client, now=now)
        national_holidays.check_and_push_lunar_holidays(fake_db, telegram_client, now=now)

    assert telegram_client.send_text.call_count == 1
