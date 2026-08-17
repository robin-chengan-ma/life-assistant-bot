"""證照題庫每日出題彈性排程（對應 docs/specs/robinson/SPEC.md FR-26、ADR-20 決策 5、6）。

負責：四種彈性排程語意（改到別天／取消／區間覆蓋／平攤到鄰近幾天）的資料操作，以及「平攤」的
分攤方案計算。不處理 Telegram 對話狀態機與 LLM 語意分類 prompt（那是 `src/bot/commands.py` 的
責任），這裡保持純粹的資料操作與計算，方便獨立測試。

**四種語意（ADR-20 決策 5）**：
① MOVE（改到別天）：今天這批題目整批挪到指定日期
② CANCEL（取消）：今天不出題，不補、不挪
③ RANGE（區間覆蓋）：某個日期區間的每日出題數量改成 N 題，區間外不受影響
④ SPREAD（平攤，2026-08-08 追加）：今天的題目分攤到接下來幾天，每天固定 +1 題，天數隨題數
   自動變動；命中既有排程覆蓋的日期直接跳過往後找。**這是唯一需要「先算提案 → 給 Robin 確認 →
   同意才寫入」的語意**（見 `compute_spread_plan()`／`apply_spread_plan()` 的分工），其餘三種
   語意是使用者已經明確下的指令，直接套用不需要額外確認。

**「今天已經生成的批次」怎麼處理**：`certificate_daily_schedule_overrides` 只會影響「還沒生成
過 assignment 的未來日期」（`assign_daily_questions()` 只在建立當下查一次生效題數，事後改
overrides 不會回頭影響已經寫入 `certificate_daily_assignments` 的既有紀錄）。因此 MOVE／
CANCEL／SPREAD 這三種會動到「今天」的語意，除了寫入 overrides，還需要額外呼叫
`delete_unanswered_assignments()` 直接刪掉今天還沒作答的既有 assignment 列，才會真的讓使用者
看不到這些題目；已經作答過的紀錄不受影響（無法也不應該回頭刪除使用者已完成的作答）。RANGE 若
剛好涵蓋今天，同樣需要呼叫這個函式。
"""
from datetime import date, timedelta

from src.bot import certificate_quiz
from submodules.cloudsql.client import CloudSQLClient

# --- 「今天已生成批次」的清理 ---


def delete_unanswered_assignments(db: CloudSQLClient, user_id: int, exam_type: str, target_date: date) -> int:
    """刪除指定日期還沒作答的既有 assignment 列，已作答過的維持不動；回傳實際刪除的筆數。"""
    rows = db.select(
        "certificate_daily_assignments",
        where="user_id = %s AND exam_type = %s AND assigned_date = %s",
        params=(user_id, exam_type, target_date),
    )
    deleted = 0
    for row in rows:
        answered = db.select("answer_logs", where="assignment_id = %s", params=(row["id"],), fetch_one=True)
        if answered is None:
            db.delete("certificate_daily_assignments", where="id = %s", params=(row["id"],))
            deleted += 1
    return deleted


def _set_single_day_override(db: CloudSQLClient, user_id: int, exam_type: str, target_date: date, daily_count: int) -> None:
    db.insert(
        "certificate_daily_schedule_overrides",
        {
            "user_id": user_id, "exam_type": exam_type,
            "start_date": target_date, "end_date": target_date,
            "daily_question_count": daily_count,
        },
    )


# --- 語意①②③：改到別天／取消／區間覆蓋 ---


def apply_cancel(db: CloudSQLClient, user_id: int, exam_type: str, today: date) -> None:
    """語意②：今天不出題，不補、不挪。"""
    delete_unanswered_assignments(db, user_id, exam_type, today)
    _set_single_day_override(db, user_id, exam_type, today, 0)


def apply_move(db: CloudSQLClient, user_id: int, exam_type: str, today: date, target_date: date) -> None:
    """語意①：今天這批題目整批挪到 `target_date`（今天原本生效的題數直接設為 `target_date`
    當天的覆蓋值，取代而非疊加，跟 `certificate_daily_schedule_overrides` 其他語意的既有設計
    一致）。"""
    original_count = certificate_quiz.effective_daily_question_count(db, user_id, exam_type, today)
    delete_unanswered_assignments(db, user_id, exam_type, today)
    _set_single_day_override(db, user_id, exam_type, today, 0)
    _set_single_day_override(db, user_id, exam_type, target_date, original_count)


def apply_range_override(
    db: CloudSQLClient, user_id: int, exam_type: str, today: date, start_date: date, end_date: date, daily_count: int
) -> None:
    """語意③：`start_date`～`end_date` 這段區間每天的出題數量改成 `daily_count`，區間外不受
    影響；若區間剛好涵蓋今天，額外清理今天已生成但還沒作答的既有題目，讓新的數量真的生效。"""
    if start_date <= today <= end_date:
        delete_unanswered_assignments(db, user_id, exam_type, today)
    db.insert(
        "certificate_daily_schedule_overrides",
        {
            "user_id": user_id, "exam_type": exam_type,
            "start_date": start_date, "end_date": end_date,
            "daily_question_count": daily_count,
        },
    )


# --- 語意④：平攤（先算提案，確認後才寫入） ---


def _find_next_available_dates(db: CloudSQLClient, user_id: int, exam_type: str, today: date, count: int) -> list[date]:
    """從明天起找出 `count` 個「還沒有既有排程覆蓋」的日期（跳過已被 Robin 手動設定過的日期，
    不覆寫既有決定，見 ADR-20 決策 6）。"""
    dates: list[date] = []
    candidate_date = today + timedelta(days=1)
    # 安全上限：理論上不會真的跑這麼多天（每日出題數量不會誇張到需要攤幾百天），純粹避免資料
    # 異常時無限迴圈。
    for _ in range(365):
        if len(dates) >= count:
            break
        if certificate_quiz.get_active_schedule_override(db, user_id, exam_type, candidate_date) is None:
            dates.append(candidate_date)
        candidate_date += timedelta(days=1)
    return dates


def _split_evenly(total: int, parts: int) -> list[int]:
    """把 `total` 平均分成 `parts` 份整數（餘數依序分給前面幾份），供「自訂天數」重算使用。"""
    if parts <= 0:
        return []
    base, remainder = divmod(total, parts)
    return [base + 1 if i < remainder else base for i in range(parts)]


def compute_spread_plan(
    db: CloudSQLClient, user_id: int, exam_type: str, today: date, num_days: int | None = None
) -> list[dict]:
    """算出「把今天的題目平攤到接下來幾天」的提案，不寫入任何資料（見模組 docstring，這個語意
    需要先給 Robin 確認）。

    預設規則（`num_days=None`）：從明天起連續每天 +1 題，直到把今天的題數攤完為止，天數等於今天
    的題數。若 Robin 對提案有調整意見、明確講出想攤成幾天（見 `src/bot/commands.py` 的確認回覆
    分類），呼叫端可傳入 `num_days` 依那個天數重新平均分攤（餘數依序分給前面幾天）。命中已有排程
    覆蓋的日期一律跳過往後找（見 ADR-20 決策 6）。回傳 `[{"date": date, "new_count": int}, ...]`，
    `new_count` 是該天覆蓋後的總題數；今天原本生效題數為 0 時回傳空清單（沒有題目可攤）。
    """
    total_to_spread = certificate_quiz.effective_daily_question_count(db, user_id, exam_type, today)
    if total_to_spread <= 0:
        return []

    if num_days is None:
        dates = _find_next_available_dates(db, user_id, exam_type, today, total_to_spread)
        additions = [1] * len(dates)
    else:
        dates = _find_next_available_dates(db, user_id, exam_type, today, num_days)
        additions = _split_evenly(total_to_spread, len(dates))

    plan: list[dict] = []
    for target_date, addition in zip(dates, additions):
        if addition <= 0:
            continue
        base_count = certificate_quiz.effective_daily_question_count(db, user_id, exam_type, target_date)
        plan.append({"date": target_date, "new_count": base_count + addition})
    return plan


def apply_spread_plan(db: CloudSQLClient, user_id: int, exam_type: str, today: date, plan: list[dict]) -> None:
    """語意④實際寫入：`plan` 必須是 `compute_spread_plan()` 算出、且已經給 Robin 確認過的方案
    （呼叫端負責確保這件事，這裡不重複檢查）。"""
    delete_unanswered_assignments(db, user_id, exam_type, today)
    _set_single_day_override(db, user_id, exam_type, today, 0)
    for item in plan:
        _set_single_day_override(db, user_id, exam_type, item["date"], item["new_count"])


def format_spread_proposal(plan: list[dict]) -> str:
    """組出「平攤」提案文字，列出幾月幾號各要多幾題，供 Robin 確認（見模組 docstring）。"""
    if not plan:
        return "今天沒有題目可以分攤喔（今天生效題數是 0）。"
    lines = ["這是我算出來的分攤方案，你看看 OK 嗎？"]
    for item in plan:
        lines.append(f"・{item['date'].month}/{item['date'].day}：+1 題（當天共 {item['new_count']} 題）")
    lines.append("同意的話回覆「OK」，想調整的話直接跟我說怎麼改，我會重新算一次給你確認。")
    return "\n".join(lines)
