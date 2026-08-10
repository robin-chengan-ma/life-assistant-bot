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


# --- _parse_pub_date：IThome 實際使用的「無時區」格式（2026-08-09 修正，見 ADR-27）---
# 根因：IThome 的 <pubDate> 其實不是 RFC 822 格式（例如 "2026-08-08  10:08:51"），過去
# parsedate_to_datetime 一律解析失敗、導致 IThome 每篇文章都被跳過，每日技術分享因此
# 每天都顯示「今日無內容」——不是真的沒新聞，是全部文章都在這一步被誤判掉。


def test_parse_pub_date_handles_ithome_naive_local_format():
    parsed = _parse_pub_date("2026-08-08  10:08:51")
    assert parsed == datetime(2026, 8, 8, 10, 8, 51, tzinfo=_TAIWAN_TZ)


def test_parse_pub_date_handles_ithome_naive_local_format_single_space():
    parsed = _parse_pub_date("2026-08-08 23:59:00")
    assert parsed == datetime(2026, 8, 8, 23, 59, 0, tzinfo=_TAIWAN_TZ)


def test_fetch_articles_published_on_recognizes_ithome_style_pub_date(monkeypatch):
    target = date(2026, 8, 8)
    rss = _make_rss_bytes(
        [
            {
                "title": "Gitea修補CVSS 9.8重大漏洞",
                "link": "https://www.ithome.com.tw/news/177977",
                "pub_date": "2026-08-08  08:08:09",
            }
        ]
    )
    monkeypatch.setattr(client_module.requests, "get", MagicMock(return_value=_fake_response(rss)))

    client = NewsFeedClient()
    result = client.fetch_articles_published_on("https://www.ithome.com.tw/rss", target)

    assert result == [{"title": "Gitea修補CVSS 9.8重大漏洞", "link": "https://www.ithome.com.tw/news/177977"}]


# --- fetch_article_content ---


def _fake_html_response(html: str, *, raise_exc: Exception | None = None):
    response = MagicMock()
    response.content = html.encode()
    if raise_exc is not None:
        response.raise_for_status = MagicMock(side_effect=raise_exc)
    else:
        response.raise_for_status = MagicMock()
    return response


def test_fetch_article_content_extracts_paragraphs_from_article_tag(monkeypatch):
    html = (
        "<html><body><nav>導覽列雜訊</nav>"
        "<article><p>第一段內容，字數需要湊到超過門檻，所以這裡多寫一些內容確保長度足夠，"
        "多補一些文字讓這段真的超過一百個字，這樣測試才會通過長度門檻的判斷邏輯喔。</p>"
        "<p>第二段內容，同樣需要有足夠的文字長度，確保測試能通過門檻判斷邏輯，"
        "同樣也補一些文字進去讓兩段合計的長度確實超過門檻設定的數值。</p></article>"
        "<footer>頁尾雜訊</footer></body></html>"
    )
    mock_get = MagicMock(return_value=_fake_html_response(html))
    monkeypatch.setattr(client_module.requests, "get", mock_get)

    client = NewsFeedClient()
    result = client.fetch_article_content("https://example.com/article/1")

    assert result is not None
    assert "第一段內容" in result
    assert "第二段內容" in result
    assert "導覽列雜訊" not in result
    assert "頁尾雜訊" not in result
    mock_get.assert_called_once_with(
        "https://example.com/article/1", timeout=10, headers=client_module._ARTICLE_REQUEST_HEADERS
    )


def test_fetch_article_content_falls_back_to_body_when_no_article_tag(monkeypatch):
    html = (
        "<html><body>"
        "<p>沒有 article 標籤時退而求其次抓整個 body 底下的段落文字，確保長度足夠超過門檻，"
        "這裡一樣補一些文字讓整體長度確實超過一百個字的門檻限制才能通過測試判斷，"
        "再多補幾句話確保萬無一失，長度絕對足夠超過設定的門檻數值，不會被誤判為抓取失敗。</p>"
        "</body></html>"
    )
    monkeypatch.setattr(client_module.requests, "get", MagicMock(return_value=_fake_html_response(html)))

    client = NewsFeedClient()
    result = client.fetch_article_content("https://example.com/article/2")

    assert result is not None
    assert "退而求其次" in result


def test_fetch_article_content_returns_none_when_content_too_short(monkeypatch):
    html = "<html><body><article><p>太短</p></article></body></html>"
    monkeypatch.setattr(client_module.requests, "get", MagicMock(return_value=_fake_html_response(html)))

    client = NewsFeedClient()
    result = client.fetch_article_content("https://example.com/article/3")

    assert result is None


def test_fetch_article_content_returns_none_when_no_article_or_body_tag(monkeypatch):
    html = "<html></html>"
    monkeypatch.setattr(client_module.requests, "get", MagicMock(return_value=_fake_html_response(html)))

    client = NewsFeedClient()
    result = client.fetch_article_content("https://example.com/article/no-body")

    assert result is None


def test_fetch_article_content_returns_none_when_no_paragraphs_found(monkeypatch):
    html = "<html><body><article></article></body></html>"
    monkeypatch.setattr(client_module.requests, "get", MagicMock(return_value=_fake_html_response(html)))

    client = NewsFeedClient()
    result = client.fetch_article_content("https://example.com/article/4")

    assert result is None


def test_fetch_article_content_retries_on_connection_error_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    html = "<html><body><article><p>" + ("重試成功後應該要能正確抓到這段內容確保長度超過門檻" * 5) + "</p></article></body></html>"
    mock_get = MagicMock(
        side_effect=[requests.exceptions.ConnectionError("refused"), _fake_html_response(html)]
    )
    monkeypatch.setattr(client_module.requests, "get", mock_get)

    client = NewsFeedClient()
    result = client.fetch_article_content("https://example.com/article/5")

    assert result is not None
    assert mock_get.call_count == 2
