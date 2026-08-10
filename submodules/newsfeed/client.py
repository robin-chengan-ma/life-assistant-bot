"""RSS 新聞來源通用 Client：抓取 RSS Feed 中發布日期落在指定日期的文章清單，並可額外抓取單篇
文章的網頁正文全文。

用 `requests` 直接 GET RSS Feed URL、用標準函式庫 `xml.etree.ElementTree` 解析 XML，不安裝
`feedparser` 等第三方 RSS 套件——RSS 本質就是 XML，標準函式庫足以應付「取出 title/link/pubDate」
這種單純需求（比照 `submodules/telegram`／`submodules/voice`「輕量優先、能用標準函式庫就不多裝
依賴」的做法）。

用途（見 robinson SPEC.md FR-23，Step 3.1）：每日技術摘要讀取 IThome／TechCrunch 新聞。呼叫端
指定要讀哪一天（`target_date`），這個 Client 不假設「今天」或「昨天」——Robin 要求固定台灣時間
23:00 收集「當天」的新聞、隔天 08:00 才推播，日期語意由呼叫端（`src/bot/skill_growth.py`）決定。

RSS 2.0 規格的 `<pubDate>` 標準格式是 RFC 822（跟 Email `Date` header 同一套格式），優先複用標準
函式庫 `email.utils.parsedate_to_datetime` 解析，手法跟 `submodules/email` 的 `_sent_on_date()`
一致。**2026-08-09 新增（見 robinson SPEC.md ADR-27）**：Robin 提供 IThome 實際 RSS 原始內容後
發現，IThome 的 `<pubDate>` 其實不是 RFC 822 格式（例如 `"2026-08-08  10:08:51"`，純日期時間、
無時區資訊、日期與時間之間還是兩個空白），`parsedate_to_datetime` 對這種格式一律丟 `ValueError`
——這是 IThome 過去每天在每日技術分享都顯示「今日無內容」的真正原因（不是真的沒新聞，而是
**每一篇**都在解析日期這一步就被跳過）。新增第二層 fallback：RFC 822 解析失敗時，改嘗試
`"%Y-%m-%d %H:%M:%S"` 這種「無時區」格式，視為發布來源當地（台灣）時間；兩種格式都解析失敗才
真的視為無法解析、跳過該篇。

2026-08-09 新增（見 robinson SPEC.md ADR-27）：`fetch_article_content()` 抓取單篇文章網頁的正文
全文，供每日技術分享改版後「每篇文章至少 5 句話深入摘要」使用——只給標題／連結會逼 Gemini
自己編造內容沒看過的文章細節，不符合專案一貫「不可幻覺」原則。抓取策略刻意保持通用、不寫死
任何站台專屬的 CSS selector（避免站台一改版就整個掛掉）：優先找 `<article>` 標籤、取其中所有
`<p>` 文字；找不到 `<article>` 才退而求其次改抓整個 `<body>` 底下的 `<p>` 文字；抓到的內容太短
（可能是版型跟預期不同、或撞到反爬蟲擋下）一律回傳 `None`，由呼叫端（`src/bot/skill_growth.py`）
優雅降級，不強行湊內容。
"""
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from submodules.retry.client import call_with_retry

_DEFAULT_TIMEOUT_SECONDS = 10
_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_NAIVE_LOCAL_PUB_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MIN_ARTICLE_CONTENT_LENGTH = 100
# 部分站台會擋下沒有瀏覽器特徵的請求，帶入標準 Browser User-Agent 降低被擋機率
# （比照 robinson SPEC.md FR-34c 104 爬蟲的做法）。
_ARTICLE_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

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
    """解析 RSS `<pubDate>`；優先嘗試 RFC 822 標準格式，失敗則 fallback 嘗試「無時區的
    `YYYY-MM-DD HH:MM:SS` 格式」（視為台灣當地時間，見模組 docstring 2026-08-09 追記）；
    兩者都解析失敗才真的回傳 `None`（呼叫端應跳過該篇文章）。
    """
    if not pub_date_text:
        return None

    try:
        parsed_dt = parsedate_to_datetime(pub_date_text)
    except (TypeError, ValueError):
        parsed_dt = None

    if parsed_dt is not None:
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        return parsed_dt

    try:
        naive_dt = datetime.strptime(pub_date_text.strip(), _NAIVE_LOCAL_PUB_DATE_FORMAT)
    except ValueError:
        return None
    return naive_dt.replace(tzinfo=_TAIWAN_TZ)


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

    def fetch_article_content(self, url: str) -> str | None:
        """抓取單篇文章網頁的正文全文（2026-08-09 新增，見 robinson SPEC.md ADR-27）。

        刻意不寫死任何站台專屬的 CSS selector：優先找 `<article>` 標籤取其中所有 `<p>`
        文字，找不到才退而求其次改抓整個 `<body>` 底下的 `<p>` 文字；抓到的內容太短
        （`_MIN_ARTICLE_CONTENT_LENGTH`，可能是版型跟預期不同、或撞到反爬蟲擋下）一律回傳
        `None`，由呼叫端優雅降級，不強行湊內容給 LLM（避免產生看似合理實則编造的摘要）。
        """

        def _do_fetch() -> str | None:
            response = requests.get(url, timeout=_DEFAULT_TIMEOUT_SECONDS, headers=_ARTICLE_REQUEST_HEADERS)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            container = soup.find("article")
            if container is None:
                container = soup.body
            if container is None:
                return None

            paragraphs = [text for p in container.find_all("p") if (text := p.get_text(strip=True))]
            content = "\n".join(paragraphs)
            if len(content) < _MIN_ARTICLE_CONTENT_LENGTH:
                return None
            return content

        return call_with_retry(_do_fetch, is_retryable=_is_retryable_requests_error)
