"""src/bot/monitoring.py 的單元測試（對應 robinson SPEC.md FR-21，Step 1.6）。"""
from unittest.mock import MagicMock

from src.bot import monitoring


class _FakeDb:
    def __init__(self, size_bytes: int):
        self.size_bytes = size_bytes
        self.queries = []

    def execute_query(self, query, params=None):
        self.queries.append(query)
        return [{"size_bytes": self.size_bytes}]


def test_get_database_size_bytes_returns_size_from_query():
    db = _FakeDb(size_bytes=123456)

    size = monitoring.get_database_size_bytes(db)

    assert size == 123456
    assert "pg_database_size" in db.queries[0]


def test_check_and_notify_sends_warning_when_over_threshold():
    # 80% 門檻 = 0.5GB * 0.8；用超過這個值的容量觸發告警
    over_threshold_bytes = int(monitoring.NEON_FREE_TIER_BYTES * 0.9)
    db = _FakeDb(size_bytes=over_threshold_bytes)
    telegram_client = MagicMock()
    monitor = monitoring.NeonCapacityMonitor()

    monitor.check_and_notify(db, telegram_client, robin_chat_id=999)

    telegram_client.send_text.assert_called_once()
    call_kwargs = telegram_client.send_text.call_args.kwargs
    assert call_kwargs["chat_id"] == 999
    assert "90" in call_kwargs["text"] or "9" in call_kwargs["text"]


def test_check_and_notify_does_not_send_when_under_threshold():
    under_threshold_bytes = int(monitoring.NEON_FREE_TIER_BYTES * 0.5)
    db = _FakeDb(size_bytes=under_threshold_bytes)
    telegram_client = MagicMock()
    monitor = monitoring.NeonCapacityMonitor()

    monitor.check_and_notify(db, telegram_client, robin_chat_id=999)

    telegram_client.send_text.assert_not_called()


def test_check_and_notify_does_not_repeat_warning_while_still_over_threshold():
    over_threshold_bytes = int(monitoring.NEON_FREE_TIER_BYTES * 0.9)
    db = _FakeDb(size_bytes=over_threshold_bytes)
    telegram_client = MagicMock()
    monitor = monitoring.NeonCapacityMonitor()

    monitor.check_and_notify(db, telegram_client, robin_chat_id=999)
    monitor.check_and_notify(db, telegram_client, robin_chat_id=999)
    monitor.check_and_notify(db, telegram_client, robin_chat_id=999)

    telegram_client.send_text.assert_called_once()


def test_check_and_notify_resends_after_dropping_below_then_rising_again():
    telegram_client = MagicMock()
    monitor = monitoring.NeonCapacityMonitor()

    over_db = _FakeDb(size_bytes=int(monitoring.NEON_FREE_TIER_BYTES * 0.9))
    under_db = _FakeDb(size_bytes=int(monitoring.NEON_FREE_TIER_BYTES * 0.5))

    monitor.check_and_notify(over_db, telegram_client, robin_chat_id=999)
    monitor.check_and_notify(under_db, telegram_client, robin_chat_id=999)
    monitor.check_and_notify(over_db, telegram_client, robin_chat_id=999)

    assert telegram_client.send_text.call_count == 2
