"""src/bot/skill_growth.py 的單元測試（對應 robinson SPEC.md FR-22、FR-23，Step 3.1；
2026-08-09 生產環境回饋修正，見 ADR-25、ADR-27）。"""
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
    newsfeed_client.fetch_article_content.return_value = "抓到的文章全文內容"
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


def test_collect_stores_one_row_per_source_when_all_have_content(fake_db, monkeypatch):
    monkeypatch.setattr(skill_growth.time, "sleep", MagicMock())
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
    newsfeed_client.fetch_article_content.assert_any_call("https://ithome.com.tw/1")
    newsfeed_client.fetch_article_content.assert_any_call("https://techcrunch.com/1")
    assert llm_client.generate_text.call_count == 3


def test_collect_stores_no_content_text_for_sources_without_content(fake_db, monkeypatch):
    monkeypatch.setattr(skill_growth.time, "sleep", MagicMock())
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


def test_collect_degrades_gracefully_when_email_source_fails(fake_db, monkeypatch):
    monkeypatch.setattr(skill_growth.time, "sleep", MagicMock())
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


def test_collect_degrades_gracefully_when_rss_source_fails(fake_db, monkeypatch):
    monkeypatch.setattr(skill_growth.time, "sleep", MagicMock())
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


def test_collect_degrades_gracefully_when_single_article_content_fetch_fails(fake_db, monkeypatch):
    monkeypatch.setattr(skill_growth.time, "sleep", MagicMock())
    _seed_owner(fake_db)
    email_client, newsfeed_client, llm_client = _make_clients(
        ithome_articles=[
            {"title": "文章一", "link": "https://ithome.com.tw/1"},
            {"title": "文章二", "link": "https://ithome.com.tw/2"},
        ]
    )
    newsfeed_client.fetch_article_content.side_effect = [RuntimeError("網路掛了"), "文章二全文"]

    skill_growth.collect_and_store_daily_digest(
        fake_db, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 15, 0)
    )

    # 單篇全文抓取失敗不應中斷整個收集流程；失敗的那篇直接捨棄，成功的那篇仍會被拿去生成摘要
    rows = {
        row["source"]: row["summary_text"]
        for row in fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 7),))
    }
    assert rows["ithome"] != skill_growth._NO_CONTENT_TEXT


def test_collect_adds_delay_between_article_content_fetches(fake_db, monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(skill_growth.time, "sleep", mock_sleep)
    monkeypatch.setattr(skill_growth.random, "uniform", MagicMock(return_value=1.5))
    _seed_owner(fake_db)
    email_client, newsfeed_client, llm_client = _make_clients(
        ithome_articles=[
            {"title": "文章一", "link": "https://ithome.com.tw/1"},
            {"title": "文章二", "link": "https://ithome.com.tw/2"},
        ]
    )

    skill_growth.collect_and_store_daily_digest(
        fake_db, email_client, newsfeed_client, llm_client, now=_utc(2026, 8, 7, 15, 0)
    )

    # 兩篇文章之間應該有一次延遲（第一篇抓取前不需要延遲）
    mock_sleep.assert_called_once_with(1.5)


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


def test_push_sends_three_separate_messages_when_all_sources_have_content(fake_db):
    _seed_owner(fake_db)
    _seed_full_digest_day(fake_db)
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))

    assert telegram_client.send_text.call_count == 3
    texts = [c.kwargs["text"] for c in telegram_client.send_text.call_args_list]
    assert texts[0].startswith("「每日技術成長摘要-TLDR」")
    assert "tldr 的重點摘要" in texts[0]
    assert texts[1].startswith("「每日技術成長摘要-IThome」")
    assert "ithome 的重點摘要" in texts[1]
    assert texts[2].startswith("「每日技術成長摘要-TechCrunch」")
    assert "techcrunch 的重點摘要" in texts[2]
    for c in telegram_client.send_text.call_args_list:
        assert c.kwargs["chat_id"] == 999

    rows = fake_db.select("skill_growth_digests", where="digest_date = %s", params=(date(2026, 8, 6),))
    assert all(row["pushed_on"] == date(2026, 8, 7) for row in rows)


def test_push_skips_sources_without_content_entirely(fake_db):
    _seed_owner(fake_db)
    _seed_digest(fake_db, source="tldr", summary_text=skill_growth._NO_CONTENT_TEXT)
    _seed_digest(fake_db, source="ithome", summary_text=skill_growth._NO_CONTENT_TEXT)
    _seed_digest(fake_db, source="techcrunch", summary_text="techcrunch 有內容")
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))

    telegram_client.send_text.assert_called_once()
    text = telegram_client.send_text.call_args.kwargs["text"]
    assert text.startswith("「每日技術成長摘要-TechCrunch」")
    assert "今日無內容" not in text


def test_push_sends_no_content_message_when_all_sources_have_no_content(fake_db):
    _seed_owner(fake_db)
    _seed_digest(fake_db, source="tldr", summary_text=skill_growth._NO_CONTENT_TEXT)
    _seed_digest(fake_db, source="ithome", summary_text=skill_growth._NO_CONTENT_TEXT)
    _seed_digest(fake_db, source="techcrunch", summary_text=skill_growth._NO_CONTENT_TEXT)
    telegram_client = MagicMock()

    skill_growth.check_and_push_daily_digest(fake_db, telegram_client, now=_utc(2026, 8, 7, 0, 0))

    telegram_client.send_text.assert_called_once()
    assert telegram_client.send_text.call_args.kwargs["text"] == skill_growth._NO_CONTENT_MESSAGE


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

    assert telegram_client.send_text.call_count == 3


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


# --- _enrich_articles_with_content ---


def test_enrich_articles_with_content_attaches_content(monkeypatch):
    monkeypatch.setattr(skill_growth.time, "sleep", MagicMock())
    newsfeed_client = MagicMock()
    newsfeed_client.fetch_article_content.return_value = "文章全文"

    result = skill_growth._enrich_articles_with_content(
        newsfeed_client, [{"title": "標題", "link": "https://example.com/1"}]
    )

    assert result == [{"title": "標題", "link": "https://example.com/1", "content": "文章全文"}]


def test_enrich_articles_with_content_skips_article_when_fetch_fails(monkeypatch):
    monkeypatch.setattr(skill_growth.time, "sleep", MagicMock())
    newsfeed_client = MagicMock()
    newsfeed_client.fetch_article_content.side_effect = RuntimeError("網路掛了")

    result = skill_growth._enrich_articles_with_content(
        newsfeed_client, [{"title": "標題", "link": "https://example.com/1"}]
    )

    assert result == []


def test_enrich_articles_with_content_keeps_successful_and_drops_failed(monkeypatch):
    monkeypatch.setattr(skill_growth.time, "sleep", MagicMock())
    newsfeed_client = MagicMock()
    newsfeed_client.fetch_article_content.side_effect = ["文章一全文", RuntimeError("網路掛了")]

    result = skill_growth._enrich_articles_with_content(
        newsfeed_client,
        [
            {"title": "標題一", "link": "https://example.com/1"},
            {"title": "標題二", "link": "https://example.com/2"},
        ],
    )

    assert result == [{"title": "標題一", "link": "https://example.com/1", "content": "文章一全文"}]


def test_enrich_articles_with_content_does_not_sleep_before_first_article(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(skill_growth.time, "sleep", mock_sleep)
    newsfeed_client = MagicMock()
    newsfeed_client.fetch_article_content.return_value = "內容"

    skill_growth._enrich_articles_with_content(newsfeed_client, [{"title": "標題", "link": "https://example.com/1"}])

    mock_sleep.assert_not_called()


# --- summarize_source / _build_source_prompt ---


def test_summarize_source_returns_no_content_text_when_content_empty():
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


def test_summarize_source_does_not_truncate_when_llm_exceeds_max_chars():
    """2026-08-12 依 Robin 回饋移除硬截斷保險：字數上限只透過 Prompt 要求，不在程式端強制截斷。"""
    llm_client = MagicMock()
    llm_client.generate_text.return_value = "字" * 250

    result = skill_growth.summarize_source("tldr", ["電子報內容"], llm_client)

    assert len(result) == 250
    assert not result.endswith("…")


def test_build_source_prompt_tldr_includes_newsletter_text():
    prompt = skill_growth._build_source_prompt("tldr", ["電子報內容"])

    assert "TLDR" in prompt
    assert "電子報內容" in prompt
    assert "200" in prompt
    assert "至少要有 5 句話" not in prompt


def test_build_source_prompt_rss_source_includes_article_content():
    prompt = skill_growth._build_source_prompt(
        "ithome", [{"title": "IThome 標題", "link": "https://ithome.com.tw/1", "content": "文章全文內容"}]
    )

    assert "IThome" in prompt
    assert "IThome 標題" in prompt
    assert "文章全文內容" in prompt


# --- _format_source_message ---


def test_format_source_message_includes_title_and_summary():
    message = skill_growth._format_source_message("tldr", "這是摘要內容")

    assert message.startswith("「每日技術成長摘要-TLDR」")
    assert "這是摘要內容" in message


def test_format_source_message_uses_correct_display_name_per_source():
    assert "IThome" in skill_growth._format_source_message("ithome", "摘要")
    assert "TechCrunch" in skill_growth._format_source_message("techcrunch", "摘要")


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
