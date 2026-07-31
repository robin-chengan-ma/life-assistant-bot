---
title: 平台核心入口 — 通關密碼驗證、Owner 對話式設定、/rule、/function
slug: platform-auth
status: implemented
created: 2026-07-30
updated: 2026-07-31
owner: Robin
---

# 平台核心入口

## 概要

這是 Robinson 的第一個 Phase 1 模組（對應 [robinson SPEC.md](../robinson/SPEC.md) Phase 1 Step 1.1），涵蓋所有使用者第一次接觸 Bot 時會用到的基礎機制：Telegram Webhook 入口、通關密碼驗證與綁定、Owner 專屬的引導式通關密碼設定對話流、綁定成功歡迎訊息，以及 `/rule`／`/function` 兩個內建說明指令。這是後續所有功能模組的前置依賴——沒有這層，使用者根本無法通過驗證進入系統。

## 需求

### 功能性需求

- [x] FR-1：`POST /telegram/webhook` 接收 Telegram 傳來的 Update JSON（文字訊息），依發送者身分與內容路由到對應處理邏輯
- [x] FR-2：`is_owner` 判斷 —— 收到訊息時，比對 `telegram_user_id` 是否等於環境變數 `ROBIN_TELEGRAM_TOKEN`；符合則視為 Robin，免通關密碼直接視為管理者兼使用者（對應 robinson SPEC.md FR-5）
- [x] FR-3：未知使用者（`users` 表查無對應 `telegram_user_id`）傳送文字時，比對是否為未使用過的 `invite_codes.code`；比對成功則綁定（寫入 `users.telegram_user_id`、標記 `invite_codes.is_used=TRUE` 並更新 `updated_at`），並回傳 FR-6d 的歡迎訊息（附錄 A 全文，純靜態文字，不呼叫 LLM）；比對失敗則回覆制式提示「請輸入通關密碼」，不進入任何其他邏輯
- [x] FR-4：Owner 專屬設定對話流（對應 robinson SPEC.md FR-6a～FR-6c）—— 僅 Robin 可觸發 `/set_invite_codes` 或「設定通關密碼」，進入多輪對話：詢問稱謂 → 收到稱謂後暫存於記憶體狀態（尚不寫入資料庫，因為 `invite_codes.code` 是 `NOT NULL`，稱謂單獨一項還無法組成合法的一列）→ 詢問通關密碼 → 收到密碼後，此時稱謂與密碼皆已齊備，一次性建立 `users`（`telegram_user_id=NULL`、`role=<稱謂>`）與 `invite_codes`（`code=<密碼>`、`user_id` 指向剛建立的 `users.id`）→ 回覆「已寫入！請問還有其他家人要設定嗎？」→ 下一則訊息若為「沒有了」或「結束」則退出設定模式，否則視為下一位家人的稱謂，繼續循環
- [x] FR-5：`/rule` 路由 —— 任何身分輸入「我要看使用規則」或 `/rule`，直接回傳附錄 A 全文，不經過 LLM
- [x] FR-6：`/function` 路由 —— 任何身分輸入「我要看所有功能」或 `/function`，回傳目前已實作功能的清單（MVP 先用最簡單條列格式，正式文案模板待產品原型後由 Robin 補上，見 robinson SPEC.md 附錄 B）。**2026-07-31 更新**：此 MVP 版本（一次回傳固定條列文字、不經 LLM）已於 Phase 1 Step 1.3a 被取代，改為「總覽＋按需深入＋人格化語氣」設計，見 [chat-core SPEC.md](../chat-core/SPEC.md) FR-9、ADR-4；本條 FR 保留作為 Step 1.1 當時的歷史紀錄，路由觸發字串（`/function`／「我要看所有功能」）本身不變
- [x] FR-7（暫時性安全網，2026-07-31 新增）：`telegram_webhook()` 對 `handle_message()` 呼叫包 `try/except`，未預期例外（例如 Gemini API 額度超限的 429）一律記錄完整 Traceback（`logging.exception`）並回覆固定安全用語 `"羅賓森好像不太舒服，等一下再試試看喔！"`，**仍然回傳 HTTP 200**。這不是完整的 FR-19（robinson SPEC.md），只解決一個具體的營運風險：Flask 若讓例外往外拋回 500，Telegram Webhook 收不到 200 會自動重送同一則訊息，形成「失敗 → 重試 → 再失敗」的迴圈，把 Gemini 免費額度燒得更快；完整的錯誤分類、Traceback 集中式 log、私訊 Robin、自主診斷仍留給 robinson SPEC.md Step 1.6／FR-19a～FR-19i

### 非功能性需求

- [x] NFR-1：安全 —— 通關密碼比對與綁定操作必須是原子性的（避免同一組密碼被兩個人同時搶綁），對應 robinson SPEC.md NFR-4
- [x] NFR-2：可用性 —— Owner 設定對話流的中間狀態存放於 process 內記憶體（見 ADR-2），若服務重啟會遺失進行到一半的設定，Robin 需重新開始；此為刻意的簡化取捨，因為觸發頻率低且僅 Robin 使用
- [x] NFR-3：可維護性 —— webhook 路由邏輯與命令處理邏輯分層存放（見「檔案結構」），不得全部塞進 `main.py`

## 設計決策

### ADR-1：Webhook 訊息解析不依賴 `python-telegram-bot`，改用原生 dict 直接解析

**背景**：`requirements.txt` 目前列了 `python-telegram-bot`，但 `submodules/telegram` 的 README 只說「可能沿用」處理 webhook dispatch，尚未真的決定。`python-telegram-bot` 的 `Application`／`Dispatcher` 設計成跑在自己的 asyncio event loop 上，若要塞進 Flask 這種同步 WSGI framework，需要額外處理 async/sync 橋接（例如每個 request 建一個新的 event loop 呼叫 `application.process_update()`），增加不必要的複雜度。

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| A：`python-telegram-bot` 的 `Update.de_json` + 手動呼叫 handler | 有型別化的 Update 物件，欄位存取較安全 | 仍需引入整包相依，且與 Flask 同步模型有 async 橋接成本 |
| B：直接讀取原生 JSON dict（`request.get_json()["message"]["from"]["id"]` 等） | 零額外相依、零 async 橋接、跟 `submodules/telegram` 目前「不依賴框架」的精神一致 | 沒有型別檢查，欄位打錯字不會在寫程式當下被抓到，需要靠測試補強 |

**決策**：採方案 B，直接解析原生 JSON dict；`requirements.txt` 移除 `python-telegram-bot`（目前未被任何程式碼使用）

**理由**：本專案目前只需要處理文字訊息與極少數指令，不需要 `python-telegram-bot` 提供的複雜功能（inline keyboard、conversation handler 框架等）；比照 ADR-4（submodules 統一四檔案結構）與 robinson SPEC.md 一貫的「簡潔直接，不過度工程」原則，方案 B 更輕量、更好測試（純函式接 dict，不需要 mock 一整包 SDK）

**後果**：`requirements.txt` 移除 `python-telegram-bot`；所有 webhook 解析寫在 `src/bot/webhook.py`，用 unit test 覆蓋各種缺欄位/格式錯誤的邊界情況（Edge Case 見測試策略）

**狀態**：accepted

### ADR-2：Owner 設定對話流的狀態存放於記憶體，不落地到資料庫

**背景**：FR-6b 的多輪對話（詢問稱謂→收密碼→循環）需要在多次 HTTP request 之間記住「現在問到哪一步」。Render 免服務單一 process 執行，但免費方案閒置會休眠，若休眠後又被喚醒，process 內記憶體會被清空。

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| A：存進 Neon 一張新的 `conversation_states` 表 | 重啟不會遺失狀態 | 多一張表、多一輪 ADR-10 審核流程，且這個對話流本來就只有 Robin 一人偶爾用到，複雜度與效益不成比例 |
| B：存在 process 記憶體的一個全域 dict（`{telegram_user_id: {step, role}}`） | 零額外資料表、實作最單純 | 服務重啟或休眠喚醒後若剛好卡在對話中途，狀態會遺失，Robin 需要重新輸入 `/set_invite_codes` |

**決策**：採方案 B

**理由**：這個對話流只有 Robin 會用、使用頻率低（新增家人才觸發一次），且 Render 免費方案配合 cron-job.org 每 10 分鐘 keep-alive 之後很少真的進入休眠；就算真的遺失狀態，代價只是 Robin 重新走一次設定流程，不影響任何使用者資料正確性。比起為了這個低頻小流程新增一張表、再走一次 ADR-10 審核，方案 B 明顯更符合「不過度工程」

**後果**：若之後這個對話流變得複雜（例如要支援多人同時設定、或步驟變多），需要重新評估搬到資料庫；`src/bot/state.py` 需明確註明這是 in-memory、非持久化

**狀態**：accepted

## 實作計畫

### Phase 1（本 spec 範圍）

- [x] Step 1：`src/bot/webhook.py` —— Flask Blueprint，`POST /telegram/webhook` 入口，解析原生 JSON，取出 `telegram_user_id`／`text`，呼叫 `router.handle_message()`
- [x] Step 2：`src/bot/auth.py` —— `is_owner(telegram_user_id)`、`find_or_create_user()`、`try_bind_invite_code()` 等身分與綁定邏輯
- [x] Step 3：`src/bot/state.py` —— in-memory 對話狀態 store（`ConversationStateStore` class），供 Owner 設定流程使用
- [x] Step 4：`src/bot/commands.py` —— `/rule`、`/function`、`/set_invite_codes` 的處理函式
- [x] Step 5：`src/bot/router.py` —— 統一路由：依身分 + 狀態 + 文字內容，分派到上述各處理函式
- [x] Step 6：`main.py` 註冊 `src/bot/webhook.py` 的 Blueprint
- [x] Step 7：附錄 A 規範文本抽成常數模組 `src/bot/templates.py`，供 FR-6d／`/rule` 共用
- [x] Step 8：更新 `src/schema/api_schema.md` 的 `POST /telegram/webhook`、`/rule`、`/function`、`/set_invite_codes` 狀態為「已實作」

## 測試策略

### Unit Tests
- [x] `auth.is_owner()`：符合 `ROBIN_TELEGRAM_TOKEN` / 不符合 / 環境變數未設定
- [x] `auth.try_bind_invite_code()`：密碼正確且未使用 / 密碼不存在 / 密碼已被使用過 / 空字串輸入 / race condition 輸掉競爭
- [x] `state.ConversationStateStore`：建立狀態 / 取得狀態 / 清除狀態 / 取得不存在的使用者狀態
- [x] `commands` 各函式：正常輸入（含中文稱謂）/ 未知對話狀態防呆；家人呼叫 Owner 專屬指令的權限邊界測試放在 `test_router.py`
- [ ] 超長文字輸入未特別測試（Telegram 本身限制單則訊息 4096 字元，且目前欄位皆為 `TEXT` 不做長度驗證，風險低，暫不列為必要項目）

### Integration Tests
- [x] `POST /telegram/webhook`：合法 Update JSON → 呼叫對應 handler；缺少 `message`／`text` 欄位、非文字訊息一律忽略
- [x] 通關密碼綁定流程：未知使用者輸入正確密碼 → `users`／`invite_codes` 正確更新 + 收到歡迎訊息；重複使用同一組密碼 → 第二次應失敗

### E2E Tests
- [x] 完整 Owner 設定流程：`/set_invite_codes` → 輸入稱謂 → 輸入密碼 → 重複第二輪 → 「沒有了」結束（`test_full_two_family_members_setup_flow`）
- [x] 家人綁定 + `/rule` + `/function` 全流程

- [x] FR-7：`handle_message()` 拋出未預期例外時，`telegram_webhook()` 仍回傳 200 並回覆安全用語（`test_webhook_swallows_unexpected_exception_and_still_returns_200`）

**測試結果**：49 個測試全數通過，`src/bot/` 覆蓋率 100%（`pytest tests/ --cov=src/bot`）。**2026-07-31 補充**：FR-7 安全網新增 1 個測試，隨 Step 1.3a 之後的整體測試套件一起計入 robinson SPEC.md 變更記錄的測試總數。

## 風險與緩解

| 風險 | 嚴重度 | 機率 | 緩解方案 |
|------|--------|------|----------|
| Owner 設定流程中途服務重啟導致狀態遺失（ADR-2 已知取捨） | 低 | 低 | Robin 重新輸入 `/set_invite_codes` 即可，不影響資料正確性 |
| 通關密碼綁定的 race condition（理論上兩人同時搶同一組碼） | 低 | 極低（個人/家用場景） | 不依賴「單一 transaction 包住 select+update」（`CloudSQLClient` 每個方法各自開關連線，無法這樣做），改用「原子性條件 UPDATE」：`UPDATE invite_codes SET is_used=TRUE WHERE id=%s AND is_used=FALSE`，第二個並行請求會影響 0 筆而非誤判成功，已有專屬單元測試覆蓋此分支 |
| 原生 JSON 解析缺乏型別檢查，欄位打錯字不會在開發期被抓到（ADR-1 已知取捨） | 中 | 中 | Unit test 覆蓋各種缺欄位情境；所有欄位存取用 `.get()` 並在缺欄位時回傳明確錯誤，不讓 `KeyError` 直接讓 process 掛掉 |
| 外部 API（Gemini／Telegram）呼叫失敗未攔截時，Telegram Webhook 重試機制會不斷重送同一則訊息，加速燒光免費額度（2026-07-31 實測發現，見 FR-7） | 中 | 中 | FR-7 已加上最小安全網（`try/except` + 固定回覆 200），實測時已解決；完整分級處理仍待 robinson SPEC.md Step 1.6 |

## 變更記錄

| 日期 | 變更內容 | 變更者 |
|------|----------|--------|
| 2026-07-30 | 初版建立，展開 robinson SPEC.md Phase 1 Step 1.1 為獨立 spec | Claude（依 Robin「請開始吧」指示） |
| 2026-07-30 | ADR-1／ADR-2 經 Robin 確認後完成 TDD 實作：`src/bot/`（`state.py`／`auth.py`／`templates.py`／`commands.py`／`router.py`／`webhook.py`），`requirements.txt` 移除 `python-telegram-bot`，新增 `requirements-dev.txt`／`pytest.ini`；49 個測試全過、覆蓋率 100%；同步更新 `src/schema/api_schema.md` 對應路由狀態 | Claude |
| 2026-07-31 | Robin 實測 Step 1.3a 時撞到 Gemini 429（額度超限），發現 `webhook.py` 未攔截例外會導致 Telegram 自動重送同一則訊息、加速燒額度；新增 FR-7（暫時性安全網）：`telegram_webhook()` 包 `try/except`，未預期例外一律 log + 回安全用語 + 仍回 200；這不是完整的 FR-19（robinson SPEC.md），只解決重試風暴這個具體風險，完整版留給 Step 1.6 | Claude（依 Robin「先加上最小安全網」指示） |
