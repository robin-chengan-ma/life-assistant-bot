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


# --- _extract_photo：純函式 ---


def test_extract_photo_returns_none_when_no_photo():
    assert webhook._extract_photo({"message": {"from": {"id": 123}, "text": "hi"}}) is None


def test_extract_photo_picks_highest_resolution_and_caption():
    payload = {
        "message": {
            "from": {"id": 123},
            "photo": [{"file_id": "small"}, {"file_id": "large"}],
            "caption": "這是什麼？",
        }
    }
    assert webhook._extract_photo(payload) == (123, "large", "這是什麼？")


def test_extract_photo_returns_none_when_photo_list_empty():
    payload = {"message": {"from": {"id": 123}, "photo": []}}
    assert webhook._extract_photo(payload) is None


def test_extract_photo_returns_none_when_file_id_missing():
    payload = {"message": {"from": {"id": 123}, "photo": [{}]}}
    assert webhook._extract_photo(payload) is None


def test_extract_photo_without_caption_returns_none_caption():
    payload = {"message": {"from": {"id": 123}, "photo": [{"file_id": "abc"}]}}
    assert webhook._extract_photo(payload) == (123, "abc", None)


# --- _extract_unsupported_file：純函式 ---


def test_extract_unsupported_file_returns_none_for_text_message():
    assert webhook._extract_unsupported_file({"message": {"from": {"id": 123}, "text": "hi"}}) is None


def test_extract_unsupported_file_returns_none_for_photo_message():
    payload = {"message": {"from": {"id": 123}, "photo": [{"file_id": "abc"}]}}
    assert webhook._extract_unsupported_file(payload) is None


def test_extract_unsupported_file_detects_document():
    payload = {"message": {"from": {"id": 123}, "document": {"file_id": "doc1"}}}
    assert webhook._extract_unsupported_file(payload) == 123


def test_extract_unsupported_file_detects_sticker():
    payload = {"message": {"from": {"id": 123}, "sticker": {"file_id": "sticker1"}}}
    assert webhook._extract_unsupported_file(payload) == 123


def test_extract_unsupported_file_ignores_voice():
    # voice/audio 依 FR-17 本來就該支援，只是 Step 1.4 還沒實作，沿用「忽略、不回覆」的既有行為
    payload = {"message": {"from": {"id": 123}, "voice": {"file_id": "voice1"}}}
    assert webhook._extract_unsupported_file(payload) is None


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


@pytest.fixture(autouse=True)
def _reset_processed_update_ids():
    # `_processed_update_ids` 是 module 層級的共用狀態，測試之間要清空避免互相汙染
    webhook._processed_update_ids.clear()
    yield
    webhook._processed_update_ids.clear()


def test_webhook_ignores_non_text_updates(client, monkeypatch):
    mock_handle_message = MagicMock()
    monkeypatch.setattr(webhook, "handle_message", mock_handle_message)

    response = client.post("/telegram/webhook", json={"edited_message": {}})

    assert response.status_code == 200
    mock_handle_message.assert_not_called()


def test_webhook_routes_valid_message_and_sends_reply(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GEMINI_API_BOT_KEY", "fake-gemini-bot-key")
    monkeypatch.setenv("GEMINI_API_TEXT_KEY", "fake-gemini-text-key")

    mock_handle_message = MagicMock(return_value="哈囉！")
    monkeypatch.setattr(webhook, "handle_message", mock_handle_message)

    mock_db_instance = MagicMock()
    mock_cloudsql_client_cls = MagicMock(return_value=mock_db_instance)
    monkeypatch.setattr(webhook, "CloudSQLClient", mock_cloudsql_client_cls)

    mock_bot_llm_instance = MagicMock()
    mock_text_llm_instance = MagicMock()

    def _fake_llm_client(api_key):
        return mock_bot_llm_instance if api_key == "fake-gemini-bot-key" else mock_text_llm_instance

    mock_llm_client_cls = MagicMock(side_effect=_fake_llm_client)
    monkeypatch.setattr(webhook, "LLMClient", mock_llm_client_cls)

    mock_telegram_instance = MagicMock()
    mock_telegram_client_cls = MagicMock(return_value=mock_telegram_instance)
    monkeypatch.setattr(webhook, "TelegramClient", mock_telegram_client_cls)

    payload = {"message": {"from": {"id": 123}, "text": "/rule"}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    mock_llm_client_cls.assert_any_call(api_key="fake-gemini-bot-key")
    mock_llm_client_cls.assert_any_call(api_key="fake-gemini-text-key")
    mock_handle_message.assert_called_once_with(
        mock_db_instance,
        webhook._state_store,
        123,
        "/rule",
        llm_client=mock_bot_llm_instance,
        text_llm_client=mock_text_llm_instance,
    )
    mock_db_instance.close.assert_called_once()
    mock_telegram_instance.send_text.assert_called_once_with(chat_id=123, text="哈囉！")


def test_webhook_swallows_unexpected_exception_and_still_returns_200(client, monkeypatch):
    # 暫時性安全網（Step 1.6 完整版之前）：handle_message 拋例外（例如 Gemini 429）時，
    # webhook 仍要回 200，否則 Telegram 會重送同一則訊息，形成「失敗→重試→再失敗」的額度燒錢迴圈。
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GEMINI_API_BOT_KEY", "fake-gemini-bot-key")
    monkeypatch.setenv("GEMINI_API_TEXT_KEY", "fake-gemini-text-key")

    mock_handle_message = MagicMock(side_effect=RuntimeError("429 RESOURCE_EXHAUSTED"))
    monkeypatch.setattr(webhook, "handle_message", mock_handle_message)

    mock_db_instance = MagicMock()
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=mock_db_instance))
    monkeypatch.setattr(webhook, "LLMClient", MagicMock())

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    payload = {"message": {"from": {"id": 123}, "text": "今天天氣如何？"}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    mock_db_instance.close.assert_called_once()
    mock_telegram_instance.send_text.assert_called_once_with(
        chat_id=123, text=webhook._UNEXPECTED_ERROR_REPLY
    )


# --- update_id 去重（FR-7a）---


def test_is_duplicate_update_false_before_marked_true_after():
    assert webhook._is_duplicate_update(555) is False
    webhook._mark_update_processed(555)
    assert webhook._is_duplicate_update(555) is True


def test_processed_update_ids_evicts_oldest_beyond_max_len(monkeypatch):
    # 避免真的塞 1000+ 筆拖慢測試，暫時調小上限來驗證防呆邊界
    monkeypatch.setattr(webhook, "_PROCESSED_UPDATE_IDS_MAXLEN", 2)

    webhook._mark_update_processed(1)
    webhook._mark_update_processed(2)
    webhook._mark_update_processed(3)  # 超過上限 2，應該把最舊的 1 擠出去

    assert webhook._is_duplicate_update(1) is False
    assert webhook._is_duplicate_update(2) is True
    assert webhook._is_duplicate_update(3) is True


def test_webhook_ignores_duplicate_update_id_without_reprocessing(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GEMINI_API_BOT_KEY", "fake-gemini-bot-key")
    monkeypatch.setenv("GEMINI_API_TEXT_KEY", "fake-gemini-text-key")

    mock_handle_message = MagicMock(return_value="哈囉！")
    monkeypatch.setattr(webhook, "handle_message", mock_handle_message)
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(webhook, "LLMClient", MagicMock())
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=MagicMock()))

    payload = {"update_id": 9001, "message": {"from": {"id": 123}, "text": "早安"}}

    first_response = client.post("/telegram/webhook", json=payload)
    second_response = client.post("/telegram/webhook", json=payload)  # 模擬 Telegram 重送同一則

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    mock_handle_message.assert_called_once()  # 第二次應該被短路擋下，不會重新處理


def test_webhook_processes_different_update_ids_normally(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GEMINI_API_BOT_KEY", "fake-gemini-bot-key")
    monkeypatch.setenv("GEMINI_API_TEXT_KEY", "fake-gemini-text-key")

    mock_handle_message = MagicMock(return_value="哈囉！")
    monkeypatch.setattr(webhook, "handle_message", mock_handle_message)
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(webhook, "LLMClient", MagicMock())
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=MagicMock()))

    client.post("/telegram/webhook", json={"update_id": 1, "message": {"from": {"id": 123}, "text": "早安"}})
    client.post("/telegram/webhook", json={"update_id": 2, "message": {"from": {"id": 123}, "text": "午安"}})

    assert mock_handle_message.call_count == 2


# --- 其他失敗模式的安全網 ---


def test_webhook_survives_db_construction_failure(client, monkeypatch):
    # db 連線本身就失敗（例如 Neon 暫時連不上）：不該讓 close() 被呼叫在 None 上炸掉，
    # 也一樣要吞例外回安全用語 + 200。
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GEMINI_API_BOT_KEY", "fake-gemini-bot-key")
    monkeypatch.setenv("GEMINI_API_TEXT_KEY", "fake-gemini-text-key")

    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(side_effect=RuntimeError("連不到資料庫")))
    monkeypatch.setattr(webhook, "handle_message", MagicMock())

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    payload = {"message": {"from": {"id": 123}, "text": "早安"}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    mock_telegram_instance.send_text.assert_called_once_with(
        chat_id=123, text=webhook._UNEXPECTED_ERROR_REPLY
    )


# --- 不支援的檔案格式（robinson SPEC.md FR-17）---


def test_webhook_rejects_unsupported_file_without_touching_db(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    mock_db_cls = MagicMock()
    monkeypatch.setattr(webhook, "CloudSQLClient", mock_db_cls)
    mock_handle_message = MagicMock()
    monkeypatch.setattr(webhook, "handle_message", mock_handle_message)

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    payload = {"message": {"from": {"id": 123}, "document": {"file_id": "doc1"}}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    mock_telegram_instance.send_text.assert_called_once_with(
        chat_id=123, text=webhook._UNSUPPORTED_FORMAT_REPLY
    )
    mock_db_cls.assert_not_called()
    mock_handle_message.assert_not_called()


def test_webhook_survives_unsupported_file_reply_send_failure(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(side_effect=RuntimeError("Telegram API 掛了")))

    payload = {"message": {"from": {"id": 123}, "sticker": {"file_id": "s1"}}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200


# --- 圖片訊息（robinson SPEC.md FR-17、ADR-13）---


def _set_photo_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GDRIVE_KEY_FILE_PATH", "fake-key.json")
    monkeypatch.setenv("GDRIVE_FOLDER_ID", "fake-folder-id")
    monkeypatch.setenv("GEMINI_API_IMAGE_KEY1", "fake-image-key1")
    monkeypatch.setenv("GEMINI_API_IMAGE_KEY2", "fake-image-key2")


def test_webhook_routes_photo_message_and_sends_reply(client, monkeypatch):
    _set_photo_env(monkeypatch)

    mock_handle_photo_message = MagicMock(return_value="這是一盤義大利麵")
    monkeypatch.setattr(webhook, "handle_photo_message", mock_handle_photo_message)

    mock_db_instance = MagicMock()
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=mock_db_instance))

    mock_gdrive_instance = MagicMock()
    mock_gdrive_cls = MagicMock(return_value=mock_gdrive_instance)
    monkeypatch.setattr(webhook, "GDriveClient", mock_gdrive_cls)

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    mock_llm_client_cls = MagicMock()
    monkeypatch.setattr(webhook, "LLMClient", mock_llm_client_cls)

    payload = {"message": {"from": {"id": 123}, "photo": [{"file_id": "abc"}], "caption": "這是什麼？"}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    mock_gdrive_cls.assert_called_once_with(key_file_path="fake-key.json", folder_id="fake-folder-id")
    assert mock_llm_client_cls.call_count == 2
    mock_llm_client_cls.assert_any_call(api_key="fake-image-key1")
    mock_llm_client_cls.assert_any_call(api_key="fake-image-key2")
    mock_handle_photo_message.assert_called_once()
    call_args = mock_handle_photo_message.call_args.args
    assert call_args[0] is mock_db_instance
    assert call_args[1] is webhook._state_store
    assert call_args[2] == 123
    assert call_args[3] == "abc"
    assert call_args[4] == "這是什麼？"
    mock_db_instance.close.assert_called_once()
    mock_telegram_instance.send_text.assert_called_once_with(chat_id=123, text="這是一盤義大利麵")


def test_webhook_photo_message_swallows_unexpected_exception(client, monkeypatch):
    _set_photo_env(monkeypatch)

    monkeypatch.setattr(
        webhook, "handle_photo_message", MagicMock(side_effect=RuntimeError("429 RESOURCE_EXHAUSTED"))
    )
    mock_db_instance = MagicMock()
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=mock_db_instance))
    monkeypatch.setattr(webhook, "GDriveClient", MagicMock())
    monkeypatch.setattr(webhook, "LLMClient", MagicMock())

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    payload = {"message": {"from": {"id": 123}, "photo": [{"file_id": "abc"}]}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    mock_db_instance.close.assert_called_once()
    mock_telegram_instance.send_text.assert_called_once_with(
        chat_id=123, text=webhook._UNEXPECTED_ERROR_REPLY
    )


def test_webhook_survives_telegram_send_failure(client, monkeypatch):
    # 傳送回覆本身失敗（Telegram API 出問題）是獨立的失敗模式，不該讓整個 route 500
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GEMINI_API_BOT_KEY", "fake-gemini-bot-key")
    monkeypatch.setenv("GEMINI_API_TEXT_KEY", "fake-gemini-text-key")

    monkeypatch.setattr(webhook, "handle_message", MagicMock(return_value="哈囉！"))
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(webhook, "LLMClient", MagicMock())
    monkeypatch.setattr(
        webhook, "TelegramClient", MagicMock(side_effect=RuntimeError("Telegram API 掛了"))
    )

    payload = {"message": {"from": {"id": 123}, "text": "早安"}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
