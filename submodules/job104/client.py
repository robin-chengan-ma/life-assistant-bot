"""104 人力銀行公開 AJAX API 通用 Client：無登入態直接呼叫 104 官網前端本身使用的職缺搜尋/詳情
JSON API，不使用瀏覽器自動化工具（Playwright/Selenium），輕量且高執行效能（見
docs/specs/robinson/SPEC.md FR-34a、ADR-24 決策 4）。

**重要限制（務必先讀）**：104 沒有公開正式文件化的 Open API，這裡呼叫的端點與欄位名稱是依公開
可觀察的前端行為整理而來；Cowork sandbox 無法連線 104.com.tw（見專案 memory「Sandbox network
limits」），所以這個模組目前只完成單元測試（mock HTTP response），**尚未經過正式部署後的真實
流量驗證**。ADR-24 決策 4 已預告：若正式部署後第一次真實排程跑出來的結果跟這裡的欄位假設不符
（例如欄位改名、詳情頁其實用不到、列表 API 已經夠完整），只需要調整這個檔案內部的解析邏輯
（`search_list()`／`fetch_job_detail()` 的回傳 dict 結構盡量維持不變），呼叫端
（`src/bot/job_search.py`）不需要跟著大改。

對外暴露 `search_list()`（職缺列表，一次一頁）與 `fetch_job_detail()`（單一職缺詳情，FR-34a
兩階段架構的第二階段）。UA／Referer 標頭固定套用（模擬瀏覽器請求，降低被擋機率），但請求節奏
（FR-34c 的 2～4 秒隨機延遲、禁併發、分頁停止時機）刻意不內建在這裡，由呼叫端
（`src/bot/job_search.py` 的 `crawl_and_upsert_jobs()`）控制——本模組只負責「單次 HTTP 請求
本身」，維持跟 `submodules/newsfeed`（RSS 抓取）一樣的最小職責。
"""
import re

import requests

from submodules.retry.client import call_with_retry

_LIST_API_URL = "https://www.104.com.tw/jobs/search/list"
_DETAIL_API_URL_TEMPLATE = "https://www.104.com.tw/job/ajax/content/{job_id}"
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
    """把可能是相對路徑的職缺連結換算成完整網址；已經是完整網址就原樣回傳。"""
    if not raw_url:
        return ""
    if raw_url.startswith("http://") or raw_url.startswith("https://"):
        return raw_url
    return _BASE_URL + (raw_url if raw_url.startswith("/") else f"/{raw_url}")


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
        region: str | None = None,
        salary_min: int | None = None,
        salary_max: int | None = None,
        industry: str | None = None,
        page: int = 1,
    ) -> list[dict]:
        """查詢職缺搜尋列表第 `page` 頁（FR-34a 兩階段架構第一階段），回傳摘要清單：
        `[{"job_id", "title", "company_id", "company_name", "region", "url"}, ...]`；
        查無結果（含翻到最後一頁之後）回傳空清單，由呼叫端依此判斷分頁何時停止。
        """
        params: dict = {"keyword": keyword, "page": page, "mode": "s", "jobsource": "joblist_search"}
        if region:
            params["area"] = region
        if salary_min:
            params["scmin"] = salary_min
        if salary_max:
            params["scmax"] = salary_max
        if industry:
            params["indcat"] = industry

        def _do_fetch() -> dict:
            response = requests.get(
                _LIST_API_URL, params=params, headers=_headers(_SEARCH_PAGE_REFERER),
                timeout=_DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()

        payload = call_with_retry(_do_fetch, is_retryable=_is_retryable_requests_error)
        raw_jobs = payload.get("data", {}).get("list", []) if isinstance(payload, dict) else []
        if not isinstance(raw_jobs, list):
            return []

        jobs = []
        for raw in raw_jobs:
            job_id = raw.get("jobNo") or raw.get("jobno")
            if not job_id:
                continue
            link = raw.get("link") if isinstance(raw.get("link"), dict) else {}
            jobs.append({
                "job_id": str(job_id),
                "title": raw.get("jobName") or raw.get("jobname") or "",
                "company_id": str(raw.get("custNo") or raw.get("custno") or ""),
                "company_name": raw.get("custName") or raw.get("custname") or "",
                "region": raw.get("jobAddrNoDesc") or raw.get("area") or "",
                "url": _normalize_url(link.get("job") or ""),
            })
        return jobs

    def fetch_job_detail(self, job_id: str) -> dict:
        """查詢單一職缺詳情頁（FR-34a 兩階段架構第二階段），回傳：
        `{"content", "required_years_experience", "applicant_count", "source_updated_at"}`；
        104 這次回應沒有提供的欄位一律回傳 `None`（FR-37b 評分時據此略過對應維度，不強行湊資料）。
        """
        detail_url = _DETAIL_API_URL_TEMPLATE.format(job_id=job_id)
        job_page_referer = f"https://www.104.com.tw/job/{job_id}"

        def _do_fetch() -> dict:
            response = requests.get(
                detail_url, headers=_headers(job_page_referer), timeout=_DEFAULT_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()

        payload = call_with_retry(_do_fetch, is_retryable=_is_retryable_requests_error)
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
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
            "applicant_count": data.get("applyCnt"),
            "source_updated_at": data.get("appearDate") or None,
        }
