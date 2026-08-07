"""src/bot/skill_growth.py 的單元測試（對應 robinson SPEC.md FR-22、FR-23，Step 3.1）。"""
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from src.bot import skill_growth


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def _make_clients(*, newsletter_texts=None, ithome_articles=None, techcrunch_articles=None, summary="摘要內容"):
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
    row = {"digest_date": date(2026, 8, 6), "summary_text": None, "pushed_on": None}
    row.update(overrides)
    return fake_db.insert("skill_growth_digests", row)


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
    _seed_digest(fake_db, digest_date=date(2026, 8, 7), summary_text="已經收集過了")
    email_client, newsfeed_client, llm_client = _make_clients(newsletter_texts=["電子報內容"])

    skill_growth.collect_and_store_daily_digest(
        fake_db, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 15, 0)
    )

    rows = fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 7),))
    assert len(rows) == 1
    llm_client.generate_text.assert_not_called()


def test_collect_stores_summary_when_sources_have_content(fake_db):
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

    row = fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 7),), fetch_one=True)
    assert row["summary_text"] == "這是重點摘要"
    email_client.fetch_emails_from_domain_on_date.assert_called_once_with("tldrnewsletter.com", date(2026, 8, 7))


def test_collect_stores_null_summary_when_all_sources_empty(fake_db):
    _seed_owner(fake_db)
    email_client, newsfeed_client, llm_client = _make_clients()

    skill_growth.collect_and_store_daily_digest(
        fake_db, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 15, 0)
    )

    row = fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 7),), fetch_one=True)
    assert row["summary_text"] is None
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

    row = fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 7),), fetch_one=True)
    assert row["summary_text"] is not None
    prompt = llm_client.generate_text.call_args.args[0]
    assert "TLDR 電子報內容" not in prompt
    assert "IThome 新聞標題" in prompt


def test_collect_degrades_gracefully_when_rss_source_fails(fake_db):
    _seed_owner(fake_db)
    email_client, newsfeed_client, llm_client = _make_clients(newsletter_texts=["電子報內容"])
    newsfeed_client.fetch_articles_published_on.side_effect = RuntimeError("RSS 掛了")

    skill_growth.collect_and_store_daily_digest(
        fake_db, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 15, 0)
    )

    row = fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 7),), fetch_one=True)
    assert row["summary_text"] is not None
    prompt = llm_client.generate_text.call_args.args[0]
    assert "TLDR 電子報內容" in prompt
    assert "IThome 新聞標題" not in prompt
    assert "TechCrunch 新聞標題" not in prompt


# --- check_and_push_daily_digest ---


def test_push_skips_outside_of_8am_window(fake_db):
    _seed_owner(fake_db)
    _seed_digest(fake_db, digest_date=date(2026, 8, 6), summary_text="摘要")
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
    _seed_digest(fake_db, digest_date=date(2026, 8, 6), summary_text="摘要")
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))

    telegram_client.send_text.assert_not_called()


def test_push_sends_no_content_message_and_marks_dedup_when_no_digest_found(fake_db):
    _seed_owner(fake_db)
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))

    telegram_client.send_text.assert_called_once()
    call_kwargs = telegram_client.send_text.call_args.kwargs
    assert call_kwargs["chat_id"] == 999
    assert call_kwargs["text"] == skill_growth._NO_CONTENT_MESSAGE

    row = fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 6),), fetch_one=True)
    assert row is not None
    assert row["pushed_on"] == date(2026, 8, 7)


def test_push_does_not_repeat_within_same_hour_when_no_digest_found(fake_db):
    _seed_owner(fake_db)
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))
    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 15))

    telegram_client.send_text.assert_called_once()


def test_push_sends_summary_and_marks_pushed(fake_db):
    _seed_owner(fake_db)
    digest_id = _seed_digest(fake_db, digest_date=date(2026, 8, 6), summary_text="這是重點摘要")
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))

    telegram_client.send_text.assert_called_once()
    call_kwargs = telegram_client.send_text.call_args.kwargs
    assert call_kwargs["chat_id"] == 999
    assert "這是重點摘要" in call_kwargs["text"]

    row = fake_db.select("skill_growth_digests", where="id = %s", params=(digest_id,), fetch_one=True)
    assert row["pushed_on"] == date(2026, 8, 7)


def test_push_sends_no_content_message_when_digest_summary_is_null(fake_db):
    _seed_owner(fake_db)
    _seed_digest(fake_db, digest_date=date(2026, 8, 6), summary_text=None)
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))

    telegram_client.send_text.assert_called_once()
    assert telegram_client.send_text.call_args.kwargs["text"] == skill_growth._NO_CONTENT_MESSAGE


def test_push_skips_when_digest_already_pushed_today(fake_db):
    _seed_owner(fake_db)
    _seed_digest(fake_db, digest_date=date(2026, 8, 6), summary_text="摘要", pushed_on=date(2026, 8, 7))
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))

    telegram_client.send_text.assert_not_called()


def test_push_does_not_repeat_within_same_hour_when_digest_has_content(fake_db):
    _seed_owner(fake_db)
    _seed_digest(fake_db, digest_date=date(2026, 8, 6), summary_text="摘要")
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


# --- build_summary_text / _build_summary_prompt ---


def test_build_summary_text_returns_none_when_all_empty():
    llm_client = MagicMock()

    result = skill_growth.build_summary_text([], [], [], llm_client)

    assert result is None
    llm_client.generate_text.assert_not_called()


def test_build_summary_text_calls_llm_and_returns_summary():
    llm_client = MagicMock()
    llm_client.generate_text.return_value = "重點摘要文字"

    result = skill_growth.build_summary_text(["電子報內容"], [], [], llm_client)

    llm_client.generate_text.assert_called_once()
    assert result == "重點摘要文字"


def test_build_summary_prompt_includes_only_non_empty_sections():
    prompt = skill_growth._build_summary_prompt([], [{"title": "IThome 標題", "link": "https://ithome.com.tw/1"}], [])

    assert "TLDR 電子報內容" not in prompt
    assert "IThome 新聞標題" in prompt
    assert "IThome 標題" in prompt
    assert "TechCrunch 新聞標題" not in prompt


def test_build_summary_prompt_includes_all_sections_when_present():
    prompt = skill_growth._build_summary_prompt(
        ["電子報內容"],
        [{"title": "IThome 標題", "link": "https://ithome.com.tw/1"}],
        [{"title": "TC 標題", "link": "https://techcrunch.com/1"}],
    )

    assert "TLDR 電子報內容" in prompt
    assert "電子報內容" in prompt
    assert "IThome 新聞標題" in prompt
    assert "TechCrunch 新聞標題" in prompt


# --- _get_owner / _get_digest ---


def test_get_owner_returns_none_when_no_owner_bound(fake_db):
    assert skill_growth._get_owner(fake_db) is None


def test_get_owner_returns_bound_owner(fake_db):
    _seed_owner(fake_db)

    owner = skill_growth._get_owner(fake_db)

    assert owner is not None
    assert owner["is_owner"] is True
    assert owner["telegram_user_id"] == 999


def test_get_digest_returns_none_when_not_found(fake_db):
    assert skill_growth._get_digest(fake_db, date(2026, 8, 7)) is None


def test_get_digest_returns_row_when_found(fake_db):
    _seed_digest(fake_db, digest_date=date(2026, 8, 7), summary_text="摘要")

    digest = skill_growth._get_digest(fake_db, date(2026, 8, 7))

    assert digest is not None
    assert digest["summary_text"] == "摘要"
