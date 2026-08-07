"""RSS 新聞來源通用 Client：抓取 RSS Feed 中發布日期落在指定日期的文章清單。

用 `requests` 直接 GET RSS Feed URL、用標準函式庫 `xml.etree.ElementTree` 解析 XML，不安裝
`feedparser` 等第三方 RSS 套件——RSS 本質就是 XML，標準函式庫足以應付「取出 title/link/pubDate」
這種單純需求（比照 `submodules/telegram`／`submodules/voice`「輕量優先、能用標準函式庫就不多裝
依賴」的做法）。

用途（見 robinson SPEC.md FR-23，Step 3.1）：每日技術摘要讀取 IThome／TechCrunch 新聞。呼叫端
指定要讀哪一天（`target_date`），這個 Client 不假設「今天」或「昨天」——Robin 要求固定台灣時間
23:00 收集「當天」的新聞、隔天 08:00 才推播，日期語意由呼叫端（`src/bot/skill_growth.py`）決定。

RSS 2.0 規格的 `<pubDate>` 是 RFC 822 格式，跟 Email `Date` header 同一套格式，複用標準函式庫
`email.utils.parsedate_to_datetime` 解析，手法跟 `submodules/email` 的 `_sent_on_date()` 一致。
"""
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests

from submodules.retry.client import call_with_retry

_DEFAULT_TIMEOUT_SECONDS = 10
_TAIWAN_TZ = ZoneInfo("Asia/Taipei")

# 2026-08-07：外部 API 重試機制（見 docs/specs/robinson/SPEC.md FR-19i、
# docs/specs/submodules-core/SPEC.md ADR-13）。只重試「暫時性錯誤」：連線失敗、逾時、
# HTTP 429（Rate Limit）與 5xx；其餘 4xx 或 XML 解析失敗（非網路問題，重試也沒用）直接往外拋。
_RETRYABLE_HTTP_STATUS_MIN = 500
_RETRYABLE_RATE_LIMIT_STATUS = 429


def _is_retryable_requests_error(exc: Exception) -> bool:
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code is None:
            return False
        return status_code == _RETRYABLE_RATE_LIMIT_STATUS or status_code >= _RETRYABLE_HTTP_STATUS_MIN
    return False


def _parse_pub_date(pub_date_text: str | None) -> datetime | None:
    """解析 RSS `<pubDate>`（RFC 822 格式）；解析失敗回傳 `None`（呼叫端應跳過該篇文章）。"""
    if not pub_date_text:
        return None
    try:
        parsed_dt = parsedate_to_datetime(pub_date_text)
    except (TypeError, ValueError):
        return None
    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
    return parsed_dt


class NewsFeedClient:
    """封裝 RSS Feed 抓取，僅支援「取得指定 Feed 中，發布日期落在台灣時間某一天的文章清單」。"""

    def fetch_articles_published_on(self, feed_url: str, target_date: date) -> list[dict]:
        """抓取 `feed_url`，回傳發布日期（換算台灣時區）等於 `target_date` 的文章清單。

        每篇文章為 `{"title": str, "link": str}`；`<item>` 缺少 `title`／`link`／`pubDate`
        任一欄位，或 `pubDate` 解析失敗，一律跳過該篇（寧可漏抓也不要抓錯天）。
        """

        def _do_fetch() -> list[dict]:
            response = requests.get(feed_url, timeout=_DEFAULT_TIMEOUT_SECONDS)
            response.raise_for_status()
            root = ET.fromstring(response.content)

            articles: list[dict] = []
            for item in root.iter("item"):
                title_el = item.find("title")
                link_el = item.find("link")
                pub_date_el = item.find("pubDate")
                if title_el is None or link_el is None or pub_date_el is None:
                    continue

                published_at = _parse_pub_date(pub_date_el.text)
                if published_at is None:
                    continue
                if published_at.astimezone(_TAIWAN_TZ).date() != target_date:
                    continue

                articles.append({"title": (title_el.text or "").strip(), "link": (link_el.text or "").strip()})
            return articles

        return call_with_retry(_do_fetch, is_retryable=_is_retryable_requests_error)
