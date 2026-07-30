---
title: Submodules — 共用子模組基礎骨架
slug: submodules-core
status: draft
created: 2026-07-29
updated: 2026-07-29
owner: Robin
---

# Submodules — 共用子模組基礎骨架

## 概要

`submodules/` 收斂 Robinson（以及未來其他個人專案）都會用到的最基礎技術操作，拆成三個彼此獨立、不含商業邏輯的小工具：PostgreSQL 連線與 CRUD、Telegram 訊息發送、LLM（Gemini）呼叫。目標是「可被跨專案重複使用」，因此一律不依賴特定框架（Flask/Django）與本專案的商業邏輯，僅依賴外部注入的設定（金鑰、連線字串）。本 spec 隸屬於 [robinson SPEC.md](../robinson/SPEC.md) 的 Phase 0（專案基礎建設）。

**每個子模組資料夾一律採固定四檔案結構**（見 ADR-4），這是一條硬規則，之後新增任何 submodules 小工具都必須遵守：

```
submodules/
├── llm/
│   ├── .env.example
│   ├── client.py
│   ├── requirements.txt
│   └── README.md
├── cloudsql/
│   ├── .env.example
│   ├── client.py
│   ├── requirements.txt
│   └── README.md
└── telegram/
    ├── .env.example
    ├── client.py
    ├── requirements.txt
    └── README.md
```

## 需求

### 功能性需求

- [x] FR-1：`submodules/cloudsql` 提供連線池管理與泛用 CRUD 介面（select / insert / update / delete），一律使用參數化查詢；目前實際串接 Neon PostgreSQL，命名為 cloudsql 是為了未來可替換成其他 PostgreSQL 相容服務時介面不變
- [x] FR-2：`submodules/telegram` 提供 Bot 基礎 HTTP Client（`call(method, payload)`）與常用訊息發送方法（文字、圖片、typing 狀態提示）
- [x] FR-3：`submodules/llm` 提供 LLM Client 初始化與文字生成 / 圖文生成呼叫；目前實際串接 Gemini API，模型固定 `gemini-flash-latest`，命名為 llm 是為了未來替換或新增供應商時介面不變
- [x] FR-4：三個子模組彼此獨立、互不 import，也不依賴 `backend/` 或本專案任何商業邏輯（單向依賴：上層可以 import submodules，反向禁止）
- [x] FR-5：所有連線資訊（DB 連線字串、Bot Token、API Key）一律由外部呼叫端注入或讀取環境變數，子模組內部不得寫死任何金鑰
- [x] FR-6：每個子模組資料夾一律只包含 `client.py`、`README.md`、`requirements.txt`、`.env.example` 四個檔案，不得拆成多個 `.py` 檔、不得加 `__init__.py`（見 ADR-4）

### 非功能性需求

- [x] NFR-1：安全 — CRUD wrapper 一律使用參數化查詢防止 SQL Injection；`delete()` / `update()` 禁止無 `where` 條件的整表操作
- [x] NFR-2：可移植性 — 不依賴 Flask/Django 等特定框架，可被任何 Python 專案直接 import 使用；每個子模組都自帶 `requirements.txt`，方便單獨搬到其他專案
- [x] NFR-3：免費方案友善 — DB 連線池上限設低（預設 1～5），避免耗盡 Neon 免費方案的連線數限制
- [x] NFR-4：一致性 — 所有子模組統一用「class 包住一個 Client」的寫法（`LLMClient`、`CloudSQLClient`、`TelegramClient`），對外方法命名風格一致，降低跨模組的學習成本

## 設計決策

### ADR-1：cloudsql 連線層選用 psycopg2 + ThreadedConnectionPool，不用 ORM

**背景**：需要決定資料層的連線與查詢方式，選項落在「輕量 SQL wrapper」與「ORM（如 SQLAlchemy）」之間。

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| psycopg2 + 連線池 + 手寫 SQL | 輕量、不綁定 schema/model 定義、CRUD wrapper 可直接操作任意 table、符合本專案「資料層偏 Pandas/ETL、直接下 SQL」的慣例 | 沒有型別安全與自動 migration，需自行注意 SQL 正確性 |
| SQLAlchemy（ORM） | 型別安全、migration 工具成熟、關聯查詢方便 | 需要為每個功能模組定義 Model class，與「跨專案重用的通用 CRUD 小工具」目標衝突；對單純的個人專案略重 |
| asyncpg | 效能較高 | 需搭配 async 框架，目前 `main.py` 是 Flask 同步架構，暫不需要 |

**決策**：選擇 psycopg2 + `ThreadedConnectionPool`，並封裝成單一 `CloudSQLClient` class（連線池 + CRUD 都在同一個 `client.py` 內，不再拆成 `connection.py` / `crud.py` 兩檔）
**理由**：CRUD wrapper 只需要操作「任意 table + 任意欄位」，不需要預先定義 Model；輕量、依賴少，最符合「可被跨專案重複使用」的定位。若未來某功能模組需要複雜關聯查詢，可在該模組自行寫 SQL 呼叫 `select()`/自訂查詢，不影響本子模組介面。
**狀態**：accepted

### ADR-2：telegram Client 用 requests 直接呼叫 Bot HTTP API

**背景**：`requirements.txt` 已有 `python-telegram-bot`，但該套件是 async-first 設計，若直接把它包進 submodules，會讓這個「基礎小工具」綁死在特定框架與事件迴圈上。

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| requests 直接呼叫 Bot HTTP API | 同步、無框架依賴、任何 Python 專案都能直接用 | 需要自己封裝 method/payload，功能不如 SDK 完整 |
| 直接暴露 `python-telegram-bot` 的 `Bot` 物件 | 功能完整（webhook、inline keyboard 等） | 綁定 async 事件迴圈，與目前 Flask 同步架構不搭，也不利跨專案重用 |

**決策**：`submodules/telegram` 的 `TelegramClient` class 封裝「發送」相關的 HTTP 呼叫（`call()` 為底層方法，`send_text` / `send_photo` / `send_chat_action` 為常用方法），用 requests 實作，全部收在同一個 `client.py`
**理由**：發送訊息是最基礎、最常被其他工具需要的操作；不綁定 event loop，才符合「跨專案重用」目標。
**後果**：主專案根目錄 `requirements.txt` 保留 `python-telegram-bot`，供 Phase 1 backend 層處理 webhook 接收與訊息路由時使用；两者分工不衝突（submodules 負責送、backend 負責收與 dispatch）。
**狀態**：accepted

### ADR-3：llm Client 採用官方 `google-genai` SDK

**背景**：Google 已將舊版 `google-generativeai` 套件標記為 deprecated，統一改用新版 `google-genai`（2025 年 5 月起 GA，涵蓋 Gemini Developer API 與 Vertex AI）。

**決策**：`submodules/llm` 的 `LLMClient` class 使用 `google-genai`（`from google import genai`），模型固定 `gemini-flash-latest`；資料夾命名為 `llm` 而非 `gemini`，讓對外介面（`generate_text` / `generate_with_image`）保持穩定，未來要換/加供應商時呼叫端不用改
**理由**：官方目前唯一持續維護的 SDK；舊版套件未來可能無法安裝或取得支援
**替代方案**：`google-generativeai`（已 deprecated，不採用）
**狀態**：accepted

### ADR-4：子模組統一採「四檔案結構」，不再用多檔案 + `__init__.py` 的 package 寫法

**背景**：第一版骨架把每個子模組拆成多個檔案（例如 `neon_postgres` 拆成 `connection.py` + `crud.py`，`telegram_client` 拆成 `client.py` + `sender.py`），並用 `__init__.py` 組成 package。Robin 認為這樣不夠乾淨、每個子模組的檔案數量也不統一，要求改成固定樣板，方便日後新增子模組時直接照抄結構。

**決策**：往後每個 `submodules/<name>/` 資料夾一律只包含以下 4 個檔案，不多不少：

| 檔案 | 用途 |
| --- | --- |
| `client.py` | 該模組唯一的程式碼檔，內含一個 `XxxClient` class，封裝這個工具的所有對外方法 |
| `README.md` | 用途、環境變數、安裝方式、使用範例 |
| `requirements.txt` | 這個模組自己需要的第三方套件（只列這個模組真正用到的，不列全專案的依賴） |
| `.env.example` | 這個模組需要的環境變數範例（給獨立測試/搬到其他專案時參考，模組程式碼本身不主動讀取，由呼叫端決定要不要用） |

不再使用 `__init__.py`（Python 3.3+ 的 namespace package 機制下，沒有 `__init__.py` 一樣能 `from submodules.llm.client import LLMClient`，不影響 import）；不再把邏輯拆成多個 `.py` 檔案——若某個模組的程式碼真的長到難以維護，優先考慮這個模組是不是做太多事，而不是拆檔案。

**理由**：統一結構讓任何人（包含未來的 AI agent）看到 `submodules/` 就知道去哪裡找 client、怎麼裝依賴、怎麼設定環境變數，不用每個模組都重新理解一次檔案配置；也方便未來要把某個子模組整包搬去其他專案時，直接複製整個資料夾即可。

**後果**：
1. 主專案根目錄的 `requirements.txt` 仍是本專案**實際部署**安裝清單（`Dockerfile` 用它跑 `pip install -r requirements.txt`），必須與三個子模組的 `requirements.txt` 內容保持同步；子模組自己的 `requirements.txt` 是「這個模組被單獨搬到其他專案時該裝什麼」的說明文件。
2. 各模組的 `.env.example` 只放「這個 Client class 建構子需要的最小參數」（例如 llm 只寫一組 `LLM_API_KEY`），不處理本專案特有的商業決策（例如 Robinson 要用兩把不同的 Gemini Key 分流對話/圖像，這是呼叫端 backend 層的責任，不寫進子模組）。

**狀態**：accepted

## 實作計畫

### Phase 0（對應 robinson SPEC.md 的 Step 0.1a）：建立子模組骨架

- [x] Step S.1：建立 `submodules/cloudsql/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`）
- [x] Step S.2：建立 `submodules/telegram/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`）
- [x] Step S.3：建立 `submodules/llm/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`）
- [x] Step S.4：更新主專案根目錄 `requirements.txt`（新增 `psycopg2-binary`、`google-genai`、`python-dotenv`）
- [x] Step S.5：改版重構 — 刪除舊版 `neon_postgres/`、`telegram_client/`、`gemini_client/`（含各自的 `__init__.py`、`connection.py`、`crud.py`、`sender.py`），統一為 ADR-4 的四檔案結構，並將三個 Client 改為 class 寫法（`CloudSQLClient`、`TelegramClient`、`LLMClient`）
- [ ] Step S.6：撰寫對應單元測試（見下方「測試策略」，暫緩至 Phase 1 backend 實際串接時一併補上）

## 測試策略

目前僅為骨架 wrapper，尚未接上真實業務邏輯，依 AGENTS.md「不適合 TDD 的情境」（第三方 wrapper）先以介面完整性與可讀性為主；待 Phase 1 backend 實際串接 Neon / Telegram / Gemini 時，一併補上以下測試：

### Unit Tests
- [ ] `cloudsql.client.CloudSQLClient`：mock `psycopg2` 連線，驗證 `select`/`insert`/`update`/`delete` 組出的 SQL 與參數正確；`update()`/`delete()` 未帶 `where` 應拋出 `ValueError`；`dsn` 未提供且無 `DATABASE_URL` 應拋出 `ValueError`
- [ ] `telegram.client.TelegramClient`：mock `requests.post`，驗證 `send_text`/`send_photo`/`send_chat_action` 組出的 payload 正確；空 `bot_token` 應拋出 `ValueError`
- [ ] `llm.client.LLMClient`：mock `genai.Client`，驗證 `generate_text`/`generate_with_image` 呼叫參數正確；空 `api_key` 應拋出 `ValueError`

### Integration Tests
- [ ] `cloudsql`：對測試用 Neon 分支資料庫實際下 CRUD，確認連線池可正常取得/歸還連線
- [ ] `telegram`：對 Telegram 測試 Bot 實際發送訊息，確認 API 回應 `ok: true`
- [ ] `llm`：對 Gemini API 實際呼叫 `gemini-flash-latest`，確認能取得非空回應（需留意計入免費額度）

## 風險與緩解

| 風險 | 嚴重度 | 機率 | 緩解方案 |
| --- | --- | --- | --- |
| 連線池設定過大，超過 Neon 免費方案連線數上限 | 中 | 低 | 預設 `max_conn=5`，並在 README 註記依實際方案調整 |
| `google-genai` SDK 介面未來變動（目前仍持續更新） | 低 | 中 | Client 對外只暴露 `generate_text`/`generate_with_image` 兩個方法，SDK 版本升級只需改內部實作 |
| CRUD wrapper 被誤用於拼接未信任的 table/column 名稱，產生 SQL Injection | 高 | 低 | table/column 一律由程式內部信任字串提供，不可直接帶入使用者輸入；README 明確註記此限制 |
| 子模組自己的 `requirements.txt` 與主專案根目錄 `requirements.txt` 版本/內容不同步 | 中 | 中 | ADR-4 已明訂根目錄 `requirements.txt` 為部署權威來源，日後新增/更新子模組依賴時兩邊都要改 |

## 變更記錄

| 日期 | 變更內容 | 變更者 |
| --- | --- | --- |
| 2026-07-29 | 初版建立：3 個子模組骨架（neon_postgres / telegram_client / gemini_client）與對應 ADR | Robin |
| 2026-07-29 | 依 Robin 指定樣板重構：資料夾更名為 `llm` / `cloudsql` / `telegram`，統一為「四檔案結構」（`client.py`/`README.md`/`requirements.txt`/`.env.example`），移除 `__init__.py` 與多檔案拆分，三個 Client 改寫成 class（`LLMClient`/`CloudSQLClient`/`TelegramClient`），新增 ADR-4、FR-6、NFR-4 | Robin |
| 2026-07-30 | `CloudSQLClient` 新增 `execute()` 方法，支援執行任意 SQL（主要供 DDL 使用），為 robinson 專案 ADR-11 的 migration 執行機制（`src/migrations/runner.py`）提供底層能力；`select`/`insert`/`update`/`delete` 的參數化保護不受影響，`execute()` 明確標註為「僅供內部信任 SQL 使用」的逃生口 | Claude（依 robinson SPEC.md ADR-11 需求） |
