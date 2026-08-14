---
title: Robinson — Robin 與家人們的生活小助手
updated: 2026-08-14
owner: Robin
---

# Robinson — Robin 與家人們的生活小助手

> 本檔案只放**最終定案版本**。未定案的想法先寫進 `docs/specs/DRAFT.md`；每個功能區塊的討論過程
> 記在 `docs/ADR/discuss/<功能>.md`，修 bug 記在 `docs/ADR/debug/<功能>.md`；單一功能區塊若成長超過
> 約 200 行，把細節移到 discuss/ 或獨立附錄，這裡只留摘要 + 連結。
>
> 本檔案於 2026-08-13 由原本「一功能一份 SPEC.md」的 7 份規格整併而成，原規格內容均已納入本文。
> 各功能區塊以純文字「來源說明」保留原規格名稱與整併日期，不依賴舊檔案路徑即可追溯。

## 產品背景

Robinson 是一個雙前台架構的家庭生活小助手：Telegram Bot 負責自然語言互動、跨日期補登與完整資料管理；Mobile App「羅賓森」提供分析圖表、個人／APP 設定、今日生活紀錄，以及待辦事項、重要日子與收藏清單等不限今日的管理入口。Robin 是產品負責人兼管理者，家人透過通關密碼取得使用權限。核心理念是「越少 UI 設定越好」，所有服務一律使用免費方案，AI 能力統一由 Gemini API 依用途分流多把 Key 提供。

## 技術棧與平台策略

| 層級 | 技術/工具/API | 版本 | 狀態 | 備註 |
| --- | --- | --- | --- | --- |
| 後端語言／Runtime | Python | 3.11 | 使用中 | Render 使用 `python:3.11-slim` Docker Image 執行 Flask、Telegram Bot 與背景排程 |
| 對話前台（完整輸入＋CRUD） | Telegram Bot API | — | 使用中 | 提供文字／語音／圖片輸入、跨日期補登與完整資料管理；`python-telegram-bot` 已移除，改用原生 JSON dict 解析 |
| Mobile 語言／UI Framework | TypeScript + React + React Native + Expo | TypeScript 6／React 19／React Native 0.86／Expo 57 | 使用中（2026-08-12 正式上線） | Mobile App「羅賓森」共用 Web／iOS／Android 程式架構；目前正式交付版本為 Expo Web |
| Mobile Web／路由 | React Native Web + Expo Router | React Native Web 0.21／Expo Router 57 | 使用中 | SPA 頁面、登入導向與各分析／設定頁路由 |
| Mobile 日期／圖片輸入 | `react-native-calendars` + DateTimePicker + `expo-image-picker` | — | 使用中 | 待辦、日期區間、重要日子、時間選擇，以及飲食拍照／相簿選擇 |
| Web 框架 | Flask | — | 使用中 | 同步架構，webhook 單一進入點 |
| 資料庫 | Neon PostgreSQL（psycopg2 + ThreadedConnectionPool） | — | 使用中 | 不用 ORM；連線池上限低（預設 1～5）配合免費額度 |
| 資料庫 Migration | `src/migrations/` + 開機自動套用 | — | 使用中 | 取代人工貼 SQL；`schema_migrations` 追蹤表 |
| App 登入認證 | bcrypt + PyJWT + Expo SecureStore | — | 使用中 | bcrypt 保存密碼雜湊、JWT Access Token、rolling Refresh Token；原生裝置以 SecureStore 保存 Refresh Token |
| 檔案儲存 | Google Drive（OAuth 2.0，真人帳號身分） | — | 使用中 | 取代原 Service Account（無 Drive 儲存額度問題） |
| AI 對話/生成 | Gemini API（`gemini-3.5-flash-lite`） | — | 使用中 | 依用途拆多把 Key，見下方「AI 模型金鑰分流」 |
| AI 語音轉文字 | Groq Whisper（OpenAI 相容 REST API） | — | 使用中 | 取代原規劃「語音一律用 Gemini」；`requests` 直打，不裝官方 `groq` SDK |
| 家庭行事曆 | Google Calendar API v3（OAuth 2.0，獨立憑證，`calendar.events` scope） | — | 使用中 | 單一共用行事曆，僅 Robin 授權，家人訂閱瀏覽 |
| 政府辦公日曆資料 | 中華民國政府行政機關辦公日曆 CSV（政府資料開放平臺） | — | 使用中 | 由 `TaiwanCalendarService` 按年度取得並快取至 `taiwan_calendar_days`，供休假日、補班日與節日顯示 |
| 備援通知 | Gmail SMTP/IMAP（`smtplib`/`imaplib`，標準函式庫） | — | 使用中 | Telegram 故障備援 + TLDR 電子報讀取 |
| RSS 擷取 | 標準函式庫 `xml.etree.ElementTree` + `requests` | — | 使用中 | 不裝 `feedparser` |
| 網頁正文擷取 | `beautifulsoup4` | — | 使用中 | 技術新聞全文摘要用 |
| 求職資料 | 104 前端 AJAX/JSON API（直接呼叫，非爬蟲工具） | — | 使用中 | 不用 Playwright/Selenium |
| 影片情報 | YouTube Data API v3 | — | 使用中 | 只取中繼資料，不下載影音 |
| Excel/CSV | `openpyxl`、標準函式庫 `csv` | — | 使用中 | 求職推薦報表、公司背景協作 |
| 音訊處理 | `pydub`（依賴系統 `ffmpeg`） | — | 使用中 | 整包聽力 MP3 切割 |
| 圖片壓縮 | `Pillow` | — | 使用中 | 上傳圖片先壓縮至 1024×1024／JPEG 80% 再送 AI |
| 農曆計算 | `lunarcalendar` | — | 使用中 | 純 Python、免網路，即時計算節日西曆日期 |
| 後端容器 | Docker（`python:3.11-slim` + ffmpeg） | — | 使用中 | 安裝正式 Python 依賴並以 `python main.py` 啟動 Flask 服務 |
| 後端部署 | Render（免費方案） | — | 使用中 | Git push to main 自動部署 Docker 容器 |
| Mobile Web 部署 | Vercel | — | 使用中 | 託管 Expo Web SPA，並將同源 `/api/*` Proxy 至 Render Flask API |
| Keep-alive | cron-job.org（每 10 分鐘打 `/healthz`） | — | 使用中 | 同時借用頻率跑十餘個排程檢查（背景 daemon thread） |
| 後端測試／覆蓋率 | pytest + pytest-cov | — | 使用中 | 測試集中於 `tests/`；認證與安全邏輯要求 100% 覆蓋 |
| Python Lint | Ruff | — | 使用中 | 執行 PEP 8 與 Python 程式碼品質檢查 |
| ORM（SQLAlchemy） | — | — | 決定不用 | 需要為每個模組定義 Model，與「跨專案重用的通用 CRUD 小工具」目標衝突，見 submodules-core 討論紀錄 ADR-1 |
| Notion（視覺化後台） | — | — | 決定不用 | 客製化程度低、無多用戶權限機制，改採 Mobile App，見 mobile-app 討論紀錄 |
| Google Search grounding | — | — | 決定不用 | Gemini 2.5 世代對新專案關閉存取、Gemini 3 世代免費層 grounding 額度為 0，見 chat-core 討論紀錄 ADR-5、submodules-core 討論紀錄 ADR-7/ADR-8 |
| AI 自主診斷＋GitHub PR 自動化 | — | — | 決定不用 | 工程量與風險不成比例，改採「完整 log 上傳雲端＋Robin 專屬連結」，見 service-resilience 討論紀錄 |
| `feedparser`（RSS 解析套件） | — | — | 決定不用 | 標準函式庫 `xml.etree.ElementTree` 已足夠，見 submodules-core 討論紀錄 ADR-14 |
| 官方 `groq` SDK | — | — | 決定不用 | 只需要單一 REST 端點，`requests` 已足夠，見 submodules-core 討論紀錄 ADR-9 |
| Gemma 4 / Gemini 付費 Tier | — | — | 決定不用（暫緩） | `gemini-3.5-flash-lite` 免費額度已夠用，留待額度不足時再評估，見 submodules-core 討論紀錄 ADR-6 |
| Yoda1 藍牙體重計被動廣播（Web/PWA） | — | — | 決定不用 | 實機驗證 PWA/Bluefy 相容性不穩定，全面移除藍牙功能，改為手動輸入，見 mobile-app SPEC.md |

**AI 模型金鑰分流**（見 submodules-core 討論紀錄 2026-07-30 條目）：`GEMINI_API_BOT_KEY`（一般問答）、`GEMINI_API_IMAGE_KEY1`/`KEY2`（影像辨識，隨機擇一）、`GEMINI_API_TEXT_KEY`（長文生成/長記憶摘要）、`GEMINI_API_PRIVACY_KEY`（個資語意偵測）、`GEMINI_API_SKILL_GROWTH_KEY`（技術摘要）、`GEMINI_API_JOB_SEARCH_KEY`（契合度評分）、`VOICE_API_KEY`（Groq Whisper）——每種用途各自一把 Key，額度互相隔離。

## 產品藍圖與功能規格

### 平台核心入口（通關密碼驗證／Owner 對話式設定／`/rule`／`/function`）

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/platform-auth.md`
**來源說明**：原記錄於 platform-auth 規格，已於 2026-08-13 併入本文件（原 robinson spec ADR-3、ADR-8 已併入本討論紀錄，內容已被本區塊取代）。

**概要**：所有使用者第一次接觸 Bot 時用到的基礎機制：Telegram Webhook 入口、通關密碼驗證與綁定、Owner 專屬引導式通關密碼設定對話流、綁定成功歡迎訊息，以及 `/rule`／`/function` 兩個內建說明指令。是後續所有功能模組的前置依賴。`/function` 的完整版（總覽＋按需深入）已於 Step 1.3a 由 Gemini 對話核心區塊取代，見下方連結。

**功能性需求**
- FR-1：`POST /telegram/webhook` 依身分與內容路由到對應處理邏輯
- FR-2：`is_owner` 判斷——比對 `telegram_user_id` 是否等於 `ROBIN_TELEGRAM_TOKEN`
- FR-3：未知使用者比對通關密碼，成功則綁定並回傳歡迎訊息（附錄 A 全文，靜態文字不經 LLM）
- FR-4：Owner 專屬 `/set_invite_codes` 對話流——詢問稱謂→收密碼→寫入 `users`／`invite_codes`→循環直到「沒有了」
- FR-5：`/rule`——回傳附錄 A 全文，不經 LLM
- FR-6：`/function` MVP 版（已於 Step 1.3a 被 chat-core 區塊的人格化總覽取代，觸發字串不變）
- FR-7（安全網）：`telegram_webhook()` 用 `try/except` 涵蓋 DB/LLM Client 建立到 `handle_message()` 整段流程，任何未預期例外一律 log + 回覆安全用語，仍回傳 HTTP 200，避免 Telegram 重試風暴燒額度
- FR-7a：`update_id` 去重（LRU 上限 1000 筆）
- FR-7b：本地端節流保護（見 submodules-core 區塊）

**非功能性需求**
- NFR-1：安全 — 通關密碼比對與綁定操作用「原子性條件 UPDATE」避免 race condition
- NFR-2：可用性 — Owner 設定對話流狀態存 process 記憶體，服務重啟會遺失，Robin 需重新開始（刻意簡化）
- NFR-3：可維護性 — webhook 路由與命令處理邏輯分層存放

**實作階段**（對應 PROGRESS.md）
- Phase 1 Step 1.1：全數完成，49 個測試全過、覆蓋率 100%

### 功能開關系統

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/feature-toggles.md`
**來源說明**：原記錄於 feature-toggles 規格，已於 2026-08-13 併入本文件。

**概要**：讓每位使用者可自行開關「自己」的功能模組，Owner 額外擁有代管權限可調整任何使用者的開關。開關狀態本身只負責「記下來、查看、切換」，實際攔截對話的邏輯依附在各功能模組自身。

**功能性需求**
- FR-1：`/my_toggles`——列出自己所有功能開/關狀態，輸入編號切換
- FR-2：`/set_toggle`——僅 Owner 可觸發，先選要調整誰
- FR-3：使用者第一次綁定成功時自動補齊全部功能開關（`is_enabled=TRUE`），冪等；2026-08-07 `skill_growth` 拆成 `tech_intel`／`certificate`／`language` 三個獨立開關（10 個模組）；**客訴回饋不含在內**——客訴是固定入口，非可關閉功能，不寫入 `feature_toggles`
- FR-4：`/my_toggles`／`/set_toggle` 顯示前皆先呼叫補齊邏輯作為安全網

**非功能性需求**
- NFR-1：可維護性 — 沿用既有 `ConversationStateStore`，新增 `flow` 欄位區分對話流
- NFR-2：安全 — 一般使用者只能查看/切換自己的開關

**實作階段**
- Phase 1 Step 1.2：全數完成，78 個測試全過、覆蓋率 100%

### Gemini 對話核心

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/chat-core.md`
**來源說明**：原記錄於 chat-core 規格，已於 2026-08-13 併入本文件。

**概要**：一般聊天訊息的核心處理邏輯，取代早期的佔位回覆。記憶架構由短記憶（最近 10 則原文）、長記憶（滾動式摘要）、知識庫（人格/家人背景/客製/使用者對話）三部分組成，查無答案時誠實回報不知道並邀請使用者提供答案存檔。`/function` 總覽與細節追問（FR-56、FR-56a～h）也在本區塊實作。

**功能性需求**
- FR-1：路由層最終 fallback 呼叫對話核心
- FR-2：Context 組裝——人格背景／家人背景／使用者自己的 custom 知識庫／最近 10 則對話
- FR-3：System Prompt 規則——人格語氣、只根據提供內容回答、誠實回報不知道、真實日期由伺服器算出、代名詞指涉「最近一次」明確點名對象、回答精簡、絕不謊報已寫入知識庫
- FR-4：查無答案時附加標記 `【NOT_FOUND】`，進入 `pending_user_knowledge` 狀態，下一則輸入由同一次 LLM 呼叫判斷是「答案」「拒絕」還是「新問題」（`【SAVE_ANSWER】`/`【DECLINE_SAVE】`/無標記）
- FR-5：只有真正進入聊天核心的訊息才記錄 `conversation_logs`
- FR-6/FR-7：長記憶查詢與滾動式摘要更新（backlog ≥10 則觸發）
- FR-8：新使用者自動建立空白摘要
- FR-9：`/function` 總覽（獨立小型 LLM 呼叫）＋細節追問（併入一般聊天核心）
- FR-10：`/clean-all-dialog`——先反問確認筆數，確認後清除自己的對話紀錄與摘要，刻意不動知識庫
- FR-11：主動新增知識——`is_owner` 決定可寫入共用或僅個人知識庫，`【REQUEST_SAVE】`標記進入反問確認，伺服器端強制覆蓋 `category`
- FR-12：`/clean-target-dialog`——依主題撈候選、LLM 判斷相關性、確認後對話紀錄軟刪除＋知識庫硬刪除

**非功能性需求**
- NFR-1：範圍界線——本階段不做外部 API 重試/降級
- NFR-2：安全——查詢一律帶 `user_id` 條件
- NFR-3/NFR-4：成本——對話視窗固定 10 則、摘要 backlog 累積到門檻才觸發

**實作階段**
- Phase 1 Step 1.3／1.3a：全數完成，全專案測試隨版本推進累積（見 PROGRESS.md）

### 個資偵測與遮蔽機制

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/privacy-masking.md`
**來源說明**：原記錄於 privacy-masking 規格，已於 2026-08-13 併入本文件（原 robinson spec ADR-5 個資部分已併入本討論紀錄）。

**概要**：使用者傳送的文字（打字或語音轉出文字）如含台灣常見個資格式，在寫入 log 或送外部 API 之前一律先遮蔽，並提醒使用者到 Telegram 對話中自行刪除原始訊息。採「Regex 硬規則＋LLM 語意辨識」雙層防線。

**功能性需求**
- FR-1：`mask_regex()`——涵蓋 8 類台灣個資格式（身分證/手機/市話/銀行帳戶/信用卡/健保卡/地址/車牌），統一替換為 `[已遮蔽個資]`
- FR-2：`mask_with_llm()`——補足 Regex 抓不到的變形寫法，排除生日與 LINE ID
- FR-3：`mask_text()` 統一入口，先跑 Regex 再跑 LLM
- FR-4：一般聊天在組 Prompt、寫入對話紀錄前先遮蔽，`detected=True` 附加提醒文案
- FR-5：圖片說明文字同樣先過 `mask_text()`
- FR-6：語音轉出文字天然涵蓋（統一經過 `handle_message()`）
- FR-7（刻意排除）：`/clean-target-dialog` 的 `topic` 不套用遮蔽（否則刪除功能失效）；通關密碼、編號選擇等純控制流程文字同樣不套用

**非功能性需求**
- NFR-1：額度隔離——語意層用獨立 `GEMINI_API_PRIVACY_KEY`
- NFR-2：不誤傷——生日/LINE ID 一律不遮蔽

**實作階段**
- Phase 1 Step 1.5：全數完成，326 個測試全過、覆蓋率 100%

### 語音訊息安全機制

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/voice-safety.md`（最終執行確認 FR-16a 的討論紀錄見 `docs/ADR/discuss/chat-core.md` ADR-9）
**來源說明**：原記錄於 robinson 母 spec 的 FR-14／FR-15／FR-16／FR-16a／FR-18，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：語音轉文字若無限制易消耗大量 Token，且個資風險需要主動防護。本區塊涵蓋語音時長上限、修正窗口限制、高風險操作的語音最終確認排除。

**功能性需求**
- FR-14：語音超過 10 分鐘強制中斷處理並提醒（用 Telegram 訊息本身的 `duration` 秒數判斷，不需先下載）
  - 規則 1：單次語音本身超過 10 分鐘時，語音功能整體鎖定 15 分鐘（獨立於 FR-15）
- FR-15：語音轉文字結果如需修正，僅能用打字編輯；語音送出後 15 分鐘內用語音修正一律拒絕，超過 15 分鐘恢復；成功轉出文字後主動附註提醒
- FR-16／FR-16a：涉及刪除/寫入資料庫的高風險操作（`/clean-all-dialog`、`/clean-target-dialog`、主動記知識），語意確認 CONFIRM 後仍需「打字逐字輸入『確認執行』」才真正動作；語音一律視為未通過且不清除狀態；卡在最終確認狀態時收到新語音，在下載/轉錄前先短路拒絕，不浪費 Drive/Groq 額度
- FR-18：不接受用於錄製會議或長篇演講的長語音

**非功能性需求**
- NFR-7：Token 節流——語音上限 10 分鐘

**實作階段**
- Phase 1 Step 1.4（FR-14/FR-15，2026-08-01～08-02 完成）、Step 1.3（FR-16a，2026-08-02 完成，見 chat-core ADR-9）

### 影像辨識

**狀態**：active
**討論紀錄**：無獨立 ADR；上傳/壓縮/命名/入庫流程設計見 `docs/ADR/discuss/submodules-core.md`（2026-07-31 條目）
**來源說明**：原記錄於 robinson 母 spec 的 FR-17／FR-17a～c，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：開放接受一般圖片供 Robinson 辨識（不限證照題目），僅支援圖片與音檔兩種檔案類型，其餘格式明確告知無法處理。

**功能性需求**
- FR-17：圖片先上傳 Google Drive、`Pillow` 壓縮至 1024×1024 內／JPEG 80%、影像雙 Key 隨機辨識；非圖片/音檔格式回覆「這個檔案格式我沒辦法處理喔」
  - FR-17a：上傳前提示個資影像警語
  - FR-17b：不確定內容須詢問使用者（`[NEED_CONFIRM]` 標記慣例，`pending_image_confirm` 流程接住澄清後重新分析）
  - FR-17c：飲食分析誤差聲明——只要是飲食成分分析一律告知存在誤差

**實作階段**
- Phase 1 Step 1.3b：全數完成，179 個測試全過、覆蓋率 100%

### Submodules 共用子模組基礎骨架

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/submodules-core.md`
**來源說明**：原記錄於 submodules-core 規格，已於 2026-08-13 併入本文件（原 robinson spec ADR-2、ADR-12、ADR-13 已併入本討論紀錄）。

**概要**：`submodules/` 收斂 Robinson 都會用到的最基礎技術操作，一律不依賴特定框架與本專案商業邏輯。每個子模組資料夾固定四檔案結構（`client.py`／`README.md`／`requirements.txt`／`.env.example`）。

**功能性需求**（依子模組列出核心能力，詳細方法簽章見程式碼與 `README.md`）
- `cloudsql`：連線池管理與泛用 CRUD（select/insert/update/delete），一律參數化查詢
- `telegram`：Bot HTTP Client（文字/圖片/typing 狀態），純文字傳送（不預設 Markdown）
- `llm`：文字/圖文生成呼叫，本地端節流保護（同一 `api_key` 60 秒超過 8 次直接擋下）
- `voice`：語音轉文字（Groq Whisper REST API），支援逐句時間軸切割
- `gdrive`：OAuth 2.0 上傳/列表/下載，`Pillow` 壓縮流程
- `email`：`smtplib`/`imaplib` 寄信/讀信（備援通知＋TLDR 電子報）
- `calendar`：Google Calendar 事件建立/更新/刪除，獨立憑證
- `retry`：`call_with_retry()` 共用重試迴圈（只重試暫時性錯誤，是子模組互相獨立原則的刻意例外）
- `newsfeed`：RSS Feed 抓取＋全文擷取

**非功能性需求**
- NFR-1：安全——CRUD wrapper 參數化查詢，`delete()`/`update()` 禁止無 `where` 整表操作
- NFR-2：可移植性——每個子模組自帶 `requirements.txt`
- NFR-3：免費方案友善——DB 連線池上限低
- NFR-4：一致性——統一 class 包 Client 的寫法

**實作階段**
- Phase 0 Step 0.1a 起始，隨各 Phase 陸續擴充（見 PROGRESS.md），958 個測試全過（含 2026-08-08 修復 `execute()` 對含 `%` 字元 SQL 的 `IndexError` 生產事故）

### 羅賓森 Mobile App（全功能個人化入口）

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/mobile-app.md`
**來源說明**：原記錄於 mobile-app 規格，已於 2026-08-13 併入本文件（原 robinson spec ADR-14、ADR-28 已併入本討論紀錄）。

**概要**：App 定位「分析頁面＋個人資訊／APP 設定＋生活紀錄」的視覺化入口，取代原規劃的 Notion 後台與唯讀 BI Dashboard。目標、功能開關與排程仍由既有 Telegram 流程處理。細節規劃（首頁卡片、各模組頁面呈現、全域 UX 規則、視覺風格）見 `docs/reference/mobile-app-ux.md`，本區塊僅列架構層決策摘要。登入/選單/個人資訊/APP設定/唯讀分析/體態飲食記錄已於 2026-08-12 正式上線部署（後端 Render＋前端 Vercel），完整路由清單見 `docs/reference/api_schema.md`「羅賓森 Mobile App」區塊。

**功能性需求**
- FR-64：分析頁面（記帳、體態等模組圖表）＋生活紀錄與 APP 設定；寫入一律複用既有 service 層函式——已實作
- FR-64a：藍牙體重計整合已全面移除（見上方技術棧「決定不用」），改為手動輸入按鈕「記錄一下」——已實作
- FR-65：帳密登入（使用者ID＋密碼），密碼單向雜湊（bcrypt/argon2），忘記密碼＝重設新密碼透過 Telegram 發送，保持登入 Refresh Token 30 天效期——已實作
- FR-67：左上選單導覽＋右上頭像下拉選單，權限矩陣依 `owner_only` 決定可見項目——已實作
- FR-68：個人基本資訊頁面（唯讀）——已實作
- FR-72：APP設定（深色模式／字體大小／隱私數字遮罩／修改密碼）——已實作

**FR-64 生活紀錄輸入擴充（2026-08-14 定案）**

- 運動紀錄提供「時間／熱量」頁籤。時間模式維持活動、持續時間與選填心率，由 AI 估算消耗熱量；選擇重訓時另要求「強度與組數」，AI 估算必須參考此內容。熱量模式只要求活動與人工消耗熱量，不呼叫 AI；熱量限制 `1～5,000` 大卡並採一般四捨五入至整數。
- 飲食紀錄先提供選填飲水量，再提供「文字／照片」頁籤。飲水量有填時限制 `1～10,000` 毫升整數；飲食內容一律必填。
- 文字模式由使用者選擇 AI 計算或人工輸入。人工模式的脂肪、碳水化合物、蛋白質與熱量全部必填；三大營養素各限制 `0～1,000.0` 公克並保留小數點後一位，允許 `0`；熱量限制 `1～10,000` 大卡並四捨五入至整數。不強制核對三大營養素換算熱量，只保存使用者確認值。
- 照片模式固定流程為「拍照／相簿 → AI 辨識食物名稱與份量 → 使用者編輯、補充並確認 → 選擇 AI 計算或人工輸入 → 二次確認 → 儲存」。辨識失敗時保留當次視窗內的照片，可重試或切換文字；關閉視窗、離開頁面或重新整理後清除，不做跨頁持久化。
- 完全採用 AI 營養／熱量結果時，資料來源記為 AI；只要使用者修改任一 AI 數值，或直接選擇人工輸入，整筆來源改記人工。既有飲食／運動資料按既有語意回填為 AI；既有運動輸入模式回填為時間。
- 飲食五大成分與運動趨勢依來源拆成兩組資料：人工輸入用實心圓，AI 估算用空心圓；同一天同時存在兩種來源時保留兩個點／兩條資料，Tooltip 顯示人工、AI 與合計值。
- 六種心情分類統一顯示 Emoji：😡 生氣／焦慮、😢 難過／低落、🫠 疲憊／厭世、🙂 普通／平淡、😌 平靜／放鬆、🥳 高興／興奮；套用首頁、心情紀錄視窗、心情分析頁及今日紀錄管理，本次不異動 Telegram。
- 所有首頁紀錄視窗底部的取消、清除、確認按鈕固定同列等寬彈性排列，縮小水平內距與間距，手機窄螢幕不得換行或溢出。
- 上述數值限制必須由 Mobile 表單與後端 Service／API 雙層驗證；超出範圍時禁止儲存並顯示對應欄位錯誤，不得只依賴前端防呆。

**實作階段**
- Phase 4 Step 4.1～4.3（求職模組）：全數完成
- Phase 4 Step 4.4／4.5（App 本體）：FR-64／FR-64a／FR-65／FR-67／FR-68／FR-72 已完成並於 2026-08-12 正式上線部署（後端 Render＋前端 Vercel）

### Mobile App 生活探索與成果

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/mobile-app.md` 2026-08-12～2026-08-14「收藏清單／旅遊行程／探索地圖／成果展示」系列條目

**概要**：以「收藏候選 → 組成行程 → 確認造訪 → 地圖回顧」串接收藏清單、旅遊行程與探索地圖；成果展示則提供手動新增與系統候選確認兩種來源。四項功能皆為個人資料，不受 Mobile App 僅能異動今日資料的限制；第一階段不做家庭共同編輯、多幣別換算或逐日逐時旅遊排程。

**功能性需求**
- FR-73 收藏清單：記錄想去地點或想執行活動；保留名稱、類型、國家、區域／城市、地址、參考網址、預估費用與備註，移除優先程度、縣市與想去日期。名稱、類型、國家及區域／城市必填；地點類收藏地址必填，非地點活動可不填地址且不進探索地圖。狀態依行程關聯與造訪紀錄自動推導；同一收藏可加入多個行程。收藏支援編輯、刪除、二次確認、5 秒復原與防連點；已有探索歷史時刪除原收藏仍保留歷史快照。
- FR-74 旅遊行程：由收藏組成當天或幾天幾夜的輕量行程，不提供第幾天、幾點去哪裡的細部排程。保存行程名稱、選填起訖日期、國家、區域／城市、收藏項目及顯示順序、預估支出與備註；規劃中可不填日期，確認或完成前必填。狀態依操作流轉為規劃中、已確認、已完成、已取消；完成時由使用者勾選實際造訪項目，未勾選收藏繼續保留。
- FR-74a 行程記帳整合：預估支出支援交通、住宿、飲食、門票、購物與其他分類，也允許只填總額；全部使用新台幣。實際支出仍以既有記帳為唯一來源，記帳可選填關聯行程且不限制交易日期；行程彙總預估、實際、差額及各記帳類別。取消行程不刪除收藏或記帳，保留支出關聯與取消標示。
- FR-75 探索地圖：不提供獨立新增入口，探索紀錄只能由收藏標記已造訪或完成行程時產生。依國家及區域／城市篩選；同一地點只顯示一個 Leaflet／OpenStreetMap 標記，點開列出各次獨立造訪。每次造訪保存名稱、類型、國家、區域／城市、地址、經緯度、備註、造訪日期及行程快照，可個別編輯或刪除。定位失敗仍可保存並列入「無法定位」，修正地址後才能重新定位，系統不得猜測座標。
- FR-76 成果展示：首頁提供手動新增成果與待確認成果提示；系統只能根據體態達標、考試達標、運動累積、探索地點／國家數、行程完成及待辦里程碑提出候選，使用者確認後才建立，拒絕後不重複提示相同成果，不以飲食或心情自動判斷。成果必填名稱、完成日期及類別，選填說明、照片及關聯紀錄，保存 `manual`／`suggested` 來源。成果支援刪除、二次確認、5 秒復原與防連點，刪除成果不影響原始紀錄。
- FR-76a 導覽入口：首頁收藏清單提供「新增收藏」；旅遊行程從收藏清單進入建立／管理；探索地圖只提供查看；成果展示提供「新增成果」與待確認提示。左側選單保留收藏清單、探索地圖與成果展示，作為查看、篩選與分析入口。

**非功能性需求**
- NFR-14：資料隔離 — 收藏、行程、探索與成果皆依 `user_id` 隔離，使用者只能管理自己的資料，Robin 不代改家人資料。
- NFR-15：地圖合規 — Leaflet 地圖必須顯示 OpenStreetMap 著作權；若使用 Nominatim，只能由使用者明確觸發搜尋，不做即時自動完成，全應用每秒最多一次並快取結果。
- NFR-16：歷史完整性 — 探索快照、實際記帳與產生成果的原始紀錄，不得因刪除收藏、行程或成果卡片而被連帶刪除。

**實作階段**
- Phase 5 Step 5.1：修正新增收藏 Modal 手機版跑版，依 FR-73 精簡收藏欄位並校正既有 Schema／API／UI／測試。
- Phase 5 Step 5.2：完成 FR-74／FR-74a 旅遊行程、收藏關聯、預估支出與記帳整合。
- Phase 5 Step 5.3：完成 FR-75 造訪確認、探索快照、地圖聚合及定位失敗處理。
- Phase 5 Step 5.4：完成 FR-76／FR-76a 手動成果、成果候選、刪除復原與首頁／選單入口。
- Phase 5 Step 5.5：整合測試、Mobile 實機窄螢幕驗收、文件與部署驗證。

### 服務健康與治理

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/service-resilience.md`（重試機制／Email 備援子模組實作細節見 `docs/ADR/discuss/submodules-core.md` ADR-11／ADR-13）
**來源說明**：原記錄於 robinson 母 spec 的 FR-19～FR-21，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：服務發生例外或錯誤時，對外一律回覆「生病了」等安全用語，不揭露技術細節；Robin 則透過私訊＋Google Drive log 連結取得完整診斷資訊。依「LLM 是否還能正常推送訊息」分兩級降級。原規劃的 AI 自主診斷＋GitHub PR 自動化機制已取消（見討論紀錄）。

**功能性需求**
- FR-19a：捕獲異常與 Log，私訊 Robin 完整 Traceback＋觸發功能＋使用者輸入摘要；空回覆同樣視為需要防呆的情境（`_EMPTY_REPLY_FALLBACK`）
- FR-19b：完整錯誤 log 上傳 Google Drive＋私訊 Robin 專屬連結（其他使用者行為完全不變，只收到「生病了」）
- FR-19f：一般感冒級——LLM 正常、其他元件異常，私訊完整錯誤詳情給 Robin，使用者收到固定感冒語句
- FR-19g：重大疾病級——LLM 本身崩潰，完全繞過 LLM，寫死範本廣播 Robin 最高等級告警＋所有家人
- FR-19h：決策執行狀態閉環回饋——所有涉及資料異動的操作，成功/失敗都必須明確回覆結果（架構層級已滿足，各功能模組無 `except` 包住 DB 寫入呼叫）
- FR-19i：外部 API 呼叫重試機制（Max 3 次＋Exponential Backoff 1/2/4 秒），實作見 submodules-core `retry` 子模組
- FR-19j：系統錯誤記錄持久化＋解法追蹤（`system_error_reports` 表），Telegram「錯誤ID=N 已處理：{解法}」指令，App 客訴回饋頁共用同一支 service 函式
- FR-20：問題修復後 Owner 專屬 `/recovered` 指令廣播「我康復了」（Phase 1 範圍：完全由 Robin 自己判斷是否已修好）
- FR-21：Neon 容量監控（達 80% 告警，借用 `/healthz` 頻率）；Gemini 免費額度用量監控刻意暫緩（官方無查詢即時用量的 API）

**非功能性需求**
- NFR-6：可維護性——錯誤訊息一律去技術化
- NFR-8：安全——Robinson 對正式環境程式碼不具備任何自動修改或部署能力
- NFR-9：韌性——所有外部 API 呼叫具備重試機制
- NFR-10：一致性——所有寫入類操作不允許靜默失敗

**實作階段**
- Phase 1 Step 1.6（基礎捕獲+Log+通知）、Phase 2 Step 2.4～2.6（log 雲端連結、重試機制、分級降級）全數完成；Step 2.4 曾規劃 AI 自主診斷＋GitHub PR 自動化並記錄於 ADR-7，後於 Step 2.4 開工前正式取消（見討論紀錄）

### 客訴收集

**狀態**：active
**討論紀錄**：無獨立 ADR，設計理由已於下方需求段落內註明
**來源說明**：原記錄於 robinson 母 spec 的 FR-60～FR-63，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：使用者輸入「我要客訴你」或 `/complaint` 觸發固定提問，下一則訊息視為客訴內容，記錄後立即呼叫 Gemini 分析並私訊 Robin（刻意的隱私例外，不涉及一般對話隔離規則，因為客訴的本質就是使用者主動想讓 Robin 知道）。此功能為固定入口，不受「功能開關系統」管轄（不會出現在 `/my_toggles`／`/set_toggle` 清單裡，也不寫入 `feature_toggles`，永遠開放）。

**功能性需求**
- FR-60：`/complaint` 固定提問，不經 LLM
- FR-61：客訴內容寫入資料庫（含 FR-13 個資遮蔽）
- FR-62：立即呼叫 Gemini 分析「可能問題點」與「修正建議」私訊 Robin；分析/私訊失敗只記 log，不影響客訴已成功記錄
- FR-63：人工決策，不涉及程式碼

**實作階段**
- Phase 1 Step 1.9：全數完成，417 個測試全過、覆蓋率 100%

### 待辦事項

**狀態**：active
**討論紀錄**：無獨立 ADR，設計決策已於下方需求段落內註明
**來源說明**：原記錄於 robinson 母 spec 的 FR-31／FR-31a／FR-31b／FR-32，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：使用者以自然語言描述「什麼時候要做什麼事」，Robinson 三輪反問（要不要記錄→什麼時候→要不要提前提醒）後記錄，支援單一時間點與時間區間兩種形式，並可選擇同步到 Google 行事曆。

**功能性需求**
- FR-31：自然語言新增，模組歸屬歧義需反問（跨模組歧義判斷 Phase 1 暫不實作，待其他模組上線後回頭補上）
- FR-31a：逾期自動標記 `expired`；完成/取消由查詢清單選定編號後 LLM 判斷標記
- FR-31b：支援時間區間（`start_at` 可選欄位），前 30 分鐘提醒以區間起點為基準，每日摘要在開始日/結束日各出現一次
- FR-32：主動查詢（`/my_todos`）、每日 08:00 固定推播、前 30 分鐘提醒（借用 `/healthz` 頻率，去重狀態存在資料列本身）

**實作階段**
- Phase 1 Step 1.7：全數完成，391 個測試全過、覆蓋率 100%；Google Calendar 同步見下方獨立區塊

### 記帳

**狀態**：active
**討論紀錄**：無獨立 ADR，設計決策已於下方需求段落內註明
**來源說明**：原記錄於 robinson 母 spec 的 FR-41～FR-44a，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：每月支出預算上限（非儲蓄目標）＋每日記帳（含補登/修正/刪除完整 CRUD）＋門檻預警＋月報推播。

**功能性需求**
- FR-41／FR-41a：`/set_budget` 設定全局預設；`budget_overrides` 支援特殊月份覆蓋，改動已有值時先反問確認
- FR-42：`/add_transaction`／`/backfill_transaction`／`/my_transactions` 完整 CRUD；備註套用個資遮蔽
- FR-43：50% 門檻只在每月 15 日前檢查、80% 門檻整月都檢查，各自每月最多推播一次
- FR-44：`/my_finance_summary` 文字摘要（本月支出/收入、預算使用率、分類佔比、跟上月比較）
- FR-44a：月底 21:00 自動推播月報（僅推給有生效預算或當月有交易的使用者）
- FR-42a：每日 23:00 記帳提醒（有預算且今天未記錄支出才推播）

**實作階段**
- Phase 2 Step 2.1：全數完成，539 個測試全過、覆蓋率 100%

### 體態管理

**狀態**：active
**討論紀錄**：無獨立 ADR，設計決策已於下方需求段落內註明
**來源說明**：原記錄於 robinson 母 spec 的 FR-45～FR-48，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：身高/體重/腰圍（基準值）、運動、飲食三個子功能共用 `body_goals` 表，各自完整 CRUD 與預警。

**功能性需求**
- FR-45：三種預警——目標達成通知、目標期限前 7 天提醒、BMI 異常提醒
- FR-46：`/set_height`、`/log_weight`／`/backfill_weight`／`/my_weight_logs`（合理範圍檢查，超出原地反問）；`/set_waist`（2026-08-08 新增，40～200 公分，僅記錄首次體重時順便詢問一次）
- FR-47：`/log_exercise`（卡路里 LLM 估算，非 MET 公式）
- FR-48：`/log_diet`（三大營養素 LLM 拆算，附誤差聲明；飲食目標不做自動達成判斷，只能手動取消）

**實作階段**
- Phase 2 Step 2.2：全數完成，661 個測試全過；`src/bot/body.py` 覆蓋率 100%；2026-08-08 腰圍擴充新增 1009 個測試

### 心情小記

**狀態**：active
**討論紀錄**：無獨立 ADR，設計決策已於下方需求段落內註明
**來源說明**：原記錄於 robinson 母 spec 的 FR-49／FR-50，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：心情分類（固定 6 選一）→ 日記內容 → 個人成就三選一提示（可跳過），全程純字串比對不需 LLM。

**功能性需求**
- FR-49：`/mood_journal` 觸發三輪流程；日記內容套用個資遮蔽；`/backfill_mood`（補記過去日期）、`/my_mood_journals`（列表後更新/刪除，刪除採簡單一輪 CONFIRM/CANCEL，不套用 FR-16a）
- FR-50：個人成就三選一提示，可跳過不強迫回答

**實作階段**
- Phase 1 Step 1.8：全數完成，409 個測試全過、覆蓋率 100%；2026-08-02 補記/更新/刪除擴充後 465 個測試全過

### 好友模式

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/friend-mode.md`
**來源說明**：原記錄於 robinson 母 spec 的 FR-51／FR-52，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：使用者主動觸發「陪我聊聊」，Robinson 動態讀取該使用者已開啟且近期（7 天）有資料的所有功能模組，生成陪伴式對話回覆，自然涵蓋心情趨勢文字摘要。僅被動模式，不含主動關懷推播。

**功能性需求**
- FR-51：心情趨勢改文字/emoji 摘要，不做圖片圖表（併入 FR-52 回覆呈現，不獨立成查詢指令）
- FR-52：「陪我聊聊」／`/friend_chat`，`_DATA_PROVIDERS` 登記表涵蓋心情/待辦/體態/記帳/證照準備等既有模組的近期查詢

**實作階段**
- Phase 3 Step 3.5：全數完成，新增 32 個測試，`friend_chat.py` 100% 覆蓋率，全專案 1294 個測試全過

### 重要通知

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/notifications.md`
**來源說明**：原記錄於 robinson 母 spec 的 FR-53／FR-53f，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：固定節日與家人生日於台灣時間 08:00 自動推播。生日/父親節/母親節全員皆收到，依身份給不同文案；掃墓提醒限固定名單（Robin/爸爸/媽媽/弟弟/弟媳/阿姨）。

**功能性需求**
- FR-53：固定節日清單（元旦、除夕/初一、掃墓、中秋、端午、父親節、母親節）＋家人生日比對；農曆節日用 `lunarcalendar` 即時計算；年度推播去重靠 `important_notifications_log`
- FR-53f：主角/其他人文案差異化，掃墓收件對象改為固定名單

**實作階段**
- Phase 2 Step 2.3：全數完成，703 個測試全過，`notifications.py` 覆蓋率 100%；FR-53f 邏輯修正（2026-08-09）程式碼調整留待獨立 Step 展開

### Google Calendar 整合

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/google-calendar.md`
**來源說明**：原記錄於 robinson 母 spec 的 FR-66，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：建立獨立「Robinson 家庭行事曆」，僅 Robin OAuth 授權寫入，家人訂閱唯讀瀏覽。待辦事項、重要通知、體態目標期限單向同步寫入。

**功能性需求**
- FR-66a：待辦事項同步——建立流程新增一題「要不要同步」，每次明確詢問不預設；MVP 不支援事後補同步
- FR-66b：重要通知同步——固定節日/生日全自動同步全天事件，不逐筆詢問
- FR-66c：體態目標期限同步——比照待辦事項逐筆詢問
- FR-66d（明確排除）：讀取行事曆做空檔查詢，非本次範圍

**實作階段**
- Phase 2 Step 2.7：全數完成，758 個測試全過，`submodules/calendar/client.py`／`body.py`／`notifications.py` 覆蓋率 100%

### 個人技能成長：每日技術分享與 TOEIC 證照題庫（僅 Robin 可用）

**狀態**：active（`language` 語言學習子開關暫時擱置，見下方討論紀錄）
**討論紀錄**：`docs/ADR/discuss/skill-growth.md`
**來源說明**：原記錄於 robinson 母 spec 的 FR-22～FR-30，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：①每日技術分享——固定 23:00 收集 TLDR 電子報＋IThome／TechCrunch 當天新聞，各自獨立 Gemini 深入摘要，隔天 08:00 拆成三則獨立訊息推播 ②TOEIC 雙軌題庫——軌道一 Robin 拍照/音檔上傳建題庫，軌道二 Gemini 即時生成單字題；每日 08:00 推播出題、20:00 提醒、彈性排程調整；正解改用 Robin 拍照上傳的答案照，不用 AI 推論。

**功能性需求**
- FR-22／FR-23：`tech_intel` 開關；`skill_growth_digests` 一天最多三筆（一筆一來源），任一來源失敗只記 log；三個來源皆無內容才推播固定訊息
- FR-24：`certificate` 開關；`/set_certificate_goal`／`/my_certificate_goals`／`/certificate_advice`（依近 30 天成效與目標生成客製化建議）
- FR-25：TOEIC 每次出題 1 聽力+2 填空+3 單字；軌道一檔名格式泛用化為 `{exam_type}_{test_id}_write/listen_{題號}.{ext}`；軌道二單字題即時生成入庫
- FR-26：每日出題數量/比例（TOEIC 額外三軌比例）、新題:複習題 7:3，彈性排程支援挪動/取消/區間覆蓋/平攤四種語意（平攤需提案確認才寫入）
- FR-27：作答只接受 A/B/C/D；正解來自 Robin 拍照上傳的 `_ans` 答案照
- FR-28：20:00 提醒、23:00 靜默視為跳過
- FR-29：`/my_quiz_stats` 彈性自然語言問答（不做圖表），排除未作答日子並支援跨區間比較
- FR-30：`/log_exam_score`／`/my_exam_scores`（正式成績獨立建表，僅查詢不修改）

**實作階段**
- Phase 3 Step 3.1（每日技術分享）、Step 3.2（TOEIC 建題庫）、Step 3.3（推播/作答/成效/正式成績）全數完成，Phase 3 主線於 1185 個測試時全過
- `language`（語言學習）功能開關已建立但暫時擱置，不排入目前 Roadmap，見討論紀錄

### YouTube 技術情報模組（個人技能成長子功能，僅 Robin 可用）

**狀態**：active（共用 `tech_intel` 開關）
**討論紀錄**：`docs/ADR/discuss/youtube-intel.md`
**來源說明**：原記錄於 robinson 母 spec 的 FR-57～FR-59，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：依多組主題設定，用 YouTube Data API 取得候選影片，LLM 判讀標題/說明欄/統計數字決定排序，每週四固定推播 Top 3，多主題採「保底＋輪替」公平曝光機制。

**功能性需求**
- FR-57／FR-57a：多主題設定（`youtube_topics`），`search.list`＋`videos.list` 補統計數字
- FR-58：LLM 語意判讀取代 Rule-based Weight；1 組主題全出自該組，2 組各保底 1、3 組以上優先選最久未推播的 3 組；30 天內已推播 `video_id` 過濾
- FR-59：每週四 08:00 排程；配額估算遠低於每日上限；失敗走重試＋一般感冒級分級降級

**實作階段**
- Phase 3 Step 3.4：全數完成

### 求職模組（僅 Robin 可用）

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/job-search.md`
**來源說明**：原記錄於 robinson 母 spec 的 FR-33～FR-40c，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：每週爬取 104 職缺（直呼 AJAX API，非瀏覽器自動化）、公司背景採 Email＋CSV＋Drive 人力協作、Gemini 批次契合度評分與技能缺口分析、應徵成效追蹤（含 LinkedIn/Cake 等外部管道職缺）。

**功能性需求**
- FR-33／FR-34：多組搜尋條件；兩階段爬取（列表→詳情頁）；2～4 秒隨機延遲禁併發；ETL 去重（`upsert_job_posting()`）；`is_closed` 依 104 API 欄位自動判斷
- FR-35：公司背景 Email 協作機制（CSV 寄送→Robin 查填→上傳回填）
- FR-36：履歷/期望工作內容收集（含結構化年資、期望薪資），與搜尋條件同一輪對話
- FR-37：Gemini 批次契合度評分，僅計算公司背景已回填的職缺
- FR-38：技能缺口分析以 104 職缺 ID 為單位；雙重排名（全庫／本週新職缺）；Excel 三工作表寄送，Robin 標記喜好後回填 `is_unliked`
- FR-39：應徵狀態 Telegram 語句記錄（任意狀態可直接設定，含「未錄取/已婉拒」）；獨立歷程表；`/my_applications` 查詢
- FR-40：外部管道職缺共用同一張表（`source` 欄位區分），合成識別碼，一起參與每週評分排名

**實作階段**
- Phase 4 Step 4.1～4.3：全數完成

### 平台架構與治理（系統架構總覽／MVP 分期／Schema 治理）

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/robinson.md`
**來源說明**：原記錄於 robinson 母 spec，已於 2026-08-13 併入本文件（系統架構總覽、名詞定義、重要資產、ADR-1、ADR-4、ADR-10、ADR-11）。

**概要**：Robinson 採三層式架構（Telegram 對話前台／Neon+GDrive 資料層／Mobile App 分析、設定與生活紀錄前台），MVP 依複雜度分 Phase 0～4 逐步交付，資料庫 Schema 一律「先審核後執行」並透過 Migration 檔案自動套用。

**名詞定義**：Owner（Robin，唯一免通關密碼者）／使用者（家人，需通關密碼）／通關密碼（一次性，`is_used=1` 後失效）／功能開關（全關時退化為純聊天 Bot）／知識庫（4 類：通用背景/通用故事/使用者客製/使用者對話紀錄）。

**重要資產（不可刪除）**：`docs/profile/Robinson.png`（Robinson 大頭照，任何清理/重構操作都必須明確排除此路徑）。

**功能性需求**
- FR-1／FR-3／FR-4：Telegram Bot 接收文字/語音；`/healthz` 極簡端點供 cron-job 每 10 分鐘呼叫（**2026-08-08 修正**：10 個排程檢查改丟背景 daemon thread 執行，避免逾時被 cron-job.org 判定失敗）；AI 統一走 Gemini `gemini-3.5-flash-lite`
- FR-9～FR-12：知識庫四類架構與資安隔離（詳細行為見「Gemini 對話核心」區塊）

**非功能性需求**
- NFR-1：成本——所有服務一律免費方案
- NFR-2：可用性——Render 15 分鐘無請求休眠，cron-job 保持喚醒
- NFR-3：容量——Neon 免費額度 0.5GB，圖片一律存 GDrive
- NFR-11：資料品質——任何排程自動收集外部資料的功能都須落實 ETL 去重（技術新聞、TOEIC、104 職缺、YouTube 皆適用）
- NFR-12：文件治理——`src/schema/db_schema.md`／`api_schema.md` 隨開發進度更新，建表 SQL 先審核後執行
- NFR-13：合規——僅供 Robin 與家人個人非商業使用

**實作階段**
- Phase 0：專案基礎建設，全數完成
- Phase 1（MVP）：核心平台＋待辦事項＋心情小記，全數完成
- Phase 2：記帳＋體態管理＋重要通知＋系統韌性，全數完成
- Phase 3：個人技能成長＋好友模式，全數完成
- Phase 4：求職模組與 Mobile App Step 4.4／4.5 全數完成；Mobile App 已於 2026-08-12 正式部署，2026-08-14 完成飲食／運動雙輸入模式、AI／人工來源圖例與心情 Emoji 擴充
- Phase 5：Mobile App 生活探索與成果（FR-73～FR-76a）已定案並排入開發

## 例外處理與邊界條件

| 情境 | 防呆機制 | Error Handling |
| --- | --- | --- |
| 通關密碼重複使用/race condition | 原子性條件 UPDATE（`WHERE is_used=FALSE`） | 第二個並行請求影響 0 筆，非誤判成功 |
| 非 Robin 觸發 Owner 專屬指令 | `auth.is_owner()` 嚴格比對 `telegram_user_id` | 一律無效且不透露此指令存在 |
| 個資輸入 | Regex + LLM 雙層偵測 | 一律遮蔽為 `[已遮蔽個資]`，附提醒文案；語意層失敗優雅降級為僅 Regex 層 |
| 語音超過 10 分鐘 | `duration` 秒數預檢查，不需先下載 | 拒絕處理並整體鎖定語音功能 15 分鐘 |
| 語音誤聽導致高風險操作誤執行 | FR-16a 逐字打字最終確認關卡 | 語音一律視為未通過，且不清除待確認狀態 |
| Gemini/Telegram 等外部 API 暫時性失敗 | `submodules/retry` 最多重試 3 次＋Exponential Backoff | 重試耗盡才判定失敗，依 LLM 是否為故障源分兩級（一般感冒級／重大疾病級） |
| Telegram 送達失敗（含 Telegram 本身故障） | 兩段式 try/except，Telegram 失敗才觸發 Email 備援 | Email 也失敗則只記 log，不再疊加第三層備援 |
| `handle_message()` 回傳空字串 | 獨立空字串防呆判斷 | 換成 `_EMPTY_REPLY_FALLBACK`，避免已讀不回 |
| LLM 本身完全失敗（額度用盡/Key 失效） | `_is_llm_failure()` 例外型別判斷 | 完全繞過 LLM，寫死範本廣播 Robin＋所有家人 |
| 資料異動寫入失敗 | 無 `except` 包住 DB 寫入呼叫，例外一路傳到單一進入點 | 被分級降級邏輯接住，絕不靜默 |
| 通關密碼設定流程重啟中斷 | 狀態存記憶體，刻意簡化 | Robin 重新輸入 `/set_invite_codes` 即可，不影響資料正確性 |
| Neon 容量接近上限 | `NeonCapacityMonitor` 借用 `/healthz` 頻率 | 達 80% 私訊 Robin 告警，回落後重置避免重複轟炸 |
| 影像/語音上傳需壓縮節省 Token | `Pillow` 強制縮放 1024×1024／JPEG 80% | 僅記憶體內即時處理，不落地存回 Drive |
| 104/YouTube 等外部資料重複爬取 | ETL 去重（唯一 ID/URL 比對，`UPDATE` 取代重複 `INSERT`） | 已存在則更新既有紀錄，避免資料庫膨脹 |
| IThome RSS `<pubDate>` 非標準格式 | `_parse_pub_date()` fallback 格式解析 | 解析失敗才真的視為無法解析（2026-08-09 修正 bug） |
| 語音修正窗口內用語音修正 | 查最近一筆 `media_uploads` 時間戳記判斷 | 拒絕並提醒改用打字，不延長窗口、不產生新記錄 |
| `/clean-target-dialog`／彈性排程「平攤」等自動運算的高影響操作 | 一律先呈現運算結果／候選範圍給使用者確認 | 任何無法判斷為確定的回覆一律視為取消，保守優先 |

## 驗收矩陣與已測試情境

| 情境 | 預期結果 | 實測結果 | 狀態 |
| --- | --- | --- | --- |
| 新使用者輸入正確通關密碼 | 綁定成功並收到附錄 A 歡迎訊息 | 符合預期 | 通過 |
| 重複使用同一組通關密碼 | 第二次應失敗 | 符合預期 | 通過 |
| 家人觸發 Owner 專屬指令（如 `/set_toggle`） | 權限邊界拒絕 | 符合預期 | 通過 |
| 使用者 A 查詢知識庫/對話紀錄 | 無法讀到使用者 B 的資料 | 符合預期（資安隔離） | 通過 |
| 身分證字號/手機號碼等 8 類個資格式輸入 | 正例遮蔽、生日/LINE ID 不誤判 | 符合預期 | 通過 |
| 語音 9:59／10:00／10:01 邊界 | 未超過放行，超過拒絕並鎖定 15 分鐘 | 符合預期 | 通過 |
| 語音修正窗口 14:59／15:00 邊界 | 窗口內拒絕、超過恢復 | 符合預期 | 通過 |
| 外部 API 前 2 次失敗、第 3 次成功 | 正常回傳，等待時間 1s/2s/4s | 符合預期 | 通過 |
| 外部 API 3 次全部失敗 | 正確拋出原始例外，不包裝新型別 | 符合預期 | 通過 |
| `/rule`／`/function`（MVP 版）觸發 | 不呼叫 LLM，回傳固定/總覽內容 | 符合預期 | 通過 |
| `/complaint` 觸發＋客訴內容記錄 | 資料庫寫入成功，Robin 收到分析報告（提出客訴者本人收不到） | 符合預期 | 通過 |
| 服務模擬「一般感冒級」錯誤 | 使用者收到感冒語句，Robin 收到完整錯誤詳情，未額外呼叫 LLM | 符合預期 | 通過 |
| 服務模擬「重大疾病級」錯誤 | 完全繞過 LLM，使用者與所有家人收到寫死廣播，Robin 收到最高等級告警 | 符合預期 | 通過 |
| Google Drive log 上傳失敗 | 使用者仍正常收到「生病了」，Robin 仍正常收到私訊（缺連結欄位） | 符合預期（優雅降級） | 通過 |
| 記帳/心情小記/體態新增後確認 | 成功時明確成功訊息，模擬 DB 逾時則收到感冒語句且未寫入 | 符合預期 | 通過 |
| 打字誤植（同音字）觸發 `【CONFIRM_NAME】` | 反問確認，確認/否認分別正確處理 | 符合預期 | 通過 |
| `pending_user_knowledge` 換問題/拒絕/提供答案 | 三選一正確分流，不誤判 | 符合預期（歷經多輪 bug 修正） | 通過 |
| FR-16a 高風險操作語音最終確認 | 語音一律拒絕且不清除狀態；打字「確認執行」才執行 | 符合預期 | 通過 |
| TOEIC 軌道一檔名比對＋整包 MP3 切割 | 正確整合題目、排除說明語音誤切 | 符合預期（經真實錄音實測修正） | 通過 |
| TOEIC 軌道二單字題生成 | 8 欄位齊全寫入，重複執行不重複生成 | 符合預期 | 通過 |
| 104 爬蟲分頁請求間隔 | 落在 2～4 秒，未使用瀏覽器自動化套件 | 符合預期 | 通過 |
| 每週四 YouTube 排程 | Robin 收到 Top 3 Markdown 連結，不重複 30 天內已推播 | 符合預期 | 通過 |
| Gemini 呼叫遇 429/404 等真實額度與世代下架問題 | 依序排查並正確判定根因（節流保護 vs 官方額度 vs 模型下架） | 符合預期（多次生產環境實測） | 通過 |
| CloudSQLClient 對含 `%` 字元 SQL 執行 | `params is None` 時不帶第二參數，避免誤觸格式化解析 | 符合預期（2026-08-08 生產事故修復） | 通過 |
