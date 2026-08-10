"""個人技能成長 — 每日重點技術分享（對應 docs/specs/robinson/SPEC.md FR-22、FR-23，Step 3.1）。

負責：整合 Gmail TLDR 電子報（見 `submodules/email`）＋ IThome／TechCrunch RSS 新聞（見
`submodules/newsfeed`）三個來源的內容，各自呼叫 Gemini 產出中文重點摘要，各自推播給 Robin。僅
Robin 可用，不處理任何 Telegram 對話流程，那是 `src/bot/commands.py`／`router.py` 的責任。

2026-08-07 經 Robin 回饋，拆成兩個獨立的排程階段（收集與推播分開，不是收到什麼就馬上推）：
① 收集（`collect_and_store_daily_digest()`）：固定台灣時間 23:00，讀取「當天」的 TLDR 電子報
   （寄件者 `dan@tldrnewsletter.com`）與 IThome／TechCrunch 新聞，三個來源各自獨立經 Gemini
   產出摘要，各寫入 `skill_growth_digests` 一筆（`digest_date` = 當天，`source` = 該來源）。
② 推播（`check_and_push_daily_digest()`）：固定台灣時間 08:00（隔天），讀取「昨天」（＝前一晚
   23:00 收集當下的「今天」）那幾筆收集結果，逐一推播給 Robin。使用者每天看到的都是「前一晚
   23:00 收集到的技術情報」。

2026-08-09 經 Robin 生產環境回饋修正（見 ADR-25）：原本三個來源合併寫入單一 `summary_text`
欄位，Robin 完全無法分辨當天到底是哪個來源沒抓到內容、還是收集本身出了問題。因此改成「一天最多
三筆、一筆一個來源管道」的正規化設計，新增 `source` 欄位（`tldr`／`ithome`／`techcrunch`），
`summary_text` 保留、但只存單一來源的摘要，未來新增來源只需要多寫一個 `source` 值，不需要再改
schema。

2026-08-09 同日再修正（見 ADR-27）：Robin 實測 ADR-25 版本的三行式精簡摘要後回饋「寫得太淺，學
不到東西」，要求改回深入摘要，但拆成三則各自獨立的 Telegram 訊息（不再合併成一則），每則標題
「每日技術成長摘要-{來源}」，內容針對每篇文章／電子報story各自列點寫至少 5 句話的重點摘要，最後
加一段「總結」；當天完全沒有內容的來源直接不推播那則訊息（連「今日無內容」都不用講）。同一輪，
Robin 提供了 IThome 實際 RSS 原始內容，讓 Claude 發現一個既有 bug：IThome 的 `<pubDate>` 其實
不是 RFC 822 標準格式，過去 `submodules/newsfeed` 的解析邏輯會直接判定失敗、導致 IThome 每天
「每一篇」文章都被跳過——這才是 IThome 每天顯示「今日無內容」的真正原因，不是真的沒新聞；已在
`submodules/newsfeed/client.py` 修正（見該模組 docstring）。另外，IThome／TechCrunch 過去只
用 RSS 的標題／連結生成摘要，等於要求 Gemini 憑空編造沒看過的文章內容；改為呼叫新增的
`newsfeed_client.fetch_article_content()` 抓取每篇文章的網頁正文全文，每篇文章之間加入 1～2 秒
隨機延遲（禮貌性延遲，比照 FR-34c 104 爬蟲的做法，避免對來源網站造成流量負擔）。

去重：`skill_growth_digests` 有 `UNIQUE (digest_date, source)` 約束，同一天同一來源只會收集一次；
`pushed_on` 記錄「這批（同一天最多三筆）是否已推播過」，避免 08:00 那個小時內 `/healthz` 多次觸發
重複推播。NFR-11「以來源日期避免重複摘要」由 `digest_date` + `source` 天然涵蓋，不需要額外的內容
雜湊表。

功能開關（見 `src/bot/toggles.py`）：`tech_intel` 是 `owner_only=True` 的功能，收集與推播前都
會檢查 Robin 本人的開關狀態，關閉時直接跳過（不收集、不推播，也不消耗 Gemini API 額度）。
2026-08-07 同日再修正：原本規劃的 `skill_growth` 開關拆成三個獨立開關（`tech_intel`／
`certificate`／`language`，見 docs/specs/feature-toggles/SPEC.md FR-3 追記），Robin 認為 TOEIC
（`certificate`）跟這裡的新聞/電子報技術情報（`tech_intel`）性質不同，不該共用同一把開關；
本模組（每日技術分享）只用其中的 `tech_intel`。

來源容錯（見 docs/specs/submodules-core/SPEC.md ADR-14 風險表）：TLDR 電子報／IThome／
TechCrunch 三個來源任一抓取失敗，只記 log、視為當天該來源沒有內容，不影響其他來源與整體收集
——單一新聞來源改版或暫時失效，不該讓 Robin 連其他兩個來源的內容都收不到。單一文章正文抓取失敗
時同樣只記 log、該篇文章在摘要 Prompt 裡註記「原文擷取失敗，僅有標題」，不影響同一來源其他文章
的抓取結果。單一來源當天沒有內容時，不呼叫 Gemini（省 API 額度、避免對空內容生成無意義文字），
`summary_text` 直接寫入固定文字「今日無內容」（`_NO_CONTENT_TEXT`）——這跟「收集當下整個服務都
不可用、連這個來源的列都沒寫入」是兩種不同情境，後者靠 `source IS NULL` 的去重標記列處理，隔天
推播時一律回覆 Robin 指定的固定訊息「未獲得最新技術分享」（`_NO_CONTENT_MESSAGE`，NFR-10 一致
性：不允許靜默跳過）；若三個來源當天都有收集到列、但全部都是「今日無內容」，同樣回覆這則固定
訊息（而不是完全不推播，避免 Robin 誤以為排程整個沒有跑）。
"""
import logging
import random
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.bot import toggles
from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_COLLECT_HOUR = 23
_PUSH_HOUR = 8
_FEATURE_KEY = "tech_intel"

_TLDR_SENDER_DOMAIN = "tldrnewsletter.com"
_ITHOME_RSS_URL = "https://www.ithome.com.tw/rss"
_TECHCRUNCH_RSS_URL = "https://techcrunch.com/feed/"

_SOURCES = ("tldr", "ithome", "techcrunch")
_SOURCE_DISPLAY_NAMES = {"tldr": "TLDR", "ithome": "IThome", "techcrunch": "TechCrunch"}
_NO_CONTENT_TEXT = "今日無內容"
_NO_CONTENT_MESSAGE = "📭 主任，未獲得最新技術分享。"

# 2026-08-09 新增（見 ADR-27）：抓取每篇文章全文之間的禮貌性延遲，避免對 IThome／TechCrunch
# 站台造成流量負擔（比照 robinson SPEC.md FR-34c 104 爬蟲的做法）。
_ARTICLE_FETCH_DELAY_MIN_SECONDS = 1
_ARTICLE_FETCH_DELAY_MAX_SECONDS = 2

_logger = logging.getLogger(__name__)


def _get_owner(db: CloudSQLClient) -> dict | None:
    """查詢 Robin（`is_owner = TRUE` 且已綁定）的使用者資料；理論上一定存在，查無資料屬於防禦性情境。"""
    return db.select(
        "users", where="is_owner = %s AND telegram_user_id IS NOT NULL", params=(True,), fetch_one=True
    )


def _get_digests_for_date(db: CloudSQLClient, digest_date: date) -> list[dict]:
    """查詢指定日期已收集的所有來源摘要（最多三筆，一筆一個來源）；查無資料代表那天還沒收集過
    （或收集當下整個服務剛好都不可用）。`source IS NULL` 的列是推播階段補寫的去重標記，不是真正
    的來源摘要，呼叫端需要自行過濾。"""
    return db.select("skill_growth_digests", where="digest_date = %s", params=(digest_date,))


def _fetch_newsletter_texts_safely(email_client, target_date: date) -> list[str]:
    """讀取 TLDR 電子報；失敗時只記 log，視為當天沒有電子報內容（見模組 docstring「來源容錯」）。"""
    try:
        return email_client.fetch_emails_from_domain_on_date(_TLDR_SENDER_DOMAIN, target_date)
    except Exception:
        _logger.exception("讀取 TLDR 電子報失敗，該來源當天視為沒有內容")
        return []


def _fetch_rss_articles_safely(newsfeed_client, feed_url: str, source_name: str, target_date: date) -> list[dict]:
    """讀取指定 RSS Feed；失敗時只記 log，視為當天沒有該來源的新聞（見模組 docstring「來源容錯」）。"""
    try:
        return newsfeed_client.fetch_articles_published_on(feed_url, target_date)
    except Exception:
        _logger.exception("讀取 %s RSS 失敗，該來源當天視為沒有內容", source_name)
        return []


def _enrich_articles_with_content(newsfeed_client, articles: list[dict]) -> list[dict]:
    """幫每篇 RSS 文章補上網頁正文全文（2026-08-09 新增，見 ADR-27）。

    單篇抓取失敗只記 log、該篇的 `content` 留 `None`（由 Prompt 組裝端註記「僅有標題」），
    不影響同一來源其他篇文章，也不中斷整批收集（見模組 docstring「來源容錯」）。文章之間加入
    1～2 秒隨機延遲，避免對來源站台造成流量負擔。
    """
    enriched: list[dict] = []
    for index, article in enumerate(articles):
        if index > 0:
            time.sleep(random.uniform(_ARTICLE_FETCH_DELAY_MIN_SECONDS, _ARTICLE_FETCH_DELAY_MAX_SECONDS))
        try:
            content = newsfeed_client.fetch_article_content(article["link"])
        except Exception:
            _logger.exception("抓取文章全文失敗，該篇僅保留標題：%s", article["link"])
            content = None
        enriched.append({**article, "content": content})
    return enriched


def _build_source_prompt(source: str, content: list) -> str:
    """組出給 Gemini 的單一來源深入摘要 Prompt（見 ADR-27）：針對每篇文章／電子報 story 各自
    列點寫至少 5 句話的重點摘要，最後加一段總結；只能根據實際提供的內容撰寫，不可編造。
    """
    label = _SOURCE_DISPLAY_NAMES[source]
    instruction = (
        f"你是 Robinson，以下是 Robin 訂閱的「{label}」今天的技術新聞／電子報內容。"
        "請用繁體中文，針對每一則報導或電子報 story 各自寫一個列點摘要，每則至少要有 5 句話，"
        "具體說明重點內容、背景與影響，不要只有一兩句空泛帶過；列點格式為「* 文章N：……」。"
        "全部列點寫完後，另外加一段「總結：」統整今天這些內容的共同重點或趨勢。"
        "只能根據下面提供的實際內容撰寫，絕對不可以編造沒有出現在原文裡的資訊；"
        "如果某篇文章只有標題、沒有提供全文內容，該則列點請直接寫"
        "「（原文擷取失敗，僅有標題：{標題}）」，不要憑空杜撰內容。\n\n"
    )

    if source == "tldr":
        body = "\n\n".join(f"--- 電子報 {index} ---\n{text}" for index, text in enumerate(content, start=1))
    else:
        parts = []
        for index, article in enumerate(content, start=1):
            if article.get("content"):
                parts.append(f"文章 {index} 標題：{article['title']}\n文章 {index} 全文：\n{article['content']}")
            else:
                parts.append(f"文章 {index} 標題：{article['title']}（無法取得全文）")
        body = "\n\n".join(parts)

    return instruction + body


def summarize_source(source: str, content: list, llm_client) -> str:
    """FR-23：把單一來源當天的原始內容，呼叫 Gemini 產出深入摘要（每篇文章至少 5 句話＋總結）。

    該來源當天沒有內容時，不呼叫 Gemini（省 API 額度、避免對空內容生成無意義文字），
    直接回傳固定文字「今日無內容」。
    """
    if not content:
        return _NO_CONTENT_TEXT

    prompt = _build_source_prompt(source, content)
    return llm_client.generate_text(prompt).strip()


def _format_source_message(source: str, summary_text: str) -> str:
    """FR-22：把單一來源的摘要組成 Robin 要求的獨立訊息格式（見 ADR-27）。"""
    label = _SOURCE_DISPLAY_NAMES[source]
    return (
        f"「每日技術成長摘要-{label}」\n\n"
        "你好，我是 Robinson。以下是我整理的最新技術情報重點以及總結：\n\n"
        f"{summary_text}"
    )


def collect_and_store_daily_digest(
    db: CloudSQLClient,
    email_client,
    newsfeed_client,
    llm_client,
    now: datetime | None = None,
) -> None:
    """FR-23：每日固定時間（台灣時間 23:00）收集當天的技術情報，三個來源各自獨立經 Gemini
    產出深入摘要，各寫入 `skill_growth_digests` 一筆（`digest_date` = 當天，`source` = 該來源）。

    只在台灣時間 23 點這個小時內執行；靠「查詢當天是否已有收集結果」（`UNIQUE (digest_date,
    source)` 亦有約束當最後一道防線）避免同一天內（`/healthz` 每 10 分鐘觸發）重複收集、重複呼叫
    Gemini；`tech_intel` 功能開關關閉時跳過，不消耗任何外部 API 額度。
    """
    now = now or datetime.now(timezone.utc)
    now_local = now.astimezone(_TAIWAN_TZ)
    if now_local.hour != _COLLECT_HOUR:
        return

    owner = _get_owner(db)
    if owner is None:
        return

    if not toggles.is_feature_enabled(db, owner["id"], _FEATURE_KEY):
        return

    today = now_local.date()
    if _get_digests_for_date(db, today):
        return

    newsletter_texts = _fetch_newsletter_texts_safely(email_client, today)
    ithome_articles = _fetch_rss_articles_safely(newsfeed_client, _ITHOME_RSS_URL, "IThome", today)
    techcrunch_articles = _fetch_rss_articles_safely(newsfeed_client, _TECHCRUNCH_RSS_URL, "TechCrunch", today)

    source_content = {
        "tldr": newsletter_texts,
        "ithome": _enrich_articles_with_content(newsfeed_client, ithome_articles),
        "techcrunch": _enrich_articles_with_content(newsfeed_client, techcrunch_articles),
    }

    for source in _SOURCES:
        summary_text = summarize_source(source, source_content[source], llm_client)
        db.insert("skill_growth_digests", {"digest_date": today, "source": source, "summary_text": summary_text})


def check_and_push_daily_digest(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """FR-22：每日固定時間（台灣時間 08:00）推播前一晚收集到的技術成長摘要給 Robin。

    只在台灣時間 08 點這個小時內執行；讀取「昨天」（＝前一晚 23:00 收集當下的「今天」）那幾筆
    `skill_growth_digests` 資料，**每個有實際內容的來源各自推播一則獨立訊息**（見 ADR-27），
    當天沒有內容的來源直接不推播、不特別講「今日無內容」；三個來源當天全部都沒有內容，或完全
    查無收集結果（例如收集當下服務剛好整個小時都不可用），一律回覆 Robin 指定的固定訊息
    「未獲得最新技術分享」（NFR-10：不允許靜默跳過）。靠 `pushed_on` 避免同一天內重複推播。
    """
    now = now or datetime.now(timezone.utc)
    now_local = now.astimezone(_TAIWAN_TZ)
    if now_local.hour != _PUSH_HOUR:
        return

    owner = _get_owner(db)
    if owner is None:
        return

    if not toggles.is_feature_enabled(db, owner["id"], _FEATURE_KEY):
        return

    today = now_local.date()
    yesterday = today - timedelta(days=1)
    rows = _get_digests_for_date(db, yesterday)

    if not rows:
        telegram_client.send_text(chat_id=owner["telegram_user_id"], text=_NO_CONTENT_MESSAGE)
        db.insert(
            "skill_growth_digests",
            {"digest_date": yesterday, "source": None, "summary_text": None, "pushed_on": today},
        )
        return

    real_rows = [row for row in rows if row.get("source") is not None]
    if not real_rows:
        # 這批只有去重標記列（`source IS NULL`），代表這個小時內已經推播過「未獲得」，跳過。
        return

    if real_rows[0].get("pushed_on") == today:
        return

    content_rows = [row for row in real_rows if row.get("summary_text") and row["summary_text"] != _NO_CONTENT_TEXT]

    if not content_rows:
        telegram_client.send_text(chat_id=owner["telegram_user_id"], text=_NO_CONTENT_MESSAGE)
    else:
        rows_by_source = {row["source"]: row for row in content_rows}
        for source in _SOURCES:
            row = rows_by_source.get(source)
            if row is None:
                continue
            message = _format_source_message(source, row["summary_text"])
            telegram_client.send_text(chat_id=owner["telegram_user_id"], text=message)

    db.update("skill_growth_digests", {"pushed_on": today}, where="digest_date = %s", params=(yesterday,))
