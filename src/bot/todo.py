"""待辦事項純邏輯（對應 docs/specs/robinson/SPEC.md FR-31、FR-31a、FR-32，Step 1.7）。

負責：新增/查詢/標記完成或取消、逾期自動標記（FR-31a）、兩種推播判斷（FR-32）。
不處理任何 Telegram 對話流程或 LLM 呼叫（那是 src/bot/chat.py、src/bot/commands.py 的責任），
保持這個模組是純粹的資料操作，方便獨立測試。

FR-32 推播時機有三種：①使用者主動查詢 → 直接呼叫 `list_pending_todos()`，由呼叫端（`commands.py`）
組成清單文字；②每日 08:00 固定推播；③預定時間前 30 分鐘提醒。②③兩種主動推播沒有獨立的排程系統，
比照 Step 1.6 `monitoring.NeonCapacityMonitor` 的做法，借用 `/healthz` 既有的 10 分鐘 cron 頻率，
由 `main.py` 在每次 `/healthz` 被呼叫時觸發 `check_and_push_reminders()`／`check_and_push_daily_digest()`。

去重狀態刻意存在 `todos` 資料列本身（`reminded_30min_sent_at`／`daily_pushed_on`），不用記憶體
instance state（跟 Step 1.6 `NeonCapacityMonitor` 用 instance state 的取捨不同）：Render 免費方案
可能不定期重啟，重啟會清空記憶體狀態，但待辦提醒「不能漏推、也不能重複推」的正確性比 Neon 容量告警
更重要，值得多花欄位換取跨重啟的持久性，詳見 `src/schema/db_schema.md` 的 `todos` 表設計理由。

FR-31 提到的跨模組歧義判斷（例如「打籃球」要反問是體態管理還是待辦事項）Phase 1 刻意不實作：
體態管理要等 Phase 2 才會做、心情小記 Step 1.8 也還沒做，目前沒有其他已完成的模組可以拿來比較，
待那些模組做出來後再回頭補上（2026-08-02 與 Robin 討論確認）。
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_REMINDER_WINDOW = timedelta(minutes=30)


def create_todo(
    db: CloudSQLClient, user_id: int, content: str, due_at: datetime, remind_before_30min: bool
) -> int:
    """新增一筆待辦事項，回傳新建列的 id。"""
    return db.insert(
        "todos",
        {
            "user_id": user_id,
            "content": content,
            "due_at": due_at,
            "remind_before_30min": remind_before_30min,
            "status": "pending",
        },
    )


def list_pending_todos(db: CloudSQLClient, user_id: int) -> list[dict]:
    """查詢某使用者目前所有待處理（status='pending'）的待辦事項，依預定時間由近到遠排序。"""
    rows = db.select("todos", where="user_id = %s AND status = %s", params=(user_id, "pending"))
    return sorted(rows, key=lambda row: row["due_at"])


def format_todo_list(todos: list[dict]) -> str:
    """把待辦事項清單格式化成使用者看的編號清單文字，供查詢與完成/取消流程共用。"""
    if not todos:
        return "目前沒有待辦事項喔！"
    lines = ["這是你目前的待辦事項：", ""]
    for index, item in enumerate(todos, start=1):
        due_local = item["due_at"].astimezone(_TAIWAN_TZ)
        lines.append(f"{index}. {item['content']}（{due_local:%Y/%m/%d %H:%M}）")
    return "\n".join(lines)


def mark_status(db: CloudSQLClient, todo_id: int, status: str) -> None:
    """把指定待辦事項標記為 completed／cancelled（使用者明確表示，FR-31a）。"""
    db.update("todos", {"status": status}, where="id = %s", params=(todo_id,))


def mark_overdue_as_expired(db: CloudSQLClient, now: datetime | None = None) -> int:
    """FR-31a：把已超過預定執行時間、仍是 pending 狀態的待辦統一標記為 expired，回傳受影響筆數。

    標記後就不會再出現在 `list_pending_todos()` 的清單或後續推播中（兩者查詢條件都限定
    `status = 'pending'`）。
    """
    now = now or datetime.now(timezone.utc)
    return db.update("todos", {"status": "expired"}, where="status = %s AND due_at < %s", params=("pending", now))


def check_and_push_reminders(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """FR-32：預定時間前 30 分鐘提醒。

    找出「使用者記錄當下選擇要提醒、還沒推播過、且落在未來 30 分鐘內」的待辦逐一推播，推播後
    立刻標記 `reminded_30min_sent_at`，避免下一次 `/healthz`（10 分鐘後）被重複推播。找不到對應
    `telegram_user_id`（理論上不該發生，防禦性處理）的直接跳過，不中斷其餘待辦的推播。
    """
    now = now or datetime.now(timezone.utc)
    window_end = now + _REMINDER_WINDOW
    due_soon = db.select(
        "todos",
        where=(
            "status = %s AND remind_before_30min = %s AND reminded_30min_sent_at IS NULL "
            "AND due_at > %s AND due_at <= %s"
        ),
        params=("pending", True, now, window_end),
    )
    for item in due_soon:
        user = db.select("users", where="id = %s", params=(item["user_id"],), fetch_one=True)
        if user is None or user.get("telegram_user_id") is None:
            continue
        due_local = item["due_at"].astimezone(_TAIWAN_TZ)
        telegram_client.send_text(
            chat_id=user["telegram_user_id"],
            text=f"⏰ 提醒你，{due_local:%H:%M} 要「{item['content']}」囉，30 分鐘後就到時間了！",
        )
        db.update("todos", {"reminded_30min_sent_at": now}, where="id = %s", params=(item["id"],))


def check_and_push_daily_digest(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """FR-32：每日 08:00 固定推播。

    只在台灣時間 08 點這個小時內執行（`/healthz` 每 10 分鐘觸發一次，這個小時內會命中好幾次，
    靠 `daily_pushed_on IS NULL` 這個條件避免重複推播）；把每位使用者「今天到期、還沒推播過」的
    待辦事項彙整成一則訊息各自推播，推播後把這幾筆的 `daily_pushed_on` 標記為今天。
    """
    now = now or datetime.now(timezone.utc)
    now_local = now.astimezone(_TAIWAN_TZ)
    if now_local.hour != 8:
        return

    today_local = now_local.date()
    day_start = datetime.combine(today_local, datetime.min.time(), tzinfo=_TAIWAN_TZ)
    day_end = day_start + timedelta(days=1)

    due_today = db.select(
        "todos",
        where="status = %s AND due_at >= %s AND due_at < %s AND daily_pushed_on IS NULL",
        params=("pending", day_start, day_end),
    )
    if not due_today:
        return

    by_user_id: dict[int, list[dict]] = {}
    for item in due_today:
        by_user_id.setdefault(item["user_id"], []).append(item)

    for user_id, items in by_user_id.items():
        user = db.select("users", where="id = %s", params=(user_id,), fetch_one=True)
        if user is None or user.get("telegram_user_id") is None:
            continue
        lines = ["📋 早安，這是你今天的待辦事項：", ""]
        for item in sorted(items, key=lambda row: row["due_at"]):
            due_local = item["due_at"].astimezone(_TAIWAN_TZ)
            lines.append(f"- {item['content']}（{due_local:%H:%M}）")
        telegram_client.send_text(chat_id=user["telegram_user_id"], text="\n".join(lines))
        for item in items:
            db.update("todos", {"daily_pushed_on": today_local}, where="id = %s", params=(item["id"],))
