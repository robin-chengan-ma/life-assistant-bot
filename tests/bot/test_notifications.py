"""src/bot/notifications.py 的單元測試（對應 robinson SPEC.md FR-53，Step 2.3）。"""
from datetime import date, datetime, timezone
from unittest.mock import Mock

from src.bot import notifications

# --- 節日日期計算 ---


def test_get_new_year():
    assert notifications.get_new_year(2026) == date(2026, 1, 1)


def test_get_fathers_day_fixed_august_8th():
    assert notifications.get_fathers_day(2026) == date(2026, 8, 8)


def test_get_mothers_day_second_sunday_of_may():
    # 2026/5/1 是星期五，第一個星期日是 5/3，第二個星期日是 5/10
    assert notifications.get_mothers_day(2026) == date(2026, 5, 10)
    # 2027/5/1 是星期六，第一個星期日是 5/2，第二個星期日是 5/9
    assert notifications.get_mothers_day(2027) == date(2027, 5, 9)


def test_get_tomb_sweeping_reminder_fixed_march_1st():
    assert notifications.get_tomb_sweeping_reminder(2026) == date(2026, 3, 1)


def test_get_lunar_new_year_day1_and_eve():
    day1 = notifications.get_lunar_new_year_day1(2026)
    assert day1 == date(2026, 2, 17)
    assert notifications.get_lunar_new_year_eve(2026) == date(2026, 2, 16)


def test_get_mid_autumn():
    assert notifications.get_mid_autumn(2026) == date(2026, 9, 25)


def test_get_dragon_boat():
    assert notifications.get_dragon_boat(2026) == date(2026, 6, 19)


def test_fixed_notifications_list_has_eight_entries_with_expected_keys():
    keys = {entry["key"] for entry in notifications.FIXED_NOTIFICATIONS}
    assert keys == {
        "new_year", "lunar_new_year_eve", "lunar_new_year_day1", "tomb_sweeping",
        "mid_autumn", "dragon_boat", "fathers_day", "mothers_day",
    }


def test_fathers_day_and_mothers_day_have_subject_role_and_message():
    # 2026-08-09（FR-53f，見 ADR-30）：主角不再被排除，改為收到不同版本的祝福文案。
    by_key = {entry["key"]: entry for entry in notifications.FIXED_NOTIFICATIONS}
    assert by_key["fathers_day"]["subject_role"] == "爸爸"
    assert by_key["fathers_day"]["subject_message"]
    assert by_key["mothers_day"]["subject_role"] == "媽媽"
    assert by_key["mothers_day"]["subject_message"]
    assert by_key["new_year"]["subject_role"] is None


def test_tomb_sweeping_has_restricted_allowed_roles():
    # 2026-08-09（FR-53f）：掃墓提醒改為固定名單，不再是「大家都收到」。
    by_key = {entry["key"]: entry for entry in notifications.FIXED_NOTIFICATIONS}
    assert by_key["tomb_sweeping"]["allowed_roles"] == ["Robin", "爸爸", "媽媽", "弟弟", "弟媳", "阿姨"]
    assert by_key["new_year"]["allowed_roles"] is None


def test_fixed_notifications_all_have_calendar_summary():
    # 2026-08-05（FR-66b、ADR-17）：每個固定節日都要有獨立的 Calendar 事件標題。
    for entry in notifications.FIXED_NOTIFICATIONS:
        assert entry["calendar_summary"]


# --- 推播主流程 ---


def _bind_user(fake_db, telegram_user_id, role, is_owner=False, birthday=None):
    return fake_db.insert(
        "users",
        {"telegram_user_id": telegram_user_id, "role": role, "is_owner": is_owner, "birthday": birthday},
    )


def test_check_and_push_skips_outside_notification_hour(fake_db):
    _bind_user(fake_db, 1, "Robin", is_owner=True)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)  # 台灣時間 20:00，不在 08:00
    telegram_client = Mock()

    notifications.check_and_push_important_notifications(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_new_year_broadcasts_to_everyone(fake_db):
    _bind_user(fake_db, 1, "Robin", is_owner=True)
    _bind_user(fake_db, 2, "爸爸")
    now = datetime(2025, 12, 31, 16, 5, tzinfo=timezone.utc)  # 台灣時間 2026/01/01 00:05... 調整見下

    # 台灣時間 08:00 對應 UTC 前一天 00:00；用 2026-01-01 08:00 台灣時間
    now = datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc)
    telegram_client = Mock()

    notifications.check_and_push_important_notifications(fake_db, telegram_client, now=now)

    assert telegram_client.send_text.call_count == 2
    log_row = fake_db.select(
        "important_notifications_log", where="notification_key = %s AND year = %s", params=("new_year", 2026)
    )
    assert len(log_row) == 1


def test_check_and_push_does_not_duplicate_within_same_year(fake_db):
    _bind_user(fake_db, 1, "Robin", is_owner=True)
    now = datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc)
    telegram_client = Mock()

    notifications.check_and_push_important_notifications(fake_db, telegram_client, now=now)
    notifications.check_and_push_important_notifications(fake_db, telegram_client, now=now)

    assert telegram_client.send_text.call_count == 1


def test_check_and_push_fathers_day_sends_subject_message_to_father(fake_db):
    # 2026-08-09（FR-53f）：爸爸本人也收到通知，但文案跟其他人不同。
    _bind_user(fake_db, 1, "Robin", is_owner=True)
    father_id = _bind_user(fake_db, 2, "爸爸")
    now = datetime(2026, 8, 8, 0, 5, tzinfo=timezone.utc)
    telegram_client = Mock()

    notifications.check_and_push_important_notifications(fake_db, telegram_client, now=now)

    messages_by_chat_id = {call.kwargs["chat_id"]: call.kwargs["text"] for call in telegram_client.send_text.call_args_list}
    assert father_id is not None
    assert 1 in messages_by_chat_id and 2 in messages_by_chat_id
    assert "父親節快樂" in messages_by_chat_id[2]
    assert "提醒你" in messages_by_chat_id[1]


def test_check_and_push_mothers_day_sends_subject_message_to_mother(fake_db):
    _bind_user(fake_db, 1, "Robin", is_owner=True)
    _bind_user(fake_db, 2, "媽媽")
    now = datetime(2026, 5, 10, 0, 5, tzinfo=timezone.utc)
    telegram_client = Mock()

    notifications.check_and_push_important_notifications(fake_db, telegram_client, now=now)

    messages_by_chat_id = {call.kwargs["chat_id"]: call.kwargs["text"] for call in telegram_client.send_text.call_args_list}
    assert 1 in messages_by_chat_id and 2 in messages_by_chat_id
    assert "母親節快樂" in messages_by_chat_id[2]
    assert "提醒你" in messages_by_chat_id[1]


def test_check_and_push_tomb_sweeping_only_sends_to_allowed_roles(fake_db):
    # 2026-08-09（FR-53f）：只有固定名單裡的角色收到掃墓提醒。
    _bind_user(fake_db, 1, "Robin", is_owner=True)
    _bind_user(fake_db, 2, "爸爸")
    outsider_id = _bind_user(fake_db, 3, "大妹")
    now = datetime(2026, 3, 1, 0, 5, tzinfo=timezone.utc)
    telegram_client = Mock()

    notifications.check_and_push_important_notifications(fake_db, telegram_client, now=now)

    sent_chat_ids = [call.kwargs["chat_id"] for call in telegram_client.send_text.call_args_list]
    assert 1 in sent_chat_ids
    assert 2 in sent_chat_ids
    assert 3 not in sent_chat_ids
    assert outsider_id is not None


def test_check_and_push_birthday_includes_birthday_person_with_different_message(fake_db):
    # 2026-08-09（FR-53f）：壽星本人也收到通知（祝福版），其他人收到提醒版。
    _bind_user(fake_db, 1, "Robin", is_owner=True)
    birthday_user_id = _bind_user(fake_db, 2, "弟弟", birthday=date(1999, 4, 22))
    now = datetime(2026, 4, 22, 0, 5, tzinfo=timezone.utc)
    telegram_client = Mock()

    notifications.check_and_push_important_notifications(fake_db, telegram_client, now=now)

    messages_by_chat_id = {call.kwargs["chat_id"]: call.kwargs["text"] for call in telegram_client.send_text.call_args_list}
    assert 1 in messages_by_chat_id and 2 in messages_by_chat_id
    assert "生日快樂！今天是你的生日" in messages_by_chat_id[2]
    assert "提醒你，今天是 弟弟 的生日" in messages_by_chat_id[1]

    log_rows = fake_db.select(
        "important_notifications_log",
        where="notification_key = %s AND year = %s",
        params=(f"birthday_{birthday_user_id}", 2026),
    )
    assert len(log_rows) == 1


def test_check_and_push_birthday_does_not_duplicate_within_same_year(fake_db):
    _bind_user(fake_db, 1, "Robin", is_owner=True)
    _bind_user(fake_db, 2, "弟弟", birthday=date(1999, 4, 22))
    now = datetime(2026, 4, 22, 0, 5, tzinfo=timezone.utc)
    telegram_client = Mock()

    notifications.check_and_push_important_notifications(fake_db, telegram_client, now=now)
    notifications.check_and_push_important_notifications(fake_db, telegram_client, now=now)

    # 2026-08-09（FR-53f）：壽星本人現在也會收到通知，2 位已綁定使用者都收到一次；
    # 第二次呼叫因為去重機制被擋下，不會重複發送。
    assert telegram_client.send_text.call_count == 2


def test_check_and_push_no_notification_on_ordinary_day(fake_db):
    _bind_user(fake_db, 1, "Robin", is_owner=True)
    now = datetime(2026, 3, 15, 0, 5, tzinfo=timezone.utc)
    telegram_client = Mock()

    notifications.check_and_push_important_notifications(fake_db, telegram_client, now=now)

    telegram_client.send_text.assert_not_called()


def test_check_and_push_broadcast_swallows_individual_failures(fake_db):
    _bind_user(fake_db, 1, "Robin", is_owner=True)
    _bind_user(fake_db, 2, "爸爸")
    now = datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc)
    telegram_client = Mock()
    telegram_client.send_text.side_effect = [RuntimeError("boom"), None]

    notifications.check_and_push_important_notifications(fake_db, telegram_client, now=now)

    assert telegram_client.send_text.call_count == 2
    log_row = fake_db.select(
        "important_notifications_log", where="notification_key = %s AND year = %s", params=("new_year", 2026)
    )
    assert len(log_row) == 1


# --- Google Calendar 同步（FR-66b，2026-08-05，見 ADR-17） ---


def test_check_and_push_creates_calendar_event_for_fixed_notification(fake_db):
    _bind_user(fake_db, 1, "Robin", is_owner=True)
    now = datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc)
    telegram_client = Mock()
    calendar_client = Mock()

    notifications.check_and_push_important_notifications(
        fake_db, telegram_client, now=now, calendar_client=calendar_client
    )

    calendar_client.create_event.assert_called_once_with(
        summary="元旦", start="2026-01-01", end="2026-01-02", all_day=True,
    )


def test_check_and_push_creates_calendar_event_for_birthday(fake_db):
    _bind_user(fake_db, 1, "Robin", is_owner=True)
    _bind_user(fake_db, 2, "弟弟", birthday=date(1999, 4, 22))
    now = datetime(2026, 4, 22, 0, 5, tzinfo=timezone.utc)
    telegram_client = Mock()
    calendar_client = Mock()

    notifications.check_and_push_important_notifications(
        fake_db, telegram_client, now=now, calendar_client=calendar_client
    )

    calendar_client.create_event.assert_called_once_with(
        summary="弟弟 生日", start="2026-04-22", end="2026-04-23", all_day=True,
    )


def test_check_and_push_skips_calendar_when_client_is_none(fake_db):
    _bind_user(fake_db, 1, "Robin", is_owner=True)
    now = datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc)
    telegram_client = Mock()

    # calendar_client 預設 None，不應拋例外，Telegram 推播照常運作。
    notifications.check_and_push_important_notifications(fake_db, telegram_client, now=now)

    assert telegram_client.send_text.call_count == 1


def test_check_and_push_swallows_calendar_event_creation_failure(fake_db):
    _bind_user(fake_db, 1, "Robin", is_owner=True)
    now = datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc)
    telegram_client = Mock()
    calendar_client = Mock()
    calendar_client.create_event.side_effect = RuntimeError("boom")

    notifications.check_and_push_important_notifications(
        fake_db, telegram_client, now=now, calendar_client=calendar_client
    )

    assert telegram_client.send_text.call_count == 1
    log_row = fake_db.select(
        "important_notifications_log", where="notification_key = %s AND year = %s", params=("new_year", 2026)
    )
    assert len(log_row) == 1
