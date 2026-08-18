---
updated: 2026-08-18
---

# 未定案草稿

> 想法先記在這裡，使用者確認要做才依 SPEC-TEMPLATE.md 的功能區塊格式升級進 `docs/specs/SPEC.md`。
> 已有完整決策脈絡的擱置/取消項目，這裡只放一行索引＋連結，詳細理由見對應的 discuss 檔案，不重複記錄。

## 待討論

## 已取消

- 2026-08-18：NFR-14～NFR-15 架構遷移正式取消；本專案不再將 `main.py`／`src/` 搬至 `backend/`，不拆建 `backend/api`、`backend/services`、`backend/repositories`、`backend/agents` 或 `data/`，也不為此調整部署入口。維持目前已完成實測的目錄與執行方式，避免大範圍搬遷造成既有功能回歸；FR-6c 與 FR-77 仍保留在 Roadmap — 詳見 `docs/ADR/discuss/robinson.md` 2026-08-18「取消 NFR-14～NFR-15 架構遷移」條目
- 2026-08-18：FR-15「成功傳送語音後 15 分鐘內不得再用語音修正」及其提示文案、`media_uploads.created_at` 修正窗口判斷正式取消；轉錄結果已改為執行前確認，聽錯時可立即重新傳語音或直接打字修正 — 詳見 `docs/ADR/discuss/voice-safety.md` 2026-08-18「取消 15 分鐘語音修正限制」條目
- 2026-08-15：Telegram 查無答案後教學、家庭／個人持久化知識庫讀寫與刪除、逐則對話紀錄、長記憶摘要，以及清除全部／指定主題知識與對話等功能正式取消；附屬的高風險語音逐字確認流程也隨適用功能取消。一般對話改用靜態人格 Prompt 與不落地的 10 分鐘短期上下文，對應路由、狀態、摘要排程與 `knowledge_base`／`conversation_logs`／`conversation_summaries` 三張資料表已排入 Phase 6 清理 — 詳見 `docs/ADR/discuss/robinson.md` 2026-08-15「移除持久化知識庫與對話記憶」及「淘汰路由、資料表與後端分層重構」條目
- 2026-08-15：除 Telegram 平台必要的 `/start` 外，所有一般使用者與 Owner Slash Commands 正式取消且不保留相容期，功能全面改由權限化選單與引導式對話處理 — 詳見 `docs/ADR/discuss/robinson.md` 2026-08-15「全面移除 Slash Commands」條目
- 2026-08-15：Telegram `/function`、中文觸發詞「我要看所有功能」及功能總覽／細節追問正式取消，後續由可見功能選單取代 — 詳見 `docs/ADR/discuss/robinson.md` 2026-08-15「使用規則選單與功能總覽移除」條目
- 2026-08-15：「客訴回饋」功能正式取消；Telegram／Mobile App 入口、API、流程與 `complaints` 資料表已排入 Phase 6 清理 — 詳見 `docs/ADR/discuss/robinson.md` 2026-08-15「權限管理的使用者建檔、功能授權與推播設定」及「淘汰路由、資料表與後端分層重構」條目
- 2026-08-14：FR-69／FR-70／FR-71「Mobile App 目標與指標設定／功能開關頁／Robin 專屬排程設定」正式取消；未建立頁面、API 或資料表，既有 Telegram 設定流程維持不變 — 詳見 `docs/ADR/discuss/mobile-app.md` 2026-08-14 條目
- 2026-08-04：視覺化後台原採 Notion，改用 Mobile App（React Native + Expo）— 詳見 `docs/ADR/discuss/mobile-app.md` 2026-08-04 條目
- 2026-08-05：AI 自主診斷＋GitHub PR 自動化修復機制，改用「完整 log 上傳雲端＋私訊 Robin 專屬連結」— 詳見 `docs/ADR/discuss/service-resilience.md` 2026-08-05 條目
- 2026-08-11：FR-64a 藍牙體重計整合全面取消；原生 BLE 與 Web Bluetooth／Bluefy 方案均不採用，Android、iOS、Web 統一改為手動輸入體重 — 詳見 `docs/ADR/discuss/mobile-app.md` 2026-08-11 條目

## 擱置中

- 2026-08-08：`language`（語言學習：英文口說練習、其他語言學習）功能開關已建立但功能未展開，不排入目前 Roadmap，何時展開留待 Phase 4 全部完成後再議 — 詳見 `docs/ADR/discuss/skill-growth.md` 2026-08-08 條目、`docs/specs/SPEC.md`「個人技能成長」段落
- 2026-08-14：非 TOEIC 證照題庫正式導入與驗收暫時擱置；既有 `exam_type`、題庫 Pipeline、每日設定與作答資料結構已支援泛用證照類型，但目前只有 TOEIC 實際題庫，未來需先確認目標證照、題型、素材與推播規則後再排入 Roadmap — 詳見 `docs/ADR/discuss/skill-growth.md` 2026-08-14 條目
- 2026-08-14：專案根目錄 `README.md` 的完整撰寫暫時擱置；NFR-14～NFR-15 目錄架構遷移已取消，未來改以「現行功能範圍穩定」作為開工時點。預計涵蓋專案簡介、主要功能、技術棧、目錄結構、環境變數設定、本地啟動、測試、部署、資料庫 migration、安全注意事項及文件索引；實際章節仍須於撰寫前依專案現況確認。
