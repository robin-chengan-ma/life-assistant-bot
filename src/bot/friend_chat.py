"""好友模式陪伴聊天純邏輯（對應 docs/specs/robinson/SPEC.md FR-51、FR-52，ADR-22，Step 3.5）。

被動觸發（使用者主動說「陪我聊聊」／`/friend_chat`）：動態讀取這位使用者「目前已開啟且近期
（預設過去 7 天）有資料」的所有功能模組近期紀錄，組成 Prompt 交給 LLM 生成一段陪伴式對話回覆。
不處理任何 Telegram 對話流程或實際呼叫 LLM（那是 `src/bot/commands.py` 的責任），保持這個模組
是純粹的資料查詢與文字組裝，方便獨立測試。

**不寫死固定模組清單**（ADR-22 決策 3）：`_DATA_PROVIDERS` 是一個可擴充的清單，每個 provider
各自負責一個功能模組「近期摘要文字」的查詢與格式化。`gather_recent_context()` 逐一檢查這位
使用者的 `feature_toggles` 開啟狀態，開啟且該 provider 回傳非空摘要才納入；因此 Robin 觸發時
可能包含技術情報／證照準備等僅 Robin 可用模組的近況，其他家人觸發時則只會看到自己有用到的
模組。日後新增功能模組時，只需要在這裡多寫一個 provider 函式並加進 `_DATA_PROVIDERS`，不需要
改動呼叫端邏輯，也不需要為「Robin」與「一般家人」分別寫兩套判斷邏輯。

各 provider 的「近期」定義依模組性質微調，不強求全部套用同一種語意：
- 心情小記／體態管理／記帳：過去 `LOOKBACK_DAYS` 天內「新增」的紀錄。
- 待辦事項：未來 `LOOKBACK_DAYS` 天內即將到期的待辦（待辦本質是「將要發生的事」，不是過去發生的
  事，往前看比往後看更符合「近況」的語感）。
- 證照準備：複用既有 `certificate_stats.compute_daily_period_stats()`，統計過去 `LOOKBACK_DAYS`
  天的日常小考作答成效。

FR-51（心情趨勢改文字/emoji 摘要，不做圖表，見 ADR-22 決策 1）由 `_mood_provider()` 實現，內容
會自然併入 FR-52 的陪伴回覆中，不是獨立指令、也不產生任何圖片。

只做被動模式（ADR-22 決策 2）：本模組沒有任何排程或去重欄位，每次呼叫都是完全獨立、即時計算，
不會寫入任何資料。
"""
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from submodules.cloudsql.client import CloudSQLClient

from src.bot import certificate_stats, finance, mood, toggles
from src.bot import todo as todo_module
from src.bot.body import list_diet_logs, list_exercise_logs, list_weight_logs

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")

# 過去/未來幾天算「近期」，純粹是程式常數（見 ADR-22 後果），之後覺得太短/太長可以直接調整，
# 不需要動資料表。
LOOKBACK_DAYS = 7

_MOOD_EMOJI = {
    "angry_anxious": "😠",
    "sad_down": "😔",
    "tired_burned_out": "😩",
    "neutral": "😐",
    "calm_relaxed": "😌",
    "happy_excited": "😄",
}
_POSITIVE_CATEGORIES = {"calm_relaxed", "happy_excited"}
_NEGATIVE_CATEGORIES = {"angry_anxious", "sad_down", "tired_burned_out"}

_MODULE_LABELS = {
    "mood_journal": "心情小記",
    "todo": "待辦事項",
    "body": "體態管理",
    "budget": "記帳",
    "certificate": "證照準備",
}


def _mood_provider(db: CloudSQLClient, user_id: int, today: date) -> str | None:
    """FR-51：心情趨勢改文字/emoji 摘要（見 ADR-22 決策 1），不做圖片圖表。"""
    window_start = today - timedelta(days=LOOKBACK_DAYS - 1)
    journals = [
        row
        for row in mood.list_mood_journals(db, user_id, limit=50)
        if window_start <= mood.entry_date_of(row) <= today
    ]
    if not journals:
        return None
    journals.sort(key=mood.entry_date_of)

    emoji_seq = "".join(_MOOD_EMOJI.get(row["mood_category"], "❓") for row in journals)
    positive = sum(1 for row in journals if row["mood_category"] in _POSITIVE_CATEGORIES)
    negative = sum(1 for row in journals if row["mood_category"] in _NEGATIVE_CATEGORIES)
    if positive > negative:
        trend = "整體偏正向"
    elif negative > positive:
        trend = "整體偏低落"
    else:
        trend = "情緒起伏不定"

    return f"最近 {len(journals)} 筆心情紀錄：{emoji_seq}（{trend}）"


def _todo_provider(db: CloudSQLClient, user_id: int, today: date) -> str | None:
    """待辦事項近況：未來 `LOOKBACK_DAYS` 天內即將到期的待辦（見模組 docstring「近期」定義說明）。"""
    window_end = today + timedelta(days=LOOKBACK_DAYS - 1)
    upcoming = [
        item
        for item in todo_module.list_pending_todos(db, user_id)
        if today <= item["due_at"].astimezone(_TAIWAN_TZ).date() <= window_end
    ]
    if not upcoming:
        return None

    preview = "、".join(
        f"{item['content']}（{item['due_at'].astimezone(_TAIWAN_TZ):%m/%d}）" for item in upcoming[:5]
    )
    return f"近期待辦事項共 {len(upcoming)} 件：{preview}"


def _body_provider(db: CloudSQLClient, user_id: int, today: date) -> str | None:
    """體態管理近況：過去 `LOOKBACK_DAYS` 天內的體重/運動/飲食紀錄。"""
    window_start = today - timedelta(days=LOOKBACK_DAYS - 1)

    def _within_window(rows: list[dict]) -> list[dict]:
        return [row for row in rows if window_start <= row["entry_date"] <= today]

    weight_logs = _within_window(list_weight_logs(db, user_id, limit=50))
    exercise_logs = _within_window(list_exercise_logs(db, user_id, limit=50))
    diet_logs = _within_window(list_diet_logs(db, user_id, limit=50))
    if not weight_logs and not exercise_logs and not diet_logs:
        return None

    parts = []
    if weight_logs:
        latest = max(weight_logs, key=lambda row: row["entry_date"])
        parts.append(f"體重紀錄 {len(weight_logs)} 筆（最新 {float(latest['weight_kg']):.1f} 公斤）")
    if exercise_logs:
        total_minutes = sum(row["duration_minutes"] for row in exercise_logs)
        parts.append(f"運動紀錄 {len(exercise_logs)} 筆（累積 {total_minutes} 分鐘）")
    if diet_logs:
        parts.append(f"飲食/飲水紀錄 {len(diet_logs)} 筆")
    return "、".join(parts)


def _budget_provider(db: CloudSQLClient, user_id: int, today: date) -> str | None:
    """記帳近況：過去 `LOOKBACK_DAYS` 天內的記帳交易。"""
    window_start = today - timedelta(days=LOOKBACK_DAYS - 1)
    transactions = [
        row
        for row in finance.list_transactions(db, user_id, limit=50)
        if window_start <= row["transaction_date"] <= today
    ]
    if not transactions:
        return None

    expense_total = sum(float(row["amount"]) for row in transactions if row["type"] == "expense")
    income_total = sum(float(row["amount"]) for row in transactions if row["type"] == "income")
    summary = f"近期記帳 {len(transactions)} 筆，支出共 {expense_total:.0f} 元"
    if income_total:
        summary += f"、收入共 {income_total:.0f} 元"
    return summary


def _certificate_provider(db: CloudSQLClient, user_id: int, today: date) -> str | None:
    """證照準備近況：複用 `certificate_stats`，統計過去 `LOOKBACK_DAYS` 天各 `exam_type` 的日常
    小考作答成效；`known_exam_types()` 沒有任何資料時直接回傳 None，不硬湊內容。"""
    exam_types = certificate_stats.known_exam_types(db, user_id)
    if not exam_types:
        return None

    window_start = today - timedelta(days=LOOKBACK_DAYS - 1)
    parts = []
    for exam_type in exam_types:
        stats = certificate_stats.compute_daily_period_stats(db, user_id, exam_type, window_start, today)
        if stats["total_answered"] == 0:
            continue
        accuracy = stats["total_correct"] / stats["total_answered"] * 100
        parts.append(f"「{exam_type}」近期測驗 {stats['total_answered']} 題，正確率約 {accuracy:.0f}%")
    return "；".join(parts) if parts else None


# ADR-22 決策 3：不寫死清單，這裡是唯一需要維護的登記點；日後新增模組只需要在這裡多加一筆。
_DATA_PROVIDERS = [
    ("mood_journal", _mood_provider),
    ("todo", _todo_provider),
    ("body", _body_provider),
    ("budget", _budget_provider),
    ("certificate", _certificate_provider),
]


def gather_recent_context(db: CloudSQLClient, user_id: int, today: date) -> dict[str, str]:
    """依 ADR-22 決策 3：逐一檢查這位使用者的 `feature_toggles` 開啟狀態＋該模組近期是否有資料，
    兩者皆滿足才納入，回傳 `{feature_key: 摘要文字}`（依 `_DATA_PROVIDERS` 順序）。"""
    context: dict[str, str] = {}
    for feature_key, provider in _DATA_PROVIDERS:
        if not toggles.is_feature_enabled(db, user_id, feature_key):
            continue
        summary = provider(db, user_id, today)
        if summary:
            context[feature_key] = summary
    return context


_PROMPT_TEMPLATE = """\
你是 Robinson，一個溫暖、有同理心、活潑的個人生活小助手。現在使用者主動想找你聊聊天、聽你聊聊他最近的\
生活狀況，請用自然口語、像朋友聊天一樣連貫的語氣，寫一段陪伴式的回覆（150~250 字，繁體中文），不要用\
條列式呈現。這位使用者的身份/稱謂是「{role}」，請用符合這個身份的方式稱呼他。

【最近 {lookback_days} 天的生活近況】
{context_text}

請根據以上資料自然地聊聊、給予關心或鼓勵；如果有心情紀錄，自然地提到心情趨勢（可以直接引用上面的\
emoji）；如果完全沒有任何近況資料，就溫暖地關心對方最近過得如何、邀請對方分享，不要假裝有資料。\
絕對不能捏造任何上面沒有提到的具體數字或事件，也不要用制式問候語開頭。請直接輸出要回覆給使用者的\
內容本身，不要加上任何前綴說明或標題。
"""


def build_companion_prompt(role: str, context: dict[str, str], lookback_days: int = LOOKBACK_DAYS) -> str:
    """組出餵給 LLM 生成好友聊天回覆的 Prompt（FR-52）。"""
    if context:
        context_text = "\n".join(
            f"・【{_MODULE_LABELS.get(key, key)}】{text}" for key, text in context.items()
        )
    else:
        context_text = "（最近沒有任何功能模組的紀錄資料）"
    return _PROMPT_TEMPLATE.format(role=role, lookback_days=lookback_days, context_text=context_text)
