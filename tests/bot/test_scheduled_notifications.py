from datetime import date, datetime, timezone

from src.bot import scheduled_notifications


class Telegram:
    def __init__(self):
        self.sent = []

    def send_text(self, chat_id, text):
        self.sent.append((chat_id, text))


def test_goal_or_trip_important_day_uses_unified_sender(fake_db):
    fake_db.insert("users", {"id": 1, "telegram_user_id": 100, "is_owner": False})
    fake_db.insert("important_days", {
        "id": 9, "owner_user_id": 1, "title": "東京行", "recurrence_type": "one_time",
        "event_date": date(2026, 8, 20), "reminder_days_before": 2,
        "audience_mode": "self", "is_active": True,
    })
    telegram = Telegram()

    scheduled_notifications.check_and_push_important_days(
        fake_db, telegram, now=datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)
    )

    assert telegram.sent == [(100, "📅 提醒你，2 天後是「東京行」。")]


def test_disabled_important_day_notification_does_not_send(fake_db):
    fake_db.insert("users", {"id": 1, "telegram_user_id": 100, "is_owner": False})
    fake_db.insert("notification_preferences", {
        "user_id": 1, "notification_key": "important_day", "is_enabled": False,
    })
    fake_db.insert("important_days", {
        "id": 9, "owner_user_id": 1, "title": "記帳目標", "recurrence_type": "one_time",
        "event_date": date(2026, 8, 18), "reminder_days_before": 0,
        "audience_mode": "self", "is_active": True,
    })
    telegram = Telegram()

    scheduled_notifications.check_and_push_important_days(
        fake_db, telegram, now=datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)
    )

    assert telegram.sent == []
