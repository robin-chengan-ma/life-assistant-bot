"""系統錯誤記錄與解法追蹤（對應 docs/specs/robinson/SPEC.md FR-19j，2026-08-09 新增）。

讓 `webhook._notify_robin_of_error()` 既有的「私訊 Robin＋Google Drive log 連結」機制
（見 FR-19b）額外落地一份可查詢、可補記解法的紀錄，存進 `system_error_reports` 表。寫入時機
與私訊同一次流程一起發生（見 webhook.py），本模組只負責純粹的資料操作，方便獨立測試。

這些是系統自動偵測且可追蹤處理狀態的錯誤紀錄，可由 Robin 補記解法。

`resolution` 只能由 Owner 在 Telegram「系統錯誤管理」選單結案；Mobile App
只是事故來源，不提供錯誤管理寫入入口。
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from submodules.cloudsql.client import CloudSQLClient

# FR-19j：例外訊息常見會把完整 Request URL 一併印出，若 URL 帶查詢字串型金鑰（例如
# `?api_key=xxx`）會直接外洩；落地到資料庫前，把任何 URL 的查詢字串部分去掉，只保留網域與路徑。
_URL_QUERY_STRING_PATTERN = re.compile(r"(https?://[^\s?]+)\?[^\s]*")
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(token|password|api[_-]?key|secret)\s*[=:]\s*\S+"
)
_INTERNAL_PATH_PATTERN = re.compile(r"/(?:[^\s/:]+/)+[^\s:]+")
_SQL_STATEMENT_PATTERN = re.compile(r"(?i)\b(SELECT|INSERT|UPDATE|DELETE|ALTER|DROP|CREATE)\b")
_DEDUP_WINDOW = timedelta(minutes=10)


@dataclass(frozen=True)
class IncidentRecord:
    report_id: int
    is_new: bool


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


def safe_display_summary(text: str | None, max_len: int = 300) -> str:
    """供 Owner 選單顯示；隱藏秘密指派、伺服器路徑與 SQL 原文。"""
    value = sanitize_error_summary(text or "", max_len=max_len)
    if _SQL_STATEMENT_PATTERN.search(value):
        return "內部資料處理失敗（詳細內容已隱藏）"
    value = _SENSITIVE_ASSIGNMENT_PATTERN.sub(r"\1=[已隱藏]", value)
    return _INTERNAL_PATH_PATTERN.sub("[內部路徑]", value)


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
            "owner_notification_method": None,
            "owner_notification_status": "pending",
            "owner_notified_at": None,
            "recovery_status": "pending",
            "recovery_sent_at": None,
            "source_platform": "telegram",
            "occurrence_count": 1,
            "last_occurred_at": datetime.now(timezone.utc),
            "resolved_by_user_id": None,
            "resolved_at": None,
        },
    )


def record_or_merge_error_report(
    db: CloudSQLClient,
    *,
    severity: str,
    triggering_feature: str,
    error_summary: str,
    drive_log_url: str | None,
    source_platform: str,
    affected_user_id: int | None = None,
    now: datetime | None = None,
) -> IncidentRecord:
    """建立事故，或把 10 分鐘內同平台、功能、摘要的未結案錯誤合併。"""
    occurred_at = now or datetime.now(timezone.utc)
    summary = sanitize_error_summary(error_summary)
    candidates = db.select(
        "system_error_reports",
        where=(
            "source_platform = %s AND triggering_feature = %s AND error_summary = %s "
            "AND resolution IS NULL AND last_occurred_at >= %s"
        ),
        params=(source_platform, triggering_feature, summary, occurred_at - _DEDUP_WINDOW),
    )
    candidates.sort(key=lambda row: row.get("last_occurred_at") or row.get("occurred_at"), reverse=True)
    existing = candidates[0] if candidates else None
    if existing is not None:
        last_occurred_at = existing.get("last_occurred_at") or existing.get("occurred_at")
        if isinstance(last_occurred_at, str):
            last_occurred_at = datetime.fromisoformat(last_occurred_at.replace("Z", "+00:00"))
        if last_occurred_at.tzinfo is None:
            last_occurred_at = last_occurred_at.replace(tzinfo=timezone.utc)
        if occurred_at - last_occurred_at <= _DEDUP_WINDOW:
            db.update(
                "system_error_reports",
                {
                    "occurrence_count": int(existing.get("occurrence_count", 1)) + 1,
                    "last_occurred_at": occurred_at,
                    "drive_log_url": drive_log_url or existing.get("drive_log_url"),
                },
                where="id = %s",
                params=(existing["id"],),
            )
            _record_affected_user(db, existing["id"], affected_user_id)
            return IncidentRecord(existing["id"], False)

    report_id = db.insert("system_error_reports", {
        "occurred_at": occurred_at,
        "severity": severity,
        "triggering_feature": triggering_feature,
        "error_summary": summary,
        "drive_log_url": drive_log_url,
        "resolution": None,
        "owner_notification_method": None,
        "owner_notification_status": "pending",
        "owner_notified_at": None,
        "recovery_status": "pending",
        "recovery_sent_at": None,
        "source_platform": source_platform,
        "occurrence_count": 1,
        "last_occurred_at": occurred_at,
        "resolved_by_user_id": None,
        "resolved_at": None,
    })
    _record_affected_user(db, report_id, affected_user_id)
    return IncidentRecord(report_id, True)


def _record_affected_user(db: CloudSQLClient, report_id: int, user_id: int | None) -> None:
    if user_id is None:
        return
    exists = any(
        row.get("system_error_report_id") == report_id and row.get("user_id") == user_id
        for row in db.select("system_error_affected_users")
    )
    if not exists:
        db.insert("system_error_affected_users", {
            "system_error_report_id": report_id,
            "user_id": user_id,
        })


def record_notification_result(
    db: CloudSQLClient,
    report_id: int,
    user_id: int,
    notification_type: str,
    delivery_status: str,
) -> int:
    """保存事故或康復通知的實際 Telegram 發送結果。"""
    return db.insert("system_error_notification_recipients", {
        "system_error_report_id": report_id,
        "user_id": user_id,
        "notification_type": notification_type,
        "delivery_status": delivery_status,
        "notified_at": datetime.now(timezone.utc) if delivery_status == "sent" else None,
    })


def update_owner_notification(db: CloudSQLClient, report_id: int, method: str | None, delivered: bool) -> None:
    """更新 Robin 錯誤通知的 Telegram／Email 送達結果。"""
    db.update("system_error_reports", {
        "owner_notification_method": method if delivered else None,
        "owner_notification_status": "sent" if delivered else "undelivered",
        "owner_notified_at": datetime.now(timezone.utc) if delivered else None,
    }, where="id = %s", params=(report_id,))


def update_resolution(db: CloudSQLClient, report_id: int, resolution: str, resolved_by_user_id: int) -> bool:
    """記錄／更新某筆系統錯誤紀錄的解法；找不到對應 ID 回傳 `False`，讓呼叫端可以回覆提示訊息
    （例如 Telegram 指令打錯 ID 時），不強行覆蓋不存在的紀錄。
    """
    existing = db.select("system_error_reports", where="id = %s", params=(report_id,), fetch_one=True)
    if existing is None:
        return False
    if existing.get("resolution") is not None:
        return False
    db.update("system_error_reports", {
        "resolution": resolution,
        "resolved_by_user_id": resolved_by_user_id,
        "resolved_at": datetime.now(timezone.utc),
    }, where="id = %s", params=(report_id,))
    return True


def list_error_reports(db: CloudSQLClient) -> list[dict]:
    """列出所有系統錯誤紀錄，依發生時間新到舊排序，供 Telegram Owner 選單使用。"""
    rows = db.select("system_error_reports")
    rows.sort(key=lambda row: row.get("last_occurred_at") or row["occurred_at"], reverse=True)
    return rows
