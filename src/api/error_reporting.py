"""FR-19l：Mobile API 未預期 5xx 共用事故通報入口。

2026-11（功能大幅精簡）：完整事故落地／Traceback 上傳機制（`system_errors.py`／
`system_error_management.py`）隨對應功能一併移除，這裡改呼叫
`src.bot.webhook._notify_owner_of_error()` 的簡化版本（只私訊 Robin 一句簡短通知）。
`db` 參數保留在函式簽章上只是為了不動到既有呼叫端，本體已不再使用。
"""
import logging

from src.bot import webhook

_logger = logging.getLogger(__name__)


def report_mobile_error(db, feature: str, affected_user_id: int | None) -> None:
    """只傳遞固定情境，不保存 Request payload、帳號、密碼或 Token。"""
    try:
        webhook._notify_owner_of_error(feature, affected_user_id)
    except Exception:
        _logger.exception("Mobile App 事故通報失敗（功能=%s）", feature)
