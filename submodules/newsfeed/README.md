# newsfeed

RSS 新聞來源通用 Client，用 `requests` 直接 GET RSS Feed、用 Python 標準函式庫 `xml.etree.ElementTree` 解析 XML，不安裝 `feedparser` 等第三方 RSS 套件；另提供 `fetch_article_content()` 抓取單篇文章網頁正文全文（用 `beautifulsoup4` 解析 HTML，見 2026-08-09 追記）。

## 環境變數

無。Feed 網址由呼叫端傳入（見下方使用範例），不需要任何環境變數；`.env.example` 為空檔案，僅作為與其他子模組一致的骨架慣例。

## 安裝

```bash
pip install -r submodules/newsfeed/requirements.txt
```

## 使用範例

```python
from submodules.newsfeed.client import NewsFeedClient

client = NewsFeedClient()

# 抓取發布日期（換算台灣時區）落在指定日期的文章；呼叫端決定要抓哪一天
from datetime import date
articles = client.fetch_articles_published_on("https://www.ithome.com.tw/rss", date(2026, 8, 7))
# [{"title": "...", "link": "https://..."}, ...]

# 抓取單篇文章網頁正文全文（2026-08-09 新增，見 docs/ADR/discuss/skill-growth.md ADR-29——
# 原文誤標為 ADR-27，該編號實際是求職模組的決策，已修正）
content = client.fetch_article_content(articles[0]["link"])
# "文章正文全文……"；抓不到或內容太短時回傳 None，呼叫端需自行優雅降級
```

## 設計限制（務必遵守）

1. `fetch_articles_published_on()` 只回傳「標題＋連結」（`{"title": str, "link": str}`），不含全文——正文全文另外用 `fetch_article_content(link)` 針對單篇文章抓取（2026-08-09 前的舊設計是全文交給呼叫端用 Gemini 依標題/連結「產生」，但這樣 Gemini 等於在編造沒看過的文章內容，Robin 要求改為真的抓全文，見 `docs/ADR/discuss/skill-growth.md` ADR-29）。
2. `<item>` 缺少 `title`／`link`／`pubDate` 任一欄位，或 `pubDate` 解析失敗，一律跳過該篇，不拋例外中斷整批解析；`pubDate` 解析支援 RFC 822 標準格式，解析失敗會 fallback 再嘗試「無時區的 `YYYY-MM-DD HH:MM:SS` 格式」（視為台灣當地時間，例如 IThome 實際使用的格式），兩者都失敗才真的跳過。
3. Feed 網址／文章網址失效或改版導致解析不到內容屬於非暫時性狀況，不會重試，直接把例外往外拋，由呼叫端優雅降級（見 `docs/specs/SPEC.md`「例外處理與邊界條件」）。
4. `fetch_article_content()` 刻意不寫死任何站台專屬的 CSS selector（優先抓 `<article>` 底下的 `<p>`，找不到才退而求其次抓整個 `<body>`），換取「不同站台都能抓、不用逐站客製」的通用性，代價是遇到版面複雜的站台可能抓到雜訊或抓不完整；抓到的內容太短（`_MIN_ARTICLE_CONTENT_LENGTH = 100` 字）一律視為抓取失敗回傳 `None`。
5. 目前唯一呼叫端是 Step 3.1 每日技術摘要（FR-23），需要更多能力（例如支援 Atom 格式）時再依實際需求擴充。

## 對應 Spec

[docs/specs/SPEC.md](../../docs/specs/SPEC.md) FR-23、[docs/ADR/discuss/submodules-core.md](../../docs/ADR/discuss/submodules-core.md) ADR-14、[docs/ADR/discuss/skill-growth.md](../../docs/ADR/discuss/skill-growth.md) ADR-29
