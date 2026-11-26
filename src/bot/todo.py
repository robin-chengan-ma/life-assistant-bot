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
自己）。待辦是一次性事件，不像生日每年重複，所以不沿用生日那套以 `important_notifications_log`
（notification_key + year）去重的機制，改成直接在 `todos` 這張表自己記錄「這一筆待辦、哪些
offset 已經推播過」：`reminded_offsets_sent INTEGER[]`，取代舊的單一時間戳 `reminded_sent_at`。
國定假日推播（`src/bot/national_holidays.py`）維持不變，仍然只在當天推播，不提供提前通知。

**資料表欄位假設（給遷移 agent 對照）：**
    todos(
        id                      BIGSERIAL PRIMARY KEY,
        user_id                 BIGINT NOT NULL,       -- 對應 users.id
        content                 TEXT NOT NULL,
        remind_start_date       DATE NOT NULL,         -- 提醒區間的第一天（單日待辦 = remind_end_date）
        remind_end_date         DATE NOT NULL,         -- 提醒區間的最後一天
        remind_offsets          INTEGER[] NOT NULL,    -- 提前幾天推播，{0,3,7,14} 的非空子集合
        reminded_offsets_sent   INTEGER[] NOT NULL,    -- 這筆待辦已經推播過的 offset 清單（去重用）
        created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
    )

推播機制沿用既有做法：沒有獨立排程系統，借用 `/healthz` 既有的固定頻率 cron，由 `main.py` 每次
被呼叫時觸發 `check_and_push_reminders()`；去重狀態存在資料列本身（`reminded_offsets_sent`），
不用記憶體 instance state，撐得過 Render 重啟。
"""

from __future__ import annotations

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
    """查詢某使用者所有待辦提醒，依提醒開始日期由近到遠排序。"""
    rows = db.select("todos", where="user_id = %s", params=(user_id,))
    return sorted(rows, key=lambda row: row["remind_start_date"])


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


def check_and_push_reminders(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """針對每一筆待辦、針對它設定的每一個 `remind_offsets`，分別計算「`remind_start_date` - offset
    天」是否等於今天（台灣時區），且現在時間落在台灣時間 08:30 附近視窗內，是的話推播給建立者本人
    （待辦一律僅限自己，不像生日設定可選推播對象，見本模組 2026-11-26 條目）。

    去重狀態存在 `todos.reminded_offsets_sent`（這筆待辦已經推播過的 offset 清單），同一個 offset
    只會推播一次；待辦是一次性事件，不像生日每年重複，所以不需要、也不沿用生日那套以年份區分的
    `important_notifications_log` 去重機制。

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
