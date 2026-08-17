"""證照準備目標設定與方向建議（對應 docs/specs/robinson/SPEC.md FR-24、ADR-19，Step 3.3）。

負責 `certificate_goals` 表（已於 0041 migration 建立）的 UPSERT 讀寫，以及組裝「方向建議」要
餵給 LLM 的 Prompt。目標（考試時間、目標分數）依 `exam_type` 各自設定一筆，重新設定即覆蓋舊值
（`certificate_goals.UNIQUE (user_id, exam_type)`）。方向建議本身由 Robinson 依使用者近期
`certificate_stats` 統計出的成效（對錯趨勢、常出錯的 `question_type`）與距離目標時間長短，用 LLM
生成客製化建議文字，不走固定範本（見 ADR-19、FR-24 條文）——這裡只負責組 Prompt，實際呼叫 LLM
與對話狀態機是 `src/bot/commands.py` 的責任。
"""
import logging
import re
from datetime import date

from src.services.goal_important_day_sync import sync_certificate_goal
from submodules.cloudsql.client import CloudSQLClient

_logger = logging.getLogger(__name__)

_ADVICE_PROMPT_TEMPLATE = """\
你是 Robinson，Robin 的個人生活小助手，個性活潑、稱呼 Robin 為「主任」。Robin 正在準備「{exam_type}」\
證照考試，需要你依照他最近的練習成效與目標，給出一段客製化的讀書方向建議（100~200 字，繁體中文，\
口語、鼓勵但不空泛，具體點出接下來該加強什麼）。不要用固定罐頭句子，要真的依照下面的數據客製化內容。

【目標】
{goal_text}

【近期成效】
{stats_text}

請直接輸出建議文字本身，不要加上任何前綴說明或標題。
"""


def get_goal(db: CloudSQLClient, user_id: int, exam_type: str) -> dict | None:
    return db.select(
        "certificate_goals", where="user_id = %s AND exam_type = %s", params=(user_id, exam_type), fetch_one=True
    )


def set_goal(
    db: CloudSQLClient, user_id: int, exam_type: str, target_date: date | None, target_score: str | None
) -> dict:
    """新增或覆蓋（UPSERT）這個使用者對某個 `exam_type` 的目標設定，回傳
    `{"previous": 舊值或 None, "target_date", "target_score"}` 供呼叫端組回覆文字（例如告知使用者
    先前設定過的舊值）。"""
    existing = get_goal(db, user_id, exam_type)
    data = {"target_date": target_date, "target_score": target_score}

    if existing is not None:
        db.update("certificate_goals", data, where="id = %s", params=(existing["id"],))
        goal_id = existing["id"]
    else:
        goal_id = db.insert("certificate_goals", {"user_id": user_id, "exam_type": exam_type, **data})

    if target_date is not None or existing is not None:
        try:
            sync_certificate_goal(db, goal_id)
        except Exception:
            _logger.exception("證照目標（id=%s）同步至重要日子失敗，目標本身已成功儲存", goal_id)

    return {"previous": existing, "target_date": target_date, "target_score": target_score}


def list_goals(db: CloudSQLClient, user_id: int) -> list[dict]:
    rows = db.select("certificate_goals", where="user_id = %s", params=(user_id,))
    rows.sort(key=lambda row: row["exam_type"])
    return rows


def format_goal_set_reply(exam_type: str, result: dict) -> str:
    """組出設定完成後的回覆文字（FR-19h 決策執行狀態閉環回饋：明確告知已成功寫入）。"""
    parts = []
    if result["target_date"]:
        d = result["target_date"]
        parts.append(f"目標考試時間 {d.year}/{d.month}/{d.day}")
    if result["target_score"]:
        parts.append(f"目標分數 {result['target_score']}")
    detail = "、".join(parts) if parts else "（沒有設定時間或分數，之後想補都可以再跟我說）"

    prefix = "已經幫你更新「{}」的目標囉！" if result["previous"] else "已經幫你記下「{}」的目標囉！"
    return f"{prefix.format(exam_type)}{detail}"


def format_goals_summary(rows: list[dict]) -> str:
    if not rows:
        return "目前還沒有設定任何證照準備目標喔！"

    lines = ["🎯 目前的證照準備目標", ""]
    for row in rows:
        pieces = []
        if row.get("target_date"):
            d = row["target_date"]
            pieces.append(f"目標時間 {d.year}/{d.month}/{d.day}")
        if row.get("target_score"):
            pieces.append(f"目標分數 {row['target_score']}")
        detail = "、".join(pieces) if pieces else "（尚未設定時間或分數）"
        lines.append(f"・{row['exam_type']}：{detail}")
    return "\n".join(lines)


def _format_goal_text(goal: dict | None, today: date) -> str:
    if goal is None:
        return "尚未設定目標。"

    pieces = []
    if goal.get("target_date"):
        target_date = goal["target_date"]
        days_left = (target_date - today).days
        if days_left >= 0:
            pieces.append(f"目標考試時間 {target_date.year}/{target_date.month}/{target_date.day}（還有 {days_left} 天）")
        else:
            pieces.append(f"目標考試時間 {target_date.year}/{target_date.month}/{target_date.day}（已經過了）")
    if goal.get("target_score"):
        pieces.append(f"目標分數 {goal['target_score']}")
    return "、".join(pieces) if pieces else "已設定目標，但沒有填時間或分數。"


def _format_stats_text(stats: dict | None) -> str:
    if stats is None or stats["total_answered"] == 0:
        return "最近沒有任何作答紀錄，還沒有足夠的數據可以分析弱點。"

    accuracy = stats["total_correct"] / stats["total_answered"] * 100
    lines = [
        (
            f"最近測驗 {stats['total_answered']} 題，答對 {stats['total_correct']} 題（正確率約 {accuracy:.0f}%），"
            f"有作答的 {stats['active_days']} 天平均每天答對 {stats['avg_correct_per_active_day']:.1f} 題。"
        )
    ]
    if stats["most_wrong_type"]:
        lines.append(f"最常出錯的題型是「{stats['most_wrong_type']}」。")
    return "".join(lines)


def check_score_achievement(db: CloudSQLClient, user_id: int, exam_type: str, score: str) -> str | None:
    """2026-08-17 補做（Robin 要求不得漏做）：使用者透過 `/record_official_score` 記錄「實際應考
    成績」後呼叫，跟這個 `exam_type` 目前設定的 `target_score` 做數字比對，達標就回傳恭喜文字。

    `target_score`／`score` 都是 TEXT（`exam_type` 開放任意證照類型，有些沒有量化分數，例如
    「通過／未通過」），只在兩邊都能抽出數字時才比較（`score >= target_score`，語意是「分數越高
    越好」，符合 TOEIC／統測分數這類常見情境）；抽不出數字（例如目標或成績本身就是「通過」這種
    文字）時直接跳過，不誤判、也不擋下記錄成績這個主流程。沒有設定目標、或目標沒填 `target_score`
    時同樣回傳 `None`。"""
    goal = get_goal(db, user_id, exam_type)
    if goal is None or not goal.get("target_score"):
        return None

    target_match = re.search(r"-?\d+(\.\d+)?", str(goal["target_score"]))
    score_match = re.search(r"-?\d+(\.\d+)?", str(score))
    if not target_match or not score_match:
        return None

    if float(score_match.group()) >= float(target_match.group()):
        return f"🎉 恭喜你達成「{exam_type}」的目標分數（{goal['target_score']}）了！"
    return None


def build_advice_prompt(exam_type: str, goal: dict | None, stats: dict | None, today: date) -> str:
    """組出餵給 LLM 生成「方向建議」的 Prompt（FR-24：不走固定範本，依實際數據客製化）。"""
    return _ADVICE_PROMPT_TEMPLATE.format(
        exam_type=exam_type,
        goal_text=_format_goal_text(goal, today),
        stats_text=_format_stats_text(stats),
    )
