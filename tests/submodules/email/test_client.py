"""submodules/email/client.py 的單元測試。

不呼叫真正的 Gmail SMTP，一律 mock `smtplib.SMTP_SSL`。
"""
import email as email_lib
from email.header import decode_header
from unittest.mock import MagicMock

import pytest

from submodules.email import client as client_module
from submodules.email.client import EmailClient


def test_init_raises_on_empty_username():
    with pytest.raises(ValueError):
        EmailClient(username="", password="app-password")


def test_init_raises_on_empty_password():
    with pytest.raises(ValueError):
        EmailClient(username="you@gmail.com", password="")


def _patch_smtp_ssl(monkeypatch):
    mock_server = MagicMock()
    mock_smtp_ssl_cls = MagicMock()
    mock_smtp_ssl_cls.return_value.__enter__.return_value = mock_server
    mock_smtp_ssl_cls.return_value.__exit__.return_value = False
    monkeypatch.setattr(client_module.smtplib, "SMTP_SSL", mock_smtp_ssl_cls)
    return mock_smtp_ssl_cls, mock_server


def test_send_text_connects_to_gmail_smtp_ssl_and_logs_in(monkeypatch):
    mock_smtp_ssl_cls, mock_server = _patch_smtp_ssl(monkeypatch)

    client = EmailClient(username="you@gmail.com", password="app-password")
    client.send_text(to="robin@gmail.com", subject="測試主旨", body="測試內容")

    mock_smtp_ssl_cls.assert_called_once_with("smtp.gmail.com", 465)
    mock_server.login.assert_called_once_with("you@gmail.com", "app-password")


def test_send_text_sends_correct_envelope_and_body(monkeypatch):
    _, mock_server = _patch_smtp_ssl(monkeypatch)

    client = EmailClient(username="you@gmail.com", password="app-password")
    client.send_text(to="robin@gmail.com", subject="測試主旨", body="測試內容")

    mock_server.sendmail.assert_called_once()
    from_addr, to_addrs, raw_message = mock_server.sendmail.call_args.args
    assert from_addr == "you@gmail.com"
    assert to_addrs == ["robin@gmail.com"]

    parsed = email_lib.message_from_string(raw_message)
    decoded_subject, encoding = decode_header(parsed["Subject"])[0]
    assert decoded_subject.decode(encoding or "utf-8") == "測試主旨"
    assert parsed["From"] == "you@gmail.com"
    assert parsed["To"] == "robin@gmail.com"
    assert parsed.get_payload(decode=True).decode("utf-8") == "測試內容"


def test_send_text_propagates_smtp_exception(monkeypatch):
    mock_smtp_ssl_cls, mock_server = _patch_smtp_ssl(monkeypatch)
    mock_server.login.side_effect = RuntimeError("535 Authentication failed")

    client = EmailClient(username="you@gmail.com", password="wrong-password")
    with pytest.raises(RuntimeError):
        client.send_text(to="robin@gmail.com", subject="主旨", body="內容")
