# job104

104 人力銀行公開 AJAX API 通用 Client，無登入態直接呼叫 104 官網前端使用的職缺搜尋/詳情 JSON API，不使用瀏覽器自動化工具（Playwright/Selenium）。

## ⚠️ 尚未經過真實流量驗證

104 沒有公開正式文件化的 Open API，這裡呼叫的端點與欄位名稱是依公開可觀察的前端行為整理而來。Cowork sandbox 無法連線 104.com.tw，這個模組目前只完成單元測試（mock HTTP response），**尚未經過正式部署後的真實流量驗證**。若正式部署後第一次真實排程跑出來的結果跟這裡的欄位假設不符，只需要調整 `client.py` 內部的解析邏輯，對外回傳的 dict 結構盡量維持不變。

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
# [{"job_id": "...", "title": "...", "company_id": "...", "company_name": "...",
#   "region": "...", "url": "https://www.104.com.tw/job/..."}, ...]

detail = client.fetch_job_detail(jobs[0]["job_id"])
# {"content": "...", "required_years_experience": 3.0, "applicant_count": None,
#  "source_updated_at": "2026-08-09"}
```

## 設計限制（務必遵守）

1. 只支援 `search_list()`／`fetch_job_detail()` 兩個唯讀查詢，不做任何寫入類操作。
2. 請求節奏（2～4 秒隨機延遲、禁併發、分頁何時停止、遇錯是否跳過繼續）刻意不內建在這裡，一律由呼叫端（`src/bot/job_search.py` 的 `crawl_and_upsert_jobs()`）控制。
3. 104 這次回應沒有提供的欄位（例如應徵人數、更新時間）一律回傳 `None`，不強行湊資料，交由呼叫端決定要不要略過對應的契合度評分維度（FR-37b）。

## 對應 Spec

[docs/specs/robinson/SPEC.md](../../docs/specs/robinson/SPEC.md) FR-34、ADR-24 決策 4
