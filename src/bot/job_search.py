"""求職模組商業邏輯（Step 4.1，見 docs/specs/robinson/SPEC.md FR-33、FR-36，ADR-24）。

僅 Robin 一人可用（`job_search` 開關於 Step 4.1 改為 `owner_only=True`，見 ADR-24 決策 2），
所以本模組不像 `finance.py`／`body.py` 需要處理多使用者並行的複雜度。目前只涵蓋 FR-33
（搜尋條件）與 FR-36（履歷／期望工作敘述／結構化年資與期望薪資）的資料存取；FR-34（爬蟲）、
FR-35（公司背景 Email 協作）留待後續 commit 擴充，見 `docs/specs/robinson/PROGRESS.md`。
"""
from submodules.cloudsql.client import CloudSQLClient

# FR-36：履歷與期望工作敘述皆為「3500 字以內」，兩者上限相同。
_MAX_TEXT_LENGTH = 3500

# FR-36：年資（`years_of_experience`）合理範圍，0～60 年已足夠涵蓋所有實際情境，避免使用者
# 誤植成月份數字（例如打「36」代表 3 年又半，這裡不猜測，一律要求使用者輸入年為單位的數字）。
_MIN_YEARS_OF_EXPERIENCE = 0
_MAX_YEARS_OF_EXPERIENCE = 60


def is_text_length_valid(text: str) -> bool:
    """FR-36：履歷／期望工作敘述皆不可超過 3500 字。"""
    return len(text) <= _MAX_TEXT_LENGTH


def is_years_of_experience_reasonable(years: float) -> bool:
    """FR-36：年資合理範圍檢查，0～60 年。"""
    return _MIN_YEARS_OF_EXPERIENCE <= years <= _MAX_YEARS_OF_EXPERIENCE


def save_search_criteria(
    db: CloudSQLClient,
    user_id: int,
    keyword: str,
    region: str | None,
    salary_min: int | None,
    salary_max: int | None,
    industry: str | None,
) -> int:
    """新增一組求職搜尋條件（FR-33），回傳新建列的 id。

    ADR-24 決策 3：允許同時存多組條件，不比照記帳預算/證照目標「一人一份、重新設定即覆蓋」的
    既有慣例，這裡固定用 INSERT 新增一筆，不會動到既有的其他組條件。
    """
    return db.insert(
        "job_search_criteria",
        {
            "user_id": user_id,
            "keyword": keyword,
            "region": region,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "industry": industry,
        },
    )


def save_profile(
    db: CloudSQLClient,
    user_id: int,
    resume: str,
    expectation: str,
    years_of_experience: float,
    expected_salary_min: int,
    expected_salary_max: int,
) -> None:
    """寫入使用者履歷／期望工作敘述／結構化年資與期望薪資（FR-36）。

    這五個欄位一次一起寫入（收集流程走到最後一步才呼叫，見 `src/bot/commands.py`
    `handle_job_search_salary_max_step`），不提供只更新部分欄位的介面——FR-36 的設計就是
    一輪完整對話收集齊全，重新執行整個 `/set_job_search` 流程即可覆蓋更新。
    """
    db.update(
        "users",
        {
            "job_resume": resume,
            "job_expectation": expectation,
            "years_of_experience": years_of_experience,
            "expected_salary_min": expected_salary_min,
            "expected_salary_max": expected_salary_max,
        },
        where="id = %s",
        params=(user_id,),
    )
