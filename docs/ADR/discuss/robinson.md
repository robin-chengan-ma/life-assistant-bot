# 平台架構與治理 討論紀錄

> 本檔案收錄 robinson 母 spec 中，屬於全專案基礎架構與治理層級、不專屬任何單一功能模組的 ADR（ADR-1、ADR-4、ADR-10、ADR-11）。與特定功能相關的 ADR 已分別遷移至對應功能的 discuss 檔案（見新版 `docs/specs/SPEC.md` 各功能區塊的討論紀錄連結）。

## 2026-07-29 [標籤：AI] ADR-1：三層式架構（前台 / 資料層 / 後台）

**狀態**：accepted（後台選型「Notion」的部分 superseded by mobile-app 討論紀錄 2026-08-04 條目，改採 Mobile App；Telegram 前台與 Neon/GDrive 資料層的決策維持不變）

**背景**：需要在免費資源限制下，兼顧「聊天即服務」的體驗與「視覺化查看」的需求。

**討論內容**：比較方案 A（自建 Web Dashboard，完全客製化但開發前端、部署成本高，不符合「越少 UI 越好」）與方案 B（全部塞進 Telegram 含圖表，單一入口但 Telegram 不擅長呈現複雜圖表/表格）。

**決策**：Telegram 作為唯一前台入口；Neon（結構化）+ Google Drive（靜態圖像）作為資料層；Notion 作為選配的視覺化後台。

**理由**：Telegram 天生支援文字/語音、免費、家人已熟悉；Neon/GDrive 免費額度足敷家庭規模使用。

**後果**：Notion 整合可獨立於核心對話邏輯之外開發，允許排在最後或先不做而不影響 MVP 可用性。

## 2026-07-29 [標籤：AI] ADR-4：MVP 分期策略

**狀態**：accepted（Phase 5「Notion 後台」已取消，併入 Phase 4，見 mobile-app 討論紀錄）

**背景**：需求涵蓋 10+ 個功能模組，若全部視為 MVP 會拉長首次上線時間、且違反「MVP」定義。

**決策**：MVP（Phase 1）僅涵蓋「平台基礎設施＋權限治理＋對話核心（含知識庫）＋待辦事項＋心情小記＋健康監控告警」；其餘功能模組依複雜度與相依性分至 Phase 2～4。

**理由**：①待辦事項與心情小記是最高頻、最輕量的日常互動，適合最先驗證聊天式互動的可用性 ②求職與技能成長複雜度高、依賴多個外部資料源，適合核心架構穩定後再疊加 ③記帳與體態管理邏輯相似，適合放在同一 Phase 一起做 ④視覺化後台屬於「錦上添花」的展示層。

**替代方案**：技術棧驗證優先（已否決，使用者感受不到聊天助手的核心價值）；全功能一次到位（已否決，開發週期過長）。

**後果**：實作計畫依 Phase 0～4 逐步展開，各 Phase 完成後才進入下一個 Phase 的詳細 spec 與 TDD 循環。

## 2026-07-30 [標籤：AI] ADR-10：資料庫 Schema 建立採「先審核後執行」流程，並統一記錄於 `src/schema/`

**狀態**：accepted

**背景**：本產品有多張資料表，若每次建表都各自決定欄位設計，容易缺乏一致性；Robin 希望對每一張表的設計保有審核權，同時要有一份「活文件」讓所有人（包含未來的 AI agent）能快速查閱目前的資料庫與 API 全貌。

**決策**：①所有資料表由 Claude 撰寫 `CREATE TABLE` SQL 並負責執行，但執行前必須先呈現 SQL 與設計理由給 Robin，取得明確同意 ②執行完成後立即同步記錄到 `src/schema/db_schema.md` ③所有 API 路由統一記錄於 `src/schema/api_schema.md` ④每張表與每個欄位都必須用 `COMMENT ON TABLE`/`COMMENT ON COLUMN` 附上中文說明，直接寫在 SQL 裡。

**替代方案**：用 migration 工具（如 Alembic）自動產生/管理 schema（已否決，對這個規模的個人專案過重）；不特別記錄、需要時直接連 Neon 查看（已否決，無法在動手改資料庫前先討論設計）。

**理由**：比照 Human-in-the-Loop 精神——AI 可以自主產生方案，但正式對資料庫執行變更前一定要有人核准。

**後果**：Phase 0 Step 0.5（Neon 資料庫初始化）與往後任何需要新增/修改資料表的 Step，都必須先在對話中提出 SQL 草案與理由。

## 2026-07-30 [標籤：AI] ADR-11：ADR-10「先審核後執行」的執行機制改為「Migration 檔案 + 開機自動套用」，取代人工貼 SQL

**狀態**：accepted

**背景**：ADR-10 規定建表前必須經 Robin 審核同意，但沒有規定「同意後由誰、怎麼執行」。實測發現 Cowork sandbox 連不到 Neon、Telegram Bot API、GitHub REST API（`api.github.com`）、Google/YouTube API、Notion API（皆被 sandbox 網路白名單擋下），但 `github.com`（git 協定）可連線，`git push` 實測成功。

**決策**：①新增 `src/migrations/` 資料夾，存放已核准的 SQL，檔名格式 `NNNN_說明.sql`，依序編號、不可回頭修改已套用過的檔案 ②新增 `schema_migrations` 中介追蹤表 ③`main.py` 啟動時自動掃描並依序執行尚未套用的檔案 ④流程仍維持審核精神：Claude 提出草案→Robin 同意→Claude 存成 migration 檔並 commit+push 到 GitHub main→Render 自動重新部署→開機自動套用 ⑤`git push` 一律透過 `GITHUB_TOKEN` + git credential helper 完成驗證。

**替代方案**：Robin 自行連 Neon 主控台貼 SQL（已否決，不符合全自動化目標）；本機 Claude Code CLI 執行（保留作為此方案失效時的備援）；透過 GitHub REST API 自動開 PR（此路徑在 sandbox 內無法直接呼叫，不採用）。

**理由**：這是唯一能同時滿足「人工審核不能省」與「核准後全自動、不用自己動手」兩個條件的作法。

**後果**：往後任何新增/修改資料表，都改為「提案→Robin 同意→Claude 建立 migration 檔並 push」，不再手動於 Neon 主控台執行；`src/schema/db_schema.md` 的紀錄時機從「執行後」改為「push 後」立即記錄。

## 2026-08-14 [標籤：使用者] 技術棧表補齊實際 Runtime、Mobile Web 與部署資料

**狀態**：accepted

**背景**：整併後的 `docs/specs/SPEC.md` 技術棧表雖已列出 Flask、Neon 與 Render，但沒有明確列出 Python、TypeScript、React／Expo、Docker、Vercel 與中華民國政府行政機關辦公日曆，且 Mobile App 狀態仍誤寫為 Placeholder。

**討論內容**：逐項比對 `requirements.txt`、`mobile/package.json`、根目錄 `Dockerfile`、`mobile/vercel.json` 與政府辦公日曆實作，區分正式核心技術、一般底層依賴，以及尚在 DRAFT 的 Leaflet／OpenStreetMap 探索地圖 POC。

**決策**：技術棧表補入 Python 3.11、TypeScript／React／React Native／Expo、React Native Web／Expo Router、Mobile 日期與圖片元件、bcrypt／PyJWT／Expo SecureStore、中華民國政府行政機關辦公日曆 CSV、Docker、Vercel、pytest／pytest-cov 與 Ruff；Render 明確標示為後端部署，Vercel 明確標示為 Mobile Web 部署，Mobile App 狀態修正為 2026-08-12 正式上線。

**理由**：技術棧表應能直接回答系統使用的語言、Framework、資料來源、建置方式與前後端部署位置，不能只列外部服務名稱，也不能保留與實際上線狀態衝突的舊資訊。

**後果**：`docs/specs/SPEC.md` 與實際部署架構一致；Leaflet／OpenStreetMap 仍屬未升級的 DRAFT 功能，本次不提前列為正式使用中的產品技術棧。

## 2026-08-15 [標籤：使用者] Telegram 功能完整盤點與重構前置分類

**狀態**：superseded（已由同日「選單矩陣、統一對話流程與重構執行順序」取代）

**背景**：Mobile App 的生活紀錄、分析、重要日子與生活探索功能已陸續完成並通過正式環境及實體手機驗收；Telegram Bot 仍累積大量指令、多輪狀態、媒體處理與排程推播。重構前需先分辨哪些能力因產品分工而必須留在 Telegram、哪些只是歷史上尚未搬到 App，以及哪些可以合併或淘汰，避免只做目錄或檔案拆分卻保留重複流程。

**討論內容**：初步盤點將 Telegram 職責分為：①Telegram 身分綁定、自然語言對話、知識庫與文字／語音／圖片入口；②因 App 明確不發通知而必須保留的主動推播；③Mobile 只允許今日資料時，由 Telegram 承擔的跨日期補登與歷史資料完整管理；④已取消 App 設定頁後仍由 Telegram 管理的功能開關、目標、證照排程、技術主題及求職設定；⑤Robin 專屬營運、錯誤告警、客訴、資料回填與康復廣播。重要日子設定的自訂事件 Telegram 提醒仍是待討論項目，不能與既有固定節日／生日推播混為已完成。

**決策**：尚未定案。本輪先完成現況與必要性盤點；後續需由 Robin 逐類確認「保留、整併、移往 App、停用」後，才能形成重構範圍與執行順序。

**理由**：Telegram 同時是對話入口、無 App 通知策略下的唯一主動通知通道，以及部分管理功能唯一入口；直接依檔案大小重構會忽略產品職責邊界，也可能誤刪仍無替代入口的功能。

**後果**：在重構規格正式定案前，不修改 `src/bot/` 行為；`docs/specs/DRAFT.md` 的「Telegram 功能完整盤點與重構討論」維持待討論狀態。

### 2026-08-15 後續討論：Telegram 採「功能選單＋引導式對話」

**狀態**：pending

**背景**：現有功能數量與意圖種類已超出純自然語言入口容易理解的範圍。LLM 可能誤判使用者想操作的模組；改用固定指令雖較準確，卻要求開發者與家人記住大量指令，實際使用成本過高。

**討論內容**：使用者提出推翻早期「以純對話為主要操作方式」的可能性，改以 Telegram Bot 可見選單負責功能探索與明確分流；點入功能後，再由對話式流程逐步收集資料、反問與確認。自然語言仍保留作為一般聊天、快速入口與模組內補充說明，不再獨自承擔全部導航與意圖判斷。

**候選方向**：採三層入口：①常駐主選單呈現高頻功能分類；②分類內使用 Inline Keyboard 顯示具體操作；③選定操作後進入既有或重構後的引導式對話狀態。低頻管理與 Robin 專屬功能放入次級選單，避免主畫面過載。

**待確認事項**：主選單分類、每層最多項目、一般使用者與 Robin 的差異、選單返回／取消規則、進行中流程切換方式、自然語言是否允許直接跳入功能，以及哪些舊 Slash Command 僅保留相容而不再要求使用者記憶。

**現況補充**：目前 Telegram 實作是「每位使用者與 Robinson Bot 的私人聊天室」模型。身分以訊息 `from.id` 綁定至 `users.telegram_user_id`，回覆與個人推播也直接送到該使用者 ID，沒有家庭共用群組的資料隔離或群組訊息呈現設計。Webhook 尚未明確檢查 `message.chat.type = private`；若 Bot 被加入多人群組，程式仍可能接收群組訊息，卻嘗試私訊寄件者，且通關密碼可能暴露在群組內。重構時需正式限制身分綁定、個人資料操作與選單互動只能在私人聊天室進行。

#### 已確認子決策：一般使用者首次啟用與通關密碼

**狀態**：accepted（屬本次 Telegram 重構討論的已確認子決策；整體重構範圍仍為 pending）

**決策**：介面及文件一律使用「通關密碼」，不使用「通關密語」。一般使用者第一次開啟 Robinson Bot 私人聊天室並點擊 Telegram `START` 後，Robinson 固定回覆「請輸入通關密碼」。使用者下一則文字才進入通關密碼驗證；驗證正確後才綁定 `users.telegram_user_id`、將一次性通關密碼標記為已使用、初始化使用者功能開關、傳送歡迎訊息並顯示正式功能選單。驗證錯誤時不得建立綁定或開啟任何功能，需顯示錯誤提示並允許重新輸入。

**驗證前限制**：尚未完成身分綁定時，圖片、語音及其他功能指令一律不得執行；多人群組中的 `START` 或通關密碼輸入也不得啟動驗證，需引導使用者改至 Bot 私人聊天室。

**現況差異**：目前尚未建立獨立 `/start` 驗證狀態；未綁定使用者傳送的任何文字都會直接被當成通關密碼嘗試驗證。實作重構時需補上明確的首次啟用狀態與測試。

#### 已確認子決策：管理者專屬「權限管理」選單

**狀態**：accepted（屬本次 Telegram 重構討論的已確認子決策；整體重構範圍仍為 pending）

**決策**：Telegram 正式功能選單依登入身分動態產生。管理者顯示「權限管理」選單；一般使用者完全不顯示此選單。第一階段只整合既有管理能力，包括建立家人帳號／一次性通關密碼，以及管理家人的功能開關；不在尚未討論前自行加入停權、刪除帳號或角色調整等新權限功能。

**安全要求**：隱藏按鈕不等於授權控制。每次進入「權限管理」及執行其 Callback／對話步驟時，後端都必須重新驗證 `is_owner`；一般使用者即使偽造 callback data 或直接輸入舊 Slash Command，也必須拒絕執行且不得讀取其他家人的資料。

**角色定義**：現行管理者即唯一 Owner Robin；若未來需要多管理者角色，必須另行討論資料模型與權限邊界，本次不預先擴充。

#### 已確認子決策：一般對話與選單功能模式切換

**狀態**：accepted

**使用者提案**：①點入 A 功能後，對話在 10 分鐘內聚焦 A；10 分鐘無互動自動回一般對話。②A 模式中點擊 B 選單，立即切換至 B。③A 模式中輸入與 A 無關的內容，自動回一般對話。④除按鈕外，文字或語音只要出現選單正式名稱（例如「權限管理」），Robinson 先詢問是否進入該功能；使用者明確確認後才切換，否則維持一般對話。

**初步評估**：方向可行，能把選單分流的確定性與自然語言便利性結合。狀態至少需保存 `mode`、`feature_key`、`step`、`last_activity_at` 與尚未寫入的 `draft`；10 分鐘逾時可在下一則 Update 到達時惰性判斷，不需要新增常駐計時器。文字與語音共用同一套名稱／別名偵測，語音只先轉文字。

**決策**：①點入功能後保留 10 分鐘功能模式；逾時後於下一則 Update 惰性切回一般對話。②點擊另一功能前，若現有草稿尚未儲存，先詢問是否放棄；確認後才清除草稿並切換。③內容明確與目前功能無關時切回一般對話；語意不確定時先反問，不讓 LLM 單方面丟棄草稿。④文字或語音提到正式功能名稱時先詢問是否進入，確認後才切換。⑤每次切換前先做授權檢查；未授權功能不得顯示、進入或洩漏內容。

#### 已確認子決策：權限管理的使用者建檔、功能授權與推播設定

**狀態**：accepted（其中「客訴資料表永久保留」已被同日「淘汰路由、資料表與後端分層重構」取代）

**使用者提案**：管理者可在「權限管理」設定一般使用者的暱稱與一次性通關密碼。系統需先建立 `users` 資料，取得資料庫 `users.id` 後，再依既有格式組成 Mobile App 使用者 ID（例如 `id = 1` 顯示 `user01`）。Mobile App 對一般使用者顯示的角色統一為「使用者」。設定完成後，Robinson 主動回覆「已設定使用者資料！」並分行顯示暱稱、使用者 ID 與通關密碼。

**功能可見性提案**：一般使用者預設可使用除「技術分享」、「求職分析」、「考試成績」與「權限管理」以外的功能，其他一般功能不再提供開關；未使用時只呈現無資料狀態。「技術分享」、「求職分析」及「考試成績」因涉及爬蟲或固定推播，仍保留授權開關與推播時間設定。「客訴回饋」提議自產品中移除。

**現況差異**：目前通關密碼不是系統自動產生，而是 Robin 在建立家人資料流程中手動輸入；程式先新增 `users`，再把該文字寫入 `invite_codes.code` 並連結新使用者。現行 `users.role` 同時被用作家人稱謂／顯示名稱，部分家庭規則也依賴此值；目前沒有獨立 `nickname` 欄位。功能開關則不限於三個特殊功能，且一般使用者目前可自行切換自己的多項功能。

**決策**：①通關密碼改由系統產生唯一的 6 位數一次性數字密碼，使用後立即失效。②資料模型拆分暱稱、家庭稱謂及授權身分；`is_owner` 繼續作為實際授權依據，Mobile App 顯示角色依其計算為「管理者／使用者」，不得再把顯示角色混入家庭稱謂。③只有管理者能替個別使用者開關「技術分享」、「求職分析」、「考試成績」，一般使用者不能自行開啟；其他一般功能全面提供且不設開關。④三項特殊功能的推播時間採「每位使用者、每項功能」分別設定。⑤「客訴回饋」移除所有 Telegram／Mobile App 入口並停止新增，但保留既有資料與資料表，不執行破壞性刪除。

**建檔完成訊息**：建立使用者與一次性密碼後，Robinson 固定傳送「已設定使用者資料！」，並分行顯示暱稱、使用者 ID、通關密碼及「此通關密碼僅供首次綁定 Telegram 使用，使用後即失效」提醒。Mobile App 使用者 ID 必須在 `users` 建立並取得主鍵後，依 `user` 加至少兩位數流水號組成。

**後果**：實作時需新增使用者資料欄位、重整功能開關資料與授權檢查、建立個別推播時間設定，並停止客訴入口。Migration 必須保留既有資料、提供相容轉換及回滾策略；在 SQL、API、測試與 Reference 同步完成前，不得宣稱本決策已實作。

#### 已確認子決策：「使用規則」選單與功能總覽移除

**狀態**：accepted

**決策**：原 `/rule` 改為 Telegram 選單並命名為「使用規則」。點擊後只回傳固定模板，不呼叫 LLM、不進入功能對話模式。模板刪除「服務使用須知」第 2、4 點、「使用限制與規範」第 5 點及完整「貼心小撇步」段落；「隱私承諾」中的「聊天記錄」改為「日常紀錄」。原 `/function`、中文觸發詞「我要看所有功能」及其功能總覽／細節追問流程全部移除，不提供替代指令，功能探索改由可見選單負責。

**理由**：使用規則是已核准的固定內容，不需要 LLM 判斷；功能總覽的目的已由 Telegram 可見選單取代，繼續保留 `/function` 只會形成重複入口與維護成本。

**補充決策**：新版精簡模板仍在首次綁定成功時主動傳送；刪除中間條目後，剩餘條目必須重新連號，不保留跳號。

**後果**：實作時需移除 Router 觸發詞、`/function` 專用 LLM 流程及不再使用的功能清單模板，並更新靜態規則模板與測試；在此之前現行指令仍可能運作。

#### 已確認子決策：全面移除 Slash Commands，僅保留 `/start`

**狀態**：accepted

**決策**：Telegram 使用者操作全面改由可見選單與選單內引導式對話完成。`/start` 是 Telegram START 按鈕啟動首次通關密碼驗證及重新顯示主選單所必需的唯一技術例外；除此以外，現有一般使用者與 Owner Slash Commands 全部移除，不設相容期。使用者輸入舊 Slash Command 時不得執行原功能，應視為一般文字處理。Owner 的權限管理、康復廣播、錯誤處理、技術分享、求職及考試操作也必須提供對應的 Owner 專屬選單，不得要求記憶隱藏指令。

**自然語言邊界**：移除的是 Slash Commands 與必須逐字輸入的固定操作格式，不是自然語言能力。文字或語音提到正式功能名稱時，仍依已確認的模式切換規則先詢問是否進入該功能；確認後才切換至選單功能對話。

**理由**：功能數量已超過使用者能合理記憶的範圍；同一能力同時維護指令、中文固定句及選單會造成路由衝突與測試成本。可見選單可提升功能探索性，並讓權限差異直接反映在介面上。

**後果**：重構時需盤點並移除 Router 內所有非 `/start` 的指令常數、正規表示式指令與說明文字，將每項仍保留的操作映射至選單／Callback／引導對話，並補上舊指令不再執行及偽造 Callback 權限檢查測試。

#### 已確認子決策：一般對話的責任邊界

**狀態**：accepted

**決策**：一般對話只負責：①彈性查詢使用者自己的結構化資料；②解釋、摘要、改寫與優化使用者提供的內容，但不執行需要即時上網的查詢；③需求不明確時協助導向正確選單；④解析使用者提供的圖片、長篇文字與錄音，進行內容辨識、轉譯、重點整理或建議。Telegram 系統層另負責推播、提醒及提供 Mobile App 新密碼，但不屬於一般對話。

**寫入限制**：一般對話不得直接新增、更新或刪除正式資料，也不得猜測使用者想操作的模組；正式資料異動必須進入對應選單流程，完成欄位驗證與確認後才可執行。

**排除範圍**：即時新聞、天氣、路況、價格、店家營業狀態及其他需網路查詢的資訊不在一般對話能力內；缺乏資料來源時必須明確說明無法確認，不得虛構。

#### 已確認子決策：移除持久化知識庫與對話記憶

**狀態**：accepted（其中「三張持久化知識／對話資料表永久保留」已被同日「淘汰路由、資料表與後端分層重構」取代）

**使用者提案**：因一般對話已縮限，評估移除 Robin／家庭背景知識庫、使用者個人知識庫及對話資料庫。

**現況影響**：`knowledge_base` 目前保存 Robinson 人格、Robin 與家人背景及使用者自建知識；`conversation_logs` 保存遮蔽後的逐則對話；`conversation_summaries` 保存跨對話的長記憶。若全部停用，個人結構化資料查詢、單次圖片／文字／錄音整理仍可運作，但 Robinson 不再跨時間記住自由文字背景、使用者教過的知識或先前聊天內容。

**決策**：①Robinson 固定語氣與基本人格改為程式內靜態 System Prompt，不再由資料庫載入。②停用家庭背景與使用者個人知識庫，不再讀取、新增或提供知識刪除流程。③停止寫入逐則對話與產生長記憶摘要，不保留跨時間聊天內容。④保留只存在程式記憶體、10 分鐘到期且不寫 DB 的短期上下文，供同一段摘要、改寫或分析的連續追問使用；切換功能時一併清除。⑤既有 `knowledge_base`、`conversation_logs`、`conversation_summaries` 表與歷史資料保留，程式停止讀寫，不執行破壞性刪除。

**後果**：個人結構化資料查詢與單次圖片／文字／錄音處理不受影響；Robinson 不再跨時間記住自由文字背景、使用者教過的知識或先前聊天。實作時需移除知識載入／寫入、對話落庫、摘要排程及相關清除入口，並確保 10 分鐘暫存不包含正式資料寫入草稿。

#### 候選機制：「排程設定」選單

**狀態**：superseded（已由同日「選單矩陣、統一對話流程與重構執行順序」取代）

**使用者提案**：Telegram 增加「排程設定」選單。點擊後自動列出該身分目前可使用、且實際具有排程的功能，並顯示每項功能的排程時間與頻率；不需要排程的功能不得出現在清單。

**原待確認事項**：①選單只供 Owner 管理所有人，或一般使用者也能查看／修改自己的排程。②哪些排程允許修改，哪些屬系統內部固定工作只能查看。③同一功能有多個時間點時如何呈現與修改，例如考試每日出題與晚間提醒、記帳每日提醒與月底月報。④關閉特殊功能時完全隱藏，或顯示為「未啟用」。⑤一次性事件提醒與每筆待辦相對提醒是否算排程設定，或只列週期性排程。上述問題已由後續 accepted 決策統一收斂。

#### 已確認子決策：Telegram 推播、成果候選與系統通知邊界

**狀態**：accepted

**背景**：一般功能開關移除後，若繼續對每項生活紀錄固定催促，未使用該功能的人仍會每天收到無關通知。另一方面，Mobile App 明確不發 App 通知，待辦、重要日期、記帳風險與非同步結果仍需要 Telegram 主動送達。

**決策**：Telegram 主動通知只保留下列產品事件：①待辦事項提醒；②重要日子提醒；③每月底自動記帳月報；④預算使用率達 50%／80% 的分級警示；⑤職缺資料已寄出等低頻非同步結果；⑥已啟用的技術分享、求職分析及考試成績固定推播；⑦目標或旅遊行程等里程碑正式完成時，詢問是否加入成果展示。飲食、運動、體態、心情與記帳等日常紀錄催促，以及沒有獨立價值的「新增／更新／刪除成功」Telegram 通知全部移除；使用者主動操作的成功或失敗只在原 App 畫面或 Telegram 對話內即時回覆。

**成果候選規則**：系統偵測到目標達成、行程完成或其他 FR-76 候選時，Telegram 使用固定訊息及「加入成果展示／略過」按鈕詢問，不交由 LLM 判斷且不得自行建立。候選同時顯示於 Mobile App；任一端完成接受或拒絕後，另一端同步更新。同一 `candidate_key` 只詢問一次，拒絕後不得重複提示。

**重要日子單一來源**：體態／飲食／運動與考試／證照等具有明確日期的目標，以及選擇同步的旅遊行程，統一建立連動的重要日子。Telegram 依該事件保存的提前提醒天數與通知對象送出提醒；目標名稱或日期變更時同步更新，達成、取消、清除日期或停用同步時停用事件。既有體態目標固定提前 7 天提醒必須移除，避免與重要日子預設提前 1 天或使用者自訂天數重複推播。

**系統操作結果**：同步操作成功只在原對話或 App 顯示確認；失敗時保留尚未送出的輸入、顯示安全錯誤並提供重試。背景工作成功只有在產物本身需要送達時推播；可自動重試的零星錯誤只記錄 Log，達到嚴重、持續或影響使用者的門檻才通知 Owner，避免告警疲勞。

**Owner 異常與康復通知**：未預期 Webhook 例外維持「使用者收到安全訊息、Owner 收到錯誤摘要／錯誤 ID／完整 Log 連結、Telegram 失敗時 Email 備援」。背景排程錯誤重構為統一的嚴重度與去重策略。原 `/recovered` 改成 Owner 專屬選單「發送康復通知」；只有先前事故確實影響使用者時才使用，發送前顯示收件對象並要求二次確認，不做自動廣播。

**現況差異**：目前成果候選主要由 Mobile App 顯示；自訂重要日子尚無通用 Telegram 發送器；體態目標仍有固定提前 7 天排程；部分背景排程例外只寫 Log；康復通知仍靠 `/recovered`。以上均屬本次 Telegram 重構待開發範圍，不得把資料已同步到 `important_days` 誤報為提醒已完整上線。

#### 2026-08-15 決策修正：特殊功能改為 Robin 專屬

**狀態**：accepted（supersedes 本文件同日「權限管理的使用者建檔、功能授權與推播設定」中允許管理者替一般使用者開啟三項特殊功能的決策）

**背景**：前一輪曾規劃由 Owner 針對個別家人授權「技術分享」、「求職分析」與「考試成績」。Robin 進一步確認這三項功能只供自己使用，非管理者沒有任何使用情境，因此不需要建立家人授權與個別推播設定。

**決策**：①「技術分享」、「求職分析」、「考試成績」永久限定 Robin／Owner 使用；非管理者在 Telegram 與 Mobile App 都不得看見入口，後端亦須拒絕存取。②「權限管理」不提供三項特殊功能的家人授權開關。③三項功能若仍需啟用／停用或調整排程，只管理 Robin 自己的設定，不建立每位使用者、每項功能的授權或推播時間。④一般生活功能仍對所有已綁定使用者直接開放且不設功能開關。

**理由**：不存在的非管理者使用情境不應產生額外資料模型、權限流程、Mobile 可見性邏輯與測試組合；直接以 Owner-only 授權規則最簡單且最安全。

**後果**：實作時需移除一般使用者自行開關與 Owner 代管家人特殊功能的流程，選單與 API 一律用 `is_owner` 做後端授權。既有 `feature_toggles` 資料表與歷史資料先保留，不因本次重構執行破壞性刪除；是否沿用 Robin 自己的三項開關由後續「排程設定」實作決定。

**Mobile App 影響範圍**：①一般使用者的左側選單與首頁不得顯示「技術分享」、「求職分析」、「考試成績」，Robin 維持可見；前端隱藏之外，對應 App API 也必須以 `is_owner` 拒絕非 Owner 存取。②個人基本資訊須配合使用者資料模型，顯示獨立暱稱及依授權身分換算的「管理者／使用者」，不得沿用家庭稱謂當角色。③「客訴回饋」須從 Mobile App 選單與頁面入口移除，既有客訴資料與資料表保留。④成果候選仍須與 Telegram 共用狀態；任一端接受或略過後，另一端同步更新。⑤Mobile App 維持不發系統通知；待辦、重要日子、預算警示、非同步結果與成果候選等主動通知仍由 Telegram 負責，App 只呈現資料與操作結果。⑥Owner 系統錯誤的 Telegram／Email 送達狀態若需在既有 Mobile 系統錯誤管理頁呈現，必須由共用 API 回傳，App 不直接寄送 Email 或 Telegram。

**Mobile App 實作邊界**：上述均屬 Telegram 重構的跨端相容工作，目前只完成規格定案，尚未修改 `mobile/`、App API、Migration 或測試；不得把既有部分入口隱藏或資料同步能力誤報為本次重構已完成。

#### 已確認子決策：Email 備援通知狀態

**狀態**：accepted

**決策**：Telegram 無法送達 Robin 專屬錯誤通知時，以寄至 `GMAIL_USER` 的 Email 作為最後一道主動通知；Email 成功後不再重複通知或於 Telegram 康復後補發。系統錯誤管理須保存並顯示最後通知方式、通知時間及 `Telegram 已送達／Email 備援已送達／未送達` 狀態。兩種管道都失敗時只保留錯誤紀錄與伺服器 Log，不新增第三種備援。此機制不適用一般使用者推播。

**實作狀態**：現行程式已有 Telegram 失敗後寄 Email，但尚未保存 Email 成功與否；送達狀態欄位、Owner 選單呈現與測試仍待 Telegram 重構實作。詳細決策見 `docs/ADR/discuss/service-resilience.md` 2026-08-15 條目。

### 2026-08-15 後續討論：淘汰路由、資料表與後端分層重構

**狀態**：accepted

**背景**：Telegram 功能盤點已取消客訴、持久化知識庫、逐則對話紀錄、長記憶及非 `/start` Slash Commands。Robin 進一步要求重構不能只隱藏選單或停止呼叫，還要移除不再使用的路由與資料表，並讓後端程式符合既定 Coding Style 與 `api → services → repositories → DB／外部 API` 單向依賴。

**決策**：不再使用的功能不能只隱藏入口或停止呼叫，必須同步移除 Telegram Router 分支、Callback／對話狀態、Mobile HTTP API、背景排程與測試。`complaints`、`knowledge_base`、`conversation_logs`、`conversation_summaries` 列入正式淘汰範圍；對應客訴、知識新增／刪除、對話清除與長摘要流程一併移除。`feature_toggles` 仍被 Robin 專屬的技術分享、求職分析及考試成績使用，現階段保留；其他資料表、`users` 舊欄位及媒體資料仍須依實際引用逐一稽核，禁止只按名稱猜測刪除。

**重構方向**：現有 `main.py` 與 `src/` 最終歸入根目錄 `backend/`；`mobile/` 維持根目錄獨立。後端拆為 `api/`、`services/`、`repositories/`、`agents/`、`jobs/`、`validators/`、`config/`、`lib/`、`utils/` 與 `migrations/`，每層再依功能領域拆子資料夾。第一階段不建立未使用的 `schemas/`；未來若出現跨 API 共用 DTO／序列化模型，再依實際需要新增。重構不得重新形成巨型 `commands.py` 或 `router.py`。

**資料清理原則**：既有建表 Migration 保留作為歷史，不得刪除或改寫；確認不再被程式、排程、Mobile、測試或外鍵引用後，以新的向前 Migration 移除資料表／欄位。執行 DROP 前須列出資料量、外鍵、依賴、備份或匯出策略、回滾方式並再次取得 Robin 明確確認；Migration、Repository、API、測試與 DB／API Reference 必須同一階段同步。

**執行邊界**：採分階段相容遷移，不把資料清理、`src/bot` 拆分、頂層搬移與部署入口切換合成一個不可回退的大改版。四張表確定列入刪除計畫，但執行 DROP 前仍須依高風險操作規範列出資料量、外鍵、依賴、備份／匯出選項與回滾方式，並再次取得 Robin 明確確認。

#### 2026-08-15 目錄責任邊界補充

**狀態**：accepted

**使用者意見**：同意先移除不再使用的路由與資料表，再分階段重構；`mobile/` 應維持根目錄獨立層級，不歸入後端。另提出不建立 `schemas/`，並重新檢視爬蟲、Telegram Bot 與 LLM 是否應歸類至 `data/`。

**釐清**：程式架構中的 `schemas/` 指 API／表單的輸入輸出資料結構與驗證程式，不是 Markdown Schema 文件。現有專案未使用 Pydantic／Marshmallow 等獨立 Schema 層，依「用到才開」原則，重構第一階段不建立空的 `schemas/`；驗證可先放在各功能 Service 的小型 validator，未來真的出現跨 API 共用 DTO 再建立。

**決策**：①`mobile/` 保持根目錄獨立。②現有 `src/` 與 `main.py` 歸入 `backend/`；Telegram Webhook、選單、Callback 是後端輸入介面，不能歸類為資料處理。③Gemini 對話、Prompt 與 Tool 是後端 `agents/`，因其參與即時商業流程與回覆，不屬於 ETL／Data Pipeline。④只有可獨立執行的資料收集、清洗與標準化流程才放 `data/`，例如 104 職缺、技術新聞／RSS、YouTube 等爬蟲；排程觸發、權限、寫入規則與推播仍由後端 Service／Job 負責。⑤外部服務通用 Client 繼續放 `submodules/`，不得把專案商業流程搬進共用封裝。⑥第一階段不建立 `schemas/`，欄位驗證依功能放入 `validators/`；跨 API 共用 DTO 出現後才新增 Schema 層。

**實作注意事項**：爬蟲目前由 `/healthz` 觸發且與後端流程耦合；搬移時需逐支確認哪些可抽成具有獨立入口的 `data/` Pipeline，哪些只是後端 Service 呼叫的外部 API Client。目錄分類以實際責任與依賴方向為準，不以「會產生資料」作為放入 `data/` 的唯一條件。

### 2026-08-15 後續討論：選單矩陣、統一對話流程與重構執行順序

**狀態**：accepted（補充並局部取代同日「一般對話與選單功能模式切換」及「排程設定」的未定細節）

**背景**：Telegram 大重構已有選單化、權限、通知與後端分層方向，但仍缺少完整角色選單、首次綁定安全邊界、功能對話生命週期、資料查詢區間、跨模組通知及分階段搬遷規則。若直接搬動程式碼，容易把尚未定案的產品行為固化在新架構中。

**角色與選單決策**：系統只設 Robin／Owner「管理者」與家人「使用者」兩種授權角色，不預先擴充多層角色。一般使用者主選單依序提供「日常紀錄、資料查詢、待辦事項、重要日子、收藏與旅遊、成果展示、排程設定、使用規則」；管理者另顯示「權限管理、技術分享、求職分析、考試成績、發送康復通知」。日常紀錄第二層整合飲食、運動、體態、心情與記帳；收藏與旅遊第二層整合新增／查看收藏、建立／查看行程及標記已造訪。探索地圖維持 Mobile App 視覺入口，不塞入 Telegram 地圖操作。Owner-only 功能除介面隱藏外，後端必須拒絕非 Owner Callback、舊入口及 API 存取。

**首次綁定決策**：一次性 6 位數通關密碼自建立起 24 小時有效，成功使用立即失效；同一綁定流程連續輸入錯誤 5 次後暫時鎖定，須由 Owner 透過「權限管理」重發。系統訊息與 Log 不得顯示完整通關密碼；Owner 建立完成時的必要回覆屬唯一受控顯示。`/start` 後依序完成通關密碼驗證、Telegram 身分綁定、使用者 ID 顯示及正式主選單呈現。

**統一功能流程決策**：所有會異動資料的選單統一採「進入功能 → 收集資料 → 驗證 → 摘要 → 二次確認 → 寫入與結果回覆」，並提供返回上一步、取消、回主選單、查看目前輸入及重新填寫。每位使用者同時只有一個作用中功能模式；功能模式 10 分鐘無互動後於下一則 Update 惰性回到一般對話。尚未送出的草稿獨立保留 30 分鐘；切換功能時若有草稿，必須讓使用者選擇「保留草稿並切換／放棄草稿／繼續編輯」，不得由 LLM 自動丟棄。只有明確提到其他功能、取消或換話題時才建議切換；語意模糊先追問。文字與語音共用功能名稱及別名偵測，辨識後仍須明確確認才進入功能。

**資料查詢決策**：一般對話與「資料查詢」只能讀取目前使用者自己的正式結構化資料，不顯示密碼、Token、內部識別值，不產生或執行任意 SQL，也不能直接新增、修改、刪除或大量匯出資料。查詢日期不限制為最近 7 天或最近 30 天；使用者可指定任意起始日期，但單次查詢區間長度只能選 7 天或 30 天。需要修改資料時導向對應選單。

**排程與通知決策**：「排程設定」只列實際會主動推播的待辦、重要日子、目標日期、旅遊日期、月底記帳月報、預算 50%／80% 警示，以及 Robin 專屬技術／求職／考試排程。介面只提供是否啟用、提前多久、推播時間與通知對象等產品欄位，不暴露 Cron 表達式或任意執行頻率。各功能只產生領域事件，由統一通知服務負責規則判斷、去重、Telegram 發送及 Robin 系統錯誤的 Email fallback；保存通知類型、接收者、預計／實際時間、管道及結果狀態，不保存敏感原始錯誤。

**跨模組決策**：目標與選擇同步的旅遊行程不得複製成彼此獨立的重要日子，重要日子需保存來源類型及來源 ID，並隨原始名稱、日期、取消與同步狀態連動。目標達成只建立成果候選，由 Telegram 與 Mobile 共同詢問；同一候選以唯一鍵防止跨端重複建立，任一端接受或略過後另一端同步狀態。

**重構順序決策**：先定案並實作認證／使用者綁定，再依序處理 Telegram 選單與狀態機、一般對話與 Agent、通知與排程、Robin 專屬功能、獨立爬蟲搬入 `data/`、舊路由／死程式清理，最後才執行資料表 Migration。大量檔案搬遷、部署入口切換、Telegram 行為改版、API 淘汰及資料表 DROP 不得放在同一個不可回退批次。每批須補單元測試、API 整合測試及 Telegram 私人聊天室實機驗收；DROP 仍須依既定規則完成資料量、相依、備份與回滾盤點並再次取得 Robin 明確確認。

**後果**：上述規則正式排入 Phase 6，但目前只完成文件定案，尚未修改程式碼、API、Migration 或部署。實作前應先依本決策產出逐批檔案對照與測試計畫，不得一次完成整個大重構。

#### 2026-08-15 決策修正：歷史異動邊界、七日查詢與帳號／草稿／排程細節

**狀態**：accepted（supersedes 上一條目中「查詢區間可選 7 天或 30 天」及尚未具體定義的帳號停用、草稿保存與排程權限）

**使用者確認**：Telegram 必須支援生活紀錄的新增、修改、刪除與歷史回補；Mobile App 仍只允許異動今日生活紀錄，待辦、重要日子、收藏、旅遊與成果等既有不限今日功能維持原規則。兩端「完全一致」指相同功能共用欄位定義、必填規則、數值範圍、驗證邏輯及讀取結果，不代表 Mobile 取得歷史生活紀錄寫入權限。

**資料查詢修正**：單次查詢最多 7 個曆日，不再提供 30 天選項。使用者選擇「最終日期」，系統以該日往前推 6 天形成含首尾的查詢區間；最終日期可透過行事曆或自然語言指定，也可位於未來。一次查詢可選多個模組；未來資料只回傳該模組實際存在的待辦、重要日子、目標、行程或其他未來紀錄，不虛構尚未發生的生活資料。Telegram 查詢結果須沿用 Mobile App 的隱私數字遮罩偏好，因此該設定須改為帳號層、由後端保存並供雙端共用，不能只保存在單一裝置。

**帳號安全細節**：通關密碼連續錯誤 5 次鎖定 30 分鐘；Owner 重發後舊密碼立即失效。已綁定使用者再次 `/start` 只重新顯示主選單。更換 Telegram 帳號須由 Owner 解除舊綁定後重新驗證。權限管理新增停用／恢復使用者，但不提供刪除帳號；停用時撤銷 Mobile Refresh Token、阻止 Telegram 與 Mobile 存取，恢復後仍須重新登入或重新綁定。此決策取代先前「第一階段不提供停權」的限制。

**草稿細節**：一般文字草稿只保存在後端 Process 記憶體，接受 Render 重啟後遺失；圖片與錄音草稿只保存 Telegram `file_id`，不重複保存媒體內容。草稿 30 分鐘到期時不主動推播，使用者再次操作才告知逾時；金額、健康資料等草稿不得為了續存而寫入長期資料表。

**排程權限細節**：一般使用者只能查看及調整自己的接收設定；重要日子的建立者可設定通知對象。Owner 可代管家人設定，但每一步都必須顯示目前操作對象。月底月報產生等系統固定工作不可修改執行頻率，只能調整是否接收及允許的通知時間。關閉提醒只停止通知，不刪除待辦、目標、重要日子、行程或其他來源資料。

**後果**：Phase 6 需新增帳號層隱私遮罩同步、通關密碼鎖定／失效、使用者停用／恢復及 Refresh Token 撤銷能力；Telegram 各生活紀錄流程則必須共用 Mobile 已有的 Service 驗證，避免兩套欄位與數值規則漂移。上述均尚未實作，涉及 DB／API 時須同步 Migration 與 Reference。

#### 2026-08-15 補充決策：Mobile 日期特例與資料庫漸進遷移

**狀態**：accepted

**背景**：Mobile App 不受「僅能異動今日生活紀錄」限制的功能不只待辦事項；Telegram 重構新增帳號鎖定、停用、通知狀態與跨端隱私偏好後，也可能需要調整既有資料模型。需避免因描述不完整而誤縮 Mobile 權限，或為追求重構速度直接刪除正式資料庫重建。

**決策**：①Mobile App 只有飲食、運動、體態、心情與記帳等生活紀錄維持「只異動今日」；待辦事項、重要日子、收藏清單、旅遊行程、探索紀錄與成果展示依各自正式規格管理不同日期。探索紀錄沒有獨立新增入口，仍由收藏標記已造訪或完成行程產生，但既有探索紀錄可依正式規則管理。②本專案不整庫刪除重建，不改變既有 `users.id` 或已建立的正式資料關聯。③新需求優先以向前相容 Migration 新增欄位或獨立資料表；既有表真的不適合擴充時，建立 V2 表、回填與驗證資料、切換 Repository，保留舊表至正式驗收完成。④舊欄位或舊表只有在引用、外鍵、資料量、備份與回滾方案完成盤點，且取得 Robin 破壞性操作二次確認後，才能以新的向前 Migration DROP。⑤目前先完成唯讀 Schema／引用盤點，不執行 Migration、清空或刪表。

**理由**：目前正式環境已有使用者、Token、生活紀錄、待辦、重要日子、收藏、行程、探索、成果及跨模組外鍵；整庫重建會破壞使用者 ID、登入狀態、歷史資料與 Migration 一致性，實際風險及回復成本高於漸進遷移。

**後果**：Phase 6 開工前須產出「沿用／新增欄位／新增獨立表／V2 搬遷／正式淘汰」資料表對照。`users` 保留既有主鍵；通關密碼安全、通知紀錄與帳號偏好依盤點結果決定擴充或拆表。第一批已取消功能的四張表仍維持 FR-77 淘汰計畫，但 DROP 前置審核不變。

### 2026-08-15 補充決策：Phase 6 第二批（Telegram 選單與狀態機）拆批盤點

**狀態**：accepted

**背景**：開工前依重構順序決策先盤點 `router.py`／`commands.py`／`templates.py`／`webhook.py`／`submodules/telegram/client.py`，確認第二批「選單與狀態機」的實際範圍。

**盤點結果**：
①`router.py` 目前以 50 組以上文字觸發詞集合（Slash Command＋中文觸發詞）搭配 `if/elif` 鏈路派發，Owner 專屬指令純粹靠程式碼寫在 `if is_owner:` 區塊內達成權限隔離，沒有資料驅動的權限定義。
②目前**沒有 `/start` 指令**：Owner 每則訊息都會觸發 `auth.get_or_create_owner()` 自動建檔；一般使用者的「首次接觸」是把任何一則訊息當通關密碼嘗試綁定，FR-3／FR-4c 定案的「按 START 才進入密碼驗證」流程尚未存在。
③`state.flow` 現況約 85 種值，每個小步驟各自獨立，是「統一功能流程」的雛形，但沒有一致的「摘要→二次確認」結構。
④**Telegram 串接層完全沒有按鈕基礎設施**：`submodules/telegram/client.py` 的 `send_text()` 不支援 `reply_markup`，`webhook.py` 沒有解析 `callback_query`，全庫零筆 `InlineKeyboard`／`callback_data` 相關程式碼。要做角色選單矩陣，必須先擴充 Telegram 串接層，不是只改 `router.py` 的派發邏輯。
⑤`/set_invite_codes` 的移除範圍已確認乾淨可移除：`router.py` 第 33、189-190、540-541 行，`commands.py` 第 501-543 行整段函式，無其他呼叫端引用；換掉的邏輯改用 Phase 6 第一批已寫好但尚未接上任何呼叫端的 `auth.create_user_and_invite()`／`auth.resend_passcode()`。

**決策**：Phase 6 第二批進一步拆成子批次，避免把「按鈕基礎設施」「認證選單化」「85 個既有 flow 遷移」三種性質、風險都不同的工作放進同一個不可回退批次：
- **第二批（2a）**：Telegram 按鈕基礎設施（`submodules/telegram/client.py` 支援 `reply_markup`、`webhook.py` 解析 `callback_query` 並呼叫 `answerCallbackQuery`）＋選單骨架與認證流程選單化（正式實作 `/start`、角色選單矩陣、Owner「權限管理」建立使用者流程改選單引導式並接上 `create_user_and_invite()`／`resend_passcode()`、移除 `/set_invite_codes`）。
- **後續子批次（2b、2c...）**：既有約 85 個 `state.flow` 依模組分組（例如先記帳、再體態、再待辦），逐批改成選單觸發並套用統一「摘要→二次確認」結構，每批各自獨立測試與實機驗收。

**理由**：三種工作的失敗模式不同——按鈕基礎設施是純技術擴充、認證選單化牽涉安全與 FR-3／FR-4 已定案行為、既有 flow 遷移數量龐大且橫跨全部功能模組；混在一批會讓單一批次的回歸範圍難以掌握，違反重構順序決策「批次隔離」的原則。

**後果**：第二批（2a）開工前需先設計選單文字／按鈕結構草案供 Robin 確認。2b 之後的子批次分組順序待 2a 完成後再排定，不在本次一併定案。

### 2026-08-15 補充決策：Phase 6 第二批 2a（按鈕基礎設施＋選單骨架＋認證選單化）實作計畫

**狀態**：accepted（已開工完成，見下方「2026-08-15 開工完成」補述）

**設計內容**：
①**Telegram 串接層**（`submodules/telegram/client.py`）：`send_text()` 新增可選參數 `reply_markup: dict | None`；新增 `answer_callback_query(callback_query_id, text=None)`。純技術擴充，不含商業邏輯。
②**Webhook 解析**（`src/bot/webhook.py`）：新增 `_extract_callback_query(payload)` 解析 `payload["callback_query"]`（回傳 telegram_user_id、chat_id、data、callback_query_id）；`telegram_webhook()` 主流程最前面加分支偵測 callback_query，改呼叫新的 `handle_callback_query()`；沿用既有 `try/except` 安全網（FR-7）與 `update_id` 去重機制。
③**選單骨架**（新檔 `src/bot/menu.py`）：資料驅動的選單定義（取代現行「權限寫在 if 區塊裡」的作法），`MAIN_MENU` 列表含 `key`／`label`／`owner_only` 欄位；`build_main_menu_keyboard(is_owner)` 依 FR-6e 組出對應按鈕，`callback_data` 格式固定 `"menu:<key>"`。**這批只做主選單骨架＋權限管理選單**，日常紀錄、資料查詢、待辦事項、重要日子、收藏與旅遊、成果展示、排程設定這 6 項先回覆「功能開發中」暫時訊息，實際邏輯留給 2b 之後遷移對應模組時才接上——確保主選單本身能獨立完整測試（按鈕都看得到、按得動）。
④**`/start` 正式實作**（FR-3、FR-4c）：`router.py` 新增 `_START_TRIGGERS = {"/start"}`，是 FR-6a 定義下唯一保留的 Slash Command。未綁定使用者按 `/start` 先回覆「請輸入通關密碼」，下一則文字才進入 `try_bind_invite_code()` 驗證（取代現行「任何文字都當密碼試」的隱性行為，堵住無明確驗證動作就能無限次嘗試密碼的漏洞）；已綁定使用者再次 `/start` 只重新顯示主選單；綁定成功呼叫 `toggles.ensure_default_toggles()`、發送 `templates.APPENDIX_A_TEXT`（FR-5：首次綁定同時作為使用規則模板），接著顯示主選單。
⑤**Owner「權限管理」選單化＋移除 `/set_invite_codes`**：精確刪除 `router.py` 第 33、189-190、540-541 行與 `commands.py` 第 501-543 行整段函式（範圍依 2026-08-15 前次盤點條目確認乾淨可移除，無其他呼叫端引用）；新增 callback 驅動的選單引導流程（權限管理 →建立使用者／停用使用者／恢復使用者／重發密碼→建立使用者時問家庭稱謂、暱稱可選），接上 Phase 6 第一批已寫好但尚未接上呼叫端的 `auth.create_user_and_invite()`／`auth.resend_passcode()`／`auth.set_user_active()`；密碼類訊息只在建立完成當下的受控回覆顯示（FR-4b）。
⑥**測試**：新增 `tests/bot/test_menu.py`（選單結構產生、Owner／非 Owner 按鈕差異）；擴充 `tests/bot/test_webhook.py`（callback_query 解析）、`tests/bot/test_router.py`（`/start` 首次／重複、權限管理選單流程）；`submodules/telegram/client.py` 對應測試檔案（`reply_markup`／`answer_callback_query` 呼叫格式，實際檔名開工時確認）。
⑦**文件**：`docs/reference/api_schema.md` 視實作是否新增內部路由結構決定要不要補；`docs/specs/SPEC.md` 不動（本批是實作既有 FR，不改變規格內容）。

**理由**：現行完全無按鈕、無 `/start` 的架構若直接在單一批次塞入全部 85 個 flow 的選單化，回歸風險過高；先落地按鈕基礎設施＋主選單骨架＋認證選單化，讓其餘模組能在後續子批次逐一掛載，同時解決 FR-3 要求但現行架構缺漏的「明確驗證動作」安全缺口。

**後果**：2a 開工後，`router.py`／`commands.py`／`webhook.py`／`submodules/telegram/client.py` 均會異動；`/set_invite_codes` 移除後舊指令使用者會收到「指令不存在」提示（Telegram 預設行為），不提供相容期（FR-6a）。2b 起的子批次分組順序待本批完成後再排定。

**2026-08-15 開工完成**：實作按設計內容①～⑥完成（⑦文件同步見本篇與 PROGRESS.md 對應條目，`api_schema.md` 因本批未新增對外 API 路由，確認不需更新）。`src/bot/menu.py`／`tests/bot/test_menu.py` 為新檔，`src/bot/commands.py`／`router.py`／`webhook.py`／`submodules/telegram/client.py` 依設計異動，`tests/bot/conftest.py`／`test_commands.py`／`test_router.py`／`test_webhook.py`／`tests/submodules/telegram/test_client.py` 同步擴充。Claude 沙箱執行完整測試 1716 項全數通過；Robin 本機執行 `python3 -m pytest` 1750 項通過、3 項失敗（`tests/bot/test_toeic.py` 因本機未安裝 `ffmpeg` 導致，屬既有環境問題，與本批異動無關，不列入本批驗收範圍）。尚待 Robin 完成 commit／push 與實機驗收。

### 2026-08-15 補充決策：Phase 6 第二批 2b 起子批次分組順序

**狀態**：accepted

**背景**：2a（按鈕基礎設施＋選單骨架＋認證選單化）已開工完成，前次盤點條目明確將 2b 之後的分組順序留待本批完成後再排定。主選單其餘 7 項（日常紀錄／資料查詢／待辦事項／重要日子／收藏與旅遊／成果展示／排程設定）目前仍回覆「功能開發中」，需要決定逐批遷移既有 85 個 `state.flow` 的順序。

**討論內容**：排序判準有四種候選——風險由低到高、使用頻率優先、沿用 ADR 先前舉例的「記帳→體態→待辦」順序、或先盤點各模組 `state.flow` 數量與欄位複雜度細節再排。Robin 選擇「風險由低到高」為排序判準；另外「資料查詢」（FR-9c／FR-9d 跨模組七日查詢）與「排程設定」因技術上依賴其他模組欄位與通知規則先底定，不受風險排序影響，一律排在最後。「日常紀錄」原為單一主選單項目，但內部飲食／運動／體態／心情／記帳 5 個子類風險落差大（記帳涉及金額、體態涉及多維健康數值，兩者風險明顯高於心情／運動），因此拆成獨立子批次分別排序，不整包一次遷移，符合 2a 決策「批次隔離」原則。

**決策**：2b 起的子批次遷移順序（每批各自獨立測試與實機驗收，逐批遷移對應模組的既有 `state.flow` 並套用統一「摘要→二次確認」結構）：
1. 重要日子
2. 日常紀錄－心情、運動
3. 收藏與旅遊
4. 成果展示
5. 待辦事項
6. 日常紀錄－飲食
7. 日常紀錄－體態
8. 日常紀錄－記帳
9. 資料查詢（FR-9c／FR-9d）
10. 排程設定

**理由**：重要日子欄位少、無金額或多維健康數值，適合作為「摘要→二次確認」結構落地後的第一個試點；心情、運動同樣欄位單純，接續驗證結構可重複使用；收藏與旅遊、成果展示屬中等複雜度（成果展示另涉跨端雙端確認流程）；待辦事項涉及排程/提醒關聯；飲食欄位較多、資料量較大；體態涉及多維健康數值且需比對既有 Mobile 日期特例規則；記帳涉及金額與最嚴格的草稿保護規則（金額類草稿不得為續存寫入長期資料表），風險最高故放最後一個模組批次；資料查詢與排程設定則因跨模組／跨規則依賴，技術上必須等前面模組欄位與通知規則穩定後才能實作，不受風險排序影響。

**後果**：Phase 6 第二批的批次規劃至此全數排定（2a 已完工，2b～2k 共 10 個子批次依上述順序執行）。各子批次開工前仍須依 SDD 流程個別提出實作計畫並等待 Robin 確認，本次僅定案「順序」，未定案各批次的實作細節、時程或起始日期。

### 2026-08-15 補充決策：Phase 6 第二批 2b（重要日子）實作計畫

**狀態**：accepted（已開工完成，見下方「開工完成」補述）

**背景**：依上述排序，2b 從「重要日子」開始。盤點發現後端服務、資料表、Mobile API 皆已完整（`src/services/app_important_days.py` 全套 CRUD＋驗證、`important_days`／`important_day_occurrences`／`important_day_recipients` 三張表、`src/api/app_important_days.py` Mobile 路由），只有 Telegram 端還沒有選單入口。

**設計內容**：
①**新檔 `src/bot/important_days.py`**：Telegram 版重要日子流程，直接呼叫既有 `AppImportantDayService`（不重寫驗證邏輯，符合 FR-6h「兩端共用相同欄位、必填、數值範圍、驗證與讀取結果」）。子選單：查看清單／新增／編輯／刪除，比照 2a「摘要→二次確認」結構——多步驟輸入（名稱→重複方式→日期/日期區間→是否全天/時間→提前提醒天數→通知對象→備註）跑完後，先回覆完整摘要文字＋「確認送出／取消」按鈕，按確認才寫入。編輯採「整筆重新輸入」而非逐欄位差異更新（沿用同一組多步驟流程，只是起手多帶 `target_id`），簡化實作複雜度；刪除需二次確認且僅按鈕觸發，使用者若在刪除確認狀態改用打字則直接取消並導回主選單，不落入未知狀態例外。
②**`menu.py`**：`important_days` 從 `_NOT_YET_IMPLEMENTED_KEYS` 移除。
③**`router.py`**：`handle_callback_query()` 新增 `menu:important_days` 與 `important_days:<action>` 前綴分派（`list`／`add`／`edit:<id>`／`delete:<id>`／`confirm_delete:<id>`／`confirm_save`）；`_dispatch_active_flow()` 新增 `important_days`（多步驟輸入）與 `important_days_delete_confirm`（按鈕式刪除確認的文字保護網）兩個 flow 分支。`webhook.py` 不需異動——2a 已建好的通用 callback_query 解析與 `(text, reply_markup)` 二元組回傳機制可直接沿用。
④**範圍排除**：FR-72a 提到的「通用 Telegram 重要日子發送器待重構」（依 `reminder_days_before` 主動推播提醒）不在本批，留給 2b～2k 順序中的「排程設定」批次；本批只做 CRUD 與清單顯示。
⑤**測試**：新增 `tests/bot/test_important_days.py`（13 項，涵蓋三種重複方式的新增流程、驗證錯誤訊息、清單擁有者權限、刪除確認、編輯流程），使用獨立 `FakeDatabase`（比照 `tests/services/test_app_important_days.py` 寫法，`execute_query` 固定回傳空清單，服務層驗證邏輯已在該檔完整覆蓋，不重複測試）；擴充 `tests/bot/conftest.py` 的共用 `FakeCloudSQLClient`（新增三張表、`id = %s AND owner_user_id = %s` where 條件、`execute_query` 存根）供 `tests/bot/test_router.py` 新增的 4 項整合測試使用（子選單按鈕、一般使用者也能新增（FR-3 非 Owner 專屬）、跨使用者刪除防護、`important_days` 已移出開發中名單）。

**理由**：後端與 Mobile 已經把驗證邏輯與資料模型定案，Telegram 端重寫一遍會違反 FR-6h 兩端一致的要求，也徒增維護成本；「整筆重新輸入」的編輯方式雖然使用體驗不如逐欄位修改，但可以完全複用新增流程的狀態機與驗證，符合本批次「風險最低」的排序理由，逐欄位編輯留待之後有需求時再迭代。

**後果**：往後任何模組批次若也能重用既有 Mobile Service，應優先評估重用而非重寫，比照本批做法。

**2026-08-15 開工完成**：實作按設計內容①～⑤完成。Claude 沙箱以獨立最小依賴環境執行 `tests/bot/test_important_days.py`、`tests/bot/test_menu.py`，13＋8 項全數通過；`tests/bot/test_router.py` 新增的 4 項整合測試因需要完整還原本專案（`google-genai`／`groq`／Google Drive／Telegram 等 submodules）的匯入依賴鏈，沙箱未還原完整依賴，程式碼已寫入但未在沙箱執行，待 Robin 本機執行 `python3 -m pytest` 驗證全套（含既有測試回歸）。**文件同步檢查**：`docs/specs/SPEC.md` 不動（FR-6e／FR-6h／FR-72a 為既有已定案規格，本批只是實作，未變更需求或產品行為）；`docs/reference/api_schema.md`／`db_schema.md` 確認不需更新（本批沒有新增對外 HTTP 路由，`callback_data` 是 Telegram 內部分派字串、不是 API 端點；沒有新增或異動資料表／Migration，全部沿用既有的 `important_days` 三張表）；`docs/specs/DRAFT.md` 無相關項目需要移動。`docs/specs/PROGRESS.md` 已同步。尚待 Robin 完成 commit／push 與實機驗收。

### 2026-08-16 補充決策：Phase 6 第二批 2c（日常紀錄－心情、運動）實作計畫

**狀態**：accepted（已開工完成，見下方「開工完成」補述）

**背景**：依 2b 起子批次順序，2c 從「日常紀錄」子選單的心情、運動兩個子類開始。盤點 `commands.py`／`router.py` 既有 `mood`／`exercise` 相關程式碼，發現兩者都還是 2a 之前的舊架構：入口靠固定文字觸發詞（`_MOOD_JOURNAL_TRIGGERS`／`_MOOD_BACKFILL_TRIGGERS`／`_MY_MOOD_JOURNALS_TRIGGERS`／`_LOG_EXERCISE_TRIGGERS`／`_BACKFILL_EXERCISE_TRIGGERS`／`_MY_EXERCISE_LOGS_TRIGGERS`，含對應 Slash Command），查詢清單後的「要更新還是刪除」用自由文字交給 LLM 分類（`_MOOD_ACTION_CLASSIFY_PROMPT`／`_EXERCISE_ACTION_CLASSIFY_PROMPT`），刪除前的確認也是自由文字再丟給 LLM 判斷是否為「確認」（`_MOOD_DELETE_CONFIRM_PROMPT`／`_EXERCISE_DELETE_CONFIRM_PROMPT`），沒有 2a／2b 建立的「摘要→二次確認」按鈕結構。

**設計內容**：
①**全面改選單觸發，移除舊文字觸發詞**：`router.py` 移除上述六組觸發詞常數與對應 `handle_message` 文字分派分支；入口改為「📝 日常紀錄」主選單 →「😊 心情」／「🏃 運動」子選單（`daily_log:mood`／`daily_log:exercise`），子選單內「➕ 新增」「🕐 補記」「📋 查看清單」「🔙 返回日常紀錄」四顆按鈕（`mood:new`／`mood:backfill`／`mood:list`／`menu:daily_log`，運動比照）。
②**`menu.py` 新增「日常紀錄」第二層子選單**：新增 `DAILY_LOG_MENU_ITEMS`（心情／運動／飲食／體態／記帳五項，`callback_data` 固定 `"daily_log:<key>"`）、`build_daily_log_menu_keyboard()`、`is_valid_daily_log_key()`、`is_daily_log_not_yet_implemented()`、`daily_log_not_yet_implemented_reply()`（導回「日常紀錄」子選單而非主選單）；主選單的 `daily_log` 從 `_NOT_YET_IMPLEMENTED_KEYS` 移除，改回覆子選單；子選單內只有 `mood`／`exercise` 接上真正邏輯，`diet`／`body`／`finance` 三項維持「開發中」，留給後續子批次。
③**摘要→二次確認套用到兩個模組**（比照 2a／2b 結構，不只套用其中一個）：心情原本「內容」是最後一輪輸入直接寫入，改成輸入完內容後先組摘要文字（心情分類＋日記內容，含 PII 遮蔽提醒）＋「✅ 確認送出／❌ 取消」按鈕（`mood:confirm_save`），按確認才呼叫 `mood.create_mood_journal()`／`update_mood_journal()`，成功後才問「個人成就」；運動原本「心率」是最後一輪輸入直接寫入，改成輸入完心率（或「沒有」）後先估算卡路里、組摘要文字＋確認／取消按鈕（`exercise:confirm_save`），按確認才呼叫 `body.create_exercise_log()`／`update_exercise_log()`。兩個模組的確認狀態（`pending_mood_confirm`／`pending_exercise_confirm`）與刪除確認狀態（`mood_delete_confirm`／`exercise_delete_confirm`）都只接受按鈕，使用者改用打字時比照 2b `important_days.handle_delete_confirm_text()` 的保守做法，直接取消流程並導回「日常紀錄」子選單，不當成未知狀態拋例外。
④**查詢清單改用按鈕**：「查看清單」列出最近紀錄，每筆附「✏️ 編輯 N」「🗑 刪除 N」兩顆按鈕（`mood:edit:<id>`／`mood:delete:<id>`，運動比照），取代原本「輸入編號→LLM 判斷要更新還是刪除」的兩輪自由文字；「✏️ 編輯」沿用原記錄的 `entry_date`，重新走一次完整多步驟輸入（`journal_id`／`exercise_id` 帶著代表這是編輯而非新增），設計比照 2b 重要日子的「整筆重新輸入」。
⑤**移除 LLM 分類 Prompt**：`_MOOD_ACTION_CLASSIFY_PROMPT`／`_MOOD_DELETE_CONFIRM_PROMPT`／`_EXERCISE_ACTION_CLASSIFY_PROMPT`／`_EXERCISE_DELETE_CONFIRM_PROMPT` 與對應的 `handle_mood_list_action_step`／`handle_mood_action_choice_step`／`handle_mood_delete_confirm_step`／`handle_exercise_list_action_step`／`handle_exercise_action_choice_step`／`handle_exercise_delete_confirm_step` 一併移除，改由明確按鈕 callback 取代，不再需要模型判斷使用者意圖（設計簡化，減少一種可能誤判的路徑）。
⑥**擁有者重新驗證（FR-6c）**：`mood:delete:<id>`／`mood:confirm_delete:<id>`／`exercise:delete:<id>`／`exercise:confirm_delete:<id>` 皆在各自的 handler 重新查一次 `user_id` 比對，不假設上一步篩過就安全，比照 2b `important_days.handle_delete` 的做法。
⑦**測試**：擴充 `tests/bot/test_router.py`——原本靠舊文字觸發詞驅動的 4 項心情整合測試改寫為按鈕驅動（新增／補記／查詢清單、編輯、刪除四種流程），新增摘要確認步驟打字保護網測試；新增 5 項運動整合測試（子選單、新增含確認關卡、確認步驟打字保護網、清單編輯刪除、跨使用者刪除防護）；`tests/bot/test_menu.py` 新增 `daily_log` 子選單相關測試、更新 `is_not_yet_implemented` 的斷言（`daily_log` 這批也移出開發中名單）。

**理由**：Robin 明確選擇「全部改成只能選單，移除舊觸發詞」（不保留舊 Slash Command／文字觸發詞相容期，比照 2a 決策 `/set_invite_codes` 不提供相容期的做法）；「摘要→二次確認」套用到兩個模組而非只套其中一個，是因為兩者風險特性接近（都是自由文字內容＋固定分類欄位的組合），分開套用會讓同一子批次內出現不一致的使用者體驗，也違反「批次內功能一致」的原則。

**後果**：2c 開工後，`router.py`／`commands.py`／`menu.py` 均會異動；`tests/bot/test_router.py`／`tests/bot/test_menu.py` 同步擴充／改寫。舊的心情／運動 Slash Command 與中文觸發詞（例如 `/mood_journal`、「我想做心情筆記」、「我的心情紀錄」、「我要記錄運動」等）失效後，使用者會收到「我不太懂這個指令耶！」（一般聊天回覆，Telegram 無指令提示），不提供相容期。

**2026-08-16 開工完成**：實作按設計內容①～⑦完成。Claude 於還原完整依賴（`lunarcalendar`／`google-genai`／`google-api-python-client`／`pydub`／`openpyxl`／`beautifulsoup4`／`bcrypt`／`PyJWT` 等）的沙箱中執行完整 `tests/` 測試，155 項全數通過（含既有測試回歸與本批新增／改寫的心情、運動、`daily_log` 子選單測試）。**文件同步檢查（2026-08-16 補正）**：初次檢查誤判 `docs/specs/SPEC.md` 不需更新；覆核後發現 FR-47／FR-49 的條文本身明確寫死 `/log_exercise`／`/mood_journal`／`/backfill_mood`／`/my_mood_journals` 等指令名稱作為入口機制，本批把入口正式改成選單按鈕、移除舊指令且不提供相容期，屬於「已定案需求變更」，已依文件治理規則同步修改 SPEC.md 對應段落（FR-47、FR-49 條文改為描述選單入口與摘要確認關卡，並加回 FR-49 段落的「討論紀錄」連結指向本篇 ADR）；FR-48（飲食）、FR-45／FR-46（體態其餘子項）本批未異動，SPEC.md 維持原文。`docs/specs/DRAFT.md` 「已取消」清單既有 2026-08-15「除 `/start` 外所有 Slash Commands 正式取消」條目已涵蓋本次心情／運動指令移除，不需新增項目。`docs/reference/api_schema.md`／`db_schema.md` 確認不需更新（沒有新增對外 HTTP 路由，沒有新增或異動資料表／Migration，`mood_journals`／`exercise_logs` 沿用既有結構）。`docs/specs/PROGRESS.md` 已同步。尚待 Robin 完成 commit／push 與實機驗收（含新／舊心情、運動紀錄、以 Owner 及一般使用者兩種身分測試）。

### 2026-08-16 補充決策：Phase 6 第二批 2d（收藏與旅遊）實作計畫

**狀態**：accepted（已開工完成，見下方「開工完成」補述）

**背景**：依 2b 起子批次順序，2d 從「收藏與旅遊」開始。盤點發現 `commands.py`／`router.py` 全文搜尋「收藏」「trip」「旅遊」「collection」零命中——跟心情/運動（2c）不同，Telegram 端完全沒有舊 `state.flow`／文字觸發詞可以遷移，是全新流程，沒有相容性包袱。後端 Mobile Service／API 已完整：`AppCollectionService`（收藏 CRUD＋geocode）與 `AppLifeExplorationService`（`list_trips`／`create_trip`／`update_trip`／`delete_trip`／`restore_trip`／`complete_trip`），資料表沿用既有 `collection_items`（migration 0072）／`trips`（0071）／`trip_collection_items`。額外發現 migration `0074_create_trip_itinerary_items.sql` 建的表全文搜尋皆無程式碼使用（對應 FR-74「不提供逐日逐時排程」的既有決策），本批不動它。FR-6e 的「收藏與旅遊」子選單只含收藏＋行程操作；探索地圖（FR-75）是 Mobile 專屬視覺入口、成果展示（FR-76）是獨立主選單項目且已排在 2e，兩者皆不在本批範圍。

Robin 對盤點結果提出的實作計畫做出三項決策：①收藏清單與旅遊行程一次做完，不拆兩個子批次（跟 2c 心情+運動同時做的先例一致）；②地址定位要提供「📍 定位地址」按鈕（比照 Mobile 規則，使用者明確按下才呼叫 Nominatim，不在文字輸入當下自動觸發）；③旅遊行程的預估支出在 Telegram 端要支援分類輸入（交通／住宿／飲食／門票／購物／其他六類逐一輸入，而非只填總額）。

**設計內容**：
①**新檔 `src/bot/collections.py`**：收藏清單 CRUD，直接呼叫既有 `AppCollectionService`（不重寫驗證邏輯，符合 FR-6h）。新增流程：類型（六選一）→名稱→國家→區域／城市→地址（可略過）→若填地址則彈出「📍 定位地址／⏭ 略過定位」按鈕，成功套用經緯度並顯示精確度標籤，失敗則標記「無法定位」但仍可繼續→參考網址→預估費用→備註→摘要＋確認／取消。編輯採「整筆重新輸入」（比照 2b）；刪除二次確認＋僅按鈕，打字一律視為取消（比照 2b／2c 保守做法）。
②**新檔 `src/bot/trips.py`**：旅遊行程 CRUD，直接呼叫既有 `AppLifeExplorationService`。新增流程：行程名稱→國家→區域／城市（只列出該目的地有收藏的清單，沒有收藏則中止流程並導引去新增收藏）→從對應收藏多選（切換勾選的 Inline Keyboard，按「✅ 完成選擇」結束）→起訖日期（可整組略過，維持規劃中）→是否同步重要日子→預估支出六分類逐一輸入（皆可略過視為 0）→備註→摘要＋確認。狀態流轉（規劃中／已確認／已完成／已取消）透過清單頁按鈕觸發「快速狀態操作」，直接用行程既有欄位組完整 payload 呼叫 `update_trip()`，不必重新走一次多步驟輸入；「完成行程」另開多選按鈕勾選實際造訪項目，呼叫 `complete_trip()`。
③**`menu.py`**：`collections` 從 `_NOT_YET_IMPLEMENTED_KEYS` 移除；子選單（收藏清單／新增收藏／旅遊行程）由 `collections.start_collections_menu()` 直接組出 Inline Keyboard，比照 `important_days` 的單層選單做法，不另外定義 `*_MENU_ITEMS` 常數（收藏與行程沒有共用的多步驟輸入欄位可以抽象化）。
④**`router.py`**：`handle_callback_query()` 新增 `menu:collections`、`collections:<action>`（`list`／`add`／`edit:<id>`／`delete:<id>`／`confirm_delete:<id>`／`geocode`／`skip_geocode`／`confirm_save`）、`trips:<action>`（同構＋`confirm:<id>`／`cancel:<id>`／`complete:<id>`／`complete_toggle:<id>`／`complete_confirm:<id>`／`toggle_item:<id>`／`items_done`／`confirm_save`）前綴分派；`_dispatch_active_flow()` 新增 `collection`／`collection_delete_confirm`／`trip`／`trip_delete_confirm`／`trip_complete_select` 五個 flow 分支。`webhook.py` 不需異動，沿用 2a 通用 callback_query 解析機制。
⑤**範圍排除**：探索地圖（FR-75）、成果展示（FR-76，已排在 2e）、`trip_itinerary_items` 閒置表，皆不在本批。

**理由**：後端與 Mobile 已經把驗證邏輯與資料模型定案，Telegram 端重寫一遍會違反 FR-6h 兩端一致的要求；收藏與行程一次做完是因為兩者風險特性接近且使用情境高度耦合（行程本來就是「從收藏組出來」），分開做反而會讓「收藏清單」在沒有行程功能配套下體驗不完整，違反「批次內功能一致」的原則（比照 2c 決策的判斷邏輯）；地址定位比照 Mobile 明確觸發規則，是延續既有 FR-75 決策，不是本批新增規則。

**後果**：2d 開工後，`router.py`／`menu.py` 均會異動，新增 `src/bot/collections.py`／`src/bot/trips.py`；`tests/bot/test_collections.py`／`tests/bot/test_trips.py` 新增，`tests/bot/test_menu.py` 補一項斷言。

**2026-08-16 開工完成**：實作按設計內容①～④完成（⑤範圍排除確認未觸碰）。新增 `tests/bot/test_collections.py`（10 項）、`tests/bot/test_trips.py`（8 項），皆用獨立 `FakeDatabase`（服務層驗證邏輯已在 `tests/services/test_app_collections.py`／`test_app_life_exploration.py` 覆蓋，這裡只測 Telegram 對話流程），更新 `tests/bot/test_menu.py` 一項斷言。**與 2b／2c 不同，本批 Claude 沙箱完全沒有執行 `pytest`**（連輕量測試都沒跑），也**沒有擴充 `tests/bot/conftest.py`／`tests/bot/test_router.py` 整合測試**——這兩項是本批相對 2b／2c 明確縮小的範圍，記錄於此供 Robin 決定是否要求補齊。**文件同步檢查**：`docs/specs/SPEC.md` 不動（FR-6e／FR-73～FR-74a 為既有已定案規格，本批純實作，未變更需求或產品行為）；`docs/reference/api_schema.md`／`db_schema.md` 確認不需更新（沒有新增對外 HTTP 路由，`callback_data` 是 Telegram 內部分派字串；沒有新增或異動資料表／Migration，全部沿用既有的 `collection_items`／`trips`／`trip_collection_items`）；`docs/specs/DRAFT.md` 無相關項目需要移動。`docs/specs/PROGRESS.md` 已同步。尚待 Robin 完成本機 `pytest` 驗證、commit／push 與 Telegram 實機驗收。

### 2026-08-16 補充決策：Phase 6 第二批 2e（成果展示）實作計畫

**狀態**：accepted（已開工完成，見下方「開工完成」補述）

**背景**：依 2b 起子批次順序，2e 從「成果展示」開始，2d 已明確排除此範圍。盤點發現跟 2d（收藏與旅遊）情況一致——`commands.py`／`router.py` 全文搜尋「成果」「achievement」只命中 FR-50 心情個人成就提示（`pending_mood_achievement`，2c 已完工的獨立功能，跟成果展示無關），Telegram 端完全沒有舊 `state.flow` 可遷移，是全新流程。後端／Mobile Service／API 已完整：`AppLifeExplorationService`（`list_achievements`／`create_achievement`／`respond_candidate`／`delete_achievement`／`restore_achievement`）與 Migration `0076`＋`0079` 建立的 `user_achievements`／`achievement_candidates` 兩張表。

盤點過程中發現 SPEC.md 現有文字與實際候選機制有落差：FR-45 寫「達成時另以 Telegram 固定按鈕詢問是否加入成果展示」，FR-76 寫「並同步以 Telegram 固定訊息及『加入成果展示／略過』按鈕詢問」，兩者措辭都暗示「候選產生的當下」要主動推播；但 `_refresh_candidates()` 實際只在呼叫 `list_achievements()`（即使用者開啟成果展示清單）時才重新掃描，是「被動」機制，且六種候選類型中只有體重、運動兩種目前在達標當下有現成觸發點（體重在 `body.py` 記錄體重當下，運動借用 `/healthz` 排程），考試、探索、行程、待辦四種完全沒有觸發點。若要做到「當下推播」需同時異動 `body.py`／考試成績登錄／`trips.py`／探索紀錄建立點／`todo.py` 等多個模組，風險特性與範圍已超出「成果展示」單一模組。

Robin 對此提出兩項決策：①推播機制維持被動掃描（使用者開啟成果展示清單時系統才重新掃描候選並列出，不在候選產生當下主動推播），SPEC.md FR-45／FR-76 文字同步修正為符合此機制的措辭；②Telegram 端刪除採直接執行，不提供二次確認與 5 秒復原（跟 Mobile App 既有的二次確認＋5 秒復原不同），因為 Telegram 對話介面沒有「按鈕自動失效」的視覺機制，若要做到「5 秒可復原」只能靠伺服器記錄時間戳事後比對，體驗陽春且徒增複雜度，不如直接刪除來得單純。

**設計內容**：
①**新檔 `src/bot/achievements.py`**：直接呼叫既有 `AppLifeExplorationService`（不重寫驗證邏輯，符合 FR-6h）。子選單：「📋 查看成果」／「➕ 新增成果」。查看成果先列待確認候選（附「✅ 加入／⏭ 略過」按鈕，對應 `respond_candidate`），再列已建立成果卡片（附「🗑 刪除」按鈕，按下直接呼叫 `delete_achievement()`，無確認流程）；新增成果走多步驟輸入：類別（七選一：體態／考試／運動／探索／旅遊／待辦／其他）→名稱→完成日期→說明（可略過）→照片網址（可略過，Telegram 端不做圖片上傳轉存）→摘要＋確認／取消。
②**`menu.py`**：`achievements` 從 `_NOT_YET_IMPLEMENTED_KEYS` 移除；子選單由 `achievements.start_achievements_menu()` 直接組出 Inline Keyboard，比照 `collections` 的單層選單做法。
③**`router.py`**：`handle_callback_query()` 新增 `menu:achievements`、`achievements:<action>`（`list`／`add`／`delete:<id>`／`candidate_accept:<id>`／`candidate_reject:<id>`／`confirm_save`）前綴分派；`_dispatch_active_flow()` 新增 `achievement`（多步驟輸入）一個 flow 分支，不需要刪除確認 flow（刪除直接執行）。
④**範圍排除**：FR-45／FR-76 描述的「候選產生當下主動推播」不在本批（維持被動掃描，見上述決策①）；成果照片上傳（僅支援貼網址）；`is_pinned`／`is_hidden` 欄位（Mobile 端目前也未使用）。

**理由**：後端與 Mobile 已經把驗證邏輯與資料模型定案，Telegram 端重寫一遍會違反 FR-6h 兩端一致的要求；被動掃描維持現況是因為「當下推播」牽涉多模組且範圍/風險與本批「成果展示選單」性質不同，比照 2d 排除 FR-75 的判斷邏輯；Telegram 刪除不做復原是因為對話介面沒有真正的「按鈕失效」機制，土法煉鋼做出來的體驗也不完整，不如維持簡單直接。

**後果**：2e 開工後，`router.py`／`menu.py` 均會異動，新增 `src/bot/achievements.py`；`tests/bot/test_achievements.py` 新增，`tests/bot/test_menu.py` 補一項斷言。`docs/specs/SPEC.md` FR-45／FR-76 條文同步修正措辭（不是需求內容變更，只是把文字對齊被動掃描的實際機制）。

**2026-08-16 開工完成**：實作按設計內容①～③完成（④範圍排除確認未觸碰）。新增 `tests/bot/test_achievements.py`（10 項），用獨立 `FakeDatabase`（服務層驗證與候選掃描邏輯已在 `tests/services/test_app_life_exploration.py` 覆蓋，這裡只測 Telegram 對話流程），更新 `tests/bot/test_menu.py` 一項斷言。比照 2d，本批 Claude 沙箱在還原 `src/bot/achievements.py`／`src/bot/menu.py`／`src/services/app_life_exploration.py`／`app_important_days.py`／`geocoding.py` 及 `submodules/cloudsql`／`submodules/retry` 最小依賴環境後，執行 `tests/bot/test_achievements.py`＋`tests/bot/test_menu.py` 共 19 項全數通過；`router.py` 因需要完整還原本專案（`google-genai`／`groq`／Google Drive／Telegram 等 submodules）的匯入依賴鏈，沙箱未還原完整依賴，程式碼已寫入但未在沙箱執行，也**沒有擴充 `tests/bot/conftest.py`／`tests/bot/test_router.py` 整合測試**，記錄於此供 Robin 決定是否要求補齊。**文件同步檢查**：`docs/specs/SPEC.md` 已修正 FR-45、FR-76 條文措辭（新增本 ADR 條目連結），FR-76a 不動；`docs/reference/api_schema.md`／`db_schema.md` 確認不需更新（沒有新增對外 HTTP 路由，`callback_data` 是 Telegram 內部分派字串；沒有新增或異動資料表／Migration，全部沿用既有的 `user_achievements`／`achievement_candidates`）；`docs/specs/DRAFT.md` 無相關項目需要移動。`docs/specs/PROGRESS.md` 已同步。

**2026-08-16 Robin 本機驗證**：執行 `pytest tests/bot/test_achievements.py tests/bot/test_menu.py -v` 19 項全過；完整 `pytest tests/ -q` 回報 4 項失敗，其中 3 項是既有 `test_toeic.py` 因本機未裝 `ffmpeg` 的環境問題（與本批無關，歷次批次已知），1 項是 `tests/bot/test_router.py::test_important_days_menu_key_not_in_not_yet_implemented_set`——本批把 `achievements` 移出 `menu.py` 的開發中名單時，這條舊斷言仍把 `achievements` 列在「應維持開發中」的清單裡，屬於 2d 曾發生過的同類迴歸（比照當時做法直接修正斷言，把 `achievements` 從「應維持開發中」移到「應移出名單」）。修正後 Robin 未再重新執行全套，尚待下次驗證確認 1795＋1 項全過。尚待 Robin 完成 commit／push 與 Telegram 實機驗收。

### 2026-08-16 補充決策：Phase 6 第二批 2f（待辦事項）實作計畫

**狀態**：accepted（已開工完成，見下方「開工完成」補述）

**背景**：依 2b 起子批次順序，2f 從「待辦事項」開始。盤點 `commands.py`／`router.py`／`todo.py` 既有邏輯：這是目前唯一還在用「舊版三輪反問」的模組（`pending_todo_confirm`／`pending_todo_time`／`pending_todo_reminder`／`pending_todo_calendar_sync`），沒有 2a 之後建立的按鈕基礎設施；`todo.py`（純邏輯）與資料表（migration `0013`／`0016`／`0031`）已完整，2f 不用動。跟 2b～2e 不同的是，待辦事項新增有一個既有的「自然語言偵測」入口（`chat.py` 主動偵測「什麼時候要做什麼事」並反問，FR-31、FR-56e），不是單純的舊文字觸發詞，Robin 明確決定保留（AskUserQuestion 確認），另外在選單加一顆「➕ 新增」按鈕，兩個入口共用同一套狀態機。

**設計內容**：
①**兩個新增入口共用「時間→提醒→行事曆同步→摘要確認」狀態機**：自然語言偵測（`pending_todo_confirm`，維持不變）與選單按鈕（`todo:add` → `pending_todo_new_content`，略過「要不要記錄」這輪反問，先問「要記什麼事」）都收斂到 `pending_todo_time`。
②**新增摘要→二次確認關卡**：`pending_todo_calendar_sync` 這一步不再直接寫入 `todos`，改成組出摘要文字＋「✅ 確認送出／❌ 取消」按鈕（`pending_todo_confirm_save`），按確認才呼叫 `todo.create_todo()`（含 Calendar 事件建立）；打字比照 2b `important_days.handle_delete_confirm_text()` 的保守做法，直接取消並導回主選單。
③**查詢清單改按鈕**：`start_todo_list()` 每筆附「✅ 完成」「🚫 取消」按鈕（`todo:complete:<id>`／`todo:cancel:<id>`），取代「輸入編號→LLM 判斷完成或取消」兩輪自由文字，移除 `_TODO_ACTION_CLASSIFY_PROMPT`；重新查一次 `user_id` 比對（FR-6c），比照 2b `important_days.handle_delete()`。
④**`menu.py`**：`todo` 從 `_NOT_YET_IMPLEMENTED_KEYS` 移除；子選單（查看清單／新增）由 `commands.start_todo_menu()` 直接組出 Inline Keyboard，比照 `important_days` 的單層選單做法。
⑤**`router.py`**：`handle_callback_query()` 新增 `menu:todo`、`todo:<action>`（`list`／`add`／`complete:<id>`／`cancel:<id>`／`confirm_save`）前綴分派，另外補上 `calendar_client` 參數（`webhook.py` 呼叫端同步補上 `_build_calendar_client()`，先前 callback_query 分支沒有這個參數，2f 是第一個需要在按鈕流程建立 Calendar 事件的批次）；`_dispatch_active_flow()` 新增 `pending_todo_new_content`（新增內容反問）與 `pending_todo_confirm_save`（摘要確認的文字保護網）兩個 flow 分支，移除 `pending_todo_list_action`／`pending_todo_action_confirm`。
⑥**移除**：`/my_todos`、「我的待辦事項」文字觸發詞（`_MY_TODOS_TRIGGERS`）不提供相容期，比照 2c／2d 決策。

**理由**：自然語言偵測入口是 FR-31／FR-56e 既有規格訂下的對話智慧功能，不是單純的相容性觸發詞，跟 2c／2d「全部改選單、移除舊觸發詞」的判準不同，Robin 明確選擇保留並讓兩個入口共用同一套狀態機，避免維護兩份重複邏輯；摘要→二次確認比照 2b～2e 一貫結構，讓待辦事項新增流程跟其餘模組體驗一致；查詢清單改按鈕、重新驗證 `user_id` 比照 2b 既有做法，理由不再重複。

**後果**：2f 開工後，`menu.py`／`commands.py`／`router.py`／`webhook.py` 均會異動（`webhook.py` 是本批唯一異動到既有其他批次沒碰過的檔案，原因見⑤）；`tests/bot/test_commands.py`／`tests/bot/test_router.py`／`tests/bot/test_menu.py` 同步改寫。舊版 `pending_todo_list_action`／`pending_todo_action_confirm` 這兩個 flow 與 `_TODO_ACTION_CLASSIFY_PROMPT`／`handle_todo_list_action_step`／`handle_todo_action_confirm_step` 一併移除。

**2026-08-16 開工完成**：實作按設計內容①～⑥完成。改寫 `tests/bot/test_commands.py` 待辦事項區塊（新增選單/按鈕相關測試，移除舊版編號輸入＋LLM 分類測試）、`tests/bot/test_router.py`（改寫自然語言全流程測試收尾為按鈕確認、新增按鈕新增/清單按鈕/偽造 callback 測試，移除舊版 `/my_todos` 編號輸入測試）、`tests/bot/test_menu.py` 一項斷言。**比照 2d／2e，本批 Claude 沙箱未執行 `pytest`**（`commands.py` 頂層匯入專案內近 20 個 `src/bot/*` 模組與 `submodules/*`，沙箱未還原完整依賴鏈，只驗證了 `ast.parse` 語法正確與人工比對既有 2b～2e 慣例），**也未擴充 `tests/bot/conftest.py`**（既有 `FakeCloudSQLClient` 的 `todos` 表結構已足夠支撐新測試，不需要異動）。**文件同步檢查**：`docs/specs/SPEC.md` 不動（FR-31／FR-31a／FR-31b／FR-32／FR-56e／FR-66a 為既有已定案規格，本批純實作，未變更需求或產品行為）；`docs/reference/api_schema.md`／`db_schema.md` 確認不需更新（沒有新增對外 HTTP 路由，`callback_data` 是 Telegram 內部分派字串；沒有新增或異動資料表／Migration，全部沿用既有的 `todos` 表）；`docs/specs/DRAFT.md` 無相關項目需要移動。`docs/specs/PROGRESS.md` 已同步。

**2026-08-16 Robin 本機驗證與實機驗收**：本機執行完整 `python3 -m pytest tests/ -q` 首輪回報 4 項失敗，3 項為既有 `test_toeic.py` `ffmpeg` 環境問題（與本批無關），1 項是 `tests/bot/test_webhook.py::test_webhook_routes_callback_query_and_answers_plus_sends_reply`——本批 `handle_callback_query()` 新增 `calendar_client` 參數、`webhook.py` 呼叫端同步補上注入後，這條舊斷言沒有更新期望的呼叫參數，屬於本批直接造成的迴歸，已修正斷言補上 `calendar_client=None`。修正後重跑全套 1806 passed／3 failed（僅剩既有 `ffmpeg` 環境問題）。commit `eabed3b`（10 files changed, 540 insertions/269 deletions），08/16 Robin 已推版並完成部署，Telegram 實機驗收：選單「➕ 新增」略過確認反問直接問內容、自然語言入口維持原行為、時間→提醒→行事曆同步→摘要確認按鈕全程正常、清單按鈕標記完成/取消正常、`/my_todos`／「我的待辦事項」舊指令已確認失效，皆無問題。

### 2026-08-16 補充決策：Phase 6 第二批 2g（日常紀錄－飲食）＋全站語音確認機制實作計畫

**狀態**：accepted（已開工，程式碼完成，見下方「開工進度」補述；**尚未測試、尚未 commit**）

**背景**：依 2b 起子批次順序，2g 從「日常紀錄－飲食」開始。盤點 `commands.py`／`router.py`／`body.py` 既有邏輯：飲食（含飲水）流程還是 Phase 6 選單化之前的舊架構——純文字觸發詞 `/log_diet`／`/backfill_diet`／`/my_diet_logs`，清單操作靠「輸入編號→自由文字選更新/刪除→LLM 分類」，沒有摘要→二次確認關卡；`diet_logs` 資料表（migration `0026`＋`0078`）已支援 `nutrition_source`（`ai`／`manual`）欄位，不需要新 migration。

Robin 在討論過程中提出三項比照 Mobile App 的對齊決策，逐一討論後定案：
①**新增流程**：先問「要不要記飲水」，答完再問「要不要記食物」，兩者合併成一次摘要一次確認送出（取代原本「先選飲食或飲水二選一」的舊設計）。
②**每日筆數**：飲食（`food`）、飲水（`water`）比照 Mobile App 的 single-daily 設計，同一天各自只能有一筆（Mobile 首頁卡片只抓當天最新一筆、`app_records.py` 的 `_SINGLE_DAILY_KINDS` 也會擋下 Mobile 端當天第二次新增），若不對齊 Telegram 一天多筆會讓 Mobile 首頁卡片文案失真且 Mobile 新增會被誤擋；Telegram 端已有紀錄時新增流程導向查看清單的編輯功能，不再讓使用者硬記第二筆。
③**輸入方式與營養素來源**：食物內容支援文字／照片兩種輸入方式（照片複用 Mobile App 既有的 `src/services/app_diet_photo.py` 辨識邏輯，不重寫），算完營養素後可選擇沿用 AI 估算或自己填寫（`nutrition_source`），比照 Mobile App `app_records.py` 現有的 `nutrition_source` 設計。

Robin 追加要求「語音辨識結果可能跟使用者實際講的內容有落差，Telegram 所有套用到語音的功能都要有『轉文字後先貼出來確認』的流程」，範圍明確要求是全站（不限 2g 飲食），因為既有語音架構 `handle_voice_message()` 是全域單一入口，涵蓋待辦、心情、運動、記帳、證照、求職、收藏旅遊與自由聊天等全部功能，決策與設計見 `docs/ADR/discuss/voice-safety.md` 2026-08-16「全站語音轉文字確認機制」條目，這裡不重複記錄，只記錄與 2g 合併開工的事實。

**設計內容**：
①**`commands.py` 飲食（含飲水）區塊全面改寫**：`start_diet_menu()` 組「➕ 新增／🕐 補記／📋 查看清單／🔙 返回」子選單；`_start_diet_new_for_date()` 依指定日期（今天或補記日期）查詢食物／飲水各自是否已存在，決定要問哪些題目（兩者都有時直接導向編輯，見決策②）；新增流程狀態機依序為 `pending_diet_water_choice` → `pending_diet_water_amount` → `pending_diet_food_choice` → `pending_diet_food_input_mode`（文字走 `pending_diet_description`，照片走 `pending_diet_photo` → `pending_diet_photo_confirm`）→ `pending_diet_nutrition_source`（AI 直接估算，人工走 `pending_diet_manual_macros`）→ `handle_diet_build_summary()` 組合摘要 → `pending_diet_confirm` 二次確認關卡才真的寫入（`handle_diet_confirm_save()`）。
②**編輯**：`start_diet_edit()` 依既有紀錄的 `entry_type` 直接跳進對應子流程（不重問「要不要記另一項」），沿用「刪除舊列＋新增」的既有更新作法。
③**`body.py`**：`create_diet_log()` 新增 `nutrition_source` 參數；`format_diet_macro_note()` 依來源分「AI 估算附誤差聲明」／「使用者自己填寫」兩種文案；移除已無用的 `format_diet_entry_type_prompt()`／`resolve_diet_entry_type()`／`DIET_ENTRY_TYPES` 等舊版「二選一」設計的死碼。
④**`menu.py`**：`diet` 從 `_DAILY_LOG_NOT_YET_IMPLEMENTED_KEYS` 移除。
⑤**`router.py`**：`handle_callback_query()` 新增 `diet:<action>` 前綴分派（`new`／`backfill`／`list`／`edit:<id>`／`delete:<id>`／`confirm_delete:<id>`／`water_yes`／`water_no`／`food_yes`／`food_no`／`food_text`／`food_photo`／`nutrition_ai`／`nutrition_manual`／`confirm_save`）；`handle_photo_message()` 新增例外分支——使用者卡在 `pending_diet_photo` 時，照片要走 `commands.handle_diet_photo_message()` 複用飲食辨識邏輯，不落入既有一般圖片分析（FR-17）；`_dispatch_active_flow()` 新增對應 pending flow 文字分支；移除 `/log_diet`／`/backfill_diet`／`/my_diet_logs` 舊觸發詞（不提供相容期，比照 2c／2f）。
⑥**全站語音確認機制**（與 2g 合併開工，設計詳見 `voice-safety.md`）：`handle_voice_message()` 轉錄成功後改成先貼出轉錄文字＋確認按鈕（`pending_voice_confirm`），使用者按「✅ 正確，繼續」（`voice_confirm:accept`）或直接打字修正才接回原本卡在的流程；`handle_callback_query()`／`webhook.py` 的 callback_query 分支同步補齊 LLM／Telegram／GDrive Client 注入。

**理由**：飲食輸入方式與營養素來源選擇比照 Mobile App 既有設計是為了兩端使用者體驗一致，也直接複用已驗證過的 `app_diet_photo.py` 辨識邏輯，避免重寫一套風險更高的照片辨識流程（違反 FR-6h 精神）；single-daily 規則對齊 Mobile 是為了避免跨平台資料顯示與新增行為互相打架，這點原本 Telegram 端傾向維持「一天多筆」（更貼近使用者隨手記錄多餐的直覺），但 Robin 在確認 Mobile 端首頁卡片只抓最新一筆、新增會被 `_SINGLE_DAILY_KINDS` 擋下之後，改為對齊 Mobile；語音確認機制全站化是因為 `handle_voice_message()` 本來就是單一攔截點，比起要求使用者自行分辨哪些功能有這層保護、哪些沒有，全站統一行為更一致也更好維護。

**後果**：2g 開工後，`menu.py`／`commands.py`／`body.py`／`router.py`／`webhook.py` 均會異動；`tests/bot/test_commands.py`（飲食區塊全面改寫）／`tests/bot/test_router.py`（新增 `diet:*` 整合測試＋語音確認相關測試）／`tests/bot/test_menu.py`（`diet` 移出開發中名單斷言）／`tests/bot/test_voice.py`／`tests/bot/test_webhook.py`（語音/callback_query 分支回傳值與 Client 注入異動）皆需要同步改寫，範圍明顯大於 2c～2f 任一批（兩個架構層級改動疊加）。

**2026-08-16 開工進度（程式碼完成，尚未測試/未 commit）**：實作按設計內容①～⑥完成，`ast.parse` 語法驗證通過，人工比對既有 2c／2f 慣例確認 flow 命名、按鈕式二次確認、`callback_data` 前綴分派、「不提供舊指令相容期」等既定模式一致。**這批 Claude 沙箱完全沒有執行 `pytest`**——跟 2d／2e／2f「依賴鏈過深」的情況更進一步：本機 VM（`device_bash`）本身沒有網路，裝不了任何套件；嘗試把整個 repo 打包搬進雲端沙箱執行也因為 `tests/`／`submodules/` 依賴鏈規模（142 個 Python 檔案）風險過高而作罷，比照既有慣例改為只做語法驗證＋人工比對。**既有測試尚未改寫**：`tests/bot/test_router.py`／`test_voice.py`／`test_webhook.py`／`test_commands.py`／`test_menu.py` 都還沒動，預期既有語音相關測試斷言（例如「轉錄後直接回覆 XXX」）會因為新增的 `pending_voice_confirm` 確認關卡而全部失敗，飲食相關既有測試也會因為函式簽名／flow 名稱全面改寫而失敗，需要 Robin 本機跑一次 `python3 -m pytest tests/ -q` 把完整失敗清單回報回來，Claude 才能針對性修正測試、確認沒有遺漏的邊界情況，之後才能進到 commit 步驟。
