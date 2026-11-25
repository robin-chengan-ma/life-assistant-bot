"""「生日設定」：Telegram 唯一保留的「重要日子」概念，只剩下每年固定（國曆）月/日重複一次的生日。

2026-11（功能大幅精簡）：舊版「重要日子」支援單次事件、浮動（農曆）日期、通知對象、備註、跟
行程/目標連動等等，隨著 Telegram 選單整個拿掉而一併簡化——所有「新增/編輯/查詢」操作改到 Mobile
App 做，這個模組在 Telegram 端只剩下：
1. 讀生日清單、算出「今天是不是誰的生日」，供排程（`check_and_push_birthdays()`）主動推播用。
2. 跟 `src/bot/todo.py` 共用同一顆「組訊息＋送出＋標記已推播」的 helper（`todo.push_reminder()`），
   避免兩邊各自重複一份幾乎一樣的 Telegram 推播程式碼。

**資料表欄位假設（給遷移 agent 對照，刻意只假設下列欄位，不假設其餘任何欄位還在，例如
`recurrence_type`／`audience_mode`／`trip_id`／`goal_id` 等舊欄位本模組完全不讀不寫）：**
    important_days(
        id          BIGSERIAL PRIMARY KEY,
        user_id     BIGINT NOT NULL,   -- 建立者（owner），對應 users.id
        name        TEXT NOT NULL,     -- 誰的生日，例如「媽媽」
        birth_month INT NOT NULL,      -- 1~12
        birth_day   INT NOT NULL,      -- 1~31（依月份有效範圍）
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
現有資料務必保留（不可因為這次簡化被清空），遷移只需要確保上述欄位存在、把不再使用的欄位
（`recurrence_type` 等）去掉或留著都不影響本模組運作。

推播去重沿用既有的 `important_notifications_log` 表（`notification_key` 這次用
`f"birthday_important_day_{important_day_id}"`，`UNIQUE (notification_key, year)` 確保同一年
只推播一次），這張表本次沒有改動。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.bot import todo
from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")


def list_birthdays(db: CloudSQLClient, user_id: int) -> list[dict]:
    """查詢某使用者建立的所有生日設定，依月/日排序。"""
    rows = db.select("important_days", where="user_id = %s", params=(user_id,))
    return sorted(rows, key=lambda row: (row["birth_month"], row["birth_day"]))


def format_birthday_list(rows: list[dict]) -> str:
    """把生日清單格式化成文字，供 Owner 權限管理以外、其餘若有需要顯示清單的地方共用。"""
    if not rows:
        return "目前還沒有任何生日設定，請到 App 新增！"
    lines = ["目前的生日設定：", ""]
    for index, row in enumerate(rows, start=1):
        lines.append(f"{index}. {row['name']}（{row['birth_month']}/{row['birth_day']}）")
    return "\n".join(lines)


def _notification_key(important_day_id: int) -> str:
    return f"birthday_important_day_{important_day_id}"


def check_and_push_birthdays(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """每日排程：今天是國曆幾月幾日，就把當天生日的設定逐一推播給建立者本人。

    去重用 `important_notifications_log`（`notification_key` + `year` 唯一），同一年只推播一次，
    即使 `/healthz` 同一天內觸發多次也不會重複推播；跟 `src/bot/todo.py` 共用
    `todo.push_reminder()` 這個送出 Telegram 訊息的 helper。
    """
    now = now or datetime.now(tz=_TAIWAN_TZ)
    today_local = now.astimezone(_TAIWAN_TZ)
    year = today_local.year

    rows = db.select(
        "important_days",
        where="birth_month = %s AND birth_day = %s",
        params=(today_local.month, today_local.day),
    )
    for row in rows:
        notification_key = _notification_key(row["id"])
        already_sent = db.select(
            "important_notifications_log",
            where="notification_key = %s AND year = %s",
            params=(notification_key, year),
            fetch_one=True,
        )
        if already_sent:
            continue

        user = db.select("users", where="id = %s", params=(row["user_id"],), fetch_one=True)
        if user is None or user.get("telegram_user_id") is None:
            continue

        text = f"🎂 今天是「{row['name']}」的生日，別忘了祝福一下！"
        todo.push_reminder(telegram_client, user["telegram_user_id"], text)
        db.insert("important_notifications_log", {"notification_key": notification_key, "year": year})
