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
        "family": family_rows[0]["content"] if family_rows else "",
        "custom": [row["content"] for row in custom_rows],
        "recent_logs": _get_recent_logs(db, user_id),
    }


def get_persona_text(db: CloudSQLClient) -> str:
    """單獨取出「Robinson 人格背景」（`general_persona`），不需要 user_id。

    供 `commands.handle_function`（FR-56c：/function 總覽也必須用人格語氣改寫）等
    不需要完整 context 的場景使用，避免每次都要湊一個假的 user_id。
    """
    persona_rows = db.select("knowledge_base", where="category = %s", params=("general_persona",))
    return persona_rows[0]["content"] if persona_rows else ""


def _get_recent_logs(db: CloudSQLClient, user_id: int) -> list[dict]:
    rows = db.select("conversation_logs", where="user_id = %s", params=(user_id,))
    active_rows = [row for row in rows if row.get("deleted_at") is None]
    sorted_rows = sorted(active_rows, key=lambda row: row["created_at"])
    return sorted_rows[-_RECENT_LOGS_LIMIT:]


def save_custom_knowledge(db: CloudSQLClient, user_id: int, content: str) -> None:
    """寫入使用者的客製知識庫（FR-4：查到網路答案且使用者同意存檔時呼叫）。"""
    db.insert("knowledge_base", {"category": "custom", "user_id": user_id, "content": content})


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
