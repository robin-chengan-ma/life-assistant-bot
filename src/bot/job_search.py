"""求職模組商業邏輯（Step 4.1，見 docs/specs/robinson/SPEC.md FR-33～FR-36，ADR-24）。

僅 Robin 一人可用（`job_search` 開關於 Step 4.1 改為 `owner_only=True`，見 ADR-24 決策 2），
所以本模組不像 `finance.py`／`body.py` 需要處理多使用者並行的複雜度。涵蓋 FR-33（搜尋條件）、
FR-34（兩階段爬蟲＋ETL 去重，呼叫 `submodules/job104` 拿資料）、FR-36（履歷／期望工作敘述／
結構化年資與期望薪資）；FR-35（公司背景 Email 協作）見本檔案下方區塊。
"""
import csv
import io
import random
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.bot import toggles
from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")

_FEATURE_KEY = "job_search"

# FR-34b：每週僅執行一次，固定台灣時間週一 08:00（Robin 2026-08-09 確認，比照 YouTube 模組
# 每週四 08:00 的既有慣例，見 youtube.py `_PUSH_WEEKDAY_THURSDAY`）。
_WEEKLY_CRAWL_WEEKDAY = 0  # Python datetime.weekday()：Monday=0
_WEEKLY_CRAWL_HOUR = 8

# FR-36：履歷與期望工作敘述皆為「3500 字以內」，兩者上限相同。
_MAX_TEXT_LENGTH = 3500

# FR-36：年資（`years_of_experience`）合理範圍，0～60 年已足夠涵蓋所有實際情境，避免使用者
# 誤植成月份數字（例如打「36」代表 3 年又半，這裡不猜測，一律要求使用者輸入年為單位的數字）。
_MIN_YEARS_OF_EXPERIENCE = 0
_MAX_YEARS_OF_EXPERIENCE = 60

# FR-34c：列表分頁／詳情頁請求之間強制 2～4 秒隨機延遲，嚴禁併發多執行緒請求。
_MIN_DELAY_SECONDS = 2
_MAX_DELAY_SECONDS = 4

# 安全防呆（非 spec 硬性規定）：避免 104 因未知原因對某組條件一直回傳非空清單時無限迴圈，
# 20 頁（每頁通常 20 筆，約 400 筆）已遠超過個人使用情境下單一搜尋條件實際會出現的職缺量。
_MAX_PAGES_PER_CRITERIA = 20


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
) -> int:
    """新增一組求職搜尋條件（FR-33），回傳新建列的 id。

    ADR-24 決策 3：允許同時存多組條件，不比照記帳預算/證照目標「一人一份、重新設定即覆蓋」的
    既有慣例，這裡固定用 INSERT 新增一筆，不會動到既有的其他組條件。

    2026-08-09 依 Robin 指示移除產業篩選（`industry`）——104 實測驗證後發現這個維度不值得繼續
    猜測參數名稱。`job_search_criteria.industry` 欄位保留在資料庫（不做 migration 刪除，避免
    非必要的破壞性操作），只是往後一律不再寫入、也不再從對話流程收集。
    """
    return db.insert(
        "job_search_criteria",
        {
            "user_id": user_id,
            "keyword": keyword,
            "region": region,
            "salary_min": salary_min,
            "salary_max": salary_max,
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


# --- FR-34：104 職缺爬蟲（兩階段架構＋ETL 去重）---


def _now() -> datetime:
    """回傳現在的台灣時間；獨立成函式方便測試用 monkeypatch 固定時間點。"""
    return datetime.now(_TAIWAN_TZ)


def list_search_criteria(db: CloudSQLClient, user_id: int) -> list[dict]:
    """查詢使用者目前設定的所有求職搜尋條件（FR-33），供 FR-34 週排程逐組送出查詢。"""
    return db.select("job_search_criteria", where="user_id = %s", params=(user_id,))


def _polite_delay(sleep_func, random_func) -> None:
    """FR-34c：每次對 104 發出請求後呼叫一次，強制 2～4 秒隨機延遲才能發下一次請求。"""
    sleep_func(random_func(_MIN_DELAY_SECONDS, _MAX_DELAY_SECONDS))


def upsert_company(
    db: CloudSQLClient, company_id_104: str, company_name: str, region: str, industry: str | None = None
) -> tuple[int, bool]:
    """FR-35a：找出這批職缺所屬公司是否已存在資料庫（以 104 公司 ID 判斷），不存在才新增
    （`background` 留空，代表尚待 Robin 人工回填）；已存在則完全不覆蓋既有欄位（避免蓋掉已經
    回填好的背景資料或更新過的公司資訊）。回傳 `(job_companies.id, 是否為新公司)`。
    """
    existing = db.select("job_companies", where="company_id_104 = %s", params=(company_id_104,), fetch_one=True)
    if existing is not None:
        return existing["id"], False

    new_id = db.insert(
        "job_companies",
        {
            "company_id_104": company_id_104,
            "company_name": company_name,
            "region": region,
            "industry": industry,
            "background": None,
        },
    )
    return new_id, True


def upsert_job_posting(db: CloudSQLClient, job: dict, detail: dict, now: datetime) -> bool:
    """FR-34d ETL 去重：以 `job_id_104` 為鍵值，已存在就 `UPDATE`（薪資/內容等可能隨時間變動的
    欄位＋`last_crawled_at`），不存在才 `INSERT` 新增一筆（`first_seen_at` 只在新增當下寫入一次，
    供 FR-38a「本週新職缺排名」判斷依據，之後每次重新爬到都不會再變動）。回傳「是否為新職缺」。

    薪資（`salary_min`／`salary_max`）目前不寫入——104 列表/詳情 API 的薪資描述格式尚未經過
    真實流量驗證（見 `submodules/job104/client.py` 模組 docstring），與其現在用不確定的規則
    猜測解析成數字區間，不如先讓這兩欄維持 `NULL`，待實測結果出爐後再補上解析邏輯，符合 ADR-24
    決策 4「先保守假設、之後視實測結果調整」的一貫做法。

    應徵人數（`applicant_count`）取自 `job`（列表階段的 `search_list()` 結果），不是
    `detail`（詳情頁 API 已確認沒有這個欄位，2026-08-09 實測驗證，見 `submodules/job104/
    client.py` 模組 docstring）。

    是否已關閉（`is_closed`）同樣取自 `job`（`search_list()` 依 `jobSwitch` 欄位自動判斷，
    2026-08-09 實測驗證確認可行，見 ADR-26 決策 5）；已存在的職缺重新爬到時一併更新這個
    欄位，職缺重新開放/關閉的狀態變化才能反映到資料庫，不會卡在第一次爬到時的舊狀態。
    """
    existing = db.select("job_postings", where="job_id_104 = %s", params=(job["job_id"],), fetch_one=True)
    fields = {
        "company_id_104": job["company_id"],
        "title": job["title"],
        "region": job["region"],
        "url": job["url"],
        "content": detail.get("content"),
        "required_years_experience": detail.get("required_years_experience"),
        "applicant_count": job.get("applicant_count"),
        "source_updated_at": detail.get("source_updated_at"),
        "is_closed": job.get("is_closed", False),
        "last_crawled_at": now,
    }
    if existing is not None:
        db.update("job_postings", fields, where="job_id_104 = %s", params=(job["job_id"],))
        return False

    db.insert("job_postings", {**fields, "job_id_104": job["job_id"], "first_seen_at": now})
    return True


def crawl_and_upsert_jobs(
    db: CloudSQLClient,
    job104_client,
    user_id: int,
    sleep_func=time.sleep,
    random_func=random.uniform,
    now: datetime | None = None,
) -> dict:
    """FR-34：對這位使用者目前設定的每一組搜尋條件（FR-33），依 FR-34a 兩階段架構爬取職缺——
    先呼叫列表 API 依條件取得摘要清單，再對清單內每一筆職缺 ID 個別呼叫詳情頁補齊完整內容。
    FR-34c 的 2～4 秒隨機延遲套用在**每一次**對 104 發出的請求之後（不論列表分頁或詳情頁），
    確保連續兩次請求之間一定間隔至少 2 秒；FR-34c 嚴禁併發，本函式全程單執行緒依序呼叫，
    天生滿足這個限制，不需要額外的鎖或旗標。FR-34d 的 ETL 去重見 `upsert_job_posting()`。

    列表 API 回傳空清單（含翻到最後一頁之後）視為這組條件已經爬完，換下一組條件；單組條件
    最多翻 `_MAX_PAGES_PER_CRITERIA` 頁（安全防呆，非 spec 硬性規定，見該常數說明）。

    地區篩選（`criteria["region"]`）2026-08-09 起改為**呼叫端自行做子字串比對篩選**，不送給
    104 API——104 的 `area` 參數要傳它自己的地區數字代碼，不是使用者輸入的地區文字，沒有可靠
    對照表（見 `submodules/job104/client.py` 模組 docstring）。分頁停止判斷仍然依據**未篩選**
    的原始清單是否為空（`jobs`），不是篩選後的 `matching_jobs`——避免某一頁剛好篩不到符合地區
    的職缺，就誤判成「這組條件已經爬完」而提早停止翻頁。

    回傳這次爬蟲的統計摘要：`{"new_company_ids": [...], "new_job_count": int,
    "updated_job_count": int}`；`new_company_ids` 供 FR-35a 判斷這批職缺所屬公司是否需要
    走 Email/CSV/Drive 協作流程（見 `build_new_companies_csv()`）。
    """
    now = now or _now()
    criteria_list = list_search_criteria(db, user_id)

    new_company_ids: list[str] = []
    new_job_count = 0
    updated_job_count = 0

    for criteria in criteria_list:
        region_filter = criteria.get("region")
        page = 1
        while page <= _MAX_PAGES_PER_CRITERIA:
            jobs = job104_client.search_list(
                criteria["keyword"],
                salary_min=criteria.get("salary_min"),
                salary_max=criteria.get("salary_max"),
                page=page,
            )
            _polite_delay(sleep_func, random_func)
            if not jobs:
                break

            matching_jobs = [j for j in jobs if not region_filter or region_filter in (j.get("region") or "")]
            for job in matching_jobs:
                _, is_new_company = upsert_company(db, job["company_id"], job["company_name"], job["region"])
                if is_new_company and job["company_id"] not in new_company_ids:
                    new_company_ids.append(job["company_id"])

                detail = job104_client.fetch_job_detail(job["job_slug"])
                _polite_delay(sleep_func, random_func)

                if upsert_job_posting(db, job, detail, now):
                    new_job_count += 1
                else:
                    updated_job_count += 1

            page += 1

    return {
        "new_company_ids": new_company_ids,
        "new_job_count": new_job_count,
        "updated_job_count": updated_job_count,
    }


# --- FR-35：公司背景 Email／CSV／Drive 人力協作機制（見 ADR-24 決策 1）---

_COMPANY_CSV_HEADER = ["104公司ID", "公司全名", "地區", "產業類型", "背景"]
_COMPANY_CSV_FILENAME_SUFFIX = "-104職缺公司.csv"

# FR-35b：固定信件標題／內文文案（Robin 已核准的措辭，比照 templates.py 靜態文案不經 LLM 生成）。
EMAIL_SUBJECT_TEMPLATE = "{date} 排程 - Robinson 104 職缺公司列表"
EMAIL_BODY_TEXT = "附件為本週爬到的最新公司列表，請參閱！"

# FR-35c：寄信成功後私訊 Robin 的固定文案（FR-19h 決策執行狀態閉環回饋）。
EMAIL_SENT_NOTIFICATION_TEXT = "已經寄送本週最新的104職缺公司信件給您了～"


def company_csv_filename(target_date: date) -> str:
    """FR-35b：組出公司背景 CSV 的固定檔名格式 `{YYYY-MM-DD}-104職缺公司.csv`。"""
    return f"{target_date.isoformat()}{_COMPANY_CSV_FILENAME_SUFFIX}"


def get_companies_by_ids(db: CloudSQLClient, company_ids: list[str]) -> list[dict]:
    """依 104 公司 ID 清單查出對應的 `job_companies` 資料列，供 FR-35b 組 CSV 使用。

    逐一查詢再彙整，不做一次性的 `IN` 查詢——個人使用情境下單週新公司數量不會太多，不需要
    為此另外設計 `FakeCloudSQLClient`／正式 `CloudSQLClient` 都要支援的批次查詢介面。
    """
    rows = []
    for company_id in company_ids:
        row = db.select("job_companies", where="company_id_104 = %s", params=(company_id,), fetch_one=True)
        if row is not None:
            rows.append(row)
    return rows


def build_new_companies_csv(companies: list[dict]) -> str:
    """FR-35b：組出待 Robin 查詢回填的新公司 CSV 內容（欄位：104公司ID／公司全名／地區／
    產業類型／背景）。用標準函式庫 `csv` module，不額外安裝第三方套件（比照
    `submodules/newsfeed` 用標準函式庫解析 RSS 而不裝 `feedparser` 的既有慣例，見 ADR-24
    後果）。「背景」欄位固定留空字串，等 Robin 查完手動填入。
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_COMPANY_CSV_HEADER)
    for company in companies:
        writer.writerow(
            [
                company["company_id_104"],
                company["company_name"],
                company.get("region") or "",
                company.get("industry") or "",
                "",
            ]
        )
    return buffer.getvalue()


def send_new_companies_email(email_client, to: str, target_date: date, csv_text: str) -> None:
    """FR-35b：把公司背景 CSV 當附件寄給 Robin 自己（`GMAIL_USER` 自寄自收）。"""
    email_client.send_text_with_attachment(
        to=to,
        subject=EMAIL_SUBJECT_TEMPLATE.format(date=target_date.isoformat()),
        body=EMAIL_BODY_TEXT,
        attachment_filename=company_csv_filename(target_date),
        attachment_bytes=csv_text.encode("utf-8-sig"),  # BOM：Excel 開啟中文 CSV 不亂碼
    )


def parse_companies_csv(csv_text: str) -> list[dict]:
    """FR-35e：解析 Robin 回填好的公司背景 CSV，回傳 `[{"company_id_104", "background"}, ...]`。

    「104公司ID」或「背景」任一欄位為空的列直接跳過（分別代表格式異常、或 Robin 還沒查完
    這家公司），不會把空字串誤當成「已確認查無資料」寫回資料庫覆蓋掉未來可能補上的內容。
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    entries = []
    for row in reader:
        company_id = (row.get("104公司ID") or "").strip()
        background = (row.get("背景") or "").strip()
        if not company_id or not background:
            continue
        entries.append({"company_id_104": company_id, "background": background})
    return entries


def apply_company_backgrounds(db: CloudSQLClient, entries: list[dict]) -> dict:
    """FR-35e：把解析出的背景逐筆 `UPDATE` 回 `job_companies`（以 104 公司 ID 比對）。

    回傳 `{"updated_count": int, "not_found_ids": [...]}`；比對不到對應公司的 ID 一律列出來，
    不可靜默略過（比照 FR-38e「找不到對應職缺就列出來提醒人工處理」的一貫做法）。
    """
    updated_count = 0
    not_found_ids: list[str] = []
    for entry in entries:
        affected = db.update(
            "job_companies",
            {"background": entry["background"]},
            where="company_id_104 = %s",
            params=(entry["company_id_104"],),
        )
        if affected:
            updated_count += 1
        else:
            not_found_ids.append(entry["company_id_104"])
    return {"updated_count": updated_count, "not_found_ids": not_found_ids}


# --- 每週排程整合入口（FR-34b、FR-35a～FR-35c）---


def check_and_run_weekly_job_search(
    db: CloudSQLClient,
    job104_client,
    email_client,
    gmail_user: str,
    telegram_client,
    now: datetime | None = None,
) -> None:
    """`/healthz` 每 10 分鐘觸發一次的其中一項排程檢查，固定台灣時間週一 08:00 這個小時內執行，
    同一天最多執行一次（`users.job_search_last_run_on` 去重，比照 `youtube_last_run_on`／
    `toeic_pipeline_last_run_on` 既有慣例）；`job_search` 功能開關關閉時跳過，不消耗任何額度。

    流程：
    1. 呼叫 `crawl_and_upsert_jobs()` 依 FR-33 各組搜尋條件爬取職缺（FR-34a～FR-34d）
    2. FR-35a：若這批職缺涉及資料庫裡還沒有背景資料的新公司（`new_company_ids` 非空），
       組 CSV 寄信給 Robin（FR-35b）、寄信成功後私訊告知（FR-35c）；若沒有新公司，
       這一步整段跳過，不寄信也不通知
    3. 更新 `job_search_last_run_on` 去重欄位

    執行過程若拋出例外，記錄警告日誌並優雅結束，不影響 `/healthz`（呼叫端 `main.py` 已經包了
    一層 try/except，這裡不重複再包，維持跟其餘 `check_and_push_*` 函式一致的分工：本函式只
    負責業務邏輯本身）。
    """
    now_local = now or _now()
    if now_local.weekday() != _WEEKLY_CRAWL_WEEKDAY or now_local.hour != _WEEKLY_CRAWL_HOUR:
        return

    owner = db.select("users", where="is_owner = %s", params=(True,), fetch_one=True)
    if owner is None:
        return
    if not toggles.is_feature_enabled(db, owner["id"], _FEATURE_KEY):
        return

    today = now_local.date()
    if owner.get("job_search_last_run_on") == today:
        return

    result = crawl_and_upsert_jobs(db, job104_client, owner["id"], now=now_local)

    if result["new_company_ids"]:
        companies = get_companies_by_ids(db, result["new_company_ids"])
        csv_text = build_new_companies_csv(companies)
        send_new_companies_email(email_client, gmail_user, today, csv_text)
        telegram_client.send_text(chat_id=owner["telegram_user_id"], text=EMAIL_SENT_NOTIFICATION_TEXT)

    db.update("users", {"job_search_last_run_on": today}, where="id = %s", params=(owner["id"],))
