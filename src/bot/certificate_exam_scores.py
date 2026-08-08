"""證照正式應考成績記錄（對應 docs/specs/robinson/SPEC.md FR-30、ADR-19 決策 7，Step 3.3）。

跟 `answer_logs`（每日小考作答紀錄）刻意分開：正式成績是「一次考試的最終結果」，同一 `exam_type`
可能多次應考、各自有獨立的應考日期與分數，寫入 `exam_official_scores` 表（已於 0042 migration
建立）。本模組只負責「記錄」與「查詢列出」兩件事（**2026-08-08 經 AskUserQuestion 與 Robin 確認
範圍**：本次只做查詢列表，不含修改／刪除，理由是正式成績本質是「考完就是定案的歷史紀錄」，不像
體重／記帳需要常態修正，先求簡單，之後真的需要再補）。不處理 Telegram 對話狀態機，那是
`src/bot/commands.py` 的責任，這裡保持純粹的資料操作，方便獨立測試。
"""
from datetime import date

from submodules.cloudsql.client import CloudSQLClient


def record_score(db: CloudSQLClient, user_id: int, exam_type: str, exam_date: date, score: str) -> int:
    """新增一筆正式應考成績，回傳新增紀錄的 id。不做 UPSERT——同一 `exam_type` 允許多次應考，
    每次都是獨立一筆（見 ADR-19 決策 7）。"""
    return db.insert(
        "exam_official_scores",
        {"user_id": user_id, "exam_type": exam_type, "exam_date": exam_date, "score": score},
    )


def list_scores(db: CloudSQLClient, user_id: int, exam_type: str | None = None) -> list[dict]:
    """列出這個使用者的正式成績紀錄，依應考日期新到舊排序；`exam_type` 為 `None` 時列出所有證照
    類型（依 `exam_type`、應考日期新到舊排序）。"""
    rows = db.select("exam_official_scores", where="user_id = %s", params=(user_id,))
    if exam_type is not None:
        rows = [row for row in rows if row["exam_type"] == exam_type]
        rows.sort(key=lambda row: row["exam_date"], reverse=True)
    else:
        rows.sort(key=lambda row: (row["exam_type"], row["exam_date"]), reverse=True)
    return rows


def distinct_exam_types(db: CloudSQLClient, user_id: int) -> list[str]:
    """回傳這個使用者目前有正式成績紀錄的所有 exam_type（供查詢時列出選項）。"""
    rows = db.select("exam_official_scores", where="user_id = %s", params=(user_id,))
    return sorted({row["exam_type"] for row in rows})


def format_scores_summary(exam_type: str | None, rows: list[dict]) -> str:
    """組出正式成績清單的文字回覆（FR-30 查詢）。"""
    if not rows:
        target = f"「{exam_type}」" if exam_type else ""
        return f"目前還沒有{target}正式成績紀錄喔！"

    header = f"📋 {exam_type} 正式成績紀錄" if exam_type else "📋 正式成績紀錄"
    lines = [header, ""]
    for row in rows:
        exam_date = row["exam_date"]
        prefix = f"・{row['exam_type']} " if exam_type is None else "・"
        lines.append(f"{prefix}{exam_date.year}/{exam_date.month}/{exam_date.day}：{row['score']}")
    return "\n".join(lines)
