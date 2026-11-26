"""Mobile App 行事曆（中華民國政府行政機關辦公日曆）HTTP API。

2026-11-26（待辦改日期區間＋行事曆，見 docs/ADR/discuss/robinson.md）：待辦事項新增/編輯時改用
行事曆 UI 選取日期（區間），需要標示國定假日/補班，這裡直接呼叫既有
`src/services/taiwan_calendar.py` 的 `TaiwanCalendarService`，不重寫抓取邏輯。
"""

import calendar
import logging
from datetime import date

from flask import Blueprint, Response, g, jsonify, request

from src.api.app_auth import require_access_token
from src.api.error_reporting import report_mobile_error
from src.services.taiwan_calendar import TaiwanCalendarService
from submodules.cloudsql.client import CloudSQLClient

app_calendar_bp = Blueprint("app_calendar", __name__, url_prefix="/api/app/calendar")
_logger = logging.getLogger(__name__)


@app_calendar_bp.after_request
def add_cors_headers(response: Response) -> Response:
    origin = request.headers.get("Origin")
    if origin in {"http://localhost:8081", "http://127.0.0.1:8081"}:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    return response


@app_calendar_bp.get("")
@require_access_token
def get_calendar_month():
    year_text = request.args.get("year")
    month_text = request.args.get("month")
    if not (year_text and year_text.isdigit() and month_text and month_text.isdigit()):
        return jsonify({"message": "請提供正確的 year／month"}), 400
    year, month = int(year_text), int(month_text)
    if not 1 <= month <= 12:
        return jsonify({"message": "請提供正確的 year／month"}), 400

    db = None
    try:
        db = CloudSQLClient()
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
        days = TaiwanCalendarService(db, sync_missing=True).days(start, end)
        return jsonify({"year": year, "month": month, "days": days}), 200
    except Exception:
        _logger.exception("載入 Mobile App 行事曆失敗")
        report_mobile_error(db, "mobile_calendar_month", g.app_user.database_id)
        return jsonify({"message": "行事曆目前無法載入，請稍後再試"}), 503
    finally:
        if db is not None:
            db.close()
