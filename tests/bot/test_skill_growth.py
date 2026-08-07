"""src/bot/skill_growth.py 的單元測試（對應 robinson SPEC.md FR-22、FR-23，Step 3.1）。"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.bot import skill_growth


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def _make_clients(*, newsletter_texts=None, ithome_articles=None, techcrunch_articles=None, summary="摘要內容"):
    telegram_client = MagicMock()
    email_client = MagicMock()
    email_client.fetch_yesterday_emails_from_domain.return_value = newsletter_texts or []
    newsfeed_client = MagicMock()
    newsfeed_client.fetch_yesterday_articles.side_effect = lambda feed_url, now=None: (
        ithome_articles or [] if "ithome" in feed_url else techcrunch_articles or []
    )
    llm_client = MagicMock()
    llm_client.generate_text.return_value = summary
    return telegram_client, email_client, newsfeed_client, llm_client


def _seed_owner(fake_db, **overrides):
    row = {"telegram_user_id": 999, "role": "Robin", "is_owner": True, "skill_growth_pushed_on": None}
    row.update(overrides)
    return fake_db.insert("users", row)


# --- check_and_push_daily_digest ---


def test_check_and_push_daily_digest_skips_outside_of_8am_window(fake_db):
    _seed_owner(fake_db)
    telegram_client, email_client, newsfeed_client, llm_client = _make_clients()

    skill_growth.check_and_push_daily_digest(
        fake_db, telegram_client, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 3, 0)
    )

    telegram_client.send_text.assert_not_called()


def test_check_and_push_daily_digest_skips_when_no_owner_bound(fake_db):
    telegram_client, email_client, newsfeed_client, llm_client = _make_clients()

    skill_growth.check_and_push_daily_digest(
        fake_db, telegram_client, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 0, 0)
    )

    telegram_client.send_text.assert_not_called()


def test_check_and_push_daily_digest_skips_when_already_pushed_today(fake_db):
    from datetime import date

    _seed_owner(fake_db, skill_growth_pushed_on=date(2026, 8, 7))
    telegram_client, email_client, newsfeed_client, llm_client = _make_clients(
        newsletter_texts=["電子報內容"]
    )

    skill_growth.check_and_push_daily_digest(
        fake_db, telegram_client, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 0, 0)
    )

    telegram_client.send_text.assert_not_called()


def test_check_and_push_daily_digest_skips_when_feature_toggle_disabled(fake_db):
    owner_id = _seed_owner(fake_db)
    fake_db.insert("feature_toggles", {"user_id": owner_id, "feature_key": "skill_growth", "is_enabled": False})
    telegram_client, email_client, newsfeed_client, llm_client = _make_clients(newsletter_texts=["電子報內容"])

    skill_growth.check_and_push_daily_digest(
        fake_db, telegram_client, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 0, 0)
    )

    telegram_client.send_text.assert_not_called()


def test_check_and_push_daily_digest_sends_summary_and_marks_pushed(fake_db):
    from datetime import date

    owner_id = _seed_owner(fake_db)
    telegram_client, email_client, newsfeed_client, llm_client = _make_clients(
        newsletter_texts=["電子報內容"],
        ithome_articles=[{"title": "IThome 新聞", "link": "https://ithome.com.tw/1"}],
        techcrunch_articles=[{"title": "TC 新聞", "link": "https://techcrunch.com/1"}],
        summary="這是重點摘要",
    )

    skill_growth.check_and_push_daily_digest(
        fake_db, telegram_client, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 0, 30)
    )

    telegram_client.send_text.assert_called_once()
    call_kwargs = telegram_client.send_text.call_args.kwargs
    assert call_kwargs["chat_id"] == 999
    assert "這是重點摘要" in call_kwargs["text"]

    updated_owner = fake_db.select("users", where="id = %s", params=(owner_id,), fetch_one=True)
    assert updated_owner["skill_growth_pushed_on"] == date(2026, 8, 7)


def test_check_and_push_daily_digest_does_not_repeat_within_same_hour(fake_db):
    _seed_owner(fake_db)
    telegram_client, email_client, newsfeed_client, llm_client = _make_clients(newsletter_texts=["電子報內容"])

    skill_growth.check_and_push_daily_digest(
        fake_db, telegram_client, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 0, 0)
    )
    skill_growth.check_and_push_daily_digest(
        fake_db, telegram_client, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 0, 15)
    )

    telegram_client.send_text.assert_called_once()


def test_check_and_push_daily_digest_sends_no_content_message_when_all_sources_empty(fake_db):
    _seed_owner(fake_db)
    telegram_client, email_client, newsfeed_client, llm_client = _make_clients()

    skill_growth.check_and_push_daily_digest(
        fake_db, telegram_client, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 0, 0)
    )

    telegram_client.send_text.assert_called_once()
    assert telegram_client.send_text.call_args.kwargs["text"] == skill_growth._NO_CONTENT_MESSAGE
    llm_client.generate_text.assert_not_called()


def test_check_and_push_daily_digest_degrades_gracefully_when_email_source_fails(fake_db):
    _seed_owner(fake_db)
    telegram_client, email_client, newsfeed_client, llm_client = _make_clients(
        ithome_articles=[{"title": "IThome 新聞", "link": "https://ithome.com.tw/1"}]
    )
    email_client.fetch_yesterday_emails_from_domain.side_effect = RuntimeError("IMAP 掛了")

    skill_growth.check_and_push_daily_digest(
        fake_db, telegram_client, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 0, 0)
    )

    telegram_client.send_text.assert_called_once()
    llm_client.generate_text.assert_called_once()
    prompt = llm_client.generate_text.call_args.args[0]
    assert "TLDR 電子報內容" not in prompt
    assert "IThome 昨日新聞標題" in prompt


def test_check_and_push_daily_digest_degrades_gracefully_when_rss_source_fails(fake_db):
    _seed_owner(fake_db)
    telegram_client, email_client, newsfeed_client, llm_client = _make_clients(newsletter_texts=["電子報內容"])
    newsfeed_client.fetch_yesterday_articles.side_effect = RuntimeError("RSS 掛了")

    skill_growth.check_and_push_daily_digest(
        fake_db, telegram_client, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 0, 0)
    )

    telegram_client.send_text.assert_called_once()
    llm_client.generate_text.assert_called_once()
    prompt = llm_client.generate_text.call_args.args[0]
    assert "TLDR 電子報內容" in prompt
    assert "IThome 昨日新聞標題" not in prompt
    assert "TechCrunch 昨日新聞標題" not in prompt


# --- _fetch_newsletter_texts_safely / _fetch_rss_articles_safely ---


def test_fetch_newsletter_texts_safely_returns_texts_on_success():
    email_client = MagicMock()
    email_client.fetch_yesterday_emails_from_domain.return_value = ["內容"]

    result = skill_growth._fetch_newsletter_texts_safely(email_client, now=_utc(2026, 8, 7, 0, 0))

    assert result == ["內容"]


def test_fetch_newsletter_texts_safely_returns_empty_list_on_exception():
    email_client = MagicMock()
    email_client.fetch_yesterday_emails_from_domain.side_effect = RuntimeError("IMAP 掛了")

    result = skill_growth._fetch_newsletter_texts_safely(email_client, now=_utc(2026, 8, 7, 0, 0))

    assert result == []


def test_fetch_rss_articles_safely_returns_articles_on_success():
    newsfeed_client = MagicMock()
    newsfeed_client.fetch_yesterday_articles.return_value = [{"title": "t", "link": "l"}]

    result = skill_growth._fetch_rss_articles_safely(
        newsfeed_client, "https://example.com/rss", "IThome", now=_utc(2026, 8, 7, 0, 0)
    )

    assert result == [{"title": "t", "link": "l"}]


def test_fetch_rss_articles_safely_returns_empty_list_on_exception():
    newsfeed_client = MagicMock()
    newsfeed_client.fetch_yesterday_articles.side_effect = RuntimeError("RSS 掛了")

    result = skill_growth._fetch_rss_articles_safely(
        newsfeed_client, "https://example.com/rss", "IThome", now=_utc(2026, 8, 7, 0, 0)
    )

    assert result == []


# --- build_daily_digest_message / _build_summary_prompt ---


def test_build_daily_digest_message_returns_no_content_message_when_all_empty():
    llm_client = MagicMock()

    result = skill_growth.build_daily_digest_message([], [], [], llm_client)

    assert result == skill_growth._NO_CONTENT_MESSAGE
    llm_client.generate_text.assert_not_called()


def test_build_daily_digest_message_calls_llm_and_wraps_summary():
    llm_client = MagicMock()
    llm_client.generate_text.return_value = "重點摘要文字"

    result = skill_growth.build_daily_digest_message(["電子報內容"], [], [], llm_client)

    llm_client.generate_text.assert_called_once()
    assert "重點摘要文字" in result


def test_build_summary_prompt_includes_only_non_empty_sections():
    prompt = skill_growth._build_summary_prompt(
        [], [{"title": "IThome 標題", "link": "https://ithome.com.tw/1"}], []
    )

    assert "TLDR 電子報內容" not in prompt
    assert "IThome 昨日新聞標題" in prompt
    assert "IThome 標題" in prompt
    assert "TechCrunch 昨日新聞標題" not in prompt


def test_build_summary_prompt_includes_all_sections_when_present():
    prompt = skill_growth._build_summary_prompt(
        ["電子報內容"],
        [{"title": "IThome 標題", "link": "https://ithome.com.tw/1"}],
        [{"title": "TC 標題", "link": "https://techcrunch.com/1"}],
    )

    assert "TLDR 電子報內容" in prompt
    assert "電子報內容" in prompt
    assert "IThome 昨日新聞標題" in prompt
    assert "TechCrunch 昨日新聞標題" in prompt


# --- _get_owner ---


def test_get_owner_returns_none_when_no_owner_bound(fake_db):
    assert skill_growth._get_owner(fake_db) is None


def test_get_owner_returns_bound_owner(fake_db):
    _seed_owner(fake_db)

    owner = skill_growth._get_owner(fake_db)

    assert owner is not None
    assert owner["is_owner"] is True
    assert owner["telegram_user_id"] == 999
