# AGENTS.md — 通用版專案開發準則（Template）

> **這是一份可直接複製到任何新專案的通用模板**，不綁定特定語言或框架。
> 使用方式：複製整份檔案為新專案根目錄的 `AGENTS.md` 與 `CLAUDE.md`（`CLAUDE.md` 內容固定為 `@AGENTS.md`），
> 再依照文末「專案覆寫」區塊，把新專案的技術棧、指令填進 Tech Stack 對照表即可。
> 第 1–116 行（SDD / TDD / 效率紀律 / 通用原則 / Workflows）是技術棧無關的通用規則，**不需要改**；
> 唯一要客製的是最後的「專案覆寫」區塊。
>
> 本模板整理自三個實際專案的共同規則（Python/FastAPI、Go、Nuxt/Vue），驗證過這套 SDD+TDD 流程
> 在不同技術棧下是可以逐字共用的，只有指令和目錄結構需要換。

本檔案是所有 AI 開發工具（Claude Code、Codex、Gemini、Cursor、Copilot 等）在本專案中的行為準則。
任何 LLM agent 進入本專案時，必須先讀取此檔案並遵守以下規則。

---

## SDD（Spec-Driven Development）— 硬規則

1. 非 trivial 任務必須先找或建 spec（`docs/specs/<slug>/SPEC.md`），再實作
2. 不得重問 spec 中已記錄的決策
3. 不得跳過 spec 直接進入中大型實作
4. 實作完必須更新 spec 的 checkbox 和 `updated` 日期
5. 中大型實作前必須等使用者確認

### SDD 工作流程

```text
1. 尋找 active spec（docs/specs/<feature-slug>/SPEC.md）
2. Spec 已存在 -> 讀取，理解需求和進度，從 checkbox 找下一個待辦
3. Spec 不存在 -> 先建 spec，等使用者確認再實作
4. 中大型任務 -> 呈現實作計畫（影響範圍、步驟、風險），等確認
5. 實作完成 -> 更新 spec checkbox、updated 日期、PROGRESS.md（若有）
```

### 決策記錄格式（ADR）

重大技術決策記在 spec 中：

```markdown
### ADR：<決策主題>
**背景**：<為什麼需要做這個決策>
**決策**：<最終選擇>
**理由**：<選擇原因>
**替代方案**：
- 方案 A：<優缺點>
- 方案 B：<優缺點>
**後果**：<決策帶來的影響>
**狀態**：accepted | superseded | deprecated
```

---

## TDD（Test-Driven Development）— 強烈建議

1. 新功能、修 bug、重構時優先先寫測試
2. 遵循 Red -> Green -> Refactor 循環
3. 覆蓋率目標 80%+，金融/認證/安全邏輯 100%
4. 不做 TDD 時必須說明原因
5. 回報時交代：測試是否新增、是否執行、未驗證範圍

### TDD 循環

```text
RED（寫失敗的測試）
  -> GREEN（寫最少的實作讓測試通過）
  -> REFACTOR（改善品質，保持綠燈）
  -> 重複
```

### 測試分層

| 層級 | 範圍 | 何時必要 | 覆蓋率 |
| --- | --- | --- | --- |
| Unit | 單一函式/方法/元件 | 所有 public function | 80%+ |
| Integration | API endpoint / DB 操作 / Server handler | 所有 API route | 80%+ |
| E2E | 完整使用者流程 | 關鍵業務流程 | 關鍵路徑 |

### 必須覆蓋的 Edge Case

1. Null / Undefined / 空值
2. 空集合（空陣列、空字串）
3. 邊界值（最小、最大、零）
4. 錯誤路徑（網路失敗、DB 錯誤、timeout）
5. 併發 / 競態條件
6. 特殊字元（Unicode、注入字串）

### 不適合 TDD 的情境

純 UI 樣式調整、Prototype/POC、第三方 wrapper、一次性 script — 至少補最小有價值的測試。

---

## 效率紀律 — 硬規則

1. **不重複讀取** — 同一檔案在同一 session 只讀一次
2. **不做無意義 retry** — 失敗就分析原因換方法，不要 sleep + retry
3. **不複述已知資訊** — 讀過就直接執行，不要回吐給使用者
4. **能平行就平行** — 獨立操作同時發出
5. **先想再做** — 組織完整再寫，不要邊寫邊改來回修
6. **精簡回報** — 只報結論、變更、下一步

---

## 通用原則

1. 簡潔直接，不過度工程
2. 只改被要求改的東西
3. 不為假設性未來需求設計
4. 安全優先（OWASP Top 10）
5. 每次實作交代影響範圍和測試狀態

---

## SDD + TDD 整合流程

```text
1. [SDD] 找到或建立 Spec
2. [SDD] 確認需求和實作計畫
3. [SDD] 使用者確認 -> 開始實作
4. [TDD] 寫失敗的測試（RED）
5. [TDD] 寫最少的實作（GREEN）
6. [TDD] 重構（REFACTOR）
7. [TDD] 重複 4-6 直到完成
8. [SDD] 更新 Spec / Progress / Changelog
```

---

## Workflows（任何 AI 工具都應遵循）

以下是可被觸發的工作流程。使用者可以說「跑 SDD 流程」、「開始 TDD」、「查 spec 進度」來啟動。

### Workflow: SDD（啟動或繼續 spec 驅動開發）

觸發詞：「SDD」、「spec」、「繼續」、「上次做到哪」、任何非 trivial 新任務

```text
步驟：
1. 搜尋 docs/specs/ 目錄，找相關的 SPEC.md
2. 若找到：
   - 讀取 spec，理解需求、決策歷史、目前進度
   - 從 checkbox 找到下一個未完成的 task
   - 報告：「目前進度 X/Y，下一個 task 是...」
   - 等使用者確認後開始實作
3. 若沒找到：
   - 用 docs/templates/SPEC-TEMPLATE.md 建立新 spec
   - 填入已知資訊，標記待確認項目
   - 呈現給使用者確認，確認後才開始實作
4. 實作完成後：
   - 更新 spec 中對應的 checkbox 為 [x]
   - 更新 spec 的 updated 日期
   - 報告：影響範圍、測試狀態、剩餘 tasks
```

### Workflow: TDD（啟動測試驅動開發循環）

觸發詞：「TDD」、「寫測試」、「test first」

```text
步驟：
1. 分析目前要做的功能或要修的 bug
2. RED -- 寫失敗的測試：
   - 建立 test file（若不存在）
   - 寫 test case，定義預期行為
   - 執行測試，確認因「功能未實作」而失敗
3. GREEN -- 寫最少的實作：
   - 只寫剛好讓測試通過的程式碼
   - 執行測試，確認通過
4. REFACTOR -- 改善品質：
   - 消除重複、改善命名、優化結構
   - 執行測試，確認仍全部通過
5. 重複 2-4 直到功能完成
6. 報告：
   - 新增測試數量和名稱
   - 執行結果（通過/失敗）
   - 覆蓋率
   - 未驗證範圍
```

### Workflow: Spec Status（查看所有 spec 進度）

觸發詞：「spec 進度」、「spec status」、「有哪些 spec」

```text
步驟：
1. 掃描 docs/specs/ 下所有 SPEC.md
2. 讀取每個 spec 的 frontmatter（title, status, updated）
3. 計算每個 spec 的 checkbox 完成率
4. 輸出摘要表格：
   | Spec | 狀態 | 進度 | 最後更新 |
5. 問使用者要繼續哪個 spec
```

### Workflow: New Spec（建立新 spec）

觸發詞：「新 spec」、「new spec」、「建 spec」

```text
步驟：
1. 問使用者 feature name（或從對話推斷）
2. 建立 docs/specs/<slug>/SPEC.md（使用 template）
3. 填入已知資訊
4. 呈現給使用者確認和補充
```

---

## 專案覆寫（Project Overrides）— 新專案請填這裡

> 以下內容請依新專案實際狀況覆寫，刪掉用不到的技術棧列。
> 三個實際案例（Python/FastAPI、Go、Nuxt/Vue）驗證過的指令已整理成下方對照表，
> 新專案若剛好是這三種技術棧，直接照抄指令即可；若是其他技術棧，比照格式補上。

### Tech Stack（範例，請替換為實際專案內容）

| 層級 | 技術 |
| --- | --- |
| Language / Runtime | <例：Python 3.11 / Go 1.25 / Node 20 + Bun> |
| Framework | <例：FastAPI / Gin / Nuxt 4> |
| 資料層 | <例：MySQL + pymysql / PostgreSQL + GORM / — > |
| 測試框架 | <例：pytest / testify + testcontainers / vitest> |
| Lint | <例：ruff / golangci-lint / eslint> |
| 部署 | <例：Docker + GitHub Actions + Cloud Run> |

### 技術棧指令對照表（Command Adapter）

跨三種常見技術棧實測整理，作為「填 Tech Stack 表格」時的指令參考：

| 動作 | Python（pytest + ruff） | Go（go test + golangci-lint） | Node / Vue（vitest + eslint） |
| --- | --- | --- | --- |
| 安裝依賴 | `pip install -r requirements.txt` | `go mod download` | `bun install` / `npm install` |
| Lint | `ruff check .` | `golangci-lint run` | `eslint . --max-warnings 0` |
| Lint 自動修復 | `ruff check --fix .` | `golangci-lint run --fix` | `eslint . --fix --max-warnings 0` |
| 單元測試 | `pytest -q` | `go test ./...` | `vitest run` |
| 測試覆蓋率 | `pytest --cov` | `go test -cover ./...` | `vitest run --coverage` |
| 本地啟動（含依賴服務） | `make docker-up` | `make docker-up` | `bun dev` |
| Build | 通常免建置（直接跑） | `go build ./...` | `bun run build` |
| 型別檢查 | `mypy .`（若有用） | 內建於編譯 | `vue-tsc --noEmit` |

> 新增其他技術棧（例如 Rust / Java）時，比照上表格式補一欄即可，維持「同一份規則、不同語言指令」的原則。

### 目錄結構慣例（依實際專案調整）

- 若專案是後端服務：優先採 `api/`（或 `controller/`）→ `service/` → `repository/` 三層職責分離，禁止跨層直接呼叫
- 若專案是前端應用：優先採 Feature-Sliced 慣例（`features/<name>/{_components,_composables,_types,_views}` + `index.ts` 作為對外唯一入口），feature 之間禁止互相 import
- Spec 一律放在 `docs/specs/<slug>/SPEC.md`，模板放在 `docs/templates/`

### 覆蓋率與安全要求微調（如與預設不同才填）

- 覆蓋率要求：預設 80%+／金融、認證、安全邏輯 100%（如新專案有不同標準，在此註明並說明原因）
- 額外的 coding convention：<專案特有規範>
