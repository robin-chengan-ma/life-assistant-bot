# 規範 — 新專案起手式套件

這個資料夾是**新專案的完整起手檔案集**，收錄了 SDD+TDD 開發框架所需的全部檔案。開始一個全新專案時，把整個資料夾內容複製到新專案根目錄即可（`規範/` 本身不用複製，複製底下的檔案/子資料夾）。

## 檔案清單

| 路徑 | 用途 | 新專案要做什麼 |
| --- | --- | --- |
| `CLAUDE.md` | Claude Code 匯入指令（`@AGENTS.md`） | 原封不動複製 |
| `AGENTS.md` | 通用版 SDD+TDD 開發準則（含技術棧指令對照表） | 複製後，把最後「專案覆寫」區塊的 Tech Stack 表格填成新專案實際技術棧 |
| `.claude/agents/*.md` | 7 個 sub-agent 角色定義（code-reviewer、debugger、planner、refactorer、researcher、spec-writer、tdd-guide） | 原封不動複製 |
| `.claude/commands/*/SKILL.md` | 4 個 slash 指令（`/sdd`、`/tdd`、`/spec`、`/efficiency`） | 原封不動複製 |
| `.claude/rules/sdd-tdd-rules.md` | rules 自動載入指標檔（內容指向 `AGENTS.md`，避免規則重複維護兩份） | 原封不動複製 |
| `docs/templates/AGENTS-TEMPLATE.md` | `AGENTS.md` 的乾淨母版備份 | 原封不動複製（留著，之後要重新產生 `AGENTS.md` 或建更多專案時當來源） |
| `docs/templates/SPEC-TEMPLATE.md` | 新建 spec 用的空白模板 | 原封不動複製 |
| `docs/templates/DEPLOY-TEMPLATE.md` | 個人 GitHub + 免費雲端平台 CI/CD 與上線指南 | 原封不動複製；真的要部署時再照文件內容建立 `.github/workflows/` |

## 新專案啟動步驟

1. 把 `規範/` 底下所有檔案/資料夾複製到新專案根目錄
2. 打開 `AGENTS.md`，找到最後「專案覆寫（Project Overrides）」區塊，填入新專案的 Tech Stack 表格（語言、框架、測試框架、Lint 工具、部署方式）
3. 建立 `docs/specs/` 空資料夾（第一個 spec 建立時會自動用到 `docs/templates/SPEC-TEMPLATE.md`）
4. 需要上線時，照 `docs/templates/DEPLOY-TEMPLATE.md` 的步驟建立 `.github/workflows/ci.yml` 與 `deploy.yml`
5. 開始開發時，跟 Claude 說「SDD」或「開始 TDD」即可觸發對應 workflow

## 不包含在這裡、新專案要自己重寫的東西

- `README.md`：專案說明，每個專案內容不同，不適合放模板
- `docs/specs/*/SPEC.md`：實際功能 spec，屬於專案內容，從空白開始建立

## 這份套件的來源

整理自三個實際專案（hotels-api / Python+FastAPI、backend-develop / Go+Gin、frontend-develop / Nuxt+Vue）驗證過的共同規則，確認 SDD+TDD 流程本文可跨技術棧逐字共用，只有指令和部署方式需要替換。
