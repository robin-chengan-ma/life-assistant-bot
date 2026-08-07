# newsfeed

RSS 新聞來源通用 Client，用 `requests` 直接 GET RSS Feed、用 Python 標準函式庫 `xml.etree.ElementTree` 解析 XML，不安裝 `feedparser` 等第三方 RSS 套件。

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
```

## 設計限制（務必遵守）

1. 只回傳「標題＋連結」（`{"title": str, "link": str}`），不解析全文內容——全文摘要交給呼叫端（`src/bot/skill_growth.py`）用 Gemini 依標題／連結產生，保持這個子模組單純。
2. `<item>` 缺少 `title`／`link`／`pubDate` 任一欄位，或 `pubDate` 解析失敗，一律跳過該篇，不拋例外中斷整批解析。
3. Feed 網址失效或改版導致解析不到文章屬於非暫時性狀況，不會重試，直接把例外往外拋，由呼叫端優雅降級（見 docs/specs/submodules-core/SPEC.md 風險表）。
4. 目前唯一呼叫端是 Step 3.1 每日技術摘要（FR-23），需要更多能力（例如支援 Atom 格式、抓取全文）時再依實際需求擴充。

## 對應 Spec

[docs/specs/submodules-core/SPEC.md](../../docs/specs/submodules-core/SPEC.md) ADR-14、[docs/specs/robinson/SPEC.md](../../docs/specs/robinson/SPEC.md) FR-23
