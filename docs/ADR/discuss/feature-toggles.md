# 功能開關系統 討論紀錄

## 2026-07-30 [標籤：AI] ADR-1：既有對話狀態 dict 新增 `flow` 欄位做流程區分

**狀態**：accepted

**背景**：Step 1.1 的 `ConversationStateStore` 狀態 dict 原本只有 `{"step": ...}`，因為當時只有一種對話流（Owner 設定通關密碼）。Step 1.2 新增兩種對話流（`/my_toggles`、`/set_toggle`），且 `/my_toggles` 一般使用者也能觸發，路由層需要先判斷「目前這個進行中的對話屬於哪一種流程」才能分派到正確的處理函式。

**討論內容**：比較方案 A（狀態 dict 新增 `flow` 欄位，單一 store 支援多種流程，但需要對既有 `set_invite_codes` 流程的狀態 dict 做破壞性變更）與方案 B（每種流程各自一個獨立的 `ConversationStateStore` 實例，不需改既有結構，但 `router.py` 需同時查詢多個 store，且無法防止同一使用者同時卡在兩個流程）。

**決策**：採方案 A。

**理由**：方案 B 的「多 store 查詢」在使用者同時操作兩種流程時會產生狀態不一致的風險，方案 A 用單一 `flow` 欄位明確排他，邏輯更單純；既有測試的破壞性變更範圍很小，且本專案測試覆蓋率 100%，重構風險可控。

**後果**：`commands.start_set_invite_codes`／`handle_set_invite_codes_step` 的狀態 dict 從 `{"step": ...}` 改為 `{"flow": "set_invite_codes", "step": ...}`，`tests/bot/test_commands.py`、`tests/bot/test_router.py` 對應斷言需同步更新。

## 2026-08-15 [標籤：使用者] 特殊功能改為 Robin 專屬

**狀態**：accepted（supersedes 既有「一般使用者自管、Owner 代管」及「Owner 可替家人開啟特殊功能」決策）

**背景**：Telegram 重構盤點確認「技術分享」、「求職分析」與「考試成績」只供 Robin 使用，非管理者沒有使用情境；其他一般功能則全面開放，不需要功能開關。

**決策**：三項特殊功能以 `is_owner` 限定 Robin；非管理者不顯示 Telegram／Mobile 入口，後端拒絕偽造 Callback、舊指令與 API 存取。權限管理不提供家人特殊功能授權。若保留三項開關，只能控制 Robin 自己的爬蟲、內容產生與推播，不建立家人開關或個別排程。

**理由**：移除不會使用的授權維度，可降低資料、權限、選單與測試複雜度，並避免一般使用者誤觸 Robin 專屬資料。

**後果**：重構時停用 `/my_toggles`、`/set_toggle` 與一般使用者功能開關流程；既有 `feature_toggles` 表與資料保留，不做破壞性刪除。Reference 在程式完成前仍記錄現行實作，完成後再同步成新狀態。
