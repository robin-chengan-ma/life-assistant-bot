"""證照題庫每日推播出題（對應 docs/specs/robinson/SPEC.md FR-26、ADR-20，Step 3.3）。

僅 Robin 可用（`certificate` 功能開關）。負責「依設定計算今天要出哪幾題、寫入
`certificate_daily_assignments`、推播通知」，不處理實際作答/批改對話（留待後續，FR-27／FR-28）。

**出題數量/比例（ADR-20 決策 1、2）**：
- 非 TOEIC 證照只能調「每日出題數量」（`certificate_daily_settings.daily_question_count`），
  題庫池不分 write/listen，一律混著抽（`question_type_filter=None`）
- TOEIC 額外可調「聽力/填空/單字」三軌比例（`listen_ratio`／`write_ratio`／`vocab_ratio`），
  沒設定時預設 1:2:3（沿用 FR-25 原文「1 聽力+2 填空+3 單字」）
- 每個 exam_type 另外都有「新題:複習題」比例（`review_ratio_new`／`review_ratio_review`），
  預設 7:3，跟三軌比例是不同維度；複習池只放「最新一次作答結果答錯」的題目，複習題不夠湊比例
  時用新題補滿，不會因此少出題（決策 2）

**彈性排程（決策 5）**：`certificate_daily_schedule_overrides` 比照 `budget_overrides`「全局
預設值＋特殊區間覆蓋」設計，查詢當天生效題數時先查有沒有覆蓋當天的區間，沒有才 fallback 用
`certificate_daily_settings` 的全局值；`daily_question_count=0` 代表當天不出題（取消）。
"""
import logging
import random
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from src.bot import toggles
from submodules.cloudsql.client import CloudSQLClient

_logger = logging.getLogger(__name__)

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_PUSH_HOUR = 8
_FEATURE_KEY = "certificate"

_DEFAULT_DAILY_QUESTION_COUNT = 6
_DEFAULT_REVIEW_RATIO_NEW = 7
_DEFAULT_REVIEW_RATIO_REVIEW = 3
_DEFAULT_TOEIC_TRACK_RATIOS = (1, 2, 3)  # listen, write, vocab（沿用 FR-25 原文預設）


# --- 設定/覆蓋查詢 ---


def _get_owner(db: CloudSQLClient) -> dict | None:
    return db.select(
        "users", where="is_owner = %s AND telegram_user_id IS NOT NULL", params=(True,), fetch_one=True
    )


def _get_settings(db: CloudSQLClient, user_id: int, exam_type: str) -> dict | None:
    return db.select(
        "certificate_daily_settings", where="user_id = %s AND exam_type = %s",
        params=(user_id, exam_type), fetch_one=True,
    )


def get_active_schedule_override(
    db: CloudSQLClient, user_id: int, exam_type: str, target_date: date
) -> dict | None:
    """回傳覆蓋當天的區間設定；同一天理論上不該有多筆重疊區間，若有則取第一筆命中的。"""
    overrides = db.select(
        "certificate_daily_schedule_overrides", where="user_id = %s AND exam_type = %s",
        params=(user_id, exam_type),
    )
    for override in overrides:
        if override["start_date"] <= target_date <= override["end_date"]:
            return override
    return None


def effective_daily_question_count(
    db: CloudSQLClient, user_id: int, exam_type: str, target_date: date
) -> int:
    """FR-26：查詢某天實際生效的出題數量——先查日期區間覆蓋，沒有才 fallback 用全局設定，
    都沒設定過就用預設值（見模組 docstring）。
    """
    override = get_active_schedule_override(db, user_id, exam_type, target_date)
    if override is not None:
        return override["daily_question_count"]

    settings = _get_settings(db, user_id, exam_type)
    if settings is not None:
        return settings["daily_question_count"]

    return _DEFAULT_DAILY_QUESTION_COUNT


# --- 出題比例計算 ---


def _split_by_ratio(total: int, ratios: list[int]) -> list[int]:
    """把 `total` 依 `ratios` 比例整數拆分，總和保證等於 `total`（餘數依序分給前面的項目）。
    `ratios` 總和為 0（或全部無效）時，每項回傳 0，避免除以零。
    """
    ratio_sum = sum(r for r in ratios if r and r > 0)
    if ratio_sum <= 0 or total <= 0:
        return [0 for _ in ratios]

    counts = [total * max(r, 0) // ratio_sum for r in ratios]
    remainder = total - sum(counts)
    index = 0
    while remainder > 0:
        counts[index % len(counts)] += 1
        remainder -= 1
        index += 1
    return counts


def _toeic_track_ratios(settings: dict | None) -> tuple[int, int, int]:
    if settings and settings.get("listen_ratio") and settings.get("write_ratio") and settings.get("vocab_ratio"):
        return settings["listen_ratio"], settings["write_ratio"], settings["vocab_ratio"]
    return _DEFAULT_TOEIC_TRACK_RATIOS


def _review_ratios(settings: dict | None) -> tuple[int, int]:
    if settings and settings.get("review_ratio_new") and settings.get("review_ratio_review"):
        return settings["review_ratio_new"], settings["review_ratio_review"]
    return _DEFAULT_REVIEW_RATIO_NEW, _DEFAULT_REVIEW_RATIO_REVIEW


# --- 候選題目查詢 ---


def _latest_answers_by_question(
    db: CloudSQLClient, user_id: int, exam_type: str, source: str, question_type_filter: str | None
) -> dict[int, dict]:
    """回傳 {題目 id: 該使用者對這題「最新一次」的作答紀錄}，只取每題最新一筆（後來答對就不算
    複習候選、也不再算新題，見模組 docstring）。
    """
    if source == "certificate":
        if question_type_filter is None:
            logs = db.select(
                "answer_logs", where="user_id = %s AND exam_type = %s AND certificate_question_id IS NOT NULL",
                params=(user_id, exam_type),
            )
        else:
            logs = db.select(
                "answer_logs",
                where="user_id = %s AND exam_type = %s AND question_type = %s AND certificate_question_id IS NOT NULL",
                params=(user_id, exam_type, question_type_filter),
            )
        key = "certificate_question_id"
    else:  # vocab
        logs = db.select(
            "answer_logs",
            where="user_id = %s AND exam_type = %s AND question_type = %s AND vocab_question_id IS NOT NULL",
            params=(user_id, exam_type, "vocab"),
        )
        key = "vocab_question_id"

    latest: dict[int, dict] = {}
    for log in logs:
        qid = log[key]
        existing = latest.get(qid)
        if existing is None or log["created_at"] > existing["created_at"]:
            latest[qid] = log
    return latest


def _candidate_certificate_questions(
    db: CloudSQLClient, exam_type: str, question_type_filter: str | None, exclude_ids: set
) -> list[dict]:
    if question_type_filter is None:
        rows = db.select(
            "certificate_questions", where="exam_type = %s AND correct_answer IS NOT NULL", params=(exam_type,)
        )
    else:
        rows = db.select(
            "certificate_questions",
            where="exam_type = %s AND question_type = %s AND correct_answer IS NOT NULL",
            params=(exam_type, question_type_filter),
        )
    return [row for row in rows if row["id"] not in exclude_ids]


def _candidate_vocab_questions(db: CloudSQLClient, exclude_ids: set) -> list[dict]:
    rows = db.select("toeic_vocab_questions")
    return [row for row in rows if row["id"] not in exclude_ids]


def _pick_track_questions(
    db: CloudSQLClient,
    user_id: int,
    exam_type: str,
    question_type_filter: str | None,
    source: str,
    track_total: int,
    review_ratio_new: int,
    review_ratio_review: int,
) -> list[dict]:
    """回傳這一軌要指派的題目清單，每筆 `{"source", "question_id", "is_review"}`。

    複習池只放「最新一次作答結果答錯」的題目；複習題數不夠湊比例時，用新題目補滿（ADR-20 決策 2）。
    """
    new_ratio_count, review_ratio_count = _split_by_ratio(track_total, [review_ratio_new, review_ratio_review])

    latest_by_question = _latest_answers_by_question(db, user_id, exam_type, source, question_type_filter)
    review_candidate_ids = [qid for qid, log in latest_by_question.items() if not log["is_correct"]]
    random.shuffle(review_candidate_ids)
    chosen_review_ids = review_candidate_ids[:review_ratio_count]

    exclude_ids = set(latest_by_question.keys())
    if source == "certificate":
        new_candidates = _candidate_certificate_questions(db, exam_type, question_type_filter, exclude_ids)
    else:
        new_candidates = _candidate_vocab_questions(db, exclude_ids)
    random.shuffle(new_candidates)

    # 複習題不夠湊滿比例時，缺口用新題目補滿，不因複習池不夠而少出題。
    new_needed = new_ratio_count + max(0, review_ratio_count - len(chosen_review_ids))
    chosen_new = new_candidates[:new_needed]

    picks = [{"source": source, "question_id": qid, "is_review": True} for qid in chosen_review_ids]
    picks += [{"source": source, "question_id": row["id"], "is_review": False} for row in chosen_new]
    return picks


def _build_assignment_plan(
    db: CloudSQLClient, user_id: int, exam_type: str, target_date: date
) -> list[dict]:
    total = effective_daily_question_count(db, user_id, exam_type, target_date)
    if total <= 0:
        return []

    settings = _get_settings(db, user_id, exam_type)
    review_ratio_new, review_ratio_review = _review_ratios(settings)

    if exam_type == "toeic":
        listen_ratio, write_ratio, vocab_ratio = _toeic_track_ratios(settings)
        listen_count, write_count, vocab_count = _split_by_ratio(
            total, [listen_ratio, write_ratio, vocab_ratio]
        )
        track_specs = [
            ("listen", "certificate", listen_count),
            ("write", "certificate", write_count),
            ("vocab", "vocab", vocab_count),
        ]
    else:
        track_specs = [(None, "certificate", total)]

    plan: list[dict] = []
    for question_type_filter, source, track_total in track_specs:
        if track_total <= 0:
            continue
        plan.extend(
            _pick_track_questions(
                db, user_id, exam_type, question_type_filter, source, track_total,
                review_ratio_new, review_ratio_review,
            )
        )
    return plan


def _existing_assignments(
    db: CloudSQLClient, user_id: int, exam_type: str, target_date: date
) -> list[dict]:
    return db.select(
        "certificate_daily_assignments",
        where="user_id = %s AND exam_type = %s AND assigned_date = %s",
        params=(user_id, exam_type, target_date),
    )


def assign_daily_questions(
    db: CloudSQLClient, user_id: int, exam_type: str, target_date: date
) -> list[dict]:
    """FR-26：依當天生效設定計算今天要出的題目，寫入 `certificate_daily_assignments`，回傳寫入
    的 assignment 列（含 `id`）。若今天已經指派過（例如同一小時內 `/healthz` 多次觸發），直接
    回傳既有清單，不重複指派、不重複消耗題庫。
    """
    existing = _existing_assignments(db, user_id, exam_type, target_date)
    if existing:
        return existing

    plan = _build_assignment_plan(db, user_id, exam_type, target_date)

    inserted: list[dict] = []
    for item in plan:
        data = {
            "user_id": user_id,
            "exam_type": exam_type,
            "assigned_date": target_date,
            "certificate_question_id": item["question_id"] if item["source"] == "certificate" else None,
            "vocab_question_id": item["question_id"] if item["source"] == "vocab" else None,
            "is_review": item["is_review"],
        }
        row_id = db.insert("certificate_daily_assignments", data)
        data["id"] = row_id
        inserted.append(data)
    return inserted


# --- 推播 ---


def distinct_exam_types_with_questions(db: CloudSQLClient) -> list[str]:
    """回傳題庫裡目前有哪些 exam_type（已補齊正解的題目才算，見 FR-26）。"""
    rows = db.select("certificate_questions")
    return sorted({row["exam_type"] for row in rows if row.get("correct_answer") is not None})


def _format_push_message(exam_type: str, assignments: list[dict]) -> str:
    review_count = sum(1 for a in assignments if a["is_review"])
    new_count = len(assignments) - review_count
    return (
        f"📚 主任，今天的「{exam_type}」複習來囉！共 {len(assignments)} 題"
        f"（{new_count} 題新題、{review_count} 題複習題），回覆「開始作答」開始吧！"
    )


def check_and_push_daily_quiz(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """FR-26：固定台灣時間 08:00，依目前題庫裡有的每個 exam_type 各自計算今天要出的題目、寫入
    `certificate_daily_assignments`，並推播通知。只在 08 點這個小時內執行；`certificate` 功能
    開關關閉時整批跳過。

    當天生效題數為 0（使用者取消或還沒有任何題庫/設定）的 exam_type 不會推播任何訊息，避免無意義
    的空訊息干擾。

    去重：靠「這個 exam_type 今天是否已經指派過」判斷是否已推播過，而非額外的 `pushed_on` 欄位
    ——`certificate_daily_assignments` 同時也是後續作答流程（FR-27）要讀的資料，只在「這次呼叫
    是第一次幫今天建立這批題目」時才推播，避免同一小時內 `/healthz` 多次觸發重複推播。
    """
    now = now or datetime.now(timezone.utc)
    now_local = now.astimezone(_TAIWAN_TZ)
    if now_local.hour != _PUSH_HOUR:
        return

    owner = _get_owner(db)
    if owner is None:
        return

    if not toggles.is_feature_enabled(db, owner["id"], _FEATURE_KEY):
        return

    today = now_local.date()
    for exam_type in distinct_exam_types_with_questions(db):
        already_assigned_today = bool(_existing_assignments(db, owner["id"], exam_type, today))

        try:
            assignments = assign_daily_questions(db, owner["id"], exam_type, today)
        except Exception:
            _logger.exception("每日推播出題失敗（exam_type=%s），不影響其他證照類型", exam_type)
            continue

        if not assignments or already_assigned_today:
            continue

        telegram_client.send_text(
            chat_id=owner["telegram_user_id"], text=_format_push_message(exam_type, assignments)
        )
