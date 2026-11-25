"""待辦事項：純粹的一次性日期＋文字提醒推播，不含任何「完成/取消/逾期」狀態。

2026-11（功能大幅精簡，Robin 明確決策）：「待辦事項只是純粹去做通知而已，不需要確認動作，
不想增加使用者負擔」——拿掉舊版的 `status`（pending/completed/cancelled/expired）、
`mark_overdue_as_expired()`、區間待辦（`start_at`）、30 分鐘前提醒、每日 08:00 摘要、Google
Calendar 同步等所有複雜度，只留下「這個時間到了，推播一次這段文字」。新增/編輯/刪除待辦事項
全部改到 Mobile App 做，Telegram 端只負責推播。

**資料表欄位假設（給遷移 agent 對照；既有 `todos` 資料允許整個清空重建，不需要保留/搬移舊資料，
本次只假設下列最小欄位）：**
    todos(
        id               BIGSERIAL PRIMARY KEY,
        user_id          BIGINT NOT NULL,       -- 對應 users.id
        content          TEXT NOT NULL,
        remind_at        TIMESTAMPTZ NOT NULL,  -- 要推播提醒的時間點
        reminded_sent_at TIMESTAMPTZ,           -- 推播去重記號，NULL 代表還沒推播過
        created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
    )

推播機制沿用既有做法：沒有獨立排程系統，借用 `/healthz` 既有的固定頻率 cron，由 `main.py` 每次
被呼叫時觸發 `check_and_push_reminders()`；去重狀態存在資料列本身（`reminded_sent_at`），不用
記憶體 instance state，撐得過 Render 重啟。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
# 提醒時間落在「現在」之前、或未來這個時間窗之內，就視為「該推播了」；窗口大小抓住 `/healthz`
# 觸發頻率（每 10～30 分鐘一次）即可，不需要跟舊版一樣算「前 N 分鐘預告」。
_REMINDER_WINDOW = timedelta(minutes=30)


def list_todos(db: CloudSQLClient, user_id: int) -> list[dict]:
    """查詢某使用者所有待辦提醒，依提醒時間由近到遠排序。"""
    rows = db.select("todos", where="user_id = %s", params=(user_id,))
    return sorted(rows, key=lambda row: row["remind_at"])


def format_todo_list(todos: list[dict]) -> str:
    """把待辦提醒清單格式化成使用者看的編號清單文字。"""
    if not todos:
        return "目前沒有待辦提醒喔！"
    lines = ["目前的待辦提醒：", ""]
    for index, item in enumerate(todos, start=1):
        when_local = item["remind_at"].astimezone(_TAIWAN_TZ)
        lines.append(f"{index}. {item['content']}（{when_local:%Y/%m/%d %H:%M}）")
    return "\n".join(lines)


def push_reminder(telegram_client, chat_id: int, text: str) -> None:
    """送出一則推播提醒訊息，由待辦事項與生日設定共用，避免兩邊各自重複一份發送程式碼。"""
    telegram_client.send_text(chat_id=chat_id, text=text)


def check_and_push_reminders(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """找出「提醒時間已到、還沒推播過」的待辦逐一推播，推播後立刻標記 `reminded_sent_at`。

    找不到對應 `telegram_user_id`（理論上不該發生，防禦性處理）的直接跳過，不中斷其餘待辦的推播。
    """
    now = now or datetime.now(UTC)
    window_end = now + _REMINDER_WINDOW
    due = db.select(
        "todos",
        where="reminded_sent_at IS NULL AND remind_at <= %s",
        params=(window_end,),
    )
    for item in due:
        user = db.select("users", where="id = %s", params=(item["user_id"],), fetch_one=True)
        if user is None or user.get("telegram_user_id") is None:
            continue
        when_local = item["remind_at"].astimezone(_TAIWAN_TZ)
        text = f"⏰ 提醒你，{when_local:%Y/%m/%d %H:%M} 要「{item['content']}」囉！"
        push_reminder(telegram_client, user["telegram_user_id"], text)
        db.update("todos", {"reminded_sent_at": now}, where="id = %s", params=(item["id"],))
