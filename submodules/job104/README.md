# job104

104 人力銀行公開 AJAX API 通用 Client，無登入態直接呼叫 104 官網前端使用的職缺搜尋/詳情 JSON API，不使用瀏覽器自動化工具（Playwright/Selenium）。

## 驗證狀態（2026-08-09 更新）

104 沒有公開正式文件化的 Open API。Cowork sandbox 無法連線 104.com.tw，所以改由 Robin 透過瀏覽器 DevTools Network 面板手動抓真實請求驗證，已確認：
- 列表 API 端點是 `https://www.104.com.tw/jobs/search/api/jobs`，回應結構是 `{"data": [...]}`（`data` 本身直接是職缺陣列）。
- 詳情 API 端點是 `https://www.104.com.tw/api/jobs/{短代碼}`，短代碼取自職缺網址（`link.job`）結尾那段，跟列表 API 的 `jobNo`（資料庫去重鍵值）是不同識別碼，不可混用。
- 主要欄位名稱（`jobName`／`custNo`／`custName`／`jobAddrNoDesc`／`jobDetail.jobDescription`／`condition.workExp`／`welfare.welfare`）皆已確認正確；應徵人數（`applyCnt`）改由列表 API 直接取得，不在詳情頁。

**仍未驗證**：地區（`area`）／產業（`indcat`）篩選查詢參數名稱這次測試沒有實際設定這兩個條件，維持原先猜測，尚未確認正確性。

## 環境變數

見 `.env.example`：無需任何金鑰（104 搜尋/詳情 API 為公開端點）。

## 安裝

```bash
pip install -r submodules/job104/requirements.txt
```

## 使用範例

```python
from submodules.job104.client import Job104Client

client = Job104Client()

jobs = client.search_list(keyword="AI 工程師", region="台北市", salary_min=50000, page=1)
# [{"job_id": "...", "job_slug": "...", "title": "...", "company_id": "...", "company_name": "...",
#   "region": "...", "url": "https://www.104.com.tw/job/...", "applicant_count": 7}, ...]

# 注意：fetch_job_detail() 要傳 job_slug（短代碼），不是 job_id（jobNo）！
detail = client.fetch_job_detail(jobs[0]["job_slug"])
# {"content": "...", "required_years_experience": 3.0, "source_updated_at": "2026-08-09"}
```

## 設計限制（務必遵守）

1. 只支援 `search_list()`／`fetch_job_detail()` 兩個唯讀查詢，不做任何寫入類操作。
2. 請求節奏（2～4 秒隨機延遲、禁併發、分頁何時停止、遇錯是否跳過繼續）刻意不內建在這裡，一律由呼叫端（`src/bot/job_search.py` 的 `crawl_and_upsert_jobs()`）控制。
3. 104 這次回應沒有提供的欄位（例如應徵人數、更新時間）一律回傳 `None`，不強行湊資料，交由呼叫端決定要不要略過對應的契合度評分維度（FR-37b）。

## 對應 Spec

[docs/specs/SPEC.md](../../docs/specs/SPEC.md) FR-34、[docs/ADR/discuss/job-search.md](../../docs/ADR/discuss/job-search.md) ADR-24 決策 4
