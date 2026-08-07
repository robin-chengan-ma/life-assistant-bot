from unittest.mock import MagicMock

import pytest
from flask import Flask
from google.genai import errors as genai_errors

from src.bot import webhook
from submodules.llm.client import LLMQuotaGuardError

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
    # voice（語音訊息）Step 1.4 已支援，走 _extract_voice()，不落在「不支援格式」判斷內
    payload = {"message": {"from": {"id": 123}, "voice": {"file_id": "voice1"}}}
    assert webhook._extract_unsupported_file(payload) is None


def test_extract_unsupported_file_ignores_audio():
    # audio（上傳的音檔）FR-17 也支援，走 _extract_voice()，不落在「不支援格式」判斷內
    payload = {"message": {"from": {"id": 123}, "audio": {"file_id": "audio1"}}}
    assert webhook._extract_unsupported_file(payload) is None


# --- _extract_voice：純函式（涵蓋 voice／audio 兩種類型，見 robinson SPEC.md FR-17）---


def test_extract_voice_returns_none_when_no_voice_or_audio():
    assert webhook._extract_voice({"message": {"from": {"id": 123}, "text": "hi"}}) is None


def test_extract_voice_returns_file_id_duration_and_mime_type_for_voice():
    payload = {
        "message": {"from": {"id": 123}, "voice": {"file_id": "v1", "duration": 42, "mime_type": "audio/ogg"}}
    }
    assert webhook._extract_voice(payload) == (123, "v1", 42, "audio/ogg")


def test_extract_voice_returns_none_when_file_id_missing():
    payload = {"message": {"from": {"id": 123}, "voice": {"duration": 42}}}
    assert webhook._extract_voice(payload) is None


def test_extract_voice_defaults_duration_and_mime_type_when_missing():
    payload = {"message": {"from": {"id": 123}, "voice": {"file_id": "v1"}}}
    assert webhook._extract_voice(payload) == (123, "v1", None, "audio/ogg")


def test_extract_voice_handles_uploaded_audio_message():
    # message.audio：使用者上傳的音檔（非錄音鍵語音訊息），FR-17 承諾一樣要支援
    payload = {
        "message": {
            "from": {"id": 123},
            "audio": {"file_id": "a1", "duration": 180, "mime_type": "audio/mpeg"},
        }
    }
    assert webhook._extract_voice(payload) == (123, "a1", 180, "audio/mpeg")


def test_extract_voice_defaults_mime_type_for_audio_without_mime_type():
    payload = {"message": {"from": {"id": 123}, "audio": {"file_id": "a1", "duration": 180}}}
    assert webhook._extract_voice(payload) == (123, "a1", 180, "audio/ogg")


def test_extract_voice_prefers_voice_when_both_present():
    # 正常情況 Telegram 不會同時給兩者，但防呆一下：voice 優先
    payload = {
        "message": {
            "from": {"id": 123},
            "voice": {"file_id": "v1", "duration": 10},
            "audio": {"file_id": "a1", "duration": 180},
        }
    }
    assert webhook._extract_voice(payload)[1] == "v1"


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
        privacy_llm_client=None,
        telegram_client=mock_telegram_instance,
        calendar_client=None,
    )
    mock_db_instance.close.assert_called_once()
    mock_telegram_instance.send_text.assert_called_once_with(chat_id=123, text="哈囉！")


# --- 個資遮蔽 LLM 語意層專用 Key（2026-08-02，見 docs/specs/privacy-masking/SPEC.md ADR-1/ADR-2） ---

def test_build_privacy_llm_client_returns_none_when_key_not_set(monkeypatch):
    monkeypatch.delenv("GEMINI_API_PRIVACY_KEY", raising=False)

    assert webhook._build_privacy_llm_client() is None


def test_build_privacy_llm_client_builds_client_when_key_set(monkeypatch):
    monkeypatch.setenv("GEMINI_API_PRIVACY_KEY", "fake-privacy-key")
    mock_instance = MagicMock()
    mock_llm_client_cls = MagicMock(return_value=mock_instance)
    monkeypatch.setattr(webhook, "LLMClient", mock_llm_client_cls)

    result = webhook._build_privacy_llm_client()

    mock_llm_client_cls.assert_called_once_with(api_key="fake-privacy-key")
    assert result is mock_instance


def test_build_calendar_client_returns_none_when_env_vars_missing(monkeypatch):
    for key in (
        "GOOGLE_CALENDAR_OAUTH_REFRESH_TOKEN",
        "GOOGLE_CALENDAR_OAUTH_CLIENT_ID",
        "GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET",
        "GOOGLE_CALENDAR_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    assert webhook._build_calendar_client() is None


def test_build_calendar_client_builds_client_when_all_env_vars_set(monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_OAUTH_REFRESH_TOKEN", "fake-refresh-token")
    monkeypatch.setenv("GOOGLE_CALENDAR_OAUTH_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "fake-calendar-id")
    mock_instance = MagicMock()
    mock_calendar_client_cls = MagicMock(return_value=mock_instance)
    monkeypatch.setattr(webhook, "CalendarClient", mock_calendar_client_cls)

    result = webhook._build_calendar_client()

    mock_calendar_client_cls.assert_called_once_with(
        refresh_token="fake-refresh-token",
        client_id="fake-client-id",
        client_secret="fake-client-secret",
        calendar_id="fake-calendar-id",
    )
    assert result is mock_instance


def test_webhook_routes_valid_message_with_privacy_key_set(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GEMINI_API_BOT_KEY", "fake-gemini-bot-key")
    monkeypatch.setenv("GEMINI_API_TEXT_KEY", "fake-gemini-text-key")
    monkeypatch.setenv("GEMINI_API_PRIVACY_KEY", "fake-privacy-key")

    mock_handle_message = MagicMock(return_value="哈囉！")
    monkeypatch.setattr(webhook, "handle_message", mock_handle_message)

    mock_db_instance = MagicMock()
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=mock_db_instance))

    mock_privacy_llm_instance = MagicMock()

    def _fake_llm_client(api_key):
        if api_key == "fake-privacy-key":
            return mock_privacy_llm_instance
        return MagicMock()

    monkeypatch.setattr(webhook, "LLMClient", MagicMock(side_effect=_fake_llm_client))
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=MagicMock()))

    payload = {"message": {"from": {"id": 123}, "text": "/rule"}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    assert mock_handle_message.call_args.kwargs["privacy_llm_client"] is mock_privacy_llm_instance


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
        chat_id=123, text=webhook._GENERAL_COLD_REPLY
    )


def test_webhook_exception_notifies_robin_when_configured(client, monkeypatch):
    # FR-19a（Step 1.6）：ROBIN_TELEGRAM_TOKEN 有設定時，例外發生應該額外私訊 Robin 完整
    # Traceback，跟回覆給原本觸發訊息的使用者是兩個獨立的 send_text 呼叫。
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "999")
    monkeypatch.setenv("GEMINI_API_BOT_KEY", "fake-gemini-bot-key")
    monkeypatch.setenv("GEMINI_API_TEXT_KEY", "fake-gemini-text-key")

    monkeypatch.setattr(
        webhook, "handle_message", MagicMock(side_effect=RuntimeError("429 RESOURCE_EXHAUSTED"))
    )
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(webhook, "LLMClient", MagicMock())

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    payload = {"message": {"from": {"id": 123}, "text": "今天天氣如何？"}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    assert mock_telegram_instance.send_text.call_count == 2
    robin_call = next(
        call for call in mock_telegram_instance.send_text.call_args_list if call.kwargs["chat_id"] == "999"
    )
    assert "429 RESOURCE_EXHAUSTED" in robin_call.kwargs["text"]
    assert "觸發功能：text" in robin_call.kwargs["text"]
    assert "今天天氣如何？" in robin_call.kwargs["text"]
    user_call = next(
        call for call in mock_telegram_instance.send_text.call_args_list if call.kwargs["chat_id"] == 123
    )
    assert user_call.kwargs["text"] == webhook._GENERAL_COLD_REPLY


def test_summarize_user_input_returns_placeholder_for_empty():
    assert webhook._summarize_user_input(None) == "(無文字內容)"
    assert webhook._summarize_user_input("") == "(無文字內容)"


def test_summarize_user_input_truncates_long_text():
    long_text = "a" * 500
    summary = webhook._summarize_user_input(long_text, max_len=300)
    assert len(summary) < len(long_text)
    assert summary.endswith("（已截斷）")


def test_summarize_user_input_strips_and_returns_short_text():
    assert webhook._summarize_user_input("  哈囉  ") == "哈囉"


def test_notify_robin_of_error_skips_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    mock_telegram_cls = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", mock_telegram_cls)

    webhook._notify_robin_of_error("text", 123, "摘要")

    mock_telegram_cls.assert_not_called()


def test_notify_robin_of_error_swallows_send_failure(monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "999")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(side_effect=RuntimeError("Telegram 掛了")))

    webhook._notify_robin_of_error("text", 123, "摘要")  # 不應該往外拋


# --- FR-19b（Step 2.4，見 ADR-15）：錯誤 log 上傳 Google Drive + Robin 專屬連結 ---


def _set_gdrive_env(monkeypatch):
    monkeypatch.setenv("GDRIVE_OAUTH_REFRESH_TOKEN", "fake-refresh-token")
    monkeypatch.setenv("GDRIVE_OAUTH_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("GDRIVE_OAUTH_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv("GDRIVE_FOLDER_ID", "fake-folder-id")


def test_upload_error_log_returns_link_on_success(monkeypatch):
    _set_gdrive_env(monkeypatch)
    mock_gdrive_instance = MagicMock()
    mock_gdrive_instance.upload_file.return_value = "https://drive.google.com/file/d/fake123/view"
    monkeypatch.setattr(webhook, "GDriveClient", MagicMock(return_value=mock_gdrive_instance))

    link = webhook._upload_error_log("error_log_test.log", b"log content")

    assert link == "https://drive.google.com/file/d/fake123/view"
    mock_gdrive_instance.upload_file.assert_called_once_with(
        "error_log_test.log", b"log content", mime_type="text/plain"
    )


def test_upload_error_log_returns_none_when_env_vars_missing(monkeypatch):
    for key in (
        "GDRIVE_OAUTH_REFRESH_TOKEN", "GDRIVE_OAUTH_CLIENT_ID", "GDRIVE_OAUTH_CLIENT_SECRET", "GDRIVE_FOLDER_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    assert webhook._upload_error_log("error_log_test.log", b"log content") is None


def test_upload_error_log_returns_none_on_upload_exception(monkeypatch):
    _set_gdrive_env(monkeypatch)
    monkeypatch.setattr(webhook, "GDriveClient", MagicMock(side_effect=RuntimeError("Drive 暫時性錯誤")))

    assert webhook._upload_error_log("error_log_test.log", b"log content") is None


def test_notify_robin_of_error_uploads_log_and_appends_link(monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "999")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    _set_gdrive_env(monkeypatch)

    mock_gdrive_instance = MagicMock()
    mock_gdrive_instance.upload_file.return_value = "https://drive.google.com/file/d/fake123/view"
    mock_gdrive_cls = MagicMock(return_value=mock_gdrive_instance)
    monkeypatch.setattr(webhook, "GDriveClient", mock_gdrive_cls)

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    try:
        raise ValueError("模擬錯誤")
    except ValueError:
        webhook._notify_robin_of_error("finance", 123, "摘要")

    mock_gdrive_cls.assert_called_once_with(
        refresh_token="fake-refresh-token",
        client_id="fake-client-id",
        client_secret="fake-client-secret",
        folder_id="fake-folder-id",
    )
    upload_call = mock_gdrive_instance.upload_file.call_args
    filename, content = upload_call.args
    assert filename.startswith("error_log_") and filename.endswith("_finance.log")
    assert upload_call.kwargs["mime_type"] == "text/plain"
    # 上傳內容裡的 Traceback 完整、不截斷（不受 Telegram 4096 字元上限影響）
    assert b"ValueError" in content
    assert b"\xe6\xa8\xa1\xe6\x93\xac\xe9\x8c\xaf\xe8\xaa\xa4" in content  # "模擬錯誤" UTF-8

    sent_text = mock_telegram_instance.send_text.call_args.kwargs["text"]
    assert "https://drive.google.com/file/d/fake123/view" in sent_text
    assert "完整 log" in sent_text


def test_notify_robin_of_error_omits_link_when_gdrive_upload_fails(monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "999")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    _set_gdrive_env(monkeypatch)
    monkeypatch.setattr(webhook, "GDriveClient", MagicMock(side_effect=RuntimeError("Drive 掛了")))

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    webhook._notify_robin_of_error("text", 123, "摘要")  # 不應該往外拋，也不應該影響訊息送出

    mock_telegram_instance.send_text.assert_called_once()
    sent_text = mock_telegram_instance.send_text.call_args.kwargs["text"]
    assert "完整 log" not in sent_text
    assert "http" not in sent_text


def test_notify_robin_of_error_omits_link_when_gdrive_env_vars_missing(monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "999")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    for key in (
        "GDRIVE_OAUTH_REFRESH_TOKEN", "GDRIVE_OAUTH_CLIENT_ID", "GDRIVE_OAUTH_CLIENT_SECRET", "GDRIVE_FOLDER_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    webhook._notify_robin_of_error("text", 123, "摘要")

    sent_text = mock_telegram_instance.send_text.call_args.kwargs["text"]
    assert "完整 log" not in sent_text


# --- ADR-16：Telegram 送達失敗時的 email 備援通知 ---


def _set_gmail_env(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "you@gmail.com")
    monkeypatch.setenv("GMAIL_PASSWORD", "fake-app-password")


def test_send_email_fallback_sends_via_email_client(monkeypatch):
    _set_gmail_env(monkeypatch)
    mock_email_instance = MagicMock()
    mock_email_cls = MagicMock(return_value=mock_email_instance)
    monkeypatch.setattr(webhook, "EmailClient", mock_email_cls)

    webhook._send_email_fallback(subject="主旨", body="內容")

    mock_email_cls.assert_called_once_with(username="you@gmail.com", password="fake-app-password")
    mock_email_instance.send_text.assert_called_once_with(to="you@gmail.com", subject="主旨", body="內容")


def test_send_email_fallback_skips_when_env_vars_missing(monkeypatch):
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_PASSWORD", raising=False)
    mock_email_cls = MagicMock()
    monkeypatch.setattr(webhook, "EmailClient", mock_email_cls)

    webhook._send_email_fallback(subject="主旨", body="內容")

    mock_email_cls.assert_not_called()


def test_send_email_fallback_swallows_send_exception(monkeypatch):
    _set_gmail_env(monkeypatch)
    monkeypatch.setattr(webhook, "EmailClient", MagicMock(side_effect=RuntimeError("Gmail 也掛了")))

    webhook._send_email_fallback(subject="主旨", body="內容")  # 不應該往外拋


def test_notify_robin_of_error_falls_back_to_email_when_telegram_fails(monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "999")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    _set_gmail_env(monkeypatch)
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(side_effect=RuntimeError("Telegram API 掛了")))

    mock_email_instance = MagicMock()
    monkeypatch.setattr(webhook, "EmailClient", MagicMock(return_value=mock_email_instance))

    try:
        raise ValueError("模擬錯誤")
    except ValueError:
        webhook._notify_robin_of_error("finance", 123, "摘要")

    mock_email_instance.send_text.assert_called_once()
    email_call = mock_email_instance.send_text.call_args.kwargs
    assert email_call["to"] == "you@gmail.com"
    assert "finance" in email_call["subject"]
    assert "ValueError" in email_call["body"]
    assert "模擬錯誤" in email_call["body"]


def test_notify_robin_of_error_returns_early_when_content_assembly_fails(monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "999")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setattr(webhook, "_upload_error_log", MagicMock(side_effect=RuntimeError("組裝內容時掛了")))

    mock_telegram_cls = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", mock_telegram_cls)

    webhook._notify_robin_of_error("text", 123, "摘要")  # 不應該往外拋

    mock_telegram_cls.assert_not_called()


def test_notify_robin_of_error_does_not_use_email_when_telegram_succeeds(monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "999")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    _set_gmail_env(monkeypatch)
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=MagicMock()))

    mock_email_cls = MagicMock()
    monkeypatch.setattr(webhook, "EmailClient", mock_email_cls)

    webhook._notify_robin_of_error("text", 123, "摘要")

    mock_email_cls.assert_not_called()


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
        chat_id=123, text=webhook._GENERAL_COLD_REPLY
    )


# --- 空字串回覆防呆（2026-08-02，見 robinson SPEC.md FR-19，Robin 回報「完全不理我」）---


def test_webhook_sends_fallback_when_reply_is_empty_string(client, monkeypatch):
    # 沒有拋例外，但 handle_message 剛好回傳空字串時（例如 Gemini 生成回傳空內容），
    # 原本 `if reply:` 會判斷為 False 而完全不送出任何 Telegram 訊息，使用者只會看到
    # 已讀不回；改用專屬的空字串安全網文案，確保一定會收到某種回應。
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GEMINI_API_BOT_KEY", "fake-gemini-bot-key")
    monkeypatch.setenv("GEMINI_API_TEXT_KEY", "fake-gemini-text-key")

    monkeypatch.setattr(webhook, "handle_message", MagicMock(return_value=""))
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(webhook, "LLMClient", MagicMock())

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    payload = {"message": {"from": {"id": 123}, "text": "我要載妹妹到水里"}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    mock_telegram_instance.send_text.assert_called_once_with(
        chat_id=123, text=webhook._EMPTY_REPLY_FALLBACK
    )


def test_webhook_sends_fallback_when_reply_is_whitespace_only(client, monkeypatch):
    # 空字串以外，純空白（例如模型只回了換行/空格）也該視為「沒有內容」，不能只用
    # `not reply` 判斷、要一併 strip() 檢查。
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GEMINI_API_BOT_KEY", "fake-gemini-bot-key")
    monkeypatch.setenv("GEMINI_API_TEXT_KEY", "fake-gemini-text-key")

    monkeypatch.setattr(webhook, "handle_message", MagicMock(return_value="   \n  "))
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(webhook, "LLMClient", MagicMock())

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    payload = {"message": {"from": {"id": 123}, "text": "嗯"}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    mock_telegram_instance.send_text.assert_called_once_with(
        chat_id=123, text=webhook._EMPTY_REPLY_FALLBACK
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
    monkeypatch.setenv("GDRIVE_OAUTH_REFRESH_TOKEN", "fake-refresh-token")
    monkeypatch.setenv("GDRIVE_OAUTH_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("GDRIVE_OAUTH_CLIENT_SECRET", "fake-client-secret")
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
    mock_gdrive_cls.assert_called_once_with(
        refresh_token="fake-refresh-token",
        client_id="fake-client-id",
        client_secret="fake-client-secret",
        folder_id="fake-folder-id",
    )
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
        chat_id=123, text=webhook._GENERAL_COLD_REPLY
    )


def _set_voice_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GDRIVE_OAUTH_REFRESH_TOKEN", "fake-refresh-token")
    monkeypatch.setenv("GDRIVE_OAUTH_CLIENT_ID", "fake-client-id")
    monkeypatch.setenv("GDRIVE_OAUTH_CLIENT_SECRET", "fake-client-secret")
    monkeypatch.setenv("GDRIVE_FOLDER_ID", "fake-folder-id")
    monkeypatch.setenv("VOICE_API_KEY", "fake-voice-key")
    monkeypatch.setenv("GEMINI_API_BOT_KEY", "fake-gemini-bot-key")
    monkeypatch.setenv("GEMINI_API_TEXT_KEY", "fake-gemini-text-key")


def test_webhook_routes_voice_message_and_sends_reply(client, monkeypatch):
    _set_voice_env(monkeypatch)

    mock_handle_voice_message = MagicMock(return_value="好的，已經記下來了！")
    monkeypatch.setattr(webhook, "handle_voice_message", mock_handle_voice_message)

    mock_db_instance = MagicMock()
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=mock_db_instance))

    mock_gdrive_instance = MagicMock()
    mock_gdrive_cls = MagicMock(return_value=mock_gdrive_instance)
    monkeypatch.setattr(webhook, "GDriveClient", mock_gdrive_cls)

    mock_voice_instance = MagicMock()
    mock_voice_cls = MagicMock(return_value=mock_voice_instance)
    monkeypatch.setattr(webhook, "VoiceClient", mock_voice_cls)

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    mock_llm_client_cls = MagicMock()
    monkeypatch.setattr(webhook, "LLMClient", mock_llm_client_cls)

    payload = {
        "message": {"from": {"id": 123}, "voice": {"file_id": "voice1", "duration": 42, "mime_type": "audio/ogg"}}
    }
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    mock_gdrive_cls.assert_called_once_with(
        refresh_token="fake-refresh-token",
        client_id="fake-client-id",
        client_secret="fake-client-secret",
        folder_id="fake-folder-id",
    )
    mock_voice_cls.assert_called_once_with(api_key="fake-voice-key")
    assert mock_llm_client_cls.call_count == 2
    mock_llm_client_cls.assert_any_call(api_key="fake-gemini-bot-key")
    mock_llm_client_cls.assert_any_call(api_key="fake-gemini-text-key")
    mock_handle_voice_message.assert_called_once()
    call_args = mock_handle_voice_message.call_args.args
    assert call_args[0] is mock_db_instance
    assert call_args[1] is webhook._state_store
    assert call_args[2] == 123
    assert call_args[3] == "voice1"
    assert call_args[4] == 42
    assert mock_handle_voice_message.call_args.kwargs["mime_type"] == "audio/ogg"
    # 2026-08-02（FR-14 規則 1）：長期持有的 _voice_lockout_store 要正確傳入，跨呼叫共用同一份。
    assert mock_handle_voice_message.call_args.kwargs["voice_lockout_store"] is webhook._voice_lockout_store
    mock_db_instance.close.assert_called_once()
    mock_telegram_instance.send_text.assert_called_once_with(chat_id=123, text="好的，已經記下來了！")


def test_webhook_routes_uploaded_audio_message_with_correct_mime_type(client, monkeypatch):
    # message.audio（使用者上傳的音檔，例如 MP3）也要走同一條路，見 robinson SPEC.md FR-17
    _set_voice_env(monkeypatch)

    mock_handle_voice_message = MagicMock(return_value="好的，已經記下來了！")
    monkeypatch.setattr(webhook, "handle_voice_message", mock_handle_voice_message)
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(webhook, "GDriveClient", MagicMock())
    monkeypatch.setattr(webhook, "VoiceClient", MagicMock())
    monkeypatch.setattr(webhook, "LLMClient", MagicMock())
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=MagicMock()))

    payload = {
        "message": {"from": {"id": 123}, "audio": {"file_id": "audio1", "duration": 180, "mime_type": "audio/mpeg"}}
    }
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    mock_handle_voice_message.assert_called_once()
    call_args = mock_handle_voice_message.call_args
    assert call_args.args[3] == "audio1"
    assert call_args.args[4] == 180
    assert call_args.kwargs["mime_type"] == "audio/mpeg"


def test_webhook_voice_message_swallows_unexpected_exception(client, monkeypatch):
    _set_voice_env(monkeypatch)

    monkeypatch.setattr(
        webhook, "handle_voice_message", MagicMock(side_effect=RuntimeError("Groq API 掛了"))
    )
    mock_db_instance = MagicMock()
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=mock_db_instance))
    monkeypatch.setattr(webhook, "GDriveClient", MagicMock())
    monkeypatch.setattr(webhook, "VoiceClient", MagicMock())
    monkeypatch.setattr(webhook, "LLMClient", MagicMock())

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    payload = {"message": {"from": {"id": 123}, "voice": {"file_id": "voice1", "duration": 42}}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    mock_db_instance.close.assert_called_once()
    mock_telegram_instance.send_text.assert_called_once_with(
        chat_id=123, text=webhook._GENERAL_COLD_REPLY
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


# --- FR-19f／FR-19g（Step 2.6）：例外分級降級 ---


def test_is_llm_failure_true_for_quota_guard_error():
    assert webhook._is_llm_failure(LLMQuotaGuardError("節流門檻觸發")) is True


def test_is_llm_failure_true_for_genai_server_error():
    assert webhook._is_llm_failure(genai_errors.ServerError(503, {"message": "overloaded"}, None)) is True


def test_is_llm_failure_true_for_genai_client_error():
    assert webhook._is_llm_failure(genai_errors.ClientError(429, {"message": "rate limited"}, None)) is True


def test_is_llm_failure_false_for_other_exceptions():
    assert webhook._is_llm_failure(RuntimeError("DB 連線失敗")) is False
    assert webhook._is_llm_failure(ConnectionError("Telegram 連不上")) is False


def test_webhook_llm_failure_replies_major_illness_and_notifies_robin_critically(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "999")
    monkeypatch.setenv("GEMINI_API_BOT_KEY", "fake-gemini-bot-key")
    monkeypatch.setenv("GEMINI_API_TEXT_KEY", "fake-gemini-text-key")

    monkeypatch.setattr(
        webhook,
        "handle_message",
        MagicMock(side_effect=genai_errors.ServerError(503, {"message": "overloaded"}, None)),
    )
    mock_db_instance = MagicMock()
    mock_db_instance.select.return_value = []  # 沒有其他家人，只驗證觸發者本身收到的回覆
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=mock_db_instance))
    monkeypatch.setattr(webhook, "LLMClient", MagicMock())

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    payload = {"message": {"from": {"id": 123}, "text": "今天天氣如何？"}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    user_call = next(
        call for call in mock_telegram_instance.send_text.call_args_list if call.kwargs["chat_id"] == 123
    )
    assert user_call.kwargs["text"] == webhook._MAJOR_ILLNESS_REPLY
    robin_call = next(
        call for call in mock_telegram_instance.send_text.call_args_list if call.kwargs["chat_id"] == "999"
    )
    assert "最高等級告警" in robin_call.kwargs["text"]
    assert "重大疾病級" in robin_call.kwargs["text"]


def test_webhook_llm_failure_broadcasts_to_family_excluding_trigger_and_owner(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("GEMINI_API_BOT_KEY", "fake-gemini-bot-key")
    monkeypatch.setenv("GEMINI_API_TEXT_KEY", "fake-gemini-text-key")

    monkeypatch.setattr(
        webhook, "handle_message", MagicMock(side_effect=LLMQuotaGuardError("節流門檻觸發"))
    )
    mock_db_instance = MagicMock()
    # select() 的 where 條件已經排除 is_owner=TRUE，這裡回傳的都是家人；123 是這次觸發訊息的
    # 使用者本人（不該收到廣播，因為已經透過主流程拿到同一句話），456 才該收到廣播。
    mock_db_instance.select.return_value = [{"telegram_user_id": 123}, {"telegram_user_id": 456}]
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=mock_db_instance))
    monkeypatch.setattr(webhook, "LLMClient", MagicMock())

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    payload = {"message": {"from": {"id": 123}, "text": "今天天氣如何？"}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    broadcast_targets = [
        call.kwargs["chat_id"]
        for call in mock_telegram_instance.send_text.call_args_list
        if call.kwargs["text"] == webhook._MAJOR_ILLNESS_REPLY
    ]
    # 123（觸發者本人）只透過主流程收到一次，不該再被廣播命中；456 是唯一該收到廣播的家人
    assert broadcast_targets.count(456) == 1
    assert broadcast_targets.count(123) == 1  # 僅主流程那一次，不是廣播重複觸發


def test_is_llm_failure_used_for_photo_and_voice_flows_too(client, monkeypatch):
    # 分級降級不只適用文字訊息，圖片/語音流程一樣要走同一套判斷邏輯
    _set_photo_env(monkeypatch)
    monkeypatch.setattr(
        webhook,
        "handle_photo_message",
        MagicMock(side_effect=genai_errors.ServerError(500, {"message": "internal error"}, None)),
    )
    mock_db_instance = MagicMock()
    mock_db_instance.select.return_value = []
    monkeypatch.setattr(webhook, "CloudSQLClient", MagicMock(return_value=mock_db_instance))
    monkeypatch.setattr(webhook, "LLMClient", MagicMock())

    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    payload = {"message": {"from": {"id": 123}, "photo": [{"file_id": "abc"}]}}
    response = client.post("/telegram/webhook", json=payload)

    assert response.status_code == 200
    mock_telegram_instance.send_text.assert_any_call(chat_id=123, text=webhook._MAJOR_ILLNESS_REPLY)


# --- _notify_robin_of_error severity 參數（FR-19g）---


def test_notify_robin_of_error_adds_critical_banner_when_severity_critical(monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "999")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    webhook._notify_robin_of_error("text", 123, "摘要", severity="critical")

    sent_text = mock_telegram_instance.send_text.call_args.kwargs["text"]
    assert sent_text.startswith(webhook._CRITICAL_SEVERITY_BANNER)


def test_notify_robin_of_error_omits_banner_when_severity_general(monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", "999")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    mock_telegram_instance = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    webhook._notify_robin_of_error("text", 123, "摘要")  # 預設 severity="general"

    sent_text = mock_telegram_instance.send_text.call_args.kwargs["text"]
    assert webhook._CRITICAL_SEVERITY_BANNER not in sent_text


# --- _broadcast_major_illness_to_family（FR-19g）：直接單元測試 ---


def test_broadcast_major_illness_returns_early_when_db_none():
    mock_telegram_cls = MagicMock()
    webhook._broadcast_major_illness_to_family(None, exclude_telegram_user_id=123)
    mock_telegram_cls.assert_not_called()


def test_broadcast_major_illness_returns_early_when_bot_token_missing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    mock_db = MagicMock()

    webhook._broadcast_major_illness_to_family(mock_db, exclude_telegram_user_id=123)

    mock_db.select.assert_not_called()


def test_broadcast_major_illness_logs_and_returns_when_query_fails(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    mock_db = MagicMock()
    mock_db.select.side_effect = RuntimeError("DB 連線失敗")
    mock_telegram_cls = MagicMock()
    monkeypatch.setattr(webhook, "TelegramClient", mock_telegram_cls)

    webhook._broadcast_major_illness_to_family(mock_db, exclude_telegram_user_id=123)  # 不應往外拋

    mock_telegram_cls.assert_not_called()


def test_broadcast_major_illness_continues_when_one_family_member_send_fails(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    mock_db = MagicMock()
    mock_db.select.return_value = [{"telegram_user_id": 111}, {"telegram_user_id": 222}]
    mock_telegram_instance = MagicMock()
    mock_telegram_instance.send_text.side_effect = [RuntimeError("送不出去"), None]
    monkeypatch.setattr(webhook, "TelegramClient", MagicMock(return_value=mock_telegram_instance))

    webhook._broadcast_major_illness_to_family(mock_db, exclude_telegram_user_id=123)  # 不應往外拋

    assert mock_telegram_instance.send_text.call_count == 2
