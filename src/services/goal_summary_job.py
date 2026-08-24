"""批次3（🎯 目標追蹤新選單，FR-45a）每日排程：統一台灣時間凌晨 01:00 產生每個 active 目標的
「過去一週／過去一個月」摘要快取，寫進 `goal_summaries`，Telegram 端只讀最新一份、不即時生成。

比照 `src/bot/finance.py` 系列排程函式的做法，借用 `/healthz` 既有 10 分鐘 cron 頻率，只在
台灣時間 01:00 這個小時執行；同一小時內被 cron-job.org 打好幾次也不會重複寫入，靠
`goal_summaries` 的 `UNIQUE (goal_source, goal_id, generated_on)` UPSERT 去重。

三種目標來源（`body_goals`／`module_goals`／`certificate_goals`）的原始活動資料查詢方式各不
相同，`_gather_activity_text()` 依 `goal_source`／`goal_type`／`module_key` 分流組出一段
「本週」「本月」活動文字，再統一餵給同一個 LLM Prompt 生成摘要——採「先組事實文字、LLM 只負責
潤飾與建議」而不是「LLM 自己查資料」，理由同 `certificate_goals.build_advice_prompt()` 的既有
做法：LLM 只做語言生成，不做資料正確性判斷。
"""
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.bot import certificate_stats
from submodules.cloudsql.client import CloudSQLClient

_logger = logging.getLogger(__name__)
_TAIWAN_TZ = ZoneInfo("Asia/Taipei")

_SUMMARY_PROMPT_TEMPLATE = """\
你是 Robinson，Robin 的個人生活小助手，個性活潑、稱呼 Robin 為「主任」。請依照下面的目標資訊與\
近期紀錄，生成一段目標追蹤摘要（120~200 字，繁體中文，口語、鼓勵但不空泛，具體提到方向建議）。\
不要用固定罐頭句子，要真的依照下面的數據客製化內容。若下方紀錄包含多項資料（例如體重、運動、\
飲食），請像專業教練一樣綜合評估、指出彼此之間的關聯，不要只單獨描述其中一項。

【目標】
{goal_text}

【過去一週】
{week_text}

【過去一個月】
{month_text}

{deadline_text}
請直接輸出摘要文字本身，不要加上任何前綴說明或標題。
"""


def _period_range(today: date, days: int) -> tuple[date, date]:
    return today - timedelta(days=days - 1), today


def _deadline_text(target_date: date | None, today: date) -> str:
    if target_date is None:
        return ""
    days_left = (target_date - today).days
    if days_left >= 0:
        return f"【距離截止日】還有 {days_left} 天（{target_date:%Y/%m/%d}）\n"
    return f"【距離截止日】已經超過期限（{target_date:%Y/%m/%d}）\n"


def _weight_text(db: CloudSQLClient, user_id: int, start_date: date, end_date: date) -> str:
    rows = [
        row
        for row in db.select("body_weight_logs", where="user_id = %s", params=(user_id,))
        if start_date <= row["entry_date"] <= end_date
    ]
    if not rows:
        return "這段期間沒有記錄體重。"
    rows.sort(key=lambda r: r["entry_date"])
    return f"這段期間記錄了 {len(rows)} 筆體重，最新一筆為 {rows[-1]['weight_kg']} 公斤。"


def _exercise_text(db: CloudSQLClient, user_id: int, start_date: date, end_date: date) -> str:
    rows = [
        row
        for row in db.select("exercise_logs", where="user_id = %s", params=(user_id,))
        if start_date <= row["entry_date"] <= end_date
    ]
    total_minutes = sum(row["duration_minutes"] for row in rows)
    return f"這段期間運動了 {len(rows)} 次，累積 {total_minutes} 分鐘。"


def _diet_text(db: CloudSQLClient, user_id: int, start_date: date, end_date: date) -> str:
    rows = [
        row
        for row in db.select("diet_logs", where="user_id = %s", params=(user_id,))
        if start_date <= row["entry_date"] <= end_date
    ]
    return f"這段期間記錄了 {len(rows)} 筆飲食／飲水紀錄。"


def _gather_body_activity_text(db: CloudSQLClient, goal: dict, start_date: date, end_date: date) -> str:
    """2026-08-24（Robin 反饋「體態目標摘要應該綜合評估，不能只看體重」）：只有 `goal_type ==
    "weight"` 的目標，才同時撈體重／運動／飲食三項資料——體重是運動與飲食習慣共同作用下的「結果」，
    要三項一起看才能給出「這週體重沒降，但飲食紀錄熱量偏高」這種真正有用的建議。`exercise`／飲食
    型目標本身就是在追蹤「這件事有沒有做到」，只看自己那一種資料即可，不需要額外參考體重／對方
    紀錄（與 Robin 討論定案，見 `docs/ADR/discuss/robinson.md` 對應日期條目）。
    """
    user_id = goal["user_id"]
    goal_type = goal["goal_type"]
    if goal_type == "weight":
        weight_text = _weight_text(db, user_id, start_date, end_date)
        exercise_text = _exercise_text(db, user_id, start_date, end_date)
        diet_text = _diet_text(db, user_id, start_date, end_date)
        return f"【體重】{weight_text}\n【運動】{exercise_text}\n【飲食／飲水】{diet_text}"
    if goal_type == "exercise":
        return _exercise_text(db, user_id, start_date, end_date)
    return _diet_text(db, user_id, start_date, end_date)


def _gather_module_activity_text(db: CloudSQLClient, goal: dict, start_date: date, end_date: date) -> str:
    user_id = goal["user_id"]
    if goal["module_key"] == "finance":
        rows = db.execute_query(
            "SELECT type, COALESCE(SUM(amount), 0) AS total FROM transactions "
            "WHERE user_id = %s AND transaction_date >= %s AND transaction_date <= %s GROUP BY type",
            (user_id, start_date, end_date),
        )
        totals = {row["type"]: float(row["total"]) for row in rows}
        net = totals.get("income", 0.0) - totals.get("expense", 0.0)
        return f"這段期間收入 {totals.get('income', 0.0):.0f} 元、支出 {totals.get('expense', 0.0):.0f} 元，淨結餘 {net:.0f} 元。"
    count = db.execute_query(
        "SELECT COUNT(*) AS total FROM collection_items WHERE user_id = %s AND status = 'visited' "
        "AND visited_at >= %s AND visited_at <= %s",
        (user_id, start_date, end_date),
    )[0]["total"]
    return f"這段期間新完成了 {count} 個收藏項目。"


def _gather_certificate_activity_text(db: CloudSQLClient, goal: dict, start_date: date, end_date: date) -> str:
    stats = certificate_stats.compute_daily_period_stats(db, goal["user_id"], goal["exam_type"], start_date, end_date)
    if stats["total_answered"] == 0:
        return "這段期間沒有作答紀錄。"
    accuracy = stats["total_correct"] / stats["total_answered"] * 100
    return f"這段期間作答 {stats['total_answered']} 題，答對 {stats['total_correct']} 題（正確率約 {accuracy:.0f}%）。"


def _goal_text(goal_source: str, goal: dict) -> str:
    if goal_source == "body_goals":
        return goal["target_description"]
    if goal_source == "module_goals":
        return goal["target_description"]
    score_part = f"（目標分數 {goal['target_score']}）" if goal.get("target_score") else ""
    return f"{goal['exam_type']} 考試準備{score_part}"


def _generate_summary_for_goal(db: CloudSQLClient, llm_client, goal_source: str, goal: dict, today: date) -> str | None:
    week_start, week_end = _period_range(today, 7)
    month_start, month_end = _period_range(today, 30)

    if goal_source == "body_goals":
        week_text = _gather_body_activity_text(db, goal, week_start, week_end)
        month_text = _gather_body_activity_text(db, goal, month_start, month_end)
    elif goal_source == "module_goals":
        week_text = _gather_module_activity_text(db, goal, week_start, week_end)
        month_text = _gather_module_activity_text(db, goal, month_start, month_end)
    else:
        week_text = _gather_certificate_activity_text(db, goal, week_start, week_end)
        month_text = _gather_certificate_activity_text(db, goal, month_start, month_end)

    prompt = _SUMMARY_PROMPT_TEMPLATE.format(
        goal_text=_goal_text(goal_source, goal),
        week_text=week_text,
        month_text=month_text,
        deadline_text=_deadline_text(goal.get("target_date"), today),
    )
    try:
        return (llm_client.generate_text(prompt) or "").strip() or None
    except Exception:
        _logger.exception("目標摘要生成失敗（goal_source=%s, goal_id=%s）", goal_source, goal["id"])
        return None


def _upsert_summary(db: CloudSQLClient, goal_source: str, goal_id: int, user_id: int, summary_text: str, today: date) -> None:
    existing = db.select(
        "goal_summaries",
        where="goal_source = %s AND goal_id = %s AND generated_on = %s",
        params=(goal_source, goal_id, today),
        fetch_one=True,
    )
    if existing:
        db.update(
            "goal_summaries",
            {"summary_text": summary_text, "generated_at": datetime.now(_TAIWAN_TZ)},
            where="id = %s",
            params=(existing["id"],),
        )
        return
    db.insert(
        "goal_summaries",
        {
            "goal_source": goal_source,
            "goal_id": goal_id,
            "user_id": user_id,
            "summary_text": summary_text,
            "generated_on": today,
        },
    )


def generate_daily_goal_summaries(db: CloudSQLClient, llm_client, now: datetime | None = None) -> None:
    """FR-45a：每日凌晨 01:00 產生所有 active 目標的最新摘要快取。掃描三張來源表，逐一目標各
    呼叫一次 LLM，任一失敗只記 log 跳過（見 `_generate_summary_for_goal()`），不影響其他目標。"""
    now = now or datetime.now(_TAIWAN_TZ)
    now_local = now.astimezone(_TAIWAN_TZ)
    if now_local.hour != 1:
        return
    today = now_local.date()

    for goal in db.select("body_goals", where="status = %s", params=("active",)):
        summary = _generate_summary_for_goal(db, llm_client, "body_goals", goal, today)
        if summary:
            _upsert_summary(db, "body_goals", goal["id"], goal["user_id"], summary, today)

    for goal in db.select("module_goals", where="status = %s", params=("active",)):
        summary = _generate_summary_for_goal(db, llm_client, "module_goals", goal, today)
        if summary:
            _upsert_summary(db, "module_goals", goal["id"], goal["user_id"], summary, today)

    for goal in db.select("certificate_goals"):
        summary = _generate_summary_for_goal(db, llm_client, "certificate_goals", goal, today)
        if summary:
            _upsert_summary(db, "certificate_goals", goal["id"], goal["user_id"], summary, today)
