---
updated: 2026-08-19
---

# 未定案草稿

> 想法先記在這裡，使用者確認要做才依 SPEC-TEMPLATE.md 的功能區塊格式升級進 `docs/specs/SPEC.md`。
> 已有完整決策脈絡的擱置/取消項目，這裡只放一行索引＋連結，詳細理由見對應的 discuss 檔案，不重複記錄。

## 待討論

- 2026-08-24：Neon compute CU-hours（免費額度 100 CU-hours／月）用量監控——Robin 收到 Neon 官方 email 顯示已用 80%，但既有 FR-21 `NeonCapacityMonitor` 只監控儲存空間（0.5GB），完全沒有涵蓋 compute CU-hours，才會沒有 Telegram 主動預警。目前排查認為主因是 `/healthz`（cron-job.org 每 10 分鐘觸發）過去讓 14 個排程檢查各自開關資料庫連線，已於 FR-21a 修正改為共用一個連線；是否要另外監控 CU-hours 本身，需先確認 Neon 官方是否有查詢即時 compute 用量的 API（目前跟 Gemini 額度監控一樣，暫時找不到），有的話再排入 Roadmap，詳見 `docs/ADR/debug/infra.md`

## 已取消

- 2026-08-18：NFR-14～NFR-15 架構遷移正式取消；本專案不再將 `main.py`／`src/` 搬至 `backend/`，不拆建 `backend/api`、`backend/services`、`backend/repositories`、`backend/agents` 或 `data/`，也不為此調整部署入口。維持目前已完成實測的目錄與執行方式，避免大範圍搬遷造成既有功能回歸；當時保留的 FR-6c 與 FR-77 已於後續批次完成 — 詳見 `docs/ADR/discuss/robinson.md` 2026-08-18「取消 NFR-14～NFR-15 架構遷移」及「FR-6c 與 FR-77 開工執行紀錄」條目
- 2026-08-18：FR-15「成功傳送語音後 15 分鐘內不得再用語音修正」及其提示文案、`media_uploads.created_at` 修正窗口判斷正式取消；轉錄結果已改為執行前確認，聽錯時可立即重新傳語音或直接打字修正 — 詳見 `docs/ADR/discuss/voice-safety.md` 2026-08-18「取消 15 分鐘語音修正限制」條目
- 2026-08-15：Telegram 查無答案後教學、家庭／個人持久化知識庫讀寫與刪除、逐則對話紀錄、長記憶摘要，以及清除全部／指定主題知識與對話等功能正式取消；附屬的高風險語音逐字確認流程也隨適用功能取消。一般對話改用靜態人格 Prompt 與不落地的 10 分鐘短期上下文；對應路由、狀態、排程與三張資料表已由 FR-77 及 migration `0094` 清理完成 — 詳見 `docs/ADR/discuss/robinson.md` 2026-08-15「移除持久化知識庫與對話記憶」及 2026-08-18「FR-6c 與 FR-77 開工執行紀錄」條目
- 2026-08-15：除 Telegram 平台必要的 `/start` 外，所有一般使用者與 Owner Slash Commands 正式取消且不保留相容期，功能全面改由權限化選單與引導式對話處理 — 詳見 `docs/ADR/discuss/robinson.md` 2026-08-15「全面移除 Slash Commands」條目
- 2026-08-15：Telegram `/function`、中文觸發詞「我要看所有功能」及功能總覽／細節追問正式取消，後續由可見功能選單取代 — 詳見 `docs/ADR/discuss/robinson.md` 2026-08-15「使用規則選單與功能總覽移除」條目
- 2026-08-15：「客訴回饋」功能正式取消；Telegram／Mobile App 入口、API、流程、測試及 `complaints` 資料表已由 FR-77 與 migration `0094` 清理完成 — 詳見 `docs/ADR/discuss/robinson.md` 2026-08-15「權限管理的使用者建檔、功能授權與推播設定」及 2026-08-18「FR-6c 與 FR-77 開工執行紀錄」條目
- 2026-08-14：FR-69／FR-70／FR-71「Mobile App 目標與指標設定／功能開關頁／Robin 專屬排程設定」正式取消；未建立頁面、API 或資料表，既有 Telegram 設定流程維持不變 — 詳見 `docs/ADR/discuss/mobile-app.md` 2026-08-14 條目
- 2026-08-04：視覺化後台原採 Notion，改用 Mobile App（React Native + Expo）— 詳見 `docs/ADR/discuss/mobile-app.md` 2026-08-04 條目
- 2026-08-05：AI 自主診斷＋GitHub PR 自動化修復機制，改用「完整 log 上傳雲端＋私訊 Robin 專屬連結」— 詳見 `docs/ADR/discuss/service-resilience.md` 2026-08-05 條目
- 2026-08-11：FR-64a 藍牙體重計整合全面取消；原生 BLE 與 Web Bluetooth／Bluefy 方案均不採用，Android、iOS、Web 統一改為手動輸入體重 — 詳見 `docs/ADR/discuss/mobile-app.md` 2026-08-11 條目

## 擱置中

- 2026-08-08：`language`（語言學習：英文口說練習、其他語言學習）功能開關已建立但功能未展開，不排入目前 Roadmap，何時展開留待 Phase 4 全部完成後再議 — 詳見 `docs/ADR/discuss/skill-growth.md` 2026-08-08 條目、`docs/specs/SPEC.md`「個人技能成長」段落
- 2026-08-14：非 TOEIC 證照題庫正式導入與驗收暫時擱置；既有 `exam_type`、題庫 Pipeline、每日設定與作答資料結構已支援泛用證照類型，但目前只有 TOEIC 實際題庫，未來需先確認目標證照、題型、素材與推播規則後再排入 Roadmap — 詳見 `docs/ADR/discuss/skill-growth.md` 2026-08-14 條目
