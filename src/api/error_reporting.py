"""FR-19l：Mobile API 未預期 5xx 共用事故通報入口。

2026-11（功能大幅精簡）：完整事故落地／Traceback 上傳機制（`system_errors.py`／
`system_error_management.py`）與私訊 Robin 的簡化告警（`webhook._notify_owner_of_error()`）
皆已移除，確認 Robin 不需要任何主動告警，有問題一律自己上後台看 log 或等 user 回報。
這裡只單純記 log，不會透過任何管道私訊任何人。
"""
import logging

_logger = logging.getLogger(__name__)


def report_mobile_error(db, feature: str, affected_user_id: int | None) -> None:
    """只記 log，不保存 Request payload、帳號、密碼或 Token，也不私訊任何人。"""
    _logger.exception(
        "Mobile App 發生未預期例外（功能=%s，affected_user_id=%s）", feature, affected_user_id
    )
