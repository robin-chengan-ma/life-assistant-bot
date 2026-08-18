---
title: Robinson — Robin 與家人們的生活小助手
updated: 2026-08-18
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
| Mobile 探索地圖 | Leaflet + OpenStreetMap | Leaflet 1.9.4 | 使用中 | Expo Web 顯示探索地圖、已具經緯度的造訪標記與同座標聚合；保留 OpenStreetMap 著作權署名，不採 Expo Maps |
| 地址轉座標／重新定位 | OpenStreetMap Nominatim | Search API | 已部署／實機驗收 | 後端代理明確觸發的地址搜尋與探索重新定位；具識別 User-Agent、全應用程序每秒最多一次及 PostgreSQL 快取，不提供即時自動完成 |
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

### 平台核心入口（通關密碼驗證／Owner 權限管理／使用規則選單）

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/platform-auth.md`、`docs/ADR/discuss/robinson.md`（2026-08-15 Telegram 重構子決策）
**來源說明**：原記錄於 platform-auth 規格，已於 2026-08-13 併入本文件（原 robinson spec ADR-3、ADR-8 已併入本討論紀錄，內容已被本區塊取代）。

**概要**：所有使用者第一次接觸 Bot 時用到的基礎機制：Telegram Webhook 入口、通關密碼驗證與綁定、Owner 專屬權限管理、綁定成功歡迎訊息，以及不經 LLM 的「使用規則」固定模板選單。功能探索統一由 Telegram 可見選單負責，不再提供 `/function` 功能總覽。

**功能性需求**
- FR-1：`POST /telegram/webhook` 依身分與內容路由到對應處理邏輯
- FR-2：`is_owner` 判斷——比對 `telegram_user_id` 是否等於 `ROBIN_TELEGRAM_TOKEN`
- FR-3：一般使用者在 Bot 私人聊天室點擊 `START` 後，下一則文字才進入通關密碼驗證；成功才綁定 Telegram 身分、令一次性密碼失效並顯示正式選單，失敗不得開啟任何功能。綁定前的圖片、語音、其他指令與多人群組驗證一律拒絕
- FR-4：Owner 專屬「權限管理」引導式流程建立一般使用者；系統先建立 `users` 取得主鍵，再產生唯一 6 位數一次性數字通關密碼，Mobile App 使用者 ID 依 `user` 加至少兩位數流水號組成。完成後固定回覆暱稱、使用者 ID、通關密碼及一次性使用提醒
- FR-4b：一次性通關密碼自建立起 24 小時有效，使用成功立即失效；同一綁定流程連續錯誤 5 次後暫時鎖定，須由 Owner 重發。除 Owner 建立完成的必要受控回覆外，訊息與 Log 不得顯示完整通關密碼
- FR-4c：通關密碼連續錯誤 5 次鎖定 30 分鐘，Owner 重發後舊密碼立即失效；已綁定使用者再次 `/start` 只重新顯示主選單。更換 Telegram 帳號須由 Owner 解除舊綁定後重新驗證
- FR-4d：權限管理提供停用／恢復使用者但不提供刪除帳號；停用時撤銷 Mobile Refresh Token 並阻止 Telegram／Mobile 存取，恢復後仍須重新登入或重新綁定
- FR-4a：使用者資料分開保存暱稱、家庭稱謂與授權身分；實際管理權限以 `is_owner` 判斷，Mobile App 顯示角色依其呈現「管理者／使用者」，不得以家庭稱謂承擔授權角色
- FR-5：「使用規則」選單回傳固定模板，不呼叫 LLM、不切換功能對話模式。2026-08-18 Robin 於對話中直接核准最終逐字版本（`src/bot/templates.py` `APPENDIX_A_TEXT`，見 `docs/ADR/discuss/robinson.md` 2026-08-18 條目），改為「功能說明」（3 點）＋「使用限制與規範」（5 點）＋「隱私承諾」三段落，移除舊版「服務使用須知」段落與完整「貼心小撇步」；隱私承諾沿用「聊天記錄」→「日常紀錄」的措辭。這份文字現為已套用版本，不再是待定案的差異說明。新版模板同時作為首次綁定成功時主動傳送的使用規則
- FR-6（取消）：移除 `/function`、中文觸發詞「我要看所有功能」及功能總覽／細節追問流程；功能探索由 Telegram 可見選單取代
- FR-6a：`/start` 是唯一保留的 Telegram Slash Command，用於 START 首次驗證及重新顯示主選單；其他一般使用者與 Owner Slash Commands 全面移除且不保留相容期，所有操作改由權限化選單、Callback 與引導式對話完成
- FR-6b：舊 Slash Command 不得再執行原功能；自然語言或語音提到正式功能名稱時，仍須先詢問是否進入該功能，明確確認後才切換
- FR-6c：每位使用者同時只能有一個功能模式；10 分鐘無互動後於下一則 Update 惰性切回一般對話，未送出草稿另保留 30 分鐘，期間仍可進行一般聊天。只有已輸入資料但尚未送出的新增／編輯流程屬於草稿；主選單、唯讀查詢、通關密碼及語音確認等暫存狀態不保留為草稿。每位使用者可同時保留不同功能的草稿，但每個功能最多一份，並依各草稿最後操作時間獨立計算 30 分鐘。切換功能時若有草稿，必須提供「保留草稿並切換／放棄草稿／繼續編輯」；再次進入仍有有效草稿的功能時，先顯示草稿摘要，再提供「繼續編輯／放棄草稿」，不得直接覆蓋。內容明確無關才建議切換，語意不確定時先反問，禁止 LLM 單方面丟棄草稿。自然語言入口採固定功能名稱與別名比對；明確命中時先詢問並引導至對應選單，未命中或無法確定時請使用者從主選單選擇，不得由 LLM 猜測功能或直接新增、修改、刪除正式資料。所有選單、Callback、名稱／別名偵測與模式切換均須重新驗證權限
- FR-6d：會異動正式資料的選單統一採「進入功能、收集資料、驗證、摘要、二次確認、寫入與結果回覆」，並提供返回上一步、取消、回主選單、查看目前輸入及重新填寫
- FR-6e：一般使用者主選單提供日常紀錄、資料查詢、待辦事項、重要日子、收藏與旅遊、成果展示、目標追蹤、「⏰ 功能開關與排程設定」、使用規則；Owner 另顯示權限管理、「💡 Youtube 技術分享設定」、「💼 求職設定」、「📖 考試設定」、發送康復通知。日常紀錄第二層包含飲食、運動、體態、心情、記帳；收藏與旅遊第二層包含收藏與行程操作，探索地圖維持 Mobile App 專用視覺入口
- FR-6e 決策更新（2026-08-18，Youtube 技術分享設定選單化）：`tech_intel` 主選單項目已接上真正邏輯（不再是「功能開發中」），子選單（`youtube_settings:*`）比照 `collections.py`／`achievements.py` 的單層選單＋按鈕式二次確認刪除模式：總覽列出目前主題並提供「➕ 新增主題」（達 `youtube.MAX_TOPICS`＝5 個上限時隱藏，仍保留伺服器端擋下訊息「已達上限 5 個主題」雙重保護）／「➖ 移除主題」（無主題時隱藏）；新增為單輪自由文字輸入；移除改為「選主題→✅ 確認移除／❌ 取消」二次確認畫面，才會真正呼叫刪除，不再是打編號直接刪除。舊文字觸發詞（`/my_youtube_topics`、`/add_youtube_topic`、`/remove_youtube_topic` 及對應中文別名）與其處理函式已全數移除，全面改選單觸發
- FR-6f：「功能開關與排程設定」依角色分流：一般使用者只顯示「我的排程」；Owner 額外顯示「功能開關」與唯讀「系統工作」。我的排程可開關待辦、重要日子（含目標與旅遊日期）、月底記帳月報、預算 50%／80% 警示；Owner 另可開關技術摘要、Youtube、求職與考試通知。關閉通知只停止發送，來源功能、資料處理與背景工作照常執行
- FR-6g：一般使用者只能調整自己的接收設定；重要日子建立者可設定通知對象。系統工作只供 Owner 查看名稱與固定時間，不提供 Cron 表達式或任意頻率修改。所有有明確日期的體態、運動、飲食、記帳、收藏及考試目標，以及選擇同步的旅遊行程，都以 `important_days` 為唯一日期提醒來源；關閉提醒不得刪除來源資料
- FR-6h：Telegram 生活紀錄支援新增、修改、刪除及歷史回補；Mobile App 的飲食、運動、體態、心情與記帳仍只允許異動今日紀錄，待辦、重要日子、收藏、旅遊、探索與成果依各自正式規格管理不同日期。探索沒有獨立新增入口，仍由收藏標記已造訪或完成行程產生。兩端共用相同欄位、必填、數值範圍、驗證與讀取結果，不共用歷史生活紀錄寫入權限
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
**討論紀錄**：`docs/ADR/discuss/feature-toggles.md`、`docs/ADR/discuss/robinson.md`（2026-08-15「特殊功能改為 Robin 專屬」）
**來源說明**：原記錄於 feature-toggles 規格，已於 2026-08-13 併入本文件。

**概要**：一般生活功能對所有已綁定使用者全面開放，不提供功能開關；「技術分享」、「求職設定」、「考試設定」永久限定 Robin／Owner 使用，並由「功能開關與排程設定」管理。

**功能性需求**
- FR-1：功能開關只限 `tech_intel`（畫面顯示「技術分享」，同時控制每日技術摘要與 Youtube 推薦）、`job_search`（求職設定）及 `certificate`（考試設定），且只控制 Robin 自己的爬蟲、內容產生與推播
- FR-2：三項特殊功能以 `is_owner` 限定 Robin；一般使用者不顯示入口，Owner 也不能替一般使用者授權。偽造 Callback、舊指令或 API 存取必須拒絕
- FR-3：待辦、記帳、體態、飲食、運動、心情、重要日子、收藏、旅遊、探索、成果等一般功能，對所有已綁定使用者直接開放；無紀錄時只顯示空資料狀態
- FR-4：三項特殊功能只支援 Robin 自己的啟用狀態與推播時間；關閉時不得執行對應爬蟲、內容產生或固定推播
- FR-4a：三項功能關閉後主選單入口仍顯示，點擊只提示「若要使用 XX 功能，請至功能開關與排程設定打開！」；功能通知另可獨立關閉，僅停止送達，不停止功能背景工作

**非功能性需求**
- NFR-1：可維護性 — 沿用既有 `ConversationStateStore`，新增 `flow` 欄位區分對話流
- NFR-2：安全 — 所有特殊功能與排程的讀寫及執行均須在後端重新驗證 `is_owner`，不以選單隱藏取代授權

**實作階段**
- Phase 1 Step 1.2：全數完成，78 個測試全過、覆蓋率 100%

### Gemini 對話核心

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/chat-core.md`
**來源說明**：原記錄於 chat-core 規格，已於 2026-08-13 併入本文件。

**概要**：一般對話只負責個人結構化資料的彈性查詢、使用者提供內容的整理／分析，以及不確定需求的功能導引。Robinson 人格改用程式內靜態 System Prompt；家庭／個人知識庫、持久化逐則對話與長記憶摘要停止讀寫，只保留記憶體內 10 分鐘短期上下文。舊 `/function` 總覽與細節追問已移除，功能探索改由 Telegram 可見選單負責。

**功能性需求**
- FR-1：路由層最終 fallback 呼叫對話核心
- FR-2：一般對話僅處理個人結構化資料的彈性查詢、使用者提供內容的解釋／摘要／改寫／分析，以及不確定需求的功能導引。圖片未附說明時預設辨識內容並整理重點；有附說明時依說明處理
- FR-3：System Prompt 使用程式內固定人格與安全規則；只根據當次內容、短期上下文及正式結構化資料回答，缺乏資料時誠實回報無法確認
- FR-8：保留不落地資料庫的 10 分鐘短期對話上下文，逾時或切換選單功能時清除
- FR-9a：一般對話不得直接新增、更新或刪除正式資料；資料異動必須切換到對應選單並完成驗證與確認
- FR-9b：一般對話不提供即時網路查詢；無資料來源時明確回報無法確認，不得虛構新聞、天氣、路況、價格或營業資訊
- FR-9c：資料查詢只允許目前使用者自己的結構化資料；使用者以行事曆或自然語言選擇最終日期，系統自動往前推 6 天，形成含首尾且最多 7 個曆日的區間，不提供 30 天或任何超過 7 天的選項。最終日期可位於未來，一次可查多個模組；不得顯示密碼、Token、內部識別值、執行任意 SQL、直接異動或大量匯出資料
- FR-9d：Telegram 查詢結果沿用帳號層的 Mobile App 隱私數字遮罩偏好；設定由後端保存並供雙端共用，不得只依賴單一手機本機狀態
- FR-13：一般對話接受對話框文字、Telegram 長按語音、圖片及上傳音檔；影片、Video Note、PDF、Office 文件、壓縮檔及其他格式一律不處理，固定回覆「我只能處理對話框文字、語音、圖片和音檔喔！」

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

**概要**：語音轉文字若無限制易消耗大量 Token，且辨識誤差需要使用者確認。本區塊涵蓋 Telegram 長按語音時長上限、超時鎖定，以及語音與音檔共用的轉錄確認流程。

**功能性需求**
- FR-14：Telegram 長按語音超過 10 分鐘強制中斷處理並提醒（用 Telegram 訊息本身的 `duration` 秒數判斷，不需先下載）
  - 規則 1：單次 Telegram 長按語音本身超過 10 分鐘時，語音功能整體鎖定 5 分鐘；所有超時與鎖定提示文案均顯示 5 分鐘
- FR-18：不接受用於錄製會議或長篇演講的長語音
- FR-16b（2026-08-16 新增、2026-08-18 擴充，見 `docs/ADR/discuss/voice-safety.md`）：全站語音與音檔轉文字確認機制——Telegram 長按語音或上傳音檔轉錄成功後不直接當成輸入內容，一律先貼出轉錄文字＋「✅ 正確，繼續」按鈕請使用者確認；使用者按下按鈕才用轉錄文字接回原本卡在的流程（含自由聊天），也可直接打字修正或立即重新傳送語音。上傳音檔不套用 FR-14 的 10 分鐘上限與 5 分鐘鎖定；其餘轉錄確認與個資防護規則相同

**非功能性需求**
- NFR-7：Token 節流——語音上限 10 分鐘

**實作階段**
- Phase 1 Step 1.4（FR-14，2026-08-01～08-02 完成；2026-08-18 鎖定時間調整為 5 分鐘）
- Phase 6 第二批 2g（FR-16b，2026-08-16；2026-08-18 擴充音檔分流並取消修正窗口）：全站語音／音檔確認機制，見 `src/bot/router.py` 的 `handle_voice_message()`／`voice_confirm:accept`／`pending_voice_confirm`

### 影像辨識

**狀態**：active
**討論紀錄**：無獨立 ADR；上傳/壓縮/命名/入庫流程設計見 `docs/ADR/discuss/submodules-core.md`（2026-07-31 條目）
**來源說明**：原記錄於 robinson 母 spec 的 FR-17／FR-17a～c，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：開放接受一般圖片供 Robinson 辨識（不限證照題目），並接受上傳音檔轉文字；其他檔案與影片格式明確拒絕。

**功能性需求**
- FR-17：圖片先上傳 Google Drive、`Pillow` 壓縮至 1024×1024 內／JPEG 80%、影像雙 Key 隨機辨識；未附說明時預設辨識內容並整理重點，有附說明時依說明處理。上傳音檔須轉文字並經 FR-16b 確認；影片與非圖片／音檔格式固定回覆「我只能處理對話框文字、語音、圖片和音檔喔！」
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
- FR-72b：隱私數字遮罩為帳號層設定，Mobile App 與 Telegram 查詢共用 `users.privacy_mask_enabled`；Mobile 可透過偏好設定 API 讀寫，Telegram 資料查詢啟用時將數字字元逐位替換為 `*`
- FR-72a：具明確日期的體態目標（體重／運動／飲食）及考試／證照目標，預設同步為一次性「重要日子」；預設提前 1 天、通知自己並顯示於待辦行事曆，使用者可在重要日子設定調整提醒與通知對象。Telegram 必須以重要日子保存的提醒天數與通知對象作為唯一期限提醒來源；目標名稱／日期更新時同步更新且保留既有提醒設定，目標達成、取消或清除日期時停用連動事件。既有體態目標固定提前 7 天提醒取消，避免重複推播。現行記帳只有月份預算，沒有單一完成日期，本階段不納入同步；資料同步已實作，通用 Telegram 重要日子發送器待重構

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
**討論紀錄**：`docs/ADR/discuss/mobile-app.md` 2026-08-12～2026-08-14「收藏清單／旅遊行程／探索地圖／成果展示」系列條目；Telegram 端實作見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2e」

**概要**：以「收藏候選 → 組成行程 → 確認造訪 → 地圖回顧」串接收藏清單、旅遊行程與探索地圖；成果展示則提供手動新增與系統候選確認兩種來源。四項功能皆為個人資料，不受 Mobile App 僅能異動今日資料的限制；第一階段不做家庭共同編輯、多幣別換算或逐日逐時旅遊排程。

**功能性需求**
- FR-73 收藏清單：記錄想去地點或想執行活動；保留名稱、類型、國家、區域／城市、選填地址、參考網址、預估費用與備註，移除優先程度、縣市與想去日期。名稱、類型、國家及區域／城市必填，地址一律明確標示為選填；未填地址仍可建立收藏並以國家及區域／城市執行區域定位。定位表單須提示目前以行政區／鄉鎮市區為主，可能無法精確辨識門牌或街道。國家與區域／城市採可搜尋、可選既有值且允許自訂新值的組合式下拉選單。狀態依行程關聯與造訪紀錄自動推導；同一收藏可加入多個行程。收藏支援編輯、刪除、二次確認、5 秒復原與防連點；已有探索歷史時刪除原收藏仍保留歷史快照。
- FR-74 旅遊行程：由收藏組成當天或幾天幾夜的輕量行程，不提供第幾天、幾點去哪裡的細部排程。單一行程只允許一個國家及一個區域／城市；國家、城市採組合式下拉選單，收藏項目只列出相同目的地的收藏並以可捲動下拉選單選擇。保存行程名稱、選填起訖日期、國家、區域／城市、收藏項目及顯示順序、預估支出與備註；規劃中可不填日期，確認或完成前必填。行程行事曆同步顯示中華民國休假日、節日與既有重要日子。狀態依操作流轉為規劃中、已確認、已完成、已取消；完成時由使用者勾選實際造訪項目，未勾選收藏繼續保留。
- FR-74b 行程重要日子同步：新增／編輯行程提供「同步至重要日子」且預設開啟；有起訖日期時建立與行程名稱、日期連動的一次性重要日子。預設提前 1 天、通知自己、顯示於待辦行事曆，使用者可自行調整；Telegram 依重要日子設定推播，不另發建立／更新／刪除行程成功通知。後續修改行程保留提醒設定並同步名稱／日期；關閉同步、取消或刪除行程時停用連動事件，恢復有效行程時依同步設定重新啟用。
- FR-74a 行程記帳整合：預估支出支援交通、住宿、飲食、門票、購物與其他分類，也允許只填總額；全部使用新台幣。實際支出仍以既有記帳為唯一來源，記帳可選填關聯行程且不限制交易日期；行程彙總預估、實際、差額及各記帳類別。取消行程不刪除收藏或記帳，保留支出關聯與取消標示。
- FR-75 探索地圖：不提供獨立新增入口，探索紀錄只能由收藏標記已造訪或完成行程時產生。依國家及區域／城市的可搜尋下拉選單篩選；同一地點只顯示一個 Leaflet／OpenStreetMap 標記，點開列出各次獨立造訪。頁面明示定位以行政區／鄉鎮市區為主，可能無法精確辨識門牌或街道。每次造訪保存名稱、類型、國家、區域／城市、地址、經緯度、備註、造訪日期及行程快照，可個別編輯或刪除。收藏表單由使用者明確按下「定位地址／定位區域」後才呼叫 Nominatim；有地址時依精確門牌、道路、城市逐級放寬，無地址時直接以國家及區域／城市定位。定位結果必須顯示精確地址、道路近似位置或城市近似位置；所有層級失敗仍可保存並列入「無法定位」。探索紀錄修改地址時立即清除舊座標，使用者可選擇重新定位，不得沿用失效座標。
- FR-76 成果展示：首頁提供手動新增成果與待確認成果提示；系統只能根據體態達標、考試達標、運動累積、探索地點／國家數、行程完成及待辦里程碑提出候選，不經 LLM 且不得自行建立。候選採被動掃描：使用者開啟成果展示清單（Mobile 首頁或 Telegram「查看成果」）時，系統才重新掃描並以「加入成果展示／略過」按鈕列出，不於候選產生的當下主動推播（2026-08-16 決策，見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2e」）。任一端接受或拒絕後須同步更新；同一候選只詢問一次，拒絕後不重複提示，不以飲食或心情自動判斷。成果必填名稱、完成日期及類別，選填說明、照片及關聯紀錄，保存 `manual`／`suggested` 來源。成果支援刪除與防連點；Mobile App 刪除另有二次確認與 5 秒復原，Telegram 端刪除為直接執行，不提供二次確認與復原（2026-08-16 決策，同上 ADR）。刪除成果不影響原始紀錄。
- FR-76a 導覽入口：首頁收藏清單提供「新增收藏」；旅遊行程從收藏清單進入建立／管理；探索地圖只提供查看；成果展示提供「新增成果」與待確認提示。左側選單保留收藏清單、探索地圖與成果展示，作為查看、篩選與分析入口。
- FR-73a（2026-08-17 新增，批次3；2026-08-17 補充 Calendar 同步，見下方「2026-08-17 補做」條目）：收藏清單目標——「清單完成度目標」，Telegram 入口為「🧭 收藏與旅遊」子選單新增的「🎯 目標」按鈕（`collections:goal:*`，分「➕ 新增／📋 查看清單」兩層，比照 FR-45 支援多筆並存與按鈕式編輯/刪除）；目標值透過方案A解析「新完成收藏項目數」，`baseline_value` 為設定當下已 `visited` 的項目數；達成判斷：收藏項目被標記已造訪（`collections:visit:*`）後，檢查「目前 `visited` 數 － `baseline_value`」是否 ≥ `target_value`，達成時回覆恭喜文字；抽不出結構化數值時退化為純文字目標。新增流程且有期限時，比照 FR-45（體態目標）多問一輪「要不要同步到 Google 家庭行事曆」（`pending_module_goal_calendar_sync`），確認後在 `<module_key>:goal:confirm_save` 建立 Calendar 事件並存回 `google_calendar_event_id`；編輯不重問，維持原同步設定。資料表為 FR-41b 同一張新表 `module_goals`（`module_key='collections'`，`sync_to_calendar`／`google_calendar_event_id` 欄位見 migration 0088）

**非功能性需求**
- NFR-14：資料隔離 — 收藏、行程、探索與成果皆依 `user_id` 隔離，使用者只能管理自己的資料，Robin 不代改家人資料。
- NFR-15：地圖合規 — Leaflet 地圖必須顯示 OpenStreetMap 著作權；Nominatim 只能由使用者明確觸發搜尋，不做即時自動完成，以可識別應用程式與聯絡方式的 User-Agent 呼叫，全應用程序每秒最多一次並將成功結果保存至 PostgreSQL 快取。
- NFR-16：歷史完整性 — 探索快照、實際記帳與產生成果的原始紀錄，不得因刪除收藏、行程或成果卡片而被連帶刪除。
- NFR-17：長清單操作 — 收藏、旅遊行程、探索紀錄與成果展示等累積型卡片清單最高 `60vh`，超出後於清單區內垂直捲動；組合式下拉選單最高 240px。Web 顯示捲軸，iOS／Android 依系統行為顯示捲動指示器。

**實作階段**
- Phase 5 Step 5.1：修正新增收藏 Modal 手機版跑版，依 FR-73 精簡收藏欄位並校正既有 Schema／API／UI／測試。
- Phase 5 Step 5.2：完成 FR-74／FR-74a 旅遊行程、收藏關聯、預估支出與記帳整合。
- Phase 5 Step 5.3：完成 FR-75 造訪確認、探索快照、地圖聚合、定位失敗清單、收藏地址轉座標與探索地址重新定位；已完成部署環境設定與實機驗收。
- Phase 5 Step 5.4：完成 FR-76／FR-76a 手動成果、成果候選、刪除復原與首頁／選單入口（Mobile App）。
- Phase 5 Step 5.5：整合測試、Mobile 實機窄螢幕驗收、文件與部署驗證。
- Phase 6 第二批 2e（2026-08-16）：Telegram 端接上 FR-76／FR-76a 成果展示選單（`src/bot/achievements.py`），直接複用既有 `AppLifeExplorationService`；候選機制維持被動掃描，刪除採直接執行、不提供二次確認與復原（與 Mobile App 差異見 FR-45、FR-76 條文），見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2e」。

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
- FR-19h：決策執行狀態閉環回饋——同步資料異動成功只在原 App 畫面或 Telegram 對話內明確回覆，不額外推播；失敗須保留未送出輸入、回覆安全訊息並提供重試。背景工作只有產物需要送達時才推播成功；零星可重試錯誤只記 Log，嚴重、持續或影響使用者的錯誤才通知 Owner
- FR-19i：外部 API 呼叫重試機制（Max 3 次＋Exponential Backoff 1/2/4 秒），實作見 submodules-core `retry` 子模組
- FR-19j：系統錯誤記錄持久化＋解法追蹤（`system_error_reports` 表）；移除 Telegram 固定文字指令，改由 Owner 專屬 Telegram 錯誤處理選單更新解法。Mobile App 只是事故來源，不提供錯誤清單或結案介面
- FR-19k：Owner 錯誤通知保存最後通知方式 `telegram`／`email`／`undelivered` 與最後通知時間；系統錯誤管理顯示「Telegram 已送達／Email 備援已送達／未送達」。Email 成功後不得重複通知或在 Telegram 康復後補發；兩種管道都失敗時保留錯誤紀錄與 Log，不建立第三種備援
- FR-19l：Mobile API 的未預期 5xx 例外必須進入與 Telegram Bot 共用的錯誤紀錄、Owner Telegram→Email 備援通知與系統錯誤管理；預期 4xx 不建立事故。一般使用者當下只看到不含技術細節的 Mobile 安全錯誤文案，不另外收到 Telegram 異常推播。錯誤紀錄要區分來源平台並在可辨識時關聯受影響使用者；登入階段未驗證身分時記為「未知使用者」，不保存帳號、密碼或其他登入輸入。同一平台、功能與安全錯誤摘要在 10 分鐘內重複時合併為同一事故、累計次數且不重複通知 Owner。新 Schema 的舊資料回填規則為：來源平台設為 `telegram`；已有處理說明者以 Owner 及原 `updated_at` 回填處理人／處理時間；無法判定的受影響使用者保持 `NULL`
- FR-20：問題修復後由 Owner 專屬「發送康復通知」選單處理；先選擇尚未完成康復通知的 Telegram Bot 或 Mobile App 事故。Telegram Bot 事故的候選收件人為該次實際成功收到事故通知的家人；Mobile App 事故優先列出可辨識的受影響使用者，無法辨識時列出所有已綁定 Telegram 的家人。預設全選且 Owner 可自行取消勾選，預覽收件名單與對應平台文案後必須二次確認才逐一以 Telegram 發送。單一失敗不影響其他收件人，部分失敗的事故保留於清單供重試；不自動發送康復通知，舊 `/recovered` 入口移除
- FR-20a：待辦、重要日子、目標、旅遊及其他模組只產生領域事件，由統一通知服務負責通知規則、去重、Telegram 發送及 Robin 系統錯誤的 Email fallback；通知紀錄保存類型、接收者、預計／實際發送時間、管道與結果，不保存敏感原始錯誤
- FR-21：Neon 容量監控（達 80% 告警，借用 `/healthz` 頻率）；Gemini 免費額度用量監控刻意暫緩（官方無查詢即時用量的 API）

**非功能性需求**
- NFR-6：可維護性——錯誤訊息一律去技術化
- NFR-8：安全——Robinson 對正式環境程式碼不具備任何自動修改或部署能力
- NFR-9：韌性——所有外部 API 呼叫具備重試機制
- NFR-10：一致性——所有寫入類操作不允許靜默失敗
- NFR-11：通知邊界——Email 備援只適用 Robin 專屬系統錯誤，不作為一般使用者 Telegram 推播失敗的替代管道

**實作階段**
- Phase 1 Step 1.6（基礎捕獲+Log+通知）、Phase 2 Step 2.4～2.6（log 雲端連結、重試機制、分級降級）全數完成；Step 2.4 曾規劃 AI 自主診斷＋GitHub PR 自動化並記錄於 ADR-7，後於 Step 2.4 開工前正式取消（見討論紀錄）

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
- FR-41／FR-41a：「💰 設定預算」（`finance:budget`）設定全局預設；`budget_overrides` 支援特殊月份覆蓋，改動已有值時先反問確認。2026-08-18（批次5）決定：覆蓋確認改成 ✅ 確認覆蓋／❌ 取消按鈕（`finance:budget_confirm_save`／`finance:budget_override_confirm_save`），不再是自由文字 LLM CONFIRM/CANCEL；套用範圍（全部月份／某幾個月）與月份清單本身仍是自由文字輸入
- FR-42：「➕ 新增記帳」／「🕐 補記記帳」／「📋 我的記帳紀錄」（`finance:add`／`finance:backfill`／`finance:list`）完整 CRUD；備註套用個資遮蔽。2026-08-18（批次5）決定：新增/補記流程改為摘要（類型／分類／金額／備註／日期）→ 二次確認按鈕（`finance:confirm_save`）才真正寫入，取代原本反問完備註直接寫入；查詢清單改為按鈕式編輯（`finance:edit:<id>`）／刪除（`finance:delete:<id>`，附二次確認），取代原本「輸入編號→LLM 分類更新或刪除→LLM CONFIRM/CANCEL」三段式文字流程
- FR-43：50% 門檻只在每月 15 日前檢查、80% 門檻整月都檢查，各自每月最多推播一次
- FR-44：「📊 我的記帳摘要」（`finance:summary`）文字摘要（本月支出/收入、預算使用率、分類佔比、跟上月比較）
- FR-44a：月底 21:00 自動推播月報（僅推給有生效預算或當月有交易的使用者）
- FR-41b（2026-08-17 新增，批次3；2026-08-17 補充 Calendar 同步；2026-08-18 批次5更新入口）：記帳目標——「儲蓄／淨結餘目標」，入口為子選單「🎯 目標」按鈕（`finance:goal`），沿用批次3既有的 `_dispatch_module_goal_callback()` 通用目標子流程，不重寫；目標值透過方案A（`goal_parser.parse_goal_input()`）解析淨結餘金額（新台幣），解析成功時 `target_value` 為目標淨結餘變化金額、`baseline_value` 固定為 0；達成判斷：每次記帳確認送出後，檢查「目標建立日期之後的收入總額－支出總額」是否 ≥ `target_value`，達成時比照 FR-45 回覆恭喜文字；抽不出結構化數值時退化為純文字目標，只能刪除結束。新增流程且有期限時，比照 FR-45（體態目標）多問一輪「要不要同步到 Google 家庭行事曆」，確認後建立 Calendar 事件並存回 `google_calendar_event_id`；編輯不重問。資料表為新表 `module_goals`（`module_key='finance'`，migration 0085；`sync_to_calendar`／`google_calendar_event_id` 欄位見 migration 0088），支援多筆並存、按鈕式編輯/刪除（`finance:goal:*`）
- FR-6e 決策更新（2026-08-18，批次5）：日常紀錄第二層五個子項目（心情／運動／飲食／體態／記帳）至此全數接上按鈕入口與真正邏輯，不再有純文字觸發詞才能使用的子模組

**實作階段**
- Phase 2 Step 2.1：全數完成，539 個測試全過、覆蓋率 100%
- 批次5（記帳按鈕化＋摘要確認，FR-41～FR-44，2026-08-18）：`start_finance_menu()` 子選單、新增/補記摘要→二次確認、按鈕式清單編輯/刪除、預算覆蓋確認按鈕化，移除全部舊文字觸發詞；詳見 `docs/ADR/discuss/robinson.md` 2026-08-18「批次5『💰 記帳』按鈕化＋摘要確認開工前 SDD 計畫確認」
- 批次3（記帳目標，FR-41b，2026-08-17）：新增 `src/bot/goals.py`（`module_goals` 通用 CRUD＋達成判斷）；`commands.py` 新增 `start_module_goal_*`／`handle_module_goal_*` 系列函式；`router.py` 新增 `finance:goal:*` 分派與 `_dispatch_module_goal_callback()` 共用邏輯；`finance.handle_transaction_note_step()` 寫入交易後呼叫 `goals.check_finance_goal_achievement()`，詳見 `docs/ADR/discuss/robinson.md` 2026-08-17「批次3：六模組目標泛化＋🎯 目標追蹤新選單 實作完成」
- 批次3 補做（記帳／收藏清單目標 Calendar 同步、飲食目標自動達成、考試成績自動達成，2026-08-17）：`module_goals` 新增 `sync_to_calendar`／`google_calendar_event_id` 欄位（migration 0088），`goals.py`／`commands.py`／`router.py` 補上 `pending_module_goal_calendar_sync` 問句與 Calendar 事件建立（比照 `body.py` 既有做法）；`body_goals` 新增 `target_direction` 欄位（migration 0089），飲食目標新增 `check_and_push_diet_goal_achievements()`（依 LLM 解析出的 MIN／MAX 方向自動判斷達成）；`certificate_goals.py` 新增 `check_score_achievement()`，記錄正式應考成績後自動跟目標分數比對。1897 個測試全過（新增 19 個），`ruff check .` 通過，詳見 `docs/ADR/discuss/robinson.md` 2026-08-17「批次3補做：不得漏做的三項功能」

### 體態管理

**狀態**：active
**討論紀錄**：無獨立 ADR，設計決策已於下方需求段落內註明
**來源說明**：原記錄於 robinson 母 spec 的 FR-45～FR-48，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：身高/體重/腰圍（基準值）、運動、飲食三個子功能共用 `body_goals` 表，各自完整 CRUD 與預警。

> **2026-08-17 全部正式生效**：FR-45、FR-46 已於 Phase 6 第二批 2h（2026-08-17）正式生效，FR-47／FR-47a（運動紀錄改版，批次2）已於 2026-08-17 正式生效，FR-45a（🎯 目標追蹤新選單）與 FR-48 目標欄位方案A（飲食目標 LLM 輔助解析）已於批次3（2026-08-17）正式生效，決策記錄見 `docs/ADR/discuss/robinson.md` 2026-08-17「日常紀錄－體態（Phase 6 第二批 2h）前置討論：範圍拆分與三批決策」「補充：目標編輯/多目標並存與🎯目標追蹤新選單」「運動紀錄改版（批次2）實作完成」及「批次3：六模組目標泛化＋🎯 目標追蹤新選單 實作完成」。實際上線狀態請對照下方「實作階段」。

**功能性需求**
- FR-45：三種預警——目標達成通知、依 FR-72a 重要日子設定的期限提醒、BMI 異常提醒；體態目標達成時回覆恭喜文字，是否加入成果展示由使用者自行開啟「🏆 成果展示」清單查看候選並確認（見 FR-76 被動掃描機制），系統不於達成當下主動推播候選按鈕，也不自行建立成果。目標支援同一使用者、同一模組（體重／運動／飲食）多筆並存，清單可「編輯」（重新走一次目標值/期限輸入）或「刪除」（二次確認），不再限制「要調整就取消重設」
- FR-45a（2026-08-17 正式生效，批次3）：主選單新增「🎯 目標追蹤」（`menu.py` `GOAL_TRACKING_MODULES`），點擊後列出已支援目標功能的模組按鈕（飲食、體態、運動、記帳、收藏清單、考試共六個）→ 選模組列出該模組未過期（active 且未超過期限，或無期限）的目標清單，無目標顯示「查無資料」→ 選一個目標顯示最新快取摘要（依「過去一個月」「過去一週」紀錄生成建議與方向、提及距離截止日還有多久，無期限的目標不顯示這段，並附加油打氣文字）；摘要由每日排程（統一凌晨 01:00，`src/services/goal_summary_job.py`，寫入新表 `goal_summaries`）產生快取，Telegram 端只顯示最新一份、不即時生成、不可操作，下方固定只有「🔙 返回主頁面」按鈕。體態/運動/飲食讀 `body_goals`，記帳/收藏清單讀新表 `module_goals`（migration 0085），考試沿用既有 `certificate_goals`，三張來源表結構不同，統一由 `goal_summaries.goal_source` 欄位區分
- FR-46：Telegram 入口為「日常紀錄」子選單的「⚖️ 體態」（取代原 `/set_height`／`/set_waist`／`/log_weight`／`/backfill_weight`／`/my_weight_logs`／`/set_body_goal`，不提供舊指令相容期）；子選單：設定身高／設定腰圍／記錄體重／補記體重／我的體態紀錄／🎯 目標／🔙 返回。身高 140～200 公分、腰圍 50～150 公分、體重 40～150 公斤，超出範圍原地反問並明講區間與單位；新增／補記流程末段先組摘要文字＋「確認送出／取消」按鈕，確認才寫入；「我的體態紀錄」（原「我的體重紀錄」正名擴充）點擊後直接顯示身高／體重／腰圍／BMI 四項，從未紀錄的欄位顯示「尚無紀錄」，體重抓最新一筆（不限今天），BMI 缺身高或體重時顯示「無法計算」；體重歷史清單改按鈕式「編輯／刪除」，刪除需二次確認；「🎯 目標」分「➕ 新增／📋 查看清單」兩層，比照 FR-45 支援多筆並存與編輯/刪除
- FR-47：Telegram 入口為「日常紀錄」子選單的「🏃 運動」（Phase 6 第二批 2c 起改為選單按鈕觸發，取代原 `/log_exercise`／`/backfill_exercise`／`/my_exercise_logs`，不提供舊指令相容期，決策見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2c」）；新增／補記流程末段先組摘要文字＋「確認送出／取消」按鈕，確認才寫入（卡路里 LLM 估算，非 MET 公式）；清單改按鈕式「編輯／刪除」，刪除需二次確認。子選單另補一顆「🎯 目標」按鈕（分「➕ 新增／📋 查看清單」兩層），比照 FR-45 支援多筆並存與編輯/刪除
- FR-47a（2026-08-17 正式生效，批次2）：運動紀錄表單全面改版，取代原「時間／熱量」雙頁籤設計——新增全域共用的運動類別表 `exercise_categories`，類別選「➕ 其他」時可直接新增全域類別（不需 Owner 審核，重複名稱以「正規化字串比對＋LLM 語意判斷」兩段式同義詞合併），現有固定類別（跑步/健走/騎自行車/游泳/重訓/打球/瑜伽）一併搬進新的類別表；欄位改成單一表單：持續時間（分鐘，必填）／心率（bpm，選填，可跳過）／補充內容（選填，可跳過，placeholder「請描述詳細內容...」），刪除「重訓強度與組數」特殊分支，強度組數改由使用者寫進「補充內容」自由文字，AI 估算消耗熱量時一併參考；下方提供「是否交由 AI 計算消耗熱量？」是／否，選「否」時顯示「消耗熱量（大卡）」輸入框（placeholder「請輸入數字」），沿用既有 1～5,000 大卡範圍限制；Mobile App（`RecordModal.tsx`）與 Telegram（`body.py`／`commands.py`／`router.py`）同步改版，新增 `GET /api/app/exercise-categories` 供 Mobile 下拉選單；舊運動紀錄資料已於 migration 0084 直接清空，不做欄位相容回填
- FR-48：Telegram 入口為「日常紀錄」子選單的「🍚 飲食」（Phase 6 第二批 2g 起改為選單按鈕觸發，取代原 `/log_diet`／`/backfill_diet`／`/my_diet_logs`，不提供舊指令相容期，決策見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2g」）；飲食（`food`）、飲水（`water`）比照 Mobile App 的 single-daily 設計，同一天各自只能有一筆，已有紀錄時新增流程會導向查看清單的編輯功能；新增流程先問要不要記飲水、再問要不要記食物（已有的項目直接跳過提問，兩項都跳過就不寫入），食物內容支援文字／照片兩種輸入方式（照片複用 Mobile App 既有的 `src/services/app_diet_photo.py` 辨識邏輯），算完營養素後可選擇沿用 AI 估算（附誤差聲明）或自己填寫（`nutrition_source`，範圍比照 migration 0078 CHECK 限制）；新增／補記流程末段組摘要＋「確認送出／取消」按鈕，確認才寫入；清單改按鈕式「編輯／刪除」，刪除需二次確認。子選單另補一顆「🎯 目標」按鈕（分「➕ 新增／📋 查看清單」兩層）；2026-08-17 正式生效（批次3；2026-08-17 補做自動達成判斷）：飲食目標改採方案A「結構化為主、LLM 輔助解析」（`goal_parser.parse_goal_input()`），能抽出結構化欄位時寫入 `body_goals.target_value`／新增的 `target_unit` 欄位（migration 0087），抽不出來時退化為純文字目標；「以上／以下」語意不明確的問題（例如「熱量控制在X以內」是上限、「每週吃蔬菜X次」是下限）已解決：新增 `target_direction` 欄位（migration 0089，`min`＝至少要達到、`max`＝不能超過），由 LLM 解析時一併判斷方向；`check_and_push_diet_goal_achievements()` 依方向自動判斷達成——`min` 方向隨時可判斷（累計值 ≥ 目標即達成），`max` 方向因數學上需要明確的結束邊界才能判斷「有沒有超標」，只在目標「有期限」且已到期時才判斷（累計值 ≤ 目標才算達成），沒有期限的 `max` 方向目標暫時無法自動判斷，只能手動刪除結束

**實作階段**
- Phase 2 Step 2.2：全數完成，661 個測試全過；`src/bot/body.py` 覆蓋率 100%；2026-08-08 腰圍擴充新增 1009 個測試
- Phase 6 第二批 2c（運動子項，2026-08-16）：入口改選單按鈕並補上摘要→二次確認，155 項測試全過（見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2c」）
- Phase 6 第二批 2g（飲食子項，2026-08-16）：入口改選單按鈕，single-daily 規則、文字/照片雙輸入、AI/人工營養素選擇、摘要→二次確認、按鈕式編輯/刪除；同批一併完成全站語音確認機制（FR-16b），見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2g」
- Phase 6 第二批 2h（體態子項，FR-45／FR-46，2026-08-17）：入口全面改選單按鈕＋摘要→二次確認，身高 140～200 公分／腰圍 50～150 公分／體重 40～150 公斤三處合理範圍同步收斂並附動態文案；新增 `get_body_summary()`／`format_body_summary()` 供「我的體態紀錄」四項摘要；目標改為運動/飲食/體態三入口共用同一套 `body:goal:*` 子流程，支援多筆並存＋按鈕式編輯/刪除；六個舊指令（`/set_height`／`/set_waist`／`/log_weight`／`/backfill_weight`／`/my_weight_logs`／`/set_body_goal`）已移除，不提供相容期；1842 個測試全過，`ruff check .` 通過；FR-45a（🎯 目標追蹤新選單）留給批次3
- 批次2（運動紀錄改版，FR-47a，2026-08-17）：新增 `exercise_categories` 全域類別表（migration 0084，同批清空舊 `exercise_logs` 資料並改結構）；`body.py` 新增 `list_exercise_categories()`／`find_or_create_exercise_category()`（兩段式同義詞合併）並改寫 `create_exercise_log()`／`update_exercise_log()`／`format_exercise_log_list()`；Telegram 流程改為選類別→時長→心率（可跳過）→補充內容（可跳過）→AI／人工熱量二選一→摘要確認；`app_records.py` 同步改寫 exercise 驗證邏輯並新增 `GET /api/app/exercise-categories`；Mobile `RecordModal.tsx` 改用 `SearchableSelect` 動態載入類別、移除雙頁籤與重訓特殊分支；1844 個測試全過（新增 2 個），`ruff check .`／`tsc --noEmit` 皆通過，詳見 `docs/ADR/discuss/robinson.md` 2026-08-17「運動紀錄改版（批次2）實作完成」
- 批次3（六模組目標泛化＋🎯 目標追蹤新選單，FR-45a／FR-48 方案A，2026-08-17）：新增 `body_goals.target_unit` 欄位（migration 0087）供飲食目標存結構化單位；新增 `src/services/goal_parser.py`（LLM 輔助解析目標值/單位，方案A）；`body.py` 的 `create_goal()`／`update_goal()` 支援 `target_unit`；飲食目標新增流程（`handle_goal_diet_description_step()`）改呼叫 `goal_parser.parse_goal_input()`。1878 個測試全過（新增 34 個），`ruff check .` 通過，詳見 `docs/ADR/discuss/robinson.md` 2026-08-17「批次3：六模組目標泛化＋🎯 目標追蹤新選單 實作完成」與 `docs/reference/db_schema.md`

### 心情小記

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2c（日常紀錄－心情、運動）實作計畫」
**來源說明**：原記錄於 robinson 母 spec 的 FR-49／FR-50，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：心情分類（固定 6 選一）→ 日記內容 → 個人成就三選一提示（可跳過），全程純字串比對不需 LLM。

**功能性需求**
- FR-49：Telegram 入口為「日常紀錄」子選單的「😊 心情」（Phase 6 第二批 2c 起改為選單按鈕觸發，取代原 `/mood_journal`／`/backfill_mood`／`/my_mood_journals`，不提供舊指令相容期）；日記內容套用個資遮蔽；輸入完內容後先組摘要文字＋「確認送出／取消」按鈕，確認才寫入；清單改按鈕式「編輯／刪除」，刪除需二次確認（僅按鈕，不再走自由文字 CONFIRM/CANCEL）
- FR-50：個人成就三選一提示，可跳過不強迫回答

**實作階段**
- Phase 1 Step 1.8：全數完成，409 個測試全過、覆蓋率 100%；2026-08-02 補記/更新/刪除擴充後 465 個測試全過
- Phase 6 第二批 2c（2026-08-16）：入口改選單按鈕並補上摘要→二次確認，移除 LLM 意圖分類，155 項測試全過（見 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2c」）

### 好友模式

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/friend-mode.md`
**來源說明**：原記錄於 robinson 母 spec 的 FR-51／FR-52，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：使用者主動觸發「陪我聊聊」，Robinson 動態讀取該使用者已開啟且近期（7 天）有資料的所有功能模組，生成陪伴式對話回覆，自然涵蓋心情趨勢文字摘要。僅被動模式，不含主動關懷推播。

**功能性需求**
- FR-51：心情趨勢改文字/emoji 摘要，不做圖片圖表（併入 FR-52 回覆呈現，不獨立成查詢指令）
- FR-52：只接受自然語言「陪我聊聊」，`_DATA_PROVIDERS` 登記表涵蓋心情/待辦/體態/記帳/證照準備等既有模組的近期查詢；`/friend_chat` 已移除

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
- FR-24：`certificate` 開關；證照準備目標依證照各自設定考試日期與目標分數，並可依近 30 天成效與目標生成客製化建議
- FR-24a（2026-08-17 新增，批次3；2026-08-17 補做自動達成判斷）：考試準備目標整合進🎯 目標追蹤主選單（FR-45a），沿用既有 `certificate_goals` 表不新建資料表；每日 01:00 排程（`goal_summary_job.py`）依 `certificate_stats.compute_daily_period_stats()` 統計近一週／一個月作答成效生成快取摘要，寫入 `goal_summaries`（`goal_source='certificate_goals'`）；自動達成判斷：使用者透過 `/record_official_score` 記錄「實際應考成績」（`handle_exam_score_value_step()`）後，立即呼叫 `certificate_goals.check_score_achievement()` 跟該 `exam_type` 設定的 `target_score` 做數字比對（兩者皆為 TEXT，只在都能抽出數字時比較，`分數 ≥ 目標分數` 視為達成），達標就在記錄成功的回覆後面附加一句恭喜；`target_score` 或成績本身不是數字（例如「通過／未通過」這類非量化證照）時優雅跳過，不誤判；跟 `/certificate_advice` 既有的即時方向建議並存，互不取代
- FR-25：TOEIC 每次出題 1 聽力+2 填空+3 單字；軌道一檔名格式泛用化為 `{exam_type}_{test_id}_write/listen_{題號}.{ext}`；軌道二單字題即時生成入庫
- FR-26：每日出題數量、新題:複習題 7:3，彈性排程支援挪動/取消/區間覆蓋/平攤四種語意（平攤需提案確認才寫入）
- FR-27：作答只接受 A/B/C/D；正解來自 Robin 拍照上傳的 `_ans` 答案照
- FR-28：未作答題目不主動催促；使用者仍可在下一批題目產生前跨日晚補答
- FR-29：`/my_quiz_stats` 彈性自然語言問答（不做圖表），排除未作答日子並支援跨區間比較
- FR-30：正式成績獨立建表，僅查詢不修改；每筆保留證照、應考日期、分數與選填補充內容
- FR-30a（2026-08-18 定案，見 `docs/ADR/discuss/skill-growth.md` 對應日期條目）：Owner 主選單「📖 考試成績」改為「📖 考試設定」，改用 `certificate_settings:*` 權限化選單並取代既有文字／Slash Command 入口。子選單固定為「證照設定／目標／每日題數設定／實際考試紀錄」。證照設定使用 Owner 專屬名冊：TOEIC 預設存在；可新增其他證照、停用自訂證照，但不得實體刪除歷史資料。尚無題庫的自訂證照仍可設定目標與記錄正式成績；每日題數頁必須明示不會推播題目。所有資料寫入採摘要與按鈕式二次確認。
- FR-30b（2026-08-18 定案）：每日題數設定依證照獨立保存。非 TOEIC 只可設定每日總題數；TOEIC 使用固定「聽力／讀寫／單字」題數，總題數自動加總。可建立、查看、編輯與刪除不重疊的日期區間覆蓋；題數為 0 表示該區間不出題，區間刪除必須二次確認。正式考試紀錄新增選填補充內容，但維持只新增與查詢、不提供修改或刪除。

**實作階段**
- Phase 3 Step 3.1（每日技術分享）、Step 3.2（TOEIC 建題庫）、Step 3.3（推播/作答/成效/正式成績）全數完成，Phase 3 主線於 1185 個測試時全過
- `language`（語言學習）功能開關已建立但暫時擱置，不排入目前 Roadmap，見討論紀錄

### YouTube 技術情報模組（個人技能成長子功能，僅 Robin 可用）

**狀態**：active（共用 `tech_intel` 開關）
**討論紀錄**：`docs/ADR/discuss/youtube-intel.md`
**來源說明**：原記錄於 robinson 母 spec 的 FR-57～FR-59，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：依多組主題設定，用 YouTube Data API 取得候選影片，LLM 判讀標題/說明欄/統計數字決定排序，每週四固定推播 Top 3，多主題採「保底＋輪替」公平曝光機制。

**功能性需求**
- FR-57／FR-57a：多主題設定（`youtube_topics`），`search.list`＋`videos.list` 補統計數字；上限 `youtube.MAX_TOPICS`＝5 組（2026-08-18 追加，見下方 FR-57a 決策更新）
- FR-57a 決策更新（2026-08-18，Youtube 技術分享設定選單化）：主題管理入口從三個獨立文字觸發詞改為主選單「💡 Youtube 技術分享設定」子選單（`youtube_settings:*`），比照 `collections.py`／`achievements.py` 單層選單＋按鈕式二次確認刪除模式；新增達 5 組上限時擋下（隱藏按鈕＋伺服器端訊息雙重保護），移除改為「選主題→按鈕二次確認」才真正刪除，不再是打編號直接刪除；舊文字觸發詞全數移除，見 `docs/ADR/discuss/youtube-intel.md` 2026-08-18 條目
- FR-58：LLM 語意判讀取代 Rule-based Weight；1 組主題全出自該組，2 組各保底 1、3 組以上優先選最久未推播的 3 組；30 天內已推播 `video_id` 過濾
- FR-59：每週四 08:00 排程；配額估算遠低於每日上限；失敗走重試＋一般感冒級分級降級

**實作階段**
- Phase 3 Step 3.4：全數完成
- 2026-08-18：主題設定入口全面選單化（`youtube_settings:*`），5 組上限、按鈕式二次確認刪除；程式碼已完成，測試尚未執行，見 PROGRESS.md 2026-08-18 條目

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
- FR-41（2026-08-18 定案，見 `docs/ADR/discuss/job-search.md` 對應日期條目）：主選單「💼 求職分析」改名「💼 求職設定」，全面選單化（`job_search:*`），取代舊有文字觸發詞（`/set_job_search`、`ID=XXX 職缺已應徵`等），比照 `collections.py`／`achievements.py` 的單層子選單模式。子選單 10 項：我的履歷（可編輯／清空）、期望工作內容（可編輯／清空）、必要條件設定（年資／期望薪資上下限，原 FR-36 `save_profile()` 五欄位中拆出的三個結構化欄位，`users.years_of_experience`／`expected_salary_min`／`expected_salary_max`，獨立於履歷／期望工作內容之外）、職缺關鍵字設定（`job_search_criteria` 清單，可新增／個別刪除）、職缺清單（唯讀，依 `score` 排序）、已應徵職缺設定／獲得面試職缺設定／拿到 offer 職缺設定（各自依 `job_applications` 最新狀態過濾，可改狀態）、職缺已關閉設定（可人工覆寫 `is_closed`）、其他平台職缺（沿用既有 `add_external_job()` 邏輯，改選單觸發）。履歷／期望工作內容／職缺關鍵字設定各自獨立清空或刪除，互不影響其餘欄位（不再是 FR-36 原本「一輪對話全部覆蓋」的設計）
- FR-41a（2026-08-18 定案，見 `docs/ADR/discuss/job-search.md` 對應日期條目）：`job_postings` 新增 `is_closed_manual_override` 欄位，人工於「職缺已關閉設定」手動切換時寫入；旗標為 `TRUE` 時，每週爬蟲 `upsert_job_posting()` 的自動 `is_closed` 判斷須跳過該筆，避免蓋掉人工設定；人工再切回「開啟」時同步清回 `FALSE`
- FR-41 實作尚未開始，見 PROGRESS.md 待排入項目

**實作階段**
- Phase 4 Step 4.1～4.3：全數完成

### 平台架構與治理（系統架構總覽／MVP 分期／Schema 治理）

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/robinson.md`
**來源說明**：原記錄於 robinson 母 spec，已於 2026-08-13 併入本文件（系統架構總覽、名詞定義、重要資產、ADR-1、ADR-4、ADR-10、ADR-11）。

**概要**：Robinson 採 Telegram 與 Mobile 雙入口，由現有 `main.py`／`src/` 提供後端商業服務與資料收集流程，搭配 PostgreSQL／GDrive 資料層及 `submodules/` 外部服務 Client。MVP 依複雜度分 Phase 0～5 逐步交付，資料庫 Schema 一律「先審核後執行」並透過 Migration 檔案自動套用。

**名詞定義**：Owner（Robin，唯一免通關密碼者）／使用者（家人，需通關密碼）／通關密碼（一次性，`is_used=1` 後失效）／功能開關（只保留 Robin 專屬技術分享、求職分析與考試成績的啟用控制）。

**重要資產（不可刪除）**：`docs/profile/Robinson.png`（Robinson 大頭照，任何清理/重構操作都必須明確排除此路徑）。

**功能性需求**
- FR-1／FR-3／FR-4：Telegram Bot 接收文字/語音；`/healthz` 極簡端點供 cron-job 每 10 分鐘呼叫（**2026-08-08 修正**：10 個排程檢查改丟背景 daemon thread 執行，避免逾時被 cron-job.org 判定失敗）；AI 統一走 Gemini `gemini-3.5-flash-lite`
- FR-9～FR-12：持久化知識庫、逐則對話紀錄與長摘要正式取消；重構時移除對應路由、狀態、排程與資料表，只保留不落地的 10 分鐘短期上下文
- FR-77：已取消功能須同步移除 Telegram Router／Callback／對話狀態、Mobile HTTP API、背景排程、測試與不再使用的資料表；第一批正式淘汰 `complaints`、`knowledge_base`、`conversation_logs`、`conversation_summaries`。舊 Migration 保留，實際刪除以新向前 Migration 執行

**非功能性需求**
- NFR-1：成本——所有服務一律免費方案
- NFR-2：可用性——Render 15 分鐘無請求休眠，cron-job 保持喚醒
- NFR-3：容量——Neon 免費額度 0.5GB，圖片一律存 GDrive
- NFR-11：資料品質——任何排程自動收集外部資料的功能都須落實 ETL 去重（技術新聞、TOEIC、104 職缺、YouTube 皆適用）
- NFR-12：文件治理——`docs/reference/db_schema.md`／`docs/reference/api_schema.md` 隨開發進度更新，建表與刪表 SQL 先審核後執行
- NFR-13：合規——僅供 Robin 與家人個人非商業使用
- NFR-18：Telegram 功能模式逾時 10 分鐘、未送出草稿保留 30 分鐘；文字草稿只存 Process 記憶體，圖片／錄音只保存 Telegram `file_id`，服務重啟可遺失且不得將金額或健康草稿寫入長期資料表。草稿到期不主動推播，使用者再次操作時才告知
- NFR-19：正式資料庫不得整庫刪除重建或改變既有 `users.id`；資料模型調整優先採向前相容 Migration。既有表不適合擴充時可建立 V2 表，依序完成回填、筆數與關聯驗證、Repository 切換及正式驗收；舊表／欄位須完成引用、外鍵、備份與回滾盤點並取得 Robin 二次確認後，才能以新的向前 Migration DROP

**實作階段**
- Phase 0：專案基礎建設，全數完成
- Phase 1（MVP）：核心平台＋待辦事項＋心情小記，全數完成
- Phase 2：記帳＋體態管理＋重要通知＋系統韌性，全數完成
- Phase 3：個人技能成長＋好友模式，全數完成
- Phase 4：求職模組與 Mobile App Step 4.4／4.5 全數完成；Mobile App 已於 2026-08-12 正式部署，2026-08-14 完成飲食／運動雙輸入模式、AI／人工來源圖例與心情 Emoji 擴充
- Phase 5：Mobile App 生活探索與成果（FR-73～FR-76a）已定案並排入開發
- Phase 6：Telegram 功能模式逾時／草稿保護／自然語言入口與取消功能清理已定案，待拆分為可回退的小階段實作；NFR-14～NFR-15 架構遷移已取消，不再改動目前目錄結構

## 例外處理與邊界條件

| 情境 | 防呆機制 | Error Handling |
| --- | --- | --- |
| 通關密碼重複使用/race condition | 原子性條件 UPDATE（`WHERE is_used=FALSE`） | 第二個並行請求影響 0 筆，非誤判成功 |
| 非 Robin 觸發 Owner 專屬指令 | `auth.is_owner()` 嚴格比對 `telegram_user_id` | 一律無效且不透露此指令存在 |
| 個資輸入 | Regex + LLM 雙層偵測 | 一律遮蔽為 `[已遮蔽個資]`，附提醒文案；語意層失敗優雅降級為僅 Regex 層 |
| Telegram 長按語音超過 10 分鐘 | `duration` 秒數預檢查，不需先下載 | 拒絕處理並整體鎖定語音功能 5 分鐘；上傳音檔不套用此限制 |
| 收到影片或其他不支援檔案 | 只放行文字、Telegram 長按語音、圖片及上傳音檔 | 固定回覆「我只能處理對話框文字、語音、圖片和音檔喔！」 |
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
| `/clean-target-dialog`／彈性排程「平攤」等自動運算的高影響操作 | 一律先呈現運算結果／候選範圍給使用者確認 | 任何無法判斷為確定的回覆一律視為取消，保守優先 |

## 驗收矩陣與已測試情境

| 情境 | 預期結果 | 實測結果 | 狀態 |
| --- | --- | --- | --- |
| 新使用者輸入正確通關密碼 | 綁定成功並收到附錄 A 歡迎訊息 | 符合預期 | 通過 |
| 重複使用同一組通關密碼 | 第二次應失敗 | 符合預期 | 通過 |
| 家人偽造 Owner 專屬 Callback | 權限邊界拒絕 | 符合預期 | 通過 |
| 身分證字號/手機號碼等 8 類個資格式輸入 | 正例遮蔽、生日/LINE ID 不誤判 | 符合預期 | 通過 |
| Telegram 長按語音 9:59／10:00／10:01 邊界 | 未超過放行，超過拒絕並鎖定 5 分鐘 | 符合預期 | 通過 |
| 上傳音檔超過 10 分鐘 | 不套用長按語音的時長上限與鎖定規則，完成轉錄後仍先確認文字 | 符合預期 | 通過 |
| 圖片無說明／有說明 | 無說明時辨識並整理重點；有說明時依說明處理 | 符合預期 | 通過 |
| 影片、Video Note 或其他檔案 | 不處理內容並回覆核准固定文案 | 符合預期 | 通過 |
| 外部 API 前 2 次失敗、第 3 次成功 | 正常回傳，等待時間 1s/2s/4s | 符合預期 | 通過 |
| 外部 API 3 次全部失敗 | 正確拋出原始例外，不包裝新型別 | 符合預期 | 通過 |
| 點擊「使用規則」選單 | 不呼叫 LLM，回傳核准後的精簡固定模板 | 待重構驗證 | 待驗證 |
| `/function` 或「我要看所有功能」 | 不再觸發功能總覽，功能探索改由選單提供 | 待重構驗證 | 待驗證 |
| `/start` | 啟動首次通關密碼驗證，已綁定使用者則重新顯示主選單 | 待重構驗證 | 待驗證 |
| 其他舊 Slash Command | 不執行原功能，所有功能改由選單操作 | 待重構驗證 | 待驗證 |
| 服務模擬「一般感冒級」錯誤 | 使用者收到感冒語句，Robin 收到完整錯誤詳情，未額外呼叫 LLM | 符合預期 | 通過 |
| 服務模擬「重大疾病級」錯誤 | 完全繞過 LLM，使用者與所有家人收到寫死廣播，Robin 收到最高等級告警 | 符合預期 | 通過 |
| Google Drive log 上傳失敗 | 使用者仍正常收到「生病了」，Robin 仍正常收到私訊（缺連結欄位） | 符合預期（優雅降級） | 通過 |
| 記帳/心情小記/體態新增後確認 | 成功時明確成功訊息，模擬 DB 逾時則收到感冒語句且未寫入 | 符合預期 | 通過 |
| FR-16a 高風險操作語音最終確認 | 語音一律拒絕且不清除狀態；打字「確認執行」才執行 | 符合預期 | 通過 |
| TOEIC 軌道一檔名比對＋整包 MP3 切割 | 正確整合題目、排除說明語音誤切 | 符合預期（經真實錄音實測修正） | 通過 |
| TOEIC 軌道二單字題生成 | 8 欄位齊全寫入，重複執行不重複生成 | 符合預期 | 通過 |
| 104 爬蟲分頁請求間隔 | 落在 2～4 秒，未使用瀏覽器自動化套件 | 符合預期 | 通過 |
| 每週四 YouTube 排程 | Robin 收到 Top 3 Markdown 連結，不重複 30 天內已推播 | 符合預期 | 通過 |
| Gemini 呼叫遇 429/404 等真實額度與世代下架問題 | 依序排查並正確判定根因（節流保護 vs 官方額度 vs 模型下架） | 符合預期（多次生產環境實測） | 通過 |
| CloudSQLClient 對含 `%` 字元 SQL 執行 | `params is None` 時不帶第二參數，避免誤觸格式化解析 | 符合預期（2026-08-08 生產事故修復） | 通過 |
