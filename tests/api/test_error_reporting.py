import logging

from src.api import error_reporting


def test_report_mobile_error_only_logs_and_does_not_raise(caplog):
    with caplog.at_level(logging.ERROR):
        error_reporting.report_mobile_error(object(), "mobile_login", 1)

    assert any("mobile_login" in record.getMessage() for record in caplog.records)


def test_report_mobile_error_handles_missing_user_id(caplog):
    with caplog.at_level(logging.ERROR):
        error_reporting.report_mobile_error(object(), "mobile_login", None)

    assert any("mobile_login" in record.getMessage() for record in caplog.records)
