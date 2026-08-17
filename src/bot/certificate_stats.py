"""證照題庫成效統計（對應 docs/specs/robinson/SPEC.md FR-29、ADR-19 決策 4、5，Step 3.3）。

負責「日常小考」（`answer_logs`）與「正式測驗」（`exam_official_scores`）兩種成效資料在一段期間
內的統計計算與文字格式化。不做圖表（ADR-19 決策 4：查證 Phase 2 記帳／體態管理模組一開始就是
文字摘要，圖表統一交給 Phase 4 App 的 FR-64），也不處理 Telegram 對話狀態機與 LLM 自然語言解析
（那是 `src/bot/commands.py` 的責任），這裡保持純粹的資料操作與計算，方便獨立測試。

**日常小考統計維度**（ADR-19 決策 5）：沿用 `answer_logs.question_type`（write／listen／vocab）
與 `exam_type`，不新增更細的主題標籤欄位——「最常出錯的地方」／「最常答對的地方」用這個維度統計。

**排除未作答日**（FR-29）：平均值只除以「有作答的天數」，不是區間總天數；沒有作答的日子額外列出
供使用者參考。
"""
from collections import Counter
from datetime import date, timedelta

from submodules.cloudsql.client import CloudSQLClient

_QUESTION_TYPE_LABELS = {"write": "填空題", "listen": "聽力題", "vocab": "單字題"}


def _label_question_type(question_type: str | None) -> str:
    if question_type is None:
        return "無"
    return _QUESTION_TYPE_LABELS.get(question_type, question_type)


# --- 日常小考統計 ---


def compute_daily_period_stats(
    db: CloudSQLClient, user_id: int, exam_type: str, start_date: date, end_date: date
) -> dict:
    """統計 `[start_date, end_date]`（含頭尾）這段期間內，某個 `exam_type` 的日常小考作答成效。

    回傳 `{"total_answered", "total_correct", "active_days", "inactive_dates",
    "avg_correct_per_active_day", "most_wrong_type", "most_correct_type"}`；
    `active_days` 是有作答的天數，`inactive_dates` 是區間內完全沒作答的日期清單（FR-29）。
    """
    logs = [
        row
        for row in db.select("answer_logs", where="user_id = %s AND exam_type = %s", params=(user_id, exam_type))
        if start_date <= row["answered_on"] <= end_date
    ]

    total_answered = len(logs)
    total_correct = sum(1 for row in logs if row["is_correct"])

    active_dates = sorted({row["answered_on"] for row in logs})
    all_dates = [start_date + timedelta(days=n) for n in range((end_date - start_date).days + 1)]
    inactive_dates = [d for d in all_dates if d not in active_dates]

    avg_correct_per_active_day = total_correct / len(active_dates) if active_dates else 0.0

    wrong_counts = Counter(row["question_type"] for row in logs if not row["is_correct"])
    correct_counts = Counter(row["question_type"] for row in logs if row["is_correct"])
    most_wrong_type = wrong_counts.most_common(1)[0][0] if wrong_counts else None
    most_correct_type = correct_counts.most_common(1)[0][0] if correct_counts else None

    return {
        "total_answered": total_answered,
        "total_correct": total_correct,
        "active_days": len(active_dates),
        "inactive_dates": inactive_dates,
        "avg_correct_per_active_day": avg_correct_per_active_day,
        "most_wrong_type": most_wrong_type,
        "most_correct_type": most_correct_type,
    }


def format_daily_period_summary(exam_type: str, start_date: date, end_date: date, stats: dict) -> str:
    """組出 FR-29 範例格式的日常小考成效文字摘要。"""
    period_text = f"{start_date.month}/{start_date.day}～{end_date.month}/{end_date.day}"
    if stats["total_answered"] == 0:
        return f"「{exam_type}」在 {period_text} 這段期間沒有任何作答紀錄喔！"

    lines = [
        f"📊 「{exam_type}」{period_text} 成效",
        "",
        (
            f"這段期間總共測驗 {stats['total_answered']} 題，答對 {stats['total_correct']} 題，"
            f"有作答的 {stats['active_days']} 天平均每天答對 {stats['avg_correct_per_active_day']:.1f} 題。"
        ),
        (
            f"你最常出錯的地方是{_label_question_type(stats['most_wrong_type'])}，"
            f"最常答對的地方是{_label_question_type(stats['most_correct_type'])}。"
        ),
    ]
    if stats["inactive_dates"]:
        dates_text = "、".join(f"{d.month}/{d.day}" for d in stats["inactive_dates"])
        lines.append(f"這段期間沒有作答的日子：{dates_text}（已從平均計算中排除）。")
    return "\n".join(lines)


def format_daily_period_comparison(
    exam_type: str, period_a: tuple[date, date], stats_a: dict, period_b: tuple[date, date], stats_b: dict
) -> str:
    """組出兩段期間的日常小考成效比較文字（FR-29「支援跨時間區間比較」）。"""
    summary_a = format_daily_period_summary(exam_type, period_a[0], period_a[1], stats_a)
    summary_b = format_daily_period_summary(exam_type, period_b[0], period_b[1], stats_b)
    lines = [summary_a, "", "── 對照 ──", "", summary_b, ""]

    diff = stats_a["avg_correct_per_active_day"] - stats_b["avg_correct_per_active_day"]
    if abs(diff) < 0.05:
        lines.append("兩段期間平均每天答對題數差不多喔！")
    elif diff > 0:
        lines.append(f"第一段期間平均每天多答對 {diff:.1f} 題，進步了！")
    else:
        lines.append(f"第一段期間平均每天少答對 {abs(diff):.1f} 題。")
    return "\n".join(lines)


# --- 正式測驗成績統計 ---


def compute_formal_period_scores(
    db: CloudSQLClient, user_id: int, exam_type: str, start_date: date, end_date: date
) -> list[dict]:
    """列出 `[start_date, end_date]`（含頭尾）這段期間內某個 `exam_type` 的正式應考成績，依應考
    日期由舊到新排序。"""
    rows = [
        row
        for row in db.select(
            "exam_official_scores", where="user_id = %s AND exam_type = %s", params=(user_id, exam_type)
        )
        if start_date <= row["exam_date"] <= end_date
    ]
    rows.sort(key=lambda row: row["exam_date"])
    return rows


def format_formal_period_summary(exam_type: str, start_date: date, end_date: date, rows: list[dict]) -> str:
    """組出正式測驗成績的文字摘要。"""
    period_text = f"{start_date.month}/{start_date.day}～{end_date.month}/{end_date.day}"
    if not rows:
        return f"「{exam_type}」在 {period_text} 這段期間沒有正式應考紀錄喔！"

    lines = [f"📋 「{exam_type}」{period_text} 正式應考紀錄", ""]
    for row in rows:
        exam_date = row["exam_date"]
        lines.append(f"・{exam_date.year}/{exam_date.month}/{exam_date.day}：{row['score']}")
    return "\n".join(lines)


# --- 供 FR-24「方向建議」共用的近況查詢 ---


def known_exam_types(db: CloudSQLClient, user_id: int) -> list[str]:
    """回傳這個使用者目前有任何成效資料（日常小考作答紀錄或正式應考紀錄）的 exam_type，
    供 FR-29／FR-24 詢問使用者「想查詢哪個證照類型」時列出候選清單。"""
    answer_types = {
        row["exam_type"] for row in db.select("answer_logs", where="user_id = %s", params=(user_id,))
    }
    score_types = {
        row["exam_type"] for row in db.select("exam_official_scores", where="user_id = %s", params=(user_id,))
    }
    return sorted(answer_types | score_types)
