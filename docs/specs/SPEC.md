---
title: Robinson — Robin 與家人們的生活小助手
updated: 2026-11-25
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

Robinson 是一個雙前台架構的家庭生活小助手。2026-11-25（ADR-33）大幅精簡後：Telegram Bot 只負責 Owner 權限管理與待辦事項／生日的單向推播提醒；Mobile App「羅賓森」是運動／飲食／體態、記帳等日常紀錄與查詢，以及待辦事項、生日設定的唯一互動入口。Robin 是產品負責人兼管理者，家人透過通關密碼取得使用權限。核心理念是「越少 UI 設定越好」，所有服務一律使用免費方案，AI 能力由 Gemini API 提供。

## 技術棧與平台策略

| 層級 | 技術/工具/API | 版本 | 狀態 | 備註 |
| --- | --- | --- | --- | --- |
| 後端語言／Runtime | Python | 3.11 | 使用中 | Render 使用 `python:3.11-slim` Docker Image 執行 Flask、Telegram Bot 與背景排程 |
| Telegram 前台（權限管理＋推播） | Telegram Bot API | — | 使用中 | 2026-11 功能大幅精簡：只剩 Owner 權限管理對話流程與待辦事項／生日的單向推播提醒，不再提供選單、一般對話或文字／語音／圖片輸入；`python-telegram-bot` 已移除，改用原生 JSON dict 解析 |
| Mobile 語言／UI Framework | TypeScript + React + React Native + Expo | TypeScript 6／React 19／React Native 0.86／Expo 57 | 使用中（2026-08-12 正式上線） | Mobile App「羅賓森」共用 Web／iOS／Android 程式架構；目前正式交付版本為 Expo Web |
| Mobile Web／路由 | React Native Web + Expo Router | React Native Web 0.21／Expo Router 57 | 使用中 | SPA 頁面、登入導向與各分析／設定頁路由 |
| Mobile 日期輸入 | `react-native-calendars` + DateTimePicker | — | 使用中 | 待辦、生日設定、時間選擇；`expo-image-picker`（飲食拍照／相簿選擇）已隨影像辨識移除一併停用 |
| Web 框架 | Flask | — | 使用中 | 同步架構，webhook 單一進入點 |
| 資料庫 | Neon PostgreSQL（psycopg2 + ThreadedConnectionPool） | — | 使用中 | 不用 ORM；連線池上限低（預設 1～5）配合免費額度 |
| 資料庫 Migration | `src/migrations/` + 開機自動套用 | — | 使用中 | 取代人工貼 SQL；`schema_migrations` 追蹤表 |
| App 登入認證 | bcrypt + PyJWT + Expo SecureStore | — | 使用中 | bcrypt 保存密碼雜湊、JWT Access Token、rolling Refresh Token；原生裝置以 SecureStore 保存 Refresh Token |
| AI 對話/生成 | Gemini API（`gemini-3.5-flash-lite`） | — | 使用中 | 運動熱量估算、飲食營養素拆算等文字生成用途沿用 `GEMINI_API_BOT_KEY`，見下方「AI 模型金鑰分流」 |
| 政府辦公日曆資料 | 中華民國政府行政機關辦公日曆 CSV（政府資料開放平臺） | — | 使用中 | 由 `TaiwanCalendarService` 按年度取得並快取至 `taiwan_calendar_days`，供休假日、補班日顯示 |
| 備援通知 | SendGrid HTTPS API（寄信） | — | 使用中 | 僅供 Telegram 故障備援；2026-08-24 起寄信改走 SendGrid API，取代原本 `smtplib` 直連 Gmail SMTP，因 Render 免費方案封鎖對外 SMTP 埠（見 `docs/ADR/discuss/submodules-core.md` 對應日期條目）。2026-11 功能精簡後，Gmail IMAP 讀信（原供 TLDR 電子報摘要使用）已隨該功能一併移除 |
| 後端容器 | Docker（`python:3.11-slim`） | — | 使用中 | 安裝正式 Python 依賴並以 `python main.py` 啟動 Flask 服務 |
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

**AI 模型金鑰分流**（見 submodules-core 討論紀錄 2026-07-30 條目）：`GEMINI_API_BOT_KEY`（運動熱量估算、飲食營養素拆算等文字生成用途）、`GEMINI_API_PRIVACY_KEY`（個資語意偵測）——每種用途各自一把 Key，額度互相隔離。2026-11 功能精簡後，`GEMINI_API_IMAGE_KEY1`/`KEY2`（影像辨識）、`GEMINI_API_TEXT_KEY`（長文生成/長記憶摘要）、`GEMINI_API_SKILL_GROWTH_KEY`（技術摘要）、`GEMINI_API_JOB_SEARCH_KEY`（契合度評分）、`VOICE_API_KEY`（Groq Whisper）已隨對應功能一併移除。

## 產品藍圖與功能規格

### 平台核心入口（通關密碼驗證／Owner 權限管理）

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/platform-auth.md`、`docs/ADR/discuss/robinson.md`（2026-08-15 Telegram 重構子決策；2026-11-25 ADR-33「砍到陽春版」）
**來源說明**：原記錄於 platform-auth 規格，已於 2026-08-13 併入本文件（原 robinson spec ADR-3、ADR-8 已併入本討論紀錄，內容已被本區塊取代）。

**概要**（2026-11 大幅精簡，見 ADR-33）：Telegram 不再提供任何可見選單或一般對話功能，只剩兩件事：①`/start` 首次通關密碼驗證與綁定；②Owner 專屬「權限管理」（獨立 `/permission` 指令觸發，取代舊版選單按鈕入口）。日常紀錄、資料查詢、待辦事項、生日設定等其餘所有互動全部改由 Mobile App 操作；Telegram 對這些模組只負責待辦事項與生日的單向推播提醒，不經過對話分派。「使用規則」固定模板選單、功能模式切換與草稿保護機制隨選單系統一併移除。

**功能性需求**
- FR-1：`POST /telegram/webhook` 依身分與內容路由到對應處理邏輯
- FR-2：`is_owner` 判斷——比對 `telegram_user_id` 是否等於 `ROBIN_TELEGRAM_TOKEN`
- FR-3：一般使用者在 Bot 私人聊天室點擊 `START` 後，下一則文字才進入通關密碼驗證；成功才綁定 Telegram 身分、令一次性密碼失效並顯示正式選單，失敗不得開啟任何功能。綁定前的圖片、語音、其他指令與多人群組驗證一律拒絕
- FR-4：Owner 專屬「權限管理」引導式流程建立一般使用者（依序詢問家庭稱謂→全名→暱稱，全名必填、暱稱可輸入「略過」跳過，2026-11-26 新增全名，見下方 FR-4a）；系統先建立 `users` 取得主鍵，再產生唯一 6 位數一次性數字通關密碼，Mobile App 使用者 ID 依 `user` 加至少兩位數流水號組成。完成後固定回覆全名、暱稱、使用者 ID、通關密碼及一次性使用提醒
- FR-4b：一次性通關密碼自建立起 24 小時有效，使用成功立即失效；同一綁定流程連續錯誤 5 次後暫時鎖定，須由 Owner 重發。除 Owner 建立完成的必要受控回覆外，訊息與 Log 不得顯示完整通關密碼
- FR-4c：通關密碼連續錯誤 5 次鎖定 30 分鐘，Owner 重發後舊密碼立即失效；已綁定使用者再次 `/start` 只重新顯示主選單。更換 Telegram 帳號須由 Owner 解除舊綁定後重新驗證
- FR-4d：權限管理提供停用／恢復使用者但不提供刪除帳號；停用時撤銷 Mobile Refresh Token 並阻止 Telegram／Mobile 存取，恢復後仍須重新登入或重新綁定
- FR-4a：使用者資料分開保存暱稱、家庭稱謂、全名與授權身分；實際管理權限以 `is_owner` 判斷，Mobile App 顯示角色依其呈現「管理者／使用者」，不得以家庭稱謂承擔授權角色。2026-11-26（migration `0108`）新增 `full_name`（全名）必填欄位——暱稱／家庭稱謂可能重複或無法分辨真實身份（例如不同家人的父母都被稱作「媽媽」），生日推播「自行選擇」對象清單（FR-53）改優先顯示全名
- FR-6a（2026-11 更新）：`/start`（一般使用者首次通關密碼驗證；已綁定者直接視為登入，Owner 免密碼）與 `/permission`（Owner 專屬「權限管理」引導式流程，取代舊版選單按鈕入口）是僅存的兩個 Telegram Slash Command；其餘一般使用者與 Owner Slash Commands、可見選單、Callback 與引導式對話全數移除
- FR-7（安全網）：`telegram_webhook()` 用 `try/except` 涵蓋 DB Client 建立到 `handle_message()` 整段流程，任何未預期例外一律 log + 回覆安全用語，仍回傳 HTTP 200，避免 Telegram 重試風暴燒額度
- FR-7a：`update_id` 去重（LRU 上限 1000 筆）

**非功能性需求**
- NFR-1：安全 — 通關密碼比對與綁定操作用「原子性條件 UPDATE」避免 race condition
- NFR-2：可用性 — Owner 設定對話流狀態存 process 記憶體，服務重啟會遺失，Robin 需重新開始（刻意簡化）
- NFR-3：可維護性 — webhook 路由與命令處理邏輯分層存放

**實作階段**（對應 PROGRESS.md）
- Phase 1 Step 1.1：全數完成，49 個測試全過、覆蓋率 100%

### Gemini 對話核心

**狀態**：removed（2026-11-25，見 ADR-33）
**討論紀錄**：`docs/ADR/discuss/chat-core.md`；移除決策見 `docs/ADR/discuss/robinson.md` 2026-11-25 ADR-33 條目

**概要**：2026-11 大幅精簡後，Telegram 已不再提供任何一般自由對話入口——`src/bot/chat.py`／`voice.py`／`image.py`／`menu.py`／`query.py` 等對話核心、語音、圖片與功能選單相關模組已全數刪除。Telegram 現在只剩兩件事：①`auth.py` 的通關密碼綁定與 Owner 權限管理（新增／停用／啟用／重發通關密碼）；②`todo.py`／`important_days.py` 的單向推播（待辦提醒、生日提醒）。使用者不會再對 Telegram 打字詢問一般問題、傳語音或傳圖片給 AI 處理；所有日常紀錄的新增／查詢改到 Mobile App 進行。本節保留僅供歷史對照，原 FR-1～FR-13 等條目描述的彈性查詢、短期對話上下文、語音/圖片輸入等能力已不存在。

**實作階段**
- Phase 1 Step 1.3／1.3a：原始對話核心設計全數完成並運作至 2026-11
- 2026-11-25（ADR-33）：對話核心、語音與圖片輸入整批移除，Telegram 收斂為「權限管理＋推播」

### 個資偵測與遮蔽機制

**狀態**：active（2026-11-25 範圍限縮，見 ADR-33）
**討論紀錄**：`docs/ADR/discuss/privacy-masking.md`
**來源說明**：原記錄於 privacy-masking 規格，已於 2026-08-13 併入本文件（原 robinson spec ADR-5 個資部分已併入本討論紀錄）。

**概要**：2026-11 隨對話核心整批移除後，`src/bot/privacy.py` 的 Regex／LLM 遮蔽邏輯不再用於「傳給 LLM 前遮蔽 Telegram 聊天內容」（該用途已不存在），改為供 `src/services/app_records.py`／`app_diet_photo.py` 在使用者透過 Mobile App 填寫記帳備註、運動／飲食補充內容等文字欄位時，寫入資料庫前先遮蔽可能含有的台灣常見個資格式。採「Regex 硬規則＋LLM 語意辨識」雙層防線不變。

**功能性需求**
- FR-1：`mask_regex()`——涵蓋 8 類台灣個資格式（身分證/手機/市話/銀行帳戶/信用卡/健保卡/地址/車牌），統一替換為 `[已遮蔽個資]`
- FR-2：`mask_with_llm()`——補足 Regex 抓不到的變形寫法，排除生日與 LINE ID
- FR-3：`mask_text()` 統一入口，先跑 Regex 再跑 LLM
- FR-4：Mobile App 寫入記帳備註、運動/飲食補充內容等自由文字欄位前，`app_records.py`／`app_diet_photo.py` 一律先呼叫 `mask_text()` 才落地資料庫

**非功能性需求**
- NFR-1：額度隔離——語意層用獨立 `GEMINI_API_PRIVACY_KEY`
- NFR-2：不誤傷——生日/LINE ID 一律不遮蔽

**實作階段**
- Phase 1 Step 1.5：全數完成，326 個測試全過、覆蓋率 100%
- 2026-11-25（ADR-33）：原「一般聊天組 Prompt 前遮蔽」用途隨對話核心移除而不再適用，遮蔽邏輯保留並持續供 Mobile App 寫入路徑使用

### Submodules 共用子模組基礎骨架

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/submodules-core.md`
**來源說明**：原記錄於 submodules-core 規格，已於 2026-08-13 併入本文件（原 robinson spec ADR-2、ADR-12、ADR-13 已併入本討論紀錄）。

**概要**：`submodules/` 收斂 Robinson 都會用到的最基礎技術操作，一律不依賴特定框架與本專案商業邏輯。每個子模組資料夾固定四檔案結構（`client.py`／`README.md`／`requirements.txt`／`.env.example`）。

**功能性需求**（依子模組列出核心能力，詳細方法簽章見程式碼與 `README.md`）
- `cloudsql`：連線池管理與泛用 CRUD（select/insert/update/delete），一律參數化查詢
- `telegram`：Bot HTTP Client（文字/圖片/typing 狀態），純文字傳送（不預設 Markdown）
- `llm`：文字/圖文生成呼叫，本地端節流保護（同一 `api_key` 60 秒超過 8 次直接擋下）
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

**概要**：App 定位「分析頁面＋個人資訊／APP 設定＋生活紀錄」的視覺化入口，取代原規劃的 Notion 後台與唯讀 BI Dashboard。細節規劃（首頁卡片、各模組頁面呈現、全域 UX 規則、視覺風格）見 `docs/reference/mobile-app-ux.md`，本區塊僅列架構層決策摘要。登入/選單/個人資訊/APP設定/唯讀分析/體態飲食記錄已於 2026-08-12 正式上線部署（後端 Render＋前端 Vercel），完整路由清單見 `docs/reference/api_schema.md`「羅賓森 Mobile App」區塊。

**2026-11 大幅精簡後的範圍**（見 ADR-33）：App 是待辦事項、生日設定、運動／飲食／體態與記帳四項日常紀錄＋查詢的唯一互動入口（Telegram 不再提供對應選單，只負責待辦與生日的單向推播）；收藏與旅遊、探索地圖、成果展示、跨模組目標追蹤、求職分析、考試成績等頁面與路由已隨對應功能整批移除。待辦事項與生日設定從「唯讀、只能到 Telegram 操作」改為 App 內可直接新增／編輯／刪除的一般頁面，待辦不再有逾期／完成狀態管理（純一次性日期＋文字提醒），生日設定只保留「每年固定（國曆）月/日重複一次」一種形式。下方 FR-64 系列條目中涉及已移除功能（求職、考試、收藏、探索、成果、跨模組目標、心情圖表、飲食拍照模式）的敘述僅供歷史對照，不代表目前實際畫面；現行畫面請以 `mobile/app/` 實際路由與元件為準。

**功能性需求**
- FR-64：分析頁面（記帳、體態等模組圖表）＋生活紀錄與 APP 設定；寫入一律複用既有 service 層函式——已實作
- FR-64a：藍牙體重計整合已全面移除（見上方技術棧「決定不用」），改為手動輸入按鈕「記錄一下」——已實作
- FR-65：帳密登入（使用者ID＋密碼），密碼單向雜湊（bcrypt/argon2），忘記密碼＝重設新密碼透過 Telegram 發送，保持登入 Refresh Token 30 天效期——已實作
- FR-65a（2026-08-23 定案，見 `docs/ADR/discuss/mobile-app.md` 條目）：帳密登入連續密碼錯誤達 2 次即鎖定帳號（`users.mobile_login_locked_at`／`mobile_login_failed_attempts`），登入成功歸零；鎖定不會自動過期，只能由 Owner 在 Telegram「權限管理→🔓 解鎖 Mobile App 帳號」按鈕式手動解鎖；API 回應獨立的 `ACCOUNT_LOCKED` 錯誤碼，與密碼錯誤區分；鎖定觸發當下同步用 Telegram 私訊通知 Owner（見 2026-08-23 續篇條目），不需等家人主動反應——已實作
- FR-67：左上選單導覽＋右上頭像下拉選單，權限矩陣依 `owner_only` 決定可見項目——已實作
- FR-68：個人基本資訊頁面（唯讀）——已實作
- FR-72：APP設定（深色模式／字體大小／隱私數字遮罩／修改密碼）——已實作
- FR-72b：隱私數字遮罩為帳號層設定，Mobile App 與 Telegram 查詢共用 `users.privacy_mask_enabled`；Mobile 可透過偏好設定 API 讀寫，Telegram 資料查詢啟用時將數字字元逐位替換為 `*`
- FR-72a：具明確日期的體態目標（體重／運動／飲食）及考試／證照目標，預設同步為一次性「重要日子」；預設提前 1 天、通知自己並顯示於待辦行事曆，使用者可在重要日子設定調整提醒與通知對象。Telegram 以重要日子保存的提醒天數與通知對象作為唯一期限提醒來源；目標名稱／日期更新時同步更新且保留既有提醒設定，目標達成、取消或清除日期時停用連動事件。既有體態目標固定提前 7 天提醒已取消，避免重複推播。現行記帳只有月份預算，沒有單一完成日期，本階段不納入同步；資料同步與通用 Telegram 重要日子發送器均已實作
- FR-64b（2026-08-18 定案）：分析頁共用日期與紀錄規則——待辦可查 1～7 天，其餘體態、飲食、運動、記帳、心情、求職及考試可查 1～30 天，預設皆為今天往前共 7 天；技術分享維持單日。日期區間結果卡片一律唯讀，依紀錄日期、同日建立時間由新到舊；最下方最近紀錄不受區間影響，今天紀錄可編輯／刪除，刪除維持二次確認與 5 秒復原，歷史紀錄顯示「歷史紀錄請至 Telegram 管理」。區間沒有資料時仍顯示目標摘要及最近紀錄；長清單最高 `60vh` 並在區塊內捲動，不分頁
- FR-64c（2026-08-18 定案；2026-08-19 補充）：所有 Mobile 目標摘要統一顯示期限、目前進度及進度條；多筆時只從進行中目標挑選最近到期者，同日取最近更新者，全部無期限則取最近更新者，其餘由唯讀「查看全部」呈現。無期限顯示「無期限」，無法量化顯示灰色未定進度與「目前無法計算」。數值改善依基準到目標比例，累積型依目前累積除以目標值，考試依最高正式成績除以目標分數；進度限制 0%～100%，超標另標示「已超越目標」。一次性運動里程碑採未完成 0%／完成 100%，由 Telegram 目標清單明確標記，不從一般運動紀錄猜測。Telegram 對所有進行中的體態、飲食、運動、記帳、收藏與考試目標都提供「標記完成」，顯示目標摘要並經按鈕式二次確認後才寫入；自動達成判斷繼續保留，手動完成作為里程碑、非量化目標及必要修正入口。完成操作必須重新驗證目標擁有者與進行中狀態，完成後停用連動的重要日子及既有 Calendar 事件。目標新增／編輯／刪除仍由 Telegram 處理，Mobile 只顯示「請前往 Telegram 設定」而不做深層連結
- FR-64c 呈現順序補充（2026-08-19）：目標摘要固定放在日期區間篩選上方，不受查詢區間影響；體態分析切換頁籤時，摘要跟著切換為該類型目標。
- FR-64d（2026-08-18 定案）：分析頁改版——待辦一般管理只留未過期待處理事項，另設「逾期待辦（N）」供完成、延期或取消；體態分析改為體態／飲食／運動頁籤，分別顯示體重／腰圍／BMI、熱量＋營養摘要、運動時間＋消耗熱量；記帳只保留收入／支出／結餘摘要及收支比較；「心情趨勢」更名「心情小記」並移除圖表；求職採總覽／推薦職缺／應徵紀錄頁籤；考試先切換證照，再顯示目標、練習及正式成績。所有圖表 X 軸同日去重，單日只顯示中央一個日期，多日最多 5 個等距日期；Y 軸顯示 4～5 個刻度，金額／熱量／題數從 0 開始，體重／腰圍／BMI 依資料範圍縮放。求職與考試設定寫入維持 Telegram 專用，Mobile 僅查看分析

**實作狀態（2026-08-19）**：FR-64b～FR-64d 已完成程式實作、push 與 Robin 實機驗收。共用分析頁、收藏清單、探索地圖、成果展示與重要日子設定的首次載入均只顯示「資料載入中…」，資料取得後再完整呈現。求職分析已完成總覽／推薦職缺／應徵紀錄頁籤；考試成績已完成證照切換、目標進度、區間練習表現、弱點與正式成績，無題庫證照顯示說明而不產生空圖表。FR-76b 跨端成果置頂與 migration `0097` 已 push 並完成跨端實機驗收。

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

### 待辦事項

**狀態**：active（2026-11-25 大幅精簡，見 ADR-33；2026-11-26 支援日期區間＋行事曆）
**討論紀錄**：無獨立 ADR，設計決策已於下方需求段落內註明；精簡決策見 `docs/ADR/discuss/robinson.md` 2026-11-25 ADR-33 條目；日期區間與行事曆決策見同檔 2026-11-26 條目
**來源說明**：原記錄於 robinson 母 spec 的 FR-31／FR-31a／FR-31b／FR-32，已於 2026-08-13 併入本文件；2026-11-25 依 Robin 明確決策「待辦事項只是純粹去做通知而已，不需要確認動作，不想增加使用者負擔」全面改版，移除狀態管理、時間區間與 Google 行事曆同步；2026-11-26 因 Robin 反饋「連續多天的行程要建立好幾筆很麻煩」改支援日期區間，並補回行事曆 UI。

**概要**：純「日期（可為區間）＋文字」提醒，不分狀態、不提供確認或完成動作。新增、編輯、刪除全部在 Mobile App 完成；Telegram 不提供任何待辦相關選單或對話流程，只負責讀取並單向推播提醒。

**功能性需求**
- FR-31：Mobile App 新增／編輯／刪除待辦，每筆只有 `content`（文字）與 `remind_start_date`／`remind_end_date`（提醒日期區間，單日時兩欄相同）兩組必要欄位；不提供 `pending`／`completed`／`expired` 等狀態欄位，也不支援 Google Calendar 同步；新增／編輯時透過 `TodoCalendarPicker`（`GET /api/app/calendar?year=&month=` 顯示國定假日／補班標記）選擇日期或區間
- FR-32：Telegram 單向推播——固定在台灣時間每天 08:30（`/healthz` 排程觸發時判斷時間窗）對 `remind_start_date` 等於當天的待辦推播一次，訊息只顯示日期（區間則顯示「起～迄」），不帶時分；去重記號 `reminded_sent_at` 落地於資料列本身以撐過服務重啟；不再提供每日固定摘要、前置提醒視窗或 `/my_todos` 查詢，查詢改到 Mobile App 進行
- FR-31c（2026-11-26 新增；同日兩度修正）：Mobile App 首頁以月曆取代原「重要通知」卡片（見 `mobile/src/components/HomeCalendar.tsx`），週末／國定假日數字顯示為紅色、平日黑色，今天用圓形色塊（比照待辦新增頁行事曆既有的今天標示樣式）框起來，支援左右翻頁檢視上個月／下個月；切換月份時先讀取該月國定假日資料、讀完才顯示，避免「先黑後紅」的色彩跳動。數字下方不顯示任何小字（避免擠在一起看不清楚），待辦事項內容、生日與國定假日名稱改集中顯示在行事曆正下方的「未來一週注意事項」區塊（只列未來 7 天，逐日列出當天的待辦內容、生日、國定假日名稱，沒有任何項目的日子不顯示）；純檢視用途，不支援在月曆上直接點選新增或編輯

**實作階段**
- Phase 1 Step 1.7：舊版「自然語言三輪反問＋狀態管理＋Google Calendar 同步」設計已完成並運作至 2026-11；2026-11-25（migration `0102`）：改版為純一次性提醒，既有資料已清空重來，詳見 `docs/reference/db_schema.md`「待辦事項」
- 2026-11-26（migration `0106`）：`remind_at` 改為 `remind_start_date`／`remind_end_date` 日期區間，新增 `GET /api/app/calendar` 與 `TodoCalendarPicker.tsx`／`HomeCalendar.tsx`

### 記帳

**狀態**：active
**討論紀錄**：無獨立 ADR，設計決策已於下方需求段落內註明
**來源說明**：原記錄於 robinson 母 spec 的 FR-41～FR-44a，已於 2026-08-13 併入本文件（其他 6 份 spec 皆未涵蓋）。

**概要**：每月支出預算上限（非儲蓄目標）＋每日記帳（含補登/修正/刪除完整 CRUD）＋門檻預警＋月報推播。

**2026-11-25 更新（見 ADR-33）**：Telegram 選單與按鈕入口已隨平台核心入口整批移除，下方 FR-41～FR-44a 描述的 `finance:*` Telegram 選單流程為歷史設計，新增／補記／查詢／編輯／刪除現全部改到 Mobile App 操作；FR-41b「儲蓄／淨結餘目標」依附的跨模組 `module_goals` 表已隨目標追蹤功能整批移除（見 `docs/reference/db_schema.md`），記帳目標功能本身也隨之下架，不再提供。

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
- FR-45a（2026-08-17 正式生效，批次3）：主選單新增「🎯 目標追蹤」（`menu.py` `GOAL_TRACKING_MODULES`），點擊後列出已支援目標功能的模組按鈕（飲食、體態、運動、記帳、收藏清單、考試共六個）→ 選模組列出該模組未過期（active 且未超過期限，或無期限）的目標清單，無目標顯示「查無資料」→ 選一個目標顯示最新快取摘要（依「過去一個月」「過去一週」紀錄生成建議與方向、提及距離截止日還有多久，無期限的目標不顯示這段，並附加油打氣文字）；摘要由每日排程（統一凌晨 01:00，`src/services/goal_summary_job.py`，寫入新表 `goal_summaries`）產生快取，Telegram 端只顯示最新一份、不即時生成、不可操作，下方固定只有「🔙 返回主頁面」按鈕。體態/運動/飲食讀 `body_goals`，記帳/收藏清單讀新表 `module_goals`（migration 0085），考試沿用既有 `certificate_goals`，三張來源表結構不同，統一由 `goal_summaries.goal_source` 欄位區分；2026-08-24（Robin 反饋「體態目標摘要應該綜合評估，不能只看體重」）：`body_goals` 三種 `goal_type` 中，只有體重目標改成同時參考體重／運動／飲食三項近期紀錄（體重是運動與飲食習慣共同作用的結果，需要三項一起看才能給出具體建議），運動／飲食目標維持只看自己那一種紀錄——詳見 `docs/ADR/discuss/robinson.md` 對應日期條目
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

### 生日設定

**狀態**：active（2026-11-25 大幅精簡，原名「重要通知／重要日子」，見 ADR-33；2026-11-26 支援多選提前提醒＋推播對象）
**討論紀錄**：`docs/ADR/discuss/notifications.md`；精簡決策見 `docs/ADR/discuss/robinson.md` 2026-11-25 ADR-33 條目；多選提醒與推播對象決策見同檔 2026-11-26 條目
**來源說明**：原記錄於 robinson 母 spec 的 FR-53／FR-53f，已於 2026-08-13 併入本文件；2026-11-25 改版為純生日設定，移除固定節日（農曆）推播、單次事件、通知對象與行程／目標連動；2026-11-26 因 Robin 反饋「生日當天才提醒來不及買禮物」及需要「讓設定的人選可以推播給誰」，補回提前提醒天數（複選）與推播對象三選項。

**概要**：使用者在 Mobile App 設定家人生日（每年固定國曆月/日重複一次，可複選提前 14／7／3 天或當天推播，並選擇推播對象），Telegram 依設定單向推播生日提醒；固定節日（父親節／母親節／中秋／端午等政府行事曆上有名稱的國定假日）另由獨立的「國定假日推播」模組負責，不屬於本區塊。

**功能性需求**
- FR-53：Mobile App 新增／編輯／刪除生日設定，每筆保留姓名、國曆月/日（`birth_month`／`birth_day`）、提前提醒天數（`remind_offsets`，可複選 14／7／3／當天，至少一項）與推播對象（`audience_mode`：`self` 僅限自己／`selected` 自行選擇／`everyone` 所有人，`selected` 模式另存 `audience_user_ids`）；不支援農曆、單次事件或備註
- FR-53f：Telegram 端（`src/bot/important_days.py`）只負責讀取清單並依排程單向推播生日提醒，依 `audience_mode` 決定收件人（`selected` 完全依照勾選名單，建立者未勾選自己則不會收到）；每個提前天數各自獨立去重，沿用既有 `important_notifications_log`（`notification_key` 改用 `birthday_important_day_{id}_offset_{offset}`）

**實作階段**
- Phase 2 Step 2.3：原版固定節日＋生日推播設計全數完成並運作至 2026-11
- 2026-11-25（migration `0103`）：改版為純生日設定，既有單次事件／農曆浮動節日資料視為「不是生日」予以捨棄，詳見 `docs/reference/db_schema.md`「生日設定」
- 2026-11-26（migration `0105`）：新增 `remind_offsets` 複選提前提醒
- 2026-11-26（migration `0107`）：新增 `audience_mode`／`audience_user_ids` 推播對象可選

### 國定假日推播

**狀態**：active（2026-11-26 新增，見 ADR-33 修正後的 robinson.md 條目）
**討論紀錄**：`docs/ADR/discuss/robinson.md` 2026-11-26 條目及「再追加」補述
**來源說明**：ADR-33（2026-11-25）原先把所有固定節日推播整批砍除；2026-11-26 Robin 反饋父親節／母親節／中秋／端午等應該要通知，確認後補回，範圍再擴大為「政府行事曆上任何有名稱的國定假日」。

**概要**：與「生日設定」是獨立模組（`src/bot/national_holidays.py`），不經 Mobile App 設定，使用者無法關閉或調整。父親節（8/8 固定）、母親節（5 月第二個星期日）提前 7 天＋當天各推播一次給所有已綁定 Telegram 的使用者；其餘政府行政機關辦公日曆表上「有名稱、真正放假」的國定假日（中秋、端午、春節、清明、國慶日等，排除純週休二日）只在當天推播一次，不提前。

**功能性需求**
- FR-56：父親節／母親節固定日期計算，提前 7 天與當天各自獨立去重推播給全體已綁定 Telegram 的使用者
- FR-57：其餘國定假日改為掃描 `TaiwanCalendarService` 行事曆資料（沿用既有 `GET /api/app/calendar` 背後的同一份資料來源），只要當天 `is_holiday=True` 且非純週末、`name` 有值即視為國定假日，當天推播一次

**實作階段**
- 2026-11-26：新增 `src/bot/national_holidays.py`，由 `/healthz` 排程觸發，不需新 migration（沿用 `important_notifications_log`）

### 平台架構與治理（系統架構總覽／MVP 分期／Schema 治理）

**狀態**：active
**討論紀錄**：`docs/ADR/discuss/robinson.md`
**來源說明**：原記錄於 robinson 母 spec，已於 2026-08-13 併入本文件（系統架構總覽、名詞定義、重要資產、ADR-1、ADR-4、ADR-10、ADR-11）。

**概要**：Robinson 採 Telegram 與 Mobile 雙入口，由現有 `main.py`／`src/` 提供後端商業服務與資料收集流程，搭配 PostgreSQL／GDrive 資料層及 `submodules/` 外部服務 Client。MVP 依複雜度分 Phase 0～5 逐步交付，資料庫 Schema 一律「先審核後執行」並透過 Migration 檔案自動套用。

**名詞定義**：Owner（Robin，唯一免通關密碼者）／使用者（家人，需通關密碼）／通關密碼（一次性，`is_used=1` 後失效）。2026-11-25（ADR-33）：技術分享、求職分析、考試成績三項功能已隨「功能開關系統」整批移除，「功能開關」一詞不再適用於本專案。

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
| Gemini/Telegram 等外部 API 暫時性失敗 | `submodules/retry` 最多重試 3 次＋Exponential Backoff | 重試耗盡才判定失敗，向上拋出例外 |
| 通關密碼設定流程重啟中斷 | 狀態存記憶體，刻意簡化 | Robin 重新輸入 `/set_invite_codes` 即可，不影響資料正確性 |

## 驗收矩陣與已測試情境

| 情境 | 預期結果 | 實測結果 | 狀態 |
| --- | --- | --- | --- |
| 新使用者輸入正確通關密碼 | 綁定成功並收到附錄 A 歡迎訊息 | 符合預期 | 通過 |
| 重複使用同一組通關密碼 | 第二次應失敗 | 符合預期 | 通過 |
| 家人偽造 Owner 專屬 Callback | 權限邊界拒絕 | 符合預期 | 通過 |
| 身分證字號/手機號碼等 8 類個資格式輸入 | 正例遮蔽、生日/LINE ID 不誤判 | 符合預期 | 通過 |
| 外部 API 前 2 次失敗、第 3 次成功 | 正常回傳，等待時間 1s/2s/4s | 符合預期 | 通過 |
| 外部 API 3 次全部失敗 | 正確拋出原始例外，不包裝新型別 | 符合預期 | 通過 |
| `/start` | 啟動首次通關密碼驗證，已綁定使用者則重新顯示主選單 | 符合預期 | 通過 |
| 記帳/體態新增後確認 | 成功時明確成功訊息 | 符合預期 | 通過 |
| Gemini 呼叫遇 429/404 等真實額度與世代下架問題 | 依序排查並正確判定根因（節流保護 vs 官方額度 vs 模型下架） | 符合預期（多次生產環境實測） | 通過 |
| CloudSQLClient 對含 `%` 字元 SQL 執行 | `params is None` 時不帶第二參數，避免誤觸格式化解析 | 符合預期（2026-08-08 生產事故修復） | 通過 |
