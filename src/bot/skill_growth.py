"""個人技能成長 — 每日重點技術分享（對應 docs/specs/robinson/SPEC.md FR-22、FR-23，Step 3.1）。

負責：整合 Gmail TLDR 電子報（見 `submodules/email`）＋ IThome／TechCrunch RSS 新聞（見
`submodules/newsfeed`）兩個來源的內容，呼叫 Gemini 產出中文重點摘要，推播給 Robin。僅 Robin
可用，不處理任何 Telegram 對話流程，那是 `src/bot/commands.py`／`router.py` 的責任。

2026-08-07 經 Robin 回饋，拆成兩個獨立的排程階段（收集與推播分開，不是收到什麼就馬上推）：
① 收集（`collect_and_store_daily_digest()`）：固定台灣時間 23:00，讀取「當天」的 TLDR 電子報
   （寄件者 `dan@tldrnewsletter.com`）與 IThome／TechCrunch 新聞，經 Gemini 產出摘要，寫入
   `skill_growth_digests` 一筆（`digest_date` = 當天）。
② 推播（`check_and_push_daily_digest()`）：固定台灣時間 08:00（隔天），讀取「昨天」（＝前一晚
   23:00 收集當下的「今天」）那一筆收集結果推播給 Robin。使用者每天看到的都是「前一晚 23:00
   收集到的技術情報」。

去重：`skill_growth_digests.digest_date` 有 `UNIQUE` 約束，同一天只會收集一次；`pushed_on` 記錄
「這筆是否已推播過」，避免 08:00 那個小時內 `/healthz` 多次觸發重複推播。NFR-11「以來源日期避免
重複摘要」由 `digest_date` 天然涵蓋，不需要額外的內容雜湊表。

功能開關（見 `src/bot/toggles.py`）：`tech_intel` 是 `owner_only=True` 的功能，收集與推播前都
會檢查 Robin 本人的開關狀態，關閉時直接跳過（不收集、不推播，也不消耗 Gemini API 額度）。
2026-08-07 同日再修正：原本規劃的 `skill_growth` 開關拆成三個獨立開關（`tech_intel`／
`certificate`／`language`，見 docs/specs/feature-toggles/SPEC.md FR-3 追記），Robin 認為 TOEIC
（`certificate`）跟這裡的新聞/電子報技術情報（`tech_intel`）性質不同，不該共用同一把開關；
本模組（每日技術分享）只用其中的 `tech_intel`。

來源容錯（見 docs/specs/submodules-core/SPEC.md ADR-14 風險表）：TLDR 電子報／IThome／
TechCrunch 三個來源任一抓取失敗，只記 log、視為當天該來源沒有內容，不影響其他來源與整體收集
——單一新聞來源改版或暫時失效，不該讓 Robin 連其他兩個來源的內容都收不到。三個來源都沒有內容
時，不呼叫 Gemini，`summary_text` 寫入 `NULL`；隔天推播時看到 `NULL`（或當天完全沒有收集到任何
一筆，例如收集當下整個服務剛好掛掉一整個小時）一律回覆 Robin 指定的固定訊息「未獲得最新技術
分享」（NFR-10 一致性：不允許靜默跳過）。
"""
import logging
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

_NO_CONTENT_MESSAGE = "📭 主任，未獲得最新技術分享。"

_logger = logging.getLogger(__name__)


def _get_owner(db: CloudSQLClient) -> dict | None:
    """查詢 Robin（`is_owner = TRUE` 且已綁定）的使用者資料；理論上一定存在，查無資料屬於防禦性情境。"""
    return db.select(
        "users", where="is_owner = %s AND telegram_user_id IS NOT NULL", params=(True,), fetch_one=True
    )


def _get_digest(db: CloudSQLClient, digest_date: date) -> dict | None:
    """查詢指定日期的收集結果；查無資料代表那天還沒收集過（或收集當下整個服務剛好都不可用）。"""
    return db.select("skill_growth_digests", where="digest_date = %s", params=(digest_date,), fetch_one=True)


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


def _build_summary_prompt(
    newsletter_texts: list[str], ithome_articles: list[dict], techcrunch_articles: list[dict]
) -> str:
    """組出給 Gemini 的摘要 prompt（FR-23：中文重點摘要與總結分享）。"""
    intro = (
        "你是 Robinson，請把以下 Robin 訂閱到的技術情報，整理成繁體中文的重點摘要，"
        "用條列方式呈現每則情報的重點，最後給一段簡短的總結分享。若某個來源完全沒有內容，"
        "就不用特別提到那個來源，不要編造內容。"
    )
    lines = [intro, ""]

    if newsletter_texts:
        lines.append("【TLDR 電子報內容】")
        for index, text in enumerate(newsletter_texts, start=1):
            lines.append(f"--- 電子報 {index} ---")
            lines.append(text)
        lines.append("")

    if ithome_articles:
        lines.append("【IThome 新聞標題】")
        lines.extend(f"- {article['title']}（{article['link']}）" for article in ithome_articles)
        lines.append("")

    if techcrunch_articles:
        lines.append("【TechCrunch 新聞標題】")
        lines.extend(f"- {article['title']}（{article['link']}）" for article in techcrunch_articles)
        lines.append("")

    return "\n".join(lines)


def build_summary_text(
    newsletter_texts: list[str], ithome_articles: list[dict], techcrunch_articles: list[dict], llm_client
) -> str | None:
    """FR-23：整合三個來源的原始內容，呼叫 Gemini 產出中文重點摘要與總結分享。

    三個來源都沒有內容時，不呼叫 Gemini（省 API 額度、避免對空內容生成無意義文字），回傳 `None`。
    """
    if not newsletter_texts and not ithome_articles and not techcrunch_articles:
        return None

    prompt = _build_summary_prompt(newsletter_texts, ithome_articles, techcrunch_articles)
    return llm_client.generate_text(prompt)


def collect_and_store_daily_digest(
    db: CloudSQLClient,
    email_client,
    newsfeed_client,
    llm_client,
    now: datetime | None = None,
) -> None:
    """FR-23：每日固定時間（台灣時間 23:00）收集當天的技術情報並經 Gemini 產出摘要，寫入
    `skill_growth_digests`（`digest_date` = 當天）。

    只在台灣時間 23 點這個小時內執行；靠「查詢當天是否已有收集結果」（`digest_date` 亦有
    `UNIQUE` 約束當最後一道防線）避免同一天內（`/healthz` 每 10 分鐘觸發）重複收集、重複呼叫
    Gemini；`skill_growth` 功能開關關閉時跳過，不消耗任何外部 API 額度。
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
    if _get_digest(db, today) is not None:
        return

    newsletter_texts = _fetch_newsletter_texts_safely(email_client, today)
    ithome_articles = _fetch_rss_articles_safely(newsfeed_client, _ITHOME_RSS_URL, "IThome", today)
    techcrunch_articles = _fetch_rss_articles_safely(newsfeed_client, _TECHCRUNCH_RSS_URL, "TechCrunch", today)

    summary_text = build_summary_text(newsletter_texts, ithome_articles, techcrunch_articles, llm_client)

    db.insert("skill_growth_digests", {"digest_date": today, "summary_text": summary_text})


def check_and_push_daily_digest(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """FR-22：每日固定時間（台灣時間 08:00）推播前一晚收集到的技術成長摘要給 Robin。

    只在台灣時間 08 點這個小時內執行；讀取「昨天」（＝前一晚 23:00 收集當下的「今天」）那筆
    `skill_growth_digests` 資料，靠 `pushed_on` 避免同一天內重複推播。找不到那筆資料（例如收集
    當下服務剛好整個小時都不可用），或 `summary_text` 為 `NULL`（三個來源當天都沒有內容），
    一律回覆 Robin 指定的固定訊息「未獲得最新技術分享」（NFR-10：不允許靜默跳過）；找不到資料
    時額外補寫一筆去重標記，避免 08:00 這個小時內重複推播同一句「未獲得」。
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
    digest = _get_digest(db, yesterday)

    if digest is None:
        telegram_client.send_text(chat_id=owner["telegram_user_id"], text=_NO_CONTENT_MESSAGE)
        db.insert("skill_growth_digests", {"digest_date": yesterday, "summary_text": None, "pushed_on": today})
        return

    if digest.get("pushed_on") == today:
        return

    if digest.get("summary_text"):
        message = f"📬 主任，這是你的每日技術成長摘要：\n\n{digest['summary_text']}"
    else:
        message = _NO_CONTENT_MESSAGE

    telegram_client.send_text(chat_id=owner["telegram_user_id"], text=message)
    db.update("skill_growth_digests", {"pushed_on": today}, where="id = %s", params=(digest["id"],))
