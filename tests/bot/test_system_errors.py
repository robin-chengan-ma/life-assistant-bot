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


def test_safe_display_summary_hides_secret_path_and_sql():
    hidden = system_errors.safe_display_summary("password=abc /app/src/api.py")
    assert "abc" not in hidden
    assert "/app/" not in hidden
    assert "已隱藏" in hidden
    assert system_errors.safe_display_summary("SELECT * FROM users") == "內部資料處理失敗（詳細內容已隱藏）"


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

    owner_id = fake_db.insert("users", {"is_owner": True})
    updated = system_errors.update_resolution(fake_db, report_id, "已重啟服務排除", owner_id)

    assert updated is True
    row = fake_db.select("system_error_reports", where="id = %s", params=(report_id,), fetch_one=True)
    assert row["resolution"] == "已重啟服務排除"
    assert row["resolved_by_user_id"] == owner_id
    assert row["resolved_at"] is not None


def test_update_resolution_returns_false_when_not_found(fake_db):
    assert system_errors.update_resolution(fake_db, 999, "解法", 1) is False


def test_record_or_merge_error_report_deduplicates_within_ten_minutes(fake_db):
    from datetime import datetime, timedelta, timezone

    user_id = fake_db.insert("users", {"telegram_user_id": 2, "is_owner": False})
    now = datetime(2026, 8, 18, 4, 0, tzinfo=timezone.utc)
    first = system_errors.record_or_merge_error_report(
        fake_db, severity="general", triggering_feature="mobile_dashboard", error_summary="boom",
        drive_log_url=None, source_platform="mobile", affected_user_id=user_id, now=now,
    )
    second = system_errors.record_or_merge_error_report(
        fake_db, severity="general", triggering_feature="mobile_dashboard", error_summary="boom",
        drive_log_url=None, source_platform="mobile", affected_user_id=user_id, now=now + timedelta(minutes=9),
    )

    assert first.is_new is True
    assert second == system_errors.IncidentRecord(first.report_id, False)
    row = fake_db.select("system_error_reports", fetch_one=True)
    assert row["occurrence_count"] == 2
    assert len(fake_db.select("system_error_affected_users")) == 1


def test_record_or_merge_error_report_creates_new_after_resolution(fake_db):
    from datetime import datetime, timedelta, timezone

    owner_id = fake_db.insert("users", {"is_owner": True})
    now = datetime(2026, 8, 18, 4, 0, tzinfo=timezone.utc)
    first = system_errors.record_or_merge_error_report(
        fake_db, severity="general", triggering_feature="mobile_dashboard", error_summary="boom",
        drive_log_url=None, source_platform="mobile", now=now,
    )
    assert system_errors.update_resolution(fake_db, first.report_id, "已修復", owner_id)
    second = system_errors.record_or_merge_error_report(
        fake_db, severity="general", triggering_feature="mobile_dashboard", error_summary="boom",
        drive_log_url=None, source_platform="mobile", now=now + timedelta(minutes=1),
    )

    assert second.is_new is True
    assert second.report_id != first.report_id


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


def test_update_owner_notification_records_email_delivery(fake_db):
    report_id = system_errors.record_error_report(
        fake_db, severity="general", triggering_feature="text", error_summary="boom", drive_log_url=None,
    )

    system_errors.update_owner_notification(fake_db, report_id, "email", True)

    row = fake_db.select("system_error_reports", where="id = %s", params=(report_id,), fetch_one=True)
    assert row["owner_notification_method"] == "email"
    assert row["owner_notification_status"] == "sent"
    assert row["owner_notified_at"] is not None


def test_record_incident_notification_failure_has_no_notified_time(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 2, "role": "媽媽", "is_owner": False})
    report_id = system_errors.record_error_report(
        fake_db, severity="critical", triggering_feature="text", error_summary="boom", drive_log_url=None,
    )

    system_errors.record_notification_result(fake_db, report_id, user_id, "incident", "failed")

    row = fake_db.select("system_error_notification_recipients", fetch_one=True)
    assert row["delivery_status"] == "failed"
    assert row["notified_at"] is None
