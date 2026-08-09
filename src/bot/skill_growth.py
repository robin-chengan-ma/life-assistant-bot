"""個人技能成長 — 每日重點技術分享（對應 docs/specs/robinson/SPEC.md FR-22、FR-23，Step 3.1）。

負責：整合 Gmail TLDR 電子報（見 `submodules/email`）＋ IThome／TechCrunch RSS 新聞（見
`submodules/newsfeed`）三個來源的內容，各自呼叫 Gemini 產出中文重點摘要，推播給 Robin。僅 Robin
可用，不處理任何 Telegram 對話流程，那是 `src/bot/commands.py`／`router.py` 的責任。

2026-08-07 經 Robin 回饋，拆成兩個獨立的排程階段（收集與推播分開，不是收到什麼就馬上推）：
① 收集（`collect_and_store_daily_digest()`）：固定台灣時間 23:00，讀取「當天」的 TLDR 電子報
   （寄件者 `dan@tldrnewsletter.com`）與 IThome／TechCrunch 新聞，三個來源各自獨立經 Gemini
   產出摘要，各寫入 `skill_growth_digests` 一筆（`digest_date` = 當天，`source` = 該來源）。
② 推播（`check_and_push_daily_digest()`）：固定台灣時間 08:00（隔天），讀取「昨天」（＝前一晚
   23:00 收集當下的「今天」）那三筆收集結果，組成三行式摘要推播給 Robin。使用者每天看到的都是
   「前一晚 23:00 收集到的技術情報」。

2026-08-09 經 Robin 生產環境回饋修正（見 ADR-25）：原本三個來源合併寫入單一 `summary_text`
欄位，Robin 完全無法分辨當天到底是哪個來源沒抓到內容、還是收集本身出了問題；推播訊息也塞了太多
原文內容，Robin 只需要三行結論。因此改成「一天最多三筆、一筆一個來源管道」的正規化設計，新增
`source` 欄位（`tldr`／`ithome`／`techcrunch`），`summary_text` 保留、但只存單一來源的精簡總結
（不再合併三個來源），未來新增來源只需要多寫一個 `source` 值，不需要再改 schema。

去重：`skill_growth_digests` 有 `UNIQUE (digest_date, source)` 約束，同一天同一來源只會收集一次；
`pushed_on` 記錄「這批（同一天三筆）是否已推播過」，避免 08:00 那個小時內 `/healthz` 多次觸發
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
——單一新聞來源改版或暫時失效，不該讓 Robin 連其他兩個來源的內容都收不到。單一來源當天沒有內容
時，不呼叫 Gemini（省 API 額度、避免對空內容生成無意義文字），`summary_text` 直接寫入固定文字
「今日無內容」（`_NO_CONTENT_TEXT`）——這跟「收集當下整個服務都不可用、連這個來源的列都沒寫入」
是兩種不同情境，後者靠 `source IS NULL` 的去重標記列處理，隔天推播時一律回覆 Robin 指定的固定
訊息「未獲得最新技術分享」（`_NO_CONTENT_MESSAGE`，NFR-10 一致性：不允許靜默跳過）。
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

_SOURCES = ("tldr", "ithome", "techcrunch")
_SOURCE_LABELS = {
    "tldr": "TLDR 電子報總結分享",
    "ithome": "ithome新聞總結分享",
    "techcrunch": "TechCrunch新聞總結分享",
}
_NO_CONTENT_TEXT = "今日無內容"
_NO_CONTENT_MESSAGE = "📭 主任，未獲得最新技術分享。"

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


def _build_source_prompt(source: str, texts: list[str]) -> str:
    """組出給 Gemini 的單一來源摘要 prompt（FR-23：中文重點摘要，只給結論，不需要條列原文）。"""
    label = _SOURCE_LABELS[source]
    body = "\n".join(texts)
    return (
        f"你是 Robinson，以下是 Robin 訂閱的「{label}」今天的原始內容，"
        "請用繁體中文整理成一段 100 字以內的重點總結，只給結論，不要條列、不要客套話、不要編造內容：\n\n"
        f"{body}"
    )


def summarize_source(source: str, texts: list[str], llm_client) -> str:
    """FR-23：把單一來源當天的原始內容，呼叫 Gemini 產出中文重點總結（100 字內）。

    該來源當天沒有內容時，不呼叫 Gemini（省 API 額度、避免對空內容生成無意義文字），
    直接回傳固定文字「今日無內容」。
    """
    if not texts:
        return _NO_CONTENT_TEXT

    prompt = _build_source_prompt(source, texts)
    return llm_client.generate_text(prompt).strip()


def _format_digest_message(rows: list[dict]) -> str:
    """FR-22：把「昨天」收集到的各來源摘要，組成 Robin 要求的三行式精簡格式。"""
    summaries = {row["source"]: (row.get("summary_text") or _NO_CONTENT_TEXT) for row in rows}
    lines = [
        "「每日技術成長摘要」",
        "",
        "你好，我是 Robinson。以下是我為 Robin 整理的最新技術情報重點摘要：",
        "",
    ]
    for index, source in enumerate(_SOURCES, start=1):
        text = summaries.get(source, _NO_CONTENT_TEXT)
        lines.append(f"{index}.{_SOURCE_LABELS[source]}：{text}")
    return "\n".join(lines)


def collect_and_store_daily_digest(
    db: CloudSQLClient,
    email_client,
    newsfeed_client,
    llm_client,
    now: datetime | None = None,
) -> None:
    """FR-23：每日固定時間（台灣時間 23:00）收集當天的技術情報，三個來源各自獨立經 Gemini
    產出摘要，各寫入 `skill_growth_digests` 一筆（`digest_date` = 當天，`source` = 該來源）。

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

    source_texts = {
        "tldr": newsletter_texts,
        "ithome": [f"- {article['title']}（{article['link']}）" for article in ithome_articles],
        "techcrunch": [f"- {article['title']}（{article['link']}）" for article in techcrunch_articles],
    }

    for source in _SOURCES:
        summary_text = summarize_source(source, source_texts[source], llm_client)
        db.insert("skill_growth_digests", {"digest_date": today, "source": source, "summary_text": summary_text})


def check_and_push_daily_digest(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """FR-22：每日固定時間（台灣時間 08:00）推播前一晚收集到的技術成長摘要給 Robin。

    只在台灣時間 08 點這個小時內執行；讀取「昨天」（＝前一晚 23:00 收集當下的「今天」）那幾筆
    `skill_growth_digests` 資料，組成三行式精簡訊息（見 `_format_digest_message`），靠
    `pushed_on` 避免同一天內重複推播。完全查無資料（例如收集當下服務剛好整個小時都不可用），
    一律回覆 Robin 指定的固定訊息「未獲得最新技術分享」（NFR-10：不允許靜默跳過），並補寫一筆
    `source IS NULL` 的去重標記列（`pushed_on` 直接設為今天），避免 08:00 這個小時內重複推播
    同一句「未獲得」。
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

    message = _format_digest_message(real_rows)
    telegram_client.send_text(chat_id=owner["telegram_user_id"], text=message)
    db.update("skill_growth_digests", {"pushed_on": today}, where="digest_date = %s", params=(yesterday,))
