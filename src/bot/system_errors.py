"""系統錯誤記錄與解法追蹤（對應 docs/specs/robinson/SPEC.md FR-19j，2026-08-09 新增）。

讓 `webhook._notify_robin_of_error()` 既有的「私訊 Robin＋Google Drive log 連結」機制
（見 FR-19b）額外落地一份可查詢、可補記解法的紀錄，存進 `system_error_reports` 表。寫入時機
與私訊同一次流程一起發生（見 webhook.py），本模組只負責純粹的資料操作，方便獨立測試。

跟 `complaints`（使用者主動送出的客訴，FR-60～FR-63）刻意分成兩張表：使用者客訴只是查看，不需要
解法欄位；系統主動推送的錯誤回報才需要追蹤處理進度，兩者性質不同（2026-08-09 Robin 澄清）。

`resolution` 支援兩個寫入入口共用同一套邏輯：Telegram「錯誤ID=N 已處理：{解法內容}」單行指令
（見 `src/bot/router.py`）與 Mobile App 客訴回饋頁的「系統錯誤回報」區塊（見
docs/specs/mobile-app/SPEC.md ADR-1，Phase 4 開工時才會有 App 端程式碼）。
"""
import re

from submodules.cloudsql.client import CloudSQLClient

# FR-19j：例外訊息常見會把完整 Request URL 一併印出，若 URL 帶查詢字串型金鑰（例如
# `?api_key=xxx`）會直接外洩；落地到資料庫前，把任何 URL 的查詢字串部分去掉，只保留網域與路徑。
_URL_QUERY_STRING_PATTERN = re.compile(r"(https?://[^\s?]+)\?[^\s]*")


def sanitize_error_summary(text: str, max_len: int = 300) -> str:
    """FR-19j：把錯誤摘要裡帶查詢字串的 URL 去掉查詢字串（避免金鑰外洩），並截斷過長內容。

    完整、未經處理的原始 Traceback 仍只透過 `drive_log_url`（FR-19b 既有機制）取得，這裡的
    `error_summary` 只是給 App／Telegram 快速瀏覽用的簡短版本，不追求完整資訊量。
    """
    text = _URL_QUERY_STRING_PATTERN.sub(r"\1", text or "").strip()
    if not text:
        return "(無法取得錯誤描述)"
    if len(text) > max_len:
        text = text[:max_len] + "...（已截斷）"
    return text


def record_error_report(
    db: CloudSQLClient,
    *,
    severity: str,
    triggering_feature: str,
    error_summary: str,
    drive_log_url: str | None,
) -> int:
    """寫入一筆系統錯誤紀錄，回傳內部序號（供私訊 Robin 時附上「錯誤ID=N」）。

    `error_summary` 在寫入前先經過 `sanitize_error_summary()` 處理，呼叫端不需要自己先處理過。
    """
    return db.insert(
        "system_error_reports",
        {
            "severity": severity,
            "triggering_feature": triggering_feature,
            "error_summary": sanitize_error_summary(error_summary),
            "drive_log_url": drive_log_url,
            "resolution": None,
        },
    )


def update_resolution(db: CloudSQLClient, report_id: int, resolution: str) -> bool:
    """記錄／更新某筆系統錯誤紀錄的解法；找不到對應 ID 回傳 `False`，讓呼叫端可以回覆提示訊息
    （例如 Telegram 指令打錯 ID 時），不強行覆蓋不存在的紀錄。
    """
    existing = db.select("system_error_reports", where="id = %s", params=(report_id,), fetch_one=True)
    if existing is None:
        return False
    db.update("system_error_reports", {"resolution": resolution}, where="id = %s", params=(report_id,))
    return True


def list_error_reports(db: CloudSQLClient) -> list[dict]:
    """列出所有系統錯誤紀錄，依發生時間新到舊排序，供 Mobile App「系統錯誤回報」區塊使用。"""
    rows = db.select("system_error_reports")
    rows.sort(key=lambda row: row["occurred_at"], reverse=True)
    return rows
