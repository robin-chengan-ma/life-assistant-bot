---
title: 個資偵測與遮蔽機制
slug: privacy-masking
status: implemented
created: 2026-08-02
updated: 2026-08-02
owner: Robin
---

# 個資偵測與遮蔽機制

## 概要

對應 [robinson SPEC.md](../robinson/SPEC.md) Phase 1 Step 1.5（FR-13、FR-13a～FR-13d）。使用者傳送的文字（打字或語音轉出文字皆算）如含台灣常見個資格式，在寫入 `conversation_logs`／`knowledge_base` 或送往 Gemini 之前，一律先遮蔽為固定文字，並在回覆中提醒使用者盡快到 Telegram 對話中自行刪除原始訊息（機器人無法代為刪除使用者自己傳送的訊息）。

遮蔽模組（Masking Filter）採「Regex 硬規則＋LLM 語意辨識」雙層防線：第一層免費、確定性高，涵蓋 8 類台灣常見個資格式；第二層補足 Regex 抓不到的變形寫法（例如用中文數字、全形符號、額外空白閃避 Regex 的狀況），排除生日與 LINE ID。

## 需求

### 功能性需求

- [x] FR-1：`src/bot/privacy.py` 提供 `mask_regex(text) -> (masked_text, detected)`，Regex 硬規則涵蓋 FR-13a 的 8 類格式：身分證字號、手機號碼、市話號碼、銀行帳戶、信用卡號、健保卡號、地址、車牌號碼；比對到的內容整段替換為固定文字 `[已遮蔽個資]`，不透露原始長度或部分內容
- [x] FR-2：`src/bot/privacy.py` 提供 `mask_with_llm(text, llm_client) -> (masked_text, detected)`，用專用 Prompt 請 LLM 找出 Regex 沒抓到、但屬於同類個資的內容並同樣替換為 `[已遮蔽個資]`；明確排除生日與 LINE ID（FR-13c），沒有偵測到就原樣回傳
- [x] FR-3：`mask_text(text, llm_client) -> (masked_text, detected)` 統一入口，先跑 FR-1 再跑 FR-2（Regex 遮蔽後的文字才送進 LLM，避免明碼進 Prompt），兩層任一層有偵測到都視為 `detected=True`
- [x] FR-4：`chat.handle_chat_message()`（一般聊天核心，涵蓋一般聊天／`pending_user_knowledge`／`pending_name_confirm`／`pending_save_knowledge_confirm` 這幾個會用到 LLM 的流程）在組 Prompt、寫入 `conversation_logs` 之前，先呼叫 `mask_text()` 把 `text` 換成遮蔽後版本，後續一律使用遮蔽後文字（含存進 `pending_save_knowledge_confirm` 狀態的 `original_request`，自然帶著遮蔽版本流到下一輪真正寫入 `knowledge_base` 的動作，不需要在 `commands.py` 額外處理）；`detected=True` 時在最終回覆最後附加提醒文案，告知使用者這則訊息含疑似個資、已自動遮蔽不會存明碼，並請使用者盡快到 Telegram 對話中自行刪除原始訊息
- [x] FR-5：`image.handle_image_message()` 的圖片說明文字（`caption`）同樣先過 `mask_text()` 再組進送給 Gemini 的 Prompt，理由同 FR-13d「送外部 API 前」
- [x] FR-6：語音轉出文字因為統一經過 `handle_message()` → `chat.handle_chat_message()`（見 robinson SPEC.md Step 1.4 架構決策），天然涵蓋 FR-4，不需要額外處理
- [x] FR-7（刻意排除範圍，明確記錄避免日後誤補）：`/clean-target-dialog`（`commands.start_clean_target_dialog_confirm`）的 `topic` 引數**不**套用遮蔽——這支指令的目的就是「依內容找出並刪除相關紀錄」，使用者很可能就是要輸入「我想刪除有關 0912345678 的紀錄」這種帶個資的搜尋主題來精準定位要刪除的資料，若先遮蔽 `topic` 會讓比對用的關鍵字直接消失、整支刪除功能失效，與 FR-13「觸發刪除機制清除敏感內容」的目的互相矛盾；通關密碼、`/set_toggle`／`/my_toggles` 編號選擇、FR-16a 最終確認關鍵字等純控制流程文字同樣不套用遮蔽，因為這些不是「使用者傳送的個資內容」，是比對用的固定格式輸入，遮蔽後會直接讓功能失效

### 非功能性需求

- [x] NFR-1：額度隔離 — FR-2 的 LLM 語意層使用獨立申請的 `GEMINI_API_PRIVACY_KEY`（比照 `GEMINI_API_IMAGE_KEY1/2` 的分流慣例），不佔用既有聊天用的 `GEMINI_API_BOT_KEY`／`GEMINI_API_TEXT_KEY` 配額——因為這一層會對「每一則」訊息都多跑一次 Gemini 呼叫，等於在既有聊天 LLM 呼叫之外新增固定成本，不能共用既有已經吃緊的 Key（2026-08-02 Robin 確認策略）
- [x] NFR-2：不誤傷 — 生日、LINE ID 一律不遮蔽（FR-13c）；至少涵蓋 FR-13a 列出的正例格式，並用反例測試確認生日／LINE ID 不會被誤判

## 設計決策

### ADR-1：LLM 語意層改用獨立 Key，不共用聊天 Key

**背景**：FR-13b 要求「Regex 硬規則＋LLM 語意辨識」雙層防線，代表語意層很可能要對每一則使用者訊息都先跑一次額外的 Gemini 呼叫（在原本聊天回覆的 LLM 呼叫之外），等於變相讓 Gemini 用量翻倍。本專案先前已多次撞到 429（見 submodules-core SPEC.md ADR-5～ADR-8），Robin 對額度消耗非常敏感。

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| A：新申請一把專用 Key（`GEMINI_API_PRIVACY_KEY`） | 不影響既有聊天/長記憶/圖片辨識的配額，額度隔離、故障域獨立 | 需要 Robin 額外去 AI Studio 申請一把新 Key |
| B：沿用既有 `GEMINI_API_BOT_KEY` | 不需要申請新 Key，實作最簡單 | 讓原本已經吃緊的聊天配額更快用完，重演先前 429 問題的風險高 |
| C：先只做 Regex 層，語意層留待後續 | 完全不影響任何額度，今天就能上線 | 不符合 FR-13b 完整要求，暫時只有 Regex 這一層防線 |

**決策**：採方案 A

**理由**：Robin 明確選擇「新申請一把專用 Key」（2026-08-02），與既有的多 Key 分流慣例（`GEMINI_API_IMAGE_KEY1/2` 給影像辨識、`GEMINI_API_TEXT_KEY` 給長記憶摘要）一致，額度隔離、互不影響，符合「每種用途各自一把 Key」的既定架構原則

**後果**：`.env.example` 新增 `GEMINI_API_PRIVACY_KEY`；`webhook.py` 需額外初始化一個 `LLMClient` 並傳入 `handle_message()`；Robin 需自行到 AI Studio 申請新 Key 並設定到本機 `.env` 與 Render 環境變數，程式碼上線前這把 Key 若缺失，語意層應優雅降級（詳見下方 ADR-2）

**狀態**：accepted

### ADR-2：語意層 Key 缺失時的降級行為

**背景**：ADR-1 決定語意層改用獨立 Key，但這把 Key 需要 Robin 額外申請，可能有一段時間（本機測試、或 Render 環境變數還沒設定完成時）該 Key 尚未就緒。

**決策**：`mask_text()` 的 `llm_client` 參數允許傳 `None`；為 `None` 時只執行 FR-1 的 Regex 層，跳過 FR-2 的 LLM 語意層，不拋出例外、不中斷訊息處理流程

**理由**：個資遮蔽是輔助防線，不應該因為選配的第二層 Key 還沒設定好就讓整個訊息處理失敗；Regex 層本身不依賴任何外部服務，永遠可以運作，符合「防禦性設計、優雅降級」原則

**後果**：`webhook.py` 若讀不到 `GEMINI_API_PRIVACY_KEY` 環境變數，`privacy_llm_client` 傳 `None` 即可，不強制要求這把 Key 一定要存在才能啟動服務

**狀態**：accepted

## 實作計畫

- [x] Step 1：`src/bot/privacy.py` —— `mask_regex()`（8 類 Regex 硬規則＋固定遮蔽文字）、`mask_with_llm()`（語意層 Prompt，排除生日／LINE ID）、`mask_text()`（統一入口，串接兩層，`llm_client=None` 時降級只跑 Regex）
- [x] Step 2：`chat.handle_chat_message()` 整合 `mask_text()`：`text` 先遮蔽再組 Prompt／寫入對話紀錄；`detected=True` 時在最終回覆附加提醒文案；新增 `privacy_llm_client` 參數，一路由 `router.handle_message()` 透傳
- [x] Step 3：`image.handle_image_message()` 的 `caption` 同樣先過 `mask_text()`；新增 `privacy_llm_client` 參數，由 `router.handle_photo_message()` 透傳
- [x] Step 4：`webhook.py` 新增 `privacy_llm_client`（讀 `GEMINI_API_PRIVACY_KEY`，缺失時傳 `None`），注入 `handle_message()`／`handle_photo_message()` 呼叫
- [x] Step 5：`.env.example` 新增 `GEMINI_API_PRIVACY_KEY` 說明
- [x] Step 6：更新 `src/schema/api_schema.md`、robinson SPEC.md（FR-13 checkbox、Step 1.5 連結）、PROGRESS.md

## 測試策略

### Unit Tests
- [x] `mask_regex()`：FR-13a 8 類格式各自的正例（依 spec 列出的範例格式）都會被遮蔽；生日格式（如「1998/05/20」「82年3月」）、LINE ID（如「@robinma」）不會被誤判遮蔽
- [x] `mask_with_llm()`：mock LLM 回傳含遮蔽結果時正確判定 `detected=True`；LLM 回傳原文不變時 `detected=False`
- [x] `mask_text()`：兩層都沒偵測到 → 原文不變、`detected=False`；只有 Regex 偵測到 → LLM 收到的是已遮蔽文字（不會把明碼送進 Prompt）；`llm_client=None` 時只執行 Regex 層、不報錯

### Integration Tests
- [x] `chat.handle_chat_message()`：使用者傳送含身分證字號的文字 → 回覆附加提醒文案、`conversation_logs` 存的是遮蔽後文字；一般不含個資的訊息 → 回覆不受影響，無提醒文案
- [x] `image.handle_image_message()`：`caption` 含個資時，送給 Gemini 的 Prompt 是遮蔽後文字
- [x] `commands.start_clean_target_dialog_confirm()`：`topic` 含疑似個資格式時**不**被遮蔽，仍可正確比對到相關紀錄（驗證 FR-7 排除範圍）

### E2E Tests
- [x] 完整流程：使用者語音講出含手機號碼的內容 → 轉錄文字 → 遮蔽 → 存入 `conversation_logs` 的是遮蔽後文字，不是明碼

**測試結果**：全專案 326 個測試全過（新增 `tests/bot/test_privacy.py` 30 個單元測試 + `test_chat.py`／`test_image.py`／`test_router.py`／`test_webhook.py` 各數個整合測試），`src/bot/`／`submodules/llm`／`submodules/voice`／`submodules/telegram` 覆蓋率 100%。

## 風險與緩解

| 風險 | 嚴重度 | 機率 | 緩解方案 |
|------|--------|------|----------|
| Regex 誤判一般數字為個資（例如 12 位健保卡號跟其他隨機 12 位數字碼撞格式） | 低 | 中 | 已知限制，先接受；正式使用後若發現高頻誤判案例再收斂規則 |
| Regex 漏抓刻意變形寫法（全形數字、中文數字、額外符號） | 中 | 中 | 由 FR-2 語意層補強；若語意層 Key 未設定則退化成只有 Regex 層，仍優於完全沒有防護 |
| 語意層增加訊息處理延遲（多一次 Gemini 呼叫） | 低 | 高（必然） | 屬於安全防線的必要成本，Robin 已確認可接受；用獨立 Key 至少不會因為額度不足而失敗 |

## 變更記錄

| 日期 | 變更內容 | 變更者 |
|------|----------|--------|
| 2026-08-02 | 初版建立，展開 robinson SPEC.md Phase 1 Step 1.5 為獨立 spec；記錄 ADR-1（語意層改用獨立 `GEMINI_API_PRIVACY_KEY`，不佔用聊天配額）、ADR-2（Key 缺失時優雅降級只跑 Regex 層）；Robin 確認策略後展開實作計畫 | Claude（依 Robin「先做吧」指示，經 AskUserQuestion 確認額度策略） |
| 2026-08-02 | **TDD 實作完成**：新增 `src/bot/privacy.py`（`mask_regex()`／`mask_with_llm()`／`mask_text()`）；`chat.handle_chat_message()`、`image.handle_image_message()` 整合遮蔽；`router.py` 透傳 `privacy_llm_client` 到 `handle_message()`／`handle_photo_message()`／`handle_voice_message()`（語音因為統一走 `handle_message()` 天然涵蓋）；`webhook.py` 新增 `_build_privacy_llm_client()`（讀 `GEMINI_API_PRIVACY_KEY`，缺失時優雅降級）；`.env.example` 補上新 Key 說明；刻意排除 `/clean-target-dialog` 的 `topic`（FR-7，避免刪除功能失效）；全專案 326 個測試全過、覆蓋率 100% | Claude（依 Robin 確認的架構實作） |
