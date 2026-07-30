---
title: Robinson 產品開發階段紀錄
spec: docs/specs/robinson/SPEC.md
updated: 2026-07-30
---

# Robinson 產品開發階段紀錄

> 本文件追蹤「產品階段」層級的進度（Phase 完成度、里程碑、待決事項），細部任務進度請看 [SPEC.md](./SPEC.md) 的 checkbox。每完成一個 Phase 的所有 Step，回來更新本文件的階段狀態與里程碑。

## 專案緣起（Claude Code 協作開始前）

- **2026-07-28**：Robin 自行完成所有外部服務的註冊與 API 金鑰申請、Telegram Bot 基礎設定；並與 Gemini 進行腦力激盪與方案收斂 —— 梳理生活痛點、評估技術可行性、把發散的想法轉化為具體的 PRD（Product Requirement Document）雛形
- **2026-07-29**：正式開始與 Claude Code 協作，產出標準規格書（`docs/specs/robinson/SPEC.md`）與 Codebase 規範等文件

## 目前階段

**Phase 0 — 專案基礎建設（已完成）→ 即將進入 Phase 1（MVP）**

## 目標時程（2026-07-30 更新：兩週制，因新增 YouTube 模組再順延 1 天）

- **Phase 0～4：2026-07-29 ～ 2026-08-12（兩週＋1 天緩衝）**，不含 Notion 後台
- **Phase 5（Notion 後台）：2026-08-12 之後再排**

原訂一週（7/29～8/4）完成 Phase 0～4，因新增大量內容（Owner 對話式設定通關密碼、`/rule`／`/function` 內建指令、TOEIC 雙軌題庫 Pipeline、104 爬蟲、FR-19 全套自主診斷＋GitHub PR 治理機制＋分級降級＋重試機制）先改為兩週（7/29～8/11）。今天又新增「YouTube 技術情報模組」（FR-57～FR-59）與跨模組的 ETL 去重通則（NFR-11），Phase 3 的工作量再增加，因此把 Phase 3 從 2 天延長為 3 天，其餘 Phase 順延，整體收尾日往後移 1 天到 8/12。

### 建議每日分配（僅供參考，Robin 可依實際進度調整）

| 日期 | 建議內容 |
| --- | --- |
| 7/28（已完成） | 專案緣起：服務註冊/API 申請、Telegram Bot 基礎設定、Gemini 腦力激盪收斂 PRD 雛形（非 Claude Code 協作範圍） |
| 7/29（已完成） | Phase 0：`submodules/` 骨架、規格書初版確認 |
| 7/30（今天） | Phase 0 收尾（Step 0.1b：`src/schema/` 骨架已完成；Step 0.2～0.5：金鑰串接含新增的 GitHub Token、YouTube API Key、依 ADR-10 流程建表、keep-alive 端點） |
| 7/31 | Phase 1：Step 1.1（通關密碼驗證＋Owner 設定對話流＋歡迎訊息＋`/rule`／`/function`）、Step 1.2～1.3（功能開關、對話核心） |
| 8/1～8/2 | Phase 1 收尾（語音、個資遮蔽、基礎錯誤處理、待辦事項、心情小記、Step 1.9 客訴收集），力求 Phase 1 當週可用；若 8/2 做不完，優先延後 Step 1.9（客訴收集非核心體驗，可挪到 Phase 2 之後補） |
| 8/3～8/4 | Phase 2：記帳、體態管理、重要通知 |
| 8/5～8/6 | Phase 2：Step 2.4～2.6（GitHub PR 自主診斷、重試機制、分級降級），技術複雜度最高，獨立預留兩天 |
| 8/7～8/9 | Phase 3：技能成長（TOEIC 雙軌 Pipeline＋YouTube 技術情報模組）、好友模式（新增 YouTube 模組後由 2 天延長為 3 天） |
| 8/10～8/11 | Phase 4：104 求職爬蟲＋整合測試 |
| 8/12 | 全 Phase 整合測試／緩衝日 |
| 8/12 之後 | Phase 5：Notion 後台 |

## 階段總覽

| Phase | 內容 | 狀態 | 目標日期 | 備註 |
| --- | --- | --- | --- | --- |
| Phase 0 | 專案基礎建設（repo 結構、金鑰串接、Render/Neon/cron-job、DB 初始化） | 🟢 已完成 | 7/29～7/30 | 全部 Step 完成：`submodules/`、`src/schema/`、`src/migrations/`（ADR-11）骨架就緒；`/healthz` 已部署上線並掛上 cron-job.org；第一批 5 張表（`users`／`invite_codes`／`knowledge_base`／`conversation_logs`／`feature_toggles`）已核准並套用成功 |
| Phase 1（MVP） | 核心平台（通關密碼對話式設定、歡迎訊息、`/rule`／`/function`／`/complaint` 內建指令、功能開關、Gemini 對話+知識庫、語音、個資遮蔽、基礎錯誤處理）＋待辦事項＋心情小記＋客訴收集 | 🟡 即將開始 | 7/31～8/2 | 新增 FR-6d（歡迎訊息）、FR-55（`/rule`）、FR-56（`/function`，文字模板待補，見附錄 B）、FR-60～FR-63（客訴收集，Step 1.9） |
| Phase 2 | 記帳＋體態管理＋重要通知＋異常自主診斷與 GitHub PR 治理＋重試機制＋分級降級 | ⚪ 未開始 | 8/3～8/6 | Step 2.4～2.6 為新增範圍，技術複雜度最高，已獨立預留兩天 |
| Phase 3 | 個人技能成長（TOEIC 雙軌題庫 Pipeline＋YouTube 技術情報模組，僅 Robin）＋好友模式 | ⚪ 未開始 | 8/7～8/9 | 新增 YouTube 模組（FR-57～FR-59，見 ADR-9），Phase 3 由 2 天延長為 3 天 |
| Phase 4 | 求職模組（104 爬蟲＋評分） | ⚪ 未開始 | 8/10～8/11 | 爬蟲策略已定案：每週一次、AJAX API、無登入態、禮貌性延遲、ETL 去重（FR-34a～FR-34d） |
| Phase 5 | Notion 後台 | ⚪ 未開始 | 8/12 之後 | 獨立拆出的最終階段，須等 Phase 0～4（含 FR-19 治理機制）穩定後才開始；期間僅維持資料層 API 抽象化彈性 |

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

## 待決事項

目前**沒有阻塞 Phase 1 開工的待決事項**。

- [x] 確認外部服務金鑰已全數申請完成（Telegram Bot Token、Neon 連線字串、Google Service Account JSON + Drive Folder ID、Gemini x2 Token、Gmail 帳密、GitHub Personal Access Token、YouTube Data API Key）——已於 `.env` 逐項核對存在；`TELEGRAM_BOT_TOKEN`／`YOUTUBE_API_KEY` 已於本次金鑰外洩事故後重新產生
- [ ] `/function` 路由的實際文字模板（分類方式、每個功能的說明文字、是否附操作提示）待有產品原型後由 Robin 補充，見 SPEC.md 附錄 B（不阻塞 Phase 1，FR-56 可先用最簡單的清單格式實作，之後再美化文案）
- [x] Step 0.5a（`src/migrations/` + migration runner）已實作
- [x] Step 0.4：Robin 已完成 cron-job.org 設定，確認 API 正常

## 下一步

1. **Phase 0 僅剩 Step 0.5**：依 ADR-10／ADR-11 流程，逐一提出使用者表、通關密碼表、知識庫表、對話紀錄表、功能開關表的 `CREATE TABLE` SQL 草案與設計理由給 Robin 審核，核准後存成 `src/migrations/` 檔案並 commit+push，由 Render 自動部署套用
2. Phase 0 完成後，為 Phase 1 各功能（Owner 通關密碼設定對話流、歡迎訊息、`/rule`／`/function`／`/complaint`、功能開關、對話核心、語音、個資遮蔽、待辦事項、心情小記、客訴收集）視需要展開個別 `docs/specs/<slug>/SPEC.md` 並進入 TDD 循環，屆時一併補上 `submodules/` 的單元測試
3. 每天對照「建議每日分配」檢查進度，落後時優先保住 Phase 1 核心體驗（通關密碼、對話核心、待辦、心情小記），Step 1.9 客訴收集等次要 Step 可延後不必硬趕
