"""心情小記純邏輯（對應 docs/specs/robinson/SPEC.md FR-49、FR-50，Step 1.8）。

負責：心情分類的解析與清單文字組裝、新增/查詢/更新/刪除純資料操作。不處理任何 Telegram 對話流程或
LLM 呼叫（那是 src/bot/commands.py 的責任），保持這個模組是純粹的資料操作，方便獨立測試。

FR-49（紀錄每日心情與隨筆）與 FR-50（個人成就三選一提示，使用者自行選擇是否回答）都不需要 LLM
判斷使用者意圖——心情分類是固定 6 選一（`_MOOD_CATEGORIES`），個人成就是「有填就存、沒填就跳過」
的簡單二分，兩者都能用純字串比對完成，不像 Step 1.7 待辦事項需要 LLM 解析模糊的自然語言時間。

2026-08-02 新增（見 robinson SPEC.md FR-49 補記/更新/刪除擴充）：Robin 提出「記帳、心情小記、
體重、飲食、運動習慣都要有補記、更新、刪除、新增的功能」，心情小記排在最優先實作。新增
`mood_journals.entry_date`（`0017_add_entry_date_to_mood_journals.sql`）記錄這筆心情小記
實際對應的日期，比照 `todo.py` 的 `start_at`／`due_at` 做法：一律由呼叫端（`commands.py`）
用台灣時區算好日期後再傳進來，不依賴資料庫預設值，才能正確支援「補記昨天/上星期五」這種
跟今天不同天的情境。既有舊資料（此欄位新增前就存在的列）`entry_date` 為 NULL，讀取時一律
fallback 使用 `created_at` 的台灣時區日期部分，語意上等同「當時新增的那天就是實際發生的那天」。
"""
from datetime import date
from zoneinfo import ZoneInfo

from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")

# FR-56h 情境範例列出的固定 6 種分類，順序即為呈現給使用者的編號順序。
MOOD_CATEGORIES: list[tuple[str, str]] = [
    ("angry_anxious", "生氣/焦慮"),
    ("sad_down", "難過/低落"),
    ("tired_burned_out", "疲倦/厭世"),
    ("neutral", "普通/平淡"),
    ("calm_relaxed", "平靜/放鬆"),
    ("happy_excited", "高興/興奮"),
]
_LABEL_BY_CODE = dict(MOOD_CATEGORIES)
_CODE_BY_LABEL = {label: code for code, label in MOOD_CATEGORIES}


def format_category_prompt() -> str:
    """組出讓使用者選擇心情分類的編號清單文字（FR-56h：「請幫我選一個」）。"""
    lines = ["好啊，那你今天的心情狀態如何？請幫我選一個（輸入編號或直接打名稱）：", ""]
    for index, (_, label) in enumerate(MOOD_CATEGORIES, start=1):
        lines.append(f"{index}. {label}")
    return "\n".join(lines)


def resolve_category(text: str) -> str | None:
    """把使用者輸入解析成心情分類代碼；接受編號（1-6）或直接輸入分類名稱，兩者皆無法比對時回傳 None。"""
    text = text.strip()
    if text.isdigit():
        index = int(text)
        if 1 <= index <= len(MOOD_CATEGORIES):
            return MOOD_CATEGORIES[index - 1][0]
        return None
    return _CODE_BY_LABEL.get(text)


def category_label(code: str) -> str:
    """依代碼查回顯示用的中文標籤，供組回覆文字使用。"""
    return _LABEL_BY_CODE[code]


def create_mood_journal(
    db: CloudSQLClient, user_id: int, mood_category: str, content: str, entry_date: date
) -> int:
    """新增一筆心情小記（FR-49），回傳新建列的 id；`achievement_note`（FR-50）留待後續由
    `set_achievement_note()` 補上，新增當下預設 NULL。

    `entry_date` 必填：一般新增時呼叫端傳今天的台灣日期，補記時傳使用者指定的過去日期，
    一律由呼叫端算好再傳進來（不可以依賴資料庫預設值），理由見本模組 docstring。
    """
    return db.insert(
        "mood_journals",
        {
            "user_id": user_id,
            "mood_category": mood_category,
            "content": content,
            "achievement_note": None,
            "entry_date": entry_date,
        },
    )


def set_achievement_note(db: CloudSQLClient, journal_id: int, achievement_note: str) -> None:
    """補上 FR-50 個人成就三選一提示的回答；使用者選擇跳過時呼叫端不會呼叫這個函式，欄位維持 NULL。"""
    db.update("mood_journals", {"achievement_note": achievement_note}, where="id = %s", params=(journal_id,))


def entry_date_of(row: dict) -> date:
    """取這筆心情小記對應的日期：`entry_date` 有值就直接用；NULL（新增 entry_date 欄位前的
    舊資料）則 fallback 使用 `created_at` 換算成台灣時區後的日期部分。"""
    entry_date = row.get("entry_date")
    if entry_date is not None:
        return entry_date
    return row["created_at"].astimezone(_TAIWAN_TZ).date()


def list_mood_journals(db: CloudSQLClient, user_id: int, limit: int = 10) -> list[dict]:
    """查詢某使用者的心情小記，依實際發生日期由新到舊排序，供查詢/補記/更新/刪除流程共用。

    `limit`：只取最近 N 筆讓使用者從清單挑選要更新/刪除的項目，避免記錄一多清單就長到不可用
    （比照 `todo.list_pending_todos()` 的清單呈現用途，但心情小記沒有「已完成/待處理」狀態
    可以篩掉，改用筆數上限控制清單長度）。
    """
    rows = db.select("mood_journals", where="user_id = %s", params=(user_id,))
    rows.sort(key=lambda row: (entry_date_of(row), row["id"]), reverse=True)
    return rows[:limit]


def format_mood_journal_list(journals: list[dict]) -> str:
    """把心情小記清單格式化成使用者看的編號清單文字，供查詢與更新/刪除流程共用。"""
    if not journals:
        return "目前還沒有心情小記紀錄喔！"
    lines = ["這是你最近的心情小記：", ""]
    for index, item in enumerate(journals, start=1):
        content = item["content"]
        preview = content if len(content) <= 20 else content[:20] + "…"
        entry_date = entry_date_of(item)
        lines.append(f"{index}. {entry_date:%Y/%m/%d} {category_label(item['mood_category'])}：{preview}")
    return "\n".join(lines)


def update_mood_journal(db: CloudSQLClient, journal_id: int, mood_category: str, content: str) -> None:
    """更新一筆心情小記的分類與內容（補記/更新功能）；`entry_date` 與 `achievement_note` 不在這裡
    異動——`entry_date` 更新時沿用原本記錄的那一天，`achievement_note` 由後續 `set_achievement_note()`
    視使用者是否重新回答再決定要不要覆蓋。"""
    db.update(
        "mood_journals",
        {"mood_category": mood_category, "content": content},
        where="id = %s",
        params=(journal_id,),
    )


def delete_mood_journal(db: CloudSQLClient, journal_id: int) -> None:
    """刪除一筆心情小記（使用者明確確認後才會呼叫，見 commands.py 的刪除確認流程）。"""
    db.delete("mood_journals", where="id = %s", params=(journal_id,))
