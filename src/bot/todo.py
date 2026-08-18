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

2026-08-02 新增（見 robinson SPEC.md FR-31b）：區間待辦事項。Robin 提出「待辦事項是不是只能存
單一時間點，不能存像『8/2 08:00 ~ 8/5 17:00』這種區間」的疑問，確認需要支援後新增可選的
`start_at` 欄位（`0016_add_start_at_to_todos.sql`）：NULL 代表沿用原本單一時間點待辦的語意，
非 NULL 時代表這是區間待辦，`due_at` 改為代表區間的結束/截止時間。設計決策（經 AskUserQuestion
確認）：①「前 30 分鐘提醒」對區間待辦以 `start_at`（開始時間）為基準，提醒「準備要開始了」，
單一時間點待辦不受影響、仍以 `due_at` 為基準 ②「每日 08:00 摘要」對區間待辦只在「開始那天」與
「結束那天」各出現一次（不會在區間中間每天都出現），因此 `daily_pushed_on` 的去重判斷從「曾經
推播過就不再推播」改為「今天是否已經推播過」，讓同一筆待辦可以在開始日、結束日分別各推播一次
（單一時間點待辦因為 `due_at` 只會落在單一天，語意不受影響，仍然只會推播一次）。
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_REMINDER_WINDOW = timedelta(minutes=30)


def create_todo(
    db: CloudSQLClient,
    user_id: int,
    content: str,
    due_at: datetime,
    remind_before_30min: bool,
    start_at: datetime | None = None,
    sync_to_calendar: bool = False,
) -> int:
    """新增一筆待辦事項，回傳新建列的 id。

    `start_at`（FR-31b）為 None 時是單一時間點待辦（沿用原本語意，`due_at` 就是預定執行時間）；
    非 None 時是區間待辦，`due_at` 代表區間的結束/截止時間。

    `sync_to_calendar`（2026-08-05，見 robinson SPEC.md FR-66a、ADR-17）：使用者在建立流程中
    明確選擇要不要同步到 Google 家庭共用行事曆，MVP 不支援事後修改（要同步就取消重建一筆）；
    實際建立 Calendar 事件、寫回 `google_calendar_event_id` 是呼叫端（`src/bot/commands.py`）
    的責任，本函式只負責記下這個布林選擇。
    """
    return db.insert(
        "todos",
        {
            "user_id": user_id,
            "content": content,
            "due_at": due_at,
            "remind_before_30min": remind_before_30min,
            "status": "pending",
            "start_at": start_at,
            "sync_to_calendar": sync_to_calendar,
        },
    )


def set_calendar_event_id(db: CloudSQLClient, todo_id: int, event_id: str) -> None:
    """記錄這筆待辦事項對應的 Google Calendar 事件 ID（FR-66a），供之後標記完成/取消時刪除對應事件。"""
    db.update("todos", {"google_calendar_event_id": event_id}, where="id = %s", params=(todo_id,))


def list_pending_todos(db: CloudSQLClient, user_id: int) -> list[dict]:
    """查詢某使用者目前所有待處理（status='pending'）的待辦事項，依預定時間由近到遠排序。"""
    rows = db.select("todos", where="user_id = %s AND status = %s", params=(user_id, "pending"))
    return sorted(rows, key=lambda row: row["due_at"])


def _format_when(item: dict) -> str:
    """把單一時間點或區間格式化成使用者看的時間文字（FR-31b），供清單顯示共用。"""
    due_local = item["due_at"].astimezone(_TAIWAN_TZ)
    start_at = item.get("start_at")
    if start_at is None:
        return f"{due_local:%Y/%m/%d %H:%M}"
    start_local = start_at.astimezone(_TAIWAN_TZ)
    return f"{start_local:%Y/%m/%d %H:%M} ～ {due_local:%Y/%m/%d %H:%M}"


def format_todo_list(todos: list[dict]) -> str:
    """把待辦事項清單格式化成使用者看的編號清單文字，供查詢與完成/取消流程共用。"""
    if not todos:
        return "目前沒有待辦事項喔！"
    lines = ["這是你目前的待辦事項：", ""]
    for index, item in enumerate(todos, start=1):
        lines.append(f"{index}. {item['content']}（{_format_when(item)}）")
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

    找出「使用者記錄當下選擇要提醒、還沒推播過、且提醒基準時間落在未來 30 分鐘內」的待辦逐一推播，
    推播後立刻標記 `reminded_30min_sent_at`，避免下一次 `/healthz`（10 分鐘後）被重複推播。找不到
    對應 `telegram_user_id`（理論上不該發生，防禦性處理）的直接跳過，不中斷其餘待辦的推播。

    提醒基準時間（FR-31b）：區間待辦（`start_at` 非 NULL）以 `start_at` 為準（提醒「準備要開始
    了」），單一時間點待辦仍以 `due_at` 為準，語意不變。
    """
    now = now or datetime.now(timezone.utc)
    window_end = now + _REMINDER_WINDOW
    due_soon = db.select(
        "todos",
        where=(
            "status = %s AND remind_before_30min = %s AND reminded_30min_sent_at IS NULL "
            "AND COALESCE(start_at, due_at) > %s AND COALESCE(start_at, due_at) <= %s"
        ),
        params=("pending", True, now, window_end),
    )
    for item in due_soon:
        user = db.select("users", where="id = %s", params=(item["user_id"],), fetch_one=True)
        if user is None or user.get("telegram_user_id") is None:
            continue
        from src.bot.schedule_settings import is_notification_enabled
        if not is_notification_enabled(db, user["id"], "todo"):
            continue
        start_at = item.get("start_at")
        due_local = item["due_at"].astimezone(_TAIWAN_TZ)
        if start_at is None:
            text = f"⏰ 提醒你，{due_local:%H:%M} 要「{item['content']}」囉，30 分鐘後就到時間了！"
        else:
            start_local = start_at.astimezone(_TAIWAN_TZ)
            text = (
                f"⏰ 提醒你，「{item['content']}」再過 30 分鐘就要開始囉"
                f"（{start_local:%m/%d %H:%M} ～ {due_local:%m/%d %H:%M}）"
            )
        telegram_client.send_text(chat_id=user["telegram_user_id"], text=text)
        db.update("todos", {"reminded_30min_sent_at": now}, where="id = %s", params=(item["id"],))


def check_and_push_daily_digest(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """FR-32：每日 08:00 固定推播。

    只在台灣時間 08 點這個小時內執行（`/healthz` 每 10 分鐘觸發一次，這個小時內會命中好幾次，
    靠 `daily_pushed_on` 這個欄位避免同一天內重複推播）；把每位使用者「今天有事發生、今天還沒
    推播過」的待辦事項彙整成一則訊息各自推播，推播後把這幾筆的 `daily_pushed_on` 標記為今天。

    「今天有事發生」（FR-31b）：單一時間點待辦是 `due_at` 落在今天；區間待辦是「今天開始」或
    「今天結束」（兩者都算，區間中間的日期不算）。去重判斷刻意從「曾經推播過就不再推播」
    （`daily_pushed_on IS NULL`）改為「今天是否已經推播過」（`daily_pushed_on IS NULL OR
    daily_pushed_on != 今天`），讓區間待辦可以在開始日、結束日分別各推播一次；單一時間點待辦
    因為 `due_at` 只會落在單一天，這個改動不影響其原本「只推播一次」的語意。
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
        where=(
            "status = %s AND ((due_at >= %s AND due_at < %s) OR (start_at >= %s AND start_at < %s)) "
            "AND (daily_pushed_on IS NULL OR daily_pushed_on != %s)"
        ),
        params=("pending", day_start, day_end, day_start, day_end, today_local),
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
        from src.bot.schedule_settings import is_notification_enabled
        if not is_notification_enabled(db, user_id, "todo"):
            continue
        lines = ["📋 早安，這是你今天的待辦事項：", ""]
        for item in sorted(items, key=lambda row: row["due_at"]):
            lines.append(f"- {item['content']}（{_format_digest_when(item, today_local)}）")
        telegram_client.send_text(chat_id=user["telegram_user_id"], text="\n".join(lines))
        for item in items:
            db.update("todos", {"daily_pushed_on": today_local}, where="id = %s", params=(item["id"],))


def _format_digest_when(item: dict, today_local) -> str:
    """每日摘要單行的時間文字（FR-31b）：單一時間點待辦沿用原本只顯示時間的格式；區間待辦依
    今天是區間的開始日、結束日、還是頭尾同一天（一日內的區間），分別給出對應的說法。
    """
    due_local = item["due_at"].astimezone(_TAIWAN_TZ)
    start_at = item.get("start_at")
    if start_at is None:
        return f"{due_local:%H:%M}"

    start_local = start_at.astimezone(_TAIWAN_TZ)
    starts_today = start_local.date() == today_local
    due_today = due_local.date() == today_local
    if starts_today and due_today:
        return f"今天 {start_local:%H:%M} ～ {due_local:%H:%M}"
    if starts_today:
        return f"今天 {start_local:%H:%M} 開始，到 {due_local:%m/%d %H:%M} 截止"
    return f"今天截止 {due_local:%H:%M}，從 {start_local:%m/%d %H:%M} 開始"
