"""submodules/email/client.py 的單元測試。

不呼叫真正的 SendGrid API／Gmail IMAP，寄信一律 mock `requests.post`，讀信一律 mock
`imaplib.IMAP4_SSL`（2026-08-24 起寄信改走 SendGrid API，見模組 docstring）。
"""
import base64
import email as email_lib
import imaplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import MagicMock

import pytest
import requests

from submodules.email import client as client_module
from submodules.email.client import (
    EmailClient,
    _extract_plain_text,
    _is_from_domain,
    _sent_on_date,
)
from submodules.retry import client as retry_client_module


def test_init_raises_on_empty_username():
    with pytest.raises(ValueError):
        EmailClient(username="", password="app-password")


def test_init_raises_on_empty_password():
    with pytest.raises(ValueError):
        EmailClient(username="you@gmail.com", password="")


def _make_response(status_code=202):
    response = MagicMock()
    response.status_code = status_code
    if status_code >= 400:
        error = requests.exceptions.HTTPError(f"{status_code} error")
        error.response = response
        response.raise_for_status.side_effect = error
    else:
        response.raise_for_status.return_value = None
    return response


def _patch_requests_post(monkeypatch, side_effect=None, response=None):
    mock_post = MagicMock(return_value=response or _make_response())
    if side_effect is not None:
        mock_post.side_effect = side_effect
    monkeypatch.setattr(client_module.requests, "post", mock_post)
    return mock_post


def test_send_text_raises_without_send_api_key():
    client = EmailClient(username="you@gmail.com", password="app-password")
    with pytest.raises(ValueError):
        client.send_text(to="robin@gmail.com", subject="測試主旨", body="測試內容")


def test_send_text_posts_to_sendgrid_with_bearer_token(monkeypatch):
    mock_post = _patch_requests_post(monkeypatch)

    client = EmailClient(username="you@gmail.com", password="app-password", send_api_key="sg-key")
    client.send_text(to="robin@gmail.com", subject="測試主旨", body="測試內容")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "https://api.sendgrid.com/v3/mail/send"
    assert kwargs["headers"]["Authorization"] == "Bearer sg-key"
    payload = kwargs["json"]
    assert payload["from"] == {"email": "you@gmail.com"}
    assert payload["personalizations"] == [{"to": [{"email": "robin@gmail.com"}]}]
    assert payload["subject"] == "測試主旨"
    assert payload["content"] == [{"type": "text/plain", "value": "測試內容"}]


def test_send_text_propagates_permanent_http_error(monkeypatch):
    _patch_requests_post(monkeypatch, response=_make_response(status_code=401))

    client = EmailClient(username="you@gmail.com", password="app-password", send_api_key="wrong-key")
    with pytest.raises(requests.exceptions.HTTPError):
        client.send_text(to="robin@gmail.com", subject="主旨", body="內容")


# --- 外部 API 重試機制（FR-19i，見 docs/specs/submodules-core/SPEC.md ADR-13）---


def test_send_text_retries_on_429_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    mock_post = _patch_requests_post(
        monkeypatch, side_effect=[_make_response(status_code=429), _make_response()]
    )

    client = EmailClient(username="you@gmail.com", password="app-password", send_api_key="sg-key")
    client.send_text(to="robin@gmail.com", subject="主旨", body="內容")

    assert mock_post.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_send_text_does_not_retry_authentication_error(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    mock_post = _patch_requests_post(monkeypatch, response=_make_response(status_code=401))

    client = EmailClient(username="you@gmail.com", password="app-password", send_api_key="wrong-key")
    with pytest.raises(requests.exceptions.HTTPError):
        client.send_text(to="robin@gmail.com", subject="主旨", body="內容")

    assert mock_post.call_count == 1
    mock_sleep.assert_not_called()


def test_send_text_raises_after_exhausting_retries(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    _patch_requests_post(monkeypatch, response=_make_response(status_code=503))

    client = EmailClient(username="you@gmail.com", password="app-password", send_api_key="sg-key")
    with pytest.raises(requests.exceptions.HTTPError):
        client.send_text(to="robin@gmail.com", subject="主旨", body="內容")

    assert mock_sleep.call_args_list == [((1,),), ((2,),)]


# --- send_text_with_attachment（2026-08-09，見 robinson SPEC.md FR-35b、ADR-24 後果；
#     2026-08-24 起改走 SendGrid API）---


def test_send_text_with_attachment_posts_body_and_base64_attachment(monkeypatch):
    mock_post = _patch_requests_post(monkeypatch)

    client = EmailClient(username="you@gmail.com", password="app-password", send_api_key="sg-key")
    client.send_text_with_attachment(
        to="you@gmail.com", subject="測試主旨", body="附件請參閱！",
        attachment_filename="2026-08-09-104職缺公司.csv", attachment_bytes="104公司ID,背景\n999,\n".encode(),
    )

    mock_post.assert_called_once()
    payload = mock_post.call_args.kwargs["json"]
    assert payload["from"] == {"email": "you@gmail.com"}
    assert payload["personalizations"] == [{"to": [{"email": "you@gmail.com"}]}]
    assert payload["content"] == [{"type": "text/plain", "value": "附件請參閱！"}]

    attachment = payload["attachments"][0]
    assert attachment["filename"] == "2026-08-09-104職缺公司.csv"
    assert attachment["type"] == "application/octet-stream"
    assert base64.b64decode(attachment["content"]) == "104公司ID,背景\n999,\n".encode()


def test_send_text_with_attachment_raises_without_send_api_key():
    client = EmailClient(username="you@gmail.com", password="app-password")
    with pytest.raises(ValueError):
        client.send_text_with_attachment(
            to="you@gmail.com", subject="主旨", body="內容",
            attachment_filename="test.csv", attachment_bytes=b"a,b\n1,2\n",
        )


def test_send_text_with_attachment_retries_on_429_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    mock_post = _patch_requests_post(
        monkeypatch, side_effect=[_make_response(status_code=429), _make_response()]
    )

    client = EmailClient(username="you@gmail.com", password="app-password", send_api_key="sg-key")
    client.send_text_with_attachment(
        to="you@gmail.com", subject="主旨", body="內容",
        attachment_filename="test.csv", attachment_bytes=b"a,b\n1,2\n",
    )

    assert mock_post.call_count == 2
    mock_sleep.assert_called_once_with(1)


# --- fetch_emails_from_domain_on_date（FR-23，Step 3.1）---

_TAIWAN_TZ = client_module._TAIWAN_TZ


def _make_raw_email(*, from_addr: str, dt: datetime, body: str, multipart: bool = False) -> bytes:
    if multipart:
        message = MIMEMultipart()
        message.attach(MIMEText("附件（非純文字內容，應被忽略）", "html", "utf-8"))
        message.attach(MIMEText(body, "plain", "utf-8"))
    else:
        message = MIMEText(body, "plain", "utf-8")
    message["From"] = from_addr
    message["Date"] = email_lib.utils.format_datetime(dt)
    message["Subject"] = "TLDR Newsletter"
    return message.as_bytes()


def _patch_imap_ssl(monkeypatch):
    mock_conn = MagicMock()
    mock_imap_ssl_cls = MagicMock()
    mock_imap_ssl_cls.return_value.__enter__.return_value = mock_conn
    mock_imap_ssl_cls.return_value.__exit__.return_value = False
    monkeypatch.setattr(client_module.imaplib, "IMAP4_SSL", mock_imap_ssl_cls)
    return mock_imap_ssl_cls, mock_conn


def test_fetch_emails_on_date_builds_search_with_given_date_range(monkeypatch):
    mock_imap_ssl_cls, mock_conn = _patch_imap_ssl(monkeypatch)
    mock_conn.search.return_value = ("OK", [b""])

    client = EmailClient(username="you@gmail.com", password="app-password")
    result = client.fetch_emails_from_domain_on_date("tldrnewsletter.com", client_module.date(2026, 8, 7))

    assert result == []
    mock_imap_ssl_cls.assert_called_once_with("imap.gmail.com")
    mock_conn.login.assert_called_once_with("you@gmail.com", "app-password")
    mock_conn.select.assert_called_once_with("INBOX", readonly=True)
    mock_conn.search.assert_called_once_with(
        None, '(SINCE "07-Aug-2026" BEFORE "08-Aug-2026" FROM "tldrnewsletter.com")'
    )


def test_fetch_emails_on_date_returns_plain_text_of_matching_emails(monkeypatch):
    _, mock_conn = _patch_imap_ssl(monkeypatch)
    target_day = datetime(2026, 8, 7, 22, 0, tzinfo=_TAIWAN_TZ)
    raw1 = _make_raw_email(from_addr="TLDR <dan@tldrnewsletter.com>", dt=target_day, body="內容一")
    raw2 = _make_raw_email(from_addr="TLDR AI <ai@tldrnewsletter.com>", dt=target_day, body="內容二")
    mock_conn.search.return_value = ("OK", [b"1 2"])
    mock_conn.fetch.side_effect = [("OK", [(b"1", raw1)]), ("OK", [(b"2", raw2)])]

    client = EmailClient(username="you@gmail.com", password="app-password")
    result = client.fetch_emails_from_domain_on_date("tldrnewsletter.com", client_module.date(2026, 8, 7))

    assert result == ["內容一", "內容二"]


def test_fetch_emails_on_date_filters_out_spoofed_domain(monkeypatch):
    _, mock_conn = _patch_imap_ssl(monkeypatch)
    target_day = datetime(2026, 8, 7, 22, 0, tzinfo=_TAIWAN_TZ)
    raw = _make_raw_email(from_addr="spoof@fake-tldrnewsletter.com", dt=target_day, body="偽造來源")
    mock_conn.search.return_value = ("OK", [b"1"])
    mock_conn.fetch.return_value = ("OK", [(b"1", raw)])

    client = EmailClient(username="you@gmail.com", password="app-password")
    result = client.fetch_emails_from_domain_on_date("tldrnewsletter.com", client_module.date(2026, 8, 7))

    assert result == []


def test_fetch_emails_on_date_filters_out_wrong_date(monkeypatch):
    _, mock_conn = _patch_imap_ssl(monkeypatch)
    wrong_day = datetime(2026, 8, 6, 22, 0, tzinfo=_TAIWAN_TZ)
    raw = _make_raw_email(from_addr="dan@tldrnewsletter.com", dt=wrong_day, body="不是那一天")
    mock_conn.search.return_value = ("OK", [b"1"])
    mock_conn.fetch.return_value = ("OK", [(b"1", raw)])

    client = EmailClient(username="you@gmail.com", password="app-password")
    result = client.fetch_emails_from_domain_on_date("tldrnewsletter.com", client_module.date(2026, 8, 7))

    assert result == []


def test_fetch_emails_on_date_returns_empty_when_search_not_ok(monkeypatch):
    _, mock_conn = _patch_imap_ssl(monkeypatch)
    mock_conn.search.return_value = ("NO", [None])

    client = EmailClient(username="you@gmail.com", password="app-password")
    result = client.fetch_emails_from_domain_on_date("tldrnewsletter.com", client_module.date(2026, 8, 7))

    assert result == []


def test_fetch_emails_on_date_skips_message_when_fetch_not_ok(monkeypatch):
    _, mock_conn = _patch_imap_ssl(monkeypatch)
    mock_conn.search.return_value = ("OK", [b"1"])
    mock_conn.fetch.return_value = ("NO", None)

    client = EmailClient(username="you@gmail.com", password="app-password")
    result = client.fetch_emails_from_domain_on_date("tldrnewsletter.com", client_module.date(2026, 8, 7))

    assert result == []


def test_fetch_emails_on_date_extracts_from_multipart_email(monkeypatch):
    _, mock_conn = _patch_imap_ssl(monkeypatch)
    target_day = datetime(2026, 8, 7, 22, 0, tzinfo=_TAIWAN_TZ)
    raw = _make_raw_email(from_addr="dan@tldrnewsletter.com", dt=target_day, body="多部分內容", multipart=True)
    mock_conn.search.return_value = ("OK", [b"1"])
    mock_conn.fetch.return_value = ("OK", [(b"1", raw)])

    client = EmailClient(username="you@gmail.com", password="app-password")
    result = client.fetch_emails_from_domain_on_date("tldrnewsletter.com", client_module.date(2026, 8, 7))

    assert result == ["多部分內容"]


def test_fetch_emails_on_date_retries_on_connection_error_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    _, mock_conn = _patch_imap_ssl(monkeypatch)
    mock_conn.login.side_effect = [ConnectionError("refused"), None]
    mock_conn.search.return_value = ("OK", [b""])

    client = EmailClient(username="you@gmail.com", password="app-password")
    result = client.fetch_emails_from_domain_on_date("tldrnewsletter.com", client_module.date(2026, 8, 7))

    assert result == []
    assert mock_conn.login.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_fetch_emails_on_date_does_not_retry_imap_protocol_error(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    _, mock_conn = _patch_imap_ssl(monkeypatch)
    mock_conn.login.side_effect = imaplib.IMAP4.error("login failed")

    client = EmailClient(username="you@gmail.com", password="wrong-password")
    with pytest.raises(imaplib.IMAP4.error):
        client.fetch_emails_from_domain_on_date("tldrnewsletter.com", client_module.date(2026, 8, 7))

    assert mock_conn.login.call_count == 1
    mock_sleep.assert_not_called()


def test_fetch_emails_on_date_raises_after_exhausting_retries(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    _, mock_conn = _patch_imap_ssl(monkeypatch)
    mock_conn.login.side_effect = ConnectionError("still down")

    client = EmailClient(username="you@gmail.com", password="app-password")
    with pytest.raises(ConnectionError):
        client.fetch_emails_from_domain_on_date("tldrnewsletter.com", client_module.date(2026, 8, 7))

    assert mock_conn.login.call_count == 3
    assert mock_sleep.call_args_list == [((1,),), ((2,),)]


# --- _is_from_domain ---


def test_is_from_domain_matches_exact_domain_regardless_of_display_name_and_case():
    assert _is_from_domain("TLDR <Dan@TLDRNewsletter.com>", "tldrnewsletter.com") is True


def test_is_from_domain_rejects_lookalike_subdomain_spoofing():
    assert _is_from_domain("spoof@fake-tldrnewsletter.com", "tldrnewsletter.com") is False


def test_is_from_domain_rejects_empty_header():
    assert _is_from_domain("", "tldrnewsletter.com") is False


# --- _sent_on_date ---


def test_sent_on_date_matches_taiwan_calendar_day():
    header = email_lib.utils.format_datetime(datetime(2026, 8, 6, 23, 30, tzinfo=_TAIWAN_TZ))
    assert _sent_on_date(header, target_date=client_module.date(2026, 8, 6)) is True


def test_sent_on_date_rejects_different_day():
    header = email_lib.utils.format_datetime(datetime(2026, 8, 5, 23, 30, tzinfo=_TAIWAN_TZ))
    assert _sent_on_date(header, target_date=client_module.date(2026, 8, 6)) is False


def test_sent_on_date_treats_naive_datetime_as_utc():
    naive_header = "Thu, 06 Aug 2026 20:30:00 -0000"
    assert _sent_on_date(naive_header, target_date=client_module.date(2026, 8, 7)) is True


def test_sent_on_date_returns_false_on_malformed_header():
    assert _sent_on_date("not a real date", target_date=client_module.date(2026, 8, 6)) is False


def test_sent_on_date_returns_false_on_empty_header():
    assert _sent_on_date("", target_date=client_module.date(2026, 8, 6)) is False


# --- _extract_plain_text ---


def test_extract_plain_text_returns_body_for_simple_text_message():
    message = MIMEText("純文字內容", "plain", "utf-8")
    parsed = email_lib.message_from_bytes(message.as_bytes())
    assert _extract_plain_text(parsed) == "純文字內容"


def test_extract_plain_text_prefers_text_plain_part_in_multipart():
    message = MIMEMultipart()
    message.attach(MIMEText("<p>HTML 版本</p>", "html", "utf-8"))
    message.attach(MIMEText("純文字版本", "plain", "utf-8"))
    parsed = email_lib.message_from_bytes(message.as_bytes())
    assert _extract_plain_text(parsed) == "純文字版本"


def test_extract_plain_text_returns_empty_string_when_no_text_plain_part():
    message = MIMEMultipart()
    message.attach(MIMEText("<p>只有 HTML</p>", "html", "utf-8"))
    parsed = email_lib.message_from_bytes(message.as_bytes())
    assert _extract_plain_text(parsed) == ""


def test_extract_plain_text_returns_empty_string_when_payload_missing():
    message = MIMEText("", "plain", "utf-8")
    parsed = email_lib.message_from_bytes(message.as_bytes())
    assert _extract_plain_text(parsed) == ""
