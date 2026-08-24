# 待辦事項模組 修復紀錄

> 同一功能的多次除錯都寫在同一個檔案，依時間往下附加新段落，不要開新檔案。不論有沒有改 code 都要記。

## 2026-08-24 Mobile App「逾期待辦」看不到已自動過期的代辦事項

**現象**：Robin 設定的一筆代辦事項（`due_at` 為當天台灣時間 09:00）到期後，Telegram 每日 08:00 摘要有正常推播（`daily_pushed_on` 已寫入當天），但事後在 Mobile App「待辦事項」頁面完全找不到這筆事項——不在「即將到期」清單，也不在「逾期待辦」區塊。Robin 逐步追問後確認：Mobile App 的「即將到期」清單目前顯示的就是 UPCOMING（尚未到期），理論上過期未處理的事項應該出現在「逾期待辦」讓使用者標記完成或取消，但實際上該區塊幾乎抓不到任何東西。

**排查過程**：先確認 DB 資料列，發現該筆事項 `status` 已是 `expired`（而非 `pending`）。追到 `src/bot/todo.py` 的 `mark_overdue_as_expired()`：只要 `status='pending' AND due_at < now`，就會被批次改成 `status='expired'`；這支函式借用 `/healthz` 既有約 10 分鐘一次的 cron 頻率執行，代表一筆待辦最慢在到期後 10 分鐘內就會從 `pending` 轉成 `expired`。再檢查 `src/services/app_analytics.py` 的 `todos()` 方法，`overdue_items` 查詢與 `calendar_counts` 查詢都寫死 `status = 'pending'`，兩者互相沒有考慮到對方的時間交互——`overdue_items` 原本假設「過期的還會是 pending」，但 `mark_overdue_as_expired()` 幾乎立刻就把它轉走，導致「逾期待辦」這個功能在實務上幾乎永遠是空的。

**根因**：`overdue_items`／`calendar_counts` 查詢的 `status='pending'` 篩選，與 `mark_overdue_as_expired()` 的自動轉態邏輯，各自單獨看都合理，但兩者的時間交互從未被檢查過——待辦一過期，幾乎立刻（10 分鐘內）就從「還可能被逾期查詢抓到的 pending」變成「已被排除在外的 expired」，等於這個功能形同虛設。`items`（即將到期）查詢本身邏輯沒有問題，不受影響。

**修復方式**：把 `src/services/app_analytics.py` 的 `overdue_items` 與 `calendar_counts` 兩段查詢的篩選條件從 `status = 'pending'` 改成 `status IN ('pending', 'expired')`，讓「還沒轉態的過期 pending」與「已被自動轉態的 expired」都能出現在逾期待辦清單與月曆計數中；`items`（即將到期）清單維持只看 `pending` 不動。另外確認 `src/api/app_analytics.py` 的 `update_record()`／`_mutate_record()` 是依 `record_id` 直接更新，沒有額外限制 `status`，因此標記完成／取消對 `expired` 的待辦一樣能正常運作，不需要修改；Mobile UI 的 `OverdueTodos` 元件（`mobile/app/analytics/[module].tsx`）也是直接渲染 `overdue_items` 陣列，沒有依賴 `status` 做額外過濾，不需要改 UI。

**驗證方式**：在 `tests/services/test_app_analytics.py` 新增 `test_todos_overdue_and_calendar_counts_include_auto_expired_items`，驗證 `status='expired'` 的待辦會出現在 `overdue_items`（含 `overdue_count` 正確）與 `calendar_counts`，並直接檢查產生的 SQL 字串含有 `status IN ('pending', 'expired')`；同時保留既有 `test_todos_separates_pending_current_and_overdue_items` 確認 `items`（即將到期）仍只顯示 `pending`、不受影響。於 Cowork 沙盒執行 `pytest tests/services/test_app_analytics.py`，39 個測試全數通過；`ruff check` 通過。待 Robin push 並在正式環境／Mobile App 實機確認：讓一筆待辦事項過期並等它自動轉為 `expired` 後，Mobile App「逾期待辦」區塊確實會顯示該筆事項，且可正常標記完成或取消。
