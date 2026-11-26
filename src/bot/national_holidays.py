"""固定國定節日（父親節／母親節）與農曆節日（中秋／端午）的主動推播。

2026-11-26（Robin 提出）：之前的「農曆節日推播」整個隨大瘦身砍掉，但 Robin 實際使用後發現完全
沒有節日提醒，要求至少把父親節／母親節（提前 7 天＋當天推播，不需要使用者設定，固定邏輯）、
中秋節／端午節（當天推播即可，不需要提前）補回來，這些都是「全家人共用」的固定節日，不是
`important_days` 那種每人各自設定的生日，所以推播對象是全體已綁定使用者，不分建立者。

- 父親節：台灣習慣固定國曆 8/8，不需要計算。
- 母親節：國際慣例 5 月第二個星期日，用日期運算直接算，不需要外部資料。
- 中秋節／端午節：農曆換算成當年國曆日期不是能用公式簡單算出來的，直接借用既有
  `src/services/taiwan_calendar.py`（政府行政機關辦公日曆，`name` 欄位本來就會標註「中秋節」
  「端午節」等國定假日名稱）查當年日期，不自己重算農曆。

推播去重沿用既有的 `important_notifications_log`（`notification_key` + `year` 唯一），
`notification_key` 用 `holiday_{slug}_offset_{offset}` 這個格式，年份用節日當年。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.bot import todo
from src.services.taiwan_calendar import TaiwanCalendarService
from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")

# 提前幾天推播 + 當天推播，父親節／母親節共用同一組邏輯，所以寫成資料結構而不是各寫一次。
_ADVANCE_OFFSETS = (7, 0)

# 農曆節日：政府行事曆 name 欄位會出現的關鍵字，對應要推播的文案（slug、關鍵字、emoji、顯示名稱）。
_LUNAR_HOLIDAYS = (
    ("mid_autumn", "中秋", "🌕", "中秋節"),
    ("dragon_boat", "端午", "🛶", "端午節"),
)


def _fathers_day(year: int) -> date:
    """台灣父親節：固定國曆 8/8。"""
    return date(year, 8, 8)


def _mothers_day(year: int) -> date:
    """母親節：5 月第二個星期日。先找 5/1 是星期幾，推到第一個星期日，再加 7 天。"""
    first_of_may = date(year, 5, 1)
    first_sunday = first_of_may + timedelta(days=(6 - first_of_may.weekday()) % 7)
    return first_sunday + timedelta(days=7)


def _notification_key(slug: str, offset: int) -> str:
    return f"holiday_{slug}_offset_{offset}"


def _already_sent(db: CloudSQLClient, notification_key: str, year: int) -> bool:
    return (
        db.select(
            "important_notifications_log",
            where="notification_key = %s AND year = %s",
            params=(notification_key, year),
            fetch_one=True,
        )
        is not None
    )


def _mark_sent(db: CloudSQLClient, notification_key: str, year: int) -> None:
    db.insert("important_notifications_log", {"notification_key": notification_key, "year": year})


def _broadcast(db: CloudSQLClient, telegram_client, text: str) -> None:
    """推播給所有已綁定 Telegram 的使用者（這是全家共用的固定節日，不分建立者）。"""
    users = db.select("users", where="telegram_user_id IS NOT NULL")
    for user in users:
        todo.push_reminder(telegram_client, user["telegram_user_id"], text)


def _check_fixed_holiday(
    db: CloudSQLClient,
    telegram_client,
    *,
    slug: str,
    label: str,
    emoji: str,
    compute_date,
    today_local: date,
) -> None:
    """父親節／母親節共用的「提前 7 天 + 當天」推播邏輯。"""
    for year in (today_local.year, today_local.year + 1):
        holiday_date = compute_date(year)
        for offset in _ADVANCE_OFFSETS:
            if holiday_date - timedelta(days=offset) != today_local:
                continue
            notification_key = _notification_key(slug, offset)
            if _already_sent(db, notification_key, year):
                continue
            if offset == 0:
                text = f"{emoji} 今天是{label}，記得跟家人說聲節日快樂！"
            else:
                text = f"{emoji} {offset} 天後是{label}（{holiday_date:%m/%d}），記得提前準備！"
            _broadcast(db, telegram_client, text)
            _mark_sent(db, notification_key, year)


def check_and_push_fixed_holidays(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """每日排程：父親節（8/8）、母親節（5 月第二個星期日）提前 7 天＋當天推播給全體使用者。"""
    now = now or datetime.now(tz=_TAIWAN_TZ)
    today_local = now.astimezone(_TAIWAN_TZ).date()

    _check_fixed_holiday(
        db, telegram_client, slug="fathers_day", label="父親節", emoji="👨‍👧",
        compute_date=_fathers_day, today_local=today_local,
    )
    _check_fixed_holiday(
        db, telegram_client, slug="mothers_day", label="母親節", emoji="👩‍👧",
        compute_date=_mothers_day, today_local=today_local,
    )


def check_and_push_lunar_holidays(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """每日排程：中秋節／端午節只在當天推播（不提前，農曆日期借用既有政府行事曆資料換算，
    不自己重算農曆）。"""
    now = now or datetime.now(tz=_TAIWAN_TZ)
    today_local = now.astimezone(_TAIWAN_TZ).date()
    year = today_local.year

    calendar_service = TaiwanCalendarService(db, sync_missing=True)
    days = calendar_service.days(date(year, 1, 1), date(year, 12, 31))

    for slug, keyword, emoji, label in _LUNAR_HOLIDAYS:
        matched_date: date | None = None
        for iso_date, info in days.items():
            name = info.get("name") or ""
            if keyword in name:
                matched_date = date.fromisoformat(iso_date)
                break
        if matched_date is None or matched_date != today_local:
            continue

        notification_key = _notification_key(slug, 0)
        if _already_sent(db, notification_key, year):
            continue

        text = f"{emoji} 今天是{label}，記得跟家人說聲節日快樂！"
        _broadcast(db, telegram_client, text)
        _mark_sent(db, notification_key, year)
