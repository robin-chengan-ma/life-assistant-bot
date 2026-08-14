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

### 文件路徑規則（本專案與日後所有專案通用）

| 檔案 | 用途 |
| --- | --- |
| `docs/specs/SPEC.md` | 唯一定案規格：產品背景、技術棧與平台策略、產品藍圖與功能規格、例外處理與邊界條件、驗收矩陣 |
| `docs/specs/PROGRESS.md` | 開發進度時程、任務狀態、推版紀錄 |
| `docs/specs/DRAFT.md` | 未定案（待討論／臨時想到／已取消／擱置中） |
| `docs/ADR/discuss/<功能>.md` | 按功能拆檔的討論紀錄，跟 AI／PM／QA／組員／單位／使用者的討論都記在這裡，用標籤區分對象 |
| `docs/ADR/debug/<功能>.md` | 按功能拆檔的修復紀錄，不論有沒有改 code 都要記 |
| `docs/reference/<主題>.md` | 技術參考文件（如 API Schema、DB Schema），跟著程式碼異動更新，不是決策紀錄也不是產品規格；內容力求簡述，避免堆疊敘事性長段落 |

> **防呆**：`docs/specs/PROGRESS.md`、`docs/specs/DRAFT.md` 若不存在（例如被誤刪），視為內容為空，
> 依對應的 `docs/templates/PROGRESS-TEMPLATE.md`／`DRAFT-TEMPLATE.md` 直接建立空白版本，不中斷流程、
> 不當作錯誤回報給使用者卡住等待。

1. 非 trivial 任務必須先查 `docs/specs/SPEC.md` 是否已有該功能的定案規格，再實作
2. 沒有定案規格時，先查 `docs/specs/DRAFT.md`；沒有草稿就先寫進 DRAFT.md，使用者確認要做才升級進 SPEC.md
3. 不得重問 SPEC.md 或 `docs/ADR/discuss/` 中已記錄的決策
4. 不得跳過 SPEC.md／DRAFT.md 直接進入中大型實作
5. 中大型實作前必須等使用者確認
6. 討論過程即時記進 `docs/ADR/discuss/<功能>.md`；修 bug 無論有沒有改 code 都要記進 `docs/ADR/debug/<功能>.md`
7. 實作完成後必須更新 SPEC.md 對應功能區塊（若規格有變動）、PROGRESS.md 任務狀態與 `updated` 日期
8. SPEC.md 單一功能區塊若成長超過約 200 行，必須把細節移到 `discuss/` 或獨立附錄，SPEC.md 本體只留摘要＋連結，避免重新腫成難以維護的巨檔

### 討論紀錄格式（`docs/ADR/discuss/<功能>.md`）

同一功能的多次討論用同一檔案，依時間附加新的段落：

```markdown
## YYYY-MM-DD [標籤：AI / PM / QA / 組員 / 單位 / 使用者] <討論主題>
**狀態**：pending | accepted | superseded | deprecated
**背景**：<為什麼需要討論>
**討論內容**：<過程摘要>
**決策**（若有）：<最終選擇>
**理由**：<選擇原因>
**後果**：<決策帶來的影響>
```

### 修復紀錄格式（`docs/ADR/debug/<功能>.md`）

同一功能的多次除錯用同一檔案，依時間附加新的段落：

```markdown
## YYYY-MM-DD <問題摘要>
**現象**：<觀察到的問題>
**排查過程**：<怎麼定位問題>
**根因**：<真正原因>
**修復方式**：<有改 code 附檔案路徑；沒改 code 要說明原因>
**驗證方式**：<怎麼確認修好了>
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
8. [SDD] 更新 SPEC.md / PROGRESS.md，視情況記錄 discuss / debug
```

---

## Workflows（任何 AI 工具都應遵循）

以下是可被觸發的工作流程。使用者可以說「跑 SDD 流程」、「開始 TDD」、「查 spec 進度」來啟動。

### Workflow: SDD（啟動或繼續 spec 驅動開發）

觸發詞：「SDD」、「spec」、「繼續」、「上次做到哪」、任何非 trivial 新任務

```text
步驟：
1. 讀取 docs/specs/SPEC.md，搜尋是否已有該功能的定案區塊
2. 已定案：
   - 讀取對應功能區塊；若段落連結了 docs/ADR/discuss/<功能>.md，一併讀取脈絡
   - 讀取 docs/specs/PROGRESS.md，從對應 FR 編號找下一個未完成任務
   - 報告：「目前進度 X/Y，下一個 task 是...」
   - 等使用者確認後開始實作
3. 未定案：
   - 查 docs/specs/DRAFT.md 是否已有相關草稿
   - 有草稿且使用者確認要做 -> 依 docs/templates/SPEC-TEMPLATE.md 的功能區塊格式，補進
     SPEC.md 對應功能區塊，DRAFT.md 該項標記「已升級」
   - 沒有草稿 -> 先記錄進 DRAFT.md，待使用者確認才升級進 SPEC.md
   - 呈現給使用者確認，確認後才開始實作
4. 中大型任務 -> 呈現實作計畫（影響範圍、步驟、風險），等確認
5. 討論過程即時寫進 docs/ADR/discuss/<功能>.md（標註對象標籤與狀態）
6. 實作完成後：
   - 更新 SPEC.md 對應功能區塊（若規格有變動；單一區塊超過約 200 行要把細節移到 discuss/ 或附錄）
   - 更新 PROGRESS.md：任務狀態、對應 FR 編號、開發者（Claude／Codex／Robin）、updated 日期，
     必要時補推版紀錄
   - 若過程中修了 bug（不論有沒有改 code）-> 記錄進 docs/ADR/debug/<功能>.md
   - 報告：影響範圍、測試狀態、剩餘 tasks
   - 若剛完成的是單一 Step（子階段）-> 主動詢問使用者：「這個 step 做完了，要執行 `/compact` 嗎？」
   - 若剛完成整個 Phase（大階段，含整個功能最後一個 Phase）-> 主動詢問使用者：
     「這個 phase 做完了，要執行 `/clear` 嗎？（提醒：`/clear` 前請確認 SPEC.md / PROGRESS.md
     已更新，避免進度遺失）」
   - 沒有 Phase 結構的舊文件 -> 以「一個完整邏輯段落完成」為準，比照上述規則主動詢問
   - 兩個指令一律只提醒、不自動執行，是否執行由使用者決定
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

### Workflow: Spec Status（查看規格與進度）

觸發詞：「spec 進度」、「spec status」、「有哪些功能」

```text
步驟：
1. 讀取 docs/specs/SPEC.md，列出所有已定案功能區塊
2. 讀取 docs/specs/PROGRESS.md，計算每個功能對應 FR 的完成率
3. 讀取 docs/specs/DRAFT.md，列出待討論／擱置中的項目
4. 輸出摘要表格：
   | 功能 | 定案狀態 | 進度 | 最後更新 |
5. 問使用者要繼續哪個功能，或要不要把某個 DRAFT 項目升級進 SPEC.md
```

### Workflow: New Feature（新增功能到 SPEC）

觸發詞：「新功能」、「new spec」、「新增規格」

```text
步驟：
1. 問使用者功能名稱與概要（或從對話推斷）
2. 先寫進 docs/specs/DRAFT.md（未定案，待確認）
3. 使用者確認要做 -> 依 docs/templates/SPEC-TEMPLATE.md 的功能區塊格式，補進 docs/specs/SPEC.md
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
- 規格文件一律放在 `docs/specs/SPEC.md`（定案）／`docs/specs/PROGRESS.md`（進度）／`docs/specs/DRAFT.md`（未定案），討論與除錯紀錄放在 `docs/ADR/discuss/<功能>.md`／`docs/ADR/debug/<功能>.md`（按功能拆檔），模板放在 `docs/templates/`

### 覆蓋率與安全要求微調（如與預設不同才填）

- 覆蓋率要求：預設 80%+／金融、認證、安全邏輯 100%（如新專案有不同標準，在此註明並說明原因）
- 額外的 coding convention：<專案特有規範>
