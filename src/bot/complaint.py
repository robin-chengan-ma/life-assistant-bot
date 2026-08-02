"""客訴收集純邏輯（對應 docs/specs/robinson/SPEC.md FR-60～FR-63，Step 1.9）。

負責：新增客訴紀錄、組出讓 Gemini 分析客訴內容的 Prompt。不處理任何 Telegram 對話流程或私訊
Robin 的動作（那是 src/bot/commands.py 的責任），保持這個模組是純粹的資料/文字組裝操作，
方便獨立測試。
"""
from submodules.cloudsql.client import CloudSQLClient

_ANALYSIS_PROMPT_TEMPLATE = (
    "以下是一位使用者針對 Robinson（一個 Telegram 生活小助手機器人）提出的客訴/意見回饋內容：\n"
    "「{content}」\n\n"
    "請你用自然口語、精簡的方式，幫忙整理成給開發者 Robin 看的分析報告，包含兩部分：\n"
    "1. 可能的問題點：這則回饋反映出的具體問題或不滿意的地方\n"
    "2. 修正/優化建議：具體可行的改善方向\n"
    "不需要客套開場白，直接條列這兩部分內容即可。"
)


def create_complaint(db: CloudSQLClient, user_id: int, content: str) -> int:
    """新增一筆客訴紀錄（FR-61），回傳新建列的 id。"""
    return db.insert("complaints", {"user_id": user_id, "content": content})


def build_analysis_prompt(content: str) -> str:
    """組出送給 Gemini 分析客訴內容的 Prompt（FR-62：可能問題點＋修正/優化建議）。"""
    return _ANALYSIS_PROMPT_TEMPLATE.format(content=content)
