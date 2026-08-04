"""記帳純邏輯（對應 docs/specs/robinson/SPEC.md FR-41～FR-44，Step 2.1）。

負責：預算目標設定/查詢、交易分類清單與解析、交易 CRUD（含補記/更新/刪除，從一開始就內建，
不像心情小記是事後補上，見 FR-49 變更記錄裡的說明）、月支出/收入加總、FR-43 門檻預警推播判斷、
FR-44 文字摘要組裝。不處理任何 Telegram 對話流程或 LLM 呼叫（那是 src/bot/commands.py 的責任），
保持這個模組是純粹的資料操作，方便獨立測試。

2026-08-04 經 AskUserQuestion 確認的設計決策：
① FR-41「理財目標」解讀為「每月支出預算上限」（一個數字），不是「每月儲蓄目標」，所以不需要
   算「收入-支出」的結餘去比對目標，直接比較「本月支出總額」與「預算上限」即可；但交易紀錄本身
   仍然「支出」「收入」兩種都做（見下方 `TRANSACTION_TYPES`），保留未來需要結餘概念時的彈性。
② 交易分類採固定清單（比照心情小記 6 選一的做法），支出/收入各自有一組清單，見
   `EXPENSE_CATEGORIES`／`INCOME_CATEGORIES`；分類文字直接存進 `transactions.category`
   （不像 mood_journals 用英文代碼＋中文標籤兩層，這裡分類清單全部是中文，沒有另外定代碼的必要）。
③ FR-43 兩個預警門檻的觸發時機：50% 門檻只在每月 15 日（含）以前檢查，代表「早期警示」；
   80% 門檻整月都會檢查，代表「嚴重警示，不管現在是月初還是月底都要提醒」；兩個門檻各自「每月
   最多推播一次」，去重狀態存在 `users.budget_alert_50_sent_month`／`budget_alert_80_sent_month`
   （比照 `todos.daily_pushed_on` 的做法，存在資料列本身而非記憶體，跨 Render 重啟仍正確）。
④ FR-44「定期視覺化支出/儲蓄趨勢」Phase 1 這版先做「使用者主動查詢時組成文字摘要」
   （`format_monthly_summary()`），不做圖表圖片、也不做主動排程推播月報——真正「定期」的部分
   由 FR-43 的門檻預警負責，摘要本身留待有實際使用需求後再考慮升級成圖表或排程推播。
"""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")

# FR-42 交易類型：expense=支出, income=收入，兩種都做（見本模組 docstring 決策①）。
TRANSACTION_TYPES: list[tuple[str, str]] = [("expense", "支出"), ("income", "收入")]
_TYPE_LABEL_BY_CODE = dict(TRANSACTION_TYPES)
_TYPE_CODE_BY_LABEL = {label: code for code, label in TRANSACTION_TYPES}

# 固定分類清單（決策②），對應 migration 0019 的 CHECK 約束。
EXPENSE_CATEGORIES: list[str] = ["餐飲", "交通", "購物", "居住", "娛樂", "醫療", "其他"]
INCOME_CATEGORIES: list[str] = ["薪資", "獎金", "其他"]

# FR-43 門檻，50% 只在每月 15 日（含）以前檢查，80% 整月都檢查（決策③）。
_MID_MONTH_ALERT_THRESHOLD = 0.5
_MID_MONTH_ALERT_DAY_CUTOFF = 15
_SEVERE_ALERT_THRESHOLD = 0.8


def format_type_prompt() -> str:
    """組出讓使用者選擇交易類型（支出/收入）的編號清單文字。"""
    lines = ["要記錄支出還是收入呢？", ""]
    for index, (_, label) in enumerate(TRANSACTION_TYPES, start=1):
        lines.append(f"{index}. {label}")
    return "\n".join(lines)


def resolve_type(text: str) -> str | None:
    """把使用者輸入解析成交易類型代碼；接受編號（1-2）或直接輸入「支出」「收入」。"""
    text = text.strip()
    if text.isdigit():
        index = int(text)
        if 1 <= index <= len(TRANSACTION_TYPES):
            return TRANSACTION_TYPES[index - 1][0]
        return None
    return _TYPE_CODE_BY_LABEL.get(text)


def type_label(code: str) -> str:
    """依代碼查回顯示用的中文標籤（「支出」／「收入」），供組回覆文字使用。"""
    return _TYPE_LABEL_BY_CODE[code]


def categories_for_type(transaction_type: str) -> list[str]:
    """依交易類型回傳對應的固定分類清單。"""
    return EXPENSE_CATEGORIES if transaction_type == "expense" else INCOME_CATEGORIES


def format_category_prompt(transaction_type: str) -> str:
    """組出讓使用者選擇分類的編號清單文字，依交易類型（支出/收入）給出不同清單。"""
    categories = categories_for_type(transaction_type)
    lines = [f"好的，那是哪個{type_label(transaction_type)}分類呢？請幫我選一個（輸入編號或直接打名稱）：", ""]
    for index, name in enumerate(categories, start=1):
        lines.append(f"{index}. {name}")
    return "\n".join(lines)


def resolve_category(transaction_type: str, text: str) -> str | None:
    """把使用者輸入解析成分類文字；接受編號或直接輸入分類名稱，皆無法比對時回傳 None。"""
    categories = categories_for_type(transaction_type)
    text = text.strip()
    if text.isdigit():
        index = int(text)
        if 1 <= index <= len(categories):
            return categories[index - 1]
        return None
    return text if text in categories else None


def create_transaction(
    db: CloudSQLClient,
    user_id: int,
    transaction_type: str,
    category: str,
    amount: float,
    note: str | None,
    transaction_date: date,
) -> int:
    """新增一筆記帳交易（FR-42），回傳新建列的 id。

    `transaction_date` 必填：一般新增時呼叫端傳今天的台灣日期，補記時傳使用者指定的過去日期，
    一律由呼叫端算好再傳進來，設計理由同 `mood_journals.entry_date`（見本模組 docstring 決策）。
    """
    return db.insert(
        "transactions",
        {
            "user_id": user_id,
            "type": transaction_type,
            "category": category,
            "amount": amount,
            "note": note,
            "transaction_date": transaction_date,
        },
    )


def update_transaction(
    db: CloudSQLClient,
    transaction_id: int,
    transaction_type: str,
    category: str,
    amount: float,
    note: str | None,
) -> None:
    """更新一筆記帳交易的類型/分類/金額/備註（FR-42 更新功能）；`transaction_date` 不在這裡
    異動，沿用原本記錄的那一天（比照 `mood.update_mood_journal()` 的做法）。"""
    db.update(
        "transactions",
        {"type": transaction_type, "category": category, "amount": amount, "note": note},
        where="id = %s",
        params=(transaction_id,),
    )


def delete_transaction(db: CloudSQLClient, transaction_id: int) -> None:
    """刪除一筆記帳交易（FR-42 刪除功能；使用者明確確認後才會呼叫，見 commands.py 的刪除確認流程）。"""
    db.delete("transactions", where="id = %s", params=(transaction_id,))


def list_transactions(db: CloudSQLClient, user_id: int, limit: int = 10) -> list[dict]:
    """查詢某使用者的記帳交易，依實際發生日期由新到舊排序，只取最近 N 筆供選擇更新/刪除
    （設計理由同 `mood.list_mood_journals()`）。"""
    rows = db.select("transactions", where="user_id = %s", params=(user_id,))
    rows.sort(key=lambda row: (row["transaction_date"], row["id"]), reverse=True)
    return rows[:limit]


def format_transaction_list(transactions: list[dict]) -> str:
    """把記帳交易清單格式化成使用者看的編號清單文字，供查詢與更新/刪除流程共用。"""
    if not transactions:
        return "目前還沒有記帳紀錄喔！"
    lines = ["這是你最近的記帳紀錄：", ""]
    for index, item in enumerate(transactions, start=1):
        sign = "-" if item["type"] == "expense" else "+"
        note_part = f"　{item['note']}" if item.get("note") else ""
        lines.append(
            f"{index}. {item['transaction_date']:%Y/%m/%d} {item['category']} "
            f"{sign}{item['amount']:.0f} 元{note_part}"
        )
    return "\n".join(lines)


def set_monthly_budget(db: CloudSQLClient, user_id: int, amount: float) -> None:
    """設定/更新使用者每月支出預算上限（FR-41）。"""
    db.update("users", {"monthly_budget": amount}, where="id = %s", params=(user_id,))


def get_monthly_budget(db: CloudSQLClient, user_id: int) -> float | None:
    """查詢使用者目前的每月支出預算上限；尚未設定時回傳 None。"""
    row = db.select("users", where="id = %s", params=(user_id,), fetch_one=True)
    if row is None:
        return None
    budget = row.get("monthly_budget")
    return float(budget) if budget is not None else None


def _month_range(year: int, month: int) -> tuple[date, date]:
    """回傳某年某月的 [起始日, 下個月起始日) 範圍，供月加總查詢的 WHERE 條件使用。"""
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def _monthly_total(db: CloudSQLClient, user_id: int, year: int, month: int, transaction_type: str) -> float:
    start, end = _month_range(year, month)
    rows = db.select(
        "transactions",
        where="user_id = %s AND type = %s AND transaction_date >= %s AND transaction_date < %s",
        params=(user_id, transaction_type, start, end),
    )
    return sum(float(row["amount"]) for row in rows)


def monthly_expense_total(db: CloudSQLClient, user_id: int, year: int, month: int) -> float:
    """加總某使用者某年某月的支出總額（FR-43 門檻檢查、FR-44 摘要共用）。"""
    return _monthly_total(db, user_id, year, month, "expense")


def monthly_income_total(db: CloudSQLClient, user_id: int, year: int, month: int) -> float:
    """加總某使用者某年某月的收入總額（FR-44 摘要用）。"""
    return _monthly_total(db, user_id, year, month, "income")


def monthly_expense_breakdown(db: CloudSQLClient, user_id: int, year: int, month: int) -> list[tuple[str, float]]:
    """依分類加總某使用者某年某月的支出，依金額由高到低排序（FR-44 摘要用）。"""
    start, end = _month_range(year, month)
    rows = db.select(
        "transactions",
        where="user_id = %s AND type = %s AND transaction_date >= %s AND transaction_date < %s",
        params=(user_id, "expense", start, end),
    )
    totals: dict[str, float] = {}
    for row in rows:
        totals[row["category"]] = totals.get(row["category"], 0.0) + float(row["amount"])
    return sorted(totals.items(), key=lambda pair: pair[1], reverse=True)


def format_monthly_summary(db: CloudSQLClient, user_id: int, today: date) -> str:
    """組合 FR-44 文字版月支出/收入摘要：本月支出/收入總額、預算使用率、分類佔比、跟上個月比較。"""
    expense_total = monthly_expense_total(db, user_id, today.year, today.month)
    income_total = monthly_income_total(db, user_id, today.year, today.month)
    budget = get_monthly_budget(db, user_id)
    breakdown = monthly_expense_breakdown(db, user_id, today.year, today.month)

    lines = [f"📊 {today.year}/{today.month} 記帳摘要", "", f"支出總計：{expense_total:.0f} 元", f"收入總計：{income_total:.0f} 元"]

    if budget is not None and budget > 0:
        percent = expense_total / budget * 100
        lines.append(f"預算上限：{budget:.0f} 元（已使用 {percent:.0f}%）")
    else:
        lines.append("尚未設定每月支出預算上限，可輸入「設定記帳預算」來設定")

    if breakdown:
        lines.append("")
        lines.append("支出分類佔比：")
        for category, amount in breakdown:
            share = amount / expense_total * 100 if expense_total else 0.0
            lines.append(f"- {category}：{amount:.0f} 元（{share:.0f}%）")

    prev_year, prev_month = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    prev_expense_total = monthly_expense_total(db, user_id, prev_year, prev_month)
    if prev_expense_total > 0:
        diff_percent = (expense_total - prev_expense_total) / prev_expense_total * 100
        trend = "增加" if diff_percent >= 0 else "減少"
        lines.append("")
        lines.append(f"跟上個月（{prev_expense_total:.0f} 元）相比，{trend}了 {abs(diff_percent):.0f}%")

    return "\n".join(lines)


def check_and_push_budget_alerts(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """FR-43：預算門檻預警。50% 門檻只在每月 15 日（含）以前檢查，80% 門檻整月都檢查，
    各自每月最多推播一次（去重狀態見本模組 docstring 決策③）。

    比照 `todo.check_and_push_reminders()` 的做法，借用 `/healthz` 既有的 10 分鐘 cron 頻率
    （見 `main.py`），沒有獨立的排程系統。
    """
    now = now or datetime.now(timezone.utc)
    now_local = now.astimezone(_TAIWAN_TZ)
    today_local = now_local.date()
    month_start = today_local.replace(day=1)

    users = db.select("users", where="monthly_budget IS NOT NULL")
    for user in users:
        if user.get("telegram_user_id") is None:
            continue
        budget = float(user["monthly_budget"])
        if budget <= 0:
            continue

        expense_total = monthly_expense_total(db, user["id"], today_local.year, today_local.month)
        percent = expense_total / budget

        if (
            today_local.day <= _MID_MONTH_ALERT_DAY_CUTOFF
            and percent >= _MID_MONTH_ALERT_THRESHOLD
            and user.get("budget_alert_50_sent_month") != month_start
        ):
            telegram_client.send_text(
                chat_id=user["telegram_user_id"],
                text=(
                    f"⚠️ 提醒你，這個月才過一半，支出已經達到預算的 {percent * 100:.0f}% 囉"
                    f"（{expense_total:.0f}／{budget:.0f} 元），要注意一下花費喔！"
                ),
            )
            db.update(
                "users", {"budget_alert_50_sent_month": month_start}, where="id = %s", params=(user["id"],)
            )

        if percent >= _SEVERE_ALERT_THRESHOLD and user.get("budget_alert_80_sent_month") != month_start:
            telegram_client.send_text(
                chat_id=user["telegram_user_id"],
                text=(
                    f"🚨 提醒你，這個月支出已經達到預算的 {percent * 100:.0f}% 了"
                    f"（{expense_total:.0f}／{budget:.0f} 元），已經很接近上限，要注意一下花費喔！"
                ),
            )
            db.update(
                "users", {"budget_alert_80_sent_month": month_start}, where="id = %s", params=(user["id"],)
            )
