"""submodules/retry/client.py 的單元測試。

不做真正的 sleep，monkeypatch time.sleep 記錄呼叫參數即可驗證 backoff 秒數是否正確。
"""
from unittest.mock import MagicMock

import pytest

from submodules.retry import client as client_module
from submodules.retry.client import call_with_retry


def _always_retryable(exc):
    return True


def _never_retryable(exc):
    return False


def test_returns_value_on_first_success(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(client_module.time, "sleep", mock_sleep)
    func = MagicMock(return_value="ok")

    result = call_with_retry(func, is_retryable=_always_retryable)

    assert result == "ok"
    assert func.call_count == 1
    mock_sleep.assert_not_called()


def test_retries_on_retryable_exception_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(client_module.time, "sleep", mock_sleep)
    func = MagicMock(side_effect=[ConnectionError("boom"), "ok"])

    result = call_with_retry(func, is_retryable=_always_retryable)

    assert result == "ok"
    assert func.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_uses_exponential_backoff_seconds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(client_module.time, "sleep", mock_sleep)
    func = MagicMock(side_effect=[ConnectionError("1"), ConnectionError("2"), "ok"])

    result = call_with_retry(func, is_retryable=_always_retryable)

    assert result == "ok"
    assert func.call_count == 3
    assert mock_sleep.call_args_list == [((1,),), ((2,),)]


def test_raises_original_exception_after_max_attempts_exhausted(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(client_module.time, "sleep", mock_sleep)
    boom = ConnectionError("still broken")
    func = MagicMock(side_effect=[boom, boom, boom])

    with pytest.raises(ConnectionError, match="still broken"):
        call_with_retry(func, is_retryable=_always_retryable)

    assert func.call_count == 3
    # 第 3 次失敗後不再等待，因為已經是最後一次嘗試
    assert mock_sleep.call_args_list == [((1,),), ((2,),)]


def test_does_not_retry_non_retryable_exception(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(client_module.time, "sleep", mock_sleep)
    func = MagicMock(side_effect=ValueError("permanent"))

    with pytest.raises(ValueError, match="permanent"):
        call_with_retry(func, is_retryable=_never_retryable)

    assert func.call_count == 1
    mock_sleep.assert_not_called()


def test_custom_max_attempts_and_backoff_seconds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(client_module.time, "sleep", mock_sleep)
    boom = ConnectionError("boom")
    func = MagicMock(side_effect=[boom, boom])

    with pytest.raises(ConnectionError):
        call_with_retry(
            func, is_retryable=_always_retryable, max_attempts=2, backoff_seconds=(0.5, 1)
        )

    assert func.call_count == 2
    mock_sleep.assert_called_once_with(0.5)
