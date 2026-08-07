---
title: 功能開關系統 — 使用者自管 + Owner 代管
slug: feature-toggles
status: implemented
created: 2026-07-30
updated: 2026-07-30
owner: Robin
---

# 功能開關系統

## 概要

對應 [robinson SPEC.md](../robinson/SPEC.md) Phase 1 Step 1.2（FR-2、FR-2a）。讓每位使用者可以自行開關「自己」的功能模組（原為 8 個，2026-08-07 拆分 `skill_growth` 後為 10 個，見下方 FR-3 追記），Owner（Robin）額外擁有代管權限，可調整任何使用者的開關。這個階段只做「開關機制本身」——把開關狀態記下來、讓使用者能查看與切換；至於功能被關閉時實際攔截對話的邏輯，要等 Step 1.3 對話核心接上後才會真正生效，目前先沿用 Step 1.1 既有的 `_PLACEHOLDER_REPLY` 佔位回覆。

依 Robin 2026-07-30 確認：權限模型採「使用者可自管、Owner 可代管」（見 robinson SPEC.md FR-2a）。

## 需求

### 功能性需求

- [x] FR-1：`/my_toggles`（或「我的功能設定」）—— 任何已綁定使用者觸發後，列出自己所有功能目前的開/關狀態，附編號；下一則訊息若為有效編號，切換該項開關（開↔關互相切換），並回覆更新後的完整清單；若為「沒有了」／「結束」則退出設定模式
- [x] FR-2：`/set_toggle`（或「設定家人功能開關」）—— 僅 Owner 可觸發，先列出所有已綁定的非 Owner 使用者供選擇要調整誰；選定後進入與 FR-1 相同的編號切換畫面，但改的是該使用者的開關；沒有任何已綁定家人時回覆提示訊息，不進入設定模式
- [x] FR-3：使用者第一次綁定成功（`try_bind_invite_code` 成功）時，自動幫他寫入一筆對應 `feature_key` 的 `feature_toggles`（`is_enabled=TRUE`）（不含「客訴回饋」，客訴為固定入口，非可關閉功能）；已存在的 `feature_key` 不重複寫入（冪等）。**2026-08-07 追記**：`feature_key` 原有 8 個模組代號，Robin 驗收 Step 3.1（每日技術分享）後回饋，認為證照準備（TOEIC 等）跟技術情報訂閱（新聞/電子報/YouTube）性質不同，語言學習（英文口說、其他語言，尚未開發）也該獨立，三者不該共用同一把開關；經 AskUserQuestion 確認命名與資料搬移方式，`skill_growth` 拆成 `tech_intel`（技術情報）／`certificate`（證照準備）／`language`（語言學習）三個獨立代號，變成 10 個模組（`0034_split_skill_growth_toggle.sql`，Robin 依 ADR-10 核准；既有 `skill_growth` 開關資料搬移為 `tech_intel`，保留原開啟狀態）
- [x] FR-4：`/my_toggles`、`/set_toggle` 顯示清單前皆會先呼叫 FR-3 的補齊邏輯作為安全網，確保舊資料（例如 Step 1.2 上線前就已綁定的使用者）不會因為缺資料而顯示異常

### 非功能性需求

- [x] NFR-1：可維護性 —— 沿用 Step 1.1 既有的 `ConversationStateStore`（記憶體，不落地），不新增資料表或持久化機制；狀態 dict 新增 `flow` 欄位區分「設定通關密碼」與「功能開關」兩種對話流，避免路由層混淆
- [x] NFR-2：安全 —— 一般使用者只能查看/切換自己的開關，無法透過任何輸入操控他人；`/set_toggle` 僅 Owner 可觸發（沿用 FR-2/`auth.is_owner` 判斷）

## 設計決策

### ADR-1：既有對話狀態 dict 新增 `flow` 欄位做流程區分

**背景**：Step 1.1 的 `ConversationStateStore` 狀態 dict 原本只有 `{"step": ...}`，因為當時只有一種對話流（Owner 設定通關密碼）。Step 1.2 新增兩種對話流（`/my_toggles`、`/set_toggle`），且 `/my_toggles` 一般使用者也能觸發，路由層需要先判斷「目前這個進行中的對話屬於哪一種流程」才能分派到正確的處理函式。

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| A：狀態 dict 新增 `flow` 欄位（例如 `{"flow": "toggle", "step": "awaiting_index"}`） | 單一 store 即可支援多種流程，改動集中在狀態 dict 結構 | 既有 `set_invite_codes` 流程的狀態 dict 需要一併補上 `flow` 欄位，屬於破壞性變更，需同步更新既有測試 |
| B：每種流程各自一個獨立的 `ConversationStateStore` 實例 | 不需改動既有流程的狀態 dict 結構 | `router.py` 需要同時查詢多個 store 才能判斷使用者目前在哪個流程，且無法防止同一使用者同時卡在兩個流程（例如 Owner 同時進行中設定通關密碼又觸發功能開關） |

**決策**：採方案 A

**理由**：方案 B 的「多 store 查詢」在使用者同時操作兩種流程時會產生狀態不一致的風險（例如卡在 A 流程一半又觸發 B 流程），方案 A 用單一 `flow` 欄位明確排他，邏輯更單純；既有測試的破壞性變更範圍很小（僅 `commands.py` 兩個函式與對應測試斷言），且本專案目前测試覆蓋率 100%，重構風險可控

**後果**：`commands.start_set_invite_codes`／`handle_set_invite_codes_step` 的狀態 dict 從 `{"step": ...}` 改為 `{"flow": "set_invite_codes", "step": ...}`，`tests/bot/test_commands.py`、`tests/bot/test_router.py` 對應斷言需同步更新

**狀態**：accepted

## 實作計畫

- [x] Step 1：`src/bot/toggles.py` —— 純邏輯：`ensure_default_toggles`／`get_toggles`／`format_toggle_list`／`toggle_by_index`／`is_feature_enabled`
- [x] Step 2：`src/bot/commands.py` 新增 `start_my_toggles`／`start_set_toggle`／`handle_toggle_step`；既有 `set_invite_codes` 狀態 dict 補上 `flow` 欄位
- [x] Step 3：`src/bot/router.py` 整合新觸發詞（`/my_toggles`、`/set_toggle`）與 `flow` 分派邏輯；家人綁定成功當下呼叫 `ensure_default_toggles`
- [x] Step 4：`tests/bot/conftest.py` 的 `FakeCloudSQLClient` 新增 `feature_toggles` 表與對應 where 條件
- [x] Step 5：更新 `src/schema/api_schema.md` 標記 `/my_toggles`、`/set_toggle` 為已實作

## 測試策略

### Unit Tests
- [x] `toggles.ensure_default_toggles()`：全新使用者補齊全部模組（原 8 筆，2026-08-07 起為 10 筆）/ 已存在部分資料時不重複寫入
- [x] `toggles.get_toggles()`：依固定順序回傳 / 資料不完整時只回傳已存在的項目
- [x] `toggles.toggle_by_index()`：合法編號切換成功（開→關、關→開）/ 編號超出範圍回傳 `None`
- [x] `toggles.is_feature_enabled()`：查無資料時預設視為開啟（防禦性）
- [x] `commands.start_my_toggles`／`handle_toggle_step`：一般使用者切換自己開關的完整流程、離開流程
- [x] `commands.start_set_toggle`：無任何家人可代管時的提示訊息 / 有家人時列出候選名單
- [x] `handle_toggle_step` 未知 step 防呆拋錯

### Integration Tests
- [x] `router.py`：一般使用者觸發 `/my_toggles` 完整切換流程；Owner 觸發 `/set_toggle` 選人後切換流程；家人無法觸發 Owner 專屬 `/set_toggle`（權限邊界測試）
- [x] 家人第一次綁定成功後，`feature_toggles` 立即有 8 筆預設開啟的資料

### E2E Tests
- [x] 完整代管流程：Owner `/set_toggle` → 選家人 → 切換兩個功能 → 「沒有了」結束

**測試結果**：28 個新測試全數通過（`test_toggles.py` 11 個、`test_commands.py`／`test_router.py` 新增部分共 17 個），加上既有測試，`src/bot/` 全部 78 個測試全過、覆蓋率維持 100%（`pytest tests/ --cov=src/bot`）。

## 風險與緩解

| 風險 | 嚴重度 | 機率 | 緩解方案 |
|------|--------|------|----------|
| `flow` 欄位重構屬於既有已上線程式碼的破壞性變更 | 低 | 低 | 100% 測試覆蓋率下重構，同步更新受影響測試並重新驗證全數通過再 commit |
| 功能開關目前尚未真的攔截對話（Step 1.3 才會生效） | 低 | 高（目前必然如此） | 已在概要與 robinson SPEC.md 註明是刻意分階段，不影響 Phase 1 其餘 Step |

## 變更記錄

| 日期 | 變更內容 | 變更者 |
|------|----------|--------|
| 2026-07-30 | 初版建立，展開 robinson SPEC.md Phase 1 Step 1.2 為獨立 spec，記錄 ADR-1（狀態 dict flow 欄位設計） | Claude（依 Robin「照你說的先做」指示） |
| 2026-07-30 | ADR-1 完成 TDD 實作：`src/bot/toggles.py`（純邏輯）、`commands.py` 新增 `start_my_toggles`／`start_set_toggle`／`handle_toggle_step`、`router.py` 整合 `/my_toggles`／`/set_toggle` 與 `flow` 分派；`set_invite_codes` 既有流程狀態 dict 補上 `flow` 欄位並同步更新既有測試；`src/bot/` 78 個測試全過、覆蓋率 100% | Claude |
| 2026-08-07 | **FR-3 追記：`skill_growth` 拆成 `tech_intel`／`certificate`／`language` 三個獨立開關，模組數由 8 個變成 10 個**。Robin 驗收 robinson SPEC.md Step 3.1（每日技術分享）後回饋，證照準備（TOEIC）跟技術情報訂閱（新聞/電子報/YouTube）性質不同、不該共用同一把開關，語言學習（尚未開發）也該獨立；經 AskUserQuestion 確認 key 命名（比照既有 8 個開關「不加模組前綴」風格）與既有資料處理方式（既有 `skill_growth` 開關資料搬移到 `tech_intel`，保留開啟狀態）。新增 migration `0034_split_skill_growth_toggle.sql`（Robin 依 ADR-10 核准）；`templates.FEATURE_LIST` 對應拆成三筆；既有測試（`test_toggles.py`／`test_commands.py`／`test_router.py`）硬編碼的模組數量斷言由 8 改為 10；全專案 888 個測試全過 | Claude（依 Robin 提出的拆分需求，經 AskUserQuestion 確認命名與資料搬移方式後實作） |
