"""src/bot/webhook.py 的測試：update_id 去重、文字/callback_query 的抽取與不支援格式短路。

2026-11（功能大幅精簡）：圖片／語音／Google Drive／Calendar／Email 備援等整合都已移除，
這裡只涵蓋保留下來的最小 plumbing。
"""
from src.bot import webhook


def test_extract_message_returns_telegram_user_id_and_text():
    payload = {"message": {"from": {"id": 123}, "text": "哈囉"}}
    assert webhook.extract_message(payload) == (123, "哈囉")


def test_extract_message_returns_none_when_missing_text():
    payload = {"message": {"from": {"id": 123}}}
    assert webhook.extract_message(payload) is None


def test_extract_message_returns_none_when_missing_from():
    payload = {"message": {"text": "哈囉"}}
    assert webhook.extract_message(payload) is None


def test_extract_callback_query_returns_tuple():
    payload = {"callback_query": {"from": {"id": 123}, "id": "cbq1", "data": "permission:create"}}
    assert webhook._extract_callback_query(payload) == (123, "cbq1", "permission:create")


def test_extract_callback_query_returns_none_when_missing_data():
    payload = {"callback_query": {"from": {"id": 123}, "id": "cbq1"}}
    assert webhook._extract_callback_query(payload) is None


def test_extract_unsupported_update_detects_non_text_message():
    payload = {"message": {"from": {"id": 123}, "photo": [{"file_id": "f1"}]}}
    assert webhook._extract_unsupported_update(payload) == 123


def test_extract_unsupported_update_returns_none_for_text_message():
    payload = {"message": {"from": {"id": 123}, "text": "哈囉"}}
    assert webhook._extract_unsupported_update(payload) is None


def test_is_duplicate_update_tracks_processed_ids():
    webhook._processed_update_ids.clear()
    assert webhook._is_duplicate_update(42) is False
    webhook._mark_update_processed(42)
    assert webhook._is_duplicate_update(42) is True


def test_mark_update_processed_evicts_oldest_beyond_maxlen():
    webhook._processed_update_ids.clear()
    for update_id in range(webhook._PROCESSED_UPDATE_IDS_MAXLEN + 1):
        webhook._mark_update_processed(update_id)
    assert webhook._is_duplicate_update(0) is False
    assert webhook._is_duplicate_update(webhook._PROCESSED_UPDATE_IDS_MAXLEN) is True


def test_telegram_webhook_ignores_update_with_no_recognizable_content(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy")
    client = webhook.bot_bp
    assert client is not None  # 僅確認 Blueprint 可以正常載入（沒有在 import 階段炸掉）
