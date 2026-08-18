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
