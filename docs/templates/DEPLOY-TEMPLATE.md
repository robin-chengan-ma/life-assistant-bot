# DEPLOY-TEMPLATE — 個人 / 小專案 CI/CD 與上線指南（Template）

> 適用對象：個人開發者或小團隊，用 **GitHub** 管版控，搭配**免費雲端平台**做 CI/CD 與上線，
> 不使用公司內部那種 GitLab CI + ArgoCD + K8s 的重量級流程。
> 本文件與 `docs/templates/AGENTS-TEMPLATE.md` 搭配使用：AGENTS-TEMPLATE 管「怎麼開發」，本文件管「怎麼上線」。
>
> 內容比照實際大型專案的分支策略（feature → develop → main → tag，對應 test/stage/beta/production 四環境）
> 簡化而來——個人專案不需要四個環境，用兩層就夠，等專案真的變大、多人協作時再加環境，
> 避免違反「不為假設性未來需求設計」原則。

---

## 1. 分支策略（簡化版）

### 預設：單分支 + PR（大多數個人專案適用）

| 分支 | 角色 | 對應動作 |
| --- | --- | --- |
| `feature/*` | 功能開發，從 `main` 切出 | push 時自動跑 lint + test（不部署） |
| `main` | 唯一穩定分支，正式環境 | PR 合併後自動 lint + test + build + deploy production |

流程：`feature/xxx` 開發 → 開 PR → CI 跑 lint/test（綠燈才能合併）→ 合併進 `main` → 自動部署正式環境。

### 進階：加一層 staging（專案變大、需要上線前驗證再加）

| 分支 | 角色 |
| --- | --- |
| `feature/*` | 功能開發 |
| `develop` | 整合分支，對應 staging 環境，PR 合併自動部署到 staging |
| `main` | 穩定分支，只從 `develop` 合併，對應 production |

> 什麼時候該加 staging：當「合併到 main 就直接上線」開始讓你緊張、或有其他人要在上線前驗證時，再加這一層。個人 side project 初期建議先用單分支版本。

---

## 2. GitHub Actions Pipeline

### 檔案結構

```text
.github/
└── workflows/
    ├── ci.yml       # PR / push 到 feature、main 時跑 lint + test
    └── deploy.yml   # push 到 main 時跑 build + deploy
```

### `ci.yml`（以 Python/FastAPI 為例，其餘技術棧照 AGENTS-TEMPLATE 的指令對照表替換對應 step）

```yaml
name: CI

on:
  pull_request:
  push:
    branches-ignore: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Lint
        run: ruff check .

      - name: Test
        run: pytest -q --cov
```

**Go 版本替換 step：**

```yaml
      - uses: actions/setup-go@v5
        with:
          go-version: "1.25"
      - run: golangci-lint run
      - run: go test ./... -cover
```

**Node / Nuxt 版本替換 step：**

```yaml
      - uses: oven-sh/setup-bun@v2
      - run: bun install
      - run: bun run lint
      - run: bun run test
```

### `deploy.yml`（build image → push GHCR → 觸發部署）

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:latest,ghcr.io/${{ github.repository }}:${{ github.sha }}

      # 依部署平台補上對應 step，例如：
      # - Cloud Run: 用 google-github-actions/deploy-cloudrun@v2
      # - Render / Railway: 呼叫平台的 deploy hook (curl webhook URL)
```

**Image Registry 建議用 GitHub Container Registry（GHCR）**：跟 repo 權限綁定、免申請額外帳號，`GITHUB_TOKEN` 內建即可推 image，不需要另外管理 Docker Hub 帳密。

### GitHub Actions 免費額度

- **Public repo**：GitHub-hosted runner 完全免費、無用量上限
- **Private repo**：Free 方案每月 2,000 分鐘（Linux）。Windows 算 2 倍、macOS 算 10 倍扣額度，都用 Linux runner 的話很難超過
- 超額後可切換為量計費（2026 年起 Linux 2-core 約 $0.006/分鐘）

[GitHub Actions billing 官方文件](https://docs.github.com/billing/managing-billing-for-github-actions/about-billing-for-github-actions)

---

## 3. 免費雲端平台選擇（2026 現況）

平台的免費方案變動很快，以下是目前（2026）查證過的實際狀況，部署前建議直接到官網 pricing 頁再次確認。

### 後端 API（Docker 常駐服務）

| 平台 | 免費方案現況 | 適合情境 |
| --- | --- | --- |
| **Google Cloud Run**（推薦） | 真正的 always-free 額度：每月約 200 萬次請求 + 一定額度的 CPU/記憶體用量，按流量計費、無流量時不收費，天然適合低流量個人專案 | Docker container 常駐服務首選，冷啟動可接受、流量低時幾乎零成本 |
| **Render** | Web service 免費方案仍存在，但閒置 15 分鐘會 sleep，喚醒要 30–50 秒；要一直保持在線需升級 Starter（US$7/月起） | 能接受偶爾冷啟動延遲的展示型專案 |
| Railway | 已無長期免費方案，新帳號只有一次性 $5 試用額度，之後要 Hobby 方案（US$5/月起） | 想要最佳開發體驗、願意付小額月費 |
| Fly.io | 只剩 2 小時試用，無法長期免費使用 | 不建議作為免費方案 |

### 前端（Nuxt / Vue，靜態或 SSR）

| 平台 | 免費方案現況 | 注意事項 |
| --- | --- | --- |
| **Cloudflare Pages**（推薦） | 免費額度最寬鬆，對商業使用限制少 | Nuxt 需搭配 `nitro-cloudflare-dev` 等 preset |
| Vercel | 對 Nuxt SSR 支援最好、DX 最佳 | **Hobby 免費方案條款限個人非商業用途**，商業專案需升級 Pro |
| Netlify | 免費額度友善 | 條款也建議商業用途前再確認 |

### 資料庫

| 需求 | 推薦平台 | 免費方案現況 |
| --- | --- | --- |
| PostgreSQL | **Neon** | 每專案 100 CU-hours/月、0.5GB 儲存、scale-to-zero（閒置 5 分鐘自動休眠，下次查詢時喚醒） |
| PostgreSQL（含 Auth/Storage 一站式） | **Supabase** | 2 個專案、500MB 儲存、5萬 MAU 認證額度 |
| **MySQL**（hotels-api 目前使用的引擎） | **Aiven for MySQL** | 提供 always-free 方案，單節點、資源有限但可長期免費使用；PlanetScale 已在 2024 年取消免費方案，不再是選項 |

[Google Cloud 免費方案](https://cloud.google.com/free) ・ [Render 定價](https://render.com/pricing) ・ [Neon 免費方案](https://neon.com/) ・ [Aiven MySQL 免費方案](https://aiven.io/free-mysql-database)

---

## 4. 針對 hotels-api 現況的建議起手式

hotels-api 本身是 Python/FastAPI + MySQL(CloudSQL) + Docker，若要照此文件建立個人 GitHub 版 CI/CD，具體組合建議：

```text
GitHub repo（main + feature/* + PR）
   │
   ├─ PR / push feature → ci.yml：ruff check + pytest（免費、無限制，public repo 情境下）
   │
   └─ merge 進 main → deploy.yml：
         1. docker build 並 push 到 ghcr.io/<repo>:sha
         2. 觸發部署到 Google Cloud Run（低流量時近乎免費）
         3. 資料庫視情況接 Aiven MySQL 免費方案，或沿用現有 CloudSQL
```

### 部署前 Checklist

- [ ] `.env` 內的機敏資訊（`API_KEY`、DB 連線字串）改存 GitHub Actions Secrets（`Settings > Secrets and variables > Actions`），不進 repo
- [ ] Dockerfile 確認可直接 `docker build` 成功（本專案已有 `Dockerfile`，可直接沿用）
- [ ] 目標平台（Cloud Run / Render）設定對應的環境變數，對齊 `.env.example`
- [ ] 健康檢查路徑（本專案已有 `/health`、`/readyz`）設定給平台的 liveness/readiness probe
- [ ] 部署後跑一次 smoke test（呼叫 `/health` 確認 200）

---

## 5. 何時該升級成進階版（多環境 + GitOps）

當出現以下任一情況，才需要比照大型專案做法（多分支對應多環境、專用 CD 工具）：

1. 團隊超過 2–3 人，需要獨立的驗證環境避免互相干擾
2. 需要在上線前給非工程角色（PM、客戶）驗收
3. 部署頻率高到手動點部署變成負擔，需要更嚴謹的 gate（例如 main 才能自動上 production）

在那之前，本文件的單分支/雙分支 + GitHub Actions + 免費平台組合已足夠，不建議提前引入 K8s/ArgoCD 等重量級工具。
