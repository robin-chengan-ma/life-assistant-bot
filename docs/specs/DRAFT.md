---
updated: 2026-08-14
---

# 未定案草稿

> 想法先記在這裡，使用者確認要做才依 SPEC-TEMPLATE.md 的功能區塊格式升級進 `docs/specs/SPEC.md`。
> 已有完整決策脈絡的擱置/取消項目，這裡只放一行索引＋連結，詳細理由見對應的 discuss 檔案，不重複記錄。

## 待討論

- [ ] 2026-08-12：收藏清單／旅遊行程／探索地圖／成果展示（規格範圍外的新方向，已完成 Leaflet 地圖技術 POC 與收藏清單第一階段實作，但尚未走規格確認流程、未收錄進 SPEC.md，需定案後才能排入 Roadmap）— 詳見 `docs/ADR/discuss/mobile-app.md` 2026-08-12 條目
- [ ] 2026-08-12：Mobile App「重要日子設定」的 Telegram 提醒推播（App 端管理介面與資料結構已完成，Telegram 提醒依當時指示不屬於該輪範圍；此功能整體尚未收錄進 SPEC.md）— 詳見 `docs/specs/PROGRESS.md` 2026-08-12「重要日子設定與待辦整合行事曆」條目
- [ ] 2026-08-14：求職分析模組功能調整；目前只有調整方向，實際欄位、流程、圖表、API 與驗收條件尚待逐項確認。
- [ ] 2026-08-14：考試成績模組功能調整；目前只有調整方向，實際欄位、流程、圖表、API 與驗收條件尚待逐項確認。
- [ ] 2026-08-14：Telegram 功能完整盤點與重構討論；需先盤點現有指令、自然語言入口、多輪狀態、排程、權限、Mobile 共用邏輯與測試覆蓋，再確認重構範圍及執行順序，不提前修改正式規格。

## 已取消

- 2026-08-14：FR-69／FR-70／FR-71「Mobile App 目標與指標設定／功能開關頁／Robin 專屬排程設定」正式取消；未建立頁面、API 或資料表，既有 Telegram 設定流程維持不變 — 詳見 `docs/ADR/discuss/mobile-app.md` 2026-08-14 條目
- 2026-08-04：視覺化後台原採 Notion，改用 Mobile App（React Native + Expo）— 詳見 `docs/ADR/discuss/mobile-app.md` 2026-08-04 條目
- 2026-08-05：AI 自主診斷＋GitHub PR 自動化修復機制，改用「完整 log 上傳雲端＋私訊 Robin 專屬連結」— 詳見 `docs/ADR/discuss/service-resilience.md` 2026-08-05 條目
- 2026-08-11：FR-64a 藍牙體重計整合全面取消；原生 BLE 與 Web Bluetooth／Bluefy 方案均不採用，Android、iOS、Web 統一改為手動輸入體重 — 詳見 `docs/ADR/discuss/mobile-app.md` 2026-08-11 條目

## 擱置中

- 2026-08-08：`language`（語言學習：英文口說練習、其他語言學習）功能開關已建立但功能未展開，不排入目前 Roadmap，何時展開留待 Phase 4 全部完成後再議 — 詳見 `docs/ADR/discuss/skill-growth.md` 2026-08-08 條目、`docs/specs/SPEC.md`「個人技能成長」段落
- 2026-08-14：非 TOEIC 證照題庫正式導入與驗收暫時擱置；既有 `exam_type`、題庫 Pipeline、每日設定與作答資料結構已支援泛用證照類型，但目前只有 TOEIC 實際題庫，未來需先確認目標證照、題型、素材與推播規則後再排入 Roadmap — 詳見 `docs/ADR/discuss/skill-growth.md` 2026-08-14 條目
- 2026-08-14：全專案程式碼與目錄架構大重構暫時擱置，待現有功能全部完成後再依 Coding Style、Clean Architecture 與 `api → services → repositories` 單向依賴原則規劃；預計涵蓋後端移入 `backend/`、Telegram Bot 職責拆分、Repository／Schema／Agent／Config 等分層與大型檔案拆解，實際遷移順序、相容策略及測試基準尚未定案。
- 2026-08-14：專案根目錄 `README.md` 的完整撰寫暫時擱置，待現有功能完成且目錄架構重構定案後執行，避免文件與實際專案結構反覆不一致；預計涵蓋專案簡介、主要功能、技術棧、目錄結構、環境變數設定、本地啟動、測試、部署、資料庫 migration、安全注意事項及文件索引，實際章節仍須於撰寫前依最終專案現況確認。
