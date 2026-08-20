from src.bot import job_search, job_settings
from src.bot.state import ConversationStateStore


def _seed_jobs(fake_db):
    fake_db.insert("job_postings", {"job_id_104": "job-1", "company_id_104": "c1", "title": "後端工程師", "url": "https://example.com/1", "score": 80, "is_closed": False, "is_closed_manual_override": False})
    fake_db.insert("job_postings", {"job_id_104": "job-2", "company_id_104": "c2", "title": "資料工程師", "url": "https://example.com/2", "score": 95, "is_closed": True, "is_closed_manual_override": False})


def test_job_settings_menu_has_ten_entries():
    _, keyboard = job_settings.start_menu()
    buttons = [row[0]["callback_data"] for row in keyboard["inline_keyboard"]]

    assert len(buttons) == 11
    assert "job_search:profile:resume" in buttons
    assert "job_search:external:add" in buttons


def test_criteria_menu_shows_region_and_salary_and_edit_button(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1})
    job_search.save_search_criteria(fake_db, user_id, "AI", "台北,新竹", 50000, 60000)

    text, keyboard = job_settings.start_criteria_menu(fake_db, user_id)

    assert "AI" in text
    assert "台北、新竹" in text
    assert "50000" in text and "60000" in text
    buttons = [row[0]["callback_data"] for row in keyboard["inline_keyboard"]]
    assert any(cb.startswith("job_search:criteria:edit:") for cb in buttons)
    assert any(cb.startswith("job_search:criteria:delete:") for cb in buttons)


def test_criteria_menu_without_region_or_salary_shows_unlimited():
    row = {"id": 1, "keyword": "後端工程師", "region": None, "salary_min": None, "salary_max": None}
    assert job_search.format_search_criteria(row) == "・後端工程師（不限地區，不限薪資）"


def test_criteria_add_example_text_mentions_multi_region():
    store = ConversationStateStore()
    text = job_settings.start_criteria_add(store, 1, 42)
    assert "多個地區" in text


def test_criteria_edit_overwrites_existing_row(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1})
    criteria_id = job_search.save_search_criteria(fake_db, user_id, "AI", "台北", 50000, 60000)
    store = ConversationStateStore()

    prompt_text, keyboard = job_settings.start_criteria_edit(fake_db, store, 1, user_id, criteria_id)
    assert "AI" in prompt_text
    assert keyboard is None

    class FakeLLM:
        def generate_text(self, _prompt):
            return "STATUS: CLEAR\nKEYWORD: 資料工程師\nREGION: 台北,新竹\nSALARY_MIN: 55000\nSALARY_MAX: 65000"

    reply = job_settings.handle_criteria_edit(fake_db, FakeLLM(), store, 1, "資料工程師，台北或新竹，薪資 5.5 到 6.5 萬")

    assert reply == "已更新職缺關鍵字設定。"
    updated = fake_db.select("job_search_criteria", where="id = %s", params=(criteria_id,), fetch_one=True)
    assert updated["keyword"] == "資料工程師"
    assert updated["region"] == "台北,新竹"
    assert updated["salary_min"] == 55000
    assert updated["salary_max"] == 65000


def test_criteria_add_saves_multi_region_string(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1})
    store = ConversationStateStore()
    job_settings.start_criteria_add(store, 1, user_id)

    class FakeLLM:
        def generate_text(self, _prompt):
            return "STATUS: CLEAR\nKEYWORD: AI\nREGION: 台北,新竹\nSALARY_MIN: 50000\nSALARY_MAX: 60000"

    reply = job_settings.handle_criteria_add(fake_db, FakeLLM(), store, 1, "台北或新竹的 AI，薪資 5 到 6 萬")

    assert reply == "已新增職缺關鍵字設定。"
    saved = fake_db.select("job_search_criteria", where="user_id = %s", params=(user_id,))[0]
    assert saved["region"] == "台北,新竹"


def test_criteria_edit_missing_row_returns_back_keyboard(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1})
    store = ConversationStateStore()

    text, keyboard = job_settings.start_criteria_edit(fake_db, store, 1, user_id, 999)

    assert "找不到" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "job_search:menu"


def test_crawl_matches_any_region_when_multiple_regions_set(fake_db, monkeypatch):
    user_id = fake_db.insert("users", {"telegram_user_id": 1})
    job_search.save_search_criteria(fake_db, user_id, "AI", "台北,新竹", None, None)

    class FakeJob104Client:
        def search_list(self, keyword, salary_min=None, salary_max=None, page=1):
            if page > 1:
                return []
            return [
                {"job_id": "job-taipei", "company_id": "c1", "company_name": "公司甲", "region": "台北市", "job_slug": "s1", "title": "AI 工程師", "url": "https://example.com/job-taipei"},
                {"job_id": "job-hsinchu", "company_id": "c2", "company_name": "公司乙", "region": "新竹市", "job_slug": "s2", "title": "AI 工程師", "url": "https://example.com/job-hsinchu"},
                {"job_id": "job-taichung", "company_id": "c3", "company_name": "公司丙", "region": "台中市", "job_slug": "s3", "title": "AI 工程師", "url": "https://example.com/job-taichung"},
            ]

        def fetch_job_detail(self, job_slug):
            return {}

    result = job_search.crawl_and_upsert_jobs(
        fake_db, FakeJob104Client(), user_id,
        sleep_func=lambda _seconds: None, random_func=lambda _a, _b: 0,
        now="now",
    )

    job_ids = {row["job_id_104"] for row in fake_db.select("job_postings")}
    assert job_ids == {"job-taipei", "job-hsinchu"}
    assert result["new_job_count"] == 2


def test_manual_closed_override_protects_crawler_value(fake_db):
    _seed_jobs(fake_db)
    job_search.set_job_closed_manually(fake_db, "job-1", True)

    job_search.upsert_job_posting(
        fake_db,
        {"job_id": "job-1", "company_id": "c1", "title": "後端工程師", "region": "台北", "url": "https://example.com/1", "is_closed": False},
        {},
        now="now",
    )

    row = fake_db.select("job_postings", where="job_id_104 = %s", params=("job-1",), fetch_one=True)
    assert row["is_closed"] is True
    assert row["is_closed_manual_override"] is True


def test_status_list_and_update_accept_all_four_statuses(fake_db):
    _seed_jobs(fake_db)
    job_search.record_application_status(fake_db, "job-1", "applied")

    listed = job_search.list_jobs_by_latest_application_status(fake_db, "applied")
    assert [item["job_id_104"] for item in listed] == ["job-1"]

    assert job_search.record_application_status(fake_db, "job-1", "rejected") is True
    latest = job_search.list_jobs_by_latest_application_status(fake_db, "rejected")
    assert [item["job_id_104"] for item in latest] == ["job-1"]


def test_resume_clear_requires_confirmation(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "job_resume": "既有履歷"})
    store = ConversationStateStore()

    text, keyboard = job_settings.start_profile_clear_confirm(fake_db, store, 1, user_id, "job_resume")
    assert "確定" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "job_search:profile:confirm_clear:resume"
    assert fake_db.select("users", where="id = %s", params=(user_id,), fetch_one=True)["job_resume"] == "既有履歷"

    job_settings.handle_profile_clear_confirm(fake_db, store, 1, user_id, "job_resume")
    assert fake_db.select("users", where="id = %s", params=(user_id,), fetch_one=True)["job_resume"] is None
