from unittest.mock import MagicMock

import pytest
from flask import Flask

from src.bot import webhook


# --- extract_message：純函式，不需要 Flask context ---

def test_extract_message_returns_none_when_message_missing():
    assert webhook.extract_message({}) is None


def test_extract_message_returns_none_when_text_missing():
    # 例如貼圖/照片訊息，沒有 text 欄位，Step 1.1 範圍外，應忽略
    payload = {"message": {"from": {"id": 123}, "photo": [{"file_id": "abc"}]}}
    assert webhook.extract_message(payload) is None


def test_extract_message_returns_user_id_and_text_for_valid_message():
    payload = {"message": {"from": {"id": 123}, "text": "/rule"}}
    assert webhook.extract_message(payload) == (123, "/rule")


# --- Flask route：mock 掉 DB / Telegram / router，只驗證接線邏輯 ---

@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.register_blueprint(webhook.bot_bp)
    flask_app.testing = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def test_webhook_ignores_non_text_updates(client, monkeypatch):
    mock_handle_message = MagicMock()
    monkeypatch.setattr(webhook, "handle_message", mock_handle_message)

    response = client.post("/telegram/webhook", json={"edited_message": {}})

    assert response.status_code == 200
    mock_handle_message.assert_not_called()


def test_webhook_routes_valid_message_and_sends_reply(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    mock_handle_message = MagicMock(return_value="哈囉！")
    monkeypatch.setattr(webhook, "handle_message", mock_handle_message)

    mock_db_instance = MagicMock()
    mock_cloudsql_client_cls = MagicMock(return_value=mock_db_instance)
    monkeypatch.setattr(webhook, "CloudSQLClient", mock_cloudsql_client_cls)

    mock_telegram_instance = MagicMock()
    mock_telegram_client_cls = MagicMock(return_value=mock_telegram_instance)
    monkeypatch.setattr(webhook, "TelegramClient", mock_telegram_client_cls)

    payload = {"message": {"from": {"id": 123}, "text": "/rule"}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    mock_handle_message.assert_called_once_with(mock_db_instance, webhook._state_store, 123, "/rule")
    mock_db_instance.close.assert_called_once()
    mock_telegram_instance.send_text.assert_called_once_with(chat_id=123, text="哈囉！")
