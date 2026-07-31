---
title: Submodules — 共用子模組基礎骨架
slug: submodules-core
status: draft
created: 2026-07-29
updated: 2026-07-31
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
- [x] FR-3：`submodules/llm` 提供 LLM Client 初始化與文字生成 / 圖文生成呼叫；目前實際串接 Gemini API，模型固定 `gemini-3.5-flash-lite`（**2026-07-31 更新**，見 ADR-6），命名為 llm 是為了未來替換或新增供應商時介面不變
- [x] FR-4：三個子模組彼此獨立、互不 import，也不依賴 `backend/` 或本專案任何商業邏輯（單向依賴：上層可以 import submodules，反向禁止）
- [x] FR-5：所有連線資訊（DB 連線字串、Bot Token、API Key）一律由外部呼叫端注入或讀取環境變數，子模組內部不得寫死任何金鑰
- [x] FR-6：每個子模組資料夾一律只包含 `client.py`、`README.md`、`requirements.txt`、`.env.example` 四個檔案，不得拆成多個 `.py` 檔、不得加 `__init__.py`（見 ADR-4）
- [x] FR-7（2026-07-31 新增，見 ADR-5）：`llm.client.LLMClient` 內建本地端節流保護 —— 呼叫 `generate_text`／`generate_with_image`／`generate_with_search` 任一方法前，先檢查「最近 60 秒內以同一把 `api_key` 呼叫的次數」，超過門檻（預設 8 次／分鐘）直接拋 `LLMQuotaGuardError`、不送出請求；門檻可透過建構子 `max_calls_per_minute` 參數調整

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

## 實作計畫

### Phase 0（對應 robinson SPEC.md 的 Step 0.1a）：建立子模組骨架

- [x] Step S.1：建立 `submodules/cloudsql/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`）
- [x] Step S.2：建立 `submodules/telegram/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`）
- [x] Step S.3：建立 `submodules/llm/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`）
- [x] Step S.4：更新主專案根目錄 `requirements.txt`（新增 `psycopg2-binary`、`google-genai`、`python-dotenv`）
- [x] Step S.5：改版重構 — 刪除舊版 `neon_postgres/`、`telegram_client/`、`gemini_client/`（含各自的 `__init__.py`、`connection.py`、`crud.py`、`sender.py`），統一為 ADR-4 的四檔案結構，並將三個 Client 改為 class 寫法（`CloudSQLClient`、`TelegramClient`、`LLMClient`）
- [ ] Step S.6：撰寫對應單元測試（見下方「測試策略」）—— `llm.client.LLMClient` 已於 Phase 1 Step 1.3 補上（2026-07-31），並於同日追加 ADR-5 本地端節流保護測試；`telegram.client.TelegramClient` 已於 Step 1.3b 補上（2026-07-31，6 個測試，覆蓋率 100%，含 `get_file_bytes`）；`cloudsql` 仍待對應功能實際串接時補上
- [x] Step S.7：建立 `submodules/gdrive/`（`client.py`、`README.md`、`requirements.txt`、`.env.example`），Step 1.3b 影像辨識需要（2026-07-31）——刻意只暴露 `upload_file()`，不做下載/列表/刪除，避免建置用不到的能力

## 測試策略

目前僅為骨架 wrapper，尚未接上真實業務邏輯，依 AGENTS.md「不適合 TDD 的情境」（第三方 wrapper）先以介面完整性與可讀性為主；待 Phase 1 backend 實際串接 Neon / Telegram / Gemini 時，一併補上以下測試：

### Unit Tests
- [ ] `cloudsql.client.CloudSQLClient`：mock `psycopg2` 連線，驗證 `select`/`insert`/`update`/`delete` 組出的 SQL 與參數正確；`update()`/`delete()` 未帶 `where` 應拋出 `ValueError`；`dsn` 未提供且無 `DATABASE_URL` 應拋出 `ValueError`
- [x] `telegram.client.TelegramClient`：mock `requests.post`/`requests.get`，驗證 `send_text`/`send_photo`/`send_chat_action` 組出的 payload 正確、`get_file_bytes` 兩段式下載（`getFile` 換 `file_path` 再打檔案專屬網域）正確；空 `bot_token` 應拋出 `ValueError`（2026-07-31，6 個測試，覆蓋率 100%）
- [x] `llm.client.LLMClient`：mock `genai.Client`，驗證 `generate_text`/`generate_with_image` 呼叫參數正確；空 `api_key` 應拋出 `ValueError`（2026-07-31 依 ADR-8 移除 `generate_with_search` 測試，見 [chat-core SPEC.md](../chat-core/SPEC.md)）
- [x] `llm.client.LLMClient` 本地端節流保護（ADR-5，2026-07-31，4 個測試）：超過門檻拋 `LLMQuotaGuardError` 且不呼叫底層 SDK／同一 `api_key` 跨 instance 共用計數／不同 `api_key` 互不影響／時間視窗過期後計數重置
- [x] `gdrive.client.GDriveClient`：mock `service_account.Credentials.from_service_account_file`／`googleapiclient.discovery.build`，驗證 `upload_file()` 帶正確 `filename`/`parents`/`mimetype`，回傳 `webViewLink`；空 `key_file_path`／`folder_id` 應拋出 `ValueError`（2026-07-31，4 個測試，覆蓋率 100%）

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
