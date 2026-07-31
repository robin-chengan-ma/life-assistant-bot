"""長記憶滾動摘要邏輯（對應 docs/specs/chat-core/SPEC.md ADR-3、FR-6～FR-8）。

跟 src/bot/knowledge.py 的短記憶（最近 10 則原文）不同，這裡處理的是「更久以前」的對話：
定期把 backlog（比短記憶更早、還沒被摘要過的對話）濃縮進一份滾動更新的摘要文字，
避免長期對話下 prompt 長度與呼叫成本無上限成長。
"""
import logging
from datetime import datetime, timezone

from submodules.cloudsql.client import CloudSQLClient

_logger = logging.getLogger(__name__)

_SHORT_MEMORY_WINDOW = 10  # 需與 knowledge.py 的短記憶則數一致，避免短記憶範圍內的對話被重複摘要
_BACKLOG_THRESHOLD = 10


def get_or_create_summary_row(db: CloudSQLClient, user_id: int) -> dict:
    """取得使用者的長記憶摘要列；不存在則建立一筆空白摘要（FR-8）。"""
    row = db.select("conversation_summaries", where="user_id = %s", params=(user_id,), fetch_one=True)
    if row:
        return row

    db.insert(
        "conversation_summaries",
        {"user_id": user_id, "summary": "", "summarized_up_to_log_id": 0},
    )
    return db.select("conversation_summaries", where="user_id = %s", params=(user_id,), fetch_one=True)


def get_summary(db: CloudSQLClient, user_id: int) -> str:
    """取得目前的長記憶摘要文字（FR-6），供 chat.py 組 prompt 使用。"""
    return get_or_create_summary_row(db, user_id)["summary"]


def maybe_update_summary(db: CloudSQLClient, text_llm_client, user_id: int) -> None:
    """檢查 backlog 是否達門檻，達到才呼叫 LLM 更新摘要（FR-7）。

    摘要更新不是本輪聊天回覆的關鍵路徑（見 ADR-3 後果段落）：呼叫端應在算出並送出
    本次聊天回覆「之後」才呼叫這個函式，且這裡主動吞掉所有例外只記錄 log，
    確保摘要更新失敗不會讓使用者收不到這次的聊天回覆。
    """
    try:
        _update_summary_if_needed(db, text_llm_client, user_id)
    except Exception:
        _logger.exception("長記憶摘要更新失敗（user_id=%s），略過本次更新", user_id)


def _update_summary_if_needed(db: CloudSQLClient, text_llm_client, user_id: int) -> None:
    summary_row = get_or_create_summary_row(db, user_id)
    watermark = summary_row["summarized_up_to_log_id"]

    all_logs = db.select("conversation_logs", where="user_id = %s", params=(user_id,))
    active_logs = sorted(
        (row for row in all_logs if row.get("deleted_at") is None),
        key=lambda row: row["created_at"],
    )
    short_memory_ids = {row["id"] for row in active_logs[-_SHORT_MEMORY_WINDOW:]}

    backlog = [
        row for row in active_logs
        if row["id"] > watermark and row["id"] not in short_memory_ids
    ]
    if len(backlog) < _BACKLOG_THRESHOLD:
        return

    backlog_text = "\n".join(
        f"{'使用者' if row['role'] == 'user' else 'Robinson'}：{row['content']}" for row in backlog
    )
    prompt = (
        "請把下面新增的對話內容，融合進既有摘要中，輸出一份更新後的精簡摘要。"
        "只保留重要事實、偏好與約定，不需要保留逐字對話細節。\n\n"
        f"【既有摘要】\n{summary_row['summary'] or '（無）'}\n\n"
        f"【新增對話內容】\n{backlog_text}"
    )
    new_summary = text_llm_client.generate_text(prompt)
    new_watermark = backlog[-1]["id"]

    db.update(
        "conversation_summaries",
        {
            "summary": new_summary,
            "summarized_up_to_log_id": new_watermark,
            "updated_at": datetime.now(timezone.utc),
        },
        where="user_id = %s",
        params=(user_id,),
    )
