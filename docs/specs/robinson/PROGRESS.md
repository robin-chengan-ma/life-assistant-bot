---
title: Robinson 產品開發階段紀錄
spec: docs/specs/robinson/SPEC.md
updated: 2026-08-02
---

# Robinson 產品開發階段紀錄

> 本文件追蹤「產品階段」層級的進度（Phase 完成度、里程碑、待決事項），細部任務進度請看 [SPEC.md](./SPEC.md) 的 checkbox。每完成一個 Phase 的所有 Step，回來更新本文件的階段狀態與里程碑。

## 專案緣起（Claude Code 協作開始前）

- **2026-07-28**：Robin 自行完成所有外部服務的註冊與 API 金鑰申請、Telegram Bot 基礎設定；並與 Gemini 進行腦力激盪與方案收斂 —— 梳理生活痛點、評估技術可行性、把發散的想法轉化為具體的 PRD（Product Requirement Document）雛形
- **2026-07-29**：正式開始與 Claude Code 協作，產出標準規格書（`docs/specs/robinson/SPEC.md`）與 Codebase 規範等文件

## 目前階段

**Phase 1（MVP）進行中 — Step 1.1、Step 1.2、Step 1.3（Gemini 對話核心）、Step 1.3a（`/function` 改版）、Step 1.3b（影像辨識基礎流程）、Step 1.4（語音轉文字）、Step 1.5（個資偵測與遮蔽機制）、Step 1.6（基礎錯誤處理層）、Step 1.7（待辦事項模組）、Step 1.8（心情小記模組）已完成，下一步 Step 1.9（客訴收集模組）**

## 目標時程（2026-07-30 更新：改為三週制，因新增多模態影像/語音處理架構）

- **Phase 0～4：2026-07-29 ～ 2026-08-18（三週）**，不含 Notion 後台
- **Phase 5（Notion 後台）：2026-08-18 之後再排**

原本兩週＋1 天緩衝（7/29～8/12）的規劃，因本次新增大量架構性內容而順延至三週：① 四把 Gemini Key 依用途分流＋語音改用 Groq Whisper（ADR-12）② 影像/語音「先上雲端、後壓縮、再辨識」的完整處理流程與命名規則（ADR-13）③ `/function` 全面改版為「總覽＋按需深入＋情境範例」＋所有對話回覆需符合人格化語氣（FR-56～FR-56d）④ 影像辨識的個資警語、不確定需詢問、飲食誤差聲明（FR-17～FR-17c）。這些改動主要集中在 Phase 1 Step 1.3（Gemini 對話核心）附近，新增 Step 1.3a／1.3b，工作量顯著增加，Robin 已同意延長至三週（若進度超前則不用真的用滿三週）。

### 建議每日分配（僅供參考，Robin 可依實際進度調整）

| 日期 | 建議內容 |
| --- | --- |
| 7/28（已完成） | 專案緣起：服務註冊/API 申請、Telegram Bot 基礎設定、Gemini 腦力激盪收斂 PRD 雛形（非 Claude Code 協作範圍） |
| 7/29（已完成） | Phase 0：`submodules/` 骨架、規格書初版確認 |
| 7/30（已完成） | Phase 0 全部完成（金鑰串接、DB 建表、`/healthz` 上線、cron-job.org）；Phase 1 Step 1.1（通關密碼驗證＋Owner 設定對話流＋歡迎訊息＋`/rule`／`/function`）完成；新增四把 Gemini Key／Groq Key 與影像/語音處理架構（ADR-12、ADR-13） |
| 7/31 | Step 1.2（功能開關系統） |
| 8/1～8/3 | Step 1.3（Gemini 對話核心＋四把 Key 分流＋人格化語氣）、Step 1.3a（`/function` 改版）、Step 1.3b（影像辨識基礎流程：GDrive 上傳＋Pillow 壓縮＋雙 Key 隨機辨識），內容較多獨立抓 3 天 |
| 8/4 | Step 1.4（語音轉文字改用 Groq Whisper＋GDrive 備份＋10 分鐘上限＋15 分鐘文字修正限制） |
| 8/5 | Step 1.5（個資偵測與刪除機制） |
| 8/6 | Step 1.6（基礎錯誤處理層）＋ Step 1.7（待辦事項模組） |
| 8/7 | Step 1.8（心情小記）＋ Step 1.9（客訴收集），若進度落後可將 Step 1.9 挪到 Phase 2 之後 |
| 8/8～8/9 | Phase 2：記帳、體態管理（含飲食誤差聲明 FR-17c）、重要通知 |
| 8/10～8/11 | Phase 2：Step 2.4～2.6（GitHub PR 自主診斷、重試機制、分級降級），技術複雜度最高，獨立預留兩天 |
| 8/12～8/14 | Phase 3：技能成長（TOEIC 雙軌 Pipeline，語音改用 Groq Whisper）＋ YouTube 技術情報模組 ＋ 好友模式 |
| 8/15～8/16 | Phase 4：104 求職爬蟲＋整合測試 |
| 8/17～8/18 | 全 Phase 整合測試／緩衝日 |
| 8/18 之後 | Phase 5：Notion 後台 |

## 階段總覽

| Phase | 內容 | 狀態 | 目標日期 | 備註 |
| --- | --- | --- | --- | --- |
| Phase 0 | 專案基礎建設（repo 結構、金鑰串接、Render/Neon/cron-job、DB 初始化） | 🟢 已完成 | 7/29～7/30 | 全部 Step 完成：`submodules/`、`src/schema/`、`src/migrations/`（ADR-11）骨架就緒；`/healthz` 已部署上線並掛上 cron-job.org；第一批 5 張表（`users`／`invite_codes`／`knowledge_base`／`conversation_logs`／`feature_toggles`）已核准並套用成功 |
| Phase 1（MVP） | 核心平台（通關密碼對話式設定、歡迎訊息、`/rule`／`/function`／`/complaint` 內建指令、功能開關、Gemini 對話+知識庫、影像辨識、語音、個資遮蔽、基礎錯誤處理）＋待辦事項＋心情小記＋客訴收集 | 🟡 進行中 | 7/31～8/7 | Step 1.1、1.2、1.3、1.3a、1.3b、1.4、1.5、1.6、1.7、1.8 完成；FR-56 全面改版為總覽＋按需深入＋情境範例（FR-56a～FR-56d） |
| Phase 2 | 記帳＋體態管理＋重要通知＋異常自主診斷與 GitHub PR 治理＋重試機制＋分級降級 | ⚪ 未開始 | 8/8～8/11 | Step 2.4～2.6 為新增範圍，技術複雜度最高，已獨立預留兩天；體態模組飲食分析需附誤差聲明（FR-17c） |
| Phase 3 | 個人技能成長（TOEIC 雙軌題庫 Pipeline＋YouTube 技術情報模組，僅 Robin）＋好友模式 | ⚪ 未開始 | 8/12～8/14 | 新增 YouTube 模組（FR-57～FR-59，見 ADR-9）；TOEIC 語音處理改用 Groq Whisper（ADR-12） |
| Phase 4 | 求職模組（104 爬蟲＋評分） | ⚪ 未開始 | 8/15～8/16 | 爬蟲策略已定案：每週一次、AJAX API、無登入態、禮貌性延遲、ETL 去重（FR-34a～FR-34d） |
| Phase 5 | Notion 後台 | ⚪ 未開始 | 8/18 之後 | 獨立拆出的最終階段，須等 Phase 0～4（含 FR-19 治理機制）穩定後才開始；期間僅維持資料層 API 抽象化彈性 |

狀態圖例：⚪ 未開始　🟡 進行中／規劃中　🟢 已完成　🔴 阻塞

## 里程碑紀錄

| 日期 | 里程碑 |
| --- | --- |
| 2026-07-28 | 專案緣起：Robin 完成服務註冊/API 金鑰申請、Telegram Bot 基礎設定，與 Gemini 腦力激盪收斂 PRD 雛形 |
| 2026-07-29 | 完成需求彙整，建立 `docs/specs/robinson/SPEC.md`（產品規格書） |
| 2026-07-29 | 建立本開發階段紀錄文件 |
| 2026-07-29 | 調整 FR-15（語音修正限制改為 15 分鐘窗口） |
| 2026-07-29 | 完成 `submodules/` 共用子模組骨架（`neon_postgres`、`telegram_client`、`gemini_client`），新建 [docs/specs/submodules-core/SPEC.md](../submodules-core/SPEC.md) |
| 2026-07-29 | `submodules/` 依 Robin 指定樣板重構：更名為 `llm`/`cloudsql`/`telegram`，統一四檔案結構 |
| 2026-07-29 | 重寫 FR-19：錯誤處理擴充為 5 步驟自主診斷流程（新增 ADR-7），Phase 1 範圍縮小、AI 診斷延後至 Phase 2 |
| 2026-07-30 | **7 項待確認事項全數回覆，Phase 1 正式解除阻塞**：MVP 分期（同意）、通關密碼設定改為 Owner 對話流（新增 FR-6a～FR-6c、ADR-8）、TOEIC 雙軌 Pipeline（新增 FR-25a～FR-25f）、104 爬蟲技術細節定案（新增 FR-34a～FR-34c，頻率改每週一次）、Notion 拆為獨立 Phase 5、個資遮蔽規則細化（新增 FR-13a～FR-13d）、FR-19e 執行機制定案為 GitHub PR 治理模式 |
| 2026-07-30 | 新增 FR-19f～FR-19i（例外分級降級「一般感冒級/重大疾病級」、決策執行狀態閉環回饋、外部 API 重試機制）與 NFR-9、NFR-10；FR-19d 補充「程式碼異動紀錄」要求 |
| 2026-07-30 | 新增 `docs/profile/Robinson.png`（Robinson 大頭照，**永久禁止刪除**），已記錄於 SPEC.md「重要資產」章節 |
| 2026-07-30 | 新增 `GITHUB_TOKEN`／`GITHUB_REPO` 至 `.env.example`，同步更新 NFR-5 |
| 2026-07-30 | 新增 FR-6d（通關密碼驗證成功歡迎訊息）、FR-55（`/rule` 路由）、FR-56（`/function` 路由）；新增「附錄 A：規範文本」存放固定歡迎訊息全文；`/function` 的實際文字模板因尚未有產品原型暫緩，記錄於附錄 B 待補清單 |
| 2026-07-30 | 補上「專案緣起」段落（見上方，2026-07-28 的 Robin 個人準備工作）；目標時程由一週改為兩週，Phase 5（Notion）順延至 8/11 之後 |
| 2026-07-30 | 新增「YouTube 技術情報模組」（FR-57～FR-59、ADR-9）：每週四自動推播 Top 3 技術影片，三層輕量篩選（格式過濾/相關度評分/歷史去重），配額 100 Units/次、每日上限 1,000 Units；新增 NFR-11 排程 ETL 去重通則，回頭補上 FR-34d（104 職缺 ETL 去重）；新增 `YOUTUBE_API_KEY` 金鑰 |
| 2026-07-30 | Phase 3 因新增 YouTube 模組由 2 天延長為 3 天（8/7～8/9），Phase 4／緩衝日順延 1 天，Phase 5（Notion）目標日期改為 8/12 之後 |
| 2026-07-30 | 概要新增「使用性質聲明」（個人非商業用途），新增 NFR-13 |
| 2026-07-30 | 新增 ADR-10（資料庫 Schema 建立採先審核後執行流程）與 NFR-12；建立 `src/schema/db_schema.md`、`src/schema/api_schema.md` 骨架；Phase 0 新增 Step 0.1b（已完成），Step 0.5 改為依 ADR-10 流程逐一審核建表 |
| 2026-07-30 | 新增客訴收集功能 FR-60～FR-63：`/complaint` 路由、客訴內容記錄、Gemini 分析私訊 Robin、Robin 人工決策；Phase 1 新增 Step 1.9 |
| 2026-07-30 | 附錄 A 開頭語句改為「📋 以下是羅賓森的使用須知：」（原「🎉 通關密碼驗證成功！」在 `/rule` 場景語意不通順），並補上「我要客訴你」觸發提示 |
| 2026-07-30 | Phase 0 啟動連線驗證時，測試腳本意外將 `TELEGRAM_BOT_TOKEN`、`YOUTUBE_API_KEY` 明文印出於對話紀錄中（原因：`requests` 例外訊息包含完整請求 URL，兩者金鑰恰好嵌在 URL 裡）；Robin 已於當天完成兩把金鑰重新產生，逐項覆核確認無其他金鑰外洩（`ROBIN_TELEGRAM_TOKEN` 部分曝光但經 Robin 確認為 Telegram 使用者 ID、非機密憑證，且僅曝光數字 ID 本身）；已修正 `submodules/telegram/README.md` 對 `ROBIN_TELEGRAM_TOKEN` 用途的錯誤描述 |
| 2026-07-30 | 發現 Cowork sandbox 對外部服務有網路白名單限制：連不到 Neon／Telegram／`api.github.com`／Google 與 YouTube API／Notion API；但 `github.com`（git 協定）可連線，並實測 `git push`（搭配 `GITHUB_TOKEN` + credential helper）可成功。新增 ADR-11：ADR-10 的執行機制改為「提出 SQL → Robin 同意 → Claude 建立 `src/migrations/` 檔案並 commit+push → Render 偵測 main 分支自動部署 → `main.py` 開機自動套用」；Robin 確認 Render 已開啟 push-to-main 自動部署，此方案可行；Phase 0 新增 Step 0.5a |
| 2026-07-30 | Step 0.5a 完成：建立 `src/migrations/`（runner.py + README）、`CloudSQLClient` 新增 `execute()`、`main.py` 整合開機自動套用；完成首次 commit + push 到 GitHub main（`5f60602..776802f`），觸發 Render 自動部署，待 Robin 於 Render 確認 `/healthz` 可正常連線後即完成 Step 0.3 |
| 2026-07-30 | Step 0.3 完成：Robin 於 Render Dashboard 確認部署成功（`Your service is live`），正式網址 `https://life-assistant-bot-yhkm.onrender.com`；下一步由 Robin 把 `/healthz` 端點加到 cron-job.org（Step 0.4） |
| 2026-07-30 | Step 0.4 完成：Robin 已於 cron-job.org 設定每 10 分鐘呼叫 `/healthz`，確認 API 正常。**Phase 0 僅剩 Step 0.5（Neon 資料庫初始化）**，其餘全數完成 |
| 2026-07-30 | Step 0.5 第一批 5 張表核准並 push：`users`／`invite_codes`／`knowledge_base`／`conversation_logs`／`feature_toggles`（`776802f..e440b7c`），已記錄到 `src/schema/db_schema.md`；ADR-10 新增第 5 點：所有建表 SQL 必須用 `COMMENT ON TABLE`／`COMMENT ON COLUMN` 附中文說明 |
| 2026-07-30 | Robin 於 Render 部署 log 確認 5 筆 migration 全數套用成功（`0001`～`0005` 皆有「套用／完成」紀錄）。**Phase 0（專案基礎建設）全部 Step 完成**：Step 0.1～0.1b、0.2～0.5 皆已完成，可正式進入 Phase 1（MVP） |
| 2026-07-30 | **Phase 1 Step 1.1 完成**：通關密碼驗證、Owner `/set_invite_codes` 對話式設定流程、FR-6d 歡迎訊息、`/rule`／`/function` 內建指令，展開為獨立 [docs/specs/platform-auth/SPEC.md](../platform-auth/SPEC.md)；新增 ADR-1（webhook 改用原生 JSON 解析、移除 `python-telegram-bot`）、ADR-2（對話狀態存記憶體不落地資料庫）；新增 `src/bot/`（`state.py`／`auth.py`／`templates.py`／`commands.py`／`router.py`／`webhook.py`），49 個測試全過、覆蓋率 100%；新增 `requirements-dev.txt`／`pytest.ini` |
| 2026-07-30 | 測試通過後，Robin 提出多模態與人格化語氣的大改版需求：新增四把 Gemini Key＋Groq `VOICE_API_KEY`（ADR-12，語音改用 Groq Whisper，取代 FR-25b 原「一律用 Gemini」決策）；新增 ADR-13（影像/語音先上雲端、`Pillow` 壓縮、統一命名、URL 入庫）；FR-17 開放一般圖片辨識並新增個資警語/不確定需確認/飲食誤差聲明（FR-17a～FR-17c）；FR-56 全面改版為總覽＋按需深入＋情境範例（FR-56a～FR-56d，記帳範例已由 Robin 提供）；`src/bot/templates.py` 附錄 A 文字同步更新；新增 `src/migrations/0006_seed_persona_and_family_knowledge.sql` 寫入 Robinson 人格背景與家人背景資料；時程由兩週延長為三週（8/12 → 8/18），Phase 1 目標日期順延至 8/7 |
| 2026-07-30 | Robin 確認 Render 部署 log 顯示 `0006` migration 套用成功，Robinson 人格背景與 Robin 家人背景已寫入 Neon `knowledge_base` 表，供未來人格化回覆（FR-56c）讀取 |
| 2026-07-30 | Robin 確認 Step 1.2 功能開關權限模型（FR-2a：使用者可自管、Owner 可代管），展開為獨立 [docs/specs/feature-toggles/SPEC.md](../feature-toggles/SPEC.md)（ADR-1：對話狀態 dict 新增 `flow` 欄位）；**Phase 1 Step 1.2 完成**：新增 `src/bot/toggles.py`、`/my_toggles`（自管）、`/set_toggle`（Owner 代管）；家人第一次綁定成功時自動建立 8 筆預設開啟的 `feature_toggles`；`src/bot/` 全部 78 個測試全過、覆蓋率 100% |
| 2026-07-31 | Robin 確認查無答案時採「單次 API 呼叫＋Google Search grounding」（見 chat-core SPEC.md ADR-1），展開為獨立 [docs/specs/chat-core/SPEC.md](../chat-core/SPEC.md)（ADR-2：`pending_kb_save` 狀態流程）；**Phase 1 Step 1.3 完成**：一般聊天訊息正式交給 Gemini 處理（取代 `_PLACEHOLDER_REPLY`），新增 `src/bot/knowledge.py`（知識庫查詢/寫入、資安隔離）、`src/bot/chat.py`（對話核心、存檔確認流程），`submodules/llm/client.py` 新增 `generate_with_search()` 並補上單元測試；全專案 104 個測試全過、覆蓋率 100% |
| 2026-07-31 | Robin 指出短記憶會忘記久遠對話，確認記憶架構改為「長記憶＋短記憶＋知識庫＋上網查資料」四部分並核准 `conversation_summaries` 建表 SQL；新增 ADR-3（滾動式摘要）：新增 `src/bot/memory.py`（backlog ≥10 則觸發、呼叫 `GEMINI_API_TEXT_KEY`），`chat.py`／`router.py`／`webhook.py` 整合第二把 Gemini Key；全專案 117 個測試全過、覆蓋率 100% |
| 2026-07-31 | Robin 提供待辦事項／求職／體態管理／心情小記情境範例（新增 FR-56e～FR-56h），補充 FR-31a（待辦逾期標記）與 FR-46（身高體重合理範圍檢查）業務規則 |
| 2026-07-31 | **Phase 1 Step 1.3a 完成**：`/function` 重新實作為「總覽＋按需深入＋情境範例」，展開為 chat-core SPEC.md FR-9／ADR-4（總覽獨立小型 LLM 呼叫，細節追問併入既有聊天核心，Robin 確認）；`commands.handle_function()` 改為 LLM 人格化總覽，`chat.py` prompt 固定附上功能手冊（含 FR-56d～FR-56h 情境範例）供按需回答；全專案 126 個測試全過、覆蓋率 100% |
| 2026-07-31 | Robin 實測撞到 Gemini 429，發現 `webhook.py` 未攔截例外會讓 Telegram 重試風暴加速燒額度，新增 platform-auth SPEC.md FR-7（安全網：`try/except` + 固定安全用語 + 仍回 200） |
| 2026-07-31 | Robin 要求「該做的防呆要做好」，再補兩層防護：platform-auth SPEC.md FR-7a（`update_id` 去重，防止「沒出錯但被誤判逾時重送」重複打 Gemini）與 submodules-core SPEC.md FR-7／ADR-5（`LLMClient` 本地端節流保護，同一 `api_key` 最近 60 秒超過 8 次呼叫直接擋下不送出請求）；全專案 137 個測試全過、覆蓋率 100% |
| 2026-07-31 | Robin 確認 429 為真實額度超限（安全網運作正常），並確認 Step 1.3b 設計：`media_uploads` 表統一記錄圖片/語音 Drive 網址、壓縮版圖片僅記憶體內處理不落地存 Drive（修正 ADR-13）；建立 `media_uploads` migration 並 push |
| 2026-07-31 | **Phase 1 Step 1.3b 完成**：影像辨識基礎流程，FR-17／FR-17a～FR-17c 全數完成；新增 `submodules/gdrive/`（僅上傳、Service Account 認證）、`TelegramClient.get_file_bytes()`、`src/bot/image.py`（`Pillow` 壓縮＋隨機挑選影像 Key＋`[NEED_CONFIRM]` 標記反問使用者）；`router.py`／`webhook.py` 完成圖片訊息與不支援格式的整合；全專案 179 個測試全過、覆蓋率 100% |
| 2026-07-31 | Robin 換用新產生的 `GEMINI_API_BOT_KEY` 後，`generate_with_search()` 固定使用的 `gemini-2.5-flash` 回傳 404；排查後確認 Gemini 2.5 世代已對新專案關閉存取（用 curl 直測 `generateContent` 驗證，跟掛不掛 Google Search 工具無關），非額度問題；Robin 指示「移除所有會用到上網查詢的部分，查無答案就誠實回不知道，並建議使用者自行查詢後提供答案存檔」；新增 chat-core SPEC.md ADR-5（supersede ADR-1／ADR-2）、submodules-core SPEC.md ADR-8（supersede ADR-7）：`generate_with_search()` 全數移除，`pending_kb_save` 流程更名為 `pending_user_knowledge` 且不再需要 yes/no 確認；全專案 174 個測試全過、覆蓋率 100% |
| 2026-08-01 | Robin 陸續回報並確認多項 chat-core 修正與新功能（日期幻覺、代名詞指涉、打字誤植先反問確認、`/clean-all-dialog`／`/clean-target-dialog`、主動新增知識等，詳見 [chat-core SPEC.md](../chat-core/SPEC.md) 變更記錄 ADR-6～ADR-8），全專案累計到 219 個測試、覆蓋率 100% |
| 2026-08-01 | **Phase 1 Step 1.4 完成**：語音轉文字流程，FR-14／FR-15 全數完成；新增 `submodules/voice/`（`VoiceClient`，`requests` 直打 Groq Whisper OpenAI 相容 REST API，見 submodules-core SPEC.md ADR-9）、`src/bot/voice.py`（10 分鐘上限／15 分鐘修正窗口檢查、上傳 Drive＋轉文字）；架構決策：轉出來的文字直接呼叫既有 `router.handle_message()` 走完整文字流程，不重複指令/對話流程分派邏輯；`src/bot/media.py` 從 `image.py` 抽出共用的 `save_media_upload()`；全專案 252 個測試全過、`src/bot/`／`submodules/llm`／`submodules/voice` 覆蓋率 100% |
| 2026-08-01 | **Step 1.4 追加修正**：Robin 回報「除了照片和音檔外的檔案格式才無效」，發現 Step 1.4 完成當下只處理了 `message.voice`（錄音鍵語音訊息），漏了 `message.audio`（使用者上傳的音檔，如 MP3）——FR-17 原文早就承諾「圖片與音檔兩種檔案類型」都支援，這是範圍沒抓對，不是新功能；修正 `webhook._extract_voice()` 同時偵測 `voice`／`audio` 並透傳 `mime_type`，新增 `voice._infer_extension()` 依實際格式決定 Drive 副檔名與 Groq 轉錄格式，避免把上傳的 MP3/M4A/WAV 誤標成 `.ogg`；全專案 262 個測試全過、`src/bot/`／`submodules/llm`／`submodules/voice` 覆蓋率 100% |
| 2026-08-02 | **新增 FR-16a（語音最終執行確認）**：Robin 問語音轉文字後是直接執行還是會先確認，得知是直接執行後，提出風險情境「語音說 A 決策被聽錯成 B 決策，且已刪除的紀錄無法回頭補上」；選定「復誦＋最終執行前一定要打字答一次」方向，`/clean-all-dialog`／`/clean-target-dialog`／主動記知識三個高風險 flow 新增 `pending_*_final_confirm` 狀態，判定 `CONFIRM` 後不再馬上執行，改為要求逐字打字輸入「確認執行」；語音輸入這一步一律拒絕且不清除狀態，詳見 [chat-core SPEC.md](../chat-core/SPEC.md) ADR-9；全專案 274 個測試全過、覆蓋率 100% |
| 2026-08-02 | **FR-16a 追加優化**：Robin 追問卡在最終確認狀態時收到新語音會如何處理，發現初版是先下載/轉錄才拒絕，浪費 Drive/Groq 額度，確認補上；`handle_voice_message()` 改為在下載/轉錄之前就短路拒絕，完全不消耗額度；全專案 275 個測試全過、覆蓋率 100% |
| 2026-08-02 | **補上 FR-14 規則 1（語音超時全面鎖定）**：Robin 指出印象中 15 分鐘鎖定應該是「單次錄音超過 10 分鐘才觸發」，核對後發現這其實跟 FR-15「修正情境鎖定」是兩條獨立規則，目前只做了後者，前者完全沒實作；確認兩條都要做，新增 `voice.mark_duration_violation()`／`is_locked_out_from_duration_violation()`，`webhook.py` 新增長期持有的 `_voice_lockout_store`；全專案 284 個測試全過、覆蓋率 100% |
| 2026-08-02 | **FR-15 修正窗口主動提醒**：Robin 追問語音功能被限制/恢復時會不會提醒使用者；盤點後發現 FR-14 規則 1 的拒絕回覆已有主動提示，但 FR-15 修正窗口開始當下、鎖定到期時都沒有主動通知（機器人被動回應訊息，沒有排程/推播機制）；Robin 選擇先聚焦較簡單的一項，新增 `router._VOICE_TRANSCRIBED_REMINDER`，語音成功轉出文字後於回覆末尾附註 15 分鐘修正窗口提醒；鎖定到期主動通知維持現狀；全專案 284 個測試全過、覆蓋率 100% |
| 2026-08-02 | **修正 Telegram send_text 400 錯誤 + 排查 gdrive 金鑰路徑**：Robin 實測回報兩個部署後問題：① `/function` 觸發 Telegram `sendMessage` 400 Bad Request，根因是 `send_text()` 預設 `parse_mode="Markdown"`，但 LLM 生成的回覆文字無法保證符合 Telegram 舊版 Markdown 語法，格式不符會整則被拒收——所有 LLM 生成回覆都有此風險，非 `/function` 獨有；Robin 選擇直接關閉 Markdown，改為預設純文字傳送 ② 語音功能因 `GDriveClient` 找不到 Service Account 金鑰檔而失敗，確認是 Robin 把金鑰放在 Render Secret Files（實際掛載路徑 `/etc/secrets/<filename>`），但 `GDRIVE_KEY_FILE_PATH` 環境變數設定的是相對路徑，兩者對不上——純屬 Render 環境變數設定問題，非程式碼錯誤，待 Robin 調整環境變數即可解決；全專案 285 個測試全過、覆蓋率 100% |
| 2026-08-02 | **Phase 1 Step 1.5 完成**：個資偵測與遮蔽機制，FR-13／FR-13a～FR-13d 全數完成，展開為獨立 [docs/specs/privacy-masking/SPEC.md](../privacy-masking/SPEC.md)；Robin 確認語意層 LLM 呼叫改用新申請的專用 Key（`GEMINI_API_PRIVACY_KEY`），不佔用既有聊天配額（吸取先前多次 429 的教訓）；新增 `src/bot/privacy.py`（Regex 硬規則＋LLM 語意雙層防線），整合進一般聊天核心與圖片說明文字，語音因統一轉文字後走既有流程天然涵蓋；`/clean-target-dialog` 的搜尋主題刻意排除遮蔽，避免使用者用個資內容當關鍵字搜尋刪除時功能失效；全專案 326 個測試全過、覆蓋率 100% |
| 2026-08-02 | **gdrive 改用 OAuth 2.0（真人帳號身分）**：Robin 實測語音上傳撞到 Google Drive API `403 storageQuotaExceeded`，查證確認 Service Account 完全沒有 Drive 儲存額度，改用 Shared Drive 需要付費 Google Workspace；經 AskUserQuestion 確認，Robin 選擇改用 OAuth 讓程式以本人身分上傳；`submodules/gdrive/client.py` 建構子改為 `refresh_token`／`client_id`／`client_secret`／`folder_id`，新增一次性本機互動授權腳本 `get_refresh_token.py`；`webhook.py` 兩處建構呼叫與環境變數同步更新；新增 submodules-core SPEC.md ADR-10、robinson SPEC.md ADR-13 補充決策；全專案 329 個測試全過、覆蓋率 100%；**待 Robin 執行的手動步驟**：Google Cloud Console 建立 OAuth 用戶端 ID、發布狀態設為正式版、本機跑 `get_refresh_token.py` 取得 refresh token、設定 Render 環境變數 |
| 2026-08-02 | **Phase 1 Step 1.6 完成**：基礎錯誤處理層，FR-19a／FR-20／FR-21 完成（FR-19b～FR-19i 的 AI 自主診斷／分級降級／重試機制仍留待 Phase 2 Step 2.4～2.6）。經 AskUserQuestion 確認兩個範圍決策：① FR-20 新增 Owner 專屬指令 `/recovered`，Robin 判斷修好後手動觸發，廣播固定文案給所有已綁定家人（排除 Robin 自己）② FR-21 Gemini 免費額度監控 Phase 1 先跳過（官方無查詢即時用量的 API），只做 Neon 容量監控（新增 `src/bot/monitoring.py` 的 `NeonCapacityMonitor`，借用 `/healthz` 既有的 10 分鐘 cron 頻率，達 80% 私訊 Robin、回落後重置避免重複告警）；FR-19a：`webhook.py` 新增 `_notify_robin_of_error()`／`_summarize_user_input()`，例外發生時除了記錄 Traceback＋情境到 log，額外私訊 Robin 完整原始內容；`submodules/cloudsql/client.py` 新增 `execute_query()` 供監控查詢使用；全專案 352 個測試全過、覆蓋率 100% |
| 2026-08-02 | **Phase 1 Step 1.7 完成**：待辦事項模組，FR-31／FR-31a／FR-32 完成。經 AskUserQuestion 確認兩個範圍決策：① 待辦意圖偵測比照 FR-11「主動新增知識」的 LLM 標記模式（新增 `chat.py` 的 `_REQUEST_TODO_MARKER`），符合「自然語言描述」的精神，不用新增固定指令 ② FR-31 跨模組歧義判斷 Phase 1 暫不實作（體態管理／心情小記都還沒做，沒有其他模組可以比較）。新增 `todos` migration（Robin 依 ADR-10 核准）；`src/bot/todo.py` 新增/查詢/標記/逾期/推播判斷純邏輯；新增流程走三輪反問（要不要記錄→什麼時候→要不要提前 30 分鐘提醒），時間解析不清楚時停留原地繼續問；查詢清單「我的待辦事項」／`/my_todos` 後可選編號標記完成/取消；每日 08:00 固定推播與前 30 分鐘提醒比照 Step 1.6 借用 `/healthz` 頻率（`main.py` 新增 `_check_todo_pushes()`），但去重狀態存在 `todos` 資料列本身而非記憶體，跨 Render 重啟仍正確；全專案 391 個測試全過、覆蓋率 100% |
| 2026-08-02 | **Phase 1 Step 1.8 完成**：心情小記模組，FR-49／FR-50 完成。經 AskUserQuestion 確認兩個範圍決策：① 日記內容與 FR-50 個人成就回答都套用 FR-13 個資遮蔽，新增第四個遮蔽入口（跟一般聊天／圖片說明文字／語音轉文字一致）② 新建 `mood_journals` 表（Robin 依 ADR-10 核准）。流程分三輪：「我想做心情筆記」／`/mood_journal` 先問心情分類（固定 6 選一，接受編號或名稱）→ 問日記內容並寫入 → 主動追問 FR-50 個人成就三選一提示（可跳過）；全程不需要 LLM，比 Step 1.7 待辦事項簡單（心情分類固定選項、個人成就有填就存沒填就跳過，純字串比對即可）；新增 `src/bot/mood.py`、`commands.py` 三個新 flow、`router.py` 整合；全專案 409 個測試全過、覆蓋率 100% |

## 待決事項

目前**沒有阻塞 Phase 1 開工的待決事項**。

- [x] 確認外部服務金鑰已全數申請完成（Telegram Bot Token、Neon 連線字串、Google Service Account JSON + Drive Folder ID、Gemini x2 Token、Gmail 帳密、GitHub Personal Access Token、YouTube Data API Key）——已於 `.env` 逐項核對存在；`TELEGRAM_BOT_TOKEN`／`YOUTUBE_API_KEY` 已於本次金鑰外洩事故後重新產生
- [ ] `/function` 路由的實際文字模板（分類方式、每個功能的說明文字、是否附操作提示）待有產品原型後由 Robin 補充，見 SPEC.md 附錄 B（不阻塞 Phase 1，FR-56 可先用最簡單的清單格式實作，之後再美化文案）
- [x] Step 0.5a（`src/migrations/` + migration runner）已實作
- [x] Step 0.4：Robin 已完成 cron-job.org 設定，確認 API 正常

## 下一步

1. **Step 1.9：客訴收集模組**（FR-60～FR-63）—— `/complaint` 路由、客訴內容記錄、Gemini 分析私訊 Robin
2. Phase 1（MVP）核心 Step 全數完成後，進入 Phase 2：記帳＋體態管理＋重要通知＋系統韌性與自主診斷治理
3. 每天對照「建議每日分配」檢查進度，落後時 Step 1.9 客訴收集屬次要功能，可延後不必硬趕
