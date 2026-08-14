# 功能開關系統 討論紀錄

## 2026-07-30 [標籤：AI] ADR-1：既有對話狀態 dict 新增 `flow` 欄位做流程區分

**狀態**：accepted

**背景**：Step 1.1 的 `ConversationStateStore` 狀態 dict 原本只有 `{"step": ...}`，因為當時只有一種對話流（Owner 設定通關密碼）。Step 1.2 新增兩種對話流（`/my_toggles`、`/set_toggle`），且 `/my_toggles` 一般使用者也能觸發，路由層需要先判斷「目前這個進行中的對話屬於哪一種流程」才能分派到正確的處理函式。

**討論內容**：比較方案 A（狀態 dict 新增 `flow` 欄位，單一 store 支援多種流程，但需要對既有 `set_invite_codes` 流程的狀態 dict 做破壞性變更）與方案 B（每種流程各自一個獨立的 `ConversationStateStore` 實例，不需改既有結構，但 `router.py` 需同時查詢多個 store，且無法防止同一使用者同時卡在兩個流程）。

**決策**：採方案 A。

**理由**：方案 B 的「多 store 查詢」在使用者同時操作兩種流程時會產生狀態不一致的風險，方案 A 用單一 `flow` 欄位明確排他，邏輯更單純；既有測試的破壞性變更範圍很小，且本專案測試覆蓋率 100%，重構風險可控。

**後果**：`commands.start_set_invite_codes`／`handle_set_invite_codes_step` 的狀態 dict 從 `{"step": ...}` 改為 `{"flow": "set_invite_codes", "step": ...}`，`tests/bot/test_commands.py`、`tests/bot/test_router.py` 對應斷言需同步更新。
