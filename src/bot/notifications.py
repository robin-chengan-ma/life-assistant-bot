"""重要通知純邏輯（對應 docs/specs/robinson/SPEC.md FR-53，Step 2.3）。

負責：固定節日（元旦/父親節/母親節/掃墓提醒/中秋/端午/除夕/初一）的西曆日期計算、生日比對、
收件人排除邏輯（家人生日/父親節/母親節「主角不能收到」）、年度推播去重判斷與推播。不處理任何
Telegram 對話流程，那是 src/bot/commands.py 的責任（本模組只有「設定家人生日」用到的資料操作
函式跟 commands.py 共用）。

2026-08-04 經 AskUserQuestion 確認的設計決策：
① 農曆節日（除夕/初一/中秋/端午）改用 `lunarcalendar` 套件即時計算西曆日期（純 Python 計算、
   不需要網路），不維護每年日期對照表；父親節固定西曆 8/8、母親節固定西曆 5 月第二個星期日，
   同樣是計算得出，不需要對照表。
② 這些通知固定在台灣時間 08:00 推播（比照待辦事項每日摘要 `todo.check_and_push_daily_digest()`
   的慣例），借用 `/healthz` 既有的 10 分鐘 cron 頻率。
③ 父親節/母親節「主角不能收到」的排除邏輯，用 `users.role` 字串完全比對「爸爸」／「媽媽」；
   家人生日「主角不能收到」則用 `user_id` 排除生日當事人自己，其餘所有已綁定使用者（含 Robin）
   都算「大家」。

家人生日資料來源：`users.birthday`（`0028_add_birthday_to_users.sql`），只比對月/日，不比對年份
（`_matches_month_day()`）；已知的 5 位家人生日已由 Robin 提供並寫入 `0030_seed_family_birthdays.sql`，
其餘家人（弟媳/大妹婿/小妹婿/阿姨等）的生日待 Robin 之後用「設定家人生日」指令自行補上
（`set_family_birthday()`／`format_family_member_prompt()`，見 `commands.py`）。
"""
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from lunarcalendar import Converter, Lunar

from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_NOTIFICATION_HOUR = 8

_logger = logging.getLogger(__name__)


def _solar_to_date(solar) -> date:
    return date(solar.year, solar.month, solar.day)


def get_lunar_new_year_day1(year: int) -> date:
    """農曆正月初一對應的西曆日期。"""
    return _solar_to_date(Converter.Lunar2Solar(Lunar(year, 1, 1, isleap=False)))


def get_lunar_new_year_eve(year: int) -> date:
    """除夕：農曆初一的前一天。"""
    return get_lunar_new_year_day1(year) - timedelta(days=1)


def get_mid_autumn(year: int) -> date:
    """中秋節：農曆八月十五對應的西曆日期。"""
    return _solar_to_date(Converter.Lunar2Solar(Lunar(year, 8, 15, isleap=False)))


def get_dragon_boat(year: int) -> date:
    """端午節：農曆五月初五對應的西曆日期。"""
    return _solar_to_date(Converter.Lunar2Solar(Lunar(year, 5, 5, isleap=False)))


def get_fathers_day(year: int) -> date:
    """父親節：台灣固定西曆 8 月 8 日（諧音「爸爸」）。"""
    return date(year, 8, 8)


def get_mothers_day(year: int) -> date:
    """母親節：西曆 5 月第二個星期日。"""
    first_of_may = date(year, 5, 1)
    days_until_sunday = (6 - first_of_may.weekday()) % 7
    first_sunday = first_of_may + timedelta(days=days_until_sunday)
    return first_sunday + timedelta(days=7)


def get_new_year(year: int) -> date:
    """元旦：西曆 1 月 1 日。"""
    return date(year, 1, 1)


def get_tomb_sweeping_reminder(year: int) -> date:
    """清明掃墓提醒：固定西曆 3 月 1 日提醒「該選一天掃墓了」，不是清明節當天本身。"""
    return date(year, 3, 1)


# FR-53「重要通知（大家都收到）」與「超級重要通知（主角不能收到）」的固定節日清單。
# `exclude_role`：None 代表大家都收到；否則排除 `users.role` 等於這個字串的人（決策③）。
#   `calendar_summary`（2026-08-05，見 robinson SPEC.md FR-66b、ADR-17）：Google Calendar 全天
#   事件的標題，刻意跟 `message`（Telegram 推播用，含表情符號與口語化語氣）分開，事件標題保持
#   簡短中性。
FIXED_NOTIFICATIONS: list[dict] = [
    {
        "key": "new_year",
        "compute_date": get_new_year,
        "message": "🎉 新年快樂！祝大家新的一年順利！",
        "exclude_role": None,
        "calendar_summary": "元旦",
    },
    {
        "key": "lunar_new_year_eve",
        "compute_date": get_lunar_new_year_eve,
        "message": "🧧 除夕快樂！祝大家新年快樂，要包紅包了喔！",
        "exclude_role": None,
        "calendar_summary": "除夕",
    },
    {
        "key": "lunar_new_year_day1",
        "compute_date": get_lunar_new_year_day1,
        "message": "🧧 新年快樂！恭喜發財，記得包紅包喔！",
        "exclude_role": None,
        "calendar_summary": "初一",
    },
    {
        "key": "tomb_sweeping",
        "compute_date": get_tomb_sweeping_reminder,
        "message": "⛰️ 提醒大家，記得找一天回去掃墓喔！",
        "exclude_role": None,
        "calendar_summary": "清明掃墓提醒",
    },
    {
        "key": "mid_autumn",
        "compute_date": get_mid_autumn,
        "message": "🌕 中秋節快樂！記得關心家人中秋有沒有要一起烤肉/吃月餅喔！",
        "exclude_role": None,
        "calendar_summary": "中秋節",
    },
    {
        "key": "dragon_boat",
        "compute_date": get_dragon_boat,
        "message": "🐉 端午節快樂！記得關心家裡有沒有包粽子/吃粽子喔！",
        "exclude_role": None,
        "calendar_summary": "端午節",
    },
    {
        "key": "fathers_day",
        "compute_date": get_fathers_day,
        "message": "👨 今天是父親節，記得跟爸爸表達感謝喔！",
        "exclude_role": "爸爸",
        "calendar_summary": "父親節",
    },
    {
        "key": "mothers_day",
        "compute_date": get_mothers_day,
        "message": "👩 今天是母親節，記得跟媽媽表達感謝喔！",
        "exclude_role": "媽媽",
        "calendar_summary": "母親節",
    },
]


def _get_all_bound_users(db: CloudSQLClient) -> list[dict]:
    """查詢所有已綁定 `telegram_user_id` 的使用者（含 Robin），供固定節日推播用。"""
    return db.select("users", where="telegram_user_id IS NOT NULL")


def _get_users_with_birthday_today(db: CloudSQLClient, today: date) -> list[dict]:
    """查詢生日月/日跟今天相同的使用者，不比對年份。"""
    users = db.select("users", where="birthday IS NOT NULL")
    return [user for user in users if user["birthday"].month == today.month and user["birthday"].day == today.day]


def _is_already_sent(db: CloudSQLClient, notification_key: str, year: int) -> bool:
    row = db.select(
        "important_notifications_log",
        where="notification_key = %s AND year = %s",
        params=(notification_key, year),
        fetch_one=True,
    )
    return row is not None


def _mark_sent(db: CloudSQLClient, notification_key: str, year: int) -> None:
    db.insert("important_notifications_log", {"notification_key": notification_key, "year": year})


def _broadcast(telegram_client, recipients: list[dict], message: str) -> None:
    """推播給每一位收件人，單一使用者傳送失敗不影響其他人（比照 `commands.handle_recovered()`）。"""
    for user in recipients:
        try:
            telegram_client.send_text(chat_id=user["telegram_user_id"], text=message)
        except Exception:
            _logger.exception("重要通知推播給 telegram_user_id=%s 失敗", user.get("telegram_user_id"))


def _create_all_day_calendar_event(calendar_client, summary: str, on_date: date) -> None:
    """FR-66b：在指定日期建立 Google Calendar 全天事件；失敗優雅降級只記警告 log，不影響 Telegram
    推播本身（推播才是這個功能的主要目的，Calendar 只是額外的加值曝光）。
    """
    try:
        calendar_client.create_event(
            summary=summary,
            start=on_date.isoformat(),
            end=(on_date + timedelta(days=1)).isoformat(),
            all_day=True,
        )
    except Exception:
        _logger.exception("建立 Google Calendar 全天事件失敗（summary=%s，date=%s）", summary, on_date)


def check_and_push_important_notifications(
    db: CloudSQLClient, telegram_client, now: datetime | None = None, calendar_client=None
) -> None:
    """FR-53：檢查今天是否為固定節日或有人生日，是的話推播對應通知（決策②：只在台灣時間 08:00
    這個小時內執行，靠 `important_notifications_log` 的 `UNIQUE(notification_key, year)` 避免
    同一天內（cron 每 10 分鐘觸發）重複推播）。

    比照 `finance.check_and_push_finance_reminders()`／`body.check_and_push_goal_deadline_reminders()`
    的做法，借用 `/healthz` 既有的 10 分鐘 cron 頻率，不需要獨立的排程系統。

    `calendar_client`（2026-08-05，見 FR-66b、ADR-17）：選配，`None` 時（環境變數未設定）只推播
    Telegram、不建立 Calendar 事件。固定節日/生日本質上是要讓全家人知道的資訊，不像待辦事項／
    體態目標需要逐筆詢問是否同步（見 FR-66a），這裡判斷通過就直接建立，複用同一次
    `important_notifications_log` 去重判斷，不需要額外追蹤更新/刪除（節日/生日建立後幾乎不會
    變動，是刻意的簡化，見 ADR-17）。
    """
    now = now or datetime.now(timezone.utc)
    now_local = now.astimezone(_TAIWAN_TZ)
    if now_local.hour != _NOTIFICATION_HOUR:
        return
    today = now_local.date()
    year = today.year

    all_bound_users = _get_all_bound_users(db)

    for entry in FIXED_NOTIFICATIONS:
        target_date = entry["compute_date"](year)
        if target_date != today:
            continue
        if _is_already_sent(db, entry["key"], year):
            continue

        recipients = all_bound_users
        exclude_role = entry["exclude_role"]
        if exclude_role is not None:
            recipients = [user for user in recipients if user.get("role") != exclude_role]

        _broadcast(telegram_client, recipients, entry["message"])
        _mark_sent(db, entry["key"], year)
        if calendar_client is not None:
            _create_all_day_calendar_event(calendar_client, entry["calendar_summary"], target_date)

    for birthday_user in _get_users_with_birthday_today(db, today):
        notification_key = f"birthday_{birthday_user['id']}"
        if _is_already_sent(db, notification_key, year):
            continue

        recipients = [user for user in all_bound_users if user["id"] != birthday_user["id"]]
        message = f"🎂 今天是 {birthday_user['role']} 的生日，記得跟他/她說聲生日快樂喔！"
        _broadcast(telegram_client, recipients, message)
        _mark_sent(db, notification_key, year)
        if calendar_client is not None:
            _create_all_day_calendar_event(calendar_client, f"{birthday_user['role']} 生日", today)


# ---------------------------------------------------------------------------
# 設定家人生日（Owner 專屬，補齊尚未知道生日的家人資料）
# ---------------------------------------------------------------------------


def list_family_members(db: CloudSQLClient) -> list[dict]:
    """查詢所有已綁定的使用者（含 Robin），供「設定家人生日」流程選擇對象。"""
    return _get_all_bound_users(db)


def format_family_member_prompt(members: list[dict]) -> str:
    """組出讓使用者選擇要設定生日的家人編號清單文字。"""
    if not members:
        return "目前還沒有任何已綁定的使用者喔！"
    lines = ["要設定誰的生日呢？請幫我選一個：", ""]
    for index, member in enumerate(members, start=1):
        birthday = member.get("birthday")
        birthday_part = f"（目前：{birthday:%m/%d}）" if birthday else "（尚未設定）"
        lines.append(f"{index}. {member['role']}{birthday_part}")
    return "\n".join(lines)


def parse_birthday_input(text: str) -> date | None:
    """把使用者輸入的生日文字解析成日期；接受「YYYY-MM-DD」「YYYY/M/D」或只給「M/D」
    （不確定出生年份時可以只給月/日，年份用占位年 1900，比對生日一律只看月/日不看年份）。
    無法解析或日期不合理（例如 2/30）一律回傳 None，交由呼叫端反問。
    """
    text = text.strip()
    for separator in ("-", "/"):
        parts = text.split(separator)
        if len(parts) == 3:
            year_str, month_str, day_str = parts
            if year_str.isdigit() and month_str.isdigit() and day_str.isdigit():
                try:
                    return date(int(year_str), int(month_str), int(day_str))
                except ValueError:
                    return None
        if len(parts) == 2:
            month_str, day_str = parts
            if month_str.isdigit() and day_str.isdigit():
                try:
                    return date(1900, int(month_str), int(day_str))
                except ValueError:
                    return None
    return None


def set_birthday(db: CloudSQLClient, user_id: int, birthday: date) -> None:
    """設定/更新使用者的生日（FR-53）。"""
    db.update("users", {"birthday": birthday}, where="id = %s", params=(user_id,))
