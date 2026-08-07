---
title: Submodules — 共用子模組基礎骨架
slug: submodules-core
status: draft
created: 2026-07-29
updated: 2026-08-07
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
├── telegram/
│   ├── .env.example
│   ├── client.py
│   ├── requirements.txt
│   └── README.md
├── gdrive/
│   ├── .env.example
│   ├── client.py
│   ├── requirements.txt
│   └── README.md
├── voice/
│   ├── .env.example
│   ├── client.py
│   ├── requirements.txt
│   └── README.md
├── email/
│   ├── .env.example
│   ├── client.py
│   ├── requirements.txt
│   └── README.md
├── calendar/
│   ├── .env.example
│   ├── client.py
│   ├── requirements.txt
│   └── README.md
├── retry/
│   ├── .env.example
│   ├── client.py
│   ├── requirements.txt
│   └── README.md
└── newsfeed/
    ├── .env.example
    ├── client.py
    ├── requirements.txt
    └── README.md
```

## 需求

### 功能性需求

- [x] FR-1：`submodules/cloudsql` 提供連線池管理與泛用 CRUD 介面（select / insert / update / delete），一律使用參數化查詢；目前實際串接 Neon PostgreSQL，命名為 cloudsql 是為了未來可替換成其他 PostgreSQL 相容服務時介面不變
- [x] FR-2：`submodules/telegram` 提供 Bot 基礎 HTTP Client（`call(method, payload)`）與常用訊息發送方法（文字、圖片、typing 狀態提示）
- [x] FR-3：`submodules/llm` 提供 LLM Client 初始化與文字生成 / 圖文生成呼叫；目前實際串接 Gemini API，模型固定 `gemini-3.5-flash-lite`（**2026-07-31 更新**，見 ADR-6），命名為 llm 是為了未來替換或新增供應商時介面不變
- [x] FR-4：三個子模組彼此獨立、互不 import，也不依賴 `backend/` 或本專案任何商業邏輯（單向依賴：上層可以 import submodules，反向禁止）
- [x] FR-5：所有連線資訊（DB 連線字串、Bot Token、API Key）一律由外部呼叫端注入或讀取環境變數，子模組內部不得寫死任何金鑰
- [x] FR-6：每個子模組資料夾一律只包含 `client.py`、`README.md`、`requirements.txt`、`.env.example` 四個檔案，不得拆成多個 `.py` 檔、不得加 `__init__.py`（見 ADR-4）
- [x] FR-7（2026-07-31 新增，見 ADR-5）：`llm.client.LLMClient` 內建本地端節流保護 —— 呼叫 `generate_text`／`generate_with_image`／`generate_with_search` 任一方法前，先檢查「最近 60 秒內以同一把 `api_key` 呼叫的次數」，超過門檻（預設 8 次／分鐘）直接拋 `LLMQuotaGuardError`、不送出請求；門檻可透過建構子 `max_calls_per_minute` 參數調整
- [x] FR-8（2026-08-01 新增，見 ADR-9）：`submodules/voice` 提供語音轉文字 Client（`VoiceClient.transcribe()`）；目前實際串接 Groq Whisper API，用 `requests` 直接呼叫其 OpenAI 相容 REST 端點，不安裝官方 `groq` SDK
- [x] FR-9（2026-08-02 新增，見 ADR-10）：`submodules/gdrive` 改用 OAuth 2.0（以真人 Google 帳號身分）認證，不再使用 Service Account；`GDriveClient` 建構子改為 `refresh_token`／`client_id`／`client_secret`／`folder_id` 四個必要參數
- [x] FR-10（2026-08-02 新增，見 robinson SPEC.md Step 1.6／FR-21）：`submodules/cloudsql.client.CloudSQLClient` 新增 `execute_query(query, params=None) -> list[dict]`，跟既有的 `execute()`（DDL 用）成對，差別是這個會回傳資料列，供 `select()` 的 table/columns/where 介面無法表達的系統層級查詢使用（例如 `src/bot/monitoring.py` 查 `pg_database_size(current_database())`）
- [x] FR-11（2026-08-05 新增，見 robinson SPEC.md FR-19b、ADR-16；2026-08-07 擴充，見 ADR-11 追記；**同日再修正**）：`submodules/email` 提供 `EmailClient.send_text(to, subject, body)`，透過 Gmail SMTP（SSL）寄送純文字信件；只用 Python 標準函式庫 `smtplib`／`email.mime`，不安裝任何第三方套件。用途是 Telegram 本身故障時的獨立備援通知管道，目前唯一呼叫端是 `src/bot/webhook.py` 的 `_notify_robin_of_error()`。新增 `fetch_emails_from_domain_on_date(sender_domain, target_date)`，用標準函式庫 `imaplib` 透過 Gmail IMAP（SSL）讀取指定寄件者網域、寄送日期（台灣時間）為呼叫端指定之 `target_date` 的信件純文字內容；呼叫端一律明確指定日期，方法本身不做「今天/昨天」的預設換算。供 robinson SPEC.md FR-22／FR-23（Step 3.1）固定台灣時間 23:00 讀取 `dan@tldrnewsletter.com` 當天寄出的 TLDR 電子報使用
- [x] FR-12（2026-08-05 新增，見 robinson SPEC.md FR-66、ADR-17）：`submodules/calendar` 提供 `CalendarClient`，用 Google Calendar API v3（OAuth 2.0，`calendar.events` scope），封裝建立/更新/刪除行事曆事件的最小介面；用途是把待辦事項、重要通知、體態目標期限單向同步寫入 Robin 的家庭共用行事曆，供家人用手機原生行事曆 App 瀏覽
- [x] FR-13（2026-08-07 新增，見 robinson SPEC.md FR-19i、ADR-13）：`submodules/retry` 提供 `call_with_retry(func, is_retryable, max_attempts=3, backoff_seconds=(1, 2, 4))`，對外部 API 呼叫套用「最多重試 3 次＋Exponential Backoff（1s/2s/4s）」的共用重試迴圈；其餘 6 個既有子模組（`llm`／`telegram`／`voice`／`gdrive`／`calendar`／`email`）皆已在各自 `client.py` 內套用，各自傳入符合自己 SDK 例外型別的 `is_retryable` 判斷式，只重試「暫時性錯誤」（連線失敗、逾時、HTTP 429／5xx），永久性錯誤（例如認證失敗、資源不存在）直接往外拋，不浪費重試次數
- [x] FR-14（2026-08-07 新增，見 robinson SPEC.md FR-22／FR-23、ADR-14；**同日修正**）：`submodules/newsfeed` 提供 `NewsFeedClient.fetch_articles_published_on(feed_url, target_date)`，用 `requests` 直接 GET RSS Feed、用標準函式庫 `xml.etree.ElementTree` 解析 XML（不安裝 `feedparser` 等第三方 RSS 套件），回傳發布日期（換算台灣時區）為呼叫端指定之 `target_date` 的文章清單（`{"title": str, "link": str}`）；不再提供「昨天」便利方法，呼叫端一律明確指定日期。用途是 robinson SPEC.md Step 3.1 固定台灣時間 23:00 讀取 IThome／TechCrunch 當天新聞

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

**2026-08-02 補充決策**：`send_text()` 原本預設 `parse_mode="Markdown"`；Robin 實測「我要看所有功能」時 Telegram 回 `400 Bad Request`，排查後確認是 `handle_function()` 的回覆文字由 LLM 自然語言生成，無法保證符合 Telegram 舊版 Markdown 語法（例如星號、底線沒有成對），一旦格式不符，Telegram 會整則拒收，使用者完全收不到回覆——這個風險不只 `/function`，所有 LLM 生成的聊天回覆都可能中獎。改為預設不帶 `parse_mode`（純文字傳送），呼叫端仍可視需要明確傳入；目前所有靜態文案模板本來就沒有依賴 Markdown 格式化（用 emoji 分段），純文字不影響既有呈現效果。

### ADR-3：llm Client 採用官方 `google-genai` SDK

**背景**：Google 已將舊版 `google-generativeai` 套件標記為 deprecated，統一改用新版 `google-genai`（2025 年 5 月起 GA，涵蓋 Gemini Developer API 與 Vertex AI）。

**決策**：`submodules/llm` 的 `LLMClient` class 使用 `google-genai`（`from google import genai`），模型固定 `gemini-3.5-flash-lite`（**2026-07-31 更新**，原為 `gemini-flash-latest`，見 ADR-6）；資料夾命名為 `llm` 而非 `gemini`，讓對外介面（`generate_text` / `generate_with_image`）保持穩定，未來要換/加供應商時呼叫端不用改
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

### ADR-5：`LLMClient` 本地端節流保護，計數以 `api_key` 為單位共用（class 層級狀態，不是掛在單一 instance 上）

**背景**：2026-07-31 Robin 實測時撞到 Gemini 429（額度超限），見 [platform-auth SPEC.md](../platform-auth/SPEC.md) FR-7。除了「出錯後不要讓 Telegram 重試風暴放大問題」，還想在「明知道會被官方拒絕」之前就先攔下來，避免浪費呼叫嘗試。難點在於：`webhook.py` 目前是**每次收到請求都重新 `LLMClient(api_key=...)`**（不是整個 process 生命週期只 new 一次），如果節流計數掛在單一 instance 上，每次請求都會拿到一個全新、計數歸零的 instance，節流形同虛設。

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| A：節流狀態掛在 class 層級，以 `api_key` 字串為 key 的 `dict`（`LLMClient._call_history_by_key`），無論建立幾個 instance，只要 `api_key` 相同就共用同一份計數 | 不需要改 `webhook.py` 的既有建構模式；正確對應「同一把 key＝同一個 Gemini 專案＝同一份官方額度」的真實世界語意 | class 層級的可變狀態需要額外注意測試隔離（多個測試用同一把假 `api_key` 會互相汙染），已用 `tests/submodules/llm/conftest.py` 的 autouse fixture 解決 |
| B：把 `webhook.py` 改成「app 啟動時只建立一次 `LLMClient`」（lazy singleton），節流狀態改回掛在 instance 上 | 語意更直覺（一個 instance 對應一個長期存在的 Client） | 需要連帶重寫 `webhook.py` 既有的、已經測試覆蓋的建構＋監控模式（多個測試會斷言「每次請求都呼叫 `LLMClient(api_key=...)`」），改動範圍與風險都比方案 A 大，且與本次「小範圍防呆」的目標不成比例 |
| C：拉一個外部服務（例如 Redis）做跨 process 共用的節流計數 | 未來若真的多 process/多 worker 部署也能正確運作 | 目前 Render 部署方式是單一 Flask process（`app.run()`，非 gunicorn 多 worker），完全用不到跨 process 共用，屬於過度工程 |

**決策**：採方案 A（2026-07-31）

**理由**：方案 A 用最小改動達成目標，不用動 `webhook.py` 既有的、已經穩定跑了好幾個 Step 的請求處理流程；方案 B 技術上更「乾淨」但改動與風險不成比例，且本專案目前部署方式本來就是單一 process，沒有 B 想解決的多 instance 生命週期問題；方案 C 是為了不存在的多 process 場景做的預先優化，違反本專案一貫的「不過度工程」原則。以 `api_key` 而非 instance 作為節流單位，也更準確反映「額度屬於 Google Cloud 專案，不屬於某個 Python 物件」這個事實（見 platform-auth SPEC.md FR-7b 的討論）。

**後果**：
- `LLMClient` 新增 `LLMQuotaGuardError` 例外類別、`max_calls_per_minute` 建構子參數（預設 8，低於官方免費層 RPM 上限保留緩衝）
- `tests/submodules/llm/conftest.py` 新增 autouse fixture，每個測試前後清空 `LLMClient._call_history_by_key`，避免測試間互相汙染
- 若未來真的改成多 process 部署（例如 gunicorn 多 worker），方案 A 的 class 層級狀態會退化成「每個 process 各自一份節流計數」，屆時需要重新評估是否要升級成方案 C

**狀態**：accepted

### ADR-6：`LLMClient` 預設模型從 `gemini-flash-latest` 別名改為明確指定的 `gemini-3.5-flash-lite`

**背景**：2026-07-31 Robin 持續撞到 Gemini 429，即使 ADR-5 的本地端節流保護（門檻 8 次/分鐘）也擋不住——因為真正的官方免費層額度遠比預期低。Robin 在 AI Studio 的 Rate Limit 頁面實測確認：`gemini-flash-latest` 這個別名當時解析到的是 Gemini 3.6 Flash（Google 最新發布的旗艦模型），免費層只有 **RPM 5、RPD 20**，遠低於 [官方模型文件](https://ai.google.dev/gemini-api/docs/models) 對「Flash 模型」的一般說明（原本假設 10～15 RPM、1500 RPD）。`gemini-flash-latest` 是**別名**（見官方文件「Model version name patterns」），會隨 Google 發布新模型自動熱切換，新模型上線初期免費層配額通常壓得最緊，這是額度異常吃緊的根本原因。

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| A：改用明確指定版本的 Gemini 模型（`gemini-3.5-flash-lite`），Robin 於 AI Studio 實測免費層 RPM 15／RPD 500 | 同屬 Gemini 家族，SDK 介面、工具支援（Google Search grounding、圖片理解）完全相容，零相容性風險；額度較目前提升 25 倍（RPD）、3 倍（RPM）；仍是官方 Stable 版本 | 額度仍遠低於 Gemma 系列，長期使用量成長後可能還是不夠 |
| B：改用 Google 開源模型 Gemma 4（`gemma-4-26b-a4b-it`），Robin 於 AI Studio 實測免費層 RPM 30／RPD 14,400 | 額度非常寬裕（是方案 A 的近 30 倍） | 不同模型家族，是否支援我們現在掛的 Google Search grounding 工具尚未驗證，貿然全面切換有請求直接失敗的風險，需要先花額外工序驗證相容性 |
| C：開通計費帳戶升級付費 Tier 1 | 額度大幅提升，且仍留在 Gemini 家族、相容性風險為零 | 需要 Robin 自行在 AI Studio 綁定信用卡，屬於 Robin 個人帳務決定，AI 不代為執行；即使有 $250 額度緩衝，仍多一層帳務管理成本 |

**決策**：先採方案 A（2026-07-31），Gemma 4（方案 B）與計費升級（方案 C）留待方案 A 的額度仍不夠用時再評估

**理由**：方案 A 是「換了保證能動」的最小風險選擇——同屬 Gemini 家族，不需要額外驗證工具相容性，就能讓 RPD 從 20 提升到 500（25 倍），大機率已經足夠解決目前個人/家庭規模的測試與日常使用量；方案 B 額度雖然誘人，但引入了未驗證的相容性風險，不符合「先用最小改動解決當下問題」的原則；方案 C 涉及 Robin 個人帳務決定，不是技術層面能單方面決定的選項

**後果**：
- `submodules/llm/client.py` 的 `_DEFAULT_MODEL` 常數改為 `"gemini-3.5-flash-lite"`
- 本地端節流保護（ADR-5）的 `_DEFAULT_MAX_CALLS_PER_MINUTE`（8）仍低於官方新上限（15），維持保守緩衝，不需調整；但注意本地端節流目前只防 RPM，沒有防 RPD（500/天）上限，若未來單日用量逼近 500 次，仍需要額外補上每日次數的本地端保護
- 若未來確認 Gemma 系列支援我們需要的工具（Google Search grounding、圖片辨識），可以考慮小規模測試後再評估是否切換

**狀態**：accepted

### ADR-7：`generate_with_search()` 固定改用 `gemini-2.5-flash`，不沿用 `_DEFAULT_MODEL`

**背景**：ADR-6 換成 `gemini-3.5-flash-lite` 後，Robin 仍持續撞到 429，且僅限於 `chat.py` 呼叫的 `generate_with_search()`（帶 Google Search 工具）——單純文字/圖片呼叫完全正常。逐步排除以下可能性後才找到真正原因：
1. 懷疑是舊專案本身被限制 → Robin 重新產生一把全新 Key（全新 Google Cloud 專案）測試，純文字呼叫（curl 直測，不掛工具）成功，證明新專案本身沒問題
2. 用同一把新 Key、同一個模型，改成帶 `google_search` 工具再測一次 → 依然 429，證明問題出在「掛了搜尋工具」這件事本身，跟專案、跟額度用完與否都無關
3. Robin 於 AI Studio Rate Limit 頁面「Tools」區塊發現：Google Search grounding 的免費額度是**依 Gemini 模型世代分桶**，不是每個模型共用同一包額度——Gemini 2 世代與 Gemini 2.5 世代皆有 1,500 次/天免費額度，但 **Gemini 3 世代（含 `gemini-3.5-flash-lite`）免費額度是 0**
4. 對照官方定價頁確認：Gemini 3 模型使用 Grounding with Google Search 一律照搜尋次數計費，免費層完全不提供；Gemini 2.5 或更早的模型才有免費配額

**決策**：`generate_with_search()` 內部固定改用 `gemini-2.5-flash`（Gemini 2.5 世代，享有 1,500 次/天免費 grounding 額度），忽略建構子傳入的 `model` 參數；`generate_text()`／`generate_with_image()` 等不需要查網路的方法維持用 `_DEFAULT_MODEL`（`gemini-3.5-flash-lite`，ADR-6）。**2026-07-31 修正**：原本選定 `gemini-2.5-flash-lite`，但 Robin 實測該模型在 AI Studio 不可選用，改用同世代的 `gemini-2.5-flash`（`gemini-2.5-pro` 較重、非必要不選）

**理由**：這是唯一不需要移除既有搜尋功能、也不需要開通計費就能解決問題的方案——同一把 Key、同一個專案即可，純粹是呼叫時指定的模型世代問題；`generate_text`／`generate_with_image` 不涉及 grounding，繼續用額度更好（RPD 500 vs 1,500，但 RPM/穩定性更好、非停用倒數中）的 `gemini-3.5-flash-lite` 沒有理由改動

**替代方案**：
- 方案 A：從 `chat.py` 移除 Google Search grounding 功能（改回 ADR-1 之前純知識庫回答）——會犧牲「查無答案時上網查」這個既有能力，且盤點後發現待辦/記帳/體態/心情小記等主力功能都不依賴 grounding，只有一般聊天在使用者問即時性資訊時受影響，影響範圍雖可控但仍是功能倒退，已否決
- 方案 B：開通計費帳戶，讓 Gemini 3 世代也能用 grounding——技術上可行，但涉及 Robin 個人帳務決定，且本次找到的方案（改用 Gemini 2.5 世代）完全免費、改動範圍更小，已否決

**後果**：
- `submodules/llm/client.py` 新增 `_SEARCH_MODEL = "gemini-2.5-flash"` 常數，`generate_with_search()` 呼叫 `generate_content` 時改傳 `model=_SEARCH_MODEL`，不再用 `self._model`
- Gemini 2.5 系列預計 2026-10-16 停用，屆時 `_SEARCH_MODEL` 需要重新評估（可能屆時 Gemini 3 世代已開放免費 grounding，或需要換其他仍在維護的世代）
- 這次排錯過程也確認了一件重要的事：AI Studio 消費者版 Rate Limit 頁面的資訊比純猜測／網路文章可靠得多，未來遇到類似額度問題應優先去該頁面核對實際數字，而不是憑經驗猜測

**狀態**：superseded by ADR-8（2026-07-31，`gemini-2.5-flash` 對新產生的 `GEMINI_API_BOT_KEY` 直接 404「no longer available to new users」，Gemini 2.5 世代整個對新專案關閉存取，非額度或選型問題，這把 Key 上此方案已無法成立）

### ADR-8：Gemini 2.5 世代對新專案關閉存取，`generate_with_search()` 直接移除（supersede ADR-7）

**背景**：2026-07-31 Robin 換用新的 `GEMINI_API_BOT_KEY`（前次排查 429 時重新產生的全新 Google Cloud 專案）後，`generate_with_search()`（ADR-7 固定用的 `gemini-2.5-flash`）開始回傳 `INFO:httpx: ... 404 Not Found`。逐步排查：
1. 先懷疑是「新專案沒開放 2.5 世代」→ 用 `curl .../v1beta/models?key=...` 列出這把 Key 實際可用的模型清單，結果 `models/gemini-2.5-flash`／`models/gemini-2.5-flash-lite`／`models/gemini-2.5-pro` 都在清單裡，代表 ListModels 層級是「看得到」的
2. 懷疑是 Render 部署的 Key 跟本機測試的 Key 不一致 → 逐把比對 `GEMINI_API_BOT_KEY`／`GEMINI_API_IMAGE_KEY1`／`GEMINI_API_IMAGE_KEY2`／`GEMINI_API_TEXT_KEY` 後幾碼，四把都對得上，排除此可能
3. 懷疑是「掛了 Google Search 工具」這個組合本身被擋 → 直接用 curl 打 `generateContent`，分別測「不掛工具的純文字請求」與「掛 `google_search` 工具的請求」，**兩者結果一模一樣**，都回傳明確錯誤訊息：`"This model models/gemini-2.5-flash is no longer available to new users. Please update your code to use a newer model for the latest features and improvements."`
4. 結論：**模型「看得到」（ListModels）不代表「呼叫得到」（generateContent）**——Google 已經對新建立的專案關閉 Gemini 2.5 世代模型的實際呼叫權限（Gemini 2.5 系列預計 2026-10-16 停用，Google 顯然已提前不讓新專案存取這個世代），跟掛不掛搜尋工具無關，換 `gemini-2.5-pro` 大機率也是同樣結果（同世代）

**決策**：不再嘗試在這把新 Key 上挽救 Gemini 2.5 世代的存取權，直接移除 `generate_with_search()`／grounding 功能（Robin 明確指示「再試下去只是在浪費時間」）。查無答案時由呼叫端改為誠實回答不知道，詳見 [chat-core SPEC.md](../chat-core/SPEC.md) ADR-5。

**替代方案**：
- 方案 A：換回舊專案的 Key 專門處理 `generate_with_search()`——舊 Key 是否仍保有 Gemini 2.5 存取權未經驗證，且 Robin 選擇不再花時間排查，已否決
- 方案 B：開通計費，讓 Gemini 3 世代也能用 grounding——涉及個人帳務決定，Robin 明確表示不考慮，已否決

**理由**：這是本次排錯過程中第一個「不依賴猜測、有 Google API 明確錯誤訊息佐證」的結論，沒有其他模型選型或設定調整能繞過「整個世代被關閉」這件事；繼續在同一個問題上嘗試不同 2.5 系列模型只是重複驗證同一個已知結論，不符合 AGENTS.md 效率紀律「不做無意義 retry」。

**後果**：
- `submodules/llm/client.py` 刪除 `generate_with_search()`、`_SEARCH_MODEL`、`_used_search()`
- 排錯過程也再次確認：Google API 的 `ListModels`（`GET /v1beta/models`）只反映「這個模型存在於目錄中」，不代表這把 Key／專案有權限實際呼叫 `generateContent`；未來遇到類似「清單看得到但呼叫失敗」的狀況，應直接用 curl 打實際的 `generateContent` 驗證，不能只看 ListModels 結果

**狀態**：accepted

### ADR-9：`voice` Client 用 `requests` 直接呼叫 Groq Whisper 的 OpenAI 相容 REST API，不安裝官方 `groq` SDK

**背景**：Step 1.4（語音轉文字，見 robinson SPEC.md FR-14／FR-15、ADR-12）需要一個 Groq Whisper 語音轉文字的 Client。Groq 官方提供 Python SDK（`groq` 套件），但 Whisper 轉錄端點（`POST /openai/v1/audio/transcriptions`）本質上是單純的 multipart 檔案上傳，跟 `submodules/telegram`（ADR-2）／`submodules/gdrive` 面對的情況類似：不需要一整包 SDK 就能完成需求。

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| A：`requests` 直接呼叫 REST 端點 | 零額外重量依賴（`requests` 本來就是專案既有依賴）、介面單純、與 `telegram`／`gdrive` 子模組的既有慣例一致 | 需要自己組 multipart payload，若 Groq API 之後新增更多進階功能（例如串流）需要自己補 |
| B：安裝官方 `groq` SDK | 官方維護、功能覆蓋更完整（例如未來的 TTS、Chat Completions） | 目前只需要「語音轉文字」這一個能力，安裝整包 SDK 是過度工程；且會讓 `submodules/voice/requirements.txt` 多一個依賴，增加子模組「可攜帶到其他專案」的安裝成本 |

**決策**：採方案 A（2026-08-01）

**理由**：與 ADR-2（telegram）一貫的判斷基準一致——本專案面對的是「單一 REST 端點」而不是「一整套需要 SDK 抽象的能力」，`requests` 已經是專案既有依賴，不需要為了一個端點多裝一包 SDK；未來若 Groq 語音相關能力擴增到需要更完整的 SDK 支援，可以再評估升級。

**替代方案**：官方 `groq` SDK（方案 B）——已否決，理由見上表。

**後果**：
- `submodules/voice/client.py`：`VoiceClient.transcribe(audio_bytes, filename, mime_type) -> str`，`response_format="text"` 讓 Groq 直接回傳純文字 body，不用另外解析 JSON
- `submodules/voice/requirements.txt` 只需要 `requests`
- 若之後語音功能擴增（例如需要逐字時間戳記 `timestamp_granularities`），只需要在 `transcribe()` 內部擴充參數，對外介面不必變動

**狀態**：accepted

### ADR-10：`gdrive` Client 改用 OAuth 2.0（真人帳號身分），supersede 原本的 Service Account 認證

**背景**：2026-08-02 Robin 實測語音上傳功能，撞到 Google Drive API 回傳 `403 storageQuotaExceeded`。查證後確認這是 Google 的既定限制而非程式邏輯錯誤：Service Account 本身完全沒有 Drive 儲存額度，用它上傳檔案到任何一般（非 Shared Drive）資料夾一律會失敗，跟目的資料夾擁有者是誰、資料夾還有沒有空間完全無關；唯二解法是改用 Shared Drive（需要付費 Google Workspace，經查證 Robin 的個人 Gmail 帳號不具備）或改用 OAuth 2.0 讓程式以真人帳號身分上傳。

**選項**：
| 方案 | 優點 | 缺點 |
|------|------|------|
| A：改用 OAuth 2.0，以 Robin 本人帳號身分上傳 | 免費（沿用 Robin 既有的個人 Google 帳號儲存額度）、不需要額外付費服務 | 需要一次性互動授權流程取得 refresh token（無法純後端自動化，需要 Robin 手動跑一次本機腳本並在瀏覽器完成同意畫面）、多一組要保管的憑證（refresh token） |
| B：升級 Google Workspace 開通 Shared Drive | 免費額度沿用官方 Service Account 對 Shared Drive 的原生支援，不需要互動授權流程 | 需要付費訂閱 Google Workspace，對個人/家庭規模的專案是不必要的成本 |
| C：延後處理，暫時停用語音/圖片雲端備份功能 | 零開發成本 | 直接犧牲既有功能，非真正解法 |

**決策**：採方案 A（2026-08-02，Robin 於 AskUserQuestion 選定「改用 OAuth 以你本人身份上傳（推薦）」）

**理由**：免費、不需要額外訂閱，一次性互動授權的額外操作成本可接受（只需要 Robin 執行一次 `get_refresh_token.py` 取得長期 refresh token，之後 production 端全自動、不需要再互動）。

**替代方案**：方案 B（升級 Workspace）、方案 C（延後處理）——均已否決，理由見上表。

**後果**：
- `submodules/gdrive/client.py`：`GDriveClient.__init__(refresh_token, client_id, client_secret, folder_id)` 四個必要參數（原本是 `key_file_path, folder_id` 兩個），內部用 `google.oauth2.credentials.Credentials` 建構憑證，`google-auth` 函式庫會在存取權杖過期時自動用 refresh_token 換發新的，不需要額外程式碼處理刷新邏輯
- 新增 `submodules/gdrive/get_refresh_token.py`：一次性本機互動授權腳本（使用 `google_auth_oauthlib.flow.InstalledAppFlow`），只在本機執行一次取得 refresh token，不進入 production 依賴、不被 `webhook.py` 匯入
- `submodules/gdrive/requirements.txt` 新增 `google-auth-oauthlib`（僅 `get_refresh_token.py` 本機執行需要；production 執行路徑用到的 `google-auth`／`google-api-python-client` 不變）
- 環境變數由 `GDRIVE_KEY_FILE_PATH` 改為 `GDRIVE_OAUTH_CLIENT_ID`／`GDRIVE_OAUTH_CLIENT_SECRET`／`GDRIVE_OAUTH_REFRESH_TOKEN`（`GDRIVE_FOLDER_ID` 不變）；原本 Render 上的 Service Account JSON 金鑰 Secret File 不再被使用，可移除
- OAuth 同意畫面發布狀態需設為「正式版（In production）」，否則「測試中」狀態核發的 refresh token 只有 7 天效期就會失效——這是 Google OAuth 的既定行為，不是本專案程式碼可以繞過的限制

**狀態**：accepted

### ADR-11：新增 `submodules/email`，用 `smtplib` 直打 Gmail SMTP 當 Telegram 故障時的備援通知管道

**背景**：Robin 在 robinson SPEC.md Step 2.4（FR-19b，錯誤 log 雲端連結）驗收時提出一個關鍵問題：Robinson 是單一 Telegram Bot 架構，如果壞掉的剛好是 Telegram API 本身（或 `TELEGRAM_BOT_TOKEN` 失效），`_notify_robin_of_error()` 連私訊 Robin 這件事本身都送不出去，之前完全沒設計任何備援管道，Robin 會完全收不到任何主動通知，只能自己去 Render Dashboard 翻 log。經確認需要新增一條完全獨立於 Telegram 的備援管道。

**決策**：
1. 新增 `submodules/email`，提供 `EmailClient.send_text(to, subject, body)`，透過 Gmail SMTP（`smtp.gmail.com:465`，SSL）寄送純文字信件。
2. 刻意只用 Python 標準函式庫 `smtplib`／`email.mime.text.MIMEText`，不安裝任何第三方套件（比照 `telegram`／`voice` 子模組「輕量優先」的慣例，見 ADR-2、ADR-9）。
3. 複用既有的 `GMAIL_USER`／`GMAIL_PASSWORD` 環境變數（`.env.example` 早在 2026-07-30 就已預留給 Phase 3 FR-23「讀取 Gmail TLDR 電子報」使用，但當時尚未有任何程式碼真的讀取這兩個變數）；`GMAIL_PASSWORD` 必須是 Google 帳號的應用程式密碼（App Password），這是 Google 官方對已開啟兩步驟驗證帳號的既定要求。
4. 呼叫端（`src/bot/webhook.py`）只在 Telegram 私訊 Robin 失敗時才觸發這個備援，平常完全不會用到，避免這條備援路徑本身增加不必要的額外呼叫或成本。

**理由**：
- `smtplib` 是 Python 標準函式庫，寄一封純文字信這種單純需求不需要引入任何第三方 email SDK 或第三方寄信服務（SendGrid、Mailgun 等），符合 NFR-1「一律使用免費方案」與本專案「輕量優先」的一貫慣例。
- 複用既有的 `GMAIL_USER`／`GMAIL_PASSWORD` 而不是新增另一組寄信專用憑證，減少要保管的金鑰數量；反正這兩個變數本來就是 Robin 自己的 Gmail 帳號，寄信跟讀信（未來 FR-23）用同一組登入資訊完全合理。
- Email 跟 Telegram 是兩個完全獨立的基礎設施（不同公司、不同協定），同時掛掉的機率遠低於單一管道，適合當作「最後一道防線」而非主要通知手段。

**替代方案**：
- 方案 A：改用第三方 Email API 服務（SendGrid／Mailgun 等）——優點是不需要處理 SMTP 連線細節、送達率通常更好；缺點是需要額外申請帳號與 API Key、免費額度通常有每日/每月上限，對於「極少觸發」的備援用途而言，多引入一個外部服務依賴不划算，已否決
- 方案 B：改用其他即時通訊服務當第二管道（例如 Discord Webhook、Slack）——優點是一樣即時；缺點是又要多申請一個帳號/服務，且本質上跟 Telegram 是同一類「即時通訊 API」風險，如果是「這類服務的網路連線本身出問題」（而非 Telegram 這家公司自己的問題）則兩者可能一起失效，風險相關性比 Email 更高，已否決
- 方案 C（採用）：`smtplib` 直打 Gmail SMTP，複用既有 `GMAIL_USER`／`GMAIL_PASSWORD`

**後果**：
- 新增 `submodules/email/`（`client.py`／`README.md`／`requirements.txt`／`.env.example`），`requirements.txt` 內容為空（僅一行註解說明不需要額外依賴）。
- `src/bot/webhook.py` 新增 `_send_email_fallback()`，`_notify_robin_of_error()` 的 Telegram 送達失敗分支改為呼叫這個函式，而不是單純記 log 就結束。
- `GMAIL_USER`／`GMAIL_PASSWORD` 從「Phase 3 預留但未使用」變成「Step 2.4 起就會用到」，NFR-5（robinson SPEC.md）同步註記這個狀態變化。
- 這是備援機制，沒有對應的「備援也失敗了怎麼辦」的再下一層——Email 寄送失敗只會記 log，這是刻意的設計邊界，不無限疊加備援層級。

**狀態**：accepted

**2026-08-07 追記（robinson SPEC.md Step 3.1，FR-22／FR-23）**：ADR-11 原始決策第 3 點就已預告「寄信跟讀信（未來 FR-23）用同一組登入資訊完全合理」，這次正式實作：`EmailClient` 新增讀信方法，同樣只用標準函式庫 `imaplib`，透過 Gmail IMAP（`imap.gmail.com:993`，SSL）讀取收件匣。設計要點：①用「寄件者網域比對」而非主旨關鍵字辨識 TLDR 電子報（經 AskUserQuestion 與 Robin 確認，電子報版本多、主旨格式不保證固定，網域 `tldrnewsletter.com` 較穩定；Robin 稍後補充實際寄件信箱為 `dan@tldrnewsletter.com`）②IMAP `SEARCH SINCE/BEFORE` 只用來粗略縮小範圍（以日曆日為單位、不保證時區精確），實際「是否符合目標日期」改用信件 `Date` header 換算台灣時區後精確比對，避免抓到時區誤差多出來的信件③沿用 ADR-13 的重試機制，`imaplib.IMAP4.error`（帳密/指令錯誤）視為永久性錯誤不重試，`OSError`／`imaplib.IMAP4.abort` 視為暫時性錯誤才重試。

**同日再修正**：Robin 驗收時進一步明確排程需求（固定台灣時間 23:00 收集「當天」信件，非原本設想的「呼叫當下的昨天」），方法簽章由最初的 `fetch_yesterday_emails_from_domain(sender_domain, now=None)` 改為 `fetch_emails_from_domain_on_date(sender_domain, target_date)`，移除子模組內部「now → 昨天」的換算邏輯，改由呼叫端（`src/bot/skill_growth.py`）明確傳入目標日期；IMAP SINCE/BEFORE 範圍計算與 `Date` header 精確比對邏輯不變，只是比對基準從「昨天」改為呼叫端指定的 `target_date`。

### ADR-12：新增 `submodules/calendar`，用獨立一組 OAuth 憑證（不與 `gdrive` 共用），scope 限定 `calendar.events`

**背景**：robinson SPEC.md 新增 FR-66（Google Calendar 整合，見 ADR-17），需要一個能建立/更新/刪除 Google Calendar 事件的子模組。

**決策**：
1. 新增 `submodules/calendar`，提供 `CalendarClient`，方法涵蓋 `create_event()`／`update_event()`／`delete_event()`，用官方 `google-api-python-client`（跟 `gdrive` 同一套 SDK 家族，介面風格一致）。
2. 認證方式沿用 `gdrive` 的 OAuth 2.0（真人帳號身分，見 ADR-10），但**使用獨立一組憑證**（`GOOGLE_CALENDAR_OAUTH_CLIENT_ID`／`GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET`／`GOOGLE_CALENDAR_OAUTH_REFRESH_TOKEN`），不與 `gdrive` 的憑證共用，即使兩者實務上可能來自同一個 Google Cloud 專案。
3. OAuth scope 只申請 `https://www.googleapis.com/auth/calendar.events`（僅限事件讀寫），不申請完整的 `https://www.googleapis.com/auth/calendar`（會額外拿到修改行事曆本身設定、刪除整個行事曆等更高權限），符合最小權限原則。

**理由**：
- 獨立憑證是刻意的設計：`gdrive` 跟 `calendar` 雖然都是 Google 服務，但功能語意完全不同（檔案儲存 vs 行事曆事件），任一組憑證外洩時，影響範圍應該互相隔離，不應該因為共用同一組 token 而讓攻擊者一次拿到兩種能力；這也符合 FR-4「子模組彼此獨立、互不依賴」的既有原則,延伸到「連金鑰都不共用」。
- `calendar.events` 而非 `calendar`：Robinson 只需要建立/更新/刪除事件，不需要修改行事曆本身的設定或刪除整個行事曆，用最小必要的 scope 降低憑證外洩時的潛在破壞範圍。

**替代方案**：
- 方案 A：直接複用 `gdrive` 現有的 OAuth 憑證，只是多要一個 scope——省去重新跑一次互動授權腳本的操作成本，但兩個子模組的憑證耦合在一起，任一模組出事會互相拖累，已否決
- 方案 B（採用）：獨立一組憑證，scope 最小化

**後果**：
- 新增 `submodules/calendar/`（`client.py`／`README.md`／`requirements.txt`／`.env.example`），比照 `gdrive` 新增一支一次性互動授權腳本（`get_refresh_token.py`）取得 `GOOGLE_CALENDAR_OAUTH_REFRESH_TOKEN`。
- `requirements.txt` 新增 `google-api-python-client`／`google-auth`（跟 `gdrive` 相同套件，各自子模組各自宣告一份，符合 ADR-4 的四檔案獨立慣例）。
- Robin 需要在 Google Cloud Console 額外開通 Calendar API（跟 Drive API 是不同的 API，需要分別啟用）。

**狀態**：accepted

### ADR-13：新增 `submodules/retry` 共用重試工具，作為 ADR-4「子模組彼此獨立、互不 import」的刻意例外

**背景**：robinson SPEC.md FR-19i 要求所有外部 API 呼叫（Gemini/OpenAI API、Telegram Bot API、104 AJAX API 等）內建「最多重試 3 次＋Exponential Backoff（1s/2s/4s）」的機制。目前有 6 個既有子模組（`llm`／`telegram`／`voice`／`gdrive`／`calendar`／`email`）都各自呼叫外部 API，理論上都需要這段重試邏輯；但 ADR-4 明訂「子模組彼此獨立、互不 import」，且每個子模組限定「四檔案結構、`client.py` 內只含一個 `XxxClient` class」。經 AskUserQuestion 與 Robin 確認三個設計問題：① 程式碼放置方式 ② 判斷「值得重試」的標準 ③ 套用範圍。

**選項**（程式碼放置方式）：
| 方案 | 優點 | 缺點 |
|------|------|------|
| A：每個 `client.py` 各自複製一份重試 helper | 嚴格遵守 ADR-4／NFR-2（子模組完全獨立、可攜） | 6 份幾乎相同的重試迴圈程式碼要各自維護，任何一處要調整（例如改重試次數）都要改 6 個檔案 |
| B（採用）：新增 `submodules/retry`，提供共用的 `call_with_retry()` | 重試迴圈與 Exponential Backoff 時間控制只維護一份；各子模組只需要各自定義 `is_retryable` 判斷式（因 SDK 例外型別而異，這部分本來就無法共用） | 打破 ADR-4「子模組彼此獨立、互不 import」的原始精神，6 個子模組都會 import `submodules/retry`，任一子模組要單獨搬到其他專案時，必須連帶搬走 `submodules/retry` 資料夾 |

**決策**：採方案 B（2026-08-07，Robin 於 AskUserQuestion 選定「抽成共用 retry 工具」）。`submodules/retry/client.py` 提供單一函式 `call_with_retry(func, is_retryable, max_attempts=3, backoff_seconds=(1, 2, 4))`——只負責「重試迴圈本身＋backoff 時間控制」，完全不內建任何 SDK 專屬的例外判斷邏輯；`is_retryable` 一律由呼叫端傳入，各子模組依自己串接的 SDK/REST API 定義各自的 `_is_retryable_xxx_error()` private 函式（例如 `llm` 檢查 `google.genai.errors.ServerError`／`ClientError(code=429)`，`telegram`／`voice` 檢查 `requests.exceptions` 系列例外與 HTTP 狀態碼，`gdrive`／`calendar` 檢查 `googleapiclient.errors.HttpError.resp.status`，`email` 排除 `smtplib.SMTPAuthenticationError`）。

**這是 `submodules/` 底下唯一不是「包裝外部服務」的子模組，是 ADR-4 的刻意例外**：仍維持四檔案結構（`client.py`／`README.md`／`requirements.txt`／`.env.example`，後兩者內容為空，僅為保持慣例一致）方便辨識，但語意上是「其他子模組共用的基礎設施」，不是「包裝某個外部 API 的 Client」；依賴方向是單向的（`llm`/`telegram`/`voice`/`gdrive`/`calendar`/`email` → `retry`），`retry` 本身不依賴任何其他子模組或本專案商業邏輯，因此仍符合 FR-4「不依賴 backend/或本專案任何商業邏輯」的精神，只是不再是「彼此互不 import」的字面意義。

**重試判斷標準（is_retryable）**：經 AskUserQuestion 確認採「只重試暫時性錯誤」（而非對所有例外一律重試）——連線失敗、逾時、HTTP 429（Rate Limit）、5xx（伺服器端問題）才重試；4xx 當中的其餘狀態碼（400 參數錯誤、401/403 認證失敗、404 資源不存在——見 ADR-8 實際排查過 Gemini 2.5 世代對新專案關閉存取回傳 404 的案例）都是「重試也沒用」的永久性錯誤，直接往外拋、不浪費重試次數與時間。`LLMClient` 既有的本地端節流保護（`LLMQuotaGuardError`，見 ADR-5）刻意設計在 `call_with_retry` 包裹範圍**之外**（`_guard_rate_limit()` 在進入重試迴圈前就先檢查），因為節流門檻是「時間窗口」邏輯，立即重試無法解決，重試也沒有意義。

**套用範圍**：經 AskUserQuestion 確認，這次只套用到 6 個現有子模組；robinson SPEC.md FR-34a 提到的 104 求職爬蟲 API 屬於 Phase 4 才會存在的程式碼，屆時開工時比照辦理。

**替代方案**：方案 A（每個 client.py 各自複製）——已否決，理由見上表。

**後果**：
- 新增 `submodules/retry/`（`client.py`／`README.md`／`requirements.txt`／`.env.example`），只用 Python 標準函式庫 `time`，`requirements.txt`／`.env.example` 皆為空
- `llm`／`telegram`／`voice`／`gdrive`／`calendar`／`email` 六個 `client.py` 都新增 `from submodules.retry.client import call_with_retry` 與各自的 `_is_retryable_xxx_error()` private 函式，把原本直接呼叫外部 API 的那一行改為透過 `call_with_retry()` 包裹
- `call_with_retry()` 重試次數用盡或遇到不可重試的例外時，一律把最後一次的原始例外原封不動往外拋出，不包裝成新的例外型別，呼叫端（例如 `src/bot/webhook.py` 既有的 `except` 邏輯）完全不需要改動
- 未來若某個子模組真的需要單獨搬到其他專案，需要連帶搬走 `submodules/retry/` 資料夾（很小，只有一個純函式），這是刻意接受的可攜性妥協
- 例外分級降級（FR-19f／FR-19g，Step 2.6）將建立在這次重試機制之上：3 次重試全部失敗後才正式判定該次 Request 失敗，才進入「一般感冒級」或「重大疾病級」的分級處理

**狀態**：accepted

### ADR-14：新增 `submodules/newsfeed`，用 `requests` + 標準函式庫 `xml.etree.ElementTree` 抓取 RSS Feed，不安裝 `feedparser`

**背景**：robinson SPEC.md FR-22／FR-23（Step 3.1，每日重點技術分享）需要抓取 IThome／TechCrunch 新聞。經 AskUserQuestion 與 Robin 確認，兩者都有公開 RSS Feed（IThome：`ithome.com.tw/rss`；TechCrunch：`techcrunch.com/feed`），採用 RSS 而非另外寫網頁爬蟲。Robin 驗收時進一步明確排程需求：固定台灣時間 23:00 收集「當天」新聞，因此最終只保留呼叫端明確指定日期的單一方法，不提供「昨天」便利方法。

**決策**：
1. 新增 `submodules/newsfeed`，提供 `NewsFeedClient.fetch_articles_published_on(feed_url, target_date)`，回傳 `{"title": str, "link": str}` 清單。
2. 用 `requests.get()` 直接下載 RSS Feed（本質是 XML），用 Python 標準函式庫 `xml.etree.ElementTree` 解析，不安裝 `feedparser` 等第三方 RSS 套件。
3. RSS `<item><pubDate>` 是 RFC 822 格式，跟 Email `Date` header 同格式，複用標準函式庫 `email.utils.parsedate_to_datetime` 解析＋換算台灣時區判斷「是否為昨天」，跟 `submodules/email` 的 `_sent_on_date()` 手法一致。
4. `<item>` 缺少 `<title>`／`<link>`／`<pubDate>` 任一欄位一律跳過，寧可漏抓也不要因為單筆格式異常而整批解析失敗。
5. 套用 ADR-13 的重試機制，`is_retryable` 判斷比照 `telegram`／`voice`：連線失敗／逾時／HTTP 429／5xx 才重試，其餘 4xx 或 XML 解析失敗（`xml.etree.ElementTree.ParseError`，非網路問題，重試也沒用）直接往外拋。

**理由**：
- RSS 本質就是標準 XML 格式，`xml.etree.ElementTree` 是 Python 標準函式庫內建工具，足以應付「取出 `title`/`link`/`pubDate`」這種單純需求，不需要引入 `feedparser` 這種功能更完整（也更重）的第三方套件，符合本專案「輕量優先、能用標準函式庫就不多裝依賴」的一貫慣例（見 ADR-2、ADR-9、ADR-11）。
- 用 RSS Feed 而非爬蟲：兩家媒體都有官方公開 RSS，穩定性與合規性都優於直接解析網頁 HTML（版面隨時可能改版），也不需要處理反爬蟲機制。
- 複用 `email.utils.parsedate_to_datetime` 解析 `pubDate`：RSS 2.0 規格明訂 `pubDate` 為 RFC 822 格式，跟 Email `Date` header 是同一套格式，直接複用標準函式庫既有工具，不需要自己寫日期解析邏輯或引入額外套件。

**替代方案**：
- 方案 A：安裝 `feedparser` 套件——優點是對各種不規範 RSS/Atom Feed 的相容性更好；缺點是多一個第三方依賴，而目標的兩個 Feed（IThome／TechCrunch）格式標準，`xml.etree.ElementTree` 足以應付，已否決
- 方案 B：直接爬取網頁 HTML（不用 RSS）——優點是不受限於 RSS Feed 是否提供完整內容；缺點是網頁版面隨時可能改版導致解析邏輯失效、且更容易觸發反爬蟲機制，已否決
- 方案 C（採用）：`requests` + `xml.etree.ElementTree` 解析官方 RSS Feed

**後果**：
- 新增 `submodules/newsfeed/`（`client.py`／`README.md`／`requirements.txt`／`.env.example`），`requirements.txt` 內容為 `requests`（比照 `telegram`／`voice`）；`.env.example` 為空（Feed URL 由呼叫端傳入，不需要環境變數）。
- `NewsFeedClient` 只回傳「標題＋連結」，不解析全文內容——Step 3.1 的中文摘要交給 Gemini 依標題／連結產出，不需要在這個子模組層級就把全文擷取出來，保持子模組單純。
- 若 IThome／TechCrunch 未來改版 RSS 結構或 Feed 網址失效，需要重新確認網址並調整（風險見下方風險表）。

**狀態**：accepted

## 實作計畫

### Phase 0（對應 robinson SPEC.md 的 Step 0.1a）：建立子模組骨架

- [x] Step S.1：建立 `submodules/cloudsql/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`）
- [x] Step S.2：建立 `submodules/telegram/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`）
- [x] Step S.3：建立 `submodules/llm/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`）
- [x] Step S.4：更新主專案根目錄 `requirements.txt`（新增 `psycopg2-binary`、`google-genai`、`python-dotenv`）
- [x] Step S.5：改版重構 — 刪除舊版 `neon_postgres/`、`telegram_client/`、`gemini_client/`（含各自的 `__init__.py`、`connection.py`、`crud.py`、`sender.py`），統一為 ADR-4 的四檔案結構，並將三個 Client 改為 class 寫法（`CloudSQLClient`、`TelegramClient`、`LLMClient`）
- [ ] Step S.6：撰寫對應單元測試（見下方「測試策略」）—— `llm.client.LLMClient` 已於 Phase 1 Step 1.3 補上（2026-07-31），並於同日追加 ADR-5 本地端節流保護測試；`telegram.client.TelegramClient` 已於 Step 1.3b 補上（2026-07-31，6 個測試，覆蓋率 100%，含 `get_file_bytes`）；`cloudsql` 仍待對應功能實際串接時補上
- [x] Step S.7：建立 `submodules/gdrive/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`），Step 1.3b 影像辨識需要（2026-07-31）——刻意只暴露 `upload_file()`，不做下載/列表/刪除，避免建置用不到的能力
- [x] Step S.8（2026-08-01，見 ADR-9）：建立 `submodules/voice/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`），Step 1.4 語音轉文字需要——`VoiceClient.transcribe()`，用 `requests` 直打 Groq Whisper 的 OpenAI 相容 REST API，不安裝官方 `groq` SDK
- [x] Step S.9（2026-08-02，見 ADR-10）：`submodules/gdrive` 從 Service Account 認證改為 OAuth 2.0（真人帳號身分），修正 Service Account 無 Drive 儲存額度導致的 `storageQuotaExceeded`；新增 `get_refresh_token.py` 一次性互動授權腳本
- [x] Step S.10（2026-08-02，見 FR-10）：`submodules/cloudsql` 新增 `execute_query()`，Phase 1 Step 1.6（FR-21 Neon 容量監控）需要
- [x] Step S.11（2026-08-05，見 FR-11、ADR-11）：建立 `submodules/email/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`），robinson SPEC.md Step 2.4（FR-19b）需要——`EmailClient.send_text()` 用 `smtplib` 直打 Gmail SMTP（SSL），不安裝第三方套件，複用既有 `GMAIL_USER`／`GMAIL_PASSWORD`
- [x] Step S.12（2026-08-05，見 FR-12、ADR-12）：建立 `submodules/calendar/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`），robinson SPEC.md Step 2.7（FR-66）需要——`CalendarClient` 提供 `create_event()`／`update_event()`／`delete_event()`，用 `google-api-python-client` 直打 Google Calendar API v3，OAuth 2.0 認證比照 `gdrive`（見 ADR-10）但使用獨立一組憑證與 `calendar.events` scope；新增一次性互動授權腳本 `get_refresh_token.py`（比照 `gdrive` 的 Step S.9）；10 個測試，覆蓋率 100%
- [x] Step S.13（2026-08-07，見 FR-11／FR-14、ADR-11 追記／ADR-14）：`submodules/email` 新增 IMAP 讀信方法；新建 `submodules/newsfeed/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`），robinson SPEC.md Step 3.1（FR-22／FR-23）需要
- [x] Step S.14（2026-08-07 同日修正，見 FR-11／FR-14、ADR-11 追記／ADR-14）：Robin 驗收後明確排程改為「固定 23:00 收集當天內容」，`submodules/email` 方法簽章由 `fetch_yesterday_emails_from_domain(sender_domain, now=None)` 改為 `fetch_emails_from_domain_on_date(sender_domain, target_date)`；`submodules/newsfeed` 移除 `fetch_yesterday_articles()` 便利方法，只保留 `fetch_articles_published_on(feed_url, target_date)`；兩者皆改為呼叫端明確指定目標日期，子模組本身不再內建「今天/昨天」換算

## 測試策略

目前僅為骨架 wrapper，尚未接上真實業務邏輯，依 AGENTS.md「不適合 TDD 的情境」（第三方 wrapper）先以介面完整性與可讀性為主；待 Phase 1 backend 實際串接 Neon / Telegram / Gemini 時，一併補上以下測試：

### Unit Tests
- [ ] `cloudsql.client.CloudSQLClient`：mock `psycopg2` 連線，驗證 `select`/`insert`/`update`/`delete` 組出的 SQL 與參數正確；`update()`/`delete()` 未帶 `where` 應拋出 `ValueError`；`dsn` 未提供且無 `DATABASE_URL` 應拋出 `ValueError`（`select`/`insert`/`update`/`delete`/`execute` 仍待對應功能實際串接時補上，見 Step S.6）；`execute_query()` 已於 2026-08-02（Step 1.6 需要）補上 3 個測試，覆蓋率 100%：回傳資料列轉成 dict list、正確傳遞 `params`、正確 commit
- [x] `telegram.client.TelegramClient`：mock `requests.post`/`requests.get`，驗證 `send_text`/`send_photo`/`send_chat_action` 組出的 payload 正確、`get_file_bytes` 兩段式下載（`getFile` 換 `file_path` 再打檔案專屬網域）正確；空 `bot_token` 應拋出 `ValueError`（2026-07-31，6 個測試，覆蓋率 100%）。**2026-08-02 更新**：`send_text()` 預設不再帶 `parse_mode`（原預設 `"Markdown"`），改為純文字傳送，見下方「2026-08-02」決策補充；新增 1 個測試涵蓋「明確傳入 `parse_mode` 時仍會帶上」的情境，共 7 個測試，覆蓋率維持 100%
- [x] `llm.client.LLMClient`：mock `genai.Client`，驗證 `generate_text`/`generate_with_image` 呼叫參數正確；空 `api_key` 應拋出 `ValueError`（2026-07-31 依 ADR-8 移除 `generate_with_search` 測試，見 [chat-core SPEC.md](../chat-core/SPEC.md)）
- [x] `llm.client.LLMClient` 本地端節流保護（ADR-5，2026-07-31，4 個測試）：超過門檻拋 `LLMQuotaGuardError` 且不呼叫底層 SDK／同一 `api_key` 跨 instance 共用計數／不同 `api_key` 互不影響／時間視窗過期後計數重置
- [x] `gdrive.client.GDriveClient`：mock `google.oauth2.credentials.Credentials`／`googleapiclient.discovery.build`，驗證 `upload_file()` 帶正確 `filename`/`parents`/`mimetype`，回傳 `webViewLink`；空 `refresh_token`／`client_id`／`client_secret`／`folder_id` 應拋出 `ValueError`；`Credentials()` 收到正確的 OAuth 參數（2026-07-31，4 個測試，覆蓋率 100%；**2026-08-02 更新**：依 ADR-10 改為 OAuth 2.0 認證，建構子從 2 參數改為 4 參數，共 7 個測試，覆蓋率維持 100%）
- [x] `voice.client.VoiceClient`（2026-08-01，ADR-9，6 個測試，覆蓋率 100%）：mock `requests.post`，驗證 `transcribe()` 組出正確的 multipart payload（`headers`／`files`／`data`）、回傳去除頭尾空白的純文字、支援自訂 `model`／`filename`／`mime_type`；空 `api_key` 應拋出 `ValueError`；底層 request 失敗（`raise_for_status()` 拋例外）應往外拋，不吞例外
- [x] `email.client.EmailClient`（2026-08-05，ADR-11，5 個測試，覆蓋率 100%）：mock `smtplib.SMTP_SSL`，驗證 `send_text()` 以正確的 host/port 建立連線並呼叫 `login()`／`sendmail()`，`sendmail()` 的 envelope（from/to）與信件內容（`Subject`／`From`／`To`／純文字 body，用 `email.message_from_string()` 解析驗證）正確；空 `username`／`password` 應拋出 `ValueError`；底層 SMTP 例外（如登入失敗）應往外拋，不吞例外——由呼叫端（`webhook._send_email_fallback()`）決定要不要吞。**2026-08-07 擴充**（ADR-11 追記，見 FR-11、FR-22／FR-23）：新增讀信方法，mock `imaplib.IMAP4_SSL`，驗證正確組出 `SINCE`/`BEFORE`/`FROM` 搜尋條件、以 `login()`／`select("INBOX", readonly=True)`／`search()`／`fetch()` 依序呼叫、正確解析純文字與 multipart 信件內容、正確過濾寄件者網域（含子網域偽造情境）與寄送日期不符者、`search`/`fetch` 回傳非 `OK` 時優雅跳過、套用重試機制（`imaplib.IMAP4.error` 不重試／`OSError` 才重試）；另涵蓋 `_is_from_domain()`／`_sent_on_date()`／`_extract_plain_text()` 三個私有輔助函式的邊界情況（大小寫、空字串、格式錯誤的 Date header、無時區的 naive datetime、multipart 找不到 `text/plain` 分段等）。**同日再修正**：方法簽章改為 `fetch_emails_from_domain_on_date(sender_domain, target_date)`，比對基準從內部換算的「昨天」改為呼叫端傳入的 `target_date`，移除「now 預設當下時間」相關測試；最終共 30 個測試，覆蓋率維持 100%
- [x] `newsfeed.client.NewsFeedClient`（2026-08-07，見 FR-14、ADR-14，測試覆蓋率 100%）：mock `requests.get`，驗證 `fetch_articles_published_on()` 正確解析 RSS XML 取出 `title`/`link`，只回傳發布日期（換算台灣時區）符合呼叫端指定 `target_date` 的文章；`<item>` 缺少必要欄位時跳過；套用重試機制（連線失敗／逾時／HTTP 429／5xx 才重試，其餘不重試）。**同日修正**：移除 `fetch_yesterday_articles()` 便利方法與相關測試，只保留 `fetch_articles_published_on()`；最終共 20 個測試，覆蓋率維持 100%
- [x] `calendar.client.CalendarClient`（2026-08-05，見 FR-12、ADR-12，10 個測試，覆蓋率 100%）：mock `google.oauth2.credentials.Credentials`／`googleapiclient.discovery.build`（比照 `gdrive` 測試手法），驗證 `create_event()`／`update_event()`／`delete_event()` 帶正確的 `calendarId`／事件內容（含全天事件 `date`／有時間點事件 `dateTime`+`timeZone` 兩種格式），回傳新增後的 event ID；空 `refresh_token`／`client_id`／`client_secret`／`calendar_id` 應拋出 `ValueError`
- [x] `retry.client.call_with_retry()`（2026-08-07，見 FR-13、ADR-13，6 個測試，覆蓋率 100%）：mock `time.sleep`，驗證第一次成功不重試／可重試例外重試後成功／Exponential Backoff 秒數依序為 1s/2s/4s／重試次數用盡後往外拋出最後一次的原始例外／`is_retryable` 判定為 `False` 時不重試、立即拋出／`max_attempts`／`backoff_seconds` 可被覆寫
- [x] 6 個既有子模組套用重試機制後的測試更新（2026-08-07，見 FR-19i、ADR-13）：`llm`（+7 個測試，含 ServerError／ClientError 429／永久性 ClientError 404 不重試／`generate_with_image` 也套用／重試用盡拋出／`ConnectionError`／`LLMQuotaGuardError` 不受重試影響）、`telegram`（+7 個測試，`call()`／`get_file_bytes()` 皆套用，含連線錯誤／5xx／400 不重試／重試用盡／`is_retryable` 邊界情況）、`voice`（+4 個測試）、`gdrive`（+5 個測試，含 `HttpError` 403 不重試／`is_retryable` 邊界情況）、`calendar`（+5 個測試，含 `HttpError` 404 不重試／`is_retryable` 邊界情況）、`email`（+3 個測試，含 `SMTPAuthenticationError` 不重試）；全部經由 monkeypatch `submodules.retry.client.time.sleep`（或共用同一個 `time` 模組物件）驗證不會真的等待，測試維持毫秒等級執行速度；全專案 795 個測試全過，這 7 個子模組（含新增的 `retry`）皆維持 100% 覆蓋率

### Integration Tests
- [ ] `cloudsql`：對測試用 Neon 分支資料庫實際下 CRUD，確認連線池可正常取得/歸還連線
- [ ] `telegram`：對 Telegram 測試 Bot 實際發送訊息，確認 API 回應 `ok: true`
- [ ] `llm`：對 Gemini API 實際呼叫 `gemini-3.5-flash-lite`，確認能取得非空回應（需留意計入免費額度）

## 風險與緩解

| 風險 | 嚴重度 | 機率 | 緩解方案 |
| --- | --- | --- | --- |
| 連線池設定過大，超過 Neon 免費方案連線數上限 | 中 | 低 | 預設 `max_conn=5`，並在 README 註記依實際方案調整 |
| `google-genai` SDK 介面未來變動（目前仍持續更新） | 低 | 中 | Client 對外只暴露 `generate_text`/`generate_with_image` 兩個方法，SDK 版本升級只需改內部實作 |
| CRUD wrapper 被誤用於拼接未信任的 table/column 名稱，產生 SQL Injection | 高 | 低 | table/column 一律由程式內部信任字串提供，不可直接帶入使用者輸入；README 明確註記此限制 |
| 子模組自己的 `requirements.txt` 與主專案根目錄 `requirements.txt` 版本/內容不同步 | 中 | 中 | ADR-4 已明訂根目錄 `requirements.txt` 為部署權威來源，日後新增/更新子模組依賴時兩邊都要改 |
| ADR-5 的節流狀態掛在 class 層級（單一 process 內共用），若未來改成多 process/多 worker 部署，各 process 會各自維護一份節流計數，實際節流效果會打折（見 ADR-5 已知取捨） | 低 | 低 | 目前 Render 部署方式是單一 Flask process，不受影響；若未來真的改多 worker，需重新評估升級為外部共用計數（ADR-5 方案 C） |
| ADR-6 只提升了 RPD 上限（20→500），本地端節流保護（ADR-5）目前只防 RPM、沒有防 RPD，單日用量若逼近 500 次仍會被官方 429 擋下 | 中 | 低 | 目前個人/家庭規模用量離 500/天還有很大緩衝；若未來實測發現常態性逼近上限，需要另外補上「每日次數」的本地端節流層 |
| IThome／TechCrunch 未來改版 RSS 結構或 Feed 網址失效，`newsfeed.client.NewsFeedClient` 解析不到文章 | 低 | 低 | 屬於「暫時性錯誤」判定外的情況（非連線問題，重試無效），會直接往外拋，由呼叫端（`src/bot/skill_growth.py`）優雅降級為「該來源今天沒有新聞」，不影響其他來源與其他模組 |

## 變更記錄

| 日期 | 變更內容 | 變更者 |
| --- | --- | --- |
| 2026-07-29 | 初版建立：3 個子模組骨架（neon_postgres / telegram_client / gemini_client）與對應 ADR | Robin |
| 2026-07-29 | 依 Robin 指定樣板重構：資料夾更名為 `llm` / `cloudsql` / `telegram`，統一為「四檔案結構」（`client.py`/`README.md`/`requirements.txt`/`.env.example`），移除 `__init__.py` 與多檔案拆分，三個 Client 改寫成 class（`LLMClient`/`CloudSQLClient`/`TelegramClient`），新增 ADR-4、FR-6、NFR-4 | Robin |
| 2026-07-30 | `CloudSQLClient` 新增 `execute()` 方法，支援執行任意 SQL（主要供 DDL 使用），為 robinson 專案 ADR-11 的 migration 執行機制（`src/migrations/runner.py`）提供底層能力；`select`/`insert`/`update`/`delete` 的參數化保護不受影響，`execute()` 明確標註為「僅供內部信任 SQL 使用」的逃生口 | Claude（依 robinson SPEC.md ADR-11 需求） |
| 2026-07-31 | Robin 實測撞到 Gemini 429 後要求「該做的防呆要做好」；新增 FR-7、ADR-5：`LLMClient` 加上本地端節流保護（同一 `api_key` 最近 60 秒超過 8 次呼叫直接擋下、不送出請求），節流計數以 class 層級狀態、`api_key` 為單位共用；新增 `tests/submodules/llm/conftest.py` 避免測試間互相汙染；全專案 137 個測試全過、覆蓋率 100% | Claude（依 Robin「該做的防呆要做好」指示） |
| 2026-07-31 | Step 1.3b（影像辨識）需要：新增 Step S.7、`submodules/gdrive/`（`GDriveClient`，僅 `upload_file()`，不做下載/列表/刪除）；`telegram.client.TelegramClient` 補上單元測試並新增 `get_file_bytes()`（Step S.6 telegram 部分完成）；修正 `pytest.ini` 加 `--import-mode=importlib`，解決多個 `submodules/*/test_client.py` 同名模組在同一次 `pytest tests/` 執行時互相衝突的問題 | Claude（依 Robin「你繼續開發你的」指示） |
| 2026-07-31 | Robin 持續撞到 429，經 AI Studio Rate Limit 頁面實測確認 `gemini-flash-latest` 別名解析到的 Gemini 3.6 Flash 免費層只有 RPM 5／RPD 20，遠低於原本假設；新增 ADR-6：改用明確指定版本的 `gemini-3.5-flash-lite`（實測 RPM 15／RPD 500，同屬 Gemini 家族、零相容性風險），Gemma 4（RPM 30／RPD 14,400）與計費升級留待額度仍不夠用時再評估；`_DEFAULT_MODEL` 改為 `gemini-3.5-flash-lite` | Claude（依 Robin「好啊，麻煩你了」指示） |
| 2026-07-31 | 換模型後 `generate_with_search()` 仍持續 429；逐步排查（新 Key／新專案測純文字成功、掛搜尋工具後同樣 429）後，Robin 於 AI Studio「Tools」區塊發現 Google Search grounding 免費額度依模型世代分桶：Gemini 2／2.5 世代有 1,500 次/天免費額度，**Gemini 3 世代（含 `gemini-3.5-flash-lite`）免費額度是 0**（官方定價頁證實：Gemini 3 使用 grounding 一律計費，免費層不提供）；新增 ADR-7：`generate_with_search()` 固定改用 `gemini-2.5-flash-lite`，其餘方法維持 ADR-6 的 `gemini-3.5-flash-lite`；同時盤點所有功能模組，確認只有一般聊天核心依賴 grounding，104／YouTube 走各自獨立官方 API 不受影響 | Claude（依 Robin「好，麻煩你了」指示） |
| 2026-07-31 | Robin 實測發現 `gemini-2.5-flash-lite` 在 AI Studio 不可選用，修正 ADR-7：`_SEARCH_MODEL` 改為 `gemini-2.5-flash`（同世代、享有相同的 1,500 次/天免費 grounding 額度） | Claude（依 Robin 回報指示） |
| 2026-07-31 | Robin 換用新產生的 `GEMINI_API_BOT_KEY` 後 `gemini-2.5-flash` 回傳 404，排查後確認為 Gemini 2.5 世代對新專案關閉存取（非額度／掛工具問題），新增 ADR-8（supersede ADR-7）：`generate_with_search()`／`_SEARCH_MODEL`／`_used_search()` 全數移除；相關測試更新，全專案 174 個測試全過、覆蓋率 100%（見 [chat-core SPEC.md](../chat-core/SPEC.md) ADR-5） | Claude（依 Robin「移除所有上網查詢的部分」指示） |
| 2026-08-01 | Phase 1 Step 1.4（語音轉文字）需要：新增 Step S.8、FR-8、ADR-9：建立 `submodules/voice/`（`VoiceClient`，用 `requests` 直打 Groq Whisper OpenAI 相容 REST API，不安裝官方 `groq` SDK，比照 `telegram` 子模組的 ADR-2 慣例）；同步補上頂部骨架示意圖遺漏已久的 `gdrive/` 資料夾；全專案 252 個測試全過、覆蓋率 100% | Claude（依 Robin「好」指示） |
| 2026-08-02 | Robin 實測回報「我要看所有功能」觸發 Telegram `400 Bad Request`；排查後確認 `send_text()` 預設 `parse_mode="Markdown"`，但回覆文字是 LLM 自然語言生成，格式不保證符合 Telegram 舊版 Markdown 語法，一旦不符會整則被拒收，所有 LLM 生成的回覆都有此風險；Robin 選擇直接關閉 Markdown，改為預設純文字傳送（見上方 ADR-2 補充決策），呼叫端仍可視需要明確傳入 `parse_mode`；新增 1 個測試，全專案 285 個測試全過、覆蓋率 100% | Claude（依 Robin 選定方向實作） |
| 2026-08-02 | Robin 實測語音上傳撞到 Google Drive API `403 storageQuotaExceeded`，查證確認 Service Account 完全沒有 Drive 儲存額度，跟資料夾空間無關；新增 FR-9、Step S.9、ADR-10：`submodules/gdrive` 改用 OAuth 2.0（真人帳號身分），`GDriveClient` 建構子改為 `refresh_token`／`client_id`／`client_secret`／`folder_id`，新增一次性本機互動授權腳本 `get_refresh_token.py`（`requirements.txt` 新增 `google-auth-oauthlib`）；`gdrive.client.GDriveClient` 測試改為 mock `google.oauth2.credentials.Credentials`，共 7 個測試；全專案 329 個測試全過、覆蓋率 100% | Claude（依 Robin 於 AskUserQuestion 選定方向實作） |
| 2026-08-02 | robinson SPEC.md Step 1.6（FR-21 Neon 容量監控）需要：新增 FR-10、Step S.10：`cloudsql.client.CloudSQLClient` 新增 `execute_query()`，跟既有 `execute()`（DDL 用）成對、差別是會回傳資料列，補上 3 個測試（先前 Step S.6 一直標記「待對應功能實際串接時補上」，這次先補新增的部分，其餘既有方法仍延續原本的延後決定）；全專案 352 個測試全過、覆蓋率 100% | Claude（依 Robin「請繼續開發吧」指示） |
| 2026-08-05 | Robin 驗收 robinson SPEC.md Step 2.4（FR-19b，錯誤 log 雲端連結）時提出「如果壞掉的是 Telegram 本身，不就完全沒辦法通知？」；新增 FR-11、Step S.11、ADR-11：建立 `submodules/email/`（`EmailClient.send_text()`，`smtplib` 直打 Gmail SMTP，不安裝第三方套件），複用既有的 `GMAIL_USER`／`GMAIL_PASSWORD`（原為 Phase 3 FR-23 預留但未使用）；5 個測試（mock `smtplib.SMTP_SSL`），覆蓋率 100%；全專案 720 個測試全過 | Claude（依 Robin 提出的問題新增備援機制） |
| 2026-08-05 | Robin 討論 Google Calendar 能拿來做什麼後，確認先做「待辦事項／重要通知／體態目標期限」單向同步寫入共用行事曆（不含讀取查空檔）；新增 FR-12、Step S.12（尚未實作）、ADR-12：規劃 `submodules/calendar/`（`CalendarClient`，Google Calendar API v3，OAuth 2.0，獨立一組憑證＋`calendar.events` scope，不與 `gdrive` 共用憑證）；對應 robinson SPEC.md FR-66、Step 2.7、ADR-17；本次僅規格文件，程式尚未動工 | Claude（依 Robin「幫我補三點至規格書」指示） |
| 2026-08-05 | **Step S.12 完成**：Robin 完成 Google Cloud Console 手動設定（Calendar API、獨立 OAuth 用戶端、共用行事曆）並指示開工；建立 `submodules/calendar/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`、`get_refresh_token.py`）：`CalendarClient` 提供 `create_event()`／`update_event()`／`delete_event()`，事件內容格式（全天 `date` 或有時間點 `dateTime`+`Asia/Taipei` 時區）由呼叫端透過 `all_day` 參數決定；10 個測試（mock `Credentials`／`build`，比照 `gdrive` 手法），覆蓋率 100%；全專案 730 個測試全過。根目錄 `requirements.txt` 已含 `google-api-python-client`／`google-auth`（gdrive 沿用），不需新增 | Claude（依 Robin「Google Calendar 已設定完，可以開工了」指示實作） |
| 2026-08-07 | **新增 FR-13、ADR-13：`submodules/retry` 共用重試工具（對應 robinson SPEC.md Step 2.5、FR-19i）**。Robin 確認繼續 Phase 2 Step 2.5 後，經 AskUserQuestion 確認三個設計問題：① 程式碼放置方式選「抽成共用 retry 工具」（而非 6 個 client 各自複製），是 ADR-4「子模組彼此獨立、互不 import」的刻意例外 ② 重試判斷標準選「只重試暫時性錯誤」（連線失敗、逾時、HTTP 429／5xx），永久性錯誤（401/403/404 等）直接往外拋 ③ 套用範圍確認這次只套用到 6 個現有子模組，104 求職爬蟲 API 留到 Phase 4 開工時比照。新增 `submodules/retry/`（`call_with_retry()`，只負責重試迴圈與 Exponential Backoff 時間控制，`is_retryable` 判斷式由呼叫端傳入）；`llm`／`telegram`／`voice`／`gdrive`／`calendar`／`email` 六個 `client.py` 都套用，各自定義符合自己 SDK 例外型別的 `_is_retryable_xxx_error()`；`LLMClient` 既有的本地端節流保護（`LLMQuotaGuardError`）刻意留在重試包裹範圍之外，因為節流是時間窗口邏輯，立即重試無意義。TDD 全程 RED→GREEN：先寫 `retry` 的 6 個測試，再逐一為 6 個子模組補上重試情境測試（成功重試、永久性錯誤不重試、重試用盡拋出、`is_retryable` 邊界情況）；全專案 795 個測試全過，7 個子模組（含新增的 `retry`）皆維持 100% 覆蓋率 | Claude（依 Robin 於 AskUserQuestion 確認範圍後實作） |
| 2026-08-07 | **Robin 選定 Phase 3 Step 3.1（每日重點技術分享，FR-22／FR-23）開工**：經 AskUserQuestion 確認三個設計問題：① TLDR 電子報辨識方式選「寄件者網域比對」（`tldrnewsletter.com`，比主旨關鍵字穩定）② IThome／TechCrunch 新聞來源選「RSS Feed」（輕量、不用額外套件）③ 去重機制核准於 `users` 表新增 `skill_growth_pushed_on`（DATE）欄位（依 ADR-10 流程，比照 `todos.daily_pushed_on` 慣例），對應 migration `0033_add_skill_growth_pushed_on_to_users.sql`。ADR-11 追記：`submodules/email` 新增 `fetch_yesterday_emails_from_domain()`（IMAP 讀信，+23 個測試，共 31 個，覆蓋率 100%）；新增 FR-14、ADR-14：建立 `submodules/newsfeed/`（`NewsFeedClient`，`requests`＋標準函式庫 `xml.etree.ElementTree` 解析 RSS，不裝 `feedparser`） | Claude（依 Robin「從 3-1 開始吧」指示，經 AskUserQuestion 確認範圍後實作） |
| 2026-08-07 | **同日修正：Step 3.1 拆成「23:00 收集／08:00 推播」兩階段**。Robin 驗收時明確給出 TLDR 寄件信箱 `dan@tldrnewsletter.com`、確認排程改為固定台灣時間 23:00 收集當天 TLDR 電子報＋IThome／TechCrunch 新聞、隔天固定 08:00 才推播；三個來源皆無內容時固定回覆「未獲得最新技術分享」。經 AskUserQuestion 確認新增 `skill_growth_digests` 表取代原規劃、尚未套用的 `users.skill_growth_pushed_on` 欄位，直接修改 `0033` migration 內容。`submodules/email` 的 `fetch_yesterday_emails_from_domain(sender_domain, now=None)` 改為 `fetch_emails_from_domain_on_date(sender_domain, target_date)`（呼叫端一律明確指定日期，最終共 30 個測試，覆蓋率維持 100%）；`submodules/newsfeed` 移除 `fetch_yesterday_articles()` 便利方法，只保留 `fetch_articles_published_on(feed_url, target_date)`（最終共 20 個測試，覆蓋率維持 100%）；ADR-11／ADR-14 皆補上同日追記說明設計變更緣由 | Claude（依 Robin 驗收回饋，經 AskUserQuestion 確認 DB 設計後修正） |
