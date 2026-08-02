"""服務健康監控邏輯（對應 docs/specs/robinson/SPEC.md FR-21，Step 1.6）。

Phase 1 範圍：只做 Neon 資料庫容量監控（NFR-3：免費額度 0.5GB，達 80% 主動告警 Robin）。

Gemini 免費額度監控（FR-21 的另一半）Phase 1 刻意暫緩：Gemini 官方沒有提供查詢即時用量的
API，只能用 `submodules/llm` ADR-5 的本地端節流計數器（每支 Key 每分鐘呼叫次數）粗略估算，
沒辦法真的知道「今天/這個月還剩多少免費額度」，準確度有限；既有的 429 例外發生時已經會走
FR-19a 的私訊通知機制，等同事後告警。真正的用量預測式監控留待未來有更好方案或官方 API
支援時再補上（見 2026-08-02 與 Robin 的討論結論）。
"""
from typing import Any

# Neon 免費方案容量上限（見 robinson SPEC.md NFR-3：免費額度僅 0.5GB）。
NEON_FREE_TIER_BYTES = int(0.5 * 1024 * 1024 * 1024)
NEON_CAPACITY_WARNING_THRESHOLD = 0.8

_NEON_CAPACITY_WARNING_TEMPLATE = (
    "⚠️ 主任，Neon 資料庫容量已經用到 {percent:.0f}% 了（{used_mb:.1f}MB／{limit_mb:.0f}MB），"
    "免費額度快用完囉，麻煩看看要不要清理一些舊資料或考慮升級方案！"
)


def get_database_size_bytes(db: Any) -> int:
    """查詢目前 Neon 資料庫佔用容量（bytes），透過 CloudSQLClient.execute_query() 逃生口查詢。"""
    rows = db.execute_query("SELECT pg_database_size(current_database()) AS size_bytes")
    return rows[0]["size_bytes"]


class NeonCapacityMonitor:
    """追蹤 Neon 容量告警狀態，避免同一次超標被重複告警（FR-21）。

    每個 instance 各自獨立記錄「目前是否已經處於告警狀態」；正式環境由 main.py 建立單一
    長期持有的 instance（比照 webhook.py `_state_store` 的既有慣例：process 生命週期內
    共用一份記憶體狀態，process 重啟後會重置，Render 免費方案本來就會不定期休眠重啟，可接受）。
    容量回落到門檻以下時會重置告警狀態，讓下一次再超標時能重新告警一次；只要持續處於超標，
    不會每次呼叫都重複轟炸 Robin。
    """

    def __init__(self) -> None:
        self._warning_sent = False

    def check_and_notify(self, db: Any, telegram_client: Any, robin_chat_id: int | str) -> None:
        size_bytes = get_database_size_bytes(db)
        usage_ratio = size_bytes / NEON_FREE_TIER_BYTES

        if usage_ratio < NEON_CAPACITY_WARNING_THRESHOLD:
            self._warning_sent = False
            return

        if self._warning_sent:
            return

        message = _NEON_CAPACITY_WARNING_TEMPLATE.format(
            percent=usage_ratio * 100,
            used_mb=size_bytes / 1024 / 1024,
            limit_mb=NEON_FREE_TIER_BYTES / 1024 / 1024,
        )
        telegram_client.send_text(chat_id=robin_chat_id, text=message)
        self._warning_sent = True
