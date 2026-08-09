"""src/bot/skill_growth.py 的單元測試（對應 robinson SPEC.md FR-22、FR-23，Step 3.1；
2026-08-09 生產環境回饋修正，見 ADR-25）。"""
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from src.bot import skill_growth


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def _make_clients(*, newsletter_texts=None, ithome_articles=None, techcrunch_articles=None, summary="重點摘要"):
    email_client = MagicMock()
    email_client.fetch_emails_from_domain_on_date.return_value = newsletter_texts or []
    newsfeed_client = MagicMock()
    newsfeed_client.fetch_articles_published_on.side_effect = lambda feed_url, target_date: (
        ithome_articles or [] if "ithome" in feed_url else techcrunch_articles or []
    )
    llm_client = MagicMock()
    llm_client.generate_text.return_value = summary
    return email_client, newsfeed_client, llm_client


def _seed_owner(fake_db, **overrides):
    row = {"telegram_user_id": 999, "role": "Robin", "is_owner": True}
    row.update(overrides)
    return fake_db.insert("users", row)


def _seed_digest(fake_db, **overrides):
    row = {"digest_date": date(2026, 8, 6), "source": "tldr", "summary_text": None, "pushed_on": None}
    row.update(overrides)
    return fake_db.insert("skill_growth_digests", row)


def _seed_full_digest_day(fake_db, digest_date=date(2026, 8, 6), pushed_on=None):
    """幫測試快速灌入某天完整的三個來源摘要。"""
    for source in skill_growth._SOURCES:
        _seed_digest(
            fake_db,
            digest_date=digest_date,
            source=source,
            summary_text=f"{source} 的重點摘要",
            pushed_on=pushed_on,
        )


# --- collect_and_store_daily_digest ---


def test_collect_skips_outside_of_11pm_window(fake_db):
    _seed_owner(fake_db)
    email_client, newsfeed_client, llm_client = _make_clients(newsletter_texts=["電子報內容"])

    skill_growth.collect_and_store_daily_digest(
        fake_db, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 3, 0)
    )

    assert fake_db.select("skill_growth_digests") == []


def test_collect_skips_when_no_owner_bound(fake_db):
    email_client, newsfeed_client, llm_client = _make_clients(newsletter_texts=["電子報內容"])

    skill_growth.collect_and_store_daily_digest(
        fake_db, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 15, 0)
    )

    assert fake_db.select("skill_growth_digests") == []


def test_collect_skips_when_feature_toggle_disabled(fake_db):
    owner_id = _seed_owner(fake_db)
    fake_db.insert("feature_toggles", {"user_id": owner_id, "feature_key": "tech_intel", "is_enabled": False})
    email_client, newsfeed_client, llm_client = _make_clients(newsletter_texts=["電子報內容"])

    skill_growth.collect_and_store_daily_digest(
        fake_db, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 15, 0)
    )

    assert fake_db.select("skill_growth_digests") == []


def test_collect_skips_when_already_collected_today(fake_db):
    _seed_owner(fake_db)
    _seed_full_digest_day(fake_db, digest_date=date(2026, 8, 7))
    email_client, newsfeed_client, llm_client = _make_clients(newsletter_texts=["電子報內容"])

    skill_growth.collect_and_store_daily_digest(
        fake_db, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 15, 0)
    )

    rows = fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 7),))
    assert len(rows) == 3
    llm_client.generate_text.assert_not_called()


def test_collect_stores_one_row_per_source_when_all_have_content(fake_db):
    _seed_owner(fake_db)
    email_client, newsfeed_client, llm_client = _make_clients(
        newsletter_texts=["電子報內容"],
        ithome_articles=[{"title": "IThome 新聞", "link": "https://ithome.com.tw/1"}],
        techcrunch_articles=[{"title": "TC 新聞", "link": "https://techcrunch.com/1"}],
        summary="這是重點摘要",
    )

    skill_growth.collect_and_store_daily_digest(
        fake_db, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 15, 0)
    )

    rows = fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 7),))
    assert len(rows) == 3
    by_source = {row["source"]: row["summary_text"] for row in rows}
    assert by_source == {"tldr": "這是重點摘要", "ithome": "這是重點摘要", "techcrunch": "這是重點摘要"}
    email_client.fetch_emails_from_domain_on_date.assert_called_once_with("tldrnewsletter.com", date(2026, 8, 7))
    assert llm_client.generate_text.call_count == 3


def test_collect_stores_no_content_text_for_sources_without_content(fake_db):
    _seed_owner(fake_db)
    email_client, newsfeed_client, llm_client = _make_clients(newsletter_texts=["電子報內容"])

    skill_growth.collect_and_store_daily_digest(
        fake_db, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 15, 0)
    )

    rows = fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 7),))
    by_source = {row["source"]: row["summary_text"] for row in rows}
    assert by_source["tldr"] != skill_growth._NO_CONTENT_TEXT
    assert by_source["ithome"] == skill_growth._NO_CONTENT_TEXT
    assert by_source["techcrunch"] == skill_growth._NO_CONTENT_TEXT
    # 只有 tldr 有內容，Gemini 只會被呼叫一次
    llm_client.generate_text.assert_called_once()


def test_collect_stores_no_content_text_for_all_sources_when_all_empty(fake_db):
    _seed_owner(fake_db)
    email_client, newsfeed_client, llm_client = _make_clients()

    skill_growth.collect_and_store_daily_digest(
        fake_db, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 15, 0)
    )

    rows = fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 7),))
    assert len(rows) == 3
    assert all(row["summary_text"] == skill_growth._NO_CONTENT_TEXT for row in rows)
    llm_client.generate_text.assert_not_called()


def test_collect_degrades_gracefully_when_email_source_fails(fake_db):
    _seed_owner(fake_db)
    email_client, newsfeed_client, llm_client = _make_clients(
        ithome_articles=[{"title": "IThome 新聞", "link": "https://ithome.com.tw/1"}]
    )
    email_client.fetch_emails_from_domain_on_date.side_effect = RuntimeError("IMAP 掛了")

    skill_growth.collect_and_store_daily_digest(
        fake_db, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 15, 0)
    )

    rows = {
        row["source"]: row["summary_text"]
        for row in fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 7),))
    }
    assert rows["tldr"] == skill_growth._NO_CONTENT_TEXT
    assert rows["ithome"] != skill_growth._NO_CONTENT_TEXT


def test_collect_degrades_gracefully_when_rss_source_fails(fake_db):
    _seed_owner(fake_db)
    email_client, newsfeed_client, llm_client = _make_clients(newsletter_texts=["電子報內容"])
    newsfeed_client.fetch_articles_published_on.side_effect = RuntimeError("RSS 掛了")

    skill_growth.collect_and_store_daily_digest(
        fake_db, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 15, 0)
    )

    rows = {
        row["source"]: row["summary_text"]
        for row in fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 7),))
    }
    assert rows["tldr"] != skill_growth._NO_CONTENT_TEXT
    assert rows["ithome"] == skill_growth._NO_CONTENT_TEXT
    assert rows["techcrunch"] == skill_growth._NO_CONTENT_TEXT


# --- check_and_push_daily_digest ---


def test_push_skips_outside_of_8am_window(fake_db):
    _seed_owner(fake_db)
    _seed_full_digest_day(fake_db)
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 3, 0))

    telegram_client.send_text.assert_not_called()


def test_push_skips_when_no_owner_bound(fake_db):
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))

    telegram_client.send_text.assert_not_called()


def test_push_skips_when_feature_toggle_disabled(fake_db):
    owner_id = _seed_owner(fake_db)
    fake_db.insert("feature_toggles", {"user_id": owner_id, "feature_key": "tech_intel", "is_enabled": False})
    _seed_full_digest_day(fake_db)
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))

    telegram_client.send_text.assert_not_called()


def test_push_sends_no_content_message_and_marks_dedup_when_nothing_collected(fake_db):
    _seed_owner(fake_db)
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))

    telegram_client.send_text.assert_called_once()
    call_kwargs = telegram_client.send_text.call_args.kwargs
    assert call_kwargs["chat_id"] == 999
    assert call_kwargs["text"] == skill_growth._NO_CONTENT_MESSAGE

    rows = fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 6),))
    assert len(rows) == 1
    assert rows[0]["source"] is None
    assert rows[0]["pushed_on"] == date(2026, 8, 7)


def test_push_does_not_repeat_within_same_hour_when_nothing_collected(fake_db):
    _seed_owner(fake_db)
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))
    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 15))

    telegram_client.send_text.assert_called_once()
    rows = fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 6),))
    assert len(rows) == 1


def test_push_sends_three_line_summary_and_marks_all_rows_pushed(fake_db):
    _seed_owner(fake_db)
    _seed_full_digest_day(fake_db)
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))

    telegram_client.send_text.assert_called_once()
    call_kwargs = telegram_client.send_text.call_args.kwargs
    assert call_kwargs["chat_id"] == 999
    text = call_kwargs["text"]
    assert "1.TLDR 電子報總結分享：tldr 的重點摘要" in text
    assert "2.ithome新聞總結分享：ithome 的重點摘要" in text
    assert "3.TechCrunch新聞總結分享：techcrunch 的重點摘要" in text

    rows = fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 6),))
    assert all(row["pushed_on"] == date(2026, 8, 7) for row in rows)


def test_push_uses_no_content_text_for_source_with_no_content(fake_db):
    _seed_owner(fake_db)
    _seed_digest(fake_db, source="tldr", summary_text="tldr 摘要")
    _seed_digest(fake_db, source="ithome", summary_text=skill_growth._NO_CONTENT_TEXT)
    _seed_digest(fake_db, source="techcrunch", summary_text=skill_growth._NO_CONTENT_TEXT)
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))

    text = telegram_client.send_text.call_args.kwargs["text"]
    assert "1.TLDR 電子報總結分享：tldr 摘要" in text
    assert f"2.ithome新聞總結分享：{skill_growth._NO_CONTENT_TEXT}" in text
    assert f"3.TechCrunch新聞總結分享：{skill_growth._NO_CONTENT_TEXT}" in text


def test_push_skips_when_digest_already_pushed_today(fake_db):
    _seed_owner(fake_db)
    _seed_full_digest_day(fake_db, pushed_on=date(2026, 8, 7))
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))

    telegram_client.send_text.assert_not_called()


def test_push_does_not_repeat_within_same_hour_when_digest_has_content(fake_db):
    _seed_owner(fake_db)
    _seed_full_digest_day(fake_db)
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))
    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 15))

    telegram_client.send_text.assert_called_once()


# --- _fetch_newsletter_texts_safely / _fetch_rss_articles_safely ---


def test_fetch_newsletter_texts_safely_returns_texts_on_success():
    email_client = MagicMock()
    email_client.fetch_emails_from_domain_on_date.return_value = ["內容"]

    result = skill_growth._fetch_newsletter_texts_safely(email_client, date(2026, 8, 7))

    assert result == ["內容"]


def test_fetch_newsletter_texts_safely_returns_empty_list_on_exception():
    email_client = MagicMock()
    email_client.fetch_emails_from_domain_on_date.side_effect = RuntimeError("IMAP 掛了")

    result = skill_growth._fetch_newsletter_texts_safely(email_client, date(2026, 8, 7))

    assert result == []


def test_fetch_rss_articles_safely_returns_articles_on_success():
    newsfeed_client = MagicMock()
    newsfeed_client.fetch_articles_published_on.return_value = [{"title": "t", "link": "l"}]

    result = skill_growth._fetch_rss_articles_safely(newsfeed_client, "https://example.com/rss", "IThome", date(2026, 8, 7))

    assert result == [{"title": "t", "link": "l"}]


def test_fetch_rss_articles_safely_returns_empty_list_on_exception():
    newsfeed_client = MagicMock()
    newsfeed_client.fetch_articles_published_on.side_effect = RuntimeError("RSS 掛了")

    result = skill_growth._fetch_rss_articles_safely(newsfeed_client, "https://example.com/rss", "IThome", date(2026, 8, 7))

    assert result == []


# --- summarize_source / _build_source_prompt ---


def test_summarize_source_returns_no_content_text_when_texts_empty():
    llm_client = MagicMock()

    result = skill_growth.summarize_source("tldr", [], llm_client)

    assert result == skill_growth._NO_CONTENT_TEXT
    llm_client.generate_text.assert_not_called()


def test_summarize_source_calls_llm_and_returns_stripped_summary():
    llm_client = MagicMock()
    llm_client.generate_text.return_value = "  重點摘要文字  "

    result = skill_growth.summarize_source("tldr", ["電子報內容"], llm_client)

    llm_client.generate_text.assert_called_once()
    assert result == "重點摘要文字"


def test_build_source_prompt_includes_label_and_body():
    prompt = skill_growth._build_source_prompt("ithome", ["- IThome 標題（https://ithome.com.tw/1）"])

    assert "ithome新聞總結分享" in prompt
    assert "IThome 標題" in prompt


# --- _format_digest_message ---


def test_format_digest_message_orders_by_fixed_source_sequence():
    rows = [
        {"source": "techcrunch", "summary_text": "tc 摘要"},
        {"source": "tldr", "summary_text": "tldr 摘要"},
        {"source": "ithome", "summary_text": "ithome 摘要"},
    ]

    message = skill_growth._format_digest_message(rows)

    lines = message.splitlines()
    assert lines[0] == "「每日技術成長摘要」"
    assert any(line.startswith("1.TLDR 電子報總結分享：") for line in lines)
    assert any(line.startswith("2.ithome新聞總結分享：") for line in lines)
    assert any(line.startswith("3.TechCrunch新聞總結分享：") for line in lines)


def test_format_digest_message_falls_back_to_no_content_text_when_source_missing():
    rows = [{"source": "tldr", "summary_text": "tldr 摘要"}]

    message = skill_growth._format_digest_message(rows)

    assert f"2.ithome新聞總結分享：{skill_growth._NO_CONTENT_TEXT}" in message
    assert f"3.TechCrunch新聞總結分享：{skill_growth._NO_CONTENT_TEXT}" in message


def test_format_digest_message_falls_back_when_summary_text_is_null():
    rows = [{"source": "tldr", "summary_text": None}]

    message = skill_growth._format_digest_message(rows)

    assert f"1.TLDR 電子報總結分享：{skill_growth._NO_CONTENT_TEXT}" in message


# --- _get_owner / _get_digests_for_date ---


def test_get_owner_returns_none_when_no_owner_bound(fake_db):
    assert skill_growth._get_owner(fake_db) is None


def test_get_owner_returns_bound_owner(fake_db):
    _seed_owner(fake_db)

    owner = skill_growth._get_owner(fake_db)

    assert owner is not None
    assert owner["is_owner"] is True
    assert owner["telegram_user_id"] == 999


def test_get_digests_for_date_returns_empty_list_when_not_found(fake_db):
    assert skill_growth._get_digests_for_date(fake_db, date(2026, 8, 7)) == []


def test_get_digests_for_date_returns_all_rows_for_that_date(fake_db):
    _seed_full_digest_day(fake_db, digest_date=date(2026, 8, 7))

    rows = skill_growth._get_digests_for_date(fake_db, date(2026, 8, 7))

    assert len(rows) == 3
    assert {row["source"] for row in rows} == set(skill_growth._SOURCES)
