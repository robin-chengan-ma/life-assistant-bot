"""submodules/telegram/client.py 的單元測試。

不呼叫真正的 Telegram API，一律 mock `requests.post`/`requests.get`。
"""
from unittest.mock import MagicMock

import pytest
import requests

from submodules.retry import client as retry_client_module
from submodules.telegram import client as client_module
from submodules.telegram.client import TelegramClient


def test_init_raises_on_empty_bot_token():
    with pytest.raises(ValueError):
        TelegramClient(bot_token="")


def _fake_response(json_data=None, content=b""):
    response = MagicMock()
    response.json.return_value = json_data or {}
    response.content = content
    response.raise_for_status = MagicMock()
    return response


def test_call_posts_to_correct_url_and_returns_json(monkeypatch):
    mock_post = MagicMock(return_value=_fake_response({"ok": True, "result": {}}))
    monkeypatch.setattr(client_module.requests, "post", mock_post)

    client = TelegramClient(bot_token="fake-token")
    result = client.call("sendMessage", {"chat_id": 123, "text": "hi"})

    assert result == {"ok": True, "result": {}}
    called_url = mock_post.call_args.args[0]
    assert called_url == "https://api.telegram.org/botfake-token/sendMessage"
    assert mock_post.call_args.kwargs["json"] == {"chat_id": 123, "text": "hi"}


def test_send_text_builds_correct_payload(monkeypatch):
    """2026-08-02：預設不帶 parse_mode（純文字），避免 LLM 生成文字格式不符 Telegram 舊版
    Markdown 語法時被整則拒收（400 Bad Request），見 client.py send_text() docstring。"""
    mock_post = MagicMock(return_value=_fake_response({"ok": True}))
    monkeypatch.setattr(client_module.requests, "post", mock_post)

    client = TelegramClient(bot_token="fake-token")
    client.send_text(chat_id=123, text="哈囉")

    assert mock_post.call_args.kwargs["json"] == {
        "chat_id": 123,
        "text": "哈囉",
    }


def test_send_text_includes_parse_mode_when_explicitly_given(monkeypatch):
    mock_post = MagicMock(return_value=_fake_response({"ok": True}))
    monkeypatch.setattr(client_module.requests, "post", mock_post)

    client = TelegramClient(bot_token="fake-token")
    client.send_text(chat_id=123, text="*哈囉*", parse_mode="Markdown")

    assert mock_post.call_args.kwargs["json"] == {
        "chat_id": 123,
        "text": "*哈囉*",
        "parse_mode": "Markdown",
    }


def test_send_photo_builds_correct_payload(monkeypatch):
    mock_post = MagicMock(return_value=_fake_response({"ok": True}))
    monkeypatch.setattr(client_module.requests, "post", mock_post)

    client = TelegramClient(bot_token="fake-token")
    client.send_photo(chat_id=123, photo="https://example.com/a.jpg", caption="貓咪")

    assert mock_post.call_args.kwargs["json"] == {
        "chat_id": 123,
        "photo": "https://example.com/a.jpg",
        "caption": "貓咪",
    }


def test_send_chat_action_builds_correct_payload(monkeypatch):
    mock_post = MagicMock(return_value=_fake_response({"ok": True}))
    monkeypatch.setattr(client_module.requests, "post", mock_post)

    client = TelegramClient(bot_token="fake-token")
    client.send_chat_action(chat_id=123)

    assert mock_post.call_args.kwargs["json"] == {"chat_id": 123, "action": "typing"}


def test_get_file_bytes_calls_get_file_then_downloads_content(monkeypatch):
    mock_post = MagicMock(
        return_value=_fake_response({"ok": True, "result": {"file_id": "f1", "file_path": "photos/abc.jpg"}})
    )
    mock_get = MagicMock(return_value=_fake_response(content=b"raw-image-bytes"))
    monkeypatch.setattr(client_module.requests, "post", mock_post)
    monkeypatch.setattr(client_module.requests, "get", mock_get)

    client = TelegramClient(bot_token="fake-token")
    content = client.get_file_bytes("f1")

    assert content == b"raw-image-bytes"
    # getFile 呼叫要帶正確的 file_id
    assert mock_post.call_args.kwargs["json"] == {"file_id": "f1"}
    # 下載網址要用檔案專屬網域＋getFile 回傳的 file_path，不是一般 Bot API 網址
    downloaded_url = mock_get.call_args.args[0]
    assert downloaded_url == "https://api.telegram.org/file/botfake-token/photos/abc.jpg"


# --- 外部 API 重試機制（FR-19i，見 docs/specs/submodules-core/SPEC.md ADR-13）---


def _http_error_response(status_code):
    response = MagicMock()
    response.status_code = status_code
    error = requests.exceptions.HTTPError(response=response)
    response.raise_for_status.side_effect = error
    return response


def test_call_retries_on_connection_error_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    ok_response = _fake_response({"ok": True})
    mock_post = MagicMock(
        side_effect=[requests.exceptions.ConnectionError("boom"), ok_response]
    )
    monkeypatch.setattr(client_module.requests, "post", mock_post)

    client = TelegramClient(bot_token="fake-token")
    result = client.call("sendMessage", {"chat_id": 123, "text": "hi"})

    assert result == {"ok": True}
    assert mock_post.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_call_retries_on_5xx_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    error_response = _http_error_response(503)
    ok_response = _fake_response({"ok": True})
    mock_post = MagicMock(side_effect=[error_response, ok_response])
    monkeypatch.setattr(client_module.requests, "post", mock_post)

    client = TelegramClient(bot_token="fake-token")
    result = client.call("sendMessage", {"chat_id": 123, "text": "hi"})

    assert result == {"ok": True}
    assert mock_post.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_call_does_not_retry_on_400(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    error_response = _http_error_response(400)
    mock_post = MagicMock(return_value=error_response)
    monkeypatch.setattr(client_module.requests, "post", mock_post)

    client = TelegramClient(bot_token="fake-token")
    with pytest.raises(requests.exceptions.HTTPError):
        client.call("sendMessage", {"chat_id": 123, "text": "hi"})

    assert mock_post.call_count == 1
    mock_sleep.assert_not_called()


def test_call_raises_after_exhausting_retries(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    mock_post = MagicMock(
        side_effect=[
            requests.exceptions.ConnectionError("1"),
            requests.exceptions.ConnectionError("2"),
            requests.exceptions.ConnectionError("3"),
        ]
    )
    monkeypatch.setattr(client_module.requests, "post", mock_post)

    client = TelegramClient(bot_token="fake-token")
    with pytest.raises(requests.exceptions.ConnectionError):
        client.call("sendMessage", {"chat_id": 123, "text": "hi"})

    assert mock_post.call_count == 3
    assert mock_sleep.call_args_list == [((1,),), ((2,),)]


def test_is_retryable_requests_error_treats_http_error_without_response_as_non_retryable():
    error = requests.exceptions.HTTPError()  # 沒有帶 response 物件的邊界情況
    assert client_module._is_retryable_requests_error(error) is False


def test_is_retryable_requests_error_treats_unrelated_exception_as_non_retryable():
    assert client_module._is_retryable_requests_error(ValueError("不相關的例外")) is False


def test_get_file_bytes_retries_download_on_5xx_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    mock_post = MagicMock(
        return_value=_fake_response({"ok": True, "result": {"file_id": "f1", "file_path": "voice/a.ogg"}})
    )
    error_response = _http_error_response(500)
    ok_response = _fake_response(content=b"raw-audio-bytes")
    mock_get = MagicMock(side_effect=[error_response, ok_response])
    monkeypatch.setattr(client_module.requests, "post", mock_post)
    monkeypatch.setattr(client_module.requests, "get", mock_get)

    client = TelegramClient(bot_token="fake-token")
    content = client.get_file_bytes("f1")

    assert content == b"raw-audio-bytes"
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once_with(1)
