"""FR-19l：Mobile API 未預期 5xx 共用事故通報入口。"""

import logging

from src.bot import webhook

_logger = logging.getLogger(__name__)


def report_mobile_error(db, feature: str, affected_user_id: int | None) -> int | None:
    """只傳遞固定情境，不保存 Request payload、帳號、密碼或 Token。"""
    try:
        return webhook._notify_robin_of_error(
            feature,
            None,
            "Mobile App 請求發生未預期錯誤",
            db=db,
            source_platform="mobile",
            affected_user_id=affected_user_id,
        )
    except Exception:
        _logger.exception("Mobile App 事故通報失敗（功能=%s）", feature)
        return None
