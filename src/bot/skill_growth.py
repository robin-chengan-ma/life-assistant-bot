"""個人技能成長 — 每日重點技術分享（對應 docs/specs/robinson/SPEC.md FR-22、FR-23，Step 3.1）。

負責：整合 Gmail TLDR 電子報（見 `submodules/email`）＋ IThome／TechCrunch RSS 新聞（見
`submodules/newsfeed`）兩個來源「昨天」的內容，呼叫 Gemini 產出中文重點摘要，固定台灣時間
08:00 推播給 Robin。僅 Robin 可用（見 robinson SPEC.md「個人技能成長（僅 Robin 可用）」
章節），不處理任何 Telegram 對話流程，那是 `src/bot/commands.py`／`router.py` 的責任。

去重機制（NFR-11）：用 `users.skill_growth_pushed_on`（比照 `todos.daily_pushed_on` 慣例）記錄
「今天是否已推播過」，避免同一天 `/healthz` 被觸發多次時重複推播；因為每天只處理「昨天」這一天
固定範圍的來源資料，這個去重判斷天然涵蓋了 NFR-11「以來源日期避免重複摘要已處理過的電子報/
新聞」的要求，不需要另外維護內容雜湊表。

功能開關（見 `src/bot/toggles.py`）：`skill_growth` 是 `owner_only=True` 的功能，推播前一律
檢查 Robin 本人的開關狀態，關閉時直接跳過（不推播、也不消耗 Gemini API 額度）。

來源容錯（見 docs/specs/submodules-core/SPEC.md ADR-14 風險表）：三個來源（TLDR 電子報／
IThome／TechCrunch）任一個抓取失敗，只記 log、視為該來源今天沒有內容，不影響其他來源與整體
推播——單一新聞來源改版或暫時失效，不該讓 Robin 連其他兩個來源的內容都收不到。三個來源都沒有
內容時，仍照常推播一則「今天沒有新內容」的固定訊息（NFR-10 一致性：不允許靜默跳過），讓 Robin
知道排程有正常執行。
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.bot import toggles
from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_PUSH_HOUR = 8
_FEATURE_KEY = "skill_growth"

_TLDR_SENDER_DOMAIN = "tldrnewsletter.com"
_ITHOME_RSS_URL = "https://www.ithome.com.tw/rss"
_TECHCRUNCH_RSS_URL = "https://techcrunch.com/feed/"

_NO_CONTENT_MESSAGE = (
    "📭 主任，今天沒有抓到新的 TLDR 電子報，IThome／TechCrunch 也沒有新文章，"
    "暫時沒有東西可以幫你整理喔，明天再看看！"
)

_logger = logging.getLogger(__name__)


def _get_owner(db: CloudSQLClient) -> dict | None:
    """查詢 Robin（`is_owner = TRUE` 且已綁定）的使用者資料；理論上一定存在，查無資料屬於防禦性情境。"""
    return db.select(
        "users", where="is_owner = %s AND telegram_user_id IS NOT NULL", params=(True,), fetch_one=True
    )


def _fetch_newsletter_texts_safely(email_client, now: datetime) -> list[str]:
    """讀取 TLDR 電子報；失敗時只記 log，視為今天沒有電子報內容（見模組 docstring「來源容錯」）。"""
    try:
        return email_client.fetch_yesterday_emails_from_domain(_TLDR_SENDER_DOMAIN, now=now)
    except Exception:
        _logger.exception("讀取 TLDR 電子報失敗，該來源今天視為沒有內容")
        return []


def _fetch_rss_articles_safely(newsfeed_client, feed_url: str, source_name: str, now: datetime) -> list[dict]:
    """讀取指定 RSS Feed；失敗時只記 log，視為今天沒有該來源的新聞（見模組 docstring「來源容錯」）。"""
    try:
        return newsfeed_client.fetch_yesterday_articles(feed_url, now=now)
    except Exception:
        _logger.exception("讀取 %s RSS 失敗，該來源今天視為沒有內容", source_name)
        return []


def _build_summary_prompt(
    newsletter_texts: list[str], ithome_articles: list[dict], techcrunch_articles: list[dict]
) -> str:
    """組出給 Gemini 的摘要 prompt（FR-23：中文重點摘要與總結分享）。"""
    intro = (
        "你是 Robinson，請把以下 Robin 昨天訂閱到的技術情報，整理成繁體中文的重點摘要，"
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
        lines.append("【IThome 昨日新聞標題】")
        lines.extend(f"- {article['title']}（{article['link']}）" for article in ithome_articles)
        lines.append("")

    if techcrunch_articles:
        lines.append("【TechCrunch 昨日新聞標題】")
        lines.extend(f"- {article['title']}（{article['link']}）" for article in techcrunch_articles)
        lines.append("")

    return "\n".join(lines)


def build_daily_digest_message(
    newsletter_texts: list[str], ithome_articles: list[dict], techcrunch_articles: list[dict], llm_client
) -> str:
    """FR-23：整合三個來源的原始內容，呼叫 Gemini 產出中文重點摘要與總結分享。

    三個來源都沒有內容時，不呼叫 Gemini（省 API 額度、避免對空內容生成無意義文字），
    直接回傳固定的「今天沒有新內容」訊息。
    """
    if not newsletter_texts and not ithome_articles and not techcrunch_articles:
        return _NO_CONTENT_MESSAGE

    prompt = _build_summary_prompt(newsletter_texts, ithome_articles, techcrunch_articles)
    summary = llm_client.generate_text(prompt)
    return f"📬 主任，這是你今天的技術成長摘要：\n\n{summary}"


def check_and_push_daily_digest(
    db: CloudSQLClient,
    telegram_client,
    email_client,
    newsfeed_client,
    llm_client,
    now: datetime | None = None,
) -> None:
    """FR-22：每日固定時間（台灣時間 08:00）推播技能成長摘要給 Robin。

    只在台灣時間 08 點這個小時內執行（`/healthz` 每 10 分鐘觸發一次，這個小時內會命中好幾次，
    靠 `users.skill_growth_pushed_on` 避免同一天內重複推播，比照 `todos.daily_pushed_on` 慣例）；
    `skill_growth` 功能開關關閉時跳過，不消耗任何外部 API 額度。
    """
    now = now or datetime.now(timezone.utc)
    now_local = now.astimezone(_TAIWAN_TZ)
    if now_local.hour != _PUSH_HOUR:
        return

    owner = _get_owner(db)
    if owner is None:
        return

    today = now_local.date()
    if owner.get("skill_growth_pushed_on") == today:
        return

    if not toggles.is_feature_enabled(db, owner["id"], _FEATURE_KEY):
        return

    newsletter_texts = _fetch_newsletter_texts_safely(email_client, now)
    ithome_articles = _fetch_rss_articles_safely(newsfeed_client, _ITHOME_RSS_URL, "IThome", now)
    techcrunch_articles = _fetch_rss_articles_safely(newsfeed_client, _TECHCRUNCH_RSS_URL, "TechCrunch", now)

    message = build_daily_digest_message(newsletter_texts, ithome_articles, techcrunch_articles, llm_client)
    telegram_client.send_text(chat_id=owner["telegram_user_id"], text=message)

    db.update("users", {"skill_growth_pushed_on": today}, where="id = %s", params=(owner["id"],))
