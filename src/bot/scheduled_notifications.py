"""重要日子、目標日期與旅遊日期的統一 Telegram 提醒發送器。"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.bot.schedule_settings import is_notification_enabled
from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_DEFAULT_HOUR = 8


def _event_date(db: CloudSQLClient, event: dict, year: int) -> date | None:
    if event["recurrence_type"] == "one_time":
        return event.get("event_date")
    if event["recurrence_type"] == "fixed_annual":
        try:
            return date(year, event["event_month"], event["event_day"])
        except ValueError:
            return None
    occurrence = db.select(
        "important_day_occurrences",
        where="important_day_id = %s AND occurrence_year = %s",
        params=(event["id"], year),
        fetch_one=True,
    )
    return occurrence.get("occurrence_date") if occurrence else None


def _recipients(db: CloudSQLClient, event: dict) -> list[dict]:
    if event["audience_mode"] == "self":
        user = db.select("users", where="id = %s", params=(event["owner_user_id"],), fetch_one=True)
        return [user] if user else []
    if event["audience_mode"] == "all":
        return db.select("users", where="telegram_user_id IS NOT NULL")
    links = db.select(
        "important_day_recipients", where="important_day_id = %s", params=(event["id"],)
    )
    recipients = []
    for link in links:
        user = db.select("users", where="id = %s", params=(link["user_id"],), fetch_one=True)
        if user:
            recipients.append(user)
    return recipients


def check_and_push_important_days(
    db: CloudSQLClient, telegram_client, now: datetime | None = None
) -> None:
    now = now or datetime.now(timezone.utc)
    now_local = now.astimezone(_TAIWAN_TZ)
    if now_local.hour != _DEFAULT_HOUR:
        return
    today = now_local.date()

    for event in db.select("important_days", where="is_active = %s", params=(True,)):
        target = _event_date(db, event, today.year)
        if target is None or target - timedelta(days=event["reminder_days_before"]) != today:
            continue
        for user in _recipients(db, event):
            if user.get("telegram_user_id") is None:
                continue
            if not is_notification_enabled(db, user["id"], "important_day"):
                continue
            notification_key = f"important_day_{event['id']}_user_{user['id']}_{target.isoformat()}"
            sent = db.select(
                "important_notifications_log",
                where="notification_key = %s AND year = %s",
                params=(notification_key, target.year),
                fetch_one=True,
            )
            if sent:
                continue
            days = event["reminder_days_before"]
            when = "今天" if days == 0 else f"{days} 天後"
            telegram_client.send_text(
                chat_id=user["telegram_user_id"],
                text=f"📅 提醒你，{when}是「{event['title']}」。",
            )
            db.insert("important_notifications_log", {
                "notification_key": notification_key,
                "year": target.year,
            })
