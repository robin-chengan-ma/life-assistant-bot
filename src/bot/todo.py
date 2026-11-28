"""待辦事項：純粹的一次性日期（可為區間）＋文字提醒推播，不含任何「完成/取消/逾期」狀態。

2026-11（功能大幅精簡，Robin 明確決策）：「待辦事項只是純粹去做通知而已，不需要確認動作，
不想增加使用者負擔」——拿掉舊版的 `status`（pending/completed/cancelled/expired）、
`mark_overdue_as_expired()`、30 分鐘前提醒、每日 08:00 摘要、Google Calendar 同步等所有複雜度，
只留下「這個時間到了，推播一次這段文字」。新增/編輯/刪除待辦事項全部改到 Mobile App 做，
Telegram 端只負責推播。

2026-11-26（待辦改日期區間＋行事曆，見 migration 0106、docs/ADR/discuss/robinson.md）：單一
`remind_at`（固定 09:00）改成 `remind_start_date`／`remind_end_date` 兩個日期（單日待辦＝兩者
相同），恢復行事曆 UI 選取區間；推播固定改成「第一天（`remind_start_date`）早上 08:30」，不再
是使用者自訂時間。

2026-11-26（待辦提前提醒，見 migration 0109）：Robin 要求待辦的提前提醒邏輯跟生日設定一模一樣
（可複選「14／7／3／當天」天前推播），但不需要推播對象選擇——待辦一律只推給建立者本人（僅限
自己）。待辦（`once` 類型）是一次性事件，不像生日每年重複，所以不沿用生日那套以
`important_notifications_log`（notification_key + year）去重的機制，改成直接在 `todos` 這張表
自己記錄「這一筆待辦、哪些 offset 已經推播過」：`reminded_offsets_sent INTEGER[]`，取代舊的單一
時間戳 `reminded_sent_at`。國定假日推播（`src/bot/national_holidays.py`）維持不變，仍然只在當天
推播，不提供提前通知。

2026-11-28（待辦支援「常態性（每月固定一天）」，見 migration 0110、docs/ADR/discuss/robinson.md）：
Robin 要求信用卡／車貸這類每月固定某一天要繳費的待辦，不用每次手動新增一筆；新增 `recurrence_type`
（`once`／`monthly`）與 `recurrence_day`（1~31）。`monthly` 類型每個月都會重複發生，不像 `once`
是「一次性」，所以不能沿用 `reminded_offsets_sent` 這種「整筆待辦記一次就永久關閉」的去重法——改
沿用生日那套 `important_notifications_log`（`notification_key` + `year` 唯一），把 `year` 欄位
借用存「年份*100+月份」（例如 2026 年 12 月存 202612）當作「這個月的這個 offset 推播過沒」的去重
鍵，讓同一筆常態性待辦每個月都能重新推播一次。`recurrence_day` 超過當月實際天數時（例如 31 號遇到
只有 28/29/30 天的月份）退回當月最後一天，跟生日 2/29 的處理方式一致。

**資料表欄位假設（給遷移 agent 對照）：**
    todos(
        id                      BIGSERIAL PRIMARY KEY,
        user_id                 BIGINT NOT NULL,       -- 對應 users.id
        content                 TEXT NOT NULL,
        remind_start_date       DATE,                  -- recurrence_type=once 時：提醒區間第一天；monthly 時 NULL
        remind_end_date         DATE,                  -- recurrence_type=once 時：提醒區間最後一天；monthly 時 NULL
        recurrence_type         TEXT NOT NULL,         -- once（一次性）／monthly（每月固定一天）
        recurrence_day          INTEGER,               -- recurrence_type=monthly 時：1~31 的每月固定日期
        remind_offsets          INTEGER[] NOT NULL,    -- 提前幾天推播，{0,3,7,14} 的非空子集合
        reminded_offsets_sent   INTEGER[] NOT NULL,    -- once 類型專用去重：這筆待辦已經推播過的 offset 清單
        created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
    )

推播機制沿用既有做法：沒有獨立排程系統，借用 `/healthz` 既有的固定頻率 cron，由 `main.py` 每次
被呼叫時觸發 `check_and_push_reminders()`；`once` 類型去重狀態存在資料列本身
（`reminded_offsets_sent`），`monthly` 類型去重狀態存在共用的 `important_notifications_log`，
兩者都落地 DB（非記憶體 instance state），撐得過 Render 重啟。
"""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
# 固定推播時刻：第一天台灣時間 08:30（決策，見本模組 2026-11-26 條目）。
_REMINDER_HOUR = 8
_REMINDER_MINUTE = 30
# 「現在」落在這個視窗之內，就視為「該推播了」；窗口大小抓住 `/healthz` 觸發頻率
# （每 10～30 分鐘一次）即可。
_REMINDER_WINDOW = timedelta(minutes=30)
_ALLOWED_REMIND_OFFSETS = (0, 3, 7, 14)


def list_todos(db: CloudSQLClient, user_id: int) -> list[dict]:
    """查詢某使用者所有待辦提醒，一次性依提醒開始日期排序在前，常態性依每月固定日期排序在後。"""
    rows = db.select("todos", where="user_id = %s", params=(user_id,))
    return sorted(
        rows,
        key=lambda row: (1, row["recurrence_day"]) if row.get("recurrence_type") == "monthly" else (0, row["remind_start_date"]),
    )


def _format_date_range(start: date, end: date) -> str:
    if start == end:
        return f"{start:%Y/%m/%d}"
    return f"{start:%Y/%m/%d}～{end:%Y/%m/%d}"


def format_todo_list(todos: list[dict]) -> str:
    """把待辦提醒清單格式化成使用者看的編號清單文字。"""
    if not todos:
        return "目前沒有待辦提醒喔！"
    lines = ["目前的待辦提醒：", ""]
    for index, item in enumerate(todos, start=1):
        if item.get("recurrence_type") == "monthly":
            date_text = f"每月 {item['recurrence_day']} 號"
        else:
            date_text = _format_date_range(item["remind_start_date"], item["remind_end_date"])
        lines.append(f"{index}. {item['content']}（{date_text}）")
    return "\n".join(lines)


def push_reminder(telegram_client, chat_id: int, text: str) -> None:
    """送出一則推播提醒訊息，由待辦事項與生日設定共用，避免兩邊各自重複一份發送程式碼。"""
    telegram_client.send_text(chat_id=chat_id, text=text)


def _format_reminder_text(content: str, date_text: str, offset: int) -> str:
    if offset == 0:
        return f"⏰ 提醒你，{date_text} 要「{content}」囉！"
    return f"⏰ {offset} 天後（{date_text}）要「{content}」，提前通知你！"


def _monthly_occurrence_date(recurrence_day: int, year: int, month: int) -> date:
    """計算某年某月「每月固定 `recurrence_day` 號」實際對應的日期；該月天數不足時（例如 31 號
    遇到只有 30 天或更少的月份）退回當月最後一天，比照生日 2/29 的既有慣例處理。"""
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(recurrence_day, last_day))


def _monthly_notification_key(todo_id: int, offset: int) -> str:
    return f"todo_monthly_{todo_id}_offset_{offset}"


def _period_key(occurrence: date) -> int:
    """`important_notifications_log.year` 欄位借用存「年份*100+月份」當成常態性待辦的去重鍵，
    讓同一筆待辦每個月都能重新推播一次（跟生日沿用同一張表，但去重顆粒度從「年」改成「月」）。"""
    return occurrence.year * 100 + occurrence.month


def check_and_push_reminders(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """針對每一筆待辦、針對它設定的每一個 `remind_offsets`，計算是否該在今天（台灣時區）推播，
    且現在時間落在台灣時間 08:30 附近視窗內，是的話推播給建立者本人（待辦一律僅限自己，不像生日
    設定可選推播對象，見本模組 2026-11-26 條目）。

    - `once`（一次性）：判斷「`remind_start_date` - offset 天」是否等於今天；去重狀態存在
      `todos.reminded_offsets_sent`（這筆待辦已經推播過的 offset 清單），同一個 offset 只會
      推播一次，因為是一次性事件不會再重複。
    - `monthly`（常態性，見本模組 2026-11-28 條目）：判斷「這個月（或下個月，處理月初/月底跨月
      的提前提醒）的 `recurrence_day` 那天 - offset 天」是否等於今天；去重沿用生日那套
      `important_notifications_log`，讓同一個 offset 每個月都能重新推播一次。

    找不到對應 `telegram_user_id`（理論上不該發生，防禦性處理）的直接跳過，不中斷其餘待辦的推播。
    """
    now = now or datetime.now(UTC)
    now_local = now.astimezone(_TAIWAN_TZ)
    reminder_time_local = datetime.combine(now_local.date(), time(_REMINDER_HOUR, _REMINDER_MINUTE), tzinfo=_TAIWAN_TZ)
    if not (reminder_time_local <= now_local <= reminder_time_local + _REMINDER_WINDOW):
        return

    today_local = now_local.date()
    rows = db.select("todos")
    for item in rows:
        offsets = item.get("remind_offsets") or [0]
        is_monthly = item.get("recurrence_type") == "monthly"

        if is_monthly:
            _check_and_push_monthly_todo(db, telegram_client, item, offsets, today_local)
        else:
            _check_and_push_once_todo(db, telegram_client, item, offsets, today_local)


def _check_and_push_once_todo(db: CloudSQLClient, telegram_client, item: dict, offsets: list[int], today_local: date) -> None:
    already_sent = set(item.get("reminded_offsets_sent") or [])
    for offset in offsets:
        if offset not in _ALLOWED_REMIND_OFFSETS or offset in already_sent:
            continue
        if item["remind_start_date"] - timedelta(days=offset) != today_local:
            continue

        user = db.select("users", where="id = %s", params=(item["user_id"],), fetch_one=True)
        if user is None or user.get("telegram_user_id") is None:
            continue
        date_text = _format_date_range(item["remind_start_date"], item["remind_end_date"])
        text = _format_reminder_text(item["content"], date_text, offset)
        push_reminder(telegram_client, user["telegram_user_id"], text)
        already_sent.add(offset)
        db.update(
            "todos",
            {"reminded_offsets_sent": sorted(already_sent)},
            where="id = %s",
            params=(item["id"],),
        )


def _check_and_push_monthly_todo(db: CloudSQLClient, telegram_client, item: dict, offsets: list[int], today_local: date) -> None:
    recurrence_day = item["recurrence_day"]
    for offset in offsets:
        if offset not in _ALLOWED_REMIND_OFFSETS:
            continue
        # 同一筆常態性待辦在「這個月」或「下個月」都可能是即將到來的那一次（例如每月 3 號的待辦，
        # 提前 14 天就要在上個月月底開始提醒），比照生日同時檢查今年/明年的寫法。
        for year, month in ((today_local.year, today_local.month), _next_month(today_local.year, today_local.month)):
            occurrence = _monthly_occurrence_date(recurrence_day, year, month)
            if occurrence - timedelta(days=offset) != today_local:
                continue

            notification_key = _monthly_notification_key(item["id"], offset)
            period_key = _period_key(occurrence)
            already_sent = db.select(
                "important_notifications_log",
                where="notification_key = %s AND year = %s",
                params=(notification_key, period_key),
                fetch_one=True,
            )
            if already_sent:
                continue

            user = db.select("users", where="id = %s", params=(item["user_id"],), fetch_one=True)
            if user is None or user.get("telegram_user_id") is None:
                continue
            date_text = f"每月 {recurrence_day} 號"
            text = _format_reminder_text(item["content"], date_text, offset)
            push_reminder(telegram_client, user["telegram_user_id"], text)
            db.insert("important_notifications_log", {"notification_key": notification_key, "year": period_key})


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year, month + 1) if month < 12 else (year + 1, 1)
