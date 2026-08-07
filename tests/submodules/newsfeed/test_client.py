"""submodules/newsfeed/client.py 的單元測試。

不呼叫真正的 RSS Feed，一律 mock `requests.get`。
"""
from datetime import date, datetime, timezone
from email.utils import format_datetime
from unittest.mock import MagicMock

import pytest
import requests

from submodules.newsfeed import client as client_module
from submodules.newsfeed.client import (
    NewsFeedClient,
    _is_retryable_requests_error,
    _parse_pub_date,
)
from submodules.retry import client as retry_client_module

_TAIWAN_TZ = client_module._TAIWAN_TZ


def _make_rss_bytes(items: list[dict]) -> bytes:
    item_xml_parts = []
    for item in items:
        fields = []
        if "title" in item:
            fields.append(f"<title>{item['title']}</title>")
        if "link" in item:
            fields.append(f"<link>{item['link']}</link>")
        if "pub_date" in item:
            fields.append(f"<pubDate>{item['pub_date']}</pubDate>")
        item_xml_parts.append(f"<item>{''.join(fields)}</item>")
    body = "".join(item_xml_parts)
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{body}</channel></rss>'.encode()


def _fake_response(content: bytes, *, raise_exc: Exception | None = None):
    response = MagicMock()
    response.content = content
    if raise_exc is not None:
        response.raise_for_status = MagicMock(side_effect=raise_exc)
    else:
        response.raise_for_status = MagicMock()
    return response


def test_fetch_articles_published_on_calls_requests_get_with_timeout(monkeypatch):
    mock_get = MagicMock(return_value=_fake_response(_make_rss_bytes([])))
    monkeypatch.setattr(client_module.requests, "get", mock_get)

    client = NewsFeedClient()
    result = client.fetch_articles_published_on("https://example.com/rss", date(2026, 8, 6))

    assert result == []
    mock_get.assert_called_once_with("https://example.com/rss", timeout=10)


def test_fetch_articles_published_on_returns_matching_articles(monkeypatch):
    target = date(2026, 8, 6)
    matching_pub_date = format_datetime(datetime(2026, 8, 6, 7, 0, tzinfo=_TAIWAN_TZ))
    other_day_pub_date = format_datetime(datetime(2026, 8, 5, 7, 0, tzinfo=_TAIWAN_TZ))
    rss = _make_rss_bytes(
        [
            {"title": "文章一", "link": "https://example.com/1", "pub_date": matching_pub_date},
            {"title": "文章二（昨天以外）", "link": "https://example.com/2", "pub_date": other_day_pub_date},
        ]
    )
    monkeypatch.setattr(client_module.requests, "get", MagicMock(return_value=_fake_response(rss)))

    client = NewsFeedClient()
    result = client.fetch_articles_published_on("https://example.com/rss", target)

    assert result == [{"title": "文章一", "link": "https://example.com/1"}]


def test_fetch_articles_published_on_skips_items_missing_required_fields(monkeypatch):
    target = date(2026, 8, 6)
    pub_date = format_datetime(datetime(2026, 8, 6, 7, 0, tzinfo=_TAIWAN_TZ))
    rss = _make_rss_bytes(
        [
            {"title": "缺連結", "pub_date": pub_date},
            {"link": "https://example.com/no-title", "pub_date": pub_date},
            {"title": "缺日期", "link": "https://example.com/no-date"},
        ]
    )
    monkeypatch.setattr(client_module.requests, "get", MagicMock(return_value=_fake_response(rss)))

    client = NewsFeedClient()
    result = client.fetch_articles_published_on("https://example.com/rss", target)

    assert result == []


def test_fetch_articles_published_on_skips_items_with_unparseable_pub_date(monkeypatch):
    target = date(2026, 8, 6)
    rss = _make_rss_bytes(
        [{"title": "壞日期", "link": "https://example.com/bad-date", "pub_date": "not a real date"}]
    )
    monkeypatch.setattr(client_module.requests, "get", MagicMock(return_value=_fake_response(rss)))

    client = NewsFeedClient()
    result = client.fetch_articles_published_on("https://example.com/rss", target)

    assert result == []


def test_fetch_articles_published_on_strips_whitespace_from_title_and_link(monkeypatch):
    target = date(2026, 8, 6)
    pub_date = format_datetime(datetime(2026, 8, 6, 7, 0, tzinfo=_TAIWAN_TZ))
    rss = _make_rss_bytes(
        [{"title": "  有空白的標題  ", "link": "  https://example.com/space  ", "pub_date": pub_date}]
    )
    monkeypatch.setattr(client_module.requests, "get", MagicMock(return_value=_fake_response(rss)))

    client = NewsFeedClient()
    result = client.fetch_articles_published_on("https://example.com/rss", target)

    assert result == [{"title": "有空白的標題", "link": "https://example.com/space"}]


# --- 外部 API 重試機制（FR-19i，見 docs/specs/submodules-core/SPEC.md ADR-13）---


def test_fetch_articles_retries_on_connection_error_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    mock_get = MagicMock(side_effect=[requests.exceptions.ConnectionError("refused"), _fake_response(_make_rss_bytes([]))])
    monkeypatch.setattr(client_module.requests, "get", mock_get)

    client = NewsFeedClient()
    result = client.fetch_articles_published_on("https://example.com/rss", date(2026, 8, 6))

    assert result == []
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_fetch_articles_retries_on_5xx_http_error_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    server_error_response = MagicMock()
    server_error_response.raise_for_status = MagicMock(
        side_effect=requests.exceptions.HTTPError(response=MagicMock(status_code=503))
    )
    mock_get = MagicMock(side_effect=[server_error_response, _fake_response(_make_rss_bytes([]))])
    monkeypatch.setattr(client_module.requests, "get", mock_get)

    client = NewsFeedClient()
    result = client.fetch_articles_published_on("https://example.com/rss", date(2026, 8, 6))

    assert result == []
    assert mock_get.call_count == 2


def test_fetch_articles_does_not_retry_on_404(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    not_found_response = MagicMock()
    not_found_response.raise_for_status = MagicMock(
        side_effect=requests.exceptions.HTTPError(response=MagicMock(status_code=404))
    )
    mock_get = MagicMock(return_value=not_found_response)
    monkeypatch.setattr(client_module.requests, "get", mock_get)

    client = NewsFeedClient()
    with pytest.raises(requests.exceptions.HTTPError):
        client.fetch_articles_published_on("https://example.com/rss", date(2026, 8, 6))

    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


def test_fetch_articles_raises_after_exhausting_retries(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    mock_get = MagicMock(side_effect=requests.exceptions.Timeout("timed out"))
    monkeypatch.setattr(client_module.requests, "get", mock_get)

    client = NewsFeedClient()
    with pytest.raises(requests.exceptions.Timeout):
        client.fetch_articles_published_on("https://example.com/rss", date(2026, 8, 6))

    assert mock_get.call_count == 3
    assert mock_sleep.call_args_list == [((1,),), ((2,),)]


# --- _is_retryable_requests_error ---


def test_is_retryable_requests_error_true_for_connection_error():
    assert _is_retryable_requests_error(requests.exceptions.ConnectionError("x")) is True


def test_is_retryable_requests_error_true_for_timeout():
    assert _is_retryable_requests_error(requests.exceptions.Timeout("x")) is True


def test_is_retryable_requests_error_true_for_429():
    exc = requests.exceptions.HTTPError(response=MagicMock(status_code=429))
    assert _is_retryable_requests_error(exc) is True


def test_is_retryable_requests_error_false_for_400():
    exc = requests.exceptions.HTTPError(response=MagicMock(status_code=400))
    assert _is_retryable_requests_error(exc) is False


def test_is_retryable_requests_error_false_when_response_is_none():
    exc = requests.exceptions.HTTPError(response=None)
    assert _is_retryable_requests_error(exc) is False


def test_is_retryable_requests_error_false_for_unrelated_exception():
    assert _is_retryable_requests_error(ValueError("x")) is False


# --- _parse_pub_date ---


def test_parse_pub_date_returns_none_for_empty_string():
    assert _parse_pub_date("") is None


def test_parse_pub_date_returns_none_for_none():
    assert _parse_pub_date(None) is None


def test_parse_pub_date_returns_none_for_malformed_string():
    assert _parse_pub_date("not a real date") is None


def test_parse_pub_date_treats_naive_datetime_as_utc():
    parsed = _parse_pub_date("Thu, 06 Aug 2026 20:30:00 -0000")
    assert parsed == datetime(2026, 8, 6, 20, 30, tzinfo=timezone.utc)


def test_parse_pub_date_preserves_explicit_timezone():
    parsed = _parse_pub_date(format_datetime(datetime(2026, 8, 6, 7, 0, tzinfo=_TAIWAN_TZ)))
    assert parsed.astimezone(_TAIWAN_TZ).date() == date(2026, 8, 6)
