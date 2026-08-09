"""src/bot/commands.py 求職模組設定流程單元測試（對應 robinson SPEC.md FR-33、FR-36，
Step 4.1，ADR-24、ADR-26）。"""
from src.bot import commands
from src.bot.state import ConversationStateStore


class _FakeGDriveClient:
    """模擬 submodules.gdrive.client.GDriveClient，只實作 handle_company_csv_uploaded 會用到的
    list_files／download_file。"""

    def __init__(self, files: dict):
        # files: {filename: csv_bytes}
        self._files = files

    def list_files(self, name_contains=None):
        return [
            {"id": f"drive-id-{name}", "name": name, "mimeType": "text/csv"}
            for name in self._files
            if name_contains is None or name_contains in name
        ]

    def download_file(self, file_id):
        for name, content in self._files.items():
            if file_id == f"drive-id-{name}":
                return content
        raise FileNotFoundError(file_id)


class _FakeLLMClient:
    """模擬 submodules.llm.client.LLMClient，只實作求職模組流程會用到的 generate_text。"""

    def __init__(self, response_text="CONFIRM"):
        self.response_text = response_text
        self.last_prompt = None

    def generate_text(self, prompt):
        self.last_prompt = prompt
        return self.response_text


_CRITERIA_CLEAR = "STATUS: CLEAR\nKEYWORD: AI 工程師\nREGION: NONE\nSALARY_MIN: 50000\nSALARY_MAX: NONE"


def _seed_owner(fake_db):
    return fake_db.insert("users", {"telegram_user_id": 8263904025, "role": "Robin", "is_owner": True})


# --- start_job_search_setup ---


def test_start_job_search_setup_sets_state(fake_db):
    user_id = _seed_owner(fake_db)
    state_store = ConversationStateStore()

    reply = commands.start_job_search_setup(state_store, 999, user_id)

    assert "需求" in reply
    assert state_store.get(999) == {"flow": "pending_job_search_criteria", "target_user_id": user_id}


# --- handle_job_search_criteria_step（FR-33）---


def test_handle_job_search_criteria_step_unclear_reprompts(fake_db):
    user_id = _seed_owner(fake_db)
    state_store = ConversationStateStore()
    commands.start_job_search_setup(state_store, 999, user_id)
    llm_client = _FakeLLMClient(response_text="STATUS: UNCLEAR")

    reply = commands.handle_job_search_criteria_step(llm_client, state_store, 999, "隨便")

    assert "不太確定" in reply
    assert state_store.get(999)["flow"] == "pending_job_search_criteria"


def test_handle_job_search_criteria_step_clear_moves_to_ready_confirm(fake_db):
    user_id = _seed_owner(fake_db)
    state_store = ConversationStateStore()
    commands.start_job_search_setup(state_store, 999, user_id)
    llm_client = _FakeLLMClient(response_text=_CRITERIA_CLEAR)

    reply = commands.handle_job_search_criteria_step(
        llm_client, state_store, 999, "我想找 AI 相關的，薪資 50000 以上，其他不限"
    )

    assert "一週只會做一次" in reply
    state = state_store.get(999)
    assert state["flow"] == "pending_job_search_ready_confirm"
    assert state["keyword"] == "AI 工程師"
    assert state["region"] is None
    assert state["salary_min"] == 50000
    assert state["salary_max"] is None


# --- handle_job_search_ready_confirm_step ---


def test_handle_job_search_ready_confirm_step_cancel_clears_state(fake_db):
    user_id = _seed_owner(fake_db)
    state_store = ConversationStateStore()
    commands.start_job_search_setup(state_store, 999, user_id)
    commands.handle_job_search_criteria_step(_FakeLLMClient(_CRITERIA_CLEAR), state_store, 999, "AI 相關")
    llm_client = _FakeLLMClient(response_text="CANCEL")

    reply = commands.handle_job_search_ready_confirm_step(llm_client, state_store, 999, "還沒準備好")

    assert "先不設定" in reply
    assert state_store.get(999) is None


def test_handle_job_search_ready_confirm_step_confirm_moves_to_resume(fake_db):
    user_id = _seed_owner(fake_db)
    state_store = ConversationStateStore()
    commands.start_job_search_setup(state_store, 999, user_id)
    commands.handle_job_search_criteria_step(_FakeLLMClient(_CRITERIA_CLEAR), state_store, 999, "AI 相關")
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_job_search_ready_confirm_step(llm_client, state_store, 999, "好了")

    assert "履歷" in reply
    assert state_store.get(999)["flow"] == "pending_job_search_resume"


# --- handle_job_search_resume_step / handle_job_search_resume_confirm_step（FR-36）---


def _advance_to_resume(fake_db, state_store, telegram_user_id=999):
    user_id = _seed_owner(fake_db)
    commands.start_job_search_setup(state_store, telegram_user_id, user_id)
    commands.handle_job_search_criteria_step(_FakeLLMClient(_CRITERIA_CLEAR), state_store, telegram_user_id, "AI 相關")
    commands.handle_job_search_ready_confirm_step(
        _FakeLLMClient("CONFIRM"), state_store, telegram_user_id, "好了"
    )
    return user_id


def test_handle_job_search_resume_step_over_length_reprompts(fake_db):
    state_store = ConversationStateStore()
    _advance_to_resume(fake_db, state_store)

    reply = commands.handle_job_search_resume_step(state_store, 999, "A" * 3501)

    assert "超過 3500 字" in reply
    assert state_store.get(999)["flow"] == "pending_job_search_resume"


def test_handle_job_search_resume_step_valid_moves_to_confirm(fake_db):
    state_store = ConversationStateStore()
    _advance_to_resume(fake_db, state_store)

    reply = commands.handle_job_search_resume_step(state_store, 999, "五年後端開發經驗")

    assert "修正" in reply
    state = state_store.get(999)
    assert state["flow"] == "pending_job_search_resume_confirm"
    assert state["resume"] == "五年後端開發經驗"


def test_handle_job_search_resume_step_appends_pii_reminder(fake_db):
    state_store = ConversationStateStore()
    _advance_to_resume(fake_db, state_store)

    reply = commands.handle_job_search_resume_step(state_store, 999, "我的手機是 0912345678")

    assert "個人敏感資料" in reply


def test_handle_job_search_resume_confirm_step_revise_returns_to_resume(fake_db):
    state_store = ConversationStateStore()
    _advance_to_resume(fake_db, state_store)
    commands.handle_job_search_resume_step(state_store, 999, "五年後端開發經驗")
    llm_client = _FakeLLMClient(response_text="REVISE")

    reply = commands.handle_job_search_resume_confirm_step(llm_client, state_store, 999, "要改")

    assert "重新提供" in reply
    assert state_store.get(999)["flow"] == "pending_job_search_resume"


def test_handle_job_search_resume_confirm_step_confirm_moves_to_expectation(fake_db):
    state_store = ConversationStateStore()
    _advance_to_resume(fake_db, state_store)
    commands.handle_job_search_resume_step(state_store, 999, "五年後端開發經驗")
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_job_search_resume_confirm_step(llm_client, state_store, 999, "沒有")

    assert "期望工作敘述" in reply
    assert state_store.get(999)["flow"] == "pending_job_search_expectation"


# --- handle_job_search_expectation_step / handle_job_search_expectation_confirm_step（FR-36）---


def _advance_to_expectation(fake_db, state_store, telegram_user_id=999):
    _advance_to_resume(fake_db, state_store, telegram_user_id)
    commands.handle_job_search_resume_step(state_store, telegram_user_id, "五年後端開發經驗")
    commands.handle_job_search_resume_confirm_step(_FakeLLMClient("CONFIRM"), state_store, telegram_user_id, "沒有")


def test_handle_job_search_expectation_step_over_length_reprompts(fake_db):
    state_store = ConversationStateStore()
    _advance_to_expectation(fake_db, state_store)

    reply = commands.handle_job_search_expectation_step(state_store, 999, "A" * 3501)

    assert "超過 3500 字" in reply
    assert state_store.get(999)["flow"] == "pending_job_search_expectation"


def test_handle_job_search_expectation_step_valid_moves_to_confirm(fake_db):
    state_store = ConversationStateStore()
    _advance_to_expectation(fake_db, state_store)

    reply = commands.handle_job_search_expectation_step(state_store, 999, "希望能遠端工作")

    assert "年資" in reply
    state = state_store.get(999)
    assert state["flow"] == "pending_job_search_expectation_confirm"
    assert state["expectation"] == "希望能遠端工作"


def test_handle_job_search_expectation_confirm_step_revise_returns_to_expectation(fake_db):
    state_store = ConversationStateStore()
    _advance_to_expectation(fake_db, state_store)
    commands.handle_job_search_expectation_step(state_store, 999, "希望能遠端工作")
    llm_client = _FakeLLMClient(response_text="REVISE")

    reply = commands.handle_job_search_expectation_confirm_step(llm_client, state_store, 999, "要改")

    assert "重新提供" in reply
    assert state_store.get(999)["flow"] == "pending_job_search_expectation"


def test_handle_job_search_expectation_confirm_step_confirm_moves_to_years_experience(fake_db):
    state_store = ConversationStateStore()
    _advance_to_expectation(fake_db, state_store)
    commands.handle_job_search_expectation_step(state_store, 999, "希望能遠端工作")
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = commands.handle_job_search_expectation_confirm_step(llm_client, state_store, 999, "沒有")

    assert "年資" in reply
    assert state_store.get(999)["flow"] == "pending_job_search_years_experience"


# --- handle_job_search_years_experience_step（FR-36，ADR-26 決策 1）---


def _advance_to_years_experience(fake_db, state_store, telegram_user_id=999):
    _advance_to_expectation(fake_db, state_store, telegram_user_id)
    commands.handle_job_search_expectation_step(state_store, telegram_user_id, "希望能遠端工作")
    commands.handle_job_search_expectation_confirm_step(
        _FakeLLMClient("CONFIRM"), state_store, telegram_user_id, "沒有"
    )


def test_handle_job_search_years_experience_step_not_a_number_reprompts(fake_db):
    state_store = ConversationStateStore()
    _advance_to_years_experience(fake_db, state_store)

    reply = commands.handle_job_search_years_experience_step(state_store, 999, "很多年")

    assert "沒看懂" in reply
    assert state_store.get(999)["flow"] == "pending_job_search_years_experience"


def test_handle_job_search_years_experience_step_unreasonable_reprompts(fake_db):
    state_store = ConversationStateStore()
    _advance_to_years_experience(fake_db, state_store)

    reply = commands.handle_job_search_years_experience_step(state_store, 999, "100")

    assert "不太合理" in reply
    assert state_store.get(999)["flow"] == "pending_job_search_years_experience"


def test_handle_job_search_years_experience_step_zero_is_valid(fake_db):
    state_store = ConversationStateStore()
    _advance_to_years_experience(fake_db, state_store)

    reply = commands.handle_job_search_years_experience_step(state_store, 999, "0")

    assert "薪資下限" in reply
    state = state_store.get(999)
    assert state["flow"] == "pending_job_search_salary_min"
    assert state["years_of_experience"] == 0


def test_handle_job_search_years_experience_step_valid_moves_to_salary_min(fake_db):
    state_store = ConversationStateStore()
    _advance_to_years_experience(fake_db, state_store)

    reply = commands.handle_job_search_years_experience_step(state_store, 999, "3.5")

    assert "薪資下限" in reply
    state = state_store.get(999)
    assert state["flow"] == "pending_job_search_salary_min"
    assert state["years_of_experience"] == 3.5


# --- handle_job_search_salary_min_step / handle_job_search_salary_max_step（FR-36）---


def _advance_to_salary_min(fake_db, state_store, telegram_user_id=999):
    _advance_to_years_experience(fake_db, state_store, telegram_user_id)
    commands.handle_job_search_years_experience_step(state_store, telegram_user_id, "3.5")


def test_handle_job_search_salary_min_step_invalid_reprompts(fake_db):
    state_store = ConversationStateStore()
    _advance_to_salary_min(fake_db, state_store)

    reply = commands.handle_job_search_salary_min_step(state_store, 999, "很多")

    assert "沒看懂" in reply
    assert state_store.get(999)["flow"] == "pending_job_search_salary_min"


def test_handle_job_search_salary_min_step_valid_moves_to_salary_max(fake_db):
    state_store = ConversationStateStore()
    _advance_to_salary_min(fake_db, state_store)

    reply = commands.handle_job_search_salary_min_step(state_store, 999, "50000")

    assert "薪資上限" in reply
    state = state_store.get(999)
    assert state["flow"] == "pending_job_search_salary_max"
    assert state["expected_salary_min"] == 50000


def _advance_to_salary_max(fake_db, state_store, telegram_user_id=999):
    _advance_to_salary_min(fake_db, state_store, telegram_user_id)
    commands.handle_job_search_salary_min_step(state_store, telegram_user_id, "50000")


def test_handle_job_search_salary_max_step_invalid_reprompts(fake_db):
    state_store = ConversationStateStore()
    _advance_to_salary_max(fake_db, state_store)

    reply = commands.handle_job_search_salary_max_step(fake_db, state_store, 999, "很多")

    assert "沒看懂" in reply
    assert state_store.get(999)["flow"] == "pending_job_search_salary_max"


def test_handle_job_search_salary_max_step_lower_than_min_reprompts(fake_db):
    state_store = ConversationStateStore()
    _advance_to_salary_max(fake_db, state_store)

    reply = commands.handle_job_search_salary_max_step(fake_db, state_store, 999, "40000")

    assert "還低耶" in reply
    assert state_store.get(999)["flow"] == "pending_job_search_salary_max"


def test_handle_job_search_salary_max_step_saves_criteria_and_profile(fake_db):
    """走一次完整流程（FR-33 搜尋條件 + FR-36 履歷/期望工作/年資/期望薪資），驗證最後一步一次寫入
    `job_search_criteria` 與 `users`。"""
    state_store = ConversationStateStore()
    user_id = _seed_owner(fake_db)
    commands.start_job_search_setup(state_store, 998, user_id)
    commands.handle_job_search_criteria_step(_FakeLLMClient(_CRITERIA_CLEAR), state_store, 998, "AI 相關")
    commands.handle_job_search_ready_confirm_step(_FakeLLMClient("CONFIRM"), state_store, 998, "好了")
    commands.handle_job_search_resume_step(state_store, 998, "五年後端開發經驗")
    commands.handle_job_search_resume_confirm_step(_FakeLLMClient("CONFIRM"), state_store, 998, "沒有")
    commands.handle_job_search_expectation_step(state_store, 998, "希望能遠端工作")
    commands.handle_job_search_expectation_confirm_step(_FakeLLMClient("CONFIRM"), state_store, 998, "沒有")
    commands.handle_job_search_years_experience_step(state_store, 998, "3.5")
    commands.handle_job_search_salary_min_step(state_store, 998, "50000")

    reply = commands.handle_job_search_salary_max_step(fake_db, state_store, 998, "70000")

    assert "已經幫你記錄好求職資料" in reply
    assert state_store.get(998) is None

    criteria_rows = fake_db.select("job_search_criteria", where="user_id = %s", params=(user_id,))
    assert len(criteria_rows) == 1
    assert criteria_rows[0]["keyword"] == "AI 工程師"

    user_row = fake_db.select("users", where="id = %s", params=(user_id,), fetch_one=True)
    assert user_row["job_resume"] == "五年後端開發經驗"
    assert user_row["job_expectation"] == "希望能遠端工作"
    assert user_row["years_of_experience"] == 3.5
    assert user_row["expected_salary_min"] == 50000
    assert user_row["expected_salary_max"] == 70000


# --- handle_company_csv_uploaded（FR-35e）---


def test_handle_company_csv_uploaded_file_not_found(fake_db):
    gdrive_client = _FakeGDriveClient(files={})

    reply = commands.handle_company_csv_uploaded(fake_db, gdrive_client, "2026-08-09-104職缺公司.csv")

    assert "找不到" in reply


def test_handle_company_csv_uploaded_applies_backgrounds_and_reports_success(fake_db):
    fake_db.insert(
        "job_companies", {"company_id_104": "100", "company_name": "A 公司", "region": "台北市", "background": None}
    )
    csv_bytes = "104公司ID,公司全名,地區,產業類型,背景\n100,A 公司,台北市,軟體業,做電商平台的新創\n".encode(
        "utf-8-sig"
    )
    gdrive_client = _FakeGDriveClient(files={"2026-08-09-104職缺公司.csv": csv_bytes})

    reply = commands.handle_company_csv_uploaded(fake_db, gdrive_client, "2026-08-09-104職缺公司.csv")

    assert "1 家公司" in reply
    row = fake_db.select("job_companies", where="company_id_104 = %s", params=("100",), fetch_one=True)
    assert row["background"] == "做電商平台的新創"


def test_handle_company_csv_uploaded_reports_not_found_ids(fake_db):
    csv_bytes = "104公司ID,公司全名,地區,產業類型,背景\n999,不存在的公司,台北市,軟體業,某個背景\n".encode(
        "utf-8-sig"
    )
    gdrive_client = _FakeGDriveClient(files={"2026-08-09-104職缺公司.csv": csv_bytes})

    reply = commands.handle_company_csv_uploaded(fake_db, gdrive_client, "2026-08-09-104職缺公司.csv")

    assert "0 家公司" in reply
    assert "999" in reply
    assert "人工確認" in reply


# --- handle_job_recommendation_excel_uploaded（Step 4.2，FR-38e）---


def _build_recommendation_xlsx(rows):
    import io

    import openpyxl

    workbook = openpyxl.Workbook()
    workbook.active.title = "所有職缺推薦"
    header = ["104公司ID", "公司全名", "地區", "產業類型", "職缺", "評分", "排名", "推薦原因", "連結", "是否喜歡"]
    workbook.active.append(header)
    for row in rows:
        workbook.active.append(row)
    workbook.create_sheet("最新職缺推薦").append(header)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_handle_job_recommendation_excel_uploaded_file_not_found(fake_db):
    gdrive_client = _FakeGDriveClient(files={})

    reply = commands.handle_job_recommendation_excel_uploaded(fake_db, gdrive_client, "2026-08-09-104職缺推薦.xlsx")

    assert "找不到" in reply


def test_handle_job_recommendation_excel_uploaded_applies_preferences_and_reports_success(fake_db):
    fake_db.insert(
        "job_postings",
        {
            "job_id_104": "1", "company_id_104": "100", "title": "AI 工程師", "region": "台北市",
            "url": "https://www.104.com.tw/job/1", "is_unliked": False,
        },
    )
    xlsx_bytes = _build_recommendation_xlsx(
        [["100", "A 公司", "台北市", "軟體業", "AI 工程師", 90.0, 1, "很符合", "https://www.104.com.tw/job/1", "1"]]
    )
    gdrive_client = _FakeGDriveClient(files={"2026-08-09-104職缺推薦.xlsx": xlsx_bytes})

    reply = commands.handle_job_recommendation_excel_uploaded(fake_db, gdrive_client, "2026-08-09-104職缺推薦.xlsx")

    assert "1 筆職缺" in reply
    row = fake_db.select("job_postings", where="job_id_104 = %s", params=("1",), fetch_one=True)
    assert row["is_unliked"] is True


def test_handle_job_recommendation_excel_uploaded_reports_not_found_urls(fake_db):
    xlsx_bytes = _build_recommendation_xlsx(
        [["999", "不存在的公司", "台北市", "軟體業", "不存在的職缺", 50.0, 1, "原因",
          "https://www.104.com.tw/job/999", "1"]]
    )
    gdrive_client = _FakeGDriveClient(files={"2026-08-09-104職缺推薦.xlsx": xlsx_bytes})

    reply = commands.handle_job_recommendation_excel_uploaded(fake_db, gdrive_client, "2026-08-09-104職缺推薦.xlsx")

    assert "0 筆職缺" in reply
    assert "https://www.104.com.tw/job/999" in reply
    assert "人工確認" in reply
