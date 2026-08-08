"""證照題庫作答與批改（對應 docs/specs/robinson/SPEC.md FR-27、FR-28，Step 3.3）。

負責：找出「目前還可以作答的題目」、組出題目呈現內容（依 `certificate_question_id`／
`vocab_question_id` 決定從軌道一/軌道二哪張題庫表讀）、批改 A/B/C/D 並寫入 `answer_logs`、
台灣時間 20:00 的作答提醒推播。不處理 Telegram 對話狀態機（單題循環的多輪反問），那是
`src/bot/commands.py` 的責任，這裡保持純粹的資料操作與計算，方便獨立測試。

**跨日晚補答（見 SPEC.md FR-28、ADR-20 決策 4）**：23:00 不主動通知（靜默視為跳過），但這不是
硬性截止——只要這個 `exam_type`還沒有更新一天的 assignment 蓋過去，使用者隨時都可以回頭把還
沒作答的題目補完；一旦新的一天推播建立了新 assignment，前一批未作答的題目就自動被視為跳過（不
會再出現在 `get_pending_assignments()` 的結果中）。判斷方式：同一 `exam_type` 只看「最新一批
`assigned_date`」，不需要額外欄位標記「是否已跳過」。

**正解格式（見 `certificate_questions.correct_answer`）**：軌道一的正解是 Robin 拍照上傳、經
Gemini Vision 解析的自由文字（`src/bot/toeic.py` 的 `_ANSWER_VISION_PARSE_PROMPT` 只要求「選項
代號或完整正確選項內容」，格式不完全固定），但作答只接受 A/B/C/D（ADR-20 決策 3），所以這裡用
`_extract_answer_letter()` 從自由文字中萃取開頭的字母；抓不到字母視為資料異常（理論上出題階段
已經篩選過「有 `correct_answer` 才會進入候選池」，這裡是最後一道防線），批改時跳過這題並記警告
log，不讓整個作答流程卡死在一筆有問題的資料上。軌道二（`toeic_vocab_questions.correct_option`）
本來就是嚴格的單一字母欄位，沒有這個問題。
"""
import logging
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from src.bot import toggles
from submodules.cloudsql.client import CloudSQLClient

_logger = logging.getLogger(__name__)

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_REMINDER_HOUR = 20
_FEATURE_KEY = "certificate"

_ANSWER_LETTER_PATTERN = re.compile(r"^\(?\s*([A-Da-d])\s*[\.\)、]?")

_REMINDER_MESSAGE_TEMPLATE = "🔔 主任，今天還有 {count} 題還沒作答喔，要不要現在完成？回覆「開始作答」即可。"
ALL_DONE_MESSAGE = "🎉 今天的題目都作答完了，辛苦啦！"


# --- 待作答題目查詢 ---


def _get_owner(db: CloudSQLClient) -> dict | None:
    return db.select(
        "users", where="is_owner = %s AND telegram_user_id IS NOT NULL", params=(True,), fetch_one=True
    )


def _get_latest_assignment_dates(db: CloudSQLClient, user_id: int) -> dict[str, date]:
    """回傳 {exam_type: 最新一次推播的 assigned_date}；用來判斷「哪一批才是目前有效、可以作答
    的題目」（見模組 docstring「跨日晚補答」）。"""
    rows = db.select("certificate_daily_assignments", where="user_id = %s", params=(user_id,))
    latest: dict[str, date] = {}
    for row in rows:
        exam_type = row["exam_type"]
        if exam_type not in latest or row["assigned_date"] > latest[exam_type]:
            latest[exam_type] = row["assigned_date"]
    return latest


def _is_assignment_answered(db: CloudSQLClient, assignment_id: int) -> bool:
    row = db.select("answer_logs", where="assignment_id = %s", params=(assignment_id,), fetch_one=True)
    return row is not None


def get_pending_assignments(db: CloudSQLClient, user_id: int) -> list[dict]:
    """回傳目前還可以作答的題目（每個 `exam_type` 只看最新一批 `assigned_date`，且尚未透過
    `assignment_id` 對應到任何 `answer_logs` 紀錄的），依 `exam_type`、`id` 排序，讓多個
    `exam_type` 依序作答完一個再做下一個（見 SPEC.md FR-27 作答方式）。
    """
    latest_dates = _get_latest_assignment_dates(db, user_id)
    rows = db.select("certificate_daily_assignments", where="user_id = %s", params=(user_id,))
    pending = [
        row for row in rows
        if row["assigned_date"] == latest_dates.get(row["exam_type"])
        and not _is_assignment_answered(db, row["id"])
    ]
    pending.sort(key=lambda row: (row["exam_type"], row["id"]))
    return pending


# --- 題目呈現內容組裝 ---


def _extract_answer_letter(correct_answer: str) -> str | None:
    """從自由文字的正解中萃取開頭的 A/B/C/D 字母（大小寫皆可，允許「A.」「(A)」「A)」「A、」等
    常見寫法）；完全抓不到視為資料異常，回傳 `None`（見模組 docstring）。"""
    match = _ANSWER_LETTER_PATTERN.match((correct_answer or "").strip())
    return match.group(1).upper() if match else None


def _build_certificate_question_view(question: dict) -> dict | None:
    letter = _extract_answer_letter(question.get("correct_answer") or "")
    if letter is None:
        return None

    options = question.get("options") or []
    options_text = "\n".join(options) if isinstance(options, list) else str(options)
    prompt_lines = [question["question_text"], options_text]
    if question.get("image_gdrive_url"):
        prompt_lines.append(f"🖼️ 題目圖片：{question['image_gdrive_url']}")
    if question.get("audio_gdrive_url"):
        prompt_lines.append(f"🔊 聽力音檔：{question['audio_gdrive_url']}")

    return {
        "prompt": "\n".join(prompt_lines),
        "correct_letter": letter,
        "explanation": question.get("explanation"),
        "question_type": question["question_type"],
    }


def _build_vocab_question_view(question: dict) -> dict:
    options_text = "\n".join(
        [
            f"A. {question['option_a']}",
            f"B. {question['option_b']}",
            f"C. {question['option_c']}",
            f"D. {question['option_d']}",
        ]
    )
    explanation = f"例句：{question['example_sentence']}\n翻譯：{question['example_sentence_translation']}"
    return {
        "prompt": f"{question['question_text']}\n{options_text}",
        "correct_letter": question["correct_option"],
        "explanation": explanation,
        "question_type": "vocab",
    }


def build_question_view(db: CloudSQLClient, assignment: dict) -> dict | None:
    """把一筆 `certificate_daily_assignments` 換算成可以直接呈現給使用者的題目內容
    `{"prompt", "correct_letter", "explanation", "question_type"}`；找不到對應題目，或軌道一
    正解無法解析出字母（資料異常）時回傳 `None`，呼叫端記警告並跳過這題。
    """
    if assignment["certificate_question_id"] is not None:
        question = db.select(
            "certificate_questions", where="id = %s", params=(assignment["certificate_question_id"],), fetch_one=True
        )
        if question is None:
            return None
        return _build_certificate_question_view(question)

    question = db.select(
        "toeic_vocab_questions", where="id = %s", params=(assignment["vocab_question_id"],), fetch_one=True
    )
    if question is None:
        return None
    return _build_vocab_question_view(question)


def format_question_prompt(question_view: dict, position: int, total: int) -> str:
    """組出發給使用者的第 N 題訊息（FR-27：一次一題，答完才給下一題）。"""
    return f"📝 第 {position}/{total} 題\n\n{question_view['prompt']}\n\n請回覆 A/B/C/D："


def format_grading_feedback(is_correct: bool, question_view: dict) -> str:
    """組出批改結果訊息，附上正解與詳解（詳解為 `None` 時不附加，FR-27）。"""
    verdict = "✅ 答對了！" if is_correct else "❌ 答錯了。"
    lines = [f"{verdict}正解是 {question_view['correct_letter']}。"]
    if question_view.get("explanation"):
        lines.append(f"詳解：{question_view['explanation']}")
    return "\n".join(lines)


# --- 批改與寫入 ---


def grade_answer(letter: str, question_view: dict) -> bool:
    """比對使用者回覆的字母（呼叫端已確認是 A/B/C/D 才會呼叫這裡）跟正解是否相符。"""
    return letter.upper() == question_view["correct_letter"].upper()


def record_answer(
    db: CloudSQLClient, user_id: int, assignment: dict, question_view: dict, is_correct: bool, answered_on: date
) -> int:
    """寫入一筆作答紀錄，`assignment_id` 對應這次是回答哪一筆每日推播指派（見模組 docstring
    「跨日晚補答」的判斷依據），回傳新增紀錄的 id。
    """
    data = {
        "user_id": user_id,
        "certificate_question_id": assignment["certificate_question_id"],
        "vocab_question_id": assignment["vocab_question_id"],
        "exam_type": assignment["exam_type"],
        "question_type": question_view["question_type"],
        "is_correct": is_correct,
        "answered_on": answered_on,
        "assignment_id": assignment["id"],
    }
    return db.insert("answer_logs", data)


# --- 20:00 作答提醒 ---


def check_and_push_answer_reminders(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """FR-28：固定台灣時間 20:00，若還有題目沒作答，提醒一次；只在 20 點這個小時內執行，同一天
    最多推播一次（`users.certificate_answer_reminder_sent_on` 去重，比照
    `toeic_pipeline_last_run_on` 既有慣例）。這裡只是單純提醒，不直接發題目，使用者要回覆
    「開始作答」才真正進入作答流程（見 `src/bot/commands.py`）。
    """
    now = now or datetime.now(timezone.utc)
    now_local = now.astimezone(_TAIWAN_TZ)
    if now_local.hour != _REMINDER_HOUR:
        return

    owner = _get_owner(db)
    if owner is None:
        return

    if not toggles.is_feature_enabled(db, owner["id"], _FEATURE_KEY):
        return

    today = now_local.date()
    if owner.get("certificate_answer_reminder_sent_on") == today:
        return

    pending = get_pending_assignments(db, owner["id"])
    if not pending:
        return

    telegram_client.send_text(
        chat_id=owner["telegram_user_id"], text=_REMINDER_MESSAGE_TEMPLATE.format(count=len(pending))
    )
    db.update(
        "users", {"certificate_answer_reminder_sent_on": today}, where="id = %s", params=(owner["id"],)
    )
