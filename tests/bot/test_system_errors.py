"""src/bot/system_errors.py 的單元測試（對應 robinson SPEC.md FR-19j）。"""
from src.bot import system_errors


def test_sanitize_error_summary_strips_url_query_string():
    text = "requests.exceptions.HTTPError: 500 for url: https://api.example.com/v1/x?api_key=SECRET123&foo=bar"
    result = system_errors.sanitize_error_summary(text)
    assert "SECRET123" not in result
    assert "https://api.example.com/v1/x" in result


def test_sanitize_error_summary_truncates_long_text():
    text = "a" * 500
    result = system_errors.sanitize_error_summary(text, max_len=50)
    assert len(result) <= 60
    assert result.endswith("已截斷）")


def test_sanitize_error_summary_empty_text_returns_placeholder():
    assert system_errors.sanitize_error_summary("") == "(無法取得錯誤描述)"
    assert system_errors.sanitize_error_summary(None) == "(無法取得錯誤描述)"


def test_sanitize_error_summary_no_url_returns_stripped_text():
    assert system_errors.sanitize_error_summary("  ValueError: bad input  ") == "ValueError: bad input"


def test_record_error_report_inserts_sanitized_row(fake_db):
    report_id = system_errors.record_error_report(
        fake_db,
        severity="general",
        triggering_feature="text",
        error_summary="ConnectionError: https://api.example.com/x?token=SECRET",
        drive_log_url="https://drive.google.com/file/abc",
    )

    row = fake_db.select("system_error_reports", where="id = %s", params=(report_id,), fetch_one=True)
    assert row["severity"] == "general"
    assert row["triggering_feature"] == "text"
    assert "SECRET" not in row["error_summary"]
    assert row["drive_log_url"] == "https://drive.google.com/file/abc"
    assert row["resolution"] is None


def test_record_error_report_allows_missing_drive_log_url(fake_db):
    report_id = system_errors.record_error_report(
        fake_db, severity="critical", triggering_feature="voice", error_summary="boom", drive_log_url=None,
    )
    row = fake_db.select("system_error_reports", where="id = %s", params=(report_id,), fetch_one=True)
    assert row["drive_log_url"] is None


def test_update_resolution_updates_existing_report(fake_db):
    report_id = system_errors.record_error_report(
        fake_db, severity="general", triggering_feature="text", error_summary="boom", drive_log_url=None,
    )

    updated = system_errors.update_resolution(fake_db, report_id, "已重啟服務排除")

    assert updated is True
    row = fake_db.select("system_error_reports", where="id = %s", params=(report_id,), fetch_one=True)
    assert row["resolution"] == "已重啟服務排除"


def test_update_resolution_returns_false_when_not_found(fake_db):
    assert system_errors.update_resolution(fake_db, 999, "解法") is False


def test_list_error_reports_sorted_newest_first(fake_db):
    fake_db.insert(
        "system_error_reports",
        {"occurred_at": "2026-08-01T00:00:00", "severity": "general", "triggering_feature": "text",
         "error_summary": "old", "drive_log_url": None, "resolution": None},
    )
    fake_db.insert(
        "system_error_reports",
        {"occurred_at": "2026-08-09T00:00:00", "severity": "critical", "triggering_feature": "voice",
         "error_summary": "new", "drive_log_url": None, "resolution": None},
    )

    rows = system_errors.list_error_reports(fake_db)

    assert [row["error_summary"] for row in rows] == ["new", "old"]
