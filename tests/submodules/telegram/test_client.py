"""submodules/telegram/client.py 的單元測試。

不呼叫真正的 Telegram API，一律 mock `requests.post`/`requests.get`。
"""
from unittest.mock import MagicMock

import pytest

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
