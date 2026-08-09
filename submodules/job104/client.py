"""104 人力銀行公開 AJAX API 通用 Client：無登入態直接呼叫 104 官網前端本身使用的職缺搜尋/詳情
JSON API，不使用瀏覽器自動化工具（Playwright/Selenium），輕量且高執行效能（見
docs/specs/robinson/SPEC.md FR-34a、ADR-24 決策 4）。

**驗證狀態（2026-08-09 更新）**：104 沒有公開正式文件化的 Open API。Cowork sandbox 無法連線
104.com.tw（見專案 memory「Sandbox network limits」），所以改由 Robin 透過瀏覽器 DevTools
Network 面板手動抓真實請求驗證，已確認：
- 列表 API 端點實際是 `https://www.104.com.tw/jobs/search/api/jobs`（不是先前猜測的
  `/jobs/search/list`，那個網址現在回傳的是 SPA 頁面 HTML，不是 JSON）；回應結構是
  `{"data": [...]}`，`data` 本身直接是職缺陣列（不是先前猜測的 `data.list`）。
- 詳情 API 端點實際是 `https://www.104.com.tw/api/jobs/{短代碼}`，這個短代碼是職缺網址
  （`link.job`）結尾那段（例如 `https://www.104.com.tw/job/94bow` → `94bow`），跟列表 API
  另外給的 `jobNo`（數字型 ID，例如 `15318320`）是**兩個不同的識別碼**——`jobNo` 拿來當資料庫
  去重鍵值（`job_id_104`），短代碼只用來組詳情 API 網址，不可混用。
- `jobName`／`custNo`／`custName`／`jobAddrNoDesc`／`jobDetail.jobDescription`／
  `condition.workExp`／`welfare.welfare` 這幾個欄位名稱原本的猜測全部正確。
- 應徵人數（`applyCnt`）其實列表 API 那頁就有了，不需要等詳情頁——`fetch_job_detail()` 已把
  這個欄位移除，改由 `search_list()` 直接回傳。
- 職缺是否已關閉可自動判斷：列表 API 每筆職缺物件都有 `jobSwitch` 欄位（`"on"` 代表開放中），
  已解決 ADR-26 決策 5 原本懸而未決的問題（不需要如原訂備案走人工 Excel 標記），`search_list()`
  已回傳 `is_closed`。目前樣本裡所有職缺都是 `"on"`，尚未見過「已關閉」實際會顯示的值，保守
  採「非 `"on"` 才算關閉」的判斷邏輯（見 `_is_job_closed()`）。

**地區／產業篩選（2026-08-09 追加澄清）**：Robin 後續補充實測過的地區篩選網址，確認 `area`
參數名稱本身正確，但值是 104 自己的地區數字代碼（例如 `"6001008000"`），不是使用者輸入的地區
文字；由於沒有可靠的代碼對照表，`search_list()` 已不再接受 `region` 參數，改由呼叫端用回傳
結果的 `region`（`jobAddrNoDesc`）文字做子字串比對篩選（見 `search_list()` docstring）。產業
篩選（`industry`）依 Robin 指示直接移除，`search_list()` 已不再接受這個參數。薪資篩選則確認
除了 `scmin`／`scmax` 外還需要帶 `sctp="M"`（薪資類型：月薪）、`scstrict=1`、`scneg=1` 篩選
才會真的套用。

對外暴露 `search_list()`（職缺列表，一次一頁）與 `fetch_job_detail()`（單一職缺詳情，FR-34a
兩階段架構的第二階段）。UA／Referer 標頭固定套用（模擬瀏覽器請求，降低被擋機率），但請求節奏
（FR-34c 的 2～4 秒隨機延遲、禁併發、分頁停止時機）刻意不內建在這裡，由呼叫端
（`src/bot/job_search.py` 的 `crawl_and_upsert_jobs()`）控制——本模組只負責「單次 HTTP 請求
本身」，維持跟 `submodules/newsfeed`（RSS 抓取）一樣的最小職責。
"""
import re

import requests

from submodules.retry.client import call_with_retry

_LIST_API_URL = "https://www.104.com.tw/jobs/search/api/jobs"
_DETAIL_API_URL_TEMPLATE = "https://www.104.com.tw/api/jobs/{job_slug}"
_LIST_PAGE_SIZE = 20
_SALARY_TYPE_MONTHLY = "M"
_SEARCH_PAGE_REFERER = "https://www.104.com.tw/jobs/search/"
_BASE_URL = "https://www.104.com.tw"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_DEFAULT_TIMEOUT_SECONDS = 10

# 2026-08-09：外部 API 重試機制（見 docs/specs/robinson/SPEC.md FR-19i）。只重試「暫時性錯誤」：
# 連線失敗/逾時與 HTTP 429／5xx；其餘 4xx（例如職缺已下架的 404）重試也沒用，直接往外拋，
# 交由呼叫端（`job_search.crawl_and_upsert_jobs()`）決定要不要跳過這筆繼續爬下一筆。
_RETRYABLE_HTTP_STATUS_MIN = 500
_RETRYABLE_RATE_LIMIT_STATUS = 429

_YEARS_PATTERN = re.compile(r"(\d+(?:\.\d+)?)")


def _is_retryable_requests_error(exc: Exception) -> bool:
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code is None:
            return False
        return status_code == _RETRYABLE_RATE_LIMIT_STATUS or status_code >= _RETRYABLE_HTTP_STATUS_MIN
    return False


def _headers(referer: str) -> dict:
    return {"User-Agent": _USER_AGENT, "Referer": referer, "Accept": "application/json"}


def _normalize_url(raw_url: str) -> str:
    """把可能是相對路徑的職缺連結換算成完整網址；已經是完整網址就原樣回傳。104 實測回應的
    `link.job` 其實本來就是完整網址，這裡繼續保留只是當一層防呆，避免哪天格式又變回相對路徑。"""
    if not raw_url:
        return ""
    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url
    return _BASE_URL + (raw_url if raw_url.startswith("/") else f"/{raw_url}")


def _extract_job_slug(url: str) -> str:
    """從職缺網址擷取結尾短代碼（例如 `https://www.104.com.tw/job/94bow` → `"94bow"`），
    這個短代碼才是 `fetch_job_detail()` 真正呼叫詳情頁 API 要用的 ID，跟 `jobNo`（列表 API
    另一個數字型 ID，用於資料庫去重鍵值 `job_id_104`）是兩個不同的識別碼，不可混用（2026-08-09
    依 Robin 實測驗證確認，見本檔案模組 docstring）。"""
    if not url:
        return ""
    return url.rstrip("/").rsplit("/", 1)[-1]


def _normalize_appear_date(raw: str | None) -> str | None:
    """104 詳情頁 API 的 `appearDate` 是 `"YYYY/MM/DD"` 格式，統一轉成 ISO `"YYYY-MM-DD"`
    格式方便寫入 `job_postings.source_updated_at`（`TIMESTAMPTZ` 欄位）。"""
    if not raw:
        return None
    return raw.replace("/", "-")


def _is_job_closed(raw_switch: str | None) -> bool:
    """依 104 API 的 `jobSwitch`（列表）／`switch`（詳情）欄位判斷職缺是否已關閉（2026-08-09
    實測驗證確認 `"on"` 代表開放中）。欄位缺失一律視為「未關閉」（回傳 `False`），避免因為
    解析不到就誤判成已關閉——沒有實際樣本能確認「已關閉」時這個欄位真正的值是什麼，只確認
    `"on"` 是「開放中」，所以用排除法（非 `"on"` 才算關閉），不是白名單比對「已知的關閉值」。
    """
    if not raw_switch:
        return False
    return raw_switch != "on"


def _parse_years(raw: str | None) -> float | None:
    """從 104 常見的「N年以上」／「不拘」等年資要求文字擷取數字；擷取不到（含「不拘」這種
    沒有數字的情況）回傳 `None`，交由呼叫端視為「這個維度略過」（FR-37b）。"""
    if not raw:
        return None
    match = _YEARS_PATTERN.search(raw)
    if not match:
        return None
    return float(match.group(1))


class Job104Client:
    """封裝 104 公開職缺搜尋/詳情 AJAX API 的最小 Client（無登入態，僅支援唯讀查詢）。"""

    def search_list(
        self,
        keyword: str,
        salary_min: int | None = None,
        salary_max: int | None = None,
        page: int = 1,
    ) -> list[dict]:
        """查詢職缺搜尋列表第 `page` 頁（FR-34a 兩階段架構第一階段），回傳摘要清單：
        `[{"job_id", "job_slug", "title", "company_id", "company_name", "region", "url",
        "applicant_count", "is_closed"}, ...]`；查無結果（含翻到最後一頁之後）回傳空清單，
        由呼叫端依此判斷分頁何時停止。`job_id`（`jobNo`）供資料庫去重鍵值使用；`job_slug`
        才是 `fetch_job_detail()` 要傳入的 ID，兩者不可混用。`is_closed` 依 `jobSwitch`
        欄位判斷（見 `_is_job_closed()`，2026-08-09 實測驗證確認可自動判斷，見 ADR-26 決策 5）。

        **不接受 `region`／`industry` 參數**（2026-08-09 依 Robin 指示調整）：`area` 這個地區
        篩選參數名稱本身已確認正確，但實際要傳 104 自己的地區數字代碼（例如 `"6001008000"`），
        不是使用者輸入的地區文字（例如「台北市」），目前沒有可靠的代碼對照表，與其送出猜測的
        代碼冒著篩選失效或篩選錯誤的風險，不如乾脆不送，改由呼叫端（`src/bot/job_search.py`
        的 `crawl_and_upsert_jobs()`）用回傳結果的 `region` 文字做關鍵字比對篩選（見該函式
        docstring）。產業篩選（`industry`）則依 Robin 指示直接移除，不再是這個模組的功能範圍。
        """
        params: dict = {
            "keyword": keyword,
            "page": page,
            "pagesize": _LIST_PAGE_SIZE,
            "mode": "s",
            "jobsource": "joblist_search",
            "searchJobs": 1,
        }
        # 薪資篩選確認除了 scmin/scmax 外，還需要 sctp（薪資類型，固定用月薪）＋
        # scstrict／scneg 這兩個旗標，篩選才會真的套用（2026-08-09 實測驗證）。
        if salary_min:
            params["scmin"] = salary_min
        if salary_max:
            params["scmax"] = salary_max
        if salary_min or salary_max:
            params["sctp"] = _SALARY_TYPE_MONTHLY
            params["scstrict"] = 1
            params["scneg"] = 1

        def _do_fetch() -> dict:
            response = requests.get(
                _LIST_API_URL, params=params, headers=_headers(_SEARCH_PAGE_REFERER),
                timeout=_DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()

        payload = call_with_retry(_do_fetch, is_retryable=_is_retryable_requests_error)
        raw_jobs = payload.get("data", []) if isinstance(payload, dict) else []
        if not isinstance(raw_jobs, list):
            return []

        jobs = []
        for raw in raw_jobs:
            job_id = raw.get("jobNo") or raw.get("jobno")
            if not job_id:
                continue
            link = raw.get("link") if isinstance(raw.get("link"), dict) else {}
            url = _normalize_url(link.get("job") or "")
            jobs.append({
                "job_id": str(job_id),
                "job_slug": _extract_job_slug(url),
                "title": raw.get("jobName") or raw.get("jobname") or "",
                "company_id": str(raw.get("custNo") or raw.get("custno") or ""),
                "company_name": raw.get("custName") or raw.get("custname") or "",
                "region": raw.get("jobAddrNoDesc") or raw.get("area") or "",
                "url": url,
                "applicant_count": raw.get("applyCnt"),
                "is_closed": _is_job_closed(raw.get("jobSwitch")),
            })
        return jobs

    def fetch_job_detail(self, job_slug: str) -> dict:
        """查詢單一職缺詳情頁（FR-34a 兩階段架構第二階段），回傳：
        `{"content", "required_years_experience", "source_updated_at"}`；104 這次回應沒有
        提供的欄位一律回傳 `None`（FR-37b 評分時據此略過對應維度，不強行湊資料）。

        `job_slug` 必須是職缺網址結尾的短代碼（`search_list()` 回傳的 `job_slug`，例如
        `"94bow"`），不是 `job_id`（`jobNo`）——兩者是不同的識別碼，實測驗證確認詳情 API
        只接受短代碼（見本檔案模組 docstring）。應徵人數（`applicant_count`）已確認列表 API
        就有提供，不在這裡回傳，改由 `search_list()` 的結果取得。
        """
        detail_url = _DETAIL_API_URL_TEMPLATE.format(job_slug=job_slug)
        job_page_referer = f"https://www.104.com.tw/job/{job_slug}"

        def _do_fetch() -> dict:
            response = requests.get(
                detail_url, headers=_headers(job_page_referer), timeout=_DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()

        payload = call_with_retry(_do_fetch, is_retryable=_is_retryable_requests_error)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        header = data.get("header") if isinstance(data.get("header"), dict) else {}
        job_detail = data.get("jobDetail") if isinstance(data.get("jobDetail"), dict) else {}
        condition = data.get("condition") if isinstance(data.get("condition"), dict) else {}
        welfare = data.get("welfare") if isinstance(data.get("welfare"), dict) else {}

        content_parts = [
            job_detail.get("jobDescription") or "",
            welfare.get("welfare") or "",
        ]
        content = "\n".join(part for part in content_parts if part)

        return {
            "content": content,
            "required_years_experience": _parse_years(condition.get("workExp")),
            "source_updated_at": _normalize_appear_date(header.get("appearDate")),
        }
