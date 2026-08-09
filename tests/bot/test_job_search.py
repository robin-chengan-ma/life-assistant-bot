"""src/bot/job_search.py 單元測試（對應 robinson SPEC.md FR-33～FR-36，Step 4.1，ADR-24）。"""
from datetime import date, datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from src.bot import job_search

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")

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
    criteria_id = job_search.save_search_criteria(fake_db, 1, "AI 工程師", None, 50000, None)

    row = fake_db.select("job_search_criteria", where="id = %s", params=(criteria_id,), fetch_one=True)
    assert row["user_id"] == 1
    assert row["keyword"] == "AI 工程師"
    assert row["region"] is None
    assert row["salary_min"] == 50000
    assert row["salary_max"] is None


def test_save_search_criteria_allows_multiple_rows_for_same_user(fake_db):
    job_search.save_search_criteria(fake_db, 1, "AI 工程師", None, 50000, None)
    job_search.save_search_criteria(fake_db, 1, "資料工程師", "台北", None, None)

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


# --- list_search_criteria（FR-33）---


def test_list_search_criteria_returns_only_this_user(fake_db):
    job_search.save_search_criteria(fake_db, 1, "AI 工程師", None, None, None)
    job_search.save_search_criteria(fake_db, 2, "別人的條件", None, None, None)

    rows = job_search.list_search_criteria(fake_db, 1)

    assert len(rows) == 1
    assert rows[0]["keyword"] == "AI 工程師"


# --- upsert_company（FR-35a）---


def test_upsert_company_inserts_new_company_with_null_background(fake_db):
    company_id, is_new = job_search.upsert_company(fake_db, "999", "某某科技", "台北市信義區", "軟體業")

    assert is_new is True
    row = fake_db.select("job_companies", where="id = %s", params=(company_id,), fetch_one=True)
    assert row["company_id_104"] == "999"
    assert row["company_name"] == "某某科技"
    assert row["background"] is None


def test_upsert_company_existing_company_does_not_overwrite(fake_db):
    existing_id = fake_db.insert(
        "job_companies",
        {"company_id_104": "999", "company_name": "某某科技", "region": "台北市", "background": "已回填的背景"},
    )

    company_id, is_new = job_search.upsert_company(fake_db, "999", "改名後的公司", "高雄市", "製造業")

    assert is_new is False
    assert company_id == existing_id
    row = fake_db.select("job_companies", where="id = %s", params=(existing_id,), fetch_one=True)
    assert row["company_name"] == "某某科技"
    assert row["background"] == "已回填的背景"


# --- upsert_job_posting（FR-34d）---


_JOB = {
    "job_id": "12345",
    "job_slug": "abcde",
    "title": "AI 工程師",
    "company_id": "999",
    "company_name": "某某科技",
    "region": "台北市信義區",
    "url": "https://www.104.com.tw/job/12345",
    "applicant_count": None,
}
_DETAIL = {
    "content": "負責 AI 模型開發",
    "required_years_experience": 3.0,
    "source_updated_at": None,
}


def test_upsert_job_posting_inserts_new_job(fake_db):
    now = datetime(2026, 8, 10, 8, 0, tzinfo=_TAIWAN_TZ)

    is_new = job_search.upsert_job_posting(fake_db, _JOB, _DETAIL, now)

    assert is_new is True
    row = fake_db.select("job_postings", where="job_id_104 = %s", params=("12345",), fetch_one=True)
    assert row["title"] == "AI 工程師"
    assert row["content"] == "負責 AI 模型開發"
    assert row["required_years_experience"] == 3.0
    assert row["first_seen_at"] == now
    assert row["last_crawled_at"] == now


def test_upsert_job_posting_updates_existing_job_without_changing_first_seen_at(fake_db):
    first_seen = datetime(2026, 8, 3, 8, 0, tzinfo=_TAIWAN_TZ)
    fake_db.insert(
        "job_postings",
        {
            "job_id_104": "12345", "company_id_104": "999", "title": "舊職缺名稱", "region": "台北市",
            "url": "https://www.104.com.tw/job/12345", "content": "舊內容",
            "required_years_experience": None, "applicant_count": None, "source_updated_at": None,
            "first_seen_at": first_seen, "last_crawled_at": first_seen,
        },
    )
    second_crawl = datetime(2026, 8, 10, 8, 0, tzinfo=_TAIWAN_TZ)

    is_new = job_search.upsert_job_posting(fake_db, _JOB, _DETAIL, second_crawl)

    assert is_new is False
    row = fake_db.select("job_postings", where="job_id_104 = %s", params=("12345",), fetch_one=True)
    assert row["title"] == "AI 工程師"
    assert row["content"] == "負責 AI 模型開發"
    assert row["first_seen_at"] == first_seen
    assert row["last_crawled_at"] == second_crawl


# --- crawl_and_upsert_jobs（FR-34a～FR-34d）---


class _FakeJob104Client:
    """模擬 submodules.job104.client.Job104Client，依 (keyword, page) 回傳預先設定好的清單，
    依 job_slug（詳情頁 API 用的短代碼 ID，跟 job_id/jobNo 是不同識別碼，2026-08-09 實測驗證
    確認，見 submodules/job104/client.py 模組 docstring）回傳預先設定好的詳情，並記錄呼叫
    次數供測試驗證分頁/延遲行為。"""

    def __init__(self, pages: dict, details: dict):
        self._pages = pages
        self._details = details
        self.search_calls: list[tuple] = []
        self.detail_calls: list[str] = []

    def search_list(self, keyword, salary_min=None, salary_max=None, page=1):
        self.search_calls.append((keyword, page))
        return self._pages.get((keyword, page), [])

    def fetch_job_detail(self, job_slug):
        self.detail_calls.append(job_slug)
        return self._details.get(job_slug, {})


def _fake_sleep(_seconds):
    pass


def _fake_random(_a, _b):
    return 0


def test_crawl_and_upsert_jobs_no_criteria_makes_no_requests(fake_db):
    client = _FakeJob104Client(pages={}, details={})

    result = job_search.crawl_and_upsert_jobs(fake_db, client, 1, sleep_func=_fake_sleep, random_func=_fake_random)

    assert result == {"new_company_ids": [], "new_job_count": 0, "updated_job_count": 0}
    assert client.search_calls == []


def test_crawl_and_upsert_jobs_single_criteria_single_page(fake_db):
    job_search.save_search_criteria(fake_db, 1, "AI 工程師", "台北市", 50000, None)
    page1 = [
        {"job_id": "1", "job_slug": "slug1", "title": "AI 工程師 A", "company_id": "100",
         "company_name": "A 公司", "region": "台北市", "url": "https://www.104.com.tw/job/1",
         "applicant_count": 3},
        {"job_id": "2", "job_slug": "slug2", "title": "AI 工程師 B", "company_id": "100",
         "company_name": "A 公司", "region": "台北市", "url": "https://www.104.com.tw/job/2",
         "applicant_count": 5},
    ]
    client = _FakeJob104Client(
        pages={("AI 工程師", 1): page1},
        details={"slug1": {"content": "內容1"}, "slug2": {"content": "內容2"}},
    )

    result = job_search.crawl_and_upsert_jobs(fake_db, client, 1, sleep_func=_fake_sleep, random_func=_fake_random)

    assert result == {"new_company_ids": ["100"], "new_job_count": 2, "updated_job_count": 0}
    assert client.search_calls == [("AI 工程師", 1), ("AI 工程師", 2)]  # 第 2 頁空清單才停止翻頁
    assert sorted(client.detail_calls) == ["slug1", "slug2"]
    jobs = fake_db.select("job_postings")
    assert len(jobs) == 2
    companies = fake_db.select("job_companies")
    assert len(companies) == 1


def test_crawl_and_upsert_jobs_filters_by_region_substring(fake_db):
    """2026-08-09 依 Robin 指示：地區篩選不送給 104 API（`area` 需要數字代碼，沒有可靠對照
    表），改由呼叫端對回傳結果的 `region` 文字做子字串比對篩選（見 `crawl_and_upsert_jobs()`
    docstring）。"""
    job_search.save_search_criteria(fake_db, 1, "AI 工程師", "台北市", None, None)
    page1 = [
        {"job_id": "1", "job_slug": "slug1", "title": "符合地區", "company_id": "100",
         "company_name": "A 公司", "region": "台北市信義區", "url": "https://www.104.com.tw/job/1",
         "applicant_count": 1},
        {"job_id": "2", "job_slug": "slug2", "title": "不符合地區", "company_id": "200",
         "company_name": "B 公司", "region": "新竹市", "url": "https://www.104.com.tw/job/2",
         "applicant_count": 2},
    ]
    client = _FakeJob104Client(
        pages={("AI 工程師", 1): page1}, details={"slug1": {}, "slug2": {}},
    )

    result = job_search.crawl_and_upsert_jobs(fake_db, client, 1, sleep_func=_fake_sleep, random_func=_fake_random)

    assert result["new_job_count"] == 1
    assert client.detail_calls == ["slug1"]  # 不符合地區的 slug2 完全不會呼叫詳情頁
    jobs = fake_db.select("job_postings")
    assert [j["title"] for j in jobs] == ["符合地區"]


def test_crawl_and_upsert_jobs_region_filter_does_not_stop_pagination_early(fake_db):
    """單頁篩選後一筆都不剩，也不能誤判成「這組條件已經爬完」而提早停止翻頁——分頁停止判斷
    要看 104 回傳的原始清單是否為空，不是篩選後的清單。"""
    job_search.save_search_criteria(fake_db, 1, "AI 工程師", "台北市", None, None)
    page1 = [
        {"job_id": "1", "job_slug": "slug1", "title": "不符合地區", "company_id": "100",
         "company_name": "A 公司", "region": "新竹市", "url": "https://www.104.com.tw/job/1",
         "applicant_count": 1},
    ]
    client = _FakeJob104Client(pages={("AI 工程師", 1): page1, ("AI 工程師", 2): []}, details={})

    result = job_search.crawl_and_upsert_jobs(fake_db, client, 1, sleep_func=_fake_sleep, random_func=_fake_random)

    assert result == {"new_company_ids": [], "new_job_count": 0, "updated_job_count": 0}
    assert client.search_calls == [("AI 工程師", 1), ("AI 工程師", 2)]
    assert client.detail_calls == []


def test_crawl_and_upsert_jobs_stops_pagination_on_empty_page(fake_db):
    job_search.save_search_criteria(fake_db, 1, "AI 工程師", None, None, None)
    client = _FakeJob104Client(pages={("AI 工程師", 1): []}, details={})

    result = job_search.crawl_and_upsert_jobs(fake_db, client, 1, sleep_func=_fake_sleep, random_func=_fake_random)

    assert result == {"new_company_ids": [], "new_job_count": 0, "updated_job_count": 0}
    assert client.search_calls == [("AI 工程師", 1)]


def test_crawl_and_upsert_jobs_multiple_criteria_each_queried(fake_db):
    job_search.save_search_criteria(fake_db, 1, "AI 工程師", None, None, None)
    job_search.save_search_criteria(fake_db, 1, "資料工程師", None, None, None)
    client = _FakeJob104Client(
        pages={
            ("AI 工程師", 1): [{"job_id": "1", "job_slug": "slug1", "title": "A", "company_id": "100",
                              "company_name": "A 公司", "region": "台北市",
                              "url": "https://www.104.com.tw/job/1", "applicant_count": 1}],
            ("資料工程師", 1): [{"job_id": "2", "job_slug": "slug2", "title": "B", "company_id": "200",
                             "company_name": "B 公司", "region": "新竹市",
                             "url": "https://www.104.com.tw/job/2", "applicant_count": 2}],
        },
        details={"slug1": {}, "slug2": {}},
    )

    result = job_search.crawl_and_upsert_jobs(fake_db, client, 1, sleep_func=_fake_sleep, random_func=_fake_random)

    assert result["new_job_count"] == 2
    assert sorted(result["new_company_ids"]) == ["100", "200"]


def test_crawl_and_upsert_jobs_applies_delay_between_every_request(fake_db):
    job_search.save_search_criteria(fake_db, 1, "AI 工程師", None, None, None)
    client = _FakeJob104Client(
        pages={("AI 工程師", 1): [{"job_id": "1", "job_slug": "slug1", "title": "A", "company_id": "100",
                                 "company_name": "A 公司", "region": "台北市",
                                 "url": "https://www.104.com.tw/job/1", "applicant_count": 1}]},
        details={"slug1": {}},
    )
    delay_calls = []

    def _tracking_sleep(seconds):
        delay_calls.append(seconds)

    job_search.crawl_and_upsert_jobs(
        fake_db, client, 1, sleep_func=_tracking_sleep, random_func=lambda a, b: 2.5
    )

    # 3 次請求：page1 列表、job1 詳情、page2 列表（空清單才停止），每次請求後都要延遲一次。
    assert len(client.search_calls) == 2
    assert len(client.detail_calls) == 1
    assert delay_calls == [2.5, 2.5, 2.5]
    for seconds in delay_calls:
        assert 2 <= seconds <= 4


# --- FR-35：公司背景 Email／CSV／Drive 人力協作機制 ---


def test_company_csv_filename():
    assert job_search.company_csv_filename(date(2026, 8, 9)) == "2026-08-09-104職缺公司.csv"


def test_get_companies_by_ids_returns_matching_rows_and_skips_missing(fake_db):
    fake_db.insert(
        "job_companies", {"company_id_104": "100", "company_name": "A 公司", "region": "台北市", "background": None}
    )
    fake_db.insert(
        "job_companies", {"company_id_104": "200", "company_name": "B 公司", "region": "新竹市", "background": None}
    )

    rows = job_search.get_companies_by_ids(fake_db, ["100", "999", "200"])

    assert [r["company_id_104"] for r in rows] == ["100", "200"]


def test_build_new_companies_csv_has_header_and_empty_background_column():
    companies = [
        {"company_id_104": "100", "company_name": "A 公司", "region": "台北市", "industry": "軟體業"},
        {"company_id_104": "200", "company_name": "B 公司", "region": None, "industry": None},
    ]

    csv_text = job_search.build_new_companies_csv(companies)

    lines = csv_text.strip().splitlines()
    assert lines[0] == "104公司ID,公司全名,地區,產業類型,背景"
    assert lines[1] == "100,A 公司,台北市,軟體業,"
    assert lines[2] == "200,B 公司,,,"


def test_send_new_companies_email_calls_client_with_expected_args():
    email_client = MagicMock()

    job_search.send_new_companies_email(email_client, "robin@gmail.com", date(2026, 8, 9), "104公司ID,背景\n100,\n")

    email_client.send_text_with_attachment.assert_called_once()
    call_kwargs = email_client.send_text_with_attachment.call_args.kwargs
    assert call_kwargs["to"] == "robin@gmail.com"
    assert call_kwargs["subject"] == "2026-08-09 排程 - Robinson 104 職缺公司列表"
    assert call_kwargs["body"] == "附件為本週爬到的最新公司列表，請參閱！"
    assert call_kwargs["attachment_filename"] == "2026-08-09-104職缺公司.csv"
    assert call_kwargs["attachment_bytes"] == "104公司ID,背景\n100,\n".encode("utf-8-sig")


def test_parse_companies_csv_extracts_filled_rows():
    csv_text = "104公司ID,公司全名,地區,產業類型,背景\n100,A 公司,台北市,軟體業,做電商平台的新創\n"

    entries = job_search.parse_companies_csv(csv_text)

    assert entries == [{"company_id_104": "100", "background": "做電商平台的新創"}]


def test_parse_companies_csv_skips_rows_with_empty_background():
    csv_text = "104公司ID,公司全名,地區,產業類型,背景\n100,A 公司,台北市,軟體業,\n"

    assert job_search.parse_companies_csv(csv_text) == []


def test_parse_companies_csv_skips_rows_with_empty_company_id():
    csv_text = "104公司ID,公司全名,地區,產業類型,背景\n,A 公司,台北市,軟體業,某個背景\n"

    assert job_search.parse_companies_csv(csv_text) == []


def test_apply_company_backgrounds_updates_matching_and_reports_not_found(fake_db):
    fake_db.insert(
        "job_companies", {"company_id_104": "100", "company_name": "A 公司", "region": "台北市", "background": None}
    )
    entries = [
        {"company_id_104": "100", "background": "電商新創"},
        {"company_id_104": "999", "background": "不存在的公司"},
    ]

    result = job_search.apply_company_backgrounds(fake_db, entries)

    assert result == {"updated_count": 1, "not_found_ids": ["999"]}
    row = fake_db.select("job_companies", where="company_id_104 = %s", params=("100",), fetch_one=True)
    assert row["background"] == "電商新創"


# --- check_and_run_weekly_job_search（FR-34b、FR-35a～FR-35c）---

_MONDAY_8AM = datetime(2026, 8, 10, 8, 0, tzinfo=_TAIWAN_TZ)  # 2026-08-10 是週一


def _seed_owner(fake_db, job_search_last_run_on=None):
    return fake_db.insert(
        "users",
        {
            "telegram_user_id": 8263904025, "role": "Robin", "is_owner": True,
            "job_search_last_run_on": job_search_last_run_on,
        },
    )


def test_check_and_run_weekly_job_search_skips_when_not_monday_8am(fake_db):
    _seed_owner(fake_db)
    job_search.save_search_criteria(fake_db, 1, "AI 工程師", None, None, None)
    email_client = MagicMock()
    telegram_client = MagicMock()
    not_monday = datetime(2026, 8, 11, 8, 0, tzinfo=_TAIWAN_TZ)

    job_search.check_and_run_weekly_job_search(
        fake_db, MagicMock(), email_client, "robin@gmail.com", telegram_client, now=not_monday
    )

    email_client.send_text_with_attachment.assert_not_called()
    telegram_client.send_text.assert_not_called()


def test_check_and_run_weekly_job_search_skips_when_no_owner(fake_db):
    email_client = MagicMock()
    telegram_client = MagicMock()

    job_search.check_and_run_weekly_job_search(
        fake_db, MagicMock(), email_client, "robin@gmail.com", telegram_client, now=_MONDAY_8AM
    )

    email_client.send_text_with_attachment.assert_not_called()


def test_check_and_run_weekly_job_search_skips_when_toggle_disabled(fake_db):
    owner_id = _seed_owner(fake_db)
    fake_db.insert("feature_toggles", {"user_id": owner_id, "feature_key": "job_search", "is_enabled": False})
    email_client = MagicMock()
    telegram_client = MagicMock()

    job_search.check_and_run_weekly_job_search(
        fake_db, MagicMock(), email_client, "robin@gmail.com", telegram_client, now=_MONDAY_8AM
    )

    email_client.send_text_with_attachment.assert_not_called()


def test_check_and_run_weekly_job_search_skips_when_already_run_today(fake_db):
    _seed_owner(fake_db, job_search_last_run_on=_MONDAY_8AM.date())
    email_client = MagicMock()
    telegram_client = MagicMock()

    job_search.check_and_run_weekly_job_search(
        fake_db, MagicMock(), email_client, "robin@gmail.com", telegram_client, now=_MONDAY_8AM
    )

    email_client.send_text_with_attachment.assert_not_called()


def test_check_and_run_weekly_job_search_no_new_companies_skips_email(fake_db, monkeypatch):
    monkeypatch.setattr(job_search, "_polite_delay", lambda *a, **k: None)
    owner_id = _seed_owner(fake_db)
    fake_db.insert(
        "job_companies", {"company_id_104": "100", "company_name": "A 公司", "region": "台北市", "background": "已知背景"}
    )
    job_search.save_search_criteria(fake_db, owner_id, "AI 工程師", None, None, None)
    client = _FakeJob104Client(
        pages={
            ("AI 工程師", 1): [
                {"job_id": "1", "job_slug": "slug1", "title": "A", "company_id": "100",
                 "company_name": "A 公司", "region": "台北市", "url": "https://www.104.com.tw/job/1",
                 "applicant_count": 1}
            ]
        },
        details={"slug1": {}},
    )
    email_client = MagicMock()
    telegram_client = MagicMock()

    job_search.check_and_run_weekly_job_search(
        fake_db, client, email_client, "robin@gmail.com", telegram_client, now=_MONDAY_8AM
    )

    email_client.send_text_with_attachment.assert_not_called()
    telegram_client.send_text.assert_not_called()
    owner_row = fake_db.select("users", where="id = %s", params=(owner_id,), fetch_one=True)
    assert owner_row["job_search_last_run_on"] == _MONDAY_8AM.date()


def test_check_and_run_weekly_job_search_new_companies_sends_email_and_notifies(fake_db, monkeypatch):
    monkeypatch.setattr(job_search, "_polite_delay", lambda *a, **k: None)
    owner_id = _seed_owner(fake_db)
    job_search.save_search_criteria(fake_db, owner_id, "AI 工程師", None, None, None)
    client = _FakeJob104Client(
        pages={
            ("AI 工程師", 1): [
                {"job_id": "1", "job_slug": "slug1", "title": "A", "company_id": "100",
                 "company_name": "A 公司", "region": "台北市", "url": "https://www.104.com.tw/job/1",
                 "applicant_count": 1}
            ]
        },
        details={"slug1": {}},
    )
    email_client = MagicMock()
    telegram_client = MagicMock()

    job_search.check_and_run_weekly_job_search(
        fake_db, client, email_client, "robin@gmail.com", telegram_client, now=_MONDAY_8AM
    )

    email_client.send_text_with_attachment.assert_called_once()
    call_kwargs = email_client.send_text_with_attachment.call_args.kwargs
    assert call_kwargs["to"] == "robin@gmail.com"
    assert "100,A 公司" in call_kwargs["attachment_bytes"].decode("utf-8-sig")
    telegram_client.send_text.assert_called_once_with(
        chat_id=8263904025, text=job_search.EMAIL_SENT_NOTIFICATION_TEXT
    )
    owner_row = fake_db.select("users", where="id = %s", params=(owner_id,), fetch_one=True)
    assert owner_row["job_search_last_run_on"] == _MONDAY_8AM.date()
