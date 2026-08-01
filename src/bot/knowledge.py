"""知識庫查詢與寫入邏輯（對應 docs/specs/chat-core/SPEC.md FR-2、FR-4、FR-5）。

負責組出「這位使用者能看到的知識」——依 FR-10 資安隔離，一般使用者只看得到通用知識庫
（人格背景／家人背景）與自己的客製知識庫，看不到別人的客製知識庫或對話紀錄。
"""
from datetime import datetime, timezone

from submodules.cloudsql.client import CloudSQLClient

_RECENT_LOGS_LIMIT = 10


def build_context(db: CloudSQLClient, user_id: int) -> dict:
    """組出對話核心需要的知識庫 context：人格背景、家人背景、自己的客製知識庫、最近對話紀錄。"""
    family_rows = db.select("knowledge_base", where="category = %s", params=("general_family",))
    custom_rows = db.select(
        "knowledge_base",
        where="category = %s AND user_id = %s",
        params=("custom", user_id),
    )

    return {
        "persona": get_persona_text(db),
        "family": _join_rows(family_rows),
        "custom": [row["content"] for row in custom_rows],
        "recent_logs": _get_recent_logs(db, user_id),
    }


def get_persona_text(db: CloudSQLClient) -> str:
    """單獨取出「Robinson 人格背景」（`general_persona`），不需要 user_id。

    供 `commands.handle_function`（FR-56c：/function 總覽也必須用人格語氣改寫）等
    不需要完整 context 的場景使用，避免每次都要湊一個假的 user_id。
    """
    persona_rows = db.select("knowledge_base", where="category = %s", params=("general_persona",))
    return _join_rows(persona_rows)


def _join_rows(rows: list[dict]) -> str:
    """把同一類別底下的多筆知識庫資料串接成一份文字。

    2026-08-01（見 chat-core SPEC.md FR-11）：`general_persona`／`general_family` 原本一律只有
    一筆（透過 migration 逐字寫入），只取 `rows[0]` 就好；主動新增知識功能上線後，Robin 可能透過
    對話新增第二筆、第三筆 `general_family`／`general_persona` 資料，因此改為把所有符合類別的
    資料都串接進 context，而不是只看第一筆——單筆的情況串接結果與原本行為完全相同，不影響既有測試。
    """
    return "\n\n".join(row["content"] for row in rows) if rows else ""


def _get_recent_logs(db: CloudSQLClient, user_id: int) -> list[dict]:
    rows = db.select("conversation_logs", where="user_id = %s", params=(user_id,))
    active_rows = [row for row in rows if row.get("deleted_at") is None]
    sorted_rows = sorted(active_rows, key=lambda row: row["created_at"])
    return sorted_rows[-_RECENT_LOGS_LIMIT:]


def save_custom_knowledge(db: CloudSQLClient, user_id: int, content: str) -> None:
    """寫入使用者的客製知識庫（FR-4：查到網路答案且使用者同意存檔時呼叫）。"""
    db.insert("knowledge_base", {"category": "custom", "user_id": user_id, "content": content})


def save_knowledge(
    db: CloudSQLClient,
    category: str,
    content: str,
    label: str | None = None,
    user_id: int | None = None,
) -> int:
    """通用知識庫寫入（2026-08-01 新增，見 chat-core SPEC.md FR-11「主動新增知識」）。

    與 `save_custom_knowledge()` 不同之處：這支可以指定任一 `category`（`custom`／
    `general_family`／`general_persona`），並附上分類/標籤 `label`（例如「SOP」「食譜」），
    供之後依主題查找、也供 `/clean-target-dialog`（FR-12）判斷刪除範圍時參考。呼叫端
    （`commands.handle_save_knowledge_confirm_step`）負責在呼叫前把關：非 Owner 一律只能
    傳 `category="custom"`，這裡不重複做權限檢查。
    """
    return db.insert(
        "knowledge_base",
        {"category": category, "user_id": user_id, "label": label, "content": content},
    )


def log_message(db: CloudSQLClient, user_id: int, role: str, content: str) -> None:
    """寫入一筆對話紀錄（FR-5）；created_at 由應用層明確帶入，不依賴資料庫預設值，
    確保同一輪對話內若立即需要重新查詢，時間排序仍然正確。
    """
    db.insert(
        "conversation_logs",
        {
            "user_id": user_id,
            "role": role,
            "content": content,
            "created_at": datetime.now(timezone.utc),
            "deleted_at": None,
        },
    )
