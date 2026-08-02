"""心情小記純邏輯（對應 docs/specs/robinson/SPEC.md FR-49、FR-50，Step 1.8）。

負責：心情分類的解析與清單文字組裝、新增/補上個人成就純資料操作。不處理任何 Telegram 對話流程或
LLM 呼叫（那是 src/bot/commands.py 的責任），保持這個模組是純粹的資料操作，方便獨立測試。

FR-49（紀錄每日心情與隨筆）與 FR-50（個人成就三選一提示，使用者自行選擇是否回答）都不需要 LLM
判斷使用者意圖——心情分類是固定 6 選一（`_MOOD_CATEGORIES`），個人成就是「有填就存、沒填就跳過」
的簡單二分，兩者都能用純字串比對完成，不像 Step 1.7 待辦事項需要 LLM 解析模糊的自然語言時間。
"""
from submodules.cloudsql.client import CloudSQLClient

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


def create_mood_journal(db: CloudSQLClient, user_id: int, mood_category: str, content: str) -> int:
    """新增一筆心情小記（FR-49），回傳新建列的 id；`achievement_note`（FR-50）留待後續由
    `set_achievement_note()` 補上，新增當下預設 NULL。
    """
    return db.insert(
        "mood_journals",
        {"user_id": user_id, "mood_category": mood_category, "content": content, "achievement_note": None},
    )


def set_achievement_note(db: CloudSQLClient, journal_id: int, achievement_note: str) -> None:
    """補上 FR-50 個人成就三選一提示的回答；使用者選擇跳過時呼叫端不會呼叫這個函式，欄位維持 NULL。"""
    db.update("mood_journals", {"achievement_note": achievement_note}, where="id = %s", params=(journal_id,))
