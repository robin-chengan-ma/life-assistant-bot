# Submodules 共用子模組基礎骨架 討論紀錄

> 本檔案彙整原 `docs/specs/submodules-core/SPEC.md` 的 ADR-1～ADR-14，以及原記錄於 robinson 母 spec、與 AI 模型金鑰策略／影像語音上傳流程相關的 ADR-2、ADR-12、ADR-13（因討論的是子模組層級的技術選型，遷移時合併於此）。

## 2026-07-29 [標籤：AI] Gemini API 金鑰拆分策略（原記錄於 robinson SPEC.md ADR-2）

**狀態**：accepted（後續由 ADR-12 條目擴充為四把 Key，見下方 2026-07-30 條目）

**背景**：全員共用同一組 Token 有機率快速耗盡免費額度，且對話與圖像解析的呼叫模式不同。

**討論內容**：比較「每人一組 Token」（額度隔離但免費 Token 數量有限，需求已明確排除）與「單一 Token 全部共用」（實作最簡單但額度風險集中）。

**決策**：申請兩組 Gemini API Token——一組專用於 Telegram 對話視窗，一組專用於圖像解析。

**理由**：分流可降低單一額度被單一功能耗盡的風險，並方便個別監控用量。

**後果**：需在監控模組中分別追蹤兩組 Token 的用量並在接近上限時告警。

## 2026-07-30 [標籤：AI] AI 模型呼叫依用途拆分四把 Gemini Key + Groq Whisper 處理語音（原記錄於 robinson SPEC.md ADR-12，取代先前「語音一律用 Gemini」的決策）

**狀態**：accepted

**背景**：隨功能擴增，AI 任務類型變多：一般問答、影像辨識、語音轉文字、長文生成。若全部共用同一把 Gemini Key，容易讓某一類任務耗盡額度時連累一般問答功能一起停擺。先前曾記錄「語音辨識一律用 Gemini」，本次明確要求改用 Groq Whisper。

**決策**：①依用途拆成四把 Gemini Key：`GEMINI_API_BOT_KEY`（一般問答）、`GEMINI_API_IMAGE_KEY1`/`KEY2`（影像辨識，每次隨機擇一）、`GEMINI_API_TEXT_KEY`（長文/生成類）②語音一律改用 Groq Whisper API（`VOICE_API_KEY`），取代原本規劃的 Gemini STT。

**理由**：四把 Key 分流可避免單一任務類型拖垮其他基礎功能；影像雙 Key 隨機分攤是最低成本的額度分散做法；Groq 的 Whisper 服務在語音轉文字這個單一任務上，免費額度與辨識品質均優於透過 Gemini 間接處理語音。

**替代方案**：維持單一 Gemini Key（已否決，額度風險集中）；所有任務各自申請獨立 Key（已否決，管理成本過高）。

**後果**：`.env.example` 新增 `VOICE_API_KEY`、`GEMINI_API_IMAGE_KEY1`、`GEMINI_API_TEXT_KEY`；原 `GEMINI_API_TOEIC_KEY` 更名為 `GEMINI_API_IMAGE_KEY2`；需要一個「隨機選擇影像 Key」的小工具函式供所有影像辨識呼叫共用。

## 2026-07-31 [標籤：AI] 影像/語音上傳採「先上雲端、後壓縮、再餵給 AI」流程，統一命名規則與 URL 入庫（原記錄於 robinson SPEC.md ADR-13）

**狀態**：accepted

**背景**：使用者上傳的圖片若直接原始尺寸餵給 Gemini，會浪費不必要的 Token 與頻寬；NFR-3 已限制 Neon 免費額度僅 0.5GB、圖片一律不進資料庫，只存 Google Drive URL。

**決策**：①使用者上傳的圖片與語音檔案一律先上傳至 Google Drive，取得檔案 URL 後才進行後續處理 ②圖片在餵給 AI 辨識前統一用 `Pillow` 強制縮放至 1024×1024 以下、轉存為 JPEG 品質 80%（僅記憶體內即時處理，不落地存回 Google Drive）③檔名規則：多益相關檔名含 `toeic` 字樣、其餘一般檔案採「使用者稱呼＋時間戳記＋用途」組合 ④Google Drive 檔案 URL 一律寫入 Neon（新增共用 `media_uploads` 表）⑤語音檔本身也要上傳至 Google Drive 保存原始音檔。

**理由**：先壓縮再辨識可直接降低 Gemini 呼叫的 Token 成本；統一檔名規則讓之後不論人工檢查或程式自動掃描比對都有一致邏輯可循。

**後果**：往後任何涉及圖片/語音上傳的功能模組實作時都必須遵守此流程；`requirements.txt` 需新增 `Pillow`。

**2026-08-02 補充**：Robin 實測語音上傳撞到 Google Drive API `403 storageQuotaExceeded`——查證後確認 Service Account 完全沒有 Drive 儲存額度，上傳到任何一般（非 Shared Drive）資料夾一律失敗；`submodules/gdrive` 已改用 OAuth 2.0（以 Robin 本人帳號身分上傳），流程與檔名/入庫規則不變，只有底層認證方式改變，詳見下方 ADR-10。

## 2026-07-29 [標籤：AI] ADR-1：cloudsql 連線層選用 psycopg2 + ThreadedConnectionPool，不用 ORM

**狀態**：accepted

**背景**：需要決定資料層的連線與查詢方式，選項落在「輕量 SQL wrapper」與「ORM（如 SQLAlchemy）」之間。

**討論內容**：比較 psycopg2+連線池+手寫SQL（輕量、不綁定 schema/model，但沒有型別安全）、SQLAlchemy（型別安全但需為每個功能定義 Model class，與「跨專案重用的通用 CRUD 小工具」目標衝突）、asyncpg（效能較高但需搭配 async 框架，目前是 Flask 同步架構）。

**決策**：選擇 psycopg2 + `ThreadedConnectionPool`，封裝成單一 `CloudSQLClient` class。

**理由**：CRUD wrapper 只需要操作「任意 table + 任意欄位」，不需要預先定義 Model；輕量、依賴少，最符合「可被跨專案重複使用」的定位。

## 2026-07-29 [標籤：AI] ADR-2：telegram Client 用 requests 直接呼叫 Bot HTTP API

**狀態**：accepted

**背景**：`requirements.txt` 已有 `python-telegram-bot`，但該套件是 async-first 設計，若直接包進 submodules，會讓這個「基礎小工具」綁死在特定框架與事件迴圈上。

**決策**：`TelegramClient` class 封裝「發送」相關 HTTP 呼叫，用 requests 實作。

**理由**：發送訊息是最基礎、最常被其他工具需要的操作；不綁定 event loop，才符合「跨專案重用」目標。

**後果**：主專案根目錄 `requirements.txt` 保留 `python-telegram-bot`，供 backend 層處理 webhook 接收與訊息路由使用；兩者分工不衝突。

**2026-08-02 補充決策**：`send_text()` 原本預設 `parse_mode="Markdown"`；Robin 實測「我要看所有功能」時 Telegram 回 `400 Bad Request`，排查後確認是 LLM 自然語言生成的回覆無法保證符合 Telegram 舊版 Markdown 語法，一旦格式不符 Telegram 會整則拒收。改為預設不帶 `parse_mode`（純文字傳送），呼叫端仍可視需要明確傳入。

## 2026-07-29 [標籤：AI] ADR-3：llm Client 採用官方 `google-genai` SDK

**狀態**：accepted

**背景**：Google 已將舊版 `google-generativeai` 標記為 deprecated，統一改用新版 `google-genai`。

**決策**：`LLMClient` 使用 `google-genai`（`from google import genai`），模型固定 `gemini-3.5-flash-lite`（見下方 ADR-6）；資料夾命名為 `llm` 而非 `gemini`，讓對外介面保持穩定。

**理由**：官方目前唯一持續維護的 SDK；舊版套件未來可能無法安裝或取得支援。

**替代方案**：`google-generativeai`（已 deprecated，不採用）。

## 2026-07-29 [標籤：AI] ADR-4：子模組統一採「四檔案結構」，不再用多檔案 + `__init__.py` 的 package 寫法

**狀態**：accepted

**背景**：第一版骨架把每個子模組拆成多個檔案，Robin 認為不夠乾淨、檔案數量也不統一，要求改成固定樣板。

**決策**：往後每個 `submodules/<name>/` 資料夾一律只包含 `client.py`（唯一程式碼檔，內含一個 `XxxClient` class）、`README.md`、`requirements.txt`、`.env.example` 四個檔案，不再使用 `__init__.py`，不再把邏輯拆成多個 `.py` 檔案。

**理由**：統一結構讓任何人（包含未來的 AI agent）看到 `submodules/` 就知道去哪裡找 client、怎麼裝依賴、怎麼設定環境變數。

**後果**：主專案根目錄的 `requirements.txt` 仍是實際部署安裝清單，必須與各子模組的 `requirements.txt` 內容保持同步；各模組的 `.env.example` 只放這個 Client class 建構子需要的最小參數。

## 2026-07-31 [標籤：AI] ADR-5：`LLMClient` 本地端節流保護，計數以 `api_key` 為單位共用（class 層級狀態）

**狀態**：accepted

**背景**：Robin 實測時撞到 Gemini 429，想在「明知道會被官方拒絕」之前就先攔下來。難點在於 `webhook.py` 是每次收到請求都重新 `LLMClient(api_key=...)`，如果節流計數掛在單一 instance 上，每次請求都會拿到全新、計數歸零的 instance，節流形同虛設。

**討論內容**：比較方案 A（節流狀態掛在 class 層級、以 `api_key` 為 key 的 dict，不需要改既有建構模式）、方案 B（`webhook.py` 改成 app 啟動時只建立一次 `LLMClient`，改動範圍與風險較大）、方案 C（拉外部服務如 Redis 做跨 process 共用計數，目前單一 process 部署完全用不到，過度工程）。

**決策**：採方案 A。

**理由**：用最小改動達成目標，不用動既有請求處理流程；以 `api_key` 而非 instance 作為節流單位，更準確反映「額度屬於 Google Cloud 專案」這個事實。

**後果**：`LLMClient` 新增 `LLMQuotaGuardError`、`max_calls_per_minute` 建構子參數（預設 8）；`tests/submodules/llm/conftest.py` 新增 autouse fixture 避免測試間互相汙染。

**已知限制**：節流計數掛在 class 層級（單一 process 內共用），這是方案 A 換取「最小改動」的直接代價——若未來部署改成多 process／多 worker（例如 gunicorn 多 worker），各 process 會各自維護一份獨立計數，實際節流效果會打折（總請求量可能達到 `max_calls_per_minute × process 數`才會被攔下）。目前單一 process 部署下無影響；屆時才需要重新評估升級成方案 C（外部共用計數，例如 Redis）。

## 2026-07-31 [標籤：AI] ADR-6：`LLMClient` 預設模型從 `gemini-flash-latest` 別名改為明確指定的 `gemini-3.5-flash-lite`

**狀態**：accepted

**背景**：即使有 ADR-5 的節流保護仍持續撞 429，Robin 在 AI Studio 實測確認 `gemini-flash-latest` 別名當時解析到 Gemini 3.6 Flash，免費層只有 RPM 5、RPD 20，遠低於預期；別名會隨 Google 發布新模型自動熱切換，新模型上線初期免費層配額通常壓得最緊。

**討論內容**：比較方案 A（改用明確指定版本 `gemini-3.5-flash-lite`，實測 RPM 15/RPD 500，同屬 Gemini 家族零相容性風險）、方案 B（改用 Gemma 4，額度更寬裕但未驗證工具相容性）、方案 C（開通計費升級付費 Tier，涉及 Robin 個人帳務決定）。

**決策**：先採方案 A，Gemma 4 與計費升級留待額度仍不夠用時再評估。

**理由**：方案 A 是「換了保證能動」的最小風險選擇。

**後果**：`_DEFAULT_MODEL` 改為 `"gemini-3.5-flash-lite"`；節流保護門檻（8）仍低於官方新上限（15），但注意本地端節流只防 RPM 沒防 RPD。

## 2026-07-31 [標籤：AI] ADR-7：`generate_with_search()` 固定改用 `gemini-2.5-flash`（superseded by ADR-8）

**狀態**：superseded by ADR-8（2026-07-31，`gemini-2.5-flash` 對新產生的 `GEMINI_API_BOT_KEY` 直接 404，Gemini 2.5 世代整個對新專案關閉存取）

**背景**：換成 `gemini-3.5-flash-lite` 後仍持續 429，且僅限於帶 Google Search 工具的呼叫；排查後在 AI Studio Rate Limit 頁面「Tools」區塊發現 Google Search grounding 免費額度依 Gemini 模型世代分桶——Gemini 2/2.5 世代有 1,500 次/天免費額度，Gemini 3 世代免費額度是 0。

**決策**：`generate_with_search()` 內部固定改用 `gemini-2.5-flash`（享有 1,500 次/天免費 grounding 額度）；其餘方法維持 `gemini-3.5-flash-lite`。

**後果**：新增 `_SEARCH_MODEL = "gemini-2.5-flash"`；Gemini 2.5 系列預計 2026-10-16 停用，屆時需重新評估。

## 2026-07-31 [標籤：AI] ADR-8：Gemini 2.5 世代對新專案關閉存取，`generate_with_search()` 直接移除（supersede ADR-7）

**狀態**：accepted

**背景**：換用新的 `GEMINI_API_BOT_KEY`（新 Google Cloud 專案）後，`generate_with_search()` 開始回傳 404。逐步排查確認：ListModels 層級「看得到」該模型，但用 curl 直接打 `generateContent`（不掛工具/掛工具皆同）回傳明確錯誤「This model ... is no longer available to new users」——模型「看得到」不代表「呼叫得到」，Google 已對新建立的專案關閉 Gemini 2.5 世代的實際呼叫權限。

**決策**：不再嘗試在這把新 Key 上挽救 Gemini 2.5 世代的存取權，直接移除 `generate_with_search()`／grounding 功能（Robin 明確指示「再試下去只是在浪費時間」）。查無答案時改由呼叫端誠實回答不知道（見 chat-core SPEC.md ADR-5）。

**替代方案**：換回舊專案的 Key（已否決，舊 Key 存續狀態不確定）；開通計費（已否決，涉及個人帳務決定）。

**後果**：`submodules/llm/client.py` 刪除 `generate_with_search()`／`_SEARCH_MODEL`／`_used_search()`；確認 `ListModels` 只反映「模型存在於目錄中」，不代表這把 Key 有權限實際呼叫。

## 2026-08-01 [標籤：AI] ADR-9：`voice` Client 用 `requests` 直接呼叫 Groq Whisper 的 OpenAI 相容 REST API，不安裝官方 `groq` SDK

**狀態**：accepted

**背景**：Groq Whisper 轉錄端點本質上是單純的 multipart 檔案上傳，跟 `submodules/telegram`（ADR-2）面對的情況類似，不需要一整包 SDK 就能完成需求。

**決策**：採方案 A（`requests` 直接呼叫 REST 端點）。

**理由**：與 ADR-2 一貫的判斷基準一致，本專案面對的是「單一 REST 端點」而不是「一整套需要 SDK 抽象的能力」。

**替代方案**：官方 `groq` SDK（已否決，目前只需要「語音轉文字」這一個能力，是過度工程）。

**後果**：`VoiceClient.transcribe(audio_bytes, filename, mime_type) -> str`，`response_format="text"` 讓 Groq 直接回傳純文字 body。

## 2026-08-02 [標籤：AI] ADR-10：`gdrive` Client 改用 OAuth 2.0（真人帳號身分），supersede 原本的 Service Account 認證

**狀態**：accepted

**背景**：Robin 實測語音上傳撞到 Google Drive API `403 storageQuotaExceeded`。查證確認 Service Account 本身完全沒有 Drive 儲存額度，用它上傳檔案到任何一般（非 Shared Drive）資料夾一律會失敗；唯二解法是改用 Shared Drive（需付費 Google Workspace，Robin 個人 Gmail 帳號不具備）或改用 OAuth 2.0。

**討論內容**：比較方案 A（改用 OAuth 2.0，以 Robin 本人帳號身分上傳，免費但需一次性互動授權）、方案 B（升級 Google Workspace 開通 Shared Drive，需付費）、方案 C（延後處理，暫時停用語音/圖片雲端備份功能）。

**決策**：採方案 A（2026-08-02，Robin 於 AskUserQuestion 選定「改用 OAuth 以你本人身份上傳（推薦）」）。

**理由**：免費、不需要額外訂閱，一次性互動授權的額外操作成本可接受。

**後果**：`GDriveClient.__init__(refresh_token, client_id, client_secret, folder_id)`；新增一次性本機互動授權腳本 `get_refresh_token.py`；環境變數由 `GDRIVE_KEY_FILE_PATH` 改為三把 OAuth 憑證；OAuth 同意畫面需設為「正式版」，否則測試中狀態核發的 refresh token 只有 7 天效期。

## 2026-08-05 [標籤：AI] ADR-11：新增 `submodules/email`，用 `smtplib` 直打 Gmail SMTP 當 Telegram 故障時的備援通知管道

**狀態**：accepted

**背景**：Robin 驗收 Step 2.4 時提出：如果壞掉的剛好是 Telegram API 本身，`_notify_robin_of_error()` 連私訊 Robin 這件事本身都送不出去，Robin 會完全收不到任何主動通知。

**決策**：①新增 `submodules/email`，`EmailClient.send_text(to, subject, body)` 透過 Gmail SMTP（SSL）②只用標準函式庫 `smtplib`／`email.mime.text.MIMEText`，不安裝第三方套件 ③複用既有 `GMAIL_USER`／`GMAIL_PASSWORD` 環境變數 ④呼叫端只在 Telegram 私訊失敗時才觸發這個備援。

**替代方案**：第三方 Email API（已否決，需額外申請帳號/Key，對極少觸發的備援用途不划算）；Discord/Slack Webhook（已否決，同屬即時通訊 API 風險類別，風險相關性比 Email 更高）。

**理由**：Email 跟 Telegram 是兩個完全獨立的基礎設施，同時掛掉的機率遠低於單一管道。

**後果**：新增 `submodules/email/`；`webhook.py` 新增 `_send_email_fallback()`；Email 本身也失敗只記 log，不再有下一層備援，是刻意的設計邊界。

**2026-08-07 追記**：正式實作讀信方法（`fetch_emails_from_domain_on_date(sender_domain, target_date)`），透過 Gmail IMAP 讀取收件匣，用「寄件者網域比對」而非主旨關鍵字辨識 TLDR 電子報（經 AskUserQuestion 確認，電子報主旨格式不保證固定，網域較穩定）；IMAP `SEARCH SINCE/BEFORE` 只用來粗略縮小範圍，實際比對改用信件 `Date` header 換算台灣時區後精確比對。**同日再修正**：排程需求改為固定台灣時間 23:00 收集「當天」信件，方法簽章從 `fetch_yesterday_emails_from_domain(sender_domain, now=None)` 改為 `fetch_emails_from_domain_on_date(sender_domain, target_date)`，移除子模組內部「now→昨天」的換算邏輯。

## 2026-08-05 [標籤：AI] ADR-12：新增 `submodules/calendar`，用獨立一組 OAuth 憑證（不與 `gdrive` 共用），scope 限定 `calendar.events`

**狀態**：accepted

**背景**：robinson SPEC.md 新增 FR-66（Google Calendar 整合），需要一個能建立/更新/刪除 Google Calendar 事件的子模組。

**決策**：①新增 `submodules/calendar`，方法涵蓋 `create_event()`/`update_event()`/`delete_event()`，用官方 `google-api-python-client` ②認證方式沿用 `gdrive` 的 OAuth 2.0，但使用獨立一組憑證 ③OAuth scope 只申請 `calendar.events`（僅限事件讀寫），不申請完整 `calendar` scope。

**替代方案**：直接複用 `gdrive` 現有的 OAuth 憑證（已否決，兩個子模組的憑證耦合在一起，任一模組出事會互相拖累）。

**理由**：獨立憑證是刻意的設計——`gdrive` 跟 `calendar` 功能語意完全不同，任一組憑證外洩時影響範圍應該互相隔離，符合子模組「連金鑰都不共用」的既有原則；最小權限原則降低憑證外洩時的潛在破壞範圍。

**後果**：需要 Robin 在 Google Cloud Console 額外開通 Calendar API。

## 2026-08-07 [標籤：AI] ADR-13：新增 `submodules/retry` 共用重試工具，作為 ADR-4「子模組彼此獨立、互不 import」的刻意例外

**狀態**：accepted

**背景**：robinson SPEC.md FR-19i 要求所有外部 API 呼叫內建「最多重試 3 次＋Exponential Backoff」機制。目前 6 個既有子模組都各自呼叫外部 API，理論上都需要這段重試邏輯，但 ADR-4 明訂子模組彼此獨立、互不 import。經 AskUserQuestion 確認三個設計問題：程式碼放置方式、判斷「值得重試」的標準、套用範圍。

**討論內容**（程式碼放置方式）：比較方案 A（每個 `client.py` 各自複製一份重試 helper，嚴格遵守獨立原則但 6 份程式碼要各自維護）與方案 B（新增 `submodules/retry` 提供共用的 `call_with_retry()`，重試迴圈只維護一份但打破彼此獨立的原始精神）。

**決策**：採方案 B（2026-08-07，Robin 於 AskUserQuestion 選定「抽成共用 retry 工具」）。`submodules/retry/client.py` 只負責「重試迴圈本身＋backoff 時間控制」，完全不內建任何 SDK 專屬的例外判斷邏輯，`is_retryable` 一律由呼叫端傳入。重試判斷標準採「只重試暫時性錯誤」（連線失敗、逾時、HTTP 429/5xx），永久性錯誤直接往外拋。套用範圍這次只套用到 6 個現有子模組，104 求職爬蟲留待 Phase 4 開工時比照。

**理由**：這是 `submodules/` 底下唯一不是「包裝外部服務」的子模組，是刻意例外，依賴方向單向（其他模組→retry），retry 本身不依賴其他子模組或商業邏輯，仍符合「不依賴 backend/本專案商業邏輯」的精神。`LLMClient` 既有的本地端節流保護刻意設計在 `call_with_retry` 包裹範圍之外，因為節流門檻是時間窗口邏輯，立即重試無法解決。

**後果**：新增 `submodules/retry/`（只用標準函式庫 `time`）；`llm`/`telegram`/`voice`/`gdrive`/`calendar`/`email` 六個 `client.py` 都新增各自的 `_is_retryable_xxx_error()`；未來若某個子模組需要單獨搬到其他專案，需要連帶搬走 `submodules/retry/`（很小，只有一個純函式），是刻意接受的可攜性妥協。

## 2026-08-07 [標籤：AI] ADR-14：新增 `submodules/newsfeed`，用 `requests` + 標準函式庫 `xml.etree.ElementTree` 抓取 RSS Feed，不安裝 `feedparser`

**狀態**：accepted

**背景**：robinson SPEC.md FR-22／FR-23（每日重點技術分享）需要抓取 IThome／TechCrunch 新聞。經 AskUserQuestion 確認兩者都有公開 RSS Feed，採用 RSS 而非另外寫網頁爬蟲。

**決策**：①新增 `submodules/newsfeed`，`fetch_articles_published_on(feed_url, target_date)` ②用 `requests.get()` 下載 RSS（XML），用標準函式庫 `xml.etree.ElementTree` 解析，不安裝 `feedparser` ③RSS `<pubDate>` 是 RFC 822 格式，複用 `email.utils.parsedate_to_datetime` 解析 ④`<item>` 缺少必要欄位一律跳過 ⑤套用 ADR-13 重試機制。

**理由**：RSS 本質就是標準 XML 格式，標準函式庫足以應付這種單純需求，符合「輕量優先」慣例；用 RSS 而非爬蟲，穩定性與合規性都優於解析網頁 HTML。

**替代方案**：安裝 `feedparser`（已否決，多一個第三方依賴）；直接爬取網頁 HTML（已否決，版面隨時可能改版）。

**後果**：新增 `submodules/newsfeed/`，`requirements.txt` 只需要 `requests`；只回傳「標題＋連結」，不解析全文內容（後續於 ADR-29〔skill-growth 討論紀錄〕新增 `fetch_article_content()` 抓全文）。

**2026-08-07 同日修正**：排程需求改為固定 23:00 收集「當天」內容，移除 `fetch_yesterday_articles()` 便利方法，只保留 `fetch_articles_published_on(feed_url, target_date)`。
