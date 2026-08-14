# 平台架構與治理 討論紀錄

> 本檔案收錄 robinson 母 spec 中，屬於全專案基礎架構與治理層級、不專屬任何單一功能模組的 ADR（ADR-1、ADR-4、ADR-10、ADR-11）。與特定功能相關的 ADR 已分別遷移至對應功能的 discuss 檔案（見新版 `docs/specs/SPEC.md` 各功能區塊的討論紀錄連結）。

## 2026-07-29 [標籤：AI] ADR-1：三層式架構（前台 / 資料層 / 後台）

**狀態**：accepted（後台選型「Notion」的部分 superseded by mobile-app 討論紀錄 2026-08-04 條目，改採 Mobile App；Telegram 前台與 Neon/GDrive 資料層的決策維持不變）

**背景**：需要在免費資源限制下，兼顧「聊天即服務」的體驗與「視覺化查看」的需求。

**討論內容**：比較方案 A（自建 Web Dashboard，完全客製化但開發前端、部署成本高，不符合「越少 UI 越好」）與方案 B（全部塞進 Telegram 含圖表，單一入口但 Telegram 不擅長呈現複雜圖表/表格）。

**決策**：Telegram 作為唯一前台入口；Neon（結構化）+ Google Drive（靜態圖像）作為資料層；Notion 作為選配的視覺化後台。

**理由**：Telegram 天生支援文字/語音、免費、家人已熟悉；Neon/GDrive 免費額度足敷家庭規模使用。

**後果**：Notion 整合可獨立於核心對話邏輯之外開發，允許排在最後或先不做而不影響 MVP 可用性。

## 2026-07-29 [標籤：AI] ADR-4：MVP 分期策略

**狀態**：accepted（Phase 5「Notion 後台」已取消，併入 Phase 4，見 mobile-app 討論紀錄）

**背景**：需求涵蓋 10+ 個功能模組，若全部視為 MVP 會拉長首次上線時間、且違反「MVP」定義。

**決策**：MVP（Phase 1）僅涵蓋「平台基礎設施＋權限治理＋對話核心（含知識庫）＋待辦事項＋心情小記＋健康監控告警」；其餘功能模組依複雜度與相依性分至 Phase 2～4。

**理由**：①待辦事項與心情小記是最高頻、最輕量的日常互動，適合最先驗證聊天式互動的可用性 ②求職與技能成長複雜度高、依賴多個外部資料源，適合核心架構穩定後再疊加 ③記帳與體態管理邏輯相似，適合放在同一 Phase 一起做 ④視覺化後台屬於「錦上添花」的展示層。

**替代方案**：技術棧驗證優先（已否決，使用者感受不到聊天助手的核心價值）；全功能一次到位（已否決，開發週期過長）。

**後果**：實作計畫依 Phase 0～4 逐步展開，各 Phase 完成後才進入下一個 Phase 的詳細 spec 與 TDD 循環。

## 2026-07-30 [標籤：AI] ADR-10：資料庫 Schema 建立採「先審核後執行」流程，並統一記錄於 `src/schema/`

**狀態**：accepted

**背景**：本產品有多張資料表，若每次建表都各自決定欄位設計，容易缺乏一致性；Robin 希望對每一張表的設計保有審核權，同時要有一份「活文件」讓所有人（包含未來的 AI agent）能快速查閱目前的資料庫與 API 全貌。

**決策**：①所有資料表由 Claude 撰寫 `CREATE TABLE` SQL 並負責執行，但執行前必須先呈現 SQL 與設計理由給 Robin，取得明確同意 ②執行完成後立即同步記錄到 `src/schema/db_schema.md` ③所有 API 路由統一記錄於 `src/schema/api_schema.md` ④每張表與每個欄位都必須用 `COMMENT ON TABLE`/`COMMENT ON COLUMN` 附上中文說明，直接寫在 SQL 裡。

**替代方案**：用 migration 工具（如 Alembic）自動產生/管理 schema（已否決，對這個規模的個人專案過重）；不特別記錄、需要時直接連 Neon 查看（已否決，無法在動手改資料庫前先討論設計）。

**理由**：比照 Human-in-the-Loop 精神——AI 可以自主產生方案，但正式對資料庫執行變更前一定要有人核准。

**後果**：Phase 0 Step 0.5（Neon 資料庫初始化）與往後任何需要新增/修改資料表的 Step，都必須先在對話中提出 SQL 草案與理由。

## 2026-07-30 [標籤：AI] ADR-11：ADR-10「先審核後執行」的執行機制改為「Migration 檔案 + 開機自動套用」，取代人工貼 SQL

**狀態**：accepted

**背景**：ADR-10 規定建表前必須經 Robin 審核同意，但沒有規定「同意後由誰、怎麼執行」。實測發現 Cowork sandbox 連不到 Neon、Telegram Bot API、GitHub REST API（`api.github.com`）、Google/YouTube API、Notion API（皆被 sandbox 網路白名單擋下），但 `github.com`（git 協定）可連線，`git push` 實測成功。

**決策**：①新增 `src/migrations/` 資料夾，存放已核准的 SQL，檔名格式 `NNNN_說明.sql`，依序編號、不可回頭修改已套用過的檔案 ②新增 `schema_migrations` 中介追蹤表 ③`main.py` 啟動時自動掃描並依序執行尚未套用的檔案 ④流程仍維持審核精神：Claude 提出草案→Robin 同意→Claude 存成 migration 檔並 commit+push 到 GitHub main→Render 自動重新部署→開機自動套用 ⑤`git push` 一律透過 `GITHUB_TOKEN` + git credential helper 完成驗證。

**替代方案**：Robin 自行連 Neon 主控台貼 SQL（已否決，不符合全自動化目標）；本機 Claude Code CLI 執行（保留作為此方案失效時的備援）；透過 GitHub REST API 自動開 PR（此路徑在 sandbox 內無法直接呼叫，不採用）。

**理由**：這是唯一能同時滿足「人工審核不能省」與「核准後全自動、不用自己動手」兩個條件的作法。

**後果**：往後任何新增/修改資料表，都改為「提案→Robin 同意→Claude 建立 migration 檔並 push」，不再手動於 Neon 主控台執行；`src/schema/db_schema.md` 的紀錄時機從「執行後」改為「push 後」立即記錄。
