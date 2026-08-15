---
updated: 2026-08-15
---

# 開發進度

> 本檔案整併自兩份舊紀錄：`docs/specs/_archive/robinson/PROGRESS.md`（Claude Code 協作的產品階段里程碑）與 `docs/specs/_archive/codex.md`（Codex 開發異動紀錄，內容集中在 Mobile App）。
> 「開發者」欄依內容來源判斷：Claude Code 協作里程碑標 `Claude`、codex.md 工作階段標 `Codex`、Claude Code 協作開始前由 Robin 自行完成的項目標 `Robin`。
> 除錯敘事（現象／根因／修復／驗證）已拆到 `docs/ADR/debug/`，決策脈絡已拆到 `docs/ADR/discuss/`，本檔只保留「哪一天、做了什麼、誰做的、狀態」。

## 時程與任務狀態

| 日期 | 對應 FR | 任務內容 | 開發者 | 狀態 | 備註 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-15 | FR-6h／NFR-19 | 補正 Mobile 日期特例並定案 Telegram 重構採漸進式資料遷移，不整庫刪除重建 | Codex | 已定案／待開發 | Mobile 不限今日範圍包含待辦、重要日子、收藏、旅遊、探索、成果；先做唯讀 Schema／引用盤點，必要時採 V2 表回填切換，未執行 Migration 或刪表 |
| 2026-08-15 | FR-3～FR-6h／FR-9c～FR-9d／FR-20a／FR-72b／NFR-18 | 定案 Telegram 角色選單、帳號安全、歷史 CRUD、統一功能流程、七日查詢、排程通知與 Phase 6 執行順序 | Codex | 已定案／待開發 | 查詢由最終日期往前推 6 天且可跨多模組；Mobile 仍只異動今日生活紀錄，Telegram 負責歷史回補；隱私遮罩改帳號層雙端共用；草稿保留 30 分鐘、功能模式 10 分鐘 |
| 2026-08-15 | FR-3～FR-6h | Phase 6 第二批（Telegram 選單與狀態機）開工前盤點：確認現況無 `/start`、無按鈕基礎設施、`state.flow` 約 85 種、`/set_invite_codes` 移除範圍，並拆出子批次 2a／2b... | Claude | 完成（純盤點與拆批決策，未開工） | 決策記錄見 `docs/ADR/discuss/robinson.md` 2026-08-15「Phase 6 第二批拆批盤點」；2a＝按鈕基礎設施＋選單骨架＋認證選單化（含移除 `/set_invite_codes`），2b 起才逐批遷移既有 85 個 flow |
| 2026-08-15 | FR-3／FR-4／FR-4a～FR-4d／FR-5／FR-6a～FR-6e | Phase 6 第二批 2a 實作完成：Telegram 按鈕基礎設施（`reply_markup`／`answer_callback_query`）、`webhook.py` callback_query 解析與分派、`menu.py` 選單骨架、`/start` 正式實作、Owner 權限管理選單化並移除 `/set_invite_codes` | Claude | 實作完成（待 Robin commit／push／實機驗收） | 完整設計內容見 `docs/ADR/discuss/robinson.md` 2026-08-15「Phase 6 第二批 2a 實作計畫」及「開工完成」補述；主選單其餘 7 項（日常紀錄／資料查詢／待辦事項／重要日子／收藏與旅遊／成果展示／排程設定）2a 先回覆「功能開發中」，實際邏輯留給 2b 起逐批接上；新增 `tests/bot/test_menu.py`、擴充 `test_router.py`／`test_commands.py`／`test_webhook.py`／`tests/submodules/telegram/test_client.py`，Claude 沙箱 1716 項全過，Robin 本機 1750 項通過／3 項失敗（`test_toeic.py` 因本機未裝 `ffmpeg`，屬既有環境問題，與本批無關） |
| 2026-08-15 | FR-77／NFR-14～NFR-15 | 定案取消功能的路由／資料表清理，以及 backend／mobile／data／submodules 責任分工 | Codex | 已定案／待開發 | 第一批淘汰 complaints、knowledge_base、conversation_logs、conversation_summaries；Mobile 維持根目錄，Telegram 與 LLM 歸後端，獨立爬蟲歸 data，第一階段不開 schemas；AGENTS 已分列實際現況與 Phase 6 目標 |
| 2026-08-15 | FR-19k | 定案 Owner 錯誤通知的 Telegram／Email／未送達狀態追蹤與系統錯誤管理呈現 | Codex | 已定案／待開發 | Email 成功不重複通知；雙重失敗只保留錯誤紀錄與 Log；不適用一般使用者推播 |
| 2026-08-15 | FR-1～FR-4（功能開關） | 將技術分享、求職分析、考試成績改為 Robin／Owner 永久專屬，取消非管理者授權與個別排程設計 | Codex | 已定案／待開發 | 一般使用者 Telegram／Mobile 不顯示入口且後端拒絕存取；Mobile 另需同步角色顯示、移除客訴入口、成果候選跨端狀態及系統錯誤送達狀態；既有資料保留 |
| 2026-08-15 | FR-19h～FR-20／FR-45／FR-72a／FR-74b／FR-76 | 定案 Telegram 主動推播邊界、重要日子統一提醒、成果候選雙端確認，以及 Owner 異常／康復通知規則 | Codex | 已定案／待開發 | 保留待辦、重要日子、月底月報、預算 50%／80%、低頻非同步結果與三項授權功能推播；取消日常紀錄催促及重複操作成功通知 |
| 2026-08-15 | FR-6c | 定案 Telegram 功能模式切換、10 分鐘逾時、草稿保護與功能名稱確認入口 | Codex | 已定案／待開發 | 權限檢查套用選單、Callback、文字／語音名稱偵測與模式切換 |
| 2026-08-15 | FR-4～FR-8／FR-10～FR-12 | 停用持久化家庭／個人知識庫、逐則對話與長記憶，改用靜態人格 Prompt 及 10 分鐘記憶體上下文 | Codex | 已定案／待開發 | 對應路由、流程與三張資料表已納入 FR-77 Phase 6 清理；DROP 前仍須完成依賴、備份與回滾審核 |
| 2026-08-15 | FR-2／FR-9a／FR-9b | 縮限 Telegram 一般對話為個人資料彈性查詢、內容整理分析及功能導引；正式資料異動一律走選單 | Codex | 已定案／待開發 | 持久化知識庫與對話記憶已另行定案停用，只保留 10 分鐘記憶體上下文 |
| 2026-08-15 | FR-6a／FR-6b | Telegram 除 `/start` 外全面取消 Slash Commands，所有一般與 Owner 操作改由權限化選單及引導式對話 | Codex | 已定案／待開發 | 不保留舊指令相容期；自然語言／語音功能名稱確認入口仍保留 |
| 2026-08-15 | FR-5／FR-6／FR-56 | Telegram「使用規則」改為固定模板選單並精簡文案；取消 `/function` 與功能總覽／細節追問 | Codex | 已定案／待開發 | 精簡模板沿用於首次綁定歡迎，刪除條目後重新連號 |
| 2026-08-15 | | 建立新專案與未來新功能的資料模型準則，並明定本專案既有表不因整理目的刪除重建 | Codex | 完成 | 同步 AGENTS、通用 Template 與 DB Schema Reference；純文件治理，未執行 Migration |
| 2026-08-15 | FR-2～FR-4／FR-4a～FR-4d | Phase 6 第一批（認證／使用者綁定）：新增 `nickname`／`family_title`／`is_active`、通關密碼 24 小時到期與 5 次錯誤鎖定 30 分鐘、`create_user_and_invite()`／`resend_passcode()`／`set_user_active()` | Claude | 完成（已部署／實機驗收） | 範圍刻意只做後端資料模型與核心驗證邏輯，Owner「權限管理」選單化流程延後到下一批（Telegram 選單與狀態機）一起做，避免與選單重構混在同一不可回退批次；`try_bind_invite_code()` 對外行為相容，`router.py` 呼叫端未變動；鎖定計數存 process 記憶體不落地（理由見 db_schema.md 0083 條目）；新增 `tests/bot/test_auth.py` 27 項測試全數通過，Robin 本機亦已覆核通過。**2026-08-15 追加修正**：`0083` 把 `invite_codes.expires_at` 改 NOT NULL 後，發現既有 `/set_invite_codes` 指令流程（`src/bot/commands.py`）未帶該欄位會直接寫入失敗，已補上 `expires_at`／`family_title`／`is_active`，屬本批次內部迴歸修正，未變更該指令對外行為。**2026-08-15 Robin 實機確認**：Render 部署後 Migration `0083` 已自動套用，`/set_invite_codes` 寫入正常、家人帳號輸入密碼綁定成功 |
| 2026-08-15 | FR-60～FR-63 | 原「使用者建檔與移除客訴」條目拆分：客訴入口、API、流程與資料表清理保留在 FR-77 Phase 6 統一清理範圍，不併入本批 | Claude | 待開發 | 見 FR-77 那筆任務 |
| 2026-08-14 | FR-64／FR-65 | 修復重要日子家庭成員查詢與求職分析契合度欄位錯置 | Codex | 完成（已部署驗收） | 使用者 ID 改由 `users.id` 動態產生；求職 SQL 改讀 `score AS match_score`；2026-08-15 Robin 已確認正式環境功能正常 |
| 2026-08-14 | FR-72a／FR-74／FR-75 | 探索篩選與定位提示、旅遊行程今日標示、重要日子載入相容修正及目標日期同步 | Codex | 完成（已部署驗收） | `0082` 體態／證照目標的重要日子關聯與既有資料回填已部署；2026-08-15 Robin 已確認功能正常 |
| 2026-08-14 | FR-73／FR-75 | 收藏地址選填、漸進式近似定位及收藏操作按鈕修復 | Codex | 完成（已實機驗收） | 地址定位、區域 fallback 與跨平台確認 Modal 已於 2026-08-15 由 Robin 確認正常 |
| 2026-08-14 | FR-73～FR-76a | 收藏清單／旅遊行程／探索地圖／成果展示 Phase 5 實作 | Codex | 完成（已部署／實機驗收） | `0079`～`0080`、生活探索 API／Service、Mobile 畫面、記帳關聯與 Nominatim 已部署，2026-08-15 Robin 確認功能正常 |
| 2026-08-14 | FR-75 | 完成 Nominatim 地址轉座標、快取、頻率限制及探索重新定位 | Codex | 完成（已部署驗收） | 正式環境已設定 Nominatim 識別 User-Agent；2026-08-15 Robin 已確認定位與探索功能正常 |
| 2026-08-14 | FR-73 | 修復 Mobile App 首頁「新增收藏」Modal 在手機窄螢幕跑版 | Codex | 完成（已實機驗收） | 選項換行、捲動區與底部按鈕間距已於 2026-08-15 由 Robin 確認正常 |
| 2026-08-14 | FR-73～FR-75 | 收藏地點組合選單、固定捲動區、行程目的地過濾、重要日子同步與探索刪除修正 | Codex | 完成（已部署／實機驗收） | `0081` 已部署；組合選單、固定捲動區、目的地過濾、行程行事曆、重要日子同步與探索刪除已於 2026-08-15 確認正常 |
| 2026-08-14 | FR-69／FR-70／FR-71 | 正式取消 Mobile App 目標與指標設定、功能開關頁及 Robin 專屬排程設定，從 SPEC 與 Roadmap 移除 | Codex | 已取消 | 既有 Telegram 設定流程不受影響；見 DRAFT 與 mobile-app ADR |
| 2026-08-14 | | 專案開發治理規則統一：AGENTS／Template 補齊文件生命週期、commit 同步、ADR／Reference 規範，並修正 `.claude/` 指令與代理規則漂移 | Codex | 完成 | 純文件治理；不需程式測試 |
| 2026-07-28 | | 專案緣起：完成外部服務註冊／API 金鑰申請、Telegram Bot 基礎設定，與 Gemini 腦力激盪收斂 PRD 雛形 | Robin | 完成 | Claude Code 協作開始前 |
| 2026-07-29 | | 完成需求彙整，建立產品規格書 `docs/specs/robinson/SPEC.md` | Claude | 完成 | 里程碑 |
| 2026-07-29 | | 建立開發階段紀錄文件 PROGRESS.md | Claude | 完成 | 里程碑 |
| 2026-07-29 | FR-15 | 調整語音修正限制為 15 分鐘窗口 | Claude | 完成 | 里程碑 |
| 2026-07-29 | | 完成 `submodules/` 共用子模組骨架（`neon_postgres`／`telegram_client`／`gemini_client`），新建 submodules-core SPEC | Claude | 完成 | 里程碑 |
| 2026-07-29 | | `submodules/` 依指定樣板重構為 `llm`／`cloudsql`／`telegram`，統一四檔案結構 | Claude | 完成 | 里程碑 |
| 2026-07-29 | FR-19 | 重寫 FR-19：錯誤處理擴充為 5 步驟自主診斷流程（ADR-7），AI 診斷延後至 Phase 2 | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-6a～FR-6c | 7 項待確認事項全數回覆，Phase 1 解除阻塞；通關密碼設定改為 Owner 對話流 | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-19f～FR-19i | 新增例外分級降級、決策執行狀態閉環回饋、外部 API 重試機制與 NFR-9／NFR-10 | Claude | 完成 | 里程碑 |
| 2026-07-30 | | 新增 `docs/profile/Robinson.png`（永久禁止刪除），記錄於 SPEC「重要資產」章節 | Claude | 完成 | 里程碑 |
| 2026-07-30 | | `.env.example` 新增 `GITHUB_TOKEN`／`GITHUB_REPO`，同步更新 NFR-5 | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-6d／FR-55／FR-56 | 新增驗證成功歡迎訊息、`/rule` 與 `/function` 路由；新增附錄 A 規範文本 | Claude | 完成 | 里程碑 |
| 2026-07-30 | | 補上「專案緣起」段落；目標時程由一週改為兩週 | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-57～FR-59 | 新增 YouTube 技術情報模組（ADR-9）：每週四推播 Top 3 技術影片、三層輕量篩選 | Claude | 完成 | 里程碑 |
| 2026-07-30 | | Phase 3 因 YouTube 模組由 2 天延長為 3 天，Phase 4／緩衝日順延 1 天 | Claude | 完成 | 里程碑 |
| 2026-07-30 | NFR-13 | 概要新增「使用性質聲明」（個人非商業用途） | Claude | 完成 | 里程碑 |
| 2026-07-30 | NFR-12 | 新增 ADR-10（Schema 先審核後執行）；建立 `db_schema.md`／`api_schema.md` 骨架 | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-60～FR-63 | 新增客訴收集功能（`/complaint` 路由、內容記錄、Gemini 分析私訊、人工決策），Phase 1 新增 Step 1.9 | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-55 | 附錄 A 開頭語句改為「📋 以下是羅賓森的使用須知：」 | Claude | 完成 | 里程碑 |
| 2026-07-30 | | 金鑰外洩事故處理：測試腳本將 `TELEGRAM_BOT_TOKEN`／`YOUTUBE_API_KEY` 明文印出於對話紀錄，金鑰已重新產生 | Claude | 完成 | 里程碑／事故 |
| 2026-07-30 | | 發現 Cowork sandbox 對外部服務有網路白名單限制（連不到 Neon／Telegram／Google／Notion API） | Claude | 完成 | 里程碑 |
| 2026-07-30 | | Step 0.5a 完成：建立 `src/migrations/`、`CloudSQLClient.execute()`、開機自動套用 migration | Claude | 完成 | 里程碑 |
| 2026-07-30 | | Step 0.3 完成：Render 部署成功並取得正式網址 | Claude | 完成 | 里程碑 |
| 2026-07-30 | | Step 0.4 完成：cron-job.org 每 10 分鐘呼叫 `/healthz` | Claude | 完成 | 里程碑 |
| 2026-07-30 | | Step 0.5 第一批 5 張表核准並 push（`users`／`invite_codes`／`knowledge_base`／`conversation_logs`／`feature_toggles`） | Claude | 完成 | 里程碑 |
| 2026-07-30 | | Render 部署 log 確認 `0001`～`0005` migration 全數套用，Phase 0 全數完成 | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-6d | Phase 1 Step 1.1 完成：通關密碼驗證、Owner `/set_invite_codes` 對話流、歡迎訊息、`/rule`／`/function` | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-17／FR-56 | 多模態與人格化語氣大改版：四把 Gemini Key＋Groq `VOICE_API_KEY`（ADR-12、ADR-13） | Claude | 完成 | 里程碑 |
| 2026-07-30 | | `0006` migration 套用成功，Robinson 人格背景與家人背景寫入 `knowledge_base` | Claude | 完成 | 里程碑 |
| 2026-07-30 | FR-2a | 確認 Step 1.2 功能開關權限模型（使用者自管、Owner 代管），展開獨立 feature-toggles SPEC | Claude | 完成 | 里程碑 |
| 2026-07-31 | | 確認查無答案採「單次 API 呼叫＋Google Search grounding」，展開獨立 chat-core SPEC | Claude | 完成 | 里程碑 |
| 2026-07-31 | | 記憶架構改為「長記憶＋短記憶＋知識庫＋上網查資料」，核准 `conversation_summaries` 建表 | Claude | 完成 | 里程碑 |
| 2026-07-31 | FR-56e～FR-56h | 補上待辦／求職／體態管理／心情小記情境範例，補充 FR-31a、FR-46 | Claude | 完成 | 里程碑 |
| 2026-07-31 | FR-9 | Phase 1 Step 1.3a 完成：`/function` 改為總覽＋按需深入＋情境範例（ADR-4） | Claude | 完成 | 里程碑 |
| 2026-07-31 | FR-7 | 實測撞到 Gemini 429，`webhook.py` 未攔截例外造成 Telegram 重試風暴，新增安全網 | Claude | 完成 | 里程碑 |
| 2026-07-31 | FR-7a | 追加兩層額度防護（`update_id` 去重、本地端節流） | Claude | 完成 | 里程碑 |
| 2026-07-31 | FR-17 | 確認 429 為真實額度超限；確認 Step 1.3b 設計（`media_uploads` 表統一記錄圖片／語音 Drive 網址） | Claude | 完成 | 里程碑 |
| 2026-07-31 | FR-17／FR-17a～c | Phase 1 Step 1.3b 完成：影像辨識基礎流程，新增 `submodules/gdrive/` | Claude | 完成 | 里程碑 |
| 2026-07-31 | | `GEMINI_API_BOT_KEY` 換新後 `gemini-2.5-flash` 回傳 404，排查並確認 Gemini 2.5 世代模型可用性 | Claude | 完成 | 里程碑 |
| 2026-08-01 | FR-11／FR-12 | chat-core 多項修正與新功能（日期幻覺、代名詞指涉、打字誤植先反問、`/clean-all-dialog`／`/clean-target-dialog`） | Claude | 完成 | 里程碑 |
| 2026-08-01 | FR-14／FR-15 | Phase 1 Step 1.4 完成：語音轉文字流程，新增 `submodules/voice/`（Groq Whisper） | Claude | 完成 | 里程碑 |
| 2026-08-01 | FR-14 | Step 1.4 追加修正：補上 `message.audio`（上傳音檔）支援 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-16a | 新增語音最終執行確認關卡，防聽錯誤觸不可逆操作 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-16a | 追加優化：最終確認狀態收到新語音一律短路，避免浪費 Drive／Groq 額度 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-14 | 補上 FR-14 規則 1：單次語音超過 10 分鐘才觸發 15 分鐘全面鎖定 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-15 | 語音功能被限制／恢復時主動提醒使用者（修正窗口提醒） | Claude | 完成 | 里程碑 |
| 2026-08-02 | | 修正 Telegram `send_text` 400 錯誤，並排查 gdrive 金鑰路徑問題 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-13／FR-13a～d | Phase 1 Step 1.5 完成：個資偵測與遮蔽機制，展開獨立 privacy-masking SPEC | Claude | 完成 | 里程碑 |
| 2026-08-02 | | gdrive 改用 OAuth 2.0（真人帳號身分），解決 Drive `403 storageQuotaExceeded` | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-19a／FR-20／FR-21 | Phase 1 Step 1.6 完成：基礎錯誤處理層 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-31／FR-31a／FR-32 | Phase 1 Step 1.7 完成：待辦事項模組 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-49／FR-50 | Phase 1 Step 1.8 完成：心情小記模組 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-60～FR-63 | Phase 1 Step 1.9 完成：客訴收集模組，Phase 1（MVP）全數完成 | Claude | 完成 | 里程碑 |
| 2026-08-02 | | Bug 修正：「完全不理我」空回覆防呆 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-31 | Bug 追加修正（上一輪非真正主因）＋兩個待辦事項問題 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-31b | 新增待辦事項支援時間區間 | Claude | 完成 | 里程碑 |
| 2026-08-02 | FR-49 | 心情小記擴充補記／更新／刪除 | Claude | 完成 | 里程碑 |
| 2026-08-04 | FR-41～FR-44 | Phase 2 Step 2.1 完成：記帳模組（Phase 1 全數完成，進入 Phase 2） | Claude | 完成 | 里程碑 |
| 2026-08-04 | FR-13 | Bug 修正：個資遮蔽語意層暫時性外部錯誤導致整則訊息完全無回覆 | Claude | 完成 | 里程碑 |
| 2026-08-04 | FR-44a | 記帳模組擴充：月底自動推播月報 | Claude | 完成 | 里程碑 |
| 2026-08-04 | FR-41a／FR-42a | 記帳模組擴充：預算特殊月份覆蓋、每日記帳提醒 | Claude | 完成 | 里程碑 |
| 2026-08-04 | FR-45～FR-48 | Phase 2 Step 2.2 完成：體態管理模組 | Claude | 完成 | 里程碑 |
| 2026-08-04 | | 移除 Notion 後台改採 Mobile App（React Native + Expo），新增 ADR-14 | Claude | 完成 | 里程碑 |
| 2026-08-04 | FR-53 | Phase 2 Step 2.3 完成：重要通知模組（超級重要通知／一般重要通知） | Claude | 完成 | 里程碑 |
| 2026-08-05 | FR-19b | Step 2.4 開工前範疇簡化，新增 ADR-15（supersede ADR-7） | Claude | 完成 | 里程碑 |
| 2026-08-05 | FR-19b | Phase 2 Step 2.4 完成：錯誤 log 雲端連結 | Claude | 完成 | 里程碑 |
| 2026-08-05 | | 新增 ADR-16：Telegram 故障時的 email 備援通知 | Claude | 完成 | 里程碑 |
| 2026-08-05 | FR-66 | 新增 Step 2.7、ADR-17（規格層級）：Google Calendar 整合 | Claude | 完成 | 里程碑 |
| 2026-08-05 | FR-66 | Phase 2 Step 2.7 完成：Google Calendar 整合（家人共用一律免費帳號、唯讀權限） | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-19i | Phase 2 Step 2.5 完成：外部 API 重試機制，新增共用 `submodules/retry` | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-19f～FR-19h | Phase 2 Step 2.6 完成：例外分級降級與決策執行狀態閉環回饋，Phase 2 全數完成 | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-22／FR-23 | Phase 3 Step 3.1 完成：每日重點技術分享 | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-22 | Step 3.1 當日修正：拆成 23:00 收集／08:00 推播兩階段，改用 `skill_growth_digests` 表 | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-2 | 功能開關拆分：`skill_growth` 拆成 `tech_intel`／`certificate`／`language` | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-24／FR-25a～f | Phase 3 Step 3.2 完成：TOEIC 雙軌題庫 Pipeline | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-25 | Step 3.2 當日修正：整包 MP3 切割改為自動判斷開頭有無作答說明語音 | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-25 | Step 3.2 追加：`exam_type` 泛用化，不寫死證照種類清單（ADR-18 決策 4） | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-26～FR-30 | Step 3.3 規格定案（尚未實作），新增 ADR-19 | Claude | 完成 | 里程碑 |
| 2026-08-07 | FR-27 | Step 3.3 第一階段實作：答案照片比對機制＋新資料表 | Claude | 完成 | 里程碑 |
| 2026-08-08 | | Production 事故：`/healthz` 逾時＋Phase 2／3 migration 疑似未套用（大量 `UndefinedColumn`） | Claude | 完成 | 里程碑／事故 |
| 2026-08-08 | | Production 事故根因找到並修復：migration 卡在 `0018` 的 `IndexError` | Claude | 完成 | 里程碑／事故 |
| 2026-08-08 | | Production 事故解決確認：一口氣套用 25 筆待處理 migration | Claude | 完成 | 里程碑／事故 |
| 2026-08-08 | FR-26 | Step 3.3 每日推播／作答細部設計定案，新增 ADR-20 | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-26 | Step 3.3 每日 08:00 推播出題機制實作完成，新增 3 張表 | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-26 | Step 3.3 彈性排程新增第四種語意「平攤」（ADR-20 決策 5／6 補充） | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-46 | Phase 2 體態管理擴充：新增腰圍設定 | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-64a | Phase 4 Mobile App 新增藍牙體重計整合規格（規格層級） | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-27／FR-28 | Step 3.3 作答與批改流程＋20:00 提醒＋彈性排程對話流程實作完成 | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-24／FR-29／FR-30 | Step 3.3 剩餘範圍全數完成（成效彈性文字問答、目標設定與方向建議、正式成績記錄） | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-57～FR-59 | Step 3.4 開工前規格釐清，新增 ADR-21（supersede ADR-9） | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-58a | Step 3.4 再修正：移除「排除 Shorts」規則，改為完全交給 LLM 判讀品質 | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-57～FR-59 | Step 3.4 實作完成：YouTube 技術情報模組全數落地 | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-51／FR-52 | Step 3.5 開工前規格定案，新增 ADR-22 | Claude | 完成 | 里程碑 |
| 2026-08-08 | FR-51／FR-52 | Step 3.5 實作完成：好友模式，Phase 3 全數完成 | Claude | 完成 | 里程碑 |
| 2026-08-08 | | `language`（語言學習）功能規劃決議擱置，新增 ADR-23 | Claude | 完成 | 里程碑；見 `docs/specs/DRAFT.md` 擱置中 |
| 2026-08-08 | FR-33～FR-36 | Step 4.1 開工前規格定案，新增 ADR-24 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-22 | 生產環境回饋修正：`skill_growth_digests` 改為一天多筆、一筆一來源管道，推播改三行式精簡格式（ADR-25） | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-33／FR-36 | Step 4.1 正式開工，完成 Phase A（DB migration）＋Phase B（對話式收集流程） | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-34／FR-35 | Step 4.1 Phase C～F 一次完成：104 爬蟲＋公司背景 Email 協作＋週排程掛載 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-34a | Step 4.1 真實流量驗證完成（瀏覽器 DevTools Network 實測修正欄位對照與端點路徑） | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-34a | Step 4.1 地區／產業篩選機制修正：產業篩選移除、地區改子字串比對 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-34 | `job_postings.is_closed` 新增並串接爬蟲（解決 ADR-26 決策 5 原問題） | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-37／FR-38 | Step 4.2 開工前規格定案，新增 ADR-26 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-37／FR-38 | Step 4.2 全數實作完成：Gemini 契合度評分＋技能缺口分析＋雙重排名 Excel 交付 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-39／FR-40 | Step 4.3 開工前規格定案，新增 ADR-27 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-39／FR-40 | Step 4.3 資料結構設計修正：外部管道職缺改用 `source` 欄位共用同一張表 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-39／FR-40 | Step 4.3 全數實作完成：應徵成效追蹤＋外部管道職缺，Phase 4 求職主線全數完成 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-64～FR-72 | Mobile App（Step 4.4／4.5）規格盤點與定案，新增 ADR-28 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-64～FR-72 | Mobile App 規格追加確認＋定名「羅賓森」 | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-22 | 每日技術分享改回深入摘要、拆成三則獨立訊息，修正 IThome RSS 解析 bug（ADR-29，supersede ADR-25 部分） | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-64 | Mobile App 使用者體驗方向第二輪確認，建立獨立 mobile-app SPEC | Claude | 完成 | 里程碑 |
| 2026-08-09 | FR-19j | 客訴回饋頁設計修正＋新增 FR-19j（系統錯誤記錄與解法追蹤，Placeholder） | Claude | 完成 | 里程碑 |
| 2026-08-10 | FR-53f／FR-19j | FR-53f 重要通知邏輯修正＋FR-19j 系統錯誤記錄與解法追蹤全數實作完成（ADR-30） | Claude | 完成 | 里程碑 |
| 2026-08-10 | FR-64 | 首頁新增「體重紀錄」卡片規劃（純規格文件更新，尚未開工） | Claude | 完成 | 里程碑 |
| 2026-08-10 | FR-64～FR-72 | Mobile App 剩餘待確認事項一次盤點並定案（純規格文件更新，尚未開工） | Claude | 完成 | 里程碑 |
| 2026-08-10 | FR-65 | Mobile App Step 4.4／4.5：登入與 Token 機制（後端 App Auth API、bcrypt 密碼、JWT Access Token、Refresh Token rolling、Expo 登入頁、SecureStore、Telegram 忘記密碼） | Codex | 完成 | codex.md |
| 2026-08-10 | FR-65 | 登入頁預覽回饋調整：移除品牌文案／卡片標題、placeholder 統一「請輸入」、顯示切換改眼睛 icon | Codex | 完成 | codex.md |
| 2026-08-10～2026-08-12 | FR-64／FR-64a／FR-65／FR-67／FR-68／FR-72 | Step 4.4／4.5 Mobile App「羅賓森」由 Placeholder 大幅推進為實作中 | Codex | 完成 | 里程碑；本輪由 Codex Desktop 開發，逐階段明細見下列 codex.md 條目 |
| 2026-08-11 | FR-67b／FR-68 | 個人基本資訊頁與安全修改密碼（密碼強度、歷史密碼不可重用、`user_password_history` 表、改密後撤銷 Refresh Token） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64a | 操作介面、體態身高與最新紀錄權限調整（身高存 `users.height_cm`、全期間最新體態卡片、跨平台 TimePicker） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64／FR-64a | 今日單筆紀錄、待辦狀態下拉與腰圍趨勢（`body_weight_logs.waist_cm`、飲食／心情／體態每日單筆） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64a | 首頁快速紀錄與今日紀錄 CRUD（`app_records` Service、六種紀錄 Modal、10 分鐘重複偵測、歷史唯讀） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64a | 體重紀錄卡片、輸入視窗與同日趨勢修正（`DISTINCT ON (entry_date)` 同日只取最新一筆） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64a | Web Bluetooth／Bluefy 相容性 POC：結論為 PWA＋Bluefy 無法取代原生 BLE | Codex | 完成 | codex.md；決策見 `docs/ADR/discuss/mobile-app.md` |
| 2026-08-11 | FR-64a | 全面移除 BLE，改為手動記錄體重（`40.0～150.0 kg`、二次確認、API 邊界同步驗證） | Codex | 完成 | codex.md；決策見 `docs/ADR/discuss/mobile-app.md` |
| 2026-08-11 | FR-64a | 藍牙體重計量測與體重寫入（Yoda1 廣播解析、`POST /api/app/body/weight-logs`）＋待辦行事曆區間標示、登入／問候 icon 調整 | Codex | 完成 | codex.md；本項後由「全面移除 BLE」取代 |
| 2026-08-11 | FR-65 | 登入前使用者 ID 預先辨識（`POST /api/app/auth/identify`、五種辨識狀態、密碼欄依辨識結果啟用） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64 | Step 4.5 唯讀儀表板與分析頁面（`app_analytics` Service／API、八個分析模組、`react-native-svg` 圖表、AppShell／DateRangeFilter） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-65 | 登入欄位、Toast 與背景圖案調整（使用者 ID 改明碼、忘記密碼防呆 Toast、漸層＋點陣背景） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64／FR-65 | 預覽回饋調整（全站共用背景、性別頭像、上次／最近登入時間、行事曆式日期選擇、技術分享單日查詢） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64 | 待辦日期範圍、件數與清單互動修正（待辦改 1～7 天且允許未來日期、月曆件數、點擊捲動） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64 | 待辦區間 API、今日標示與狀態卡片修正（`parse_todo_date_range()`、四種狀態標籤配色） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-65／FR-67 | 登入提示、性別頭像與登出修正（一次性登入提示 Modal、`boy.png`／`woman.png`、自訂登出確認 Modal） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64a | 首頁體態卡片標題修正與紀錄視窗標題靠左對齊 | Codex | 完成 | codex.md |
| 2026-08-11 | FR-67b／FR-68 | 個人選單按鈕視覺一致性修正（改為與左側功能選單相同的白底圖示文字列） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-67b／FR-68 | 個人選單項目靠左修正 | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64～FR-72 | Step 4.4／4.5 大量未 commit 程式碼正式 commit＋push，完成正式上線部署（後端 Render＋前端 Vercel） | Claude | 完成 | 里程碑 |
| 2026-08-12 | FR-65 | Web 版 PWA「加入主畫面」體驗修正：SPA 路由 404、App icon、雙指縮放 | Claude | 完成 | 里程碑 |
| 2026-08-12 | | 收藏清單第一階段、首頁新入口與資料結構（`0071`～`0077` migration、收藏 CRUD API、收藏頁／首頁卡片） | Codex | 完成 | codex.md；規格未定案，見 `docs/specs/DRAFT.md` 待討論 |
| 2026-08-12 | FR-64 | 行事曆多活動防跑版（固定日期格高度、重要日子單行「+N」摘要） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64／FR-64a | 首頁本周重要日子、iPhone 輸入體驗與飲水紀錄（當週邊界過濾、`food`／`water` 分流、輸入字級 ≥16px） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64 | 全行事曆文案去重與語意配色統一（節日紅、重要日子藍、件數橘／黑；同名節日只留一筆） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64 | 操作可靠性與誤刪復原（請求鎖防連點、失敗保留輸入、刪除 5 秒復原期） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64a | 飲食拍照／相簿辨識、內容確認與營養估算（`app_diet_photo` Service、辨識→確認→估算→再確認、新增／取代模式） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64／FR-64a | 待辦日期區間行事曆資料同步修正（三個行事曆共用同一份月份資料、重要通知與生日合併） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64 | 重要日子設定與待辦整合行事曆（`0069` 三張表、`app_important_days` Service／API、管理頁、首頁重要通知改時程清單） | Codex | 完成 | codex.md；Telegram 提醒未納入，見 `docs/specs/DRAFT.md` 待討論 |
| 2026-08-12 | FR-72 | APP 設定（`0067` 偏好欄位、深／淺色模式、字體大小、隱私數字遮罩與 `SensitiveValue` 元件） | Codex | 完成 | codex.md；FR-69／FR-70／FR-71 本輪依指示跳過 |
| 2026-08-12 | FR-65 | 使用者 ID 失焦驗證造成登入按鈕無回應修復 | Codex | 完成 | codex.md；除錯紀錄見 `docs/ADR/debug/mobile-app.md` |
| 2026-08-12 | FR-72 | 個人選單間距與深色模式可讀性修正（行事曆深色主題、重複字級倍率移除） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-72 | 今日紀錄視窗深色配色補強（六種紀錄視窗、內嵌行事曆、時間選擇欄位） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64／FR-64a | 中華民國行事曆、待辦件數與導覽順序（`0068` 快取表、`taiwan_calendar` Service、左側選單固定排序） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64 | 重要日子設定：行事曆統一與通知對象狀態改善 | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64 | 待辦事項與重要日子日期區間（`0070` 結束日欄位、區間重疊查詢、`GENERATE_SERIES` 逐日計數） | Codex | 完成 | codex.md |
| 2026-08-12 | FR-64 | 分析頁日期選擇器行事曆統一（`holidayOnly` 模式，只顯示政府節日） | Codex | 完成 | codex.md |
| 2026-08-11 | FR-64a | 飲食照片與 Gemini 流程實機驗收完成（拍照／相簿選擇、辨識與後續流程可正常使用） | Robin／Codex | 完成 | Robin 已於實體手機確認兩種照片來源皆可使用 |
| 2026-08-12 | | 收藏清單／探索地圖／成果展示前置 POC（Leaflet 1.9.4＋OpenStreetMap，不採 Expo Maps） | Codex | 完成 | codex.md；技術選型見 `docs/ADR/discuss/mobile-app.md` |
| 2026-08-12 | FR-64 | 首頁心情趨勢卡片高度修正 | Codex | 完成 | codex.md；除錯紀錄見 `docs/ADR/debug/mobile-app.md` |
| 2026-08-14 | FR-64 | 飲食／運動雙輸入模式、AI／人工來源圖例、心情 Emoji 與窄螢幕按鈕完成實作 | Codex | 完成 | 新增 `0078` migration、輸入防呆、照片確認流程、來源拆分圖表與 Tooltip；147 項相關測試通過，完整回歸 1676 通過／3 項因本機缺 `ffmpeg` 未執行，Mobile typecheck 與 Web export 通過 |
| 2026-08-14 | FR-65 | Expo 本機預覽登入 API 路由修正 | Codex | 完成 | localhost 改用 `EXPO_PUBLIC_API_BASE_URL`，正式 Web 維持同網域 API；瀏覽器已驗證 `user01` 可完成身分辨識 |
| 2026-08-12 | FR-65 | Web 預覽登入無法連線修正（API Base URL 改 `window.location.origin`、React Hook 順序、快取標頭） | Codex | 完成 | codex.md；除錯紀錄見 `docs/ADR/debug/mobile-app.md` |
> 「開發者」欄固定填 `Claude`、`Codex` 或實際負責人姓名，方便回溯是哪個工具／人做的。

## Commit 紀錄

> 本表只代表本地 Git commit，不等同於已 push 或已部署。資料來源為 `git log --format="%h|%ad|%s" --date=short`（截至 2026-08-14，本次 PROGRESS 同步 commit 完成後共 127 筆）。git author 全部是 Robin 本人，因此「開發者」欄依 commit 內容與工作階段判斷。

| 日期 | 版本 / commit | 異動摘要 | 開發者 |
| --- | --- | --- | --- |
| 2026-08-15 | `996c603` | 修正 /set_invite_codes 因 0083 NOT NULL 迴歸 | Claude |
| 2026-08-15 | `4740d00` | Phase 6 第一批：通關密碼到期與鎖定、使用者停用機制 | Claude |
| 2026-08-15 | `d13c390` | 定案 Telegram 重構、權限管理與功能取消，同步 8/15 部署驗收 | Claude |
| 2026-08-14 | `67ef251` | 修正重要日子家庭成員查詢與求職分析載入 | Codex |
| 2026-08-14 | `b3f165a` | 同步目標日期並修正 Mobile App 重要日子相關問題 | Codex |
| 2026-08-14 | `4760689` | 完善 Mobile 收藏地點選擇、固定捲動、旅遊行程與重要日子同步 | Codex |
| 2026-08-14 | `bff8679` | 改善收藏地址定位並修復已造訪與刪除操作 | Codex |
| 2026-08-14 | `b2e3362` | 完成 Mobile App 探索地址定位、快取與重新定位 | Codex |
| 2026-08-14 | `c514b17` | 完成 Mobile App 收藏、旅遊行程、探索地圖與成果展示 Phase 5 | Codex |
| 2026-08-14 | `84960d2` | 擴充 Mobile App 飲食與運動紀錄模式 | Codex |
| 2026-08-14 | `d84222f` | 正式取消 App 三項設定功能 | Codex |
| 2026-08-14 | `fb62163` | 統一開發與文件治理規則 | Codex |
| 2026-08-14 | `ec36062` | 補齊待討論、已取消與擱置項目 | Codex |
| 2026-08-14 | `b991323` | 補齊正式技術棧資訊 | Codex |
| 2026-08-14 | `55177ad` | 整併規格與文件架構 | Codex |
| 2026-08-13 | `3160b14` | 記錄 PWA icon/縮放/SPA 路由修正過程，補充 FR-65c 保持登入在 Web 版的已知限制 | Claude |
| 2026-08-12 | `4f7bfd3` | 修正 web.output 改為 static，讓 +html.tsx 的 icon/manifest/viewport 設定真正生效 | Claude |
| 2026-08-12 | `ed644f3` | Web 版加入 App icon、manifest，加入主畫面時使用真正的羅賓森頭像並支援全螢幕模式 | Claude |
| 2026-08-12 | `341df03` | 修正 Vercel SPA 路由：直接開啟 /login 等網址時 fallback 回 index.html | Claude |
| 2026-08-12 | `0e8ccd3` | Vercel 設定相關紀錄 | Claude |
| 2026-08-12 | `167624f` | 修正 .gitignore：補回被誤擋的 mobile/tsconfig.json，新增 Vercel 部署設定 | Claude |
| 2026-08-12 | `b8beff4` | Step 4.4/4.5：Mobile App「羅賓森」登入/選單/個人資訊/APP設定/唯讀分析/體態飲食記錄完工 | Codex |
| 2026-08-10 | `3d6b313` | Mobile App 剩餘待確認事項定案（純規格文件，尚未開工） | Claude |
| 2026-08-10 | `b3e3b61` | 規劃首頁新增「體重紀錄」卡片（純規格文件，尚未開工） | Claude |
| 2026-08-10 | `7b2ec5d` | 實作 FR-53f（重要通知邏輯修正）與 FR-19j（系統錯誤記錄與解法追蹤） | Claude |
| 2026-08-10 | `e890a77` | 每日技術分享改回深入摘要、拆成三則獨立訊息，修正 IThome RSS 解析 bug（ADR-29） | Claude |
| 2026-08-09 | `c84d037` | Step 4.3：應徵成效追蹤＋外部管道職缺（FR-39、FR-40，ADR-27） | Claude |
| 2026-08-09 | `76f449b` | docs: Step 4.3 外部職缺資料結構改用 source 欄位共用同一張表（ADR-27 決策 5/6 修正） | Claude |
| 2026-08-09 | `6570a99` | docs: Step 4.3（應徵成效追蹤）開工前規格定案，新增 ADR-27 | Claude |
| 2026-08-09 | `223f617` | Step 4.2：Gemini 契合度評分＋技能缺口分析＋雙重排名 Excel 交付（FR-37、FR-38，ADR-26） | Claude |
| 2026-08-09 | `c860275` | docs: Step 4.1 收尾、Step 4.2 開工前置依賴解除 | Claude |
| 2026-08-09 | `22ec966` | feat(job104): 新增 job_postings.is_closed 自動判斷欄位 | Claude |
| 2026-08-09 | `ae92792` | fix(job104): 依 Robin 回饋移除產業篩選、地區篩選改為子字串比對 | Claude |
| 2026-08-09 | `64eb691` | fix(job104): 依真實 API 驗證修正欄位對照與端點路徑 | Claude |
| 2026-08-09 | `1774e06` | Step 4.1 Phase C-F：完成 FR-34 爬蟲＋FR-35 公司背景協作＋週排程掛載，Step 4.1 全數完工 | Claude |
| 2026-08-09 | `a40560e` | Step 4.1 Phase B：新增求職模組 FR-33/FR-36 對話式收集流程 | Claude |
| 2026-08-09 | `eda9054` | Step 4.1 Phase A：新增求職模組 DB schema（users 欄位＋job_search_criteria／job_companies／job_postings 三張新表，見 ADR-24） | Claude |
| 2026-08-09 | `981d41c` | Step 4.2 開工前規格定案：新增 ADR-26，修正 FR-36 歸屬、重寫 FR-37/FR-38 | Claude |
| 2026-08-09 | `1ddf9d2` | 修正每日技術成長摘要：改為一天多筆、一筆一個來源管道（source 正規化，ADR-25） | Claude |
| 2026-08-08 | `61c4514` | Step 3.5 完成：好友模式陪伴聊天（FR-51、FR-52、ADR-22） | Claude |
| 2026-08-08 | `521280b` | Step 3.4 完成：YouTube 技術情報模組（FR-57～FR-59、ADR-21） | Claude |
| 2026-08-08 | `74e2b93` | Step 3.3 剩餘範圍全數完成：FR-29 成效彈性文字問答、FR-24 目標設定與方向建議、FR-30 正式成績記錄 | Claude |
| 2026-08-08 | `b83cf33` | Step 3.3: 證照題庫作答與批改流程 + 20:00 提醒 + 彈性排程對話流程（FR-27/FR-28） | Claude |
| 2026-08-08 | `1986550` | 體態管理新增腰圍設定（FR-46）+ Phase 4 藍牙體重計規格（FR-64a） | Claude |
| 2026-08-08 | `93e0e93` | SPEC.md：彈性排程新增第四種語意「平攤到鄰近幾天」（ADR-20 決策 5/6） | Claude |
| 2026-08-08 | `be180b9` | Step 3.3：每日 08:00 推播出題機制（FR-26，ADR-20） | Claude |
| 2026-08-08 | `20fbce6` | PROGRESS.md：記錄 production 事故已確認解決（migration 全套用 + healthz 修復上線） | Claude |
| 2026-08-08 | `e799198` | 修復 production 事故根因：CloudSQLClient.execute() 的 IndexError | Claude |
| 2026-08-08 | `8b093ed` | 修復 production 事故：/healthz 逾時（改背景執行緒跑排程檢查） | Claude |
| 2026-08-07 | `fd63b96` | Step 3.3 第一階段：答案照片比對機制（FR-27 部分）+ 新資料表 | Claude |
| 2026-08-07 | `3737562` | 證照題庫泛用化：exam_type 不寫死清單，toeic_questions 改名 certificate_questions | Claude |
| 2026-08-07 | `ed48543` | Step 3.2 修正：整包 MP3 切割自動判斷開頭有無作答說明語音 | Claude |
| 2026-08-07 | `75ffcfb` | Phase 3 Step 3.2 完成：TOEIC 雙軌題庫 Pipeline（FR-24、FR-25a～FR-25f） | Claude |
| 2026-08-07 | `7a128fe` | 功能開關拆分：skill_growth 拆成 tech_intel／certificate／language | Claude |
| 2026-08-07 | `b2114b3` | docs: 更新 PROGRESS.md，GEMINI_API_SKILL_GROWTH_KEY 已由 Robin 設定完成 | Claude |
| 2026-08-07 | `d618493` | Step 3.1 修正：每日技術分享拆成 23:00 收集／08:00 推播兩階段 | Claude |
| 2026-08-07 | `a783d5c` | feat: 每日重點技術分享（FR-22、FR-23，Step 3.1） | Claude |
| 2026-08-07 | `4a82136` | feat: 例外分級降級與決策執行狀態閉環回饋（FR-19f~FR-19h，Step 2.6） | Claude |
| 2026-08-07 | `31747f8` | feat: 外部 API 重試機制（FR-19i，Step 2.5） | Claude |
| 2026-08-07 | `9478dc8` | feat: Telegram 故障 email 備援通知 + Google Calendar 整合（ADR-16、Step 2.7） | Claude |
| 2026-08-05 | `2077991` | feat: 重要通知模組（FR-53，Step 2.3） | Claude |
| 2026-08-04 | `8870b21` | docs: 移除 Notion 後台規劃，改採 Mobile App（React Native + Expo） | Claude |
| 2026-08-04 | `9410113` | feat: 體態管理模組（FR-45~FR-48，Step 2.2） | Claude |
| 2026-08-04 | `23b291e` | feat: 記帳月底自動月報推播（FR-44a） | Claude |
| 2026-08-04 | `488511f` | fix: 個資遮蔽語意層暫時性外部錯誤導致整則訊息完全無回覆 | Claude |
| 2026-08-04 | `71ab515` | feat: 記帳模組擴充（FR-41a 預算特殊月份覆蓋、FR-42a 每日記帳提醒） | Claude |
| 2026-08-04 | `5be3360` | feat: 記帳模組（FR-41～FR-44） | Claude |
| 2026-08-02 | `68e88cb` | feat: 心情小記支援補記/更新/刪除（FR-49 擴充） | Claude |
| 2026-08-02 | `73b7e12` | feat: 待辦事項支援時間區間（FR-31b） | Claude |
| 2026-08-02 | `9045697` | fix: 修正話題轉移誤判為拒絕 + 待辦時間擅自猜測 + 8點提醒承諾邏輯錯誤 | Claude |
| 2026-08-02 | `4855bb6` | fix: webhook 空字串回覆防呆，修正「完全不理我」bug | Claude |
| 2026-08-02 | `47693e3` | Phase 1 Step 1.9：客訴收集模組（FR-60~63），Phase 1（MVP）全數完成 | Claude |
| 2026-08-02 | `837e8c1` | Phase 1 Step 1.8：心情小記模組（FR-49/FR-50） | Claude |
| 2026-08-02 | `0168774` | Phase 1 Step 1.7：待辦事項模組（FR-31/FR-31a/FR-32） | Claude |
| 2026-08-02 | `c192cef` | 保留 GDRIVE_KEY_FILE_PATH 於 .env.example（Robin 指示保留） | Claude |
| 2026-08-02 | `da9efa0` | Phase 1 Step 1.6：基礎錯誤處理層（FR-19a/FR-20/FR-21） | Claude |
| 2026-08-02 | `9dcf656` | gdrive 改用 OAuth 2.0（真人帳號身分），修正 storageQuotaExceeded | Claude |
| 2026-08-02 | `88d36af` | Phase 1 Step 1.5：個資偵測與遮蔽機制（FR-13） | Claude |
| 2026-08-02 | `5680aa1` | 修正 Telegram send_text 400 錯誤，排查語音功能 gdrive 金鑰路徑問題 | Claude |
| 2026-08-02 | `74ea671` | 語音成功轉出文字後附註 FR-15 修正窗口提醒 | Claude |
| 2026-08-02 | `af30855` | feat(voice): 補上 FR-14 規則 1，單次語音超時觸發 15 分鐘全面鎖定 | Claude |
| 2026-08-02 | `77bc0d9` | fix(chat-core): 最終確認狀態的語音一律短路，避免浪費 Drive/Groq 額度 | Claude |
| 2026-08-02 | `0cc39bb` | feat(chat-core): 新增語音最終執行確認關卡，防聽錯誤觸不可逆操作（FR-16a） | Claude |
| 2026-08-01 | `81b821d` | fix(voice): 補上 message.audio（上傳音檔）支援，修正 Step 1.4 範圍缺口 | Claude |
| 2026-08-01 | `60efdb3` | Phase 1 Step 1.4：語音轉文字流程（FR-14、FR-15） | Claude |
| 2026-08-01 | `6c254b7` | 新增主動記知識功能（FR-11）與 /clean-target-dialog（FR-12），見 ADR-8 | Claude |
| 2026-08-01 | `bde5d5f` | 修正四個測試回報問題：刪除確認、誠實性、寵物資料、反問誤觸發 | Claude |
| 2026-08-01 | `afacabc` | 修正代名詞指涉優先順序 bug：跳回更早提過的人而非最近點名的人 | Claude |
| 2026-08-01 | `f249571` | 新增打字誤植先確認機制、回答精簡規則、/clean-all-dialog 指令 | Claude |
| 2026-07-31 | `89f4386` | 修正 pending_user_knowledge 三個邏輯漏洞（ADR-6，部分 supersede ADR-5） | Claude |
| 2026-07-31 | `12c4afa` | 新增家庭成員知識庫：范焞琪（母親范麗芳的親妹妹，Robin 的阿姨） | Claude |
| 2026-07-31 | `59d04b2` | 修正代名詞指涉錯誤：問小布丁幾歲被誤答成爺爺年齡 | Claude |
| 2026-07-31 | `577894e` | 修正家人知識庫民國年換算錯誤（小布丁生日年答錯 2013 應為 2024） | Claude |
| 2026-07-31 | `6830307` | 修正日期幻覺：prompt 注入伺服器真實日期，加強禁止捏造事實規則 | Claude |
| 2026-07-31 | `a5aa56a` | 移除 Google Search grounding，查無答案改誠實回報不知道（ADR-5/ADR-8） | Claude |
| 2026-07-31 | `ef50dbe` | 修正 ADR-7：_SEARCH_MODEL 改為 gemini-2.5-flash | Claude |
| 2026-07-31 | `0db2196` | generate_with_search 固定改用 gemini-2.5-flash-lite（ADR-7） | Claude |
| 2026-07-31 | `2386e2d` | LLMClient 預設模型改為 gemini-3.5-flash-lite（ADR-6） | Claude |
| 2026-07-31 | `4b039ef` | Step 1.3b: 影像辨識基礎流程（FR-17、ADR-13） | Claude |
| 2026-07-31 | `659d2ff` | db: 新增 media_uploads 表（Step 1.3b 影像辨識前置作業） | Claude |
| 2026-07-31 | `853e0ed` | feat: 加強額度防呆 — update_id 去重 + LLMClient 本地端節流保護 | Claude |
| 2026-07-31 | `987b689` | fix: webhook 加最小安全網，防止 Telegram 重試風暴燒 Gemini 額度 | Claude |
| 2026-07-31 | `84521d6` | feat: Step 1.3a /function 改版 — 總覽 + 按需深入 + 情境範例（FR-9/ADR-4） | Claude |
| 2026-07-31 | `e16d685` | spec: 補上待辦事項/求職/體態管理/心情小記情境範例（FR-56e~h） | Claude |
| 2026-07-31 | `60e9e6a` | 長記憶（滾動式摘要）：對話核心新增 ADR-3，記憶架構補齊四部分 | Claude |
| 2026-07-31 | `27ae0b1` | 新增 conversation_summaries 表（長記憶滾動摘要，Robin 核准 ADR-3 建表 SQL） | Claude |
| 2026-07-31 | `5e8c347` | Phase 1 Step 1.3 完成：Gemini 對話核心（知識庫問答、資安隔離、人格化語氣） | Claude |
| 2026-07-30 | `75c4bf3` | Phase 1 Step 1.2 完成：功能開關系統（/my_toggles、/set_toggle） | Claude |
| 2026-07-30 | `ad246d2` | 新增 FR-2a：Step 1.2 功能開關權限模型（使用者可自管、Owner 可代管） | Claude |
| 2026-07-30 | `1119a9b` | 更新 PROGRESS.md：紀錄 0006 migration 已套用成功 | Claude |
| 2026-07-30 | `cf48e16` | 多模態與人格化語氣大改版：新增 ADR-12/ADR-13、FR-17/FR-56 改版、三週時程延長 | Claude |
| 2026-07-30 | `573c1c6` | Phase 1 Step 1.1: passcode auth, owner setup flow, /rule /function | Claude |
| 2026-07-30 | `2d98bbe` | Mark Phase 0 fully complete: all 5 migrations confirmed applied on Render | Claude |
| 2026-07-30 | `2e461da` | Record Step 0.5 first-batch migration push in SPEC.md/PROGRESS.md | Claude |
| 2026-07-30 | `e440b7c` | Add Phase 0 Step 0.5 first-batch DB migrations (ADR-10/ADR-11) | Claude |
| 2026-07-30 | `776802f` | Add Robinson product spec, submodules, schema docs, and Phase 0 infra | Claude |
| 2026-07-29 | `5f60602` | Chore: Remove all .DS_Store files recursively | Robin |
| 2026-07-27 | `fdc55a9` | fix: add flask to requirements.txt | Robin |
| 2026-07-27 | `d92b391` | fix: rename DockerFile to Dockerfile | Robin |
| 2026-07-27 | `9041aab` | chore: add initial project skeleton for deployment setup | Robin |
| 2026-07-27 | `91eff3b` | Initial commit | Robin |

## Push 紀錄

> Push 必須由 Robin 親自執行；本表只記錄已有明確證據的結果，不依本地 commit 狀態推測遠端狀態。

| 日期 | Branch／版本 | 遠端 | 狀態 | 備註 |
| --- | --- | --- | --- | --- |
| 2026-08-15 | `main`／`996c603` | GitHub | 完成 | 8/15 Robin 已推版 |
| 2026-08-15 | `main`／`4740d00` | GitHub | 完成 | 8/15 Robin 已推版 |
| 2026-08-15 | `main`／`d13c390` | GitHub | 完成 | 8/15 Robin 已推版 |
| 2026-08-14 | `main`／`67ef251` | GitHub | 完成 | 8/14 Robin 已推版；本次 PROGRESS 同步 commit 將一併 push |
| 2026-08-14 | `main`／`b3f165a` | GitHub | 完成 | 8/14 Robin 已推版；本次 PROGRESS 同步 commit 將一併 push |
| 2026-08-14 | `main`／`4760689` | GitHub | 完成 | 8/14 Robin 已推版；本次 PROGRESS 同步 commit 將一併 push |
| 2026-08-14 | `main`／`bff8679` | GitHub | 完成 | 8/14 Robin 已推版；本次 PROGRESS 同步 commit 將一併 push |
| 2026-08-14 | `main`／`b2e3362` | GitHub | 完成 | 8/14 Robin 已推版；本次 PROGRESS 同步 commit 將一併 push |
| 2026-08-14 | `main`／`c514b17` | GitHub | 完成 | Robin 已推版；本次 PROGRESS 同步 commit 將一併 push |
| 2026-08-14 | `main`／`84960d2`＋`18a4ef7` | GitHub | 完成 | Robin 已確認功能 commit 與 PROGRESS 同步 commit 均已 push |
| 2026-08-14 | `main`／`fbb905a` | GitHub | 完成 | Robin 已確認 Push 紀錄同步 commit 已 push |
| 2026-08-14 | `main`／`1c8e836` | GitHub | 完成 | Robin 已確認本次兩筆 commit 均已 push |
| 2026-08-14 | `main`／`fb62163` | GitHub | 完成 | Robin 已確認 push |
| 2026-08-12 | `main`／Step 4.4～4.5 | GitHub | 完成 | 依當日正式上線里程碑紀錄 |

## 部署紀錄

| 日期 | 版本／範圍 | 環境 | 狀態 | 驗證 |
| --- | --- | --- | --- | --- |
| 2026-08-15 | FR-2～FR-4a～FR-4d（Phase 6 第一批，Migration 0083） | Render 正式環境／Telegram 實機 | 完成 | Robin 已確認 `/set_invite_codes` 寫入正常、家人 Telegram 帳號輸入通關密碼綁定成功 |
| 2026-08-15 | FR-64／FR-65／FR-72a／FR-73～FR-76a | Render＋Vercel 正式環境／Mobile 實體手機 | 完成 | Robin 已確認重要日子與求職分析載入、收藏／旅遊／探索／成果、Nominatim 定位、相關 migration 與 Mobile 實機操作正常 |
| 2026-08-12 | Step 4.4～4.5 Mobile App 與後端 API | Render＋Vercel 正式環境 | 完成 | 依當日正式上線里程碑紀錄 |
