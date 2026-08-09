"""src/bot/job_search.py 單元測試（對應 robinson SPEC.md FR-33、FR-36，Step 4.1，ADR-24）。"""
from src.bot import job_search

# --- is_text_length_valid（FR-36）---


def test_is_text_length_valid_within_limit():
    assert job_search.is_text_length_valid("我的履歷內容")


def test_is_text_length_valid_at_exact_limit():
    assert job_search.is_text_length_valid("A" * 3500)


def test_is_text_length_valid_over_limit():
    assert not job_search.is_text_length_valid("A" * 3501)


# --- is_years_of_experience_reasonable（FR-36，ADR-26 決策 1）---


def test_is_years_of_experience_reasonable_zero_is_valid():
    assert job_search.is_years_of_experience_reasonable(0)


def test_is_years_of_experience_reasonable_typical_value():
    assert job_search.is_years_of_experience_reasonable(3.5)


def test_is_years_of_experience_reasonable_boundary_max():
    assert job_search.is_years_of_experience_reasonable(60)


def test_is_years_of_experience_reasonable_over_max():
    assert not job_search.is_years_of_experience_reasonable(60.1)


def test_is_years_of_experience_reasonable_negative():
    assert not job_search.is_years_of_experience_reasonable(-1)


# --- save_search_criteria（FR-33，ADR-24 決策 3：允許同時存多組）---


def test_save_search_criteria_inserts_row(fake_db):
    criteria_id = job_search.save_search_criteria(fake_db, 1, "AI 工程師", None, 50000, None, None)

    row = fake_db.select("job_search_criteria", where="id = %s", params=(criteria_id,), fetch_one=True)
    assert row["user_id"] == 1
    assert row["keyword"] == "AI 工程師"
    assert row["region"] is None
    assert row["salary_min"] == 50000
    assert row["salary_max"] is None
    assert row["industry"] is None


def test_save_search_criteria_allows_multiple_rows_for_same_user(fake_db):
    job_search.save_search_criteria(fake_db, 1, "AI 工程師", None, 50000, None, None)
    job_search.save_search_criteria(fake_db, 1, "資料工程師", "台北", None, None, "軟體業")

    rows = fake_db.select("job_search_criteria", where="user_id = %s", params=(1,))
    assert len(rows) == 2
    assert {row["keyword"] for row in rows} == {"AI 工程師", "資料工程師"}


# --- save_profile（FR-36）---


def test_save_profile_updates_user_fields(fake_db):
    user_id = fake_db.insert("users", {"telegram_user_id": 1, "role": "Robin", "is_owner": True})

    job_search.save_profile(fake_db, user_id, "履歷內容", "期望工作內容", 3.5, 50000, 70000)

    row = fake_db.select("users", where="id = %s", params=(user_id,), fetch_one=True)
    assert row["job_resume"] == "履歷內容"
    assert row["job_expectation"] == "期望工作內容"
    assert row["years_of_experience"] == 3.5
    assert row["expected_salary_min"] == 50000
    assert row["expected_salary_max"] == 70000
