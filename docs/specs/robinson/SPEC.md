---
title: Robinson — Robin 與家人們的生活小助手
slug: robinson
status: draft
created: 2026-07-29
updated: 2026-08-08
owner: Robin
---

# Robinson

## 概要

Robinson 是一個雙前台架構的家庭生活小助手：Telegram Bot 作為 LUI（Language User Interface，語言型使用者介面），負責所有自然語言輸入（文字/語音/照片）、系統設定與資料的 CRUD 控制；Mobile App（React Native + Expo）作為唯讀的 Rich GUI，專注 BI 圖表展示（例如記帳消費圓餅圖、體態體重折線圖）與動態數據篩選，不提供任何寫入操作入口（**2026-08-04 更新，見 ADR-14**：原規劃的 Notion 視覺化後台已由 Mobile App 取代）。Robin 是產品負責人兼管理者，家人們透過通關密碼（Telegram）或 APP Access Token（Mobile App）取得使用權限。所有 AI 能力統一使用共用的 Gemini API（`gemini-3.5-flash-lite`，見 submodules-core SPEC.md ADR-6），資料分別存放在 Neon PostgreSQL（結構化資料）與 Google Drive（靜態圖像）。核心設計理念是「越少 UI 設定越好」，使用者以打字或語音跟 Robinson 對話即可完成大部分操作，Mobile App 僅補足 Telegram 不擅長呈現的圖表視覺化需求。

**專案緣起**：2026-07-28 Robin 先自行完成所有外部服務的註冊與 API 金鑰申請、Telegram Bot 基礎設定，並與 Gemini 進行腦力激盪與方案收斂 —— 梳理生活痛點、評估技術可行性、把發散的想法轉化為具體的 PRD 雛形；2026-07-29 才開始與 Claude Code 協作，產出本 spec 與 Codebase 規範等標準文件（詳見 [PROGRESS.md](./PROGRESS.md) 里程碑紀錄）。

**使用性質聲明**：本產品僅供 Robin 與家人「個人使用、非商業用途」，不對外公開、不收費、不提供第三方使用。此聲明是本 spec 內所有外部服務串接（YouTube Data API、104 求職網爬蟲等）合規性評估的基礎前提（見 NFR-13）。

## 名詞定義

| 名詞 | 定義 |
| --- | --- |
| Owner（Robin） | 產品負責人，擁有管理者 + 使用者全部權限，唯一免通關密碼者 |
| 使用者（家人） | 需通關密碼才能使用，僅有使用者權限 |
| 通關密碼 | Robin 為每位家人設定的一次性密碼，`is_used=1` 後失效，僅能被一人使用 |
| 功能開關 | 每個大功能模組都有獨立開關，全部關閉時 Robinson 退化為純聊天 Bot |
| 知識庫 | 分 4 類：通用背景、通用故事、使用者客製、使用者對話紀錄（詳見「知識庫架構」） |
| APP Access Token | Mobile App 專用的登入憑證（2026-08-04 新增，見 ADR-14），與 Telegram 的通關密碼機制彼此獨立、互不取代；一般使用者登入需另外搭配 `user_name`／稱謂，Robin 僅需 `user_name` |

## 系統架構總覽

| 層級 | 服務 | 角色 |
| --- | --- | --- |
| 前台 | Telegram Bot | 唯一使用者介面（文字 + 語音 + 圖片） |
| AI 層 | Gemini API（`gemini-3.5-flash-lite`，依用途拆四把 Key） | `GEMINI_API_BOT_KEY` 跑一般問答、`GEMINI_API_IMAGE_KEY1`／`GEMINI_API_IMAGE_KEY2` 跑影像辨識（每次隨機擇一）、`GEMINI_API_TEXT_KEY` 跑長文生成（見 ADR-12；模型版本見 submodules-core SPEC.md ADR-6） |
| AI 層 | Groq API（Whisper） | 語音轉文字（含多益錄音檔切割），對應 `VOICE_API_KEY`（見 ADR-12，取代先前「語音一律用 Gemini」的舊決策） |
| 資料層 | Neon PostgreSQL | 結構化資料（使用者、知識庫、待辦、記帳…） |
| 資料層 | Google Drive | 使用者上傳的圖片/語音檔案原始檔（含證照題目截圖），URL 統一記錄於 Neon（見 ADR-13） |
| 前台（唯讀） | Google Calendar（2026-08-05，見 FR-66、ADR-17） | 家庭共用行事曆：待辦事項、重要通知（節日/生日）、體態目標期限單向同步寫入，供家人用手機原生行事曆 App 瀏覽；單一共用行事曆，僅 Robin 帳號 OAuth 授權，家人訂閱即可看到，不需各自授權 |
| 前台（唯讀） | Mobile App（React Native + Expo，Phase 4，見 ADR-14） | BI Dashboard：圖表視覺化（消費圓餅圖、體重折線圖等）與動態數據篩選；後端計算好圖表 JSON 結構後回傳，App 端只負責渲染，不提供任何寫入/CRUD 入口（**取代原規劃的 Notion 後台**） |
| 排程 | cron-job.org | 每 10 分鐘打一次 keep-alive API，避免 Render 睡眠 |
| 部署 | Render（免費方案，750 hr/月） | 應用程式 Host |
| 資訊來源 | YouTube Data API v3 | 每週擷取技術情報影片候選清單，僅取中繼資料（含統計數字），不下載影音（見 FR-57～FR-59、ADR-21，supersede ADR-9） |

## 重要資產（不可刪除）

| 路徑 | 內容 | 說明 |
| --- | --- | --- |
| `docs/profile/Robinson.png` | Robinson 大頭照 | Robin 手動放置，供未來設定 Telegram Bot 頭像等用途使用。**任何情況下都不可刪除或覆寫此檔案**，包含清理暫存檔、重構專案結構等操作都必須明確排除這個路徑 |

## 需求

### 功能性需求 — 平台基礎

- [ ] FR-1：Telegram Bot 接收文字與語音訊息，語音需先轉文字再進入對話流程
- [ ] FR-2：每個功能模組（待辦、求職、記帳、體態、技術情報、證照準備、語言學習、心情小記、好友模式、重要通知）皆有獨立開關，全關時僅保留純聊天能力（**2026-08-07 修正**：原規劃的「技能成長」單一開關拆成「技術情報」「證照準備」「語言學習」三個獨立開關，見 FR-22／FR-23 說明與 feature-toggles SPEC.md FR-3 追記）
  - [ ] FR-2a：權限模型——一般使用者可自行開關「自己」的功能（例如對 Robinson 說「幫我關掉記帳」）；Owner 額外擁有代管權限，可調整任何使用者（含自己）的功能開關（**2026-07-30 決定**，見 Step 1.2 討論）
- [ ] FR-3：提供 `/healthz`（或等義）極簡 API，供 cron-job 每 10 分鐘呼叫，防止 Render 休眠。**2026-08-08（production 事故修復）**：Phase 2／3 陸續把多達 10 個排程檢查借用這個端點的呼叫頻率觸發（見 `main.py` `health_check()`），每天台灣時間 08:00 有 3 個排程（待辦每日摘要、重要通知、技術摘要推播）剛好卡在同一小時真的執行，Robin 實測單次 `/healthz` 耗時超過 40 秒，超過 cron-job.org 30 秒逾時被判定失敗。修正為：這 10 個檢查改成丟進背景 daemon thread 執行，`/healthz` 立即回 200，不等待檢查跑完；各檢查函式本來就有各自的去重設計（`daily_pushed_on` 等），背景執行緒偶爾跟下一次觸發重疊也不會重複推播
- [ ] FR-4：所有 AI 功能統一呼叫 Gemini API，模型固定 `gemini-3.5-flash-lite`（見 submodules-core SPEC.md ADR-6），全體使用者共用同一組對話 Token，圖像解析使用另一組獨立 Token

### 功能性需求 — 使用者與權限

- [x] FR-5：Robin 免通關密碼直接視為管理者兼使用者；其他使用者第一次互動須輸入通關密碼才能啟用
- [x] FR-6：通關密碼由 Robin 私訊逐一告知家人，每組密碼僅能被使用一次（用過標記 `is_used=1`），密碼與使用者為一對一綁定；設定方式採「僅限 Owner 觸發的引導式設定對話流」（Conversation State Machine），不提供任何後台表單：
  - [x] FR-6a：觸發方式 — 僅 Robin 可傳送 `/set_invite_codes` 指令或「設定通關密碼」文字，觸發 Robinson 進入設定模式；其他使用者觸發此指令一律無效
  - [x] FR-6b：對話式設定流程 — Robinson 詢問「請問要設定哪一位家人的稱謂？（例如：爸爸）」→ Robin 回覆稱謂 → Robinson 追問「收到，請輸入『<稱謂>』專屬的通關密碼：」→ Robin 輸入密碼 → Robinson 將 `(role, invite_code)` 寫入 Neon DB 並回覆「已寫入！請問還有其他家人要設定嗎？」→ 循環直到 Robin 輸入「沒有了」或「結束」，Robinson 確認並退出設定模式
  - [x] FR-6c：家人綁定機制 — 家人私訊 Bot 輸入正確密碼後，系統自動將其 `telegram_user_id` 與對應稱謂（role）綁定並開通使用者權限，同時把該密碼標記 `is_used=1`
  - [x] FR-6d：歡迎訊息 — FR-6c 綁定成功的當下，Robinson 立即回傳固定的歡迎訊息範本（不經過 LLM 生成，純靜態文字，節省 Token），內容見「附錄 A：規範文本」；**假設**：此訊息目前僅設計給家人在完成通關密碼綁定時觸發，Robin 本人因免密碼直接視為管理者，不會走這個綁定流程，若 Robin 也想在第一次互動時收到這則訊息，需另外確認觸發時機
- [ ] FR-7：每位使用者有唯一 ID；家人若要新增/調整功能或排程（待辦通知排程除外），必須經 Robin 手動設定，Robinson 不自行開放
- [ ] FR-8：待辦事項的推播排程是唯一允許使用者自行調整的排程項目

### 功能性需求 — 內建說明指令

- [x] FR-55：`/rule` 路由 — 使用者在對話框輸入「我要看使用規則」（或直接輸入 `/rule`）時，直接觸發 `/rule` 路由，回傳與 FR-6d 相同的「附錄 A：規範文本」，不經過 LLM 生成，任何身分（Robin 或家人）皆可觸發
- [x] FR-56：`/function` 路由 — 使用者在對話框輸入「我要看所有功能」（或直接輸入 `/function`）時，直接觸發 `/function` 路由，回傳「功能總覽」：條列式列出所有功能模組名稱與一句話簡述，並註記哪些為 Owner（Robin）專屬、哪些所有使用者皆可用；**不在總覽階段就展開每個功能的細節或情境範例**，避免一次回傳過多文字不利閱讀。**2026-07-31 完成（Step 1.3a）**：展開為獨立 [docs/specs/chat-core/SPEC.md](../chat-core/SPEC.md) FR-9／ADR-4，總覽獨立小型 LLM 呼叫，細節追問併入一般聊天核心：
  - [x] FR-56a：功能細節按需展開 — 使用者針對特定功能追問時（例如「記帳功能可以做什麼？」），才回傳該功能的完整能力說明（例如：能新增、修改、清除記帳項目）
  - [x] FR-56b：情境範例 — 每個功能的細節說明都必須附上至少一組情境範例（模擬使用者與 Robinson 的多輪對話），引導使用者了解怎麼開口使用該功能；各功能的實際範例文案於該功能模組實作時，由 Robin 提供或由 Claude 草擬後經 Robin 確認才定案（記帳模組範例已由 Robin 提供，見 FR-56d）
  - [x] FR-56c：人格化語氣 — 除了 FR-55（`/rule`）與 FR-6d（歡迎訊息）等明確定義為「固定文字、不經 LLM 生成」的規範性文本外，其餘所有對話回覆（含 `/function` 的功能說明）都必須先參考知識庫中的「Robinson 人格背景」，把內容轉換成人類自然口語的語氣再回覆使用者；任何模板或整理好的清單只作為 Robinson 內部組織回覆內容的素材，不可以逐字照搬模板全文直接回傳給使用者
  - [x] FR-56d：記帳功能情境範例（Robin 提供，直接採用，做為其他功能撰寫範例的參考格式）：
    - 情境1（單筆快速記帳）：使用者：「早餐花80元」→ Robinson：「好的，幫你記錄好了喔～」
    - 情境2（設定月度目標，多輪對話）：使用者：「我想要設定這個月目標」→ Robinson：「什麼目標？」→ 使用者：「記帳功能」→ Robinson：「那你這個月的記帳目標是要看支出就好，還是要看能存多少？」→ 使用者：「儲存」→ Robinson：「那你告訴我這個月總收入與要儲存的目標」→ 使用者：「收入50000元，想要存10000元」→ Robinson：「好喔！幫你記錄好了～」
  - [x] FR-56e：待辦事項功能情境範例（Robin 提供，直接採用；對應 FR-31、FR-31a、FR-32）：
    - 情境1（單筆快速記錄＋提醒設定）：使用者：「我下午要去買菜」→ Robinson：「要幫你紀錄到待辦事項嗎？」→ 使用者：「好」→ Robinson：「下午幾點呢？」→ 使用者：「三點」→ Robinson：「那要在前 30 分鐘時提醒你嗎？」→ 使用者：「好」
    - 情境2（模組判斷歧義＋完整流程）：使用者：「打籃球」→ Robinson：「請問這是紀錄體態管理，還是要紀錄到待辦事項呢？」→ 使用者：「待辦事項」→ Robinson：「好的，請問是什麼時候做呢？」→ 使用者：「明天晚上」→ Robinson：「幾點？」→ 使用者：「7:30」→ Robinson：「已收到 2026/07/31 19:30，明天早上會先通知您一次，若你使用查詢功能，我也會再跟你說一次，需要在前 30 分鐘時提醒你嗎？」→ 使用者：「不用」→ Robinson：「好的」
    - 補充規則（FR-31a）：待辦事項若已超過預定執行時間，或使用者說已完成／取消，該筆待辦要被標記結束
  - [x] FR-56f：求職功能情境範例（Robin 提供，直接採用；對應 FR-33、FR-36、FR-37）：
    - 情境（設定條件＋收集履歷與期望工作，多輪對話）：使用者：「我最近想要找工作了」→ Robinson：「好的，你有什麼特別的需求嗎(找 AI 相關？只在台中市？薪資待遇區間要在 45000 元以上？年資要求在 1-3 年？學歷要求學士以上？)」→ 使用者：「我想找 AI、資料相關的，然後不限地區，薪資待遇區間 50000元以上，其他沒特別要求」→ Robinson：「好的，但我要提醒你一下，這個功能一週只會做一次喔，要等到排程啟動後，我才能給你清單與連結，然後我需要你給我『詳細的履歷敘述(3500字以內)，記得不用給您的個資資訊如電子郵件或手機號碼等』和『未來期望工作敘述(期望工作內容、企業文化、薪資、福利等)』，你準備好了嗎？」→ 使用者：「好了」→ Robinson：「先給我詳細的履歷敘述(3500字以內)！」→ 使用者：「（履歷內容）」→ Robinson：「有需要修正嗎？沒有的話再給我未來期望工作敘述」→ 使用者：「（期望工作內容）」→ Robinson：「有需要修正嗎？沒有的話我直接紀錄喔！」→ 使用者：「好的」
    - 補充規則：取得使用者履歷與期望工作內容後，加上每週排程取得的職缺資料，即可進行契合度比對（FR-37）
  - [x] FR-56g：體態管理功能情境範例（Robin 提供，直接採用；對應 FR-46～FR-48）：
    - 情境1（純紀錄，選擇子功能）：使用者：「體態管理」→ Robinson：「你要純粹紀錄就好，還是想要有一個目標？」→ 使用者：「紀錄就好」→ Robinson：「好的，那你想要使用『身高和體重』、『運動習慣』、『飲食記錄』哪一個功能呢？還是全都用？」→ 使用者：「身高和體重」→ Robinson：「那先告訴我你的身高？」→ 使用者：「173」→ Robinson：「體重呢？」→ 使用者：「80」→ Robinson：「OK，已幫你紀錄」
    - 情境2（設定目標＋主動給建議，多輪對話）：使用者：「我要設定體態管理目標」→ Robinson：「請問你是要完成哪一種目標？(BMI？完成某項運動挑戰？飲食完美控制？)」→ 使用者：「體重目標」→ Robinson：「請告訴我目標值」→ 使用者：「60 公斤」→ Robinson：「有預計完成時間嗎(例如：三個月內完成)」→ 使用者：「三個月」→ Robinson：「三個月內瘦到 60 KG，已幫你紀錄了，那需要提供建議嗎？」→ 使用者：「好」→ Robinson：「先告訴我你現在的體重」→ 使用者：「75」→ Robinson：「我的建議是……」
    - 情境3（模組判斷歧義＋估算免責聲明）：使用者：「我今天有跑步 30 分鐘，大約 5 公里」→ Robinson：「請問這是心情小記紀錄，還是要我幫你紀錄運動習慣呢？」→ 使用者：「運動習慣」→ Robinson：「那你有心率紀錄嗎？」→ 使用者：「沒有」→ Robinson：「OK，那你今天大約消耗了 ... 卡路里，這個數字只是估算值，不會到很準確喔！」
    - 補充規則（對應 FR-46）：目標不限於瘦身，可以是各種體態相關目標；記錄身高體重前需做合理範圍檢查（成人身高約 140～220 公分、體重約 40 公斤以上），數字明顯異常需先跟使用者確認
  - [x] FR-56h：心情小記功能情境範例（Robin 提供，直接採用；對應 FR-49、FR-50）：
    - 情境（心情分類選單＋日記內容）：使用者：「我想做心情筆記」→ Robinson：「好啊，那你今天的心情狀態如何？請幫我選一個 (生氣/焦慮、難過/低落、疲倦/厭世、普通/平淡、平靜/放鬆、高興/興奮)」→ 使用者：「高興/興奮」→ Robinson：「給我完整的日記內容」→ 使用者：「（日記內容）」→ Robinson：「好的，已經紀錄了」

### 功能性需求 — 客訴收集

- [x] FR-60：`/complaint` 路由 — 使用者在對話框輸入「我要客訴你」（或直接輸入 `/complaint`）時，直接觸發 `/complaint` 路由，Robinson 固定回覆「請問你覺得哪個地方需要改進呢？」（不經過 LLM 生成），並進入等待客訴內容狀態；任何身分（Robin 或家人）皆可觸發（**2026-08-02 Step 1.9 實作**）
- [x] FR-61：客訴記錄 — 使用者在 FR-60 觸發後回覆的下一則訊息，視為客訴內容，寫入 Neon DB 客訴紀錄表（含使用者 ID、時間戳記、原始文字）（**2026-08-02 實作**：內容套用 FR-13 個資遮蔽，跟一般聊天/圖片/語音/心情小記四個既有入口一致）
- [x] FR-62：客訴分析 — FR-61 寫入完成後，立即呼叫 Gemini 分析客訴內容，產出「可能問題點」與「修正/優化建議」，私訊給 Robin；**此為刻意的隱私例外**：一般情況下 Robin 看不到其他使用者的對話紀錄（FR-11），但客訴內容的本質就是「使用者主動想讓 Robin 知道」，因此不受 FR-10/FR-11 資料隔離規則限制（**2026-08-02 實作**：分析與私訊失敗不影響客訴內容已成功記錄，只記錄 log；找不到 Robin 的 users 記錄時同樣優雅跳過）
- [x] FR-63：人工決策與後續討論 — Robin 收到 FR-62 的分析報告後自行決定如何處理（是否採納、如何調整），不強制自動執行任何變更；Robin 可與 Robinson 對話討論後續調整方向，比照 NFR-8 的 Human-in-the-Loop 精神，但客訴處理屬於產品/內容/流程層級的決策，不涉及程式碼變更（純人工流程，不需要額外程式碼實作）

### 功能性需求 — 知識庫架構

- [ ] FR-9：知識庫分四類：① 通用－Robinson 人格與背景、② 通用－Robin 與家人的背景故事、③ 客製－使用者自建知識庫（Robin 的客製知識庫涵蓋管理者與使用者身份，不拆分）、④ 客製－使用者對話紀錄
- [ ] FR-10：資安隔離 —— 一般使用者只能看到「通用知識庫」與「自己建立的客製知識庫」，看不到其他人的客製知識庫與對話紀錄
- [ ] FR-11：Robin 雖有全部權限，但在 Telegram Bot 介面上同樣看不到其他使用者的知識庫與對話紀錄，僅能自行連 Neon 下 SQL 查詢
- [ ] FR-12：Robinson 只根據知識庫既有內容回答，不主動做 Web Search；若使用者提供网路查到的答案，Robinson 需記錄進資料庫

### 功能性需求 — 資安與行為治理（"警察證"）

- [x] FR-13：偵測到使用者傳送個資時，提醒使用者盡快收回訊息，並觸發刪除機制清除知識庫與對話紀錄中的敏感內容；遮蔽模組（Masking Filter）採「Regex 硬規則 + LLM 語意辨識」雙層防線（2026-08-02 完成，展開為獨立 [docs/specs/privacy-masking/SPEC.md](../privacy-masking/SPEC.md)；架構決策：遮蔽在「寫入 Log／送外部 API 之前」就先在原始文字上完成，等於命中的內容從此不會以明碼形式存在，天然達成「清除敏感內容」的效果，不需要另外一支事後掃描刪除的批次流程）：
  - [x] FR-13a：Regex 硬規則需覆蓋以下台灣在地敏感個資格式：① 身分證字號（含大小寫，如 A123456789／a123456789）② 手機號碼（含各式分隔符，如 0912345678／0912-345-678／0912 345 678）③ 市話號碼（含區碼與括號，如 04-22334455／(04)2233-4455）④ 銀行帳戶（含銀行代碼與帳號，如中國信託 123456789012／822-123456789012）⑤ 信用卡號／CVV（16 位卡號與後三碼）⑥ 健保卡號（12 位數字）⑦ 地址資訊（含縣市/鄉鎮市區/路段/門牌號碼/樓層之台灣地址）⑧ 車牌號碼（新舊型車牌，如 ABC-1234／1234-AB）（`src/bot/privacy.py::mask_regex()`；已知限制：CVV 因為只有「後三碼」沒有固定上下文關鍵字可辨識，目前未單獨處理，僅隨附在 16 碼卡號一起被抓到才會遮蔽，卡號後面單獨出現的 3 碼 CVV 不會被 Regex 層攔到，需靠 LLM 語意層補強）
  - [x] FR-13b：LLM 語意辨識作為第二道防線，補足 Regex 無法涵蓋的變形寫法或上下文語意判斷（`src/bot/privacy.py::mask_with_llm()`，用獨立 `GEMINI_API_PRIVACY_KEY`，見 privacy-masking SPEC.md ADR-1）
  - [x] FR-13c：排除項目 — 生日與 LINE ID 不需遮蔽（生日作為背景邏輯資料使用，LINE ID 無輸入需求）（測試涵蓋反例，見 `test_privacy.py`）
  - [x] FR-13d：處理時機 — 凡符合上述 Regex 條件或經 LLM 語意判定為敏感個資者，在寫入 Log 或傳送至外部 API 前，一律強制轉換為固定遮蔽文字（Masking）（**實作微調**：原文寫「星號遮蔽」，實作改用固定標記文字 `[已遮蔽個資]` 取代連續星號，理由是純星號在訊息中容易跟一般強調符號混淆、也看不出「這裡曾經有個資」的明確語意，固定標記文字更清楚）
- [x] FR-14：語音訊息超過 10 分鐘強制中斷處理，並提醒使用者語音長度限制（2026-08-01 完成，見 `src/bot/voice.py` 的 `exceeds_duration_limit()`：用 Telegram 訊息本身就帶的 `duration` 秒數判斷，不需要先下載檔案就能擋下，避免浪費 Drive／Groq 額度）
  - [x] FR-14 規則 1：單次語音「本身」超過 10 分鐘時，語音功能整體鎖定 15 分鐘，這段期間任何語音訊息都拒絕（不限於修正情境）（**2026-08-02 完成**：Robin 澄清這是跟 FR-15 獨立的兩條規則，原本只有 FR-15 的「修正情境」鎖定，漏了「單純超時本身」的全面鎖定；見 `src/bot/voice.py` 的 `mark_duration_violation()`／`is_locked_out_from_duration_violation()`，用獨立的 `ConversationStateStore` 記憶體儲存最近一次超時的時間點，因為超時的語音一開始就不會寫入 `media_uploads`，無法沿用 FR-15 查 DB 時間戳記的作法）
- [x] FR-15：語音轉文字結果如需修正，僅能用打字編輯；自該筆語音訊息送出起 15 分鐘內，若使用者仍嘗試用語音修正，Robinson 需拒絕並提醒改用打字，不得執行語音轉文字；超過 15 分鐘後，語音模式恢復可用，不再限制（2026-08-01 完成，見 `src/bot/voice.py` 的 `is_within_correction_window()`：查該使用者 `media_uploads` 最近一筆 `audio` 記錄的時間判斷，不需要額外的資料表或記憶體狀態；被擋下的嘗試不會產生新記錄、不會延長窗口）。**2026-08-02 補充**：語音成功轉出文字、回覆送出前，會主動附註一句提醒（`router._VOICE_TRANSCRIBED_REMINDER`），告知使用者這 15 分鐘修正窗口已經開始、想修正請改用打字——避免使用者只能靠「再傳一次語音被拒絕」才被動發現被鎖定。鎖定到期本身沒有主動通知（機器人是被動回應訊息的架構，沒有排程/推播機制），使用者下次互動時語音自然就能用了
- [ ] FR-16：Robinson 不自行腦補做決策，涉及寫入/修改資料庫的操作前一律先與使用者確認
  - [x] FR-16a：語音輸入的最終執行確認 — 涉及刪除或寫入資料庫的高風險操作（`/clean-all-dialog`、`/clean-target-dialog`、主動記知識），在使用者以自然語言表達「確定」之後，不得直接執行，必須再要求使用者以**打字**逐字輸入固定關鍵字才能真正執行；這一步驟語音輸入一律視為未通過（**2026-08-02 完成**：Robin 提出情境「使用者用語音說執行 A 決策，但 LLM 聽錯了，直接執行 B 決策，且已刪除的紀錄無法回頭補上」，指出單靠一次寬鬆的 LLM CONFIRM/CANCEL 語意分類撐不住語音誤判的風險；`commands.py` 三個高風險 flow 新增 `pending_*_final_confirm` 狀態，要求逐字輸入「確認執行」；`router.py` 新增 `via_voice` 參數，`handle_voice_message()` 呼叫 `handle_message()` 時固定傳 `True`，`_dispatch_active_flow()` 依此拒絕語音輸入完成最終確認，且刻意不讓語音訊息清除 `pending_*_final_confirm` 狀態，避免使用者搞不清楚原本的操作算不算數——**追加優化**：Robin 追問卡在此狀態時收到新語音會如何處理，發現初版是先下載/轉錄才拒絕、浪費額度，修正為在下載/轉錄之前就短路回覆，比照 FR-14/FR-15「先擋才不浪費額度」的原則）
- [x] FR-17：開放接受一般圖片供 Robinson 辨識使用（不再侷限於「證照題目」用途），但僅支援圖片與音檔兩種檔案類型；使用者上傳 PDF、Excel、PPT 等其他格式檔案時，模型無法直接處理，須明確告知使用者「這個檔案格式我沒辦法處理喔，只能看懂圖片和音檔」並說明原因，不可靜默忽略或誤導使用者以為已處理（**2026-07-31 完成**：`webhook.py` 的 `_extract_unsupported_file` 偵測 document/video/video_note/animation/sticker 直接回拒絕文案；**2026-08-01 完成**：`voice`／`audio`（錄音鍵語音訊息與使用者上傳的音檔）兩種訊息類型皆已支援，見 Step 1.4——**追加修正**：Step 1.4 完成當下只做了 `voice`，Robin 回報「除了照片和音檔外的檔案格式才無效」才發現漏了 `message.audio`（上傳的音檔），這是範圍沒抓對 FR-17 原文承諾，已補上，見 `webhook._extract_voice()`）：
  - [x] FR-17a：個資影像警語 — 使用者上傳任何影像前，必須被告知「不准上傳包含個人資料的影像，後果需自行承擔」，此警語記錄於附錄A使用須知，供使用者事前知悉
  - [x] FR-17b：不確定內容須詢問使用者 — 影像辨識若有無法判斷的部分（例如：使用者上傳一道菜的照片，但部分食材被遮住看不清楚），Robinson 不可盲目猜測，必須明確詢問使用者以確認內容後才繼續分析（**2026-07-31 完成**：`src/bot/image.py` 用 `[NEED_CONFIRM]` 標記慣例讓 LLM 主動回報不確定處，`pending_image_confirm` 對話流程接住使用者的澄清後重新分析一次）
  - [x] FR-17c：飲食分析誤差聲明 — 只要是飲食成分分析（不論透過影像、語音或文字方式取得），一律必須告知使用者分析結果存在部分誤差，不可讓使用者誤以為是精確數值（**2026-07-31 完成**：內嵌於 `image.py` 的 Prompt 規則中，由 LLM 依情境自行判斷是否適用）
- [ ] FR-18：不接受用於錄製會議或長篇演講的長語音（見 FR-14 十分鐘上限）

### 功能性需求 — 服務健康與治理

- [ ] FR-19：服務發生例外或錯誤時，對所有使用者僅回覆「生病了」等安全用語、不揭露技術細節；同時 Robinson 需完整記錄錯誤情境並提供 Robin 專屬的完整診斷資訊管道，不得在未經 Robin 同意前擅自變更系統。**2026-07-31 補充**：Step 1.3a 上線後實測撞到 Gemini 429 額度超限，發現 `webhook.py` 未攔截例外會讓 Telegram 重試風暴加速燒額度，已提前補上最小安全網（見 [platform-auth SPEC.md](../platform-auth/SPEC.md) FR-7）；這只解決「重試風暴」這個具體風險，不是本條 FR-19 的完整實作。**2026-08-05 更新（見 ADR-15，supersede ADR-7）**：原規劃的 FR-19b～FR-19e「AI 自主診斷＋衝擊評估＋GitHub PR 自動化」整套 Human-in-the-Loop 機制已取消，FR-19b 改寫為更輕量的「完整錯誤 log 上傳雲端＋私訊 Robin 專屬連結」設計，FR-19c／FR-19d／FR-19e 三條需求編號直接移除（內容併入新版 FR-19b）；FR-19f～FR-19i（分級降級／執行回饋／重試機制）不受影響，仍待 Step 2.5～2.6：
  - [x] FR-19a（2026-08-02 完成，Step 1.6）：捕獲異常與 Log — 完整記錄系統錯誤 Traceback 與發生情境（觸發功能、使用者輸入摘要、時間戳記等），寫入集中式 log。實作：`main.py` 的 `logging.basicConfig` 加上 `asctime`；`webhook.py` 的 `_logger.exception()` 記錄「觸發功能」（photo/voice/text）與 `telegram_user_id`；額外新增 `_notify_robin_of_error()`，把完整 Traceback＋發生情境（含使用者輸入摘要，過長自動截斷）私訊給 Robin（簡化版通知，Phase 1 不含 FR-19b 的雲端 log 連結，留待 Step 2.4）
    - **2026-08-02 追加修正（Robin 回報「打字給 Robinson 完全不理我」）**：原本 `webhook.py` 只在「有拋例外」時才確保回覆非空（安全用語），但沒拋例外、`handle_message()` 剛好回傳空字串時（例如 Gemini 那次生成剛好回傳空內容），`if reply:` 判斷為 False，完全不會呼叫 `send_text()`——使用者只會看到已讀不回，連安全用語都收不到，等於違反 FR-19h「嚴禁靜默或無明確狀態反饋」的精神。修正：`webhook.py` 在 `if reply:` 之前加一層獨立防呆（`not reply or not reply.strip()`），空/純空白回覆一律換成新增的 `_EMPTY_REPLY_FALLBACK`（措辭跟例外安全語區分，讓使用者知道是「這句沒接上」而非「系統掛了」），並記警告 log 方便事後排查（沒有 Traceback 可私訊 Robin，這種情況不觸發 FR-19a 的錯誤通知）。
  - [x] FR-19b（**2026-08-05 改寫並完成，見 ADR-15**）：完整錯誤 log 上傳雲端＋Robin 專屬連結 — 例外發生時，把完整 Traceback（含發生的 py 檔案／行號／函式呼叫堆疊，Python 內建即有）、觸發功能、使用者輸入摘要、時間戳記組成一份 log 檔案，透過既有 `submodules/gdrive/client.py` 的 `GDriveClient.upload_file()` 上傳至 Google Drive，取得可分享連結。**對其他所有使用者（含觸發當下的一般使用者與其他家人）一律只回覆既有的「生病了」安全用語，絕不揭露技術細節或連結**；只有私訊 Robin 的 `_notify_robin_of_error()` 訊息會額外附上這個 Google Drive log 連結，讓 Robin 自己點開查看完整內容（甚至可另外交給 Claude Code 協助排查修復），不再需要看被截斷的 Traceback 片段。上傳失敗（例如 Google Drive API 暫時性錯誤）不得影響「生病了」安全用語與私訊 Robin 這兩件事本身正常送出，優雅降級為訊息中略過連結欄位並記警告 log。實作：`webhook.py` 新增 `_upload_error_log()`（封裝 `GDriveClient` 呼叫與例外優雅降級）與 `_ERROR_LOG_FILE_TEMPLATE`（未截斷的完整 log 檔案內容），`_notify_robin_of_error()` 延伸為同時上傳 log 並在私訊訊息附加連結；`_ROBIN_ERROR_NOTIFY_TEMPLATE` 新增 `{log_link_line}` 欄位（無連結時為空字串）；全專案 709 個測試全過，`webhook.py` 達到 100% 覆蓋率。**2026-08-05 追加（見 ADR-16）**：Robin 提出「如果壞掉的是 Telegram 本身，不就沒辦法通知？」——Telegram 是唯一對外管道，`_notify_robin_of_error()` 本身送達失敗時完全沒有備援，只會記一行 log。新增 `submodules/email`（`EmailClient`，`smtplib` 直打 Gmail SMTP，複用既有 `GMAIL_USER`／`GMAIL_PASSWORD`）當獨立備援管道：`webhook.py` 新增 `_send_email_fallback()`，`_notify_robin_of_error()` 拆成「組裝內容」與「透過 Telegram 送達」兩段 try/except，只有後者失敗才觸發 email 備援（內容含完整 Traceback，跟 Telegram 訊息同等資訊量）；email 本身也失敗只記 log，不再有下一層備援，這是刻意的設計邊界；全專案 720 個測試全過，`webhook.py`／`submodules/email/client.py` 皆達到 100% 覆蓋率
  - [x] FR-19f（**2026-08-07 完成，見 Step 2.6**）：例外分級降級 —「一般感冒級」：當 Try 流程中 LLM API 本身仍可正常連線與推送訊息，僅其他元件異常（資料庫連線失敗、爬蟲解析錯誤、第三方 API 逾時等，且已用盡 FR-19i 的重試機制）時，由後端捕捉例外後私訊完整錯誤詳情給 Robin，並回覆使用者靜態感冒語句（不額外呼叫 LLM 生成，節省 Token）。範本：「🤒 主任，我好像有點小感冒（系統暫時性異常），不過別擔心！我已經自動紀錄日誌通知 Robin 處理囉，請稍後再試一次！」（**實作**：`webhook.py` 新增 `_GENERAL_COLD_REPLY` 固定範本、`_is_llm_failure()` 分類判斷式，凡不屬於 LLM API 本身失敗的未預期例外，一律回這句並照舊呼叫 `_notify_robin_of_error()`）
  - [x] FR-19g（**2026-08-07 完成，見 Step 2.6**）：例外分級降級 —「重大疾病級」：當 Try 區塊執行到呼叫 LLM API（如 `call_llm_api()`）本身直接拋出例外（Gemini 伺服器 500、API Key 失效、額度用罄、網路斷線等，且已用盡 FR-19i 重試機制），代表 LLM 已完全無法處理任何請求或推送訊息。此時必須完全繞過 LLM，直接由 Telegram Bot 底層讀取寫死在後端的靜態字串範本：① 向 Robin 推播最高等級的 StackTrace 告警 ② 同時向所有已綁定的家人帳號廣播重大疾病通知。範本：「🚨 主人與各位家人非常抱歉，我最近患上了重大的疾病（AI 核心服務暫時無法運作），目前無法回答任何問題。Robin 已收到緊急通知並正在全力搶救中！」（**實作**：`webhook.py` 新增 `_MAJOR_ILLNESS_REPLY` 固定範本；`_is_llm_failure(exc)` 用 `LLMQuotaGuardError`（本地端節流保護，見 submodules-core SPEC.md ADR-5）與 `google.genai.errors.APIError`（涵蓋 Gemini 官方回傳的 `ServerError`／`ClientError`）兩種「唯獨呼叫 LLM 才會拋出」的例外型別判斷是否為 LLM 本身失敗，不會跟其他元件的例外混淆；`_notify_robin_of_error(..., severity="critical")` 在通知內容前加上 `_CRITICAL_SEVERITY_BANNER` 最高等級告警橫幅；新增 `_broadcast_major_illness_to_family()` 廣播給所有已綁定家人（排除 Robin 自己——他走告警橫幅；排除觸發當下的使用者——他已經透過主流程的 `reply` 收到同一句話，避免重複發送），單一使用者傳送失敗不影響其他人）
  - [x] FR-19h（**2026-08-07 完成，見 Step 2.6**）：決策執行狀態閉環回饋 — 所有涉及資料異動的操作（寫入 DB、記帳、體態/心情紀錄、新增待辦等），在使用者做出最終「確認」指令後，不論成功或失敗都必須明確回覆結果，嚴禁靜默或無明確狀態反饋：① 成功 — 明確告知操作已成功落實（例：「好的！已成功為您紀錄今日晚餐開銷 $150 元囉！」）② 失敗（一般感冒級）— 依 FR-19f 語句告知未成功並已通知 Robin 處理中 ③ 失敗（重大疾病級）— 依 FR-19g 底層寫死範本回覆（**稽核結果**：本條屬於架構層級已滿足、不需要逐一修改每個功能模組的驗證型任務——`src/bot/finance.py`／`todo.py`／`mood.py`／`router.py` 皆確認沒有任何 `except` 包住 DB 寫入呼叫（`body.py` 唯二的 `except` 只包住「選配的 LLM 卡路里/營養估算」，估算失敗刻意優雅降級不擋下紀錄本身，不影響 DB 寫入的例外傳遞），代表任何資料異動操作失敗時，例外會一路往外傳到 `webhook.py` 單一進入點的 `try/except`，被 Step 2.6 新增的分級邏輯接住、絕不會靜默；成功路徑則從 Phase 1/Phase 2 各模組實作起就已經內建明確的確認文案（例如「已經幫你記錄好了！」「已經刪除這筆心情紀錄了！」，見 `src/bot/commands.py` 各 flow 的 `return` 文字），本條無需新增額外程式碼，僅為驗證與記錄）
  - [x] FR-19i（**2026-08-07 完成，見 docs/specs/submodules-core/SPEC.md FR-13、ADR-13**）：外部 API 呼叫重試機制 — 所有外部 API 呼叫（Gemini/OpenAI API、Telegram Bot API、104 AJAX API 等）皆須內建自動重試：最多重試 3 次（Max Retries = 3），採 Exponential Backoff 搭配 Time Sleep（第 1 次失敗等 1 秒、第 2 次失敗等 2 秒、第 3 次失敗等 4 秒），避免連續轟炸外部 API 觸發封鎖或 Rate Limit；3 次全部失敗才正式判定該次 Request 失敗，並依錯誤來源進入 FR-19f 或 FR-19g 的分級流程。**實作範圍**：新增共用工具 `submodules/retry`（`call_with_retry()`），`llm`／`telegram`／`voice`／`gdrive`／`calendar`／`email` 六個既有子模組皆已套用，只重試「暫時性錯誤」（連線失敗、逾時、HTTP 429／5xx），永久性錯誤（401/403/404 等）直接往外拋不浪費重試次數；104 求職爬蟲 API 屬於 Phase 4 才會存在的程式碼，留待那時比照辦理；本條只完成「重試機制本身」，3 次全部失敗後把最後一次的原始例外原封不動往外拋出，讓呼叫端既有的 `except` 邏輯不需要改動——「依錯誤來源進入 FR-19f 或 FR-19g 的分級流程」這段留待 Step 2.6 在這個基礎上建立
- [x] FR-20（2026-08-02 完成，Step 1.6）：問題修復後（Robin 手動修復），Robinson 需主動回訊息告知所有使用者「我康復了」；此廣播主要對應 FR-19g（重大疾病級）的全員影響情境，FR-19f（一般感冒級）僅私訊 Robin、未廣播全員，修復後是否額外告知該次受影響的使用者由 Robin 自行決定。**Phase 1 實作範圍**：「有沒有修好」完全由 Robin 自己判斷（**2026-08-05 更新，見 ADR-15**：FR-19b 已改為輕量的雲端 log 連結設計，不再有 AI 自主修復／GitHub PR 機制，本條「Robin 自己判斷」為長期定案，非過渡狀態），新增 Owner 專屬指令 `/recovered`（`commands.handle_recovered()`），手動觸發時廣播固定文案給所有已綁定家人（排除 Robin 自己）
- [x] FR-21（2026-08-02 完成，Step 1.6，僅 Neon 容量部分）：監控 Neon 容量（達 80% 告警）、Gemini 免費額度用量等異常指標，超過門檻時主動通知 Robin。**Phase 1 實作範圍**：只做 Neon 容量監控（`src/bot/monitoring.py`，`NeonCapacityMonitor`），借用 `/healthz` 既有的 cron-job.org 每 10 分鐘呼叫頻率順便檢查，容量達 80% 私訊 Robin、回落後重置告警狀態避免重複轟炸；Gemini 免費額度用量監控刻意暫緩——官方沒有查詢即時用量的 API，本地端節流計數器（ADR-5）只能粗略估算「每分鐘呼叫次數」，無法真的得知「今天/這個月還剩多少免費額度」，準確度有限，且既有的 429 例外已經會走 FR-19a 私訊機制當作事後告警，留待未來有更好方案或官方 API 支援時再補上主動式監控

### 功能性需求 — 個人技能成長（僅 Robin 可用）

- [x] FR-22（**2026-08-07 完成並修正，見 Step 3.1；2026-08-09 推播格式再修正，見 ADR-25**）：每日固定時間自動推播技能成長摘要——經 Robin 回饋修正為「收集」與「推播」兩個獨立排程時間點：固定台灣時間 23:00 收集當天的技術情報（`src/bot/skill_growth.collect_and_store_daily_digest()`），固定隔天台灣時間 08:00 推播前一晚收集到的摘要（`check_and_push_daily_digest()`），兩者都借用 `/healthz` 既有的 10 分鐘 cron 頻率、各自只在對應的小時內執行；去重靠 `skill_growth_digests` 表（`UNIQUE (digest_date, source)` 約束收集去重、`pushed_on` 欄位比照 `todos.daily_pushed_on` 慣例做推播去重，同一天的幾筆一起標記）。**2026-08-09 修正（見 ADR-25）**：推播內容改為 Robin 指定的三行式精簡格式（「1.TLDR 電子報總結分享：……」「2.ithome新聞總結分享：……」「3.TechCrunch新聞總結分享：……」），不再輸出原文條列內容，方便 Robin 一眼判斷哪個來源當天沒有內容或收集異常
- [x] FR-23（**2026-08-07 完成並修正，見 Step 3.1、submodules-core SPEC.md ADR-11 追記／ADR-14；2026-08-09 改為三來源各自獨立摘要，見 ADR-25**）：每日重點技術分享（開關）：固定台灣時間 23:00 擷取 Gmail「當天」TLDR 電子報 + IThome / TechCrunch「當天」新聞，三個來源各自獨立經 Gemini 產出中文重點摘要，隔天 08:00 推播（依 NFR-11，以來源日期避免重複摘要已處理過的電子報/新聞）。實作細節：①TLDR 電子報寄件者固定為 `dan@tldrnewsletter.com`，用 `submodules/email` 新增的 `fetch_emails_from_domain_on_date(sender_domain, target_date)`（IMAP，寄件者網域比對 `tldrnewsletter.com`，經 AskUserQuestion 確認；呼叫端指定日期，不假設「今天」或「昨天」）②IThome／TechCrunch 用新增的 `submodules/newsfeed`（RSS Feed，`requests`＋標準函式庫 `xml.etree.ElementTree`，同樣以指定日期查詢）③三個來源任一失敗只記 log、視為當天無內容，不影響其他來源與整體收集④單一來源當天沒內容時，該來源不呼叫 Gemini（`summary_text` 寫入固定文字「今日無內容」，見 ADR-25），推播階段若完全查無前一晚的收集結果（例如收集當下服務整小時都不可用）一律回覆 Robin 指定的固定訊息「未獲得最新技術分享」，不靜默跳過（NFR-10）⑤去重用「來源日期」（每天固定只收集「當天」）＋`skill_growth_digests.(digest_date, source)`（收集去重，`UNIQUE` 約束）／`pushed_on`（推播去重）機制，不需要額外的內容雜湊表⑥`tech_intel` 功能開關（`owner_only=True`；**2026-08-07 同日再修正**：原規劃的 `skill_growth` 拆成 `tech_intel`／`certificate`／`language` 三個獨立開關，見 feature-toggles SPEC.md FR-3 追記，本功能只用其中的 `tech_intel`，因為 Robin 認為證照準備〔TOEIC〕跟技術情報訂閱性質不同、不該共用同一把開關）關閉時，收集與推播兩階段都會跳過，不消耗 Gemini API 額度⑦Gemini 呼叫用獨立的 `GEMINI_API_SKILL_GROWTH_KEY`（Robin 已於 2026-08-07 申請並設定到 `.env`／Render 部署環境）；**2026-08-09 修正（見 ADR-25）**：三個來源各自獨立呼叫 Gemini（一次收集最多 3 次 API 呼叫），`skill_growth_digests` 改為一天最多三筆、一筆一個來源，欄位新增 `source`（`tldr`／`ithome`／`techcrunch`），`summary_text` 只存單一來源的精簡總結，未來新增來源只需要多寫一個 `source` 值、不需要改 schema
- [x] FR-24：證照題庫（`certificate` 開關，2026-08-07 起獨立於技術情報 `tech_intel` 之外，見 feature-toggles SPEC.md FR-3 追記）：使用者設定目標（時間、目標分數），Robinson 可在使用者不知如何準備時提供方向建議。**2026-08-07（Step 3.2）確認範圍**：這條「目標設定＋方向建議」的對話式功能與 FR-26（自訂每日題數/彈性排程）性質相近，一併留到 Step 3.3 展開；Step 3.2 只完成 FR-25a～FR-25f 的題庫建立 Pipeline。**2026-08-07（Step 3.3 設計定案，見 ADR-19）**：目標（考試時間、目標分數）依 `exam_type` 各自設定一筆，重新設定即覆蓋舊值；方向建議由 Robinson 依使用者近期 FR-29 統計出的成效（對錯趨勢、常出錯的 `question_type`）與距離目標時間長短，用 LLM 生成客製化建議文字，不走固定範本。**2026-08-08 實作完成**：新增 `src/bot/certificate_goals.py`（`get_goal()`／`set_goal()`〔UPSERT，寫入 `certificate_goals` 表，0041 migration 已存在〕／`list_goals()`／`build_advice_prompt()`）；`commands.py` 新增「設定證照目標」／`/set_certificate_goal`（選 exam_type → 目標考試時間，可回覆「跳過」→ 目標分數，可回覆「跳過」→ 覆蓋寫入並告知舊值）、「我的證照目標」／`/my_certificate_goals`（單次列表）、「給我讀書建議」／`/certificate_advice`（只有一個候選 exam_type 直接生成、多個則先反問；抓近 30 天 `certificate_stats.compute_daily_period_stats()` 成效＋目標，組 Prompt 交給 LLM 生成客製化建議文字，不走固定範本）；`router.py` 註冊三個觸發詞與四個新 `pending_*` 狀態分派
- [x] FR-25：TOEIC 為第一個題庫，每次出題預設 1 題聽力 + 2 題填空 + 3 題單字英翻中，採「雙軌混合架構」產生題目；未來可套用同模板擴充 AWS / GCP 等其他證照（**2026-08-07 完成，見 Step 3.2**）：
  - [x] FR-25a：軌道一（高準確度題庫）來源 — Robin 將題目照片（圖檔）與聽力音檔（MP3）上傳至 Google Drive 指定資料夾。**2026-08-07 確認實際檔名規則**：`toeic_{測驗場次代號}_write_{題號}.{ext}`（填空/單字題，僅圖片）、`toeic_{測驗場次代號}_listen_{題號}.{ext}`（聽力題，Robin 已切好的單題圖片/音檔）、`toeic_{測驗場次代號}_listen.mp3`（聽力題整包音檔，尚未切割）。**2026-08-07 同日追記（見 ADR-18 決策 4）**：檔名格式泛用化為 `{exam_type}_{測驗場次代號}_write/listen_{題號}.{ext}`，`exam_type` 開放任意字串（不限 toeic），供 GCP／AWS 等未來證照類型直接沿用同一套 Pipeline
  - [x] FR-25b：軌道一檔名比對規則 — 若為已分拆的音檔，系統直接比對圖檔與音檔的檔名規則（見 FR-25a 實際格式，檔名含 `toeic` 字樣供辨識歸類，見 ADR-13），比對成功即整合為一筆完整題目；若為整包大型 MP3，Robinson 呼叫 Groq Whisper API（`VOICE_API_KEY`，`transcribe_with_segments()`）取得逐句時間軸，依語句停頓自動切割為獨立小音檔（**2026-07-30 更新**：語音轉文字改採 Groq Whisper，取代先前「一律用 Gemini」的規劃，見 ADR-12；**2026-08-07 新增 ADR-18**：切割邏輯是尚未經真實錄音驗證的啟發式判斷，Robin 已知情並選擇這次一起做；**同日再追記**：檔名比對改用 FR-25a 泛用化後的 `exam_type` 前綴而非固定 `toeic` 關鍵字，Google Drive 掃描也改成列出整個資料夾所有檔案，不再用關鍵字過濾）
  - [x] FR-25c：軌道一圖文解析與入庫 — 使用 Gemini Vision 解析題目圖檔中的文字與選項，寫入 Neon DB `toeic_questions` 表（題目文字、選項、對應圖檔 URL、對應音檔 URL）；**依原文刻意不存正解**（題目照片本身未必附答案）。**2026-08-07 同日追記**：資料表重新命名為 `certificate_questions` 並新增 `exam_type` 欄位，Vision 解析 Prompt 也改為依 `exam_type` 動態組字（例如「這張『GCP』證照考試的題目照片」），詳見 ADR-18 決策 4、`src/schema/db_schema.md`。**2026-08-07（Step 3.3，見 ADR-19）追記**：「刻意不存正解」的決策部分推翻——Robin 改為把購買的測驗書正確解答／詳解也一併拍照上傳（檔名 `{exam_type}_{test_id}_write/listen_{題號}_ans.png`），Robinson 不再需要用 AI 推論正解，正解一律來自真實資料。比對與入庫機制見 FR-27
  - [x] FR-25d：軌道二（單字刷題庫）題目規格 — Gemini 即時生成多益最新核心單字英翻中選擇題，每題須包含：單字（Target Word）、題目（英翻中選答）、4 個繁體中文選項（1 個正確答案＋3 個具干擾性的錯誤選項）、英文實用例句（Example Sentence）、例句繁體中文翻譯
  - [x] FR-25e：軌道二儲存機制 — 生成後同步寫入 DB（`toeic_vocab_questions`）供後續測驗重複抽考，避免重複呼叫 API 造成 Token 浪費；每週生成題數由 `users.toeic_weekly_question_count` 決定（Robin 自訂，預設 21 題＝一天 3 題）
  - [x] FR-25f：排程與去重規則 — 兩軌道的檔案掃描/生成排程統一為每週日台灣時間 22:00（Robin 2026-08-07 指定，取代原「排程頻率未定案」狀態）。**2026-08-07 修正去重規則**：原規劃「檔名中的日期是否落在過去一週內」與 Robin 實際確認的檔名格式（無日期）對不上，改用 `toeic_questions.source_image_filename` 是否已存在資料庫判斷是否處理過（符合 NFR-11 ETL 去重原則，效果等價，更貼合實際檔名設計）；軌道二額外靠 `users.toeic_pipeline_last_run_on`（今天是否已執行過）避免 `/healthz` 同一小時內多次觸發重複生成
- [x] FR-26：使用者可自訂每日題數、各證照類型比例、或將當日題目挪到其他天（彈性排程）。**2026-08-07（Step 3.3 設計定案，見 ADR-19）**：每日固定台灣時間 08:00 推播（比照 `skill_growth_digests` 排程模式，借用 `/healthz` 頻率）；推播候選池只從「已補齊正解（`correct_answer` 非 NULL）」的題目抽選（見 FR-27），沒有正解的題目不會出現在每日推播，避免使用者作答完卻無法批改。**2026-08-08（見 ADR-20）**：非 TOEIC 證照只能調「每日出題數量」，TOEIC 額外可調「聽力/填空/單字」三軌比例；另有跟三軌比例不同維度的「新題/複習題」比例（預設 7:3，所有證照類型通用）；彈性排程支援「今天改到別天」「直接取消今天的」「某日期區間每日題數改為 N」「今天的平攤到鄰近幾天」四種語意，區間外日期不受影響。**2026-08-08 追加（見 ADR-20 決策 5④、6）**：「平攤」語意需要 Robinson 自行計算分攤到哪幾天、每天各加幾題（規則：從明天起連續每天 +1 題直到攤完，跳過已有覆蓋的日期），但算完不能直接寫入，必須先列出「幾月幾號各要多幾題」給 Robin 確認，Robin 同意才寫入，有調整意見則依建議重算後再次確認
- [x] FR-27：每題作答後提供正解與詳解，並記錄該題對錯，錯題可排入後續複習。**2026-08-07（Step 3.3 設計定案，見 ADR-19）**：正解不再由 AI 推論——Robin 拍攝購買的測驗書正確解答／詳解，檔名 `{exam_type}_{test_id}_write/listen_{題號}_ans.png` 上傳至 Google Drive 同一資料夾；每週日 22:00 排程掃描時先處理一般題目檔案建立題目列，再處理 `_ans` 檔案，用 `(exam_type, test_id, question_type, question_number)` 比對到既有題目後 `UPDATE` 補上 `correct_answer`／`explanation`，不新建題目列；因此正解與詳解在建題庫階段就已備妥，作答當下不必即時呼叫 Gemini。作答結果（對/錯、作答時間、對應題目、`exam_type`）寫入新增的作答紀錄表，供 FR-29 統計與錯題複習使用。**2026-08-08（見 ADR-20）**：作答只接受回覆選項字母 A/B/C/D，格式不符時需先請使用者重新輸入正確格式才能繼續批改；錯題複習池只放「最新一次作答結果是答錯」的題目，答對一次就從複習池移除，不做間隔重複演算法。**2026-08-08 實作完成**：新增 `src/bot/certificate_answer.py`（待作答清單查詢、題目呈現內容組裝、批改與寫入 `answer_logs.assignment_id`、20:00 提醒）與 `src/bot/certificate_schedule.py`（MOVE/CANCEL/RANGE/SPREAD 四種彈性排程語意純邏輯，含「平攤」提案計算），`commands.py`／`router.py` 新增「開始作答」（一次一題、答完才給下一題）與「調整出題排程」（自由描述 → LLM 分類語意 → SPREAD 額外進入提案確認迴圈）兩組對話流程，見 ADR-20 決策 3、5、6
- [x] FR-28：當日題目未完成，20:00 提醒是否要作答，23:00 前仍未做則視為跳過；使用者要求延期時 Robinson 需記住新的排程。**2026-08-08（見 ADR-20）**：23:00 視為跳過採靜默處理，不主動發送通知。**2026-08-08 實作完成**：20:00 提醒改用 `certificate_answer.check_and_push_answer_reminders()`（`users.certificate_answer_reminder_sent_on` 去重，比照既有排程模式），23:00 不做任何主動動作（沒有對應的排程函式）；23:00 之後仍可補答，直到隔天 08:00 新一批 assignment 產生才視為過期（見 FR-27 的「跨日晚補答」判斷邏輯）
- [x] FR-29：使用者可用自然語言詢問一段時間內的答對/答錯成效。**2026-08-07（Step 3.3 設計定案，見 ADR-19，取代原「圖表方式呈現」的規劃）**：查證後確認 Phase 2 記帳／體態管理模組從一開始就是文字摘要、沒有任何畫圖表模組；圖表視覺化統一交給 Phase 4 Mobile App（FR-64）。本條在 Telegram 端一律用文字簡述回覆，範例：「上週總共測驗 N1 題，答對 N2 題，平均每天答對 N3 題，你最常出錯的地方是……，最常答對的地方是……」；沒有作答的日子要列出來並從平均計算中排除；使用者沒說清楚 `exam_type` 或「正式測驗 vs 日常小考」時 Robinson 需反問，不可自行猜測；需支援跨時間區間比較（如「上週和上上週比較」），彈性解析使用者描述的日期範圍；錯題統計維度沿用既有的 `question_type`（write/listen）與 `exam_type`，不新增更細的主題標籤欄位。**2026-08-08 實作完成**：新增 `src/bot/certificate_stats.py`（`compute_daily_period_stats()`〔平均只除以有作答天數、列出未作答日期、依 `question_type` 統計最常錯/最常對〕、`compute_formal_period_scores()`、對應文字格式化函式、`known_exam_types()`）；`commands.py` 新增「查詢我的成效」／`/my_quiz_stats`，設計為「每輪把使用者已經講過的內容全部疊加起來重新丟給 LLM 解析」而非死板單欄位反問（`_QUIZ_STATS_PARSE_PROMPT` 依序判斷 exam_type／正式-小考／時間區間，缺哪個就對應反問 `NEED_EXAM_TYPE`／`NEED_SCOPE`／`NEED_PERIOD`，都清楚了才是 `CLEAR`；LLM 判斷出的 `exam_type` 若對不到既有資料清單，視為 `UNCLEAR` 安全網防呆）；支援 `COMPARE` 兩區間比較（`format_daily_period_comparison()`）
- [x] FR-30：保留欄位記錄實際應考日期與正式成績。**2026-08-07（Step 3.3 設計定案，見 ADR-19）**：正式成績與「每日小考作答紀錄」是不同概念——同一 `exam_type` 可能多次應考，各自有獨立的應考日期與分數，另建資料表記錄，不與每日小考的作答紀錄混用。**2026-08-08 實作完成**（經 AskUserQuestion 與 Robin 確認範圍，只做查詢列表、不含修改／刪除——正式成績是「考完就定案」的歷史紀錄，不像體重/記帳需要常態修正，先求簡單）：新增 `src/bot/certificate_exam_scores.py`（`record_score()`／`list_scores()`／`distinct_exam_types()`／`format_scores_summary()`，寫入 `exam_official_scores` 表，0042 migration 已存在）；`commands.py` 新增「我要記錄正式成績」／`/log_exam_score`（選 exam_type → 應考日期 → 成績自由文字，依序寫入）、「我的正式成績」／`/my_exam_scores`（單次列出所有紀錄，不分證照類型）；`router.py` 註冊兩個觸發詞與三個新 `pending_*` 狀態分派

### 功能性需求 — YouTube 技術情報模組（個人技能成長子功能，僅 Robin 可用；**2026-08-07 修正**：與每日技術分享〔FR-22／FR-23〕共用 `tech_intel` 開關，因為兩者同屬「技術情報訂閱」性質，見 feature-toggles SPEC.md FR-3 追記；獨立於「證照準備」`certificate`、「語言學習」`language` 兩個開關之外）

- [x] FR-57：輕量化資料獲取（**2026-08-08 修正，見 ADR-21**）— 依每組主題設定的關鍵字，各自呼叫 `YouTube Data API v3` 的 `search.list`（`order=relevance` 相關度優先）取得前 10 筆候選資料，擷取 `title`／`description`／`channelTitle`／`publishedAt`／`videoId`／`url`；候選名單確定後，另呼叫 `videos.list`（`part=statistics`，可批次查多支影片）補上 `viewCount`／`likeCount`／`commentCount`，供 FR-58b 判讀熱度與品質；全程只讀取文字與統計數字，不下載或轉錄影音本身，避免龐大運算與 Token 成本。**2026-08-08 實作完成**：新增 `submodules/youtube`（`YouTubeClient`，API Key 認證，`search_videos()`／`get_video_details()`，重試邏輯沿用 `submodules/retry`）
  - [x] FR-57a（**2026-08-08 新增，見 ADR-21**）：多主題設定 — Robin 可設定多組關鍵字/主題（例如「後端架構」「AI Agent」「DevOps」），每組各自獨立執行 FR-57 的候選蒐集；主題清單存資料庫，設定後每週自動沿用，增減主題需另用指令調整。**2026-08-08 實作完成**：新增 `youtube_topics` 表（0049 migration）；`src/bot/youtube.py` 的 `list_topics()`／`add_topic()`／`remove_topic()`／`format_topics_list()`；`commands.py`／`router.py` 新增「我的YouTube主題」／`/my_youtube_topics`（單次列表）、「新增YouTube主題」／`/add_youtube_topic`（單輪輸入）、「移除YouTube主題」／`/remove_youtube_topic`（列清單 → 輸入編號直接刪除，屬低風險可重新新增的操作，不需要待辦事項刪除那種二次確認）三個 Owner 專屬指令
- [x] FR-58：Top 3 推薦篩選邏輯（**2026-08-08 改版，見 ADR-21，取代原「三層輕量規則式篩選」設計**）：
  - [x] FR-58a（**2026-08-08 修正，見 ADR-21**）：格式過濾 — 只排除候選清單中重複出現的來源（同一支影片重複入選時去重）；**不特別排除 Shorts 短影音，時長不設限**，品質高低完全交給 FR-58b 的 LLM 判讀（含觀看數/讚數/留言數等數據）決定，不用時長門檻一刀切。**2026-08-08 實作完成**：`youtube._dedupe_by_video_id()`
  - [x] FR-58b（**2026-08-08 改版，見 ADR-21，取代原「Rule-based Weight」設計**）：LLM 語意判讀 — 把候選的標題、說明欄、頻道名稱、發布時間、觀看次數、讚數、留言數交給 LLM，綜合判斷「是否符合設定的主題」與「這些數據代表的熱度/品質」給出排序，只讀文字與統計數字、不下載影片本身，成本維持低廉；不對發布時間設定強制過濾門檻，避免剔除具高技術含量的經典影片。**2026-08-08 實作完成**：`youtube._build_ranking_prompt()`／`_parse_scores()`／`score_candidates_for_topic()`；LLM 輸出格式解析失敗時優雅降級為依觀看數排序（`score` 標記為 `None`），不讓 Pipeline 卡住
  - [x] FR-58c（**2026-08-08 新增，見 ADR-21**）：多主題分配與輪替公平性 — 每週固定推薦 3 支影片：只有 1 組主題時，從該組挑出 LLM 判斷分數最高的 3 支；有 2 組主題時，各保底 1 支，剩餘 1 個名額給兩組候選中分數最高者；有 3 組以上主題時，優先選「距離上次被推播最久」的 3 組各推 1 支，確保每個主題長期下來都有曝光機會，不會有主題永遠被排擠。**2026-08-08 實作完成**：`youtube.select_weekly_recommendations()`（`_topics_by_priority()` 依 `last_recommended_on` 由舊到新排序、`NULL` 最優先；單一通用「保底 + 補滿」演算法同時滿足三種情境，見模組 docstring）；同一支影片同時符合多組主題搜尋結果時，保底輪與補滿輪皆會跳過已保底/已選中的 `video_id`，避免重複計入
  - [x] FR-58d（原 FR-58c）：歷史比對與精準輸出 — 過濾過去 30 天內已推播之 `video_id`（符合 NFR-11 ETL 去重原則），最終於 Telegram 以 Markdown 超連結（`[影片標題](url)`）呈現。**2026-08-08 實作完成**：新增 `youtube_pushed_videos` 表（0050 migration）；`youtube._filter_recently_pushed()`（30 天窗口）／`format_push_message()`（Markdown 超連結）
- [x] FR-59：每週自動排程與配額控管：
  - [x] FR-59a：排程模組預設每週執行一次（每週四自動推播）。**2026-08-08 實作完成**：`youtube.check_and_push_weekly_youtube()` 固定台灣時間週四 08:00，借用 `/healthz` 既有頻率；`users.youtube_last_run_on`（0051 migration）去重，比照既有排程模式
  - [x] FR-59b（**2026-08-08 更新配額估算，見 ADR-21**）：配額成本 — 每組主題各消耗一次 `search.list`（100 Units／次）；`videos.list` 查統計資料成本低（每 50 支影片 1 Unit）。多組主題情境下（例如 5 組）單次執行約落在 500～600 Units，仍遠低於每日 1,000 Units 上限（自訂保守門檻）與 YouTube 官方每日 10,000 Units 免費額度——**配額為 Google 提供的免費每日用量上限，非計費機制，用不完不會扣款，超過上限當天暫停查詢、隔天重置**。**2026-08-08 實作範圍說明**：本次先實作排程與推播主流程，尚未實作主動累計每日配額用量的計數器（目前每週僅執行一次、單次估算遠低於門檻，風險低）；若之後主題數大幅增加導致接近門檻，需回頭補上配額計數與 FR-59c 的主動降級判斷
  - [x] FR-59c：Fallback 降級機制 — 若超出每日配額上限或連線異常，依 FR-19i（重試機制）與 FR-19f（一般感冒級分級降級）處理：記錄 Exception 於日誌，並回傳友善提示，確保系統不崩潰。**2026-08-08 實作完成**：`submodules/youtube` 的 API 呼叫沿用 `submodules/retry`（HTTP 429/5xx、連線逾時自動重試）；`youtube.check_and_push_weekly_youtube()` 整段包 try/except，任何 Exception 只記錄日誌、不中斷 `/healthz`，且仍會標記 `youtube_last_run_on` 避免同一天重複嘗試

### 功能性需求 — 待辦事項

- [x] FR-31：使用者以自然語言描述「什麼時候要做什麼事」，Robinson 解析後記錄；若使用者描述內容可能與其他功能模組重疊（例如「打籃球」既像待辦事項也像體態管理的運動紀錄），Robinson 需先反問使用者要記到哪個模組，不可自行猜測（**2026-08-02 Step 1.7 實作**：跨模組歧義判斷 Phase 1 暫不實作——體態管理要 Phase 2 才做、心情小記 Step 1.8 也還沒做，目前沒有其他已完成的模組可以比較，待那些模組做出來後再回頭補上；自然語言偵測比照 FR-11「主動新增知識」的 LLM 標記模式，見 `src/bot/chat.py` 的 `_REQUEST_TODO_MARKER`）
- [x] FR-31a：待辦事項狀態管理 —— 該筆待辦已超過預定執行時間、或使用者明確表示已完成／取消時，需將該筆標記為已結束狀態，不再出現在待處理清單或後續推播中（**2026-08-02 實作**：逾期由 `src/bot/todo.py` 的 `mark_overdue_as_expired()` 借用 `/healthz` 排程檢查自動標記為 `expired`；完成/取消由「我的待辦事項」查詢清單後選定編號、LLM 判斷使用者意思後標記為 `completed`／`cancelled`）
- [x] FR-32：推播時機：使用者主動查詢時、每日 08:00 固定推播、預計處理時間前 30 分鐘提醒（提醒與否由使用者於記錄當下決定，見 FR-56e 情境範例）（**2026-08-02 實作**：主動查詢＝「我的待辦事項」／`/my_todos`；每日 08:00 固定推播與前 30 分鐘提醒兩者都沒有獨立排程系統，借用 `/healthz` 既有的 10 分鐘 cron 頻率，去重狀態存在 `todos` 資料列本身（`reminded_30min_sent_at`／`daily_pushed_on`），見 `src/schema/db_schema.md` todos 表設計理由）
- [x] FR-31b：待辦事項除了單一時間點，也要能記錄一段時間區間（例如「2026-08-02 08:00 ～ 2026-08-05 17:00」的出差、旅行等跨天/跨時段任務）（**2026-08-02 實作**，Robin 詢問「待辦事項是不是只能存單一時間點」後新增，經 AskUserQuestion 確認三個設計決策：① `todos` 新增可選的 `start_at` 欄位而非把 `due_at` 整個改成必填的 start/end 兩欄，既有單一時間點待辦完全不受影響（`0016_add_start_at_to_todos.sql`，Robin 依 ADR-10 核准）② 前 30 分鐘提醒對區間待辦以 `start_at`（開始時間）為基準（提醒「準備要開始了」），單一時間點待辦仍以 `due_at` 為基準 ③ 每日 08:00 摘要對區間待辦只在「開始那天」與「結束那天」各出現一次，去重判斷從「曾經推播過就不再推播」改為「今天是否已經推播過」（`daily_pushed_on IS NULL OR daily_pushed_on != 今天`），讓同一筆待辦能在開始日、結束日分別各推播一次。`commands._TODO_TIME_PARSE_PROMPT` 新增選填的 `START_AT` 欄位，只有原始描述或回覆同時講出明確的開始與結束時間才判斷為區間，且開始/結束兩個時間點都要分別滿足「日期明確」「時段不歧義」才算 CLEAR；確認訊息與「我的待辦事項」清單都會依是否為區間顯示「開始 ～ 結束」或單一時間）

### 功能性需求 — 求職（**2026-08-08 決議僅 Robin 可用，見 ADR-24**）

- [x] FR-33（**2026-08-08 修正，見 ADR-24 決策 3；2026-08-09 實作；2026-08-09 依 Robin 實測回饋移除產業別維度**）：使用者可同時設定多組查詢條件（各組各自包含關鍵字、地區、薪資範圍），不限單組覆蓋；每組條件各自獨立生效，每週排程各自送出查詢。產業篩選已移除（實測後確認 104 API 該參數名稱不值得繼續猜測，`job_search_criteria.industry` 欄位保留但不再收集/使用）；地區篩選改為爬蟲階段對回傳結果做子字串比對（見 FR-34a 註記），不送給 104 API
- [x] FR-34（**2026-08-09 實作，見 `submodules/job104/client.py`／`src/bot/job_search.py`**）：定期爬取 104 最新更新職缺，並深入爬取職缺內容、應徵條件、福利：
  - [x] FR-34a（**2026-08-08 補充，見 ADR-24 決策 4；2026-08-09 實作；2026-08-09 由 Robin 透過瀏覽器 DevTools 手動實測驗證，欄位對應已修正見 `submodules/job104/client.py` 模組 docstring「驗證狀態」段落**）：抓取機制 — 不使用瀏覽器自動化工具（Playwright/Selenium）、無需登入態，直接分析並呼叫 104 前端 AJAX/JSON API（列表 `https://www.104.com.tw/jobs/search/api/jobs`、詳情 `https://www.104.com.tw/api/jobs/{短代碼}`，皆已實測確認）解析資料，輕量且高執行效能。**採兩階段架構**：先呼叫列表 API 依 FR-33 各組條件取得職缺摘要清單，再對清單內每一筆職缺個別呼叫詳情頁補齊完整職缺內容／應徵條件／福利；實測確認應徵人數（`applicant_count`）其實列表 API 就有，已改為列表階段直接取得，僅職缺內容/福利/年資要求仍需詳情頁補齊，兩階段架構維持不變。地區篩選（`area`）參數名稱經 Robin 補充實測確認正確，但值是 104 自己的地區數字代碼（例如 `"6001008000"`），不是使用者輸入的地區文字，沒有可靠對照表，故 `search_list()` 不送這個參數，改由爬蟲階段對回傳結果的地區文字做子字串比對篩選；產業篩選依 Robin 指示直接移除，不再是這個模組的功能範圍
  - [x] FR-34b（**2026-08-09 實作**：`check_and_run_weekly_job_search()` 固定台灣時間週一 08:00 執行）：執行頻率 — 每週僅執行一次（固定時間排程），不對 104 伺服器造成流量負擔（修正原「每日爬取」的規劃）
  - [x] FR-34c（**2026-08-08 補充；2026-08-09 實作**：`_polite_delay()`）：反爬蟲友善機制 — Header 帶入標準 Browser User-Agent 與 Referer；列表分頁請求之間、以及 FR-34a 每一筆詳情頁請求之間，皆強制加入 2～4 秒隨機延遲，嚴禁併發多執行緒請求
  - [x] FR-34d（**2026-08-09 實作**：`upsert_job_posting()`；**2026-08-09 追加 `is_closed` 自動判斷，見 migration `0057`**）：ETL 去重 — 以 104 職缺唯一 ID（或職缺 URL）作為去重鍵值，已存在資料庫的職缺應更新既有紀錄（如薪資/職缺狀態變動）而非重複新增，避免每週爬蟲造成資料庫重複資料膨脹（符合 NFR-11 ETL 去重原則）。職缺是否已關閉（`job_postings.is_closed`）依 104 API 的 `jobSwitch`／`switch` 欄位自動判斷（`"on"` 代表開放中），每次重新爬到既有職缺時同步更新，解決 ADR-26 決策 5 原本懸而未決的問題，FR-38b 的 Excel「是否關閉」欄位因此不會出現
- [x] FR-35（**2026-08-08 全面改寫，見 ADR-24 決策 1，取代原「Gemini Web Search 補充公司背景」設計；2026-08-09 實作**）：職缺公司背景資訊改採「Email 協作」機制，不使用 Gemini Web Search（該能力已因 grounding 失效被移除，見 chat-core SPEC.md ADR-5）：
  - [x] FR-35a（**2026-08-09 實作**：`crawl_and_upsert_jobs()` 的 `new_company_ids`／`check_and_run_weekly_job_search()`）：每週排程爬完職缺後（FR-34），比對這批職缺所屬公司清單，找出資料庫裡尚未有背景資料的新公司（以 104 公司 ID 判斷是否已存在）；若這批公司全部都已有背景資料，FR-35b～FR-35e 整段流程完全跳過，不寄信也不通知
  - [x] FR-35b（**2026-08-09 實作**：`submodules/email` 新增 `send_text_with_attachment()`，`build_new_companies_csv()`／`send_new_companies_email()`）：有新公司時，先把新公司寫入資料庫（`background` 留空），組一份 CSV（欄位：104公司ID、公司全名、地區、產業類型、背景〔空〕），命名為 `{YYYY-MM-DD}-104職缺公司.csv`，透過 Email 寄給 Robin（沿用 `submodules/email`／`GMAIL_USER` 自寄自收），標題「{YYYY-MM-DD} 排程 - Robinson 104 職缺公司列表」，內容「附件為本週爬到的最新公司列表，請參閱！」
  - [x] FR-35c（**2026-08-09 實作**）：寄信成功後，私訊 Robin Telegram：「已經寄送本週最新的104職缺公司信件給您了～」（FR-19h 決策執行狀態閉環回饋）
  - [ ] FR-35d：Robin 自行上網查詢並填好 CSV 的「背景」欄位，上傳到既有共用 Google Drive 資料夾（沿用 `GDRIVE_FOLDER_ID`，比照 TOEIC 模組同一資料夾、靠檔名慣例區分），檔名不變（Robin 手動操作步驟，無程式碼實作項目，等正式部署後第一次真實排程跑完才會實際發生）
  - [x] FR-35e（**2026-08-09 實作**：`router.py` `_UPLOADED_FILE_PATTERN`／`commands.handle_company_csv_uploaded()`）：Robin 上傳後在 Telegram 說「已上傳{YYYY-MM-DD}-104職缺公司.csv」，Robinson 偵測到此訊息格式後，至 Drive 資料夾以檔名找到該檔案、下載、解析 CSV，把「背景」欄位逐筆 UPDATE 回資料庫對應公司（以 104 公司 ID 比對），完成後回覆處理結果（成功筆數；找不到對應公司的列出來提醒人工處理，不可靜默略過）
- [x] FR-36（**2026-08-09 修正，見 ADR-26 決策 1**：歸屬 Step 4.1，與 FR-33 同一輪對話流程收集，不歸屬 Step 4.2；**2026-08-09 實作**）：記錄使用者 3500 字內個人履歷與未來期望工作內容；**新增兩個結構化欄位輔助 FR-37 契合度評分**：①年資（`years_of_experience`，浮點數，例如 3.5 年，Robin 直接填數字）②期望薪資下限／上限（`expected_salary_min`／`expected_salary_max`，數字），從原本混在自由文字裡的「期望工作敘述」拆出來，不用再靠 LLM 從自由文字猜測
- [x] FR-37（**2026-08-09 全面修正，見 Step 4.2、ADR-26 決策 2～4；2026-08-09 實作**：`src/bot/job_search.py` `list_scorable_jobs()`／`score_jobs()`／`apply_scores()`）：Gemini 批次（非逐筆）交叉比對使用者履歷／期望工作內容（含 FR-36 結構化年資、期望薪資）與職缺內容，計算 0～100 契合度分數：
  - [x] FR-37a：**評分範圍限定**——僅計算「所屬公司背景資料已回填完成」（見 FR-35）的職缺；背景仍空白的職缺本次評分跳過，待未來背景補齊後於下次排程自然被納入，不因此卡住整批評分或整個排程
  - [x] FR-37b：比對維度——職缺內容、年資（比對使用者 `years_of_experience` 與職缺要求年資）、期望薪資（比對 `expected_salary_min`／`expected_salary_max` 與職缺薪資範圍）為必要維度；**（2026-08-09 更新）**「應徵人數」（`applicant_count`）「更新時間」（`source_updated_at`）兩項經 Step 4.1 實測確認 104 API 皆可取得，一併納入比對維度；個別職缺若這兩欄剛好是 `NULL`（理論上少數情況），評分時該筆職缺略過對應維度，不強行湊資料。**已知限制**：`salary_min`／`salary_max` 目前尚未解析寫入（見 FR-34d），所有職缺這兩欄恆為 `NULL`，Prompt 會標示「未提供」讓 LLM 略過薪資比對，待未來補上薪資解析邏輯後自然生效，不影響本次評分流程
  - [x] FR-37c：呼叫方式——比照 YouTube 模組（FR-58b）的做法，把符合 FR-37a 範圍的職缺整批（而非逐筆）交給 Gemini 一次性算出各筆分數與推薦原因文字，節省 API 呼叫次數（NFR-1 免費額度限制）；職缺數量過多超出單次 Prompt 負荷時分批送出（`_SCORING_BATCH_SIZE = 15`）
  - [x] FR-37d：執行時機——比照 FR-34b 頻率，固定每週排程執行一次（緊接在該週爬蟲與公司背景流程之後），不因為「這週沒有新公司背景可用」而跳過整次評分——只要資料庫裡已有背景資料的職缺，都會被重新納入這次評分範圍（`check_and_run_weekly_job_search()` 內 `_run_weekly_scoring_and_recommendation()`）
- [x] FR-38（**2026-08-09 全面修正，見 Step 4.2、ADR-26 決策 1、5、6；2026-08-09 實作**）：契合度評分完成後，以「104 職缺 ID」為單位（非以公司為單位，避免同公司多個職缺的技能需求混在一起分不清楚）整理技能缺口，逐筆說明使用者履歷／技能與該職缺要求的落差：
  - [x] FR-38a：**「前 30 名」雙重排名機制**——① 全庫排名：資料庫所有已評分職缺（排除 `is_unliked = TRUE`、`is_closed = TRUE`）依分數由高到低取前 30 名 ② 本週新職缺排名：僅本次排程新爬到的職缺（依首次入庫時間判斷）依分數取前 30 名；兩種排名各自獨立計算（`build_ranked_jobs()`，`rank` 動態計算不持久化，見 migration `0058` 設計理由）
  - [x] FR-38b：**交付機制**——每週排程完成 FR-37 評分與技能缺口分析後，整理成 Excel 檔（檔名 `{YYYY-MM-DD}-104職缺推薦.xlsx`），含三張工作表：工作表 1「所有職缺推薦」（FR-38a 全庫排名前 30 名，欄位：104公司ID／公司全名／地區／產業類型／職缺／評分／排名／推薦原因／連結／是否喜歡；**不含「是否關閉」**）、工作表 2「最新職缺推薦」（FR-38a 本週新職缺排名前 30 名，欄位同工作表 1）、工作表 3「技能缺口」（欄位：104職缺ID／說明，對應工作表 1／2 出現過的職缺）。**（2026-08-09 更新）**「是否關閉」已確認可自動判斷（`job_postings.is_closed`，見 FR-34d、migration `0057`），Excel 不會出現這欄，原訂的人工備案不需要。透過 Email 寄給 Robin（沿用 `GMAIL_USER` 自寄自收，比照 FR-35b），標題「{YYYY-MM-DD} 排程 - Robinson 104 職缺推薦」，內容「附件為本週整理的職缺推薦列表，以及技能缺口分析，請參閱！」（`build_job_recommendation_excel()`／`send_job_recommendation_email()`，用 `openpyxl` 產生，見 `requirements.txt`）
  - [x] FR-38c：寄信成功後私訊 Robin：「已寄送本週 104 職缺推薦檔案給您～」（FR-19h 決策執行狀態閉環回饋，比照 FR-35c；`RECOMMENDATION_EMAIL_SENT_NOTIFICATION_TEXT`）
  - [x] FR-38d：Robin 於 Excel 中標記「是否喜歡」（不喜歡填 1，喜歡維持空白＝`is_unliked = FALSE`）後，上傳到既有共用 Google Drive 資料夾（沿用 `GDRIVE_FOLDER_ID`），檔名不變
  - [x] FR-38e：Robin 上傳後於 Telegram 說「已上傳{YYYY-MM-DD}-104職缺推薦.xlsx」，Robinson 依檔名關鍵字（`.xlsx`／「職缺推薦」）與 FR-35e 的公司背景 CSV（`.csv`／「職缺公司」）區分為兩條**各自獨立**的回填流程，偵測到後至 Drive 下載解析，以「連結」（職缺 URL，天然唯一，不需要額外的比對欄位）為比對鍵值，把「是否喜歡」→ `is_unliked` 逐筆 `UPDATE` 回資料庫對應職缺；完成後回覆處理結果（成功筆數；比對不到對應職缺的列出來提醒人工處理，不可靜默略過，比照 FR-35e）。**實作**：`router.py` `_UPLOADED_FILE_PATTERN` 擴充 `104職缺推薦.xlsx` 分支、`commands.handle_job_recommendation_excel_uploaded()`、`job_search.parse_recommendation_excel()`／`apply_job_preferences()`
  - [ ] FR-38f：應徵成效追蹤——Robin 已預告未來會用「ID=XXX 職缺已應徵」／「ID=XXX 職缺已獲得面試」／「ID=XXX 職缺已拿到 Offer」這類 Telegram 訊息記錄狀態；本條屬於 FR-39（Step 4.3）範圍，本次僅記錄需求，細部設計（資料表欄位、狀態機、觸發語句 regex）留待 Step 4.3 開工時展開
- [x] FR-39（**2026-08-09 規格定案，見 Step 4.3、ADR-27；2026-08-09 實作**）：記錄應徵成效（投遞 / 面試邀約 / 實際面試 / Offer），以 Telegram 文字訊息「ID=XXX 職缺已應徵」等語句觸發：
  - [x] FR-39a：**職缺 ID 來源**——FR-38b 的「所有職缺推薦」「最新職缺推薦」兩張工作表新增「104職缺ID」欄位（原本只有「技能缺口」工作表有），Robin 直接從推薦 Excel 抄 ID 打語句，不需要另外查
  - [x] FR-39b：**狀態機**——任何狀態都能直接設定，不強制依「已應徵→已獲得面試→已拿到 Offer」順序推進（例如公司沒發正式面試邀約就直接約時間面試，可以跳過中間狀態直接設定）；除 Robin 預告的三種狀態外，新增第四種結束狀態「未錄取／已婉拒」，供之後統計整體應徵成效（例如應徵 20 家、幾家有面試、幾家沒下文）。**實作**：`router.py` `_APPLICATION_STATUS_PATTERN`（`ID=<ID> 職缺已應徵／已獲得面試／已拿到 Offer／已婉拒／未錄取`）直接解析，不走多輪對話狀態機
  - [x] FR-39c：**歷程記錄**——應徵狀態存成獨立歷程表（非直接覆蓋 `job_postings` 單一欄位），每次狀態變更新增一筆紀錄＋時間戳，保留完整歷程（例如「哪天投遞、哪天收到面試邀約、哪天拿到 Offer」都查得到），供未來統計「平均從投遞到收到回覆幾天」之類的成效指標。**實作**：`job_applications` 表（migration `0060`）、`job_search.record_application_status()`
  - [x] FR-39d（**2026-08-09 開工時追加**）：**查詢指令**——「我的應徵紀錄」／`/my_applications`，列出各職缺目前最新的應徵狀態（依最新更新時間排序），比照 FR-30 正式成績「只查詢不修改」的簡化做法。**實作**：`job_search.list_latest_application_statuses()`／`format_application_statuses()`、`commands.handle_my_applications()`
- [x] FR-40（**2026-08-09 規格定案，見 Step 4.3、ADR-27；2026-08-09 實作**）：LinkedIn、Cake 等其他管道的職缺以 Telegram 文字訊息方式手動記錄進資料庫，並納入 FR-37 契合度評分考量：
  - [x] FR-40a：**資料結構**——外部管道職缺與 104 職缺共用同一張 `job_postings`／`job_companies`，新增 `source` 欄位區分來源（`104`／`linkedin`／`cake`…，預設 `104`），取代「另建獨立表」的設計，之後要加其他求職平台不需要再開新表（**2026-08-09 修正，見 ADR-27 決策 5**：Claude 原提案外部職缺用獨立表儲存，Robin 指出應統一用 `source` 欄位以利擴充性，Claude 採納並確認統一表可直接沿用既有評分/排名邏輯）；沒有 104 官方 ID 時由系統配發合成識別碼（例如 `EXT-3`）寫入既有 `job_id_104`／`company_id_104` 欄位，職缺內容與公司背景由 Robin 新增時手動填入既有欄位。**實作**：migration `0059`（`source` 欄位）、`job_search.add_external_job()`、`commands.start_add_external_job()` 六輪對話流程（管道→職稱→公司名→連結→內容→公司背景）、「新增外部職缺」／`/add_external_job` 觸發詞
  - [x] FR-40b：**評分**——外部管道職缺直接沿用 FR-37／FR-38a 既有的批次評分與每週排名流程（不需要獨立的評分批次），會跟 104 職缺一起出現在同一份每週推薦 Excel 前 30 名裡（**2026-08-09 確認，見 ADR-27 決策 6**：Robin 選擇「混在一起排」，不特別區分來源）；需要 Robin 在新增職缺時一併提供職缺內容與公司背景（沒有 104 API 可以自動抓，無法沿用 FR-35 的 Email 協作機制）
  - [x] FR-40c：**ID 命名空間**——外部管道職缺沒有 104 職缺 ID，Robin 新增後 Robinson 會回覆分配到的合成識別碼（寫入 `job_postings.job_id_104`），供之後應徵狀態追蹤（FR-39）與觸發語句使用，跟 104 職缺走同一個查詢路徑，不需要分開處理兩種命名空間

### 功能性需求 — 記帳

- [x] FR-41：使用者設定理財目標（如每月存款金額）（**2026-08-04 Step 2.1 實作**：經 AskUserQuestion 確認解讀為「每月支出預算上限」，非「每月儲蓄目標」——不需要算「收入-支出」結餘去比對，直接比較「本月支出總額」與「預算上限」；「設定記帳預算」／`/set_budget` 觸發，寫入 `users.monthly_budget`）
- [x] FR-42：每日記帳（含補登與修正）（**2026-08-04 實作**：從一開始就內建完整 CRUD，不像心情小記是事後才補上——「我要記帳」／`/add_transaction` 一般新增、「我要補記帳」／`/backfill_transaction` 補記過去日期、「我的記帳紀錄」／`/my_transactions` 查詢並可更新/刪除；交易分類固定清單（比照心情小記），支出/收入兩種交易類型都做；備註套用 FR-13 個資遮蔽；刪除採簡單一輪 LLM CONFIRM/CANCEL，不套用 FR-16a，理由同心情小記的補記/更新/刪除擴充）
- [x] FR-43：預警通知：月中前已花超過目標 50%、月底前已超過 80% 等門檻告警（**2026-08-04 實作**：經 AskUserQuestion 確認觸發時機——50% 門檻只在每月 15 日（含）以前檢查，代表早期警示；80% 門檻整月都檢查，代表不管月初月底只要花超過就提醒；兩個門檻各自每月最多推播一次，去重狀態存在 `users.budget_alert_50_sent_month`／`budget_alert_80_sent_month`；比照 FR-32 待辦推播，借用 `main.py` `/healthz` 既有的 10 分鐘 cron 頻率，見 `finance.check_and_push_budget_alerts()`）
- [x] FR-44：定期視覺化支出/儲蓄趨勢（**2026-08-04 實作**：Phase 1 這版先做「使用者主動查詢時的文字摘要」——「我的記帳摘要」／`/my_finance_summary`，內容包含本月支出/收入總計、預算使用率、支出分類佔比、跟上個月比較；不做圖表圖片，主動排程推播月報部分見下方 FR-44a，文字摘要本身留待有實際使用需求後再考慮升級成圖表）
- [x] FR-44a：月底自動推播月報（**2026-08-04 實作**，Robin 要求「記帳摘要請在每月底自動推一次月報」後新增，經 AskUserQuestion 確認兩個設計決策：① 推播時刻為台灣時間 21:00，刻意跟 FR-42a 每日提醒的 23:00 錯開 ② 只推給「這個月有生效預算（全局預設或當月覆蓋皆算）或這個月有任一筆記帳交易」的使用者，避免完全沒用記帳功能的家人收到一則全部是 0 元的空洞報告；`finance.check_and_push_monthly_report()` 比照其他推播機制借用 `/healthz` 頻率，內容沿用 FR-44 的 `format_monthly_summary()`，「是不是月底最後一天」用「明天日期是不是 1 號」判斷、不寫死 28～31；去重欄位 `users.finance_monthly_report_sent_month`（`0022_add_finance_monthly_report_field_to_users.sql`，Robin 依 ADR-10 核准），比照 FR-43 的門檻預警去重設計）
- [x] FR-41a：預算特殊月份覆蓋（**2026-08-04 實作**，Robin 提出記帳模組使用回饋後新增，經 AskUserQuestion 確認三個設計決策：① 預算跟月份的關聯採「全局預設值＋特殊月份覆蓋」設計而非逐月各自設定——`users.monthly_budget` 保留當全局預設，新增 `budget_overrides` 表（`0020_create_budget_overrides_table.sql`，Robin 依 ADR-10 核准）只存跟預設值不同的特殊月份，查詢當月「實際生效」預算時優先用覆蓋值、沒有才 fallback 用全局預設（`finance.get_effective_monthly_budget()`），好處是改全局預設不會動到已設定過的特殊月份 ② 每次呼叫「設定記帳預算」都先反問套用範圍（全部月份／只套用某幾個月），而不是直接問金額 ③ 要覆蓋的範圍已有舊值時（無論是全局預設或某個月的覆蓋值），一律先反問「你已經設定...確認要改嗎？」才能真正寫入，簡單一輪 LLM CONFIRM/CANCEL；FR-43 門檻預警、FR-44 摘要都已改用生效預算查詢邏輯；月份輸入一律套用「今年」，尚不支援跨年設定，是本次的簡化假設）
- [x] FR-42a：每日記帳提醒（**2026-08-04 實作**，Robin 提出「有設定支出目標時應每天固定時間提醒記帳，但當天已記錄就不必提醒，收入不用檢查」的回饋，經 AskUserQuestion 確認推播時刻為台灣時間 23:00：`finance.check_and_push_finance_reminders()` 借用 `/healthz` 既有 10 分鐘 cron 頻率，只在 23 點這個小時內執行；對「這個月有生效預算（全局預設或當月覆蓋皆算）」且「今天完全沒有支出紀錄」且「今天還沒推播過」的使用者推播一次，去重欄位 `users.finance_reminder_sent_date`（`0021_add_finance_reminder_field_to_users.sql`，Robin 依 ADR-10 核准）比照 `todos.daily_pushed_on`；收入不檢查，理由是記帳預算本來就只針對支出設門檻，收入沒有「每天都要記」的急迫性）

### 功能性需求 — 體態管理

- [x] FR-45：視覺化與預警通知（沿用記帳模組的告警機制）（**2026-08-04 完成**：三種預警情境——目標達成通知（體重目標每次記錄即時檢查、運動目標借用 `/healthz` 頻率排程加總累積分鐘數）、目標期限前 7 天提醒、BMI 異常提醒（記錄體重當下就地附加，不用排程），詳見 `src/bot/body.py`）
- [x] FR-46：身體數據：目標設定、身高（初始設定，變動才修正）、體重（有量才記）、自動計算 BMI 並附標準說明；記錄前需做合理範圍檢查（成人身高約 140～220 公分、體重約 40 公斤以上），數字或單位明顯不合理時需向使用者確認，不直接寫入（**2026-08-04 完成**：`/set_height`、`/log_weight`／`/backfill_weight`／`/my_weight_logs` 從一開始就內建補記/更新/刪除，超出合理範圍原地反問重新輸入，不直接寫入）。**2026-08-08 擴充**：新增腰圍（初始設定，變動才修正，設計與身高完全對稱，不像體重需要每天/每次的歷史紀錄）。腰圍刻意定位為「參考指標，非必要」——BMI 計算不使用腰圍，缺少腰圍不影響任何既有功能。兩種觸發方式：① 獨立指令「設定腰圍」／`/set_waist`，隨時可主動設定/更新 ② 記錄體重（`/log_weight` 新增一筆，不含 `/my_weight_logs` 觸發的更新流程）後，若使用者從未設定過腰圍，Robinson 會順便問一次「要不要也記錄一下腰圍呢？」；問過一次之後除非使用者自己再更新，不會每次記體重都重複問，避免每天打擾。回覆時直接輸入公分數字即完成記錄，任何無法解析成數字的回覆（含「跳過」「不用」等）一律視為跳過、不強迫明確拒絕；合理範圍 40～200 公分（比身高體重寬鬆，畢竟只是參考用途）
- [x] FR-47：運動：目標設定、運動習慣紀錄（項目、時長、心率選填）、自動估算當日消耗卡路里（**2026-08-04 完成**：`/log_exercise`／`/backfill_exercise`／`/my_exercise_logs`，卡路里改用 LLM 估算而非 MET 公式，經 AskUserQuestion 與 Robin 確認，估算失敗不擋下紀錄）
- [x] FR-48：飲食：目標設定、飲食與飲水紀錄、自動拆算每餐蛋白質/碳水/脂肪/卡路里（**2026-08-04 完成**：`/log_diet`／`/backfill_diet`／`/my_diet_logs`，飲食與飲水同一張表用 `entry_type` 區分；三大營養素拆算沿用 `GEMINI_API_BOT_KEY`，經 AskUserQuestion 與 Robin 確認；務必附上 FR-17c 估算誤差聲明。體態目標（`/set_body_goal`／`/my_body_goals`）三個子功能共用一張 `body_goals` 表，飲食目標因太主觀不做自動達成判斷，只能手動取消，這是已知的刻意簡化）

### 功能性需求 — 心情小記

- [x] FR-49：紀錄每日心情與隨筆（**2026-08-02 Step 1.8 實作**：觸發後先問心情分類（FR-56h 情境範例固定 6 選一），再問完整日記內容，全程純字串比對不需要 LLM；日記內容套用 FR-13 個資遮蔽，跟一般聊天等既有入口一致）（**2026-08-02 追加補記/更新/刪除**：Robin 提出「記帳、心情小記、體重、飲食、運動習慣都要有補記、更新、刪除、新增的功能」，心情小記優先實作，其餘三個都在 Phase 2 才會做的模組（記帳、體態管理）從一開始就會內建 CRUD、不需要另外補。新增 `mood_journals.entry_date`（`0017_add_entry_date_to_mood_journals.sql`，Robin 已核准）記錄實際發生日期，設計比照 `todos.start_at`：新增可選欄位、一律由 app 端算好台灣時區日期後寫入，不依賴資料庫預設值。「我要補記心情」／`/backfill_mood` 先問要補記哪一天（LLM 解析、只接受今天或過去日期，未來日期拒絕），講清楚後接到既有分類/內容/成就三輪反問，`entry_date` 用解析出的日期；「我的心情紀錄」／`/my_mood_journals` 列出最近 10 筆（依 `entry_date` 新到舊排序），選編號後反問要更新還是刪除——更新沿用原 `entry_date`、重新走一次分類/內容流程並改成 UPDATE；刪除採簡單一輪 LLM CONFIRM/CANCEL（不套用 FR-16a 逐字打字最終確認，理由：屬於中等風險、可事後補記修正的操作，跟待辦事項完成/取消同一等級，FR-16a 保留給 `/clean-all-dialog`／`/clean-target-dialog`／主動記知識三個「一旦誤刪就大量、跨紀錄不可逆遺失資料」的高風險流程）詳見 `src/bot/mood.py`、`src/bot/commands.py`、`api_schema.md` 的 `/backfill_mood`／`/my_mood_journals`）
- [x] FR-50：個人成就三選一提示（使用者自行選擇是否回答）：今天完成了什麼一句話總結／挑一件有感覺的事／寫下啟發或下次想改變的地方（僅需一項）（**2026-08-02 實作**：記錄完成後主動追問，使用者可輸入既有的「結束」／「沒有了」跳過，不強迫回答；有回答時同樣套用 FR-13 個資遮蔽）

### 功能性需求 — 好友模式

- [x] FR-51（**2026-08-08 規格定案並完成實作，見 ADR-22**）：心情趨勢改用文字／emoji 摘要呈現，不做圖片圖表——比照 FR-44（記帳）／FR-29（證照成效）既有決策「圖表統一交給 Phase 4 Mobile App（FR-64）」，Telegram 端只用文字或 emoji 序列（例如「最近 3 筆心情紀錄：😄😌😔（整體偏正向）」）呈現趨勢，不新增繪圖套件或請 LLM 生成圖片；未來 Mobile App 擴充範圍時再把 `mood_journals` 納入正式圖表。本條內容併入 FR-52 的好友聊天回覆中一併呈現，不獨立成一個查詢指令；實作見 `src/bot/friend_chat.py` 的 `_mood_provider()`
- [x] FR-52（**2026-08-08 規格定案並完成實作，見 ADR-22**）：使用者主動觸發好友聊天（觸發詞「陪我聊聊」／`/friend_chat`），Robinson 動態讀取這位使用者「目前已開啟且近期有資料」的所有功能模組近期紀錄——不寫死固定模組清單，逐一檢查該使用者的 `feature_toggles` 開啟狀態＋該模組近期（預設近 7 天）是否有資料，兩者皆滿足才納入 Prompt 素材；組成 Prompt 交給 LLM 生成一段陪伴式對話回覆，內容自然涵蓋 FR-51 的心情趨勢摘要與其他模組近況（例如待辦完成度、體態/記帳動態、Robin 專屬的證照學習進度等，視該使用者實際使用的模組而定）。本次範圍僅做「被動模式」——使用者需自己觸發，不含主動關懷推播（例如偵測心情連續低落主動問候），主動關懷留待未來視實際使用回饋另開 Step 展開。單輪生成完整回覆，不強制走多輪反問狀態機，使用者後續接續聊天視為一般聊天，不特別維持「好友模式」狀態。**實作**：新增 `src/bot/friend_chat.py`（`_DATA_PROVIDERS` 登記表涵蓋心情小記／待辦事項／體態管理／記帳／證照準備五個既有模組的近期查詢 provider，`gather_recent_context()` 逐一檢查開關與資料、`build_companion_prompt()` 組 Prompt）；`commands.py` 新增 `start_friend_chat()`；`router.py` 新增「陪我聊聊」／`/friend_chat` 觸發詞，放在 owner／家人共用區塊（`friend_mode` 開關 `owner_only=False`）；`templates.py` 補上情境範例。TDD 全程，`friend_chat.py` 100% 覆蓋率，新增 32 個測試，全專案 1294 個測試全過

### 功能性需求 — 重要通知

- [x] FR-53：特殊節日/生日自動發送提醒給相關成員（例如父親節不發給父親本人）（**2026-08-04 Step 2.3 實作**：分成「超級重要通知（主角不能收到）」與「重要通知（大家都收到）」兩類，固定台灣時間 08:00 推播，借用 `/healthz` 既有的 10 分鐘 cron 頻率（比照 `body.check_and_push_goal_deadline_reminders()` 等既有慣例），不需要獨立排程系統，詳見 `src/bot/notifications.py` 模組 docstring。固定節日清單：1/1 元旦（大家都收到）、除夕/初一（大家都收到，提醒包紅包）、3/1 固定提醒選一天掃墓（大家都收到）、中秋節（大家都收到，提醒烤肉/月餅）、端午節（大家都收到，提醒粽子）、父親節（西曆固定 8/8，排除 `users.role = "爸爸"` 本人）、母親節（西曆 5 月第二個星期日，排除 `users.role = "媽媽"` 本人）；農曆節日（除夕/初一/中秋/端午）改用 `lunarcalendar` 套件即時計算西曆日期（純 Python、不需要網路），不維護每年日期對照表。家人生日則用新增的 `users.birthday`（`0028_add_birthday_to_users.sql`，只比對月/日不比對年份）比對，當天排除生日當事人自己、其餘所有已綁定使用者（含 Robin）都算「大家」；已知的 5 位家人生日已由 Robin 提供並寫入 `0030_seed_family_birthdays.sql`，其餘家人（弟媳/大妹婿/小妹婿/阿姨）的生日透過新增的 Owner 專屬指令「設定家人生日」／`/set_family_birthday` 自行補上（先列出所有已綁定使用者選編號，再輸入生日，格式接受「YYYY-MM-DD」或不確定年份時的「M/D」）。年度推播去重靠新增的 `important_notifications_log` 表（`0029_create_important_notifications_log_table.sql`，`UNIQUE(notification_key, year)`），固定節日用節日代碼、生日用 `birthday_<user_id>` 各自獨立去重。詳見 `src/bot/notifications.py`、`src/bot/commands.py`、`src/bot/router.py`、`src/schema/db_schema.md`）

### 功能性需求 — Google Calendar 整合（2026-08-05 新增，見 ADR-17）

> Robin 詢問「家人沒有 Google 帳號怎麼辦」「Calendar API 要不要錢」後確認方向：單一共用行事曆（僅 Robin 帳號 OAuth 授權），家人各自訂閱即可在手機原生行事曆 App 看到全貌，不需要每人各自授權；API 本身免費（見 ADR-17）。範圍限定「Robinson 單向寫入」，讀取行事曆做空檔查詢（例如「這週三下午有沒有空」）明確排除在本次範圍，留待未來視實際使用回饋再評估。

- [x] FR-66：Google Calendar 整合總則 — 建立一個獨立的「Robinson 家庭行事曆」（Robin 的 Google 帳號底下的次要日曆，非主行事曆），透過既有 OAuth 模式（比照 `gdrive`，見 ADR-17）授權寫入；家人以訂閱方式在自己手機的原生行事曆 App（iOS/Android 皆原生支援）瀏覽，不需要各自跑 OAuth 流程
  - [x] FR-66a：待辦事項同步 — 建立待辦事項的多輪反問流程新增一題「要不要同步到 Google 行事曆？」（**2026-08-05 新增，見 ADR-17 補充決策**：每次新增都明確詢問，不預設同步也不預設不同步，避免使用者忘記講而讓私密待辦意外曝光在家庭共用行事曆上）；選擇同步的待辦事項，後續更新時間/標記完成/取消或刪除時，同步更新/刪除對應的 Google Calendar 事件；選擇不同步的待辦事項只存在資料庫，不建立任何 Calendar 事件，且 MVP 不支援事後補同步（要同步就取消重建一筆，避免額外設計「補同步」流程）；不額外拆分「待辦事項」與「行程」兩種概念，跟 FR-31 是同一份資料，Calendar 只是多一個瀏覽入口，不是另一份真相來源
  - [x] FR-66b：重要通知同步 — FR-53 的固定節日（元旦/除夕/初一/掃墓提醒/中秋/端午/父親節/母親節）與家人生日，除了既有台灣時間 08:00 當天 Telegram 推播外，額外在對應日期建立 Calendar 全天事件，讓家人提前在行事曆上看到即將到來的節日/生日，不用等到當天才知道；固定節日/生日本質上就是要讓家人知道的資訊，不涉及個人隱私疑慮，不需要 FR-66a 那種逐筆詢問，一律自動同步；複用既有 `important_notifications_log` 的 `UNIQUE(notification_key, year)` 去重判斷，同一次判斷順便建立事件，不需要額外追蹤更新/刪除（節日/生日建立後幾乎不會變動，是刻意的簡化）
  - [x] FR-66c：體態管理目標期限同步 — 設定 FR-46～FR-48 的 `body_goals` 目標時，比照 FR-66a 同樣新增一題「要不要同步到 Google 行事曆？」（**2026-08-05 新增，見 ADR-17 補充決策**：體重/運動/飲食目標對某些人來說也是不想公開的隱私，跟待辦事項同等對待，每次明確詢問；沒有期限的目標不會問這一題，因為沒有日期可以建事件）；選擇同步的目標，後續更新期限/達成/使用者手動取消時，同步更新/刪除對應事件；選擇不同步則只存資料庫，MVP 同樣不支援事後補同步
  - [ ] FR-66d（明確排除，非本次範圍）：讀取行事曆做空檔查詢（例如「我這週三下午有沒有空」「全家人這週末誰有空」）——這需要 Calendar 讀取權限與跨使用者行事曆比對，複雜度與隱私考量都高出一個量級，待前三項基礎功能上線、有實際使用回饋後再評估是否要做

### 功能性需求 — Mobile App（BI Dashboard，Phase 4，2026-08-04 取代原 Notion 後台，見 ADR-14）

> 本節僅先定調架構、技術棧與資料模型方向；登入流程與 App 各頁面的詳細互動邏輯留待 Phase 4 對應 Step 開工時展開獨立 spec（`docs/specs/mobile-app/SPEC.md`，屆時建立），此處視為 **Placeholder**。

- [ ] FR-64：唯讀 BI Dashboard 視覺化——將記帳、體態管理等模組的資料計算為圖表（消費圓餅圖、體重/運動趨勢折線圖等）與篩選介面，呈現於 Mobile App；App 端原則上不提供新增/修改/刪除資料的操作入口，寫入操作以 Telegram Bot 為主（取代原 FR-54 的 Notion 方案）。**2026-08-08 追加例外（見 FR-64a）**：藍牙體重計量測是唯一的例外，因為量測動作天生發生在手機上（App 端做藍牙掃描），不透過 Telegram 硬做反而會脫離使用情境；除此之外的資料異動仍一律透過 Telegram Bot
- [ ] FR-64a（2026-08-08 新增，Placeholder）：藍牙體重計整合——Robin 已購入支援藍牙廣播（BLE Advertisement）的體重計，並用 nRF Connect for Mobile 實測確認可從掃描結果的 Manufacturer Data（廠商資料）取得量測後的體重值。App 端新增「開始測量」按鈕，點擊後啟動藍牙掃描，10 秒內偵測到體重值則顯示並記錄；10 秒內未偵測到則顯示「未取得您的體重值」，不記錄任何資料。**體重紀錄維持雙入口**：人不在家、沒帶體重計時，同樣可以直接在 Telegram 手動輸入體重值（既有 FR-46 `/log_weight` 流程不變）；兩種入口最終都寫入同一張 `body_weight_logs`，App 端這支寫入 API 是 FR-64「App 不寫資料」原則的唯一例外，但仍遵循「後端算好結果、App 只負責渲染/呼叫」的既有分層原則，實際寫入邏輯復用現有 `body.create_weight_log()` 等既有服務層函式，不另外複製一份業務邏輯。

  **藍牙資料解析規格**（Robin 已用 nRF Connect for Mobile 實測驗證，Phase 4 開工時 App 端直接依此規格解析）：掃描到裝置後讀取廣播封包中的 Manufacturer Data 欄位，取一個 16 位元（2 bytes）的十六進位整數；取出整包 hex 資料中索引 2、3 的位元組（big-endian），組成體重原始值後除以 100 得到公斤數。Python 對照範例（Robin 提供，供未來 App 端 TypeScript/原生藍牙 SDK 實作時對照）：

  ```python
  # 拿到的 HEX 範例：16 C0 24 D6 ...
  raw_bytes = bytearray.fromhex("16C024D61388000025000000000000")
  # 取出索引 2 與 3（即 0x24D6）
  weight_raw = (raw_bytes[2] << 8) + raw_bytes[3]  # 0x24D6 -> 9430
  # 直接除以 100 得到公斤數
  weight_kg = weight_raw / 100.0  # 94.3 kg
  ```

  未涵蓋（留待 Phase 4 開工展開獨立 spec 時細部設計）：如何辨識/篩選出「這台特定體重計」的廣播封包（避免掃到附近其他藍牙裝置）、掃描逾時之外的例外處理（藍牙未開啟、權限未授權等）、App 端寫入 API 的路由設計與身分驗證細節（沿用 FR-65 的 `APP Access Token`）。
- [ ] FR-65：多用戶登入機制——App 面向所有使用者（Multi-user，不僅限於 Robin）：
  - [ ] FR-65a：一般使用者登入需輸入 `user_name`、稱謂、`APP Access Token` 三項完成驗證
  - [ ] FR-65b：Robin（Owner）登入僅需輸入 `user_name`、`APP Access Token` 兩項（比照 Telegram 免通關密碼的管理者身分簡化）
  - [ ] FR-65c：Token 的產生、過期、刷新機制與各頁面詳細互動流程，留待 Phase 4 深入討論（見上方 Placeholder 說明）

**技術細節補充（Robin 對 App 開發較不熟悉，由 Claude 主動提出以下標準做法供 Phase 4 展開時參考）**：

1. **API 設計原則**：後端（沿用現有 `src/` Flask 分層，未來若獨立拆分則遵循 AGENTS.md 的 `backend/` 樣板）新增獨立的 `/api/app/*` 路由群組，與既有 Telegram webhook 路由區隔；每個圖表對應一支 API，後端算好「圖表就緒」的 JSON 結構（例如 `{"type": "pie", "labels": [...], "values": [...]}`）後直接回傳，App 端不做任何二次聚合運算，只負責渲染——確保同一份計算邏輯只維護一處，未來若要多加一個前端（例如 Web Dashboard）也能直接複用；所有 `/api/app/*` 路由需在 `Authorization` header 帶入 `APP Access Token` 驗證身分。
2. **React Native + Expo 基礎路由結構**（Expo Router，file-based routing，實際建立時機為 Phase 4 開工時）：

   ```
   mobile/                    # 新增頂層目錄，與 src/ 平級獨立（比照 AGENTS.md 職責分離原則）
   └── app/
       ├── _layout.tsx        # 根 Layout，處理登入態導轉
       ├── login.tsx          # 登入頁（user_name／稱謂／APP Access Token）
       └── (tabs)/
           ├── _layout.tsx    # 底部 Tab 導覽
           ├── dashboard.tsx  # 總覽（各模組摘要卡片）
           ├── finance.tsx    # 記帳圖表（消費圓餅圖、月趨勢折線圖）
           └── body.tsx       # 體態圖表（體重折線圖、運動/飲食統計）
   ```

3. **資料模型補充**：`users` 表新增 `app_access_token`（`TEXT UNIQUE`，供 App 登入驗證，與 Telegram 的 `invite_codes` 機制彼此獨立、互不取代）；圖表本身不另建資料表儲存，一律即時從既有業務表（`transactions`／`body_weight_logs`／`exercise_logs`／`diet_logs` 等）聚合運算後回傳，避免資料重複與不同步。實際建表 SQL 仍依 ADR-10「先審核後執行」流程，於 Phase 4 開工、Robin 核准後才建立，此處僅為方向性的欄位規劃。

### 非功能性需求

- [ ] NFR-1：成本 — 所有服務一律使用免費方案（Render / Neon / Gemini x2 / Google Drive / cron-job.org / Expo 免費方案）
- [ ] NFR-2：可用性 — Render 免費方案 15 分鐘無請求會休眠，需 cron-job 每 10 分鐘打 keep-alive API 維持喚醒
- [ ] NFR-3：容量 — Neon 免費額度僅 0.5GB，圖片一律存 Google Drive，不進資料庫；容量達 80% 需主動告警
- [ ] NFR-4：安全 — 通關密碼一次性使用、使用者資料互相隔離（FR-10、FR-11）、個資偵測與刪除機制（FR-13）
- [ ] NFR-5：安全 — 敏感金鑰（Telegram Token、Gemini API Key ×4：`GEMINI_API_BOT_KEY`／`GEMINI_API_IMAGE_KEY1`／`GEMINI_API_IMAGE_KEY2`／`GEMINI_API_TEXT_KEY`、Groq API Key `VOICE_API_KEY`、Neon 連線字串、Google Service Account JSON、Gmail 密碼、GitHub Personal Access Token、YouTube Data API Key）一律透過 `.env` 管理，不進版控；`users.app_access_token`（Mobile App 登入用，見 FR-65）為逐使用者資料庫欄位而非全域金鑰，不適用本條「.env 管理」規則，但仍需注意不可在 log 或錯誤訊息中明碼印出。**2026-08-05 更新（見 ADR-15）**：GitHub Personal Access Token 的用途已限縮——原為 FR-19e GitHub PR 機制新增，該機制已取消，但這把權杖仍由 ADR-11 的 `src/migrations/` git push 機制使用（跟 FR-19e 是巧合共用同一把權杖，非依賴關係），故繼續保留於 `.env` 管理範圍；`GITHUB_REPO`（原本只給 FR-19e 的 GitHub REST API 指定目標 repo 用）已無用途，從 `.env.example` 移除。**2026-08-05 追加（見 ADR-16）**：Gmail 密碼（`GMAIL_PASSWORD`，需為應用程式密碼）從「Phase 3 FR-23 預留但尚未使用」變成「Step 2.4 起就會用到」——`submodules/email` 複用這組帳密透過 SMTP 寄送 Telegram 故障時的備援通知。**2026-08-05 追加（見 FR-66、ADR-17）**：新增 `GOOGLE_CALENDAR_OAUTH_CLIENT_ID`／`GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET`／`GOOGLE_CALENDAR_OAUTH_REFRESH_TOKEN` 三把敏感金鑰，比照 `gdrive` 的 OAuth 2.0 模式，但獨立一組憑證（scope 僅 `calendar.events`，最小權限，不申請完整 `calendar` scope），與 `gdrive` 的憑證互不共用，符合子模組彼此獨立、互不依賴的慣例（見 submodules-core SPEC.md FR-4）；`GOOGLE_CALENDAR_ID`（行事曆 ID，非機密但仍建議透過 `.env` 管理，統一金鑰治理方式）。**2026-08-07 追加（見 FR-22、FR-23，Step 3.1）**：`GMAIL_USER`／`GMAIL_PASSWORD` 從「Step 2.4 起用於寄信備援」再擴充為「同時用於 FR-23 讀取 TLDR 電子報」（同一組帳密，IMAP／SMTP 都支援，不需要另外申請）；新增 `GEMINI_API_SKILL_GROWTH_KEY`（第 5 把 Gemini Key），比照 `GEMINI_API_PRIVACY_KEY` 的既有慣例，讓每日技術摘要功能有獨立的 API 配額，不佔用聊天/長記憶/圖片辨識既有 Key 的額度
- [ ] NFR-6：可維護性 — 錯誤訊息對使用者一律去技術化（FR-19），技術 log 僅回報 Robin
- [ ] NFR-7：Token 節流 — 不支援會議/長演講錄音轉譯，語音上限 10 分鐘，避免大量消耗 Gemini 免費額度
- [ ] NFR-8（**2026-08-05 改寫，見 ADR-15**）：安全 — Robinson 對正式環境程式碼**不具備任何自動修改或部署能力**：發生例外時只做「記錄＋上傳雲端 log＋私訊 Robin 連結」，所有修復動作一律由 Robin 本人（或 Robin 自行請 Claude Code 協助）手動進行，系統本身沒有寫入 Git、開分支、開 PR 或部署到 `main` 的任何權限或程式碼路徑
- [x] NFR-9（**2026-08-07 完成，見 Step 2.5、Step 2.6**）：韌性 — 所有外部 API 呼叫具備重試（Max 3 次）與 Exponential Backoff 機制，重試耗盡才進入例外分級降級流程，避免單一元件失敗直接癱瘓服務（FR-19f～FR-19i）
- [x] NFR-10（**2026-08-07 完成，見 Step 2.6 FR-19h 稽核**）：一致性 — 所有寫入類操作必須提供明確的成功/失敗執行結果回饋，不允許靜默失敗（FR-19h）
- [ ] NFR-11：資料品質 — 任何透過「排程」自動收集外部資料的功能，都必須落實 ETL（Extract-Transform-Load）流程並具備去重機制，避免重複寫入資料庫；目前適用範圍：每日技術新聞摘要（FR-23）、TOEIC 雙軌題庫（FR-25f）、104 職缺爬蟲（FR-34d）、YouTube 技術情報（FR-58c）；未來新增任何排程類功能都必須比照辦理
- [ ] NFR-12：文件治理 — 所有資料表與 API 路由都必須維護對應的 schema 文件（`src/schema/db_schema.md`、`src/schema/api_schema.md`）；建表 SQL 一律先給 Robin 審核並說明設計理由，取得同意後才能執行，執行後立即同步記錄到 `db_schema.md`（見 ADR-10）
- [ ] NFR-13：合規 — 本產品僅供 Robin 與家人個人非商業使用，不對外公開、不收費；此為使用 104、YouTube Data API 等外部服務的合規基礎前提（見概要「使用性質聲明」）

## 設計決策

### ADR-1：三層式架構（前台 / 資料層 / 後台）

**背景**：需要在免費資源限制下，兼顧「聊天即服務」的體驗與「視覺化查看」的需求。

**決策**：Telegram 作為唯一前台入口；Neon（結構化）+ Google Drive（靜態圖像）作為資料層；Notion 作為選配的視覺化後台。

**理由**：Telegram 天生支援文字/語音、免費、家人已熟悉；Neon/GDrive 免費額度足敷家庭規模使用；Notion 上手快、適合非工程背景的家人瀏覽。

**替代方案**：
- 方案 A：自建 Web Dashboard — 優點是完全客製化；缺點是需額外開發前端、部署成本高，不符合「越少 UI 越好」原則
- 方案 B：全部塞進 Telegram（含圖表）— 優點是單一入口；缺點是 Telegram 不擅長呈現複雜圖表/表格

**後果**：Notion 整合可獨立於核心對話邏輯之外開發，允許排在最後或先不做而不影響 MVP 可用性。

**狀態**：accepted（後台選型「Notion」的部分 superseded by ADR-14，2026-08-04，改採 Mobile App＋React Native/Expo；Telegram 前台與 Neon/GDrive 資料層的決策維持不變）

### ADR-2：Gemini API 金鑰拆分策略

**背景**：全員共用同一組 Token 有機率快速耗盡免費額度，且對話與圖像解析的呼叫模式不同。

**決策**：申請兩組 Gemini API Token —— 一組專用於 Telegram 對話視窗，一組專用於圖像（證照題目）解析；模型統一使用 `gemini-3.5-flash-lite`（**2026-07-31 更新**，原為 `gemini-flash-latest`，見 submodules-core SPEC.md ADR-6）。

**理由**：分流可降低單一額度被單一功能耗盡的風險，並方便個別監控用量。

**替代方案**：
- 方案 A：每人一組 Token — 優點是額度隔離；缺點是免費 Token 數量有限，且需求文件已明確排除此做法
- 方案 B：單一 Token 全部共用 — 實作最簡單，但額度風險集中

**後果**：需在監控模組中分別追蹤兩組 Token 的用量並在接近上限時告警（見 FR-21）。

**狀態**：accepted

### ADR-3：通關密碼機制

**背景**：家人共用同一個 Bot，需要輕量級但可控的准入機制，且不希望增加額外 UI（如註冊頁面）。

**決策**：Robin 於資料庫預先建立通關密碼清單並私下分發；使用者第一次互動時在 Telegram 對話中輸入密碼即完成啟用，密碼使用後標記 `is_used=1` 失效。

**理由**：完全在聊天介面內完成，不需額外頁面；一次性設計避免密碼被轉發濫用。

**替代方案**：
- 方案 A：Telegram 白名單（手動加 chat_id）— 優點更安全；缺點是 Robin 需手動取得每位家人的 chat_id，操作不直覺
- 方案 B：邀請連結 — 優點使用者體驗好；缺點需額外實作 deep-link 與過期邏輯，超出 MVP 範圍

**後果**：需設計密碼與使用者的一對一綁定資料表，並在密碼輸入錯誤時給予合理提示（不可洩漏密碼是否存在等資安細節）。

**狀態**：accepted

### ADR-4：MVP 分期策略

**背景**：需求涵蓋 10+ 個功能模組（技能成長、待辦、求職、記帳、體態、心情小記、好友模式、重要通知、視覺化後台…），若全部視為 MVP 會拉長首次上線時間、且違反「MVP」定義。

**決策**：MVP（Phase 1）僅涵蓋「平台基礎設施 + 權限治理 + 對話核心（含知識庫）+ 待辦事項 + 心情小記 + 健康監控告警」；其餘功能模組依複雜度與相依性分至 Phase 2～4（詳見「實作計畫」；**2026-08-04 更新**：原規劃獨立拆出的 Phase 5「Notion 後台」已取消，視覺化後台改為 Mobile App，併入 Phase 4，見 ADR-14 與待確認事項 Q5 的回覆註記）。

**理由**：
1. 待辦事項與心情小記是最高頻、最輕量的日常互動，且待辦事項已被使用者明訂為「唯一可自行調整排程」的功能，適合最先驗證聊天式互動的可用性。
2. 求職（104 爬蟲 + 評分模型）與技能成長（TOEIC 題庫 + 排程提醒邏輯）複雜度高、依賴多個外部資料源，適合在核心架構穩定後再疊加。
3. 記帳與體態管理邏輯相似（目標 + 每日紀錄 + 預警 + 視覺化），適合放在同一 Phase 一起做，複用告警與圖表邏輯。
4. 視覺化後台屬於「錦上添花」的展示層，原規劃獨立拆成 Phase 5（Notion）、排在全專案最終階段；**2026-08-04 更新**：Notion 方案已取消，改為 Mobile App（React Native + Expo），且因技術棧與求職模組（Phase 4）性質相近（皆屬於「錦上添花、可與核心對話功能並行推進」的模組），併入 Phase 4 一併規劃，見 ADR-14。

**替代方案**：
- 方案 A：技術棧驗證優先（先做視覺化後台 + 圖表 pipeline）— 缺點是使用者感受不到「聊天助手」的核心價值
- 方案 B：全功能一次到位 — 缺點是開發週期過長，且不符合 SDD/TDD 逐步驗證的精神

**後果**：使用者需在確認本 spec 時，明確同意或調整此分期順序（見「待確認事項」）。

**狀態**：accepted（待使用者確認分期內容）

### ADR-5：語音與個資的安全護欄

**背景**：語音轉文字若無限制易消耗大量 Token（如誤傳會議錄音）；個資外洩風險需要主動防護而非事後補救。

**決策**：語音超過 10 分鐘強制中斷並提示；語音轉文字結果的修正僅接受文字輸入，且此限制僅在該筆語音送出後 15 分鐘內生效，超過 15 分鐘語音模式即恢復正常使用；偵測到個資關鍵字（身分證字號、電話、信用卡卡號格式）時主動提示收回並清除相關記錄。

**理由**：對應使用者明確列出的「Robinson 警察證」規則，屬於安全與成本雙重考量的硬性限制。

**替代方案**：
- 方案 A：事後人工審查 — 不即時、無法防止額度已被消耗
- 方案 B：完全禁止語音修正 — 使用者體驗差，且不符合需求描述

**後果**：需要在對話流程中加入個資偵測（regex / Gemini 分類）與語音時長預檢查兩道邏輯。

**狀態**：accepted

### ADR-6：錯誤處理的對外用語

**背景**：使用者不需要（也不應該）知道系統的技術錯誤細節，但 Robin 需要完整資訊才能除錯。

**決策**：對一般使用者一律回覆「生病了」等擬人化用語且不解釔原因；技術 log 僅回報 Robin；修復後主動群發「我康復了」。

**理由**：符合 Robinson 的人格設定，同時避免暴露系統架構給非技術使用者造成困惑或誤解。

**替代方案**：
- 方案 A：回傳詳細錯誤訊息 — 對非技術背景的家人不友善
- 方案 B：完全不回應 — 使用者會誤以為 Bot 失聯，體驗更差

**後果**：需要建立一個集中式的錯誤處理層，統一攔截例外並轉換為對外用語，同時寫入告警管道通知 Robin。

**狀態**：accepted

### ADR-7：異常的自主診斷與人工核准修復流程（Human-in-the-Loop，GitHub PR 機制）

**背景**：Robin 希望 Robinson 不只是把錯誤丟給人看，而是能像資淺工程師一樣先做初步診斷 —— 抓 log、上網查可能原因、評估修復的影響範圍，再把「建議方案」交給 Robin 審核，而不是自己動手改。這個能力比單純的錯誤訊息轉譯（ADR-6）複雜得多，牽涉到 AI 主動上網搜尋、產生修復建議、以及「誰能觸發正式環境變更」這個高風險決策。Robin 已於 2026-07-29 明確定義執行機制，本 ADR 更新為最終版本。

**決策**：
1. FR-19 擴充為 FR-19a～FR-19i：捕獲異常與 Log → 自主診斷與搜尋 → 衝擊評估 → 發送建議報告給 Robin（含程式碼異動紀錄）→ 核准後執行修復（GitHub PR 機制）→ 例外分級降級（一般感冒級／重大疾病級）→ 決策執行狀態閉環回饋 → 外部 API 重試機制。
2. **執行機制（FR-19e）確定為「Render 線上自主運維模組」**：Robinson 部署在 Render 上的服務本身內建這套自主運維邏輯（非本機 Claude Code CLI 操作）。發生例外時，Robinson 直接在線上呼叫 LLM API 診斷、透過 GitHub API 自動開立修復分支與 PR（PR 內容含程式碼異動紀錄），再私訊 Robin 附上 PR 連結；Robin 在 GitHub 審核並 Merge PR 後，才觸發 Render 既有 CI/CD 自動部署完成修復。
3. **「開 PR」與「核准執行」的界線**：開分支、開 PR 視為「產生建議方案」的一部分，不觸及 `main` branch，不算是需要事先核准的「執行」；真正需要人工核准的動作是「Merge PR 到 main」，這個動作本身就是 Robin 的核准，不需要另外在 Telegram 回覆「同意／執行」等字樣。Robinson 任何情況下都不具備直接推送或部署到 `main` 的權限。
4. 分兩個 Phase 交付：**Phase 1（MVP）** 只做 FR-19a（捕獲＋Log）與簡化版通知（把原始 Traceback 直接私訊給 Robin，不含 AI 分析與 PR 機制），Robin 自己判斷原因；**Phase 2** 才補上完整的 FR-19b～FR-19i（AI 診斷、衝擊評估、GitHub PR 自動化、分級降級、執行回饋、重試機制）。
5. FR-19b 的上網查詢範圍僅限「診斷系統錯誤原因」，不牴觸 FR-12「Robinson 不主動 Web Search 回答使用者問題」的規則 —— 兩者是不同情境（對外聊天 vs. 對內除錯）。

**理由**：
- Phase 1 若直接要求完整的 AI 自主診斷 + GitHub 自動化，會大幅拉長 MVP 交付時間，且此時系統還沒有真實錯誤樣本可供診斷邏輯驗證，不符合 ADR-4「MVP 聚焦最小可用範圍」的精神。
- 用「開 PR 而非直接改 `main`」作為執行機制，把 AI 能自主做的事（診斷、寫 patch、開分支）與只有人類能做的事（審核、合併到正式環境）用 Git 的既有機制（branch protection、PR review）天然分開，不需要額外自建一套權限系統。
- GitHub PR 天生就會留下完整的 diff 紀錄，滿足 FR-19d「必須包含程式碼異動紀錄」的要求，不需要額外實作 diff 產生邏輯。

**替代方案**：
- 方案 A：Robinson 直接改正式環境檔案並自動部署，Robin 只需回覆「同意」— 缺點是 AI 直接寫入正式環境程式碼風險過高，且 Render 的 Git-based 部署本來就需要 commit 進版控才能觸發，直接改檔案不符合現有部署機制
- 方案 B：先在沙箱環境驗證再部署 — 缺點是需要額外建置沙箱/staging 環境，超出免費方案資源與目前規模所需
- 方案 C（採用）：GitHub API 開分支 + PR，人工在 GitHub review 後 Merge，沿用 Render 既有的 Git-based CI/CD 自動部署

**後果**：
- `docs/specs/robinson/PROGRESS.md` 的階段時程已更新：Phase 1 的錯誤處理範圍縮小（只剩捕獲＋Log＋通知），Phase 2 新增 Step 2.4 專門做 AI 自主診斷、GitHub PR 自動化、分級降級與重試機制。
- 需新增 `GITHUB_TOKEN`（需要 repo 權限，用於建立分支與開 PR）作為新的敏感金鑰，已同步更新 NFR-5 與 `.env.example`。
- 若 Robin 長時間未處理某個 PR，目前不特別處理（PR 會持續開著），未來若需要「PR 逾時提醒」可再另開需求，非本次必要範圍。

**狀態**：superseded by ADR-15（2026-08-05，Step 2.4 開工前 Robin 重新評估後認為 AI 自主診斷＋GitHub PR 自動化風險與工程量不成比例，且 FR-19b 的上網查詢前提已因 submodules-core ADR-8 而不可行，改為「完整 log 上傳雲端＋Robin 專屬連結」的輕量方案）

### ADR-8：通關密碼設定改用對話式狀態機，不做後台表單

**背景**：原本 FR-6 只寫「Robin 於資料庫預先建立通關密碼清單」，沒有定義 Robin 實際上要怎麼操作。若要新增一個網頁後台表單來設定密碼，會違反產品「越少 UI 設定越好」的核心理念，也會多一套獨立的驗證/部署成本。

**決策**：新增僅限 Robin 觸發的「引導式設定對話流」（Conversation State Machine）：Robin 用 `/set_invite_codes` 或「設定通關密碼」文字觸發 → Robinson 逐一詢問稱謂與密碼 → 寫入 Neon DB → 循環直到 Robin 說「沒有了」結束（詳見 FR-6a～FR-6c）。

**理由**：完全複用 Telegram 對話介面，不需要另外開發/部署任何網頁表單；對話式的一問一答天然形成簡單的資料驗證（一次只問一件事，不容易漏填）；符合 Robin 一貫「用聊天完成大部分操作」的產品設計原則。

**替代方案**：
- 方案 A：Robin 直接下 SQL 手動寫入 — 優點最快；缺點是每次都要開資料庫工具，不符合「聊天完成操作」的體驗，且容易手誤
- 方案 B：獨立網頁後台表單 — 優點是介面清楚；缺點需要額外開發、部署、驗證登入態，成本遠高於效益

**後果**：需要在對話處理層實作一個簡單的「設定模式」狀態機（記錄目前在問稱謂還是在問密碼），且必須確認只有 Robin 的 `telegram_user_id` 能觸發此模式，避免家人誤觸或惡意觸發。

**狀態**：accepted

### ADR-9：YouTube 技術情報採「三層輕量規則式篩選」，不用 ML/向量推薦

**背景**：需要從 YouTube 上找出「最新技術趨勢」與「經典高技術含量影片」中最優質的內容，但完整下載/轉錄影音分析內容成本過高（運算與 Token 皆貴），且免費資源有限，需要一個幾乎零邊際成本的篩選方式。

**決策**：採用「API 相關度初篩 + 彈性品質評分（Rule-based Weight）+ 歷史去重」三層輕量篩選架構（FR-57、FR-58），只用 API 回傳的中繼資料（標題、頻道、發布時間）做排序，不下載、不轉錄、不做語意向量比對；不以發布時間作為唯一硬指標，避免篩掉經典高品質影片。

**理由**：
- YouTube Data API 的 `search.list` 呼叫（`order=relevance`）本身已經是 Google 的相關度演算法結果，direct 沿用比自建推薦模型便宜且準確度已經夠用
- Rule-based Weight（關鍵字匹配度 + 頻道權重）不需要訓練或維護模型，符合「全部免費方案」的成本限制
- 只留中繼資料、不處理影音本身，讓整個模組的運算與 Token 成本趨近於零，與其他模組（TOEIC、104 爬蟲）的免費資源原則一致

**替代方案**：
- 方案 A：下載影片並用 Gemini 做內容摘要/語意分析後排序 — 優點是排序更精準；缺點是下載+處理成本高，且大量消耗 Gemini 免費額度，不符合專案的零成本原則
- 方案 B：用 Embedding 做語意向量相似度推薦 — 優點是可以做更細緻的個人化推薦；缺點是需要額外的向量資料庫與 Embedding API 呼叫成本，對「每週 3 支影片」這種小規模推播需求是過度設計

**後果**：排序品質完全依賴 YouTube 官方相關度演算法 + 簡單規則，可能不如客製化推薦精準，但符合目前規模（每週 Top 3、僅 Robin 使用）與零成本要求；若未來要提升精準度，可在不改變資料獲取層的前提下，單獨升級 FR-58b 的評分規則。

**狀態**：superseded by ADR-21（2026-08-08，Step 3.4 開工前 Robin 釐清原始需求——他要的是「LLM 讀標題/說明欄判斷是否符合主題」而非本 ADR 討論並否決的「下載影片＋Gemini 摘要」，兩者成本量級差異很大，前者其實可以做，見 ADR-21）

### ADR-10：資料庫 Schema 建立採「先審核後執行」流程，並統一記錄於 `src/schema/`

**背景**：本產品有多張資料表（使用者、通關密碼、知識庫、待辦、記帳、體態、TOEIC 題庫、YouTube 推播紀錄、客訴…），若每次建表都各自決定欄位設計，容易缺乏一致性，也可能建出不必要或設計不良的欄位；Robin 希望對每一張表的設計保有審核權，同時要有一份「活文件」讓所有人（包含未來的 AI agent）能快速查閱目前的資料庫與 API 全貌。

**決策**：
1. 本產品所有資料表由 Claude（我）撰寫 `CREATE TABLE` SQL 語法並負責執行；但**執行前**必須先把 SQL 語法與設計理由（為什麼這樣設計欄位、型別、索引、外鍵）呈現給 Robin，取得明確同意後才能對 Neon 資料庫執行
2. 執行完成後，立即把該次的建表 SQL 與設計理由同步記錄到 `src/schema/db_schema.md`
3. 所有 API 路由（含 Telegram webhook 與內建指令如 `/rule`、`/function`、`/complaint`）統一記錄於 `src/schema/api_schema.md`，兩份文件皆隨開發進度持續更新，視為與 spec 同等重要的活文件
4. 因兩份文件都稱作「schema.md」但同資料夾不能重名，命名為 `db_schema.md`（資料表）與 `api_schema.md`（API），皆放在 `src/schema/` 底下
5. 每張表與每個欄位都必須用 `COMMENT ON TABLE` / `COMMENT ON COLUMN` 附上中文說明，直接寫在 `CREATE TABLE` 的 SQL 語法裡（而不是只寫在 `db_schema.md` 的設計理由段落）；這樣即使未來直接連 Neon 用其他工具查表，不需要回頭翻文件也能看懂每個欄位的用途，此規則適用所有未來新增/修改的資料表

**理由**：比照 FR-19e 的 Human-in-the-Loop 精神 —— AI 可以自主產生方案（這裡是 SQL 設計），但正式對資料庫執行變更前一定要有人核准；把 schema 文件與程式碼放在同一個 repo（`src/schema/`）而不是只寫在 spec 裡，是因為未來實際寫 CRUD 程式碼時，工程師（或 AI agent）會直接在程式碼目錄找答案，比回頭翻 spec 更直覺。

**替代方案**：
- 方案 A：用 migration 工具（如 Alembic）自動產生/管理 schema — 優點是版本控制成熟；缺點是對這個規模的個人專案過重，且不影響「執行前需要人工核准」這個核心需求，屬於錦上添花，非必要
- 方案 B：不特別記錄，需要時直接連 Neon 查看目前表結構 — 缺點是無法在動手改資料庫前先討論設計，也沒有歷史脈絡可查

**後果**：Phase 0 Step 0.5（Neon 資料庫初始化）與往後任何需要新增/修改資料表的 Step，都必須先在對話中提出 SQL 草案與理由，等 Robin 同意後才能執行；`src/schema/` 資料夾與兩份 `.md` 檔案需在 Phase 0 建立骨架。

**狀態**：accepted

### ADR-11：ADR-10「先審核後執行」的執行機制改為「Migration 檔案 + 開機自動套用」，取代人工貼 SQL

**背景**：ADR-10 規定建表前必須經 Robin 審核同意，但沒有規定「同意後由誰、怎麼執行」。實測發現 Claude Code / Cowork 目前所在的執行環境連不到 Neon、Telegram Bot API、GitHub REST API（`api.github.com`）、Google/YouTube API（`googleapis.com`）、Notion API（`api.notion.com`）——這些網域都被 sandbox 的網路白名單擋下（`403 Forbidden` 或 DNS 解析失敗），代表 ADR-10 原本假設的「Claude 直接對 Neon 執行 SQL」在這個環境下無法直接做到。

但同一次測試也發現一個關鍵例外：`github.com`（git 協定所走的網域，不同於 REST API 用的 `api.github.com`）是可以連線的，且用 `GITHUB_TOKEN` 搭配 git credential helper 驗證後，`git push` 實測成功。這代表 Claude 雖然不能直接連 Neon，但可以把核准過的 SQL 寫成版本控制的檔案，commit + push 到 GitHub。

**決策**：
1. 新增 `src/migrations/` 資料夾，存放已核准的 SQL，檔名格式 `NNNN_說明.sql`（例如 `0001_create_users_table.sql`），依序編號、不可回頭修改已套用過的檔案（如需變更，另開新檔案）
2. Neon 資料庫新增一張中介追蹤表 `schema_migrations`（記錄檔名、套用時間），視為本機制的基礎設施，其建立本身即隨 ADR-11 本次核准一併授權，不需再走一次 ADR-10 個別審核
3. `main.py` 啟動時自動掃描 `src/migrations/`，比對 `schema_migrations` 已套用清單，依編號順序執行尚未套用的檔案，執行後寫入追蹤表
4. 執行流程仍維持 ADR-10 的審核精神不變：Claude 提出 SQL 草案 + 設計理由 → Robin 回覆同意 → Claude 才把該筆 SQL 存成 migration 檔案並 commit + push 到 GitHub main 分支 → Robin 已確認 Render 有開啟「push 到 GitHub main 即自動重新部署」，故 push 之後會自動觸發部署，部署啟動時自動套用該筆 migration，全程不需 Robin 手動連 Neon 貼 SQL
5. `git push` 一律透過 `GITHUB_TOKEN` + git credential helper 完成驗證，禁止把 token 直接寫入 remote URL 或印出於任何指令/輸出中（避免重演本次金鑰外洩事故）

**理由**：這個方案是唯一能同時滿足「ADR-10 的人工審核不能省」與「Robin 希望核准後全自動、不用自己動手」兩個條件的作法；比起要求 Robin 自己連 Neon 主控台貼 SQL，或改用本機 Claude Code CLI 執行（仍需 Robin 每次在電腦前操作），這個方案核准後完全不需要 Robin 再介入。也不需要引入額外的 migration 工具（如 Alembic），維持 ADR-10 提到「對個人專案過重」的一致判斷，僅用一張簡單的追蹤表 + 檔案掃描就能達成版本化與冪等執行。

**替代方案**：
- 方案 A：Robin 自行連 Neon 主控台貼 SQL 執行——每次都需要 Robin 手動操作，不符合「全自動化」的目標，已否決
- 方案 B：Robin 在本機用 Claude Code CLI 執行——本機網路無限制，可行，但仍需要 Robin 每次在自己電腦前跑一次，不算真正的全自動化，保留作為此方案失效時的備援
- 方案 C：透過 GitHub REST API（`api.github.com`）自動開 branch/PR，走 FR-19e 的治理機制——但 `api.github.com` 在此 sandbox 被擋，無法直接呼叫，故本次 DB schema 執行不採用此路徑；FR-19e 的 PR 自動化機制本身不受影響（那是在 Render 正式環境或其他有網路權限的環境執行），僅代表無法在 Cowork sandbox 內測試該流程

**後果**：
- Phase 0 新增 Step 0.5a：建立 `src/migrations/` 骨架與 `main.py` 的 migration runner 邏輯
- 往後任何新增/修改資料表，都改為「提案 → Robin 同意 → Claude 建立 migration 檔並 push」，不再手動於 Neon 主控台執行
- `src/schema/db_schema.md` 的紀錄時機微調：從「執行後立即記錄」改為「push 後立即記錄」（實際套用時間以 `schema_migrations` 追蹤表為準，部署完成後可回頭核對）

**狀態**：accepted

### ADR-12：AI 模型呼叫依用途拆分四把 Gemini Key + Groq Whisper 處理語音，取代先前「語音一律用 Gemini」的決策

**背景**：隨著功能擴增，Robinson 需要處理的 AI 任務類型變多：一般問答、影像辨識（含證照題目）、語音轉文字、長文生成（翻譯題目、摘要、文案改寫）。若全部共用同一把 Gemini Key，容易讓某一類任務（例如證照題目圖片辨識）耗盡額度時，連累一般問答功能也一起停擺，違反 FR-19f「一般感冒級」希望把影響範圍限縮到最小的精神。另外，先前 FR-25b 曾記錄「語音辨識一律用 Gemini，不使用 Whisper 等其他模型」，Robin 此次明確要求改用 Groq 的 Whisper 服務處理語音，此為對先前決策的正式取代（supersede）。

**決策**：
1. 依用途拆成四把 Gemini Key，各自獨立計費與額度：
   - `GEMINI_API_BOT_KEY`：使用者一般問答（FR-9～FR-12 知識庫問答）；知識庫查無答案時，Robinson 誠實回覆不知道，並建議使用者自行查詢後把答案提供給 Robinson，下一則輸入即存回資料庫（**2026-07-31 修正**：原本規劃上網查詢後詢問存檔，因這把 Key 所屬的新 Google Cloud 專案對 Gemini 2.5 世代關閉存取、grounding 功能整條路走不通，已移除，見 [chat-core SPEC.md](../chat-core/SPEC.md) ADR-5、[submodules-core SPEC.md](../submodules-core/SPEC.md) ADR-8）
   - `GEMINI_API_IMAGE_KEY1` / `GEMINI_API_IMAGE_KEY2`：所有影像辨識工作（含 FR-25 證照題目圖片解析），**每次執行隨機擇一使用**，達到簡易的額度分攤效果
   - `GEMINI_API_TEXT_KEY`：長文/生成類文字工作（多益英翻中題目生成、語音轉文字後的重點整理、使用者要求的文案優化/改寫等）
2. 語音一律改用 Groq 的 Whisper API（`VOICE_API_KEY`）做語音轉文字，取代原本規劃的 Gemini STT；多益錄音檔的切割與辨識同樣改走這個管道
3. 本決策正式取代 FR-25b 內「語音辨識一律用 Gemini」的舊描述，FR-25b 需同步修正為「使用 Groq Whisper」

**理由**：
- 四把 Key 分流可以避免單一任務類型（尤其是耗費較高的影像/長文生成）拖垮其他基礎功能，額度管理更精細，也讓 FR-19f 分級降級的判斷更容易對應到「是哪個具體功能出問題」
- 影像雙 Key 隨機分攤是最低成本的額度分散做法，不需要額外的負載平衡邏輯
- Groq 的 Whisper 服務在語音轉文字這個單一任務上，免費額度與辨識品質均優於透過 Gemini 間接處理語音，且不影響「一律用 Gemini 做對話/生成」的整體 AI 供應商一致性（因為語音轉文字本來就是預處理步驟，轉出來的文字仍會交給 Gemini 做後續理解與生成）

**替代方案**：
- 方案 A：維持單一 Gemini Key 打天下——實作最簡單，但額度風險集中，且無法反映本次「語音改用 Groq」的明確需求，已否決
- 方案 B：所有任務都各自申請一把獨立 Key（例如問答、影像 1、影像 2、生成、語音再細分）——管理成本過高，且影像類任務本來就適合用「隨機分攤」而非「精確分類」，已否決

**後果**：
- `.env.example`／`.env` 新增 `VOICE_API_KEY`、`GEMINI_API_IMAGE_KEY1`、`GEMINI_API_TEXT_KEY`；原 `GEMINI_API_TOEIC_KEY` 更名為 `GEMINI_API_IMAGE_KEY2`（Robin 已於本機完成兩份 `.env` 檔案的更新）
- `submodules/llm` 的呼叫端範例與說明同步更新，反映四把 Key 的新用途劃分
- FR-25b 需修正措辭，反映 Groq Whisper 取代 Gemini STT 的決策
- 實作層面：需要一個「隨機選擇影像 Key」的小工具函式，供所有影像辨識呼叫共用，避免各功能各自重複實作

**狀態**：accepted

### ADR-13：影像/語音上傳採「先上雲端、後壓縮、再餵給 AI」流程，統一命名規則與 URL 入庫

**背景**：使用者上傳的圖片若直接原始尺寸餵給 Gemini，會浪費不必要的 Token 與頻寬；同時 NFR-3 已限制 Neon 免費額度僅 0.5GB、圖片一律不進資料庫，只存 Google Drive URL。目前規格對「怎麼上傳、怎麼壓縮、檔名怎麼取」還沒有統一規則，容易造成之後各功能各自土法煉鋼、URL 有的記錄有的沒記錄。

**決策**：
1. 使用者上傳的圖片與語音檔案，一律先上傳至 Google Drive（`GDRIVE_FOLDER_ID` 指定資料夾），取得檔案 URL 後才進行後續處理
2. 圖片在餵給 AI 辨識前，統一用 `Pillow` 強制縮放至 1024×1024 以下、轉存為 JPEG 品質 80%，降低傳給 Gemini 的 Payload 大小與 Token 消耗；壓縮後的版本才是實際送給 AI 辨識的版本。**2026-07-31 更新（Robin 確認）**：壓縮僅發生在記憶體內、即時處理，不另外把壓縮版存回 Google Drive——Google Drive 只保留原始檔，避免多一份檔案與多一個欄位的維護成本
3. 檔名規則：
   - 多益相關的圖片與音檔（含錄音切割後的小檔案）：檔名內須包含 `toeic` 字樣，供後續程式辨識歸類（沿用 FR-25b 既有的檔名比對邏輯）
   - 其餘一般使用者上傳的檔案：檔名採「使用者稱呼（`users.role`）＋當下時間戳記＋用途」組合（例如 `爸爸_20260731153000_飲食紀錄.jpg`）
4. 不論哪一類檔案，Google Drive 的檔案 URL 一律寫入 Neon 資料庫對應資料列。**2026-07-31 確定**：建立共用的 `media_uploads` 表（`user_id`、`media_type`〔`image`／`audio`〕、`gdrive_url`、`created_at`），Step 1.3b（影像）與 Step 1.4（語音）共用同一張表，依 ADR-10 流程經 Robin 核准 SQL 後建立（見 `src/schema/db_schema.md`）
5. 使用者上傳的語音檔本身（不含語音轉出來的文字內容）也要上傳至 Google Drive 保存原始音檔

**理由**：先壓縮再辨識可以直接降低 Gemini 呼叫的 Token 成本，符合 NFR-7 的節流原則；統一檔名規則讓之後不論是人工到 Google Drive 檢查、或程式自動掃描比對，都有一致的邏輯可以依循，不需要每個功能各自發明一套命名慣例；URL 一律入庫是延續 NFR-3「圖片不進資料庫、只存 URL」的既有原則，此處只是把它明確化為所有影像/語音上傳功能的共同義務

**替代方案**：
- 方案 A：不壓縮、直接把原始圖片送給 Gemini——實作簡單，但浪費 Token 與頻寬，且免費額度更容易被耗盡，已否決
- 方案 B：每個功能各自決定檔名規則與是否入庫——彈性最高，但會導致之後檔案散亂難以追蹤，已否決

**後果**：往後任何涉及圖片/語音上傳的功能模組（飲食記錄、心情小記附圖、TOEIC 題庫等）實作時，都必須遵守本 ADR 的上傳/壓縮/命名/入庫流程；`requirements.txt` 需新增 `Pillow`

**2026-08-02 補充**：Robin 實測語音上傳撞到 Google Drive API `403 storageQuotaExceeded`——查證後確認 Service Account 完全沒有 Drive 儲存額度，上傳到任何一般（非 Shared Drive）資料夾一律失敗，跟資料夾空間無關；`submodules/gdrive` 已改用 OAuth 2.0（以 Robin 本人帳號身分上傳），本 ADR 描述的「先上雲端、後壓縮、再餵給 AI」流程與檔名/入庫規則不變，只有底層認證方式改變。詳見 [submodules-core SPEC.md ADR-10](../submodules-core/SPEC.md)。

**狀態**：accepted

### ADR-14：視覺化後台改採 Mobile App（React Native + Expo），取代 Notion（supersede ADR-1 的後台選型部分）

**背景**：ADR-1 原本選定 Notion 作為視覺化後台，理由是「上手快、適合非工程背景的家人瀏覽」。Robin 重新評估後，希望改用自建的 Mobile App，取得更客製化的 BI Dashboard 體驗、獨立的多用戶登入機制，並讓「Telegram 負責輸入、App 負責視覺化」的分工更明確。

**決策**：
1. 移除所有 Notion API 串接與資料同步邏輯（原 FR-54 全數移除，改為 FR-64／FR-65，見上方「功能性需求 — Mobile App」）。
2. 系統架構確立為「Telegram Bot（LUI）+ Mobile App（Rich GUI）」兩前台分工：
   - **Telegram Bot**：負責所有自然語言輸入（文字/語音/照片）、系統設定與資料的 CRUD 控制，沿用既有 FR-1～FR-63 全數功能，不受本次調整影響。
   - **Mobile App**：專注 BI 圖表展示（消費圓餅圖、體重折線圖等）與動態數據篩選，**唯讀**，不提供任何寫入/CRUD 操作入口。
3. Mobile App 技術棧確定採用 **React Native + Expo**。
4. 新增多用戶登入機制（FR-65）：App 面向所有使用者而非僅限 Robin；一般使用者需輸入 `user_name`／稱謂／`APP Access Token` 三項，Robin 僅需 `user_name`／`APP Access Token` 兩項。
5. API 設計原則、React Native + Expo 基礎路由結構、資料模型補充（`users.app_access_token`），詳見上方「功能性需求 — Mobile App」的技術細節補充段落。
6. 登入與 App 各頁面的詳細互動邏輯留待 Phase 4 對應 Step 開工時再深入討論展開獨立 spec，本 ADR 僅先定調架構與技術棧方向。

**理由**：
- Notion 雖然上手快，但客製化互動式篩選能力弱、且沒有原生的多用戶權限控管機制，需要額外拼湊；自建 App 能完全掌控圖表呈現方式與登入權限模型。
- 家人主要透過手機使用，Native App 的操作體驗優於瀏覽器版 Notion 頁面或另建 Web Dashboard。
- React Native + Expo 是目前最成熟的跨平台（iOS/Android）方案之一，免費方案（Expo Go／EAS 免費額度）足敷家庭規模使用，符合 NFR-1 全免費原則。

**替代方案**：
- 方案 A：維持 Notion——優點是零開發成本；缺點是客製化程度低、多用戶登入機制需另外拼湊，且 Robin 已明確改變主意，已否決
- 方案 B：改建 Web Dashboard（React/Vue SPA）——優點是不需要處理 App Store／Google Play 上架流程；缺點是家人主要透過手機使用，Native App 體驗更佳，且與既有「越少 UI 越好、聊天優先」的產品理念相比，一個安裝一次即可用的 App 比每次開瀏覽器輸入網址更貼近日常使用情境，已否決

**後果**：
- Phase 5（Notion 後台）自實作計畫移除；相關工作併入 Phase 4，與求職模組並列（見「實作計畫」Phase 4）。
- 未來 Phase 4 開工時，新增頂層 `mobile/` 目錄放置 Expo 專案，與 `src/`（後端）平級獨立，遵循 AGENTS.md 職責分離原則；本次調整**不**立即建立任何程式碼或目錄骨架，純屬規格層級的架構調整。
- `users` 資料表未來需新增 `app_access_token` 欄位（見 FR-65），實際建表時機與 SQL 仍依 ADR-10「先審核後執行」流程，於 Phase 4 開工、Robin 核准後才建立。
- NFR-1、NFR-5 已同步移除 Notion 相關描述（見上方非功能性需求）。

**狀態**：accepted

### ADR-15：Step 2.4 取消 AI 自主診斷＋GitHub PR 自動化，改為「完整 log 上傳雲端＋Robin 專屬連結」（supersede ADR-7）

**背景**：Step 2.4 開工前重新評估 ADR-7 訂下的方案，發現兩個實際落地時的關鍵問題：① FR-19b 要求「上網查詢可能原因」，但 [submodules-core SPEC.md](../submodules-core/SPEC.md) ADR-8 已記錄 Gemini 的 Google Search grounding 功能因新 Key 對 Gemini 2.5 世代 404「no longer available to new users」而被整個移除，Robin 明確表示不考慮開通計費帳戶，代表 FR-19b 字面要求的「即時上網查詢」技術上已經做不到，只能退化為「LLM 純推理」，可靠度打折且對「套件/API 版本又出怪招」這類問題容易誤判（這正是專案自己在 ADR-6～ADR-8 那幾輪 Gemini 模型下架風波中親身遇過的情境）② FR-19e 要求 AI 自動生成程式碼修改並透過 GitHub API 提交進分支——這需要新建 `submodules/github/client.py`、串接 GitHub API、讓 LLM 讀取相關檔案內容生成 diff，工程量與風險都相當高（LLM 在缺乏完整 codebase 上下文下自動修改正式專案程式碼，即使不直接 Merge，審查負擔也可能比人工從頭修復更高），且這個 sandbox 環境連不到 `api.github.com`（ADR-10 已記錄過此限制），無法在此直接驗證整合。Robin 評估後認為這套機制難度與風險不成比例，希望簡化為一個更務實的替代方案：Robinson 只需要在捕獲例外時，把完整診斷資訊（Traceback、觸發功能、使用者輸入摘要）存成 log 檔案上傳到 Google Drive（複用 Step 1.3b 既有的 `GDriveClient`），私訊 Robin 一個專屬連結，讓 Robin 自己點開查看、或視情況另外請 Claude Code 協助排查修復；其他使用者仍然只收到既有「生病了」安全用語，不會有任何差異。

**決策**：
1. FR-19b～FR-19e 整套「AI 自主診斷→衝擊評估→建議報告→GitHub PR 自動化→人工 Merge 核准」機制取消。FR-19c／FR-19d／FR-19e（含 FR-19e-1～FR-19e-5）三條需求編號直接移除，FR-19b 改寫為新內容：「完整錯誤 log 上傳雲端＋私訊 Robin 專屬連結」。
2. 新版 FR-19b 具體設計：延伸既有 `webhook._notify_robin_of_error()`，例外發生時把完整 Traceback（Python 內建即含檔案/行號/呼叫堆疊）＋觸發功能＋使用者輸入摘要＋時間戳記組成 log 檔案內容，呼叫既有 `submodules/gdrive/client.py` 的 `GDriveClient.upload_file()` 上傳，取得 `webViewLink` 後附加在私訊 Robin 的訊息裡；上傳失敗需優雅降級（訊息略過連結欄位、記警告 log），不得影響「生病了」安全用語與私訊 Robin 這兩件事本身正常運作。
3. **對其他使用者（含觸發當下的一般使用者與所有其他家人）的行為完全不變**：一律只收到既有的「生病了」等安全用語，絕不揭露技術細節、Traceback 或任何連結；Google Drive log 連結只出現在私訊 Robin 的專屬訊息裡，這是本次修改唯一新增的資訊管道，且僅限 Robin 可見。
4. FR-19f～FR-19i（例外分級降級、決策執行狀態閉環回饋、外部 API 重試機制）不受影響，維持原規劃，留待 Step 2.5～2.6 實作。
5. `GITHUB_REPO` 環境變數移除——這個變數當初是為了讓 GitHub REST API 知道要對哪個 repo 開分支/PR，現在不再需要。**但 `GITHUB_TOKEN` 必須保留**：ADR-11 記錄過這把權杖還有另一個完全獨立的用途——`src/migrations/` 機制的「Claude 提出 SQL → Robin 核准 → commit + push 到 GitHub main」流程，`git push` 是透過 `GITHUB_TOKEN` + git credential helper 驗證的，跟本次取消的 GitHub REST API PR 自動化是兩件不相關的事，只是恰好共用同一把權杖；NFR-5 同步註記這把金鑰現在的用途已限縮為「git push 驗證」，不再用於任何 GitHub REST API 呼叫。新方案本身複用既有的 `GDRIVE_OAUTH_REFRESH_TOKEN`／`GDRIVE_FOLDER_ID`，不需要新增任何金鑰。

**理由**：
- FR-19b 原本設計的「上網查詢」前提（Gemini Search grounding）已經在 ADR-8 被證實不可行，繼續照抄舊設計等於在一個已知做不到的前提上蓋東西。
- Traceback 本身就完整包含「哪支 py 檔案、哪一行、呼叫堆疊」這些資訊，不需要額外的 AI 診斷或程式碼異動生成邏輯就能滿足 Robin 真正的需求（**看到問題出在哪，方便自己或請 Claude Code 修**），改用雲端連結只是解除 Telegram 4096 字元訊息上限造成的截斷問題，複雜度與原方案不成比例。
- 完全複用 Step 1.3b/1.4 已經上線驗證過的 `GDriveClient`，不需要新的 submodule、新的外部服務串接、新的敏感金鑰，開發與測試都能在既有基礎設施與這個 sandbox 環境內完成，不受 `api.github.com` 網路限制影響。
- 風險大幅降低：拿掉「LLM 自動生成並提交程式碼變更」這個最高風險環節，正式環境程式碼的修改權限完全保留在 Robin 手上，NFR-8 的 Human-in-the-Loop 精神不但沒有減弱，反而更徹底（連「開 PR」這個較低風險的自動化都不做了）。

**替代方案**：
- 方案 A：維持 ADR-7 原方案，FR-19b 改用其他免費/低成本搜尋 API（如 Brave Search）取代已失效的 Gemini grounding——技術上可行，但仍要額外申請 Key、整合成本高，且沒有解決 FR-19e GitHub PR 自動化本身的工程量與審查風險問題，Robin 選擇不採用
- 方案 B：開通 Gemini 計費帳戶恢復 Google Search grounding，其餘維持 ADR-7 原設計——涉及 Robin 個人帳務決定，且與 submodules-core ADR-8 的既有決策矛盾，已否決
- 方案 C（採用）：完全取消 AI 自主診斷＋GitHub PR 自動化，改用「雲端 log 連結」的輕量方案

**後果**：
- `docs/specs/robinson/PROGRESS.md` 的 Step 2.4 說明與時程估計需同步更新，反映範疇大幅簡化。
- 系統架構總覽表移除「治理 | GitHub API」這一列；`GITHUB_REPO` 從 `.env.example` 移除，`GITHUB_TOKEN` 保留（ADR-11 的 migration git push 機制仍依賴它），NFR-5 註記其用途已限縮為 git push 驗證。
- 風險表移除「AI 自主診斷誤判」「GitHub PR 逾時未處理」等隨此機制取消而消失的風險項目，新增「Drive log 檔案無生命週期管理」的低風險項目。
- 未來若診斷需求成長到現有方案不敷使用（例如真的需要更聰明的自動化排查），可以在有更多真實錯誤樣本、且 Gemini grounding 或其他搜尋方案重新可行之後，另開新的 ADR 重新評估，不受本次決策綁死。

**狀態**：accepted

### ADR-16：Telegram 本身故障時的備援通知管道，新增 `submodules/email`

**背景**：Robin 驗收 Step 2.4（FR-19b，錯誤 log 雲端連結）時提出一個關鍵問題：Telegram 是 Robinson 唯一的對外管道，`_notify_robin_of_error()` 私訊 Robin 的機制完全建立在「Telegram 自己是正常運作的」這個假設上——如果今天壞掉的剛好是 Telegram API 本身（或 `TELEGRAM_BOT_TOKEN` 失效），連這個錯誤通知本身都送不出去，Robin 會完全收不到任何主動通知，只能自己去 Render Dashboard 翻應用程式 log。這是 FR-19b 設計時沒考慮到的單點故障，需要補上一條獨立備援管道。

**決策**：
1. 新增 `submodules/email`（見 submodules-core SPEC.md FR-11、ADR-11），提供 `EmailClient.send_text(to, subject, body)`，用 Python 標準函式庫 `smtplib` 直打 Gmail SMTP（SSL），不安裝任何第三方套件。
2. 複用既有的 `GMAIL_USER`／`GMAIL_PASSWORD` 環境變數（原為 Phase 3 FR-23 讀取 Gmail 電子報預留，至今尚未有程式碼使用），不新增另一組寄信專用憑證。
3. `webhook.py` 的 `_notify_robin_of_error()` 拆成兩段 try/except：第一段組裝通知內容（Traceback、log 上傳），失敗就直接放棄；第二段專門負責「透過 Telegram 送達」，只有這段失敗才呼叫新增的 `_send_email_fallback()`，寄一封內容跟 Telegram 訊息同等資訊量（含完整 Traceback）的備援信給 Robin 自己的 Gmail 帳號。
4. Email 備援只有這一層：`GMAIL_USER`／`GMAIL_PASSWORD` 未設定或寄信本身也失敗，一律只記 log、不再有下一層備援，這是刻意的設計邊界（Email 跟 Telegram 是兩個完全獨立的基礎設施，同時故障的機率已經足夠低，不需要無限疊加備援層級）。

**理由**：
- Email 跟 Telegram 是不同公司、不同協定的獨立基礎設施，同時掛掉的機率遠低於單一管道，適合當作最後一道防線。
- 複用既有的 `GMAIL_USER`／`GMAIL_PASSWORD` 而非新增一組憑證，減少要保管的金鑰數量，且這兩個變數本來就是 Robin 自己的帳號。
- 拆成兩段 try/except 才能準確分辨「連通知內容都組不出來」（email 備援也無用武之地）跟「內容組好了但 Telegram 送不出去」（email 備援才有意義）這兩種不同的失敗情境，避免不分青紅皂白地觸發備援。

**替代方案**：
- 方案 A：改用第三方 Email API（SendGrid／Mailgun）——優點是送達率可能更好；缺點是要多申請帳號/Key，對「極少觸發」的備援用途不划算，已否決
- 方案 B：改用 Discord/Slack Webhook 當第二管道——優點一樣即時；缺點是同屬「即時通訊 API」風險類別，若是網路層級的問題可能兩者一起失效，風險相關性比 Email 更高，已否決
- 方案 C（採用）：`smtplib` 直打 Gmail SMTP，複用既有 `GMAIL_USER`／`GMAIL_PASSWORD`

**後果**：
- 新增 `submodules/email/`，詳見 submodules-core SPEC.md FR-11、ADR-11、Step S.11。
- `webhook.py` 新增 `_send_email_fallback()`，`_notify_robin_of_error()` 拆成兩段 try/except；`GMAIL_USER`／`GMAIL_PASSWORD` 從「預留未用」變成「Step 2.4 起實際使用」，NFR-5 同步註記。
- 這個備援機制的涵蓋範圍僅限「私訊 Robin 的錯誤通知」（`_notify_robin_of_error()`），不涵蓋一般使用者收到的「生病了」安全用語——一般使用者本來就沒有登記 email，這件事本質上無法用同樣的機制解決，屬於 Telegram-only 架構的既有限制，不在本次範圍內。

**狀態**：accepted

### ADR-17：新增 Google Calendar 整合，單一共用行事曆（Robin 帳號 OAuth），不做per-user 授權

**背景**：Robin 想幫 Robinson 加一個 Google Calendar 工具，討論後聚焦出三個有價值的方向：待辦事項、重要通知（節日/生日）、體態目標期限單向同步寫入 Calendar，讓家人不用開口問就能在手機原生行事曆 App 看到全貌。過程中確認兩個關鍵前提：① 家人不一定有 Google 帳號——查證後 Google Calendar 支援不需要帳號的「私密 iCal 網址訂閱」，但同步延遲可能長達 24 小時，不適合即時提醒用途；② Calendar API 本身免費（額度每分鐘 10,000 次請求，家庭規模用量遠用不到）。

**決策**：
1. 建一個獨立的「Robinson 家庭行事曆」（Robin Google 帳號底下的次要日曆），Robinson 只透過 Robin 一人的 OAuth 授權寫入，家人用「訂閱」的方式在自己手機看，不需要各自授權（比照 `gdrive` 現有模式）。
2. 家人若沒有 Google 帳號，建議直接申請一個免費帳號取得即時雙向同步體驗（Android 手機通常本來就有）；若真的不想辦，退而求其次用「私密 iCal 網址訂閱」，但明確定位為「非即時、隨手瀏覽大局」用途，不取代 Telegram 既有的即時推播機制——兩個管道分工明確，不是二選一。
3. MVP 範圍只做「Robinson 單向寫入」，不做「讀取行事曆查空檔」（原規劃第 4 點）——後者需要 Calendar 讀取權限、跨使用者行事曆比對，複雜度與隱私考量都高出一個量級，留待前三項基礎功能有實際使用回饋後再評估。
4. 待辦事項同步（FR-66a）不額外拆分「待辦事項」與「行程」兩種概念，MVP 先同步所有 `todos`，避免過度設計；Calendar 是既有 `todos` 資料的額外瀏覽入口，不是另一份真相來源。
5. 新增獨立的 `submodules/calendar`（比照 `gdrive` 的 OAuth 2.0 模式），但用**獨立一組憑證**，scope 只申請 `calendar.events`（最小權限，不要完整 `calendar` scope），跟 `gdrive` 的憑證互不共用——即使兩者可能來自同一個 Google Cloud 專案，也刻意讓每個子模組的金鑰各自獨立管理，符合 submodules-core SPEC.md FR-4「子模組彼此獨立、互不依賴」的既有原則，任一組憑證外洩時的影響範圍互相隔離。
6.（**2026-08-05 補充**）家人的共用權限固定設為「查看所有活動詳細資料」（唯讀），不給「進行變更」權限——這是 Google Calendar 共用設定本身的權限分級，不需要 Robinson 額外寫程式限制。理由：Robinson 只寫不讀（見決策 3），如果家人能直接編輯，Robinson 完全不知道被改了什麼；一旦之後 Robinson 因為待辦事項/目標更新而覆寫同一筆事件，家人的手動修改會被無聲蓋掉，比「Robinson 不知道」更麻煩（資料被默默覆蓋而不自知）。設定唯讀權限從根本上避免這個衝突，不用在應用層額外處理。
7.（**2026-08-05 補充**）Robin 提出部分待辦事項/體態目標可能是使用者不想讓其他家人看到的隱私（例如幫某人準備的驚喜、正在偷偷減肥）；確認方向：FR-66a（待辦事項）與 FR-66c（體態目標）的建立流程各自新增一題「要不要同步到 Google 行事曆？」，**每次都明確詢問，不設預設值**（多一輪反問換取不會因為忘記講而外洩隱私），選擇不同步的項目只留在資料庫、不建立任何 Calendar 事件；FR-66b（重要通知，節日/生日）本質上就是要讓全家人知道的資訊，不涉及個人隱私，維持全部自動同步，不用逐筆詢問。

**理由**：
- 單一共用行事曆＋Robin 一人授權，是複雜度最低、又能滿足「家人能在手機上看到全貌」這個核心需求的做法；per-user 授權要每個家人各自跑一次 OAuth 同意流程，複雜度直接跳到 Mobile App（Phase 4）等級，不成比例。
- Telegram 跟 Calendar 分工明確（即時推播 vs 隨手瀏覽），不會因為 iCal 訂閱的延遲問題而讓家人誤以為 Calendar 是即時提醒管道，避免錯誤預期。
- 不拆分「行程」概念是刻意的最小可行版本：如果之後發現「待辦事項」跟「行程」混在一起造成困擾（例如很多待辦事項是純自我提醒，不適合出現在家庭共用行事曆上），再回頭評估要不要拆分,現在沒有實際使用回饋支撐這個複雜度。

**替代方案**：
- 方案 A：每個家人各自 OAuth 授權自己的 Google 帳號——體驗最完整（雙向、各自隱私），但複雜度跳級，且家人不一定有 Google 帳號，已否決
- 方案 B：只用私密 iCal 網址訂閱、不管家人有沒有 Google 帳號——省去帳號申請的溝通成本，但同步延遲問題無解，且訂閱網址本身是敏感憑證，處理不慎有外洩風險，已否決（但保留當「家人不想辦帳號」時的備案）
- 方案 C（採用）：單一共用行事曆＋Robin 帳號 OAuth 授權，家人建議辦免費帳號取得即時體驗，不想辦的用 iCal 訂閱當退而求其次的方案

**後果**：
- 新增 `submodules/calendar/`（`client.py`／`README.md`／`requirements.txt`／`.env.example`），對應 submodules-core SPEC.md 新增 FR-12、ADR-12、Step S.12；`get_refresh_token.py` 已先行建立（2026-08-05，不影響 production，只是一次性本機授權腳本）。
- 需要新的資料庫欄位：`todos.google_calendar_event_id`、`todos.sync_to_calendar`（`BOOLEAN`）、`body_goals.google_calendar_event_id`、`body_goals.sync_to_calendar`（`BOOLEAN`），依 ADR-10「先審核後執行」流程，實際建表 SQL 待 Step 開工時提出並經 Robin 核准；`sync_to_calendar` 由建立當下的反問結果決定，MVP 不支援事後修改（見決策 7）。
- Robin 需要完成幾項一次性的手動設定（Google Cloud Console 開通 Calendar API、建立次要日曆、以「查看所有活動詳細資料」唯讀權限分享給家人、跑一次互動式授權腳本取得 refresh token）才能讓這個功能真正動起來，這些是操作面的準備工作，不是程式碼可以自動化的部分。
- NFR-5 新增三把 Google Calendar 專屬敏感金鑰，系統架構總覽表新增一列。
- FR-66a／FR-66c 的多輪反問流程各多一輪「要不要同步」的詢問，使用者建立待辦事項/體態目標時的互動步驟數 +1。

**狀態**：accepted

### ADR-18：TOEIC 雙軌題庫 Pipeline（Step 3.2）三項設計決策

**背景**：Step 3.2 開工前經 AskUserQuestion 與 Robin 確認三個關鍵設計問題，記錄於此供未來參考。

**決策**：
1. **`gdrive` 擴大 OAuth scope 而非改走 Telegram 上傳**：Robin 選擇維持「直接把照片/音檔手動丟進 Google Drive 資料夾，機器人每週排程掃描」的工作流程（符合 FR-25a／25f 原文設計），而非改成透過 Telegram 傳送。原本 `submodules/gdrive` 刻意只做 `upload_file()`、scope 固定 `drive.file`（只能看到本程式自己建立的檔案），看不到 Robin 手動上傳的檔案；本次新增 `list_files()`／`download_file()`，scope 擴大為 `drive.file + drive.readonly`，Robin 需重新執行一次 `get_refresh_token.py` 取得新 refresh token。
2. **整包聽力 MP3 自動切割這次一起做**：Robin 手上還沒有真實錄音可以驗證切法對不對，經提醒風險後仍選擇一起做。切割邏輯（`src/bot/toeic._find_split_plan()`）用 Groq Whisper 逐句時間軸之間的停頓當候選切割點，是**尚未經真實素材驗證的啟發式判斷**，Robin 上傳第一份整包音檔後大概率需要依實際效果調整參數。**2026-08-07 同日追加驗證**：Robin 上傳真實錄音 `Test01_Part1.mp3`（6 題、276.7 秒）實測，發現原始版本（單純取最大的幾個停頓當切割點）會把開頭一段作答說明語音（TOEIC Part 1 開考前的固定口頭指示，實測約 117.6 秒）整段併入第一題，導致第一段長度是其他題目的 5 倍以上；Robin 確認「有的音檔可能有這種說明語音、有的可能沒有，都要考慮到」。修正為：候選切割點先依「停頓長度至少達全音檔最大停頓的一半」篩選掉句子內部的小停頓雜訊，再把「完全沒有說明語音」與「音檔前 60% 範圍內每一個候選停頓都當作一次可能的說明語音結尾」逐一試切、實際比較每種切法的「每段長度變異數」，選變異數最小（最平均）的一組——用真實錄音重新實測後，正確排除了說明語音，6 段題目長度落在 12.5～36.3 秒之間（多數集中在 27～29 秒），較先前的 152.8 秒異常值大幅改善；新增迴歸測試 `test_split_audio_by_question_count_excludes_leading_instructions_regression()` 用合成音檔重現同樣情境防止未來退化。
3. **Step 3.2 範圍只到「建題庫」**：每週日 22:00 建好題庫後，「每天早上 8 點上線」的每日推播/作答/批改功能明確留給 Step 3.3（FR-26～FR-30），避免兩個 Step 的邊界混在一起、之後要調整作答邏輯時牽動範圍過大。FR-24 的「目標設定＋方向建議」對話式功能因性質與 FR-26 相近，也一併留到 Step 3.3。
4. **同日追加：`exam_type` 泛用化，不寫死證照種類清單**：Robin 完工後詢問「以後新增 GCP、AWS 等其他證照考試，現有機制能否直接沿用」。原始設計把 TOEIC 寫死在檔名前綴解析（`toeic_XXXX_write_1.png`）、資料表名（`toeic_questions`）、Vision Prompt 內文，無法直接套用到其他證照類型。Robin 明確要求「exam_type 不能直接鎖死這三類（TOEIC/GCP/AWS），因為會有多種可能，不然就是一律在 Telegram 設定 exam_type」，於是當場決定泛用化：檔名格式改為 `{exam_type}_{test_id}_write/listen_{題號}.{ext}`，`exam_type` 從檔名第一段開放解析成任意字串（不加 CHECK 限制、不寫死列舉清單），資料表 `toeic_questions` 重新命名為 `certificate_questions` 並新增 `exam_type` 欄位（見 `0038_generalize_toeic_questions_to_certificate_questions.sql`，Robin 核准）；Drive 掃描邏輯同步從「檔名關鍵字過濾」改成「列出整個資料夾所有檔案」（經 AskUserQuestion 確認 Robin 選擇「直接列出整個資料夾所有檔案」而非改用 Telegram 設定），避免關鍵字過濾漏掉非 TOEIC 檔案。軌道二（`toeic_vocab_questions`、Gemini 生成單字題）刻意維持 TOEIC 專用不泛用化，因為英文單字題的生成玩法跟技術證照的考古題性質不同，見 `src/schema/db_schema.md` `toeic_vocab_questions` 變更紀錄。

**理由**：
- 決策 1：符合 Robin 原本設想的使用情境（拍照後直接丟資料夾，不用透過聊天視窗一張張傳），且是 FR-25a／25f 原文已經隱含的設計，改用 Telegram 反而需要另外修改 SPEC 文字。
- 決策 2：一次把 Pipeline 做完整，比分兩次交付更有效率；風險已提前告知 Robin 並取得同意，且程式碼有完整 try/except 保護，切割失敗只會讓那一批聽力題暫緩處理、不影響其他題目或系統穩定性。
- 決策 3：延續 Step 3.1（每日技術分享）的「先確認範圍再動工」慣例，避免範圍蔓延（scope creep）。
- 決策 4：Robin 對未來擴充性有明確要求（不寫死清單），開放式字串解析成本低（不需要 CHECK 約束、不需要每次新增證照類型就開 migration），符合「新增證照類型只換檔名前綴、不改程式碼」的目標；若日後真的需要更嚴謹的驗證（例如防呆打錯字），可以之後再視實際使用情況加上應用層級的白名單提示，不影響資料庫層彈性。

**替代方案**：
- 決策 1 替代方案：透過 Telegram 上傳（見上方比較）——不用改 OAuth scope，但不符合 Robin 原本設想的工作流程，已否決。
- 決策 2 替代方案：先只做「已切好的小檔案比對」，大型 MP3 自動切割留到有真實素材後再做——風險更低，但 Robin 選擇效率優先，已否決。
- 決策 4 替代方案：一律在 Telegram 對話設定 `exam_type`（Robin 提出的備案）——多一道手動設定步驟、且跟「檔名驅動」的既有工作流程不一致，已否決；另一個被否決的方案是用 CHECK 約束鎖死 `('toeic', 'gcp', 'aws')` 固定清單——直接違反 Robin「不能鎖死這三類」的明確要求，已否決。

**後果**：
- Robin 需要在方便的時候執行 `get_refresh_token.py` 並更新 `.env`／Render 的 `GDRIVE_OAUTH_REFRESH_TOKEN`，否則軌道一在正式環境會因為看不到 Drive 檔案而永遠掃到 0 筆（不影響軌道二的單字題生成，兩者互相獨立、任一邊失敗不影響另一邊，見 `run_weekly_pipeline()`）。
- 整包 MP3 切割邏輯的參數（停頓門檻等）未來可能需要依 Robin 實測結果調整，不是一次到位的定案。
- FR-24、FR-26～FR-30（含每日推播機制）留待 Step 3.3 一併展開規劃。
- `exam_type` 沒有拼字檢查，Robin 上傳檔案時若打錯字（例如 `gcp` 打成 `gpc`）會被當成新的證照類型獨立存在，不會報錯也不會自動歸併；目前刻意不處理，等真的發生再視情況加防呆。

**狀態**：accepted

### ADR-19：Step 3.3（作答紀錄、成效追蹤與正式成績）設計決策

**背景**：Step 3.3 開工前經多輪對話與 AskUserQuestion 與 Robin 確認範圍與關鍵設計問題，記錄於此供未來參考。

**決策**：
1. **每日推播固定 08:00**：比照 `skill_growth_digests`（Step 3.1）的排程模式，借用 `/healthz` 既有 10 分鐘 cron 頻率、只在對應小時內執行，不另建獨立排程系統。
2. **正解改用真實拍照，不用 AI 推論**：Robin 手上有購買的測驗書正確解答／詳解，選擇拍照上傳而非讓 Gemini 推論答案。檔名規則 `{exam_type}_{test_id}_write/listen_{題號}_ans.png`，延伸 Step 3.2 的檔名解析（`parse_filename()`）辨識 `_ans` 後綴；週排程掃描分兩階段：先處理一般題目檔案（建立題目列），再處理 `_ans` 檔案（用 `exam_type`／`test_id`／`question_type`／`question_number` 比對既有題目後 `UPDATE` 補上正解＋詳解，不新建題目列）。因為是真實資料，批改訊息不需要加註「AI 推論僅供參考」之類的免責聲明。
3. **缺正解的題目排除於每日推播候選池**：若 Robin 忘記拍或漏傳某題的答案照，該題不會出現在每日推播選題，直到正解補齊為止；不使用「沒答案時才由 AI 推論備援」的方案，避免批改內容混雜不確定的 AI 猜測。
4. **成效查詢改為彈性文字問答，不做圖表**：查證 Phase 2 記帳／體態管理模組程式碼後確認一開始就是文字摘要呈現、沒有任何圖表產生模組可以沿用或移除；圖表視覺化統一交給 Phase 4 Mobile App 的 FR-64 BI Dashboard。FR-29 在 Telegram 端一律用自然語言文字摘要回覆，需要能：① 排除未作答的日子並從平均計算中扣除 ② `exam_type` 或「正式測驗 vs 日常小考」不明確時主動反問 ③ 支援跨時間區間比較。
5. **錯題統計維度沿用既有欄位，不新增主題標籤**：`certificate_questions` 目前只有 `question_type`（write/listen）與 `exam_type`，沒有更細的文法/字彙/Part 1-7 分類。權衡「新增 `category` 欄位可統計更細但增加 Vision 解析不確定性與複雜度」與「用現有欄位足夠回答『最常出錯的地方』」後，選擇不新增欄位，用現有維度統計即可。
6. **作答紀錄用一張統一表串連軌道一／軌道二**：軌道一（`certificate_questions`，拍照建題庫）與軌道二（`toeic_vocab_questions`，Gemini 生成單字題）是兩張分開的題庫表。新增的作答紀錄表用兩個可為 NULL 的外鍵（分別指向兩張題庫表的 `id`）＋ `CHECK` 限制兩者只能有一個非 NULL，取代「分開建兩張作答紀錄表、查詢時 UNION」的方案，讓 FR-29 查詢「一段時間成效」不用跨表 UNION。
7. **正式成績獨立建表**：FR-30「保留欄位記錄實際應考日期與正式成績」跟「每日小考作答紀錄」是不同概念——同一 `exam_type` 可能多次應考、各自有獨立的應考日期與分數，因此獨立建表而非在 `users` 或 `certificate_questions` 加欄位。

**理由**：
- 決策 1：延續既有排程慣例，降低維護成本，不需要新的排程機制。
- 決策 2、3：Robin 有現成的正確解答來源，比讓 AI 推論更準確、也不需要額外的信賴聲明；缺正解題目直接排除是最簡單、不會誤導使用者的處理方式。
- 決策 4：避免重工——現有模組已經是文字摘要路線，維持一致的產品體驗（Telegram 純文字、App 才看圖表），也符合 Robin 對 Phase 4 App 的整體規劃。
- 決策 5：避免 Step 3.3 範圍蔓延到「重新設計 Vision 解析 Prompt 與題目主題分類系統」，延續 Step 3.2 決策 3「先求穩」的慣例；日後真的需要更細的統計維度可以再加欄位，不影響現有資料。
- 決策 6：查詢效能與程式碼複雜度考量，一張表可以直接用單一 SQL 查出一段時間所有作答紀錄，不需要在應用層合併兩個查詢結果。
- 決策 7：正式成績跟每日小考在語意上是兩件事（一次考試的最終結果 vs. 每天練習的逐題紀錄），混在同一張表會讓兩種查詢邏輯互相干擾。

**替代方案**：
- 決策 2 替代方案：沿用原規劃讓 Gemini Vision 推論正解——已否決，Robin 有更準確的真實資料來源。
- 決策 3 替代方案：沒有正解時照樣推播、事後標記待確認，或沒有正解時才用 AI 推論備援——皆已否決，Robin 選擇最簡單、不混入不確定資料的方案。
- 決策 5 替代方案：新增 `category` 欄位讓 Vision 解析時順便標注更細主題——已否決，避免增加解析不確定性與 scope creep。
- 決策 6 替代方案：軌道一／軌道二分開建兩張作答紀錄表——已否決，查詢會需要 UNION 兩張表，增加程式複雜度。

**後果**：
- `certificate_questions` 新增 `correct_answer`／`explanation`／`answer_source_filename` 欄位，Step 3.2 既有的「正解為 NULL」資料在補拍 `_ans` 照片前，會持續被排除於每日推播候選池之外。
- Step 3.2 的週排程掃描邏輯（`sync_track1_from_drive()`）需要改為兩階段處理，處理順序變得重要（先題目後正解），需要對應測試覆蓋處理順序錯亂的情境（例如同一批次內 `_ans` 檔案先於題目檔案被列出）。
- 新增作答紀錄表因為用兩個可為 NULL 的外鍵＋ CHECK 限制，寫入時呼叫端需要明確知道是軌道一還是軌道二的題目 ID，多一層呼叫端判斷邏輯。
- FR-29 的自然語言解析（`exam_type`／正式-小考／日期區間）複雜度較高，需要比照 FR-31（待辦事項自然語言解析）的既有模式處理歧義反問。

**狀態**：accepted

### ADR-20：Step 3.3 每日推播出題（FR-26）與作答（FR-27）細部設計

**背景**：ADR-19 定案 Step 3.3 整體範圍後，開工前針對「每日推播出題」「作答」這兩塊互相牽動的功能，經多輪對話與 AskUserQuestion 進一步確認設計細節。

**決策**：
1. **出題數量/比例依 `exam_type` 是否為 TOEIC 而不同**：非 TOEIC 的證照類型只能調「每日出題數量」（單一數字，預設 6 題）；TOEIC 除了「每日出題數量」，還能另外調「聽力／填空／單字」三軌的出題比例（沿用 FR-25 原文預設 1:2:3）。理由：非 TOEIC 證照沒有軌道二（單字題）可分配，只有一個題庫池，沒有「比例」可言；現階段只有 TOEIC 有實際題庫，其他證照類型的分配邏輯留待真的新增時再設計，避免現在就為假設性需求過度設計。
2. **新題／複習題比例**：另開一個跟 TOEIC 三軌比例不同維度的「複習比例」，預設新題:複習題 = 7:3，所有 `exam_type` 通用（TOEIC 會先照三軌比例分好各軌題數，再從各軌題數裡挖一部分改成複習題）。複習池只放「最新一次作答結果是答錯」的題目，跳過（未作答）不算複習池的一部分——避免使用者單純那天沒空作答，就被系統誤判成弱點反覆推播；複習題只要重新答對一次就從複習池移除，不做「連續答對 N 次才算精熟」的間隔重複演算法（先求簡單）；複習池題數不夠湊滿比例時，用新題目補滿，不會因此少出題。
3. **作答格式**：只接受回覆選項字母 `A`／`B`／`C`／`D`，不用 LLM 解析口語化的回答；回覆格式不符時，Robinson 需先請使用者重新輸入正確格式，收到有效字母前不進入批改流程。
4. **23:00 視為跳過採靜默處理**：不主動發送「今天當作跳過」的通知，使用者要查才會知道當天沒作答，避免每天晚上又多一則提醒訊息。
5. **彈性排程支援四種語意**：①「今天不想做，改到別天」——單純把當天這批題目挪到指定日期 ②「直接取消今天的」——不補、不挪 ③「某個日期區間的每日出題數量改成 N 題」——只影響該區間，區間外的日期維持原本的全局每日出題數量設定，比照 `budget_overrides`「全局預設值＋特殊區間覆蓋」的既有模式 ④**2026-08-08 追加**「把今天的平攤到其他天（儘量挑離今天近的日期）」——Robinson 需自行計算要分攤到哪幾天、每天各要多幾題，**但計算完不能直接寫入 `certificate_daily_schedule_overrides`**，必須先把「幾月幾號各要多幾題」列出來讓 Robin 確認；Robin 回覆肯定才真的寫入，若 Robin 提出調整意見則依建議重新計算後再次確認，反覆直到 Robin 同意為止。
6. **語意④「平攤」的計算規則**（經 AskUserQuestion 確認）：從明天起算，連續每天 +1 題，直到把今天延期的題目數全部分完為止（例如今天延期 6 題，就是明天到第 6 天各 +1 題；天數隨延期題數變動，題數越多、攤的天數越多，藉此讓單日增幅維持在 +1 這個很小的量級，避免某一天忽然暴增）；計算候選日期時，若剛好命中 Robin 已經手動設定過排程覆蓋的日期，直接跳過該日、往後找下一個沒有覆蓋的日期，不覆寫 Robin 既有的決定。

**理由**：
- 決策 1：符合現況（只有 TOEIC 有實際題庫）與 AGENTS.md「不為假設性未來需求設計」的通用原則。
- 決策 2：把「複習」跟「TOEIC 特有的三軌分配」拆成兩個獨立維度，邏輯更單純，也讓複習機制天然適用所有證照類型，不用等其他證照類型上線才補。
- 決策 3、4：降低實作複雜度與訊息干擾，符合 Robin 明確選擇的方向。
- 決策 5：延續 `budget_overrides`（FR-41a）已經驗證過的「全局預設＋特殊區間覆蓋」設計模式，不用重新發明一套排程資料結構。
- 決策 5 語意④、決策 6：這個語意會一次動到多筆日期的資料，屬於「Robinson 自行運算後的建議」而非使用者明確逐一下的指令，比照 FR-19h「決策執行狀態閉環回饋」與專案內其他 `pending_*` 確認流程的既有慣例，寫入前一定要讓 Robin 看過具體會變動的日期與題數，可修正、可否決，避免自動化計算算錯或跟 Robin 的直覺不符卻已經生效；「+1/天」而非「集中在少數幾天」是因為 Robin 明確要求「儘量離當天近一點的日期」，攤越多天單日增幅越小，越貼近這個意圖；跳過既有覆蓋的日期是因為那天的數字是 Robin 自己刻意設定過的，不應該被系統自動決策覆蓋掉。

**資料表設計**（實際建表 SQL 依 ADR-10 流程提出，**2026-08-08 已建表**，見 `0043`～`0045` migration、`src/schema/db_schema.md`）：
- `certificate_daily_settings`：每個 `user_id`＋`exam_type` 一筆，存 `daily_question_count`／`review_ratio_new`／`review_ratio_review`／`listen_ratio`／`write_ratio`／`vocab_ratio`（後三者僅 TOEIC 填值，其他證照類型固定 `NULL`）
- `certificate_daily_schedule_overrides`：比照 `budget_overrides`，存 `start_date`／`end_date`／`daily_question_count`，查詢當天生效題數時先查是否有覆蓋當天的區間，沒有才 fallback 用 `certificate_daily_settings` 的全局值
- `certificate_daily_assignments`：記錄每天實際推播了哪幾題（兩個可為 NULL 的外鍵＋ CHECK，比照 `answer_logs` 串連軌道一/軌道二），並標記 `is_review`；20:00 提醒／23:00 視為跳過都靠「今天的 assignments 裡有沒有對應的 `answer_logs`」判斷還沒作答的題目

**實作進度（2026-08-08）**：每日 08:00 出題與推播的核心邏輯已完成（`src/bot/certificate_quiz.py`：依 `certificate_daily_schedule_overrides`／`certificate_daily_settings` 解析當天生效題數與比例、依決策 1/2 拆池選題、寫入 `certificate_daily_assignments` 並推播，掛上 `/healthz` 背景排程），對應決策 1、2、5（資料層/查詢邏輯部分）已實作；**決策 3（作答格式驗證）、4（23:00 靜默跳過）、5（彈性排程的四種語意在 Telegram 對話中如何觸發，含語意④「平攤」的計算與確認流程，見決策 6）尚未實作**，留待「作答與批改對話流程」該步驟一併展開（`certificate_daily_settings`／`certificate_daily_schedule_overrides` 目前只能靠直接寫 DB 設定，還沒有對應的 Telegram 指令）。

**實作進度（2026-08-08 追加，全部完成）**：決策 3、4、5、6 全數實作完成。新增 `src/bot/certificate_answer.py`（`get_pending_assignments()` 依 exam_type＋最新一批 assigned_date 判斷待作答題目、`build_question_view()` 依 `certificate_question_id`／`vocab_question_id` 組出題目呈現內容、`grade_answer()`／`record_answer()` 批改並寫入 `answer_logs.assignment_id`、`check_and_push_answer_reminders()` 20:00 提醒）與 `src/bot/certificate_schedule.py`（`apply_move()`／`apply_cancel()`／`apply_range_override()`／`compute_spread_plan()`＋`apply_spread_plan()` 四種語意純邏輯，皆會同步刪除今天已建立但未作答的 `certificate_daily_assignments`，確保排程調整立即生效不用等隔天）；`commands.py` 新增「開始作答」（`start_quiz_answer()`／`handle_quiz_answer_step()`，一次一題、只接受 A/B/C/D）與「調整出題排程」（`start_quiz_schedule_adjust()` 先選 exam_type、`handle_quiz_schedule_intent_step()` 用 LLM 把自由文字分類成 MOVE/CANCEL/RANGE/SPREAD、`handle_quiz_schedule_spread_confirm_step()` 處理 SPREAD 的提案確認/依建議重算迴圈）；`router.py` 註冊「開始作答」／`/start_quiz`、「調整出題排程」／`/adjust_quiz_schedule` 兩個觸發詞與四個新 `pending_*` 狀態分派；`main.py` 新增 `_check_certificate_answer_reminder()` 掛上 `/healthz` 背景排程。新增 `answer_logs.assignment_id`、`users.certificate_answer_reminder_sent_on` 兩個欄位（`0047`／`0048` migration）。

**Step 3.3 剩餘範圍實作進度（2026-08-08 追加，FR-24／FR-29／FR-30 全部完成，見 ADR-19）**：`certificate_goals`／`exam_official_scores` 兩張表沿用 ADR-19 定案當下已建好的 `0041`／`0042` migration，本次不需新增 migration。新增 `src/bot/certificate_exam_scores.py`（FR-30：`record_score()`／`list_scores()`／`distinct_exam_types()`／`format_scores_summary()`）、`src/bot/certificate_stats.py`（FR-29：`compute_daily_period_stats()`／`compute_formal_period_scores()`／對應文字格式化／`known_exam_types()`，供 FR-24 方向建議共用）、`src/bot/certificate_goals.py`（FR-24：`get_goal()`／`set_goal()`〔UPSERT〕／`list_goals()`／`build_advice_prompt()`）。`commands.py` 新增六組對話流程／單次查詢指令：「我要記錄正式成績」／`/log_exam_score`（選 exam_type → 應考日期 → 成績自由文字）、「我的正式成績」／`/my_exam_scores`（單次列表，經 AskUserQuestion 確認不含修改／刪除）、「設定證照目標」／`/set_certificate_goal`（選 exam_type → 目標時間可跳過 → 目標分數可跳過 → 覆蓋寫入）、「我的證照目標」／`/my_certificate_goals`（單次列表）、「給我讀書建議」／`/certificate_advice`（單一候選直接生成、多候選先反問，抓近 30 天成效＋目標組 Prompt 交給 LLM 生成客製化文字）、「查詢我的成效」／`/my_quiz_stats`（FR-29 核心：每輪把使用者已講過的內容全部疊加重新丟給 LLM 解析 exam_type／正式-小考／時間區間／是否比較兩區間，缺哪個就對應反問，都清楚了才真正查詢）。`router.py` 註冊六個觸發詞與七個新 `pending_*` 狀態分派。TDD 全程，三個純邏輯模組皆 100% 覆蓋率；新增 86 個測試（`test_certificate_exam_scores.py`／`test_certificate_stats.py`／`test_certificate_goals.py`／`test_certificate_exam_scores_commands.py`／`test_certificate_goals_commands.py`／`test_certificate_stats_commands.py`／`test_router.py` 新增整合測試），全專案 1185 個測試全過；Phase 3 個人技能成長主線（Step 3.1～3.3）至此全數完成，僅剩 YouTube 模組（Step 3.4）與好友模式（Step 3.5）尚未開始。

**替代方案**：
- 決策 1 替代方案：現在就設計成通用規則（比例由題庫現有結構動態算）——已否決，Robin 選擇先服務實際存在的需求。
- 決策 3 替代方案：用 LLM 解析口語化回答——已否決，選擇題本來就適合固定格式回覆，LLM 解析反而增加不確定性。
- 決策 4 替代方案：發送跳過通知（比照 FR-19h 不靜默精神）——已否決，Robin 認為每天已經有 20:00 提醒，晚上再一則跳過通知太多。

**後果**：
- `certificate_daily_assignments` 需要在每日 08:00 推播當下就寫入完整的「今天推了哪幾題」清單，後續 20:00 提醒／23:00 跳過判斷／複習池計算都依賴這張表，寫入時機與內容正確性很重要。
- 複習池查詢需要「同一題目最新一次作答結果」的邏輯（不是所有歷史記錄都算），查詢複雜度比單純的 `answer_logs` 全表掃描高一些。
- 彈性排程的四種語意（挪動/取消/區間覆蓋/平攤）需要比照 FR-31 待辦事項的自然語言解析模式處理，複雜度不低，且與 `certificate_daily_schedule_overrides` 的覆蓋語意需要一致對應；語意④「平攤」額外需要一個「算出提案 → 呈現給 Robin → 等待確認或依回饋調整 → 確認後才真正寫入多筆覆蓋」的多輪對話狀態機，複雜度高於其他三種語意（其他三種是一次性動作，這個是「提案—確認」迴圈）。

**狀態**：accepted

### ADR-21：YouTube 技術情報改採「LLM 語意判讀 + 多維度指標 + 多主題輪替」，取代原「純 Rule-based 規則式篩選」（supersede ADR-9）

**背景**：Step 3.4 開工前跟 Robin 確認 FR-57～FR-59 細節，發現書面規格跟 Robin 原始想法有落差——ADR-9 當時定案「Rule-based Weight（關鍵字匹配度 + 頻道權重），不用 ML/語意分析」，理由是評估過的替代方案（下載影片＋Gemini 摘要／Embedding 向量推薦）成本過高。但 Robin 澄清他要的其實是「LLM 讀候選影片的標題和說明欄，判斷是否符合我想看的主題」，並非 ADR-9 討論並否決的「下載/轉錄影片內容」，兩者成本量級完全不同——前者只是把 API 已經回傳的文字 metadata 餵給 LLM 做一次分類判斷，跟專案其他模組（例如 FR-29 成效問答）用 LLM 的方式同量級，並不昂貴。同時 Robin 也提出希望額外參考觀看次數／讚數／留言數等數據，以及支援多組主題（不只單一關鍵字）。

**決策**：
1. **LLM 完全取代 Rule-based Weight**：FR-58b 改為把候選影片的標題、說明欄、頻道名稱、發布時間，加上 FR-57 額外用 `videos.list` 補上的觀看次數／讚數／留言數，一次交給 LLM 判斷「是否符合設定的主題」與「這些數據代表的熱度/品質」，直接給出排序，不再另外計算關鍵字比對分數或頻道權重。
2. **只讀文字與統計數字，不下載/轉錄影片本身**：維持 ADR-9 最初「零邊際成本」的精神——LLM 判讀的輸入完全來自 API 回傳的 metadata（標題、說明欄、統計數字），不下載影片、不做語音轉文字、不做影像分析，成本增量僅止於一次輕量 LLM 文字分類呼叫（比照 FR-29 量級），維持整包 Pipeline 的免費資源原則。
3. **支援多組主題，每組各自蒐集候選**：Robin 可設定多組關鍵字/主題（例如「後端架構」「AI Agent」「DevOps」），各組各自呼叫 FR-57 的 `search.list` 取得候選，供 FR-58c 的分配邏輯挑選。
4. **多主題分配採「保底 + 輪替」，不是每次都選同一批熱門主題**：每週固定推薦 3 支——只有 1 組主題時 3 支都出自該組；2 組主題時各保底 1 支、剩餘 1 個名額給分數最高的候選；3 組以上主題時，優先選「距離上次被推播最久」的 3 組各推 1 支（比照 `todos.daily_pushed_on`／`certificate_questions.source_image_filename` 這類既有「記錄上次狀態」去重慣例，新增 `last_recommended_on` 欄位追蹤輪替），確保每個主題長期都有曝光機會。
5. **不刻意排除 Shorts 短影音，時長不設限**（2026-08-08 追加確認）：Robin 澄清 FR-58a 原文「剔除 Shorts」不是他真正在意的規則，他要的單純是「品質高」，不是「時長長」；因此 FR-58a 只保留候選清單內的重複來源去重，時長完全交給 FR-58b 的 LLM 判讀（含觀看數/讚數/留言數等品質訊號）決定要不要選入，不再另外用時長門檻過濾。

**理由**：
- 決策 1、2：Robin 要的判讀方式本來就沒有踩到 ADR-9 否決的成本紅線，屬於書面規格記錄跟原始需求有落差需要修正，不是重新開一次已經否決過的方案。
- 決策 3、4：Robin 明確要多主題支援；「保底 + 輪替」比「永遠只推固定幾個主題」更符合「技術情報訂閱」的初衷——避免冷門但 Robin 有興趣的主題永遠被熱門主題排擠掉。
- 決策 5：「品質」與「時長」是兩件事，用時長一刀切反而可能誤刪真正高品質的短影片、放過低品質的長影片；交給 LLM 綜合標題/說明欄/互動數據判斷更貼近 Robin 實際想要的「品質」定義。
- 配額成本經重新估算（見 FR-59b）：多組主題情境下單次執行約落在 500～600 Units，仍遠低於自訂的每日 1,000 Units 保守上限與 Google 官方每日 10,000 Units 免費額度，此配額純粹是 Google 提供的免費用量上限、非計費機制，不會產生任何費用。

**替代方案**：
- 決策 1 替代方案：LLM 疊加在 Rule-based 之上（先規則式篩一批、LLM 只做最後把關）——已否決，Robin 選擇 LLM 完全取代，判斷邏輯更單純、不用維護兩套排序邏輯。
- 決策 4 替代方案：固定只推「候選分數最高的 3 組」，不考慮輪替——已否決，Robin 對邊界情況授權「你自己處理」，選擇能兼顧公平曝光的輪替設計而非任由少數熱門主題長期壟斷版面。
- 決策 5 替代方案：沿用原本的時長門檻（≤60 秒視為 Shorts 剔除）——已否決，不符合 Robin 實際想要的「品質優先」判斷標準。

**後果**：
- `src/bot/youtube.py`（暫定模組名稱）的 Prompt 設計需要把「文字判讀」與「數據判讀」講清楚給 LLM，避免 LLM 誤以為要點開連結看影片本身。
- 需新增主題設定資料表（暫定 `youtube_topics`：`user_id`／`topic`／`last_recommended_on`，供多主題與輪替邏輯查詢），供 Robin 用指令新增/查詢/刪除主題；欄位與指令細節於 Step 3.4 正式開工、依 ADR-10 流程提出建表 SQL 時定案。
- FR-57 新增一次 `videos.list` 呼叫（查統計數字），Pipeline 從單一 API 呼叫變成「`search.list`（每主題一次）+ `videos.list`（合併查詢候選統計）」兩階段，程式複雜度略增但成本仍低廉。
- ADR-9 的原始三層規則式篩選設計正式作廢，本 ADR 生效後 Step 3.4 依此設計實作，不再需要另外維護 Rule-based Weight 的評分程式碼。
- 決策 5 讓實作更單純：`videos.list` 回傳的 `contentDetails.duration`（ISO 8601 時長字串）不需要解析，FR-58a 只剩「候選清單內 `video_id` 去重」這個簡單邏輯。

**狀態**：accepted

### ADR-22：Step 3.5（好友模式）規格定案——心情趨勢改文字摘要、範圍限被動模式、資料來源動態涵蓋所有已使用模組

**背景**：FR-51／FR-52 原始規格過於簡略（僅一行文字），開工前 Robin 要求先聽 Claude 對這個功能的設計想法再定案，經討論並用 AskUserQuestion 確認三個關鍵決策：① FR-51「心情趨勢圖」跟 FR-44／FR-29 既有「圖表統一交給 Phase 4 Mobile App」的架構決策是否衝突、如何處理 ② Step 3.5 這次要做到「僅被動模式（使用者主動觸發）」還是連「主動關懷推播」也一起做 ③ 好友聊天時要讀哪些模組的近期紀錄當素材——固定清單（僅心情/待辦/體態/記帳）或動態涵蓋該使用者所有實際使用中的模組（含 Robin 專屬模組）。

**決策**：
1. **FR-51 改為文字／emoji 摘要，不做圖片圖表**：比照 FR-44／FR-29 既有慣例，圖表視覺化統一留給 Phase 4 Mobile App（FR-64），之後擴充範圍再涵蓋 `mood_journals`；本次只在好友聊天回覆中用文字/emoji 呈現趨勢。
2. **Step 3.5 這次只做被動模式**：使用者主動觸發（「陪我聊聊」／`/friend_chat`）才生成陪伴對話，不做排程主動關懷推播；主動關懷（例如偵測連續多日心情低落主動問候）留待未來視實際使用回饋另開 Step。
3. **資料來源動態涵蓋該使用者所有已開啟且近期有資料的模組，不寫死固定清單**：每次觸發時逐一檢查該使用者的 `feature_toggles` 開啟狀態，開啟且該模組近期（預設近 7 天）有資料才納入 Prompt 素材；因此 Robin 觸發時可能包含技術情報／證照準備等僅 Robin 可用模組的近況，其他家人觸發時則只會看到自己有用到的模組（例如心情小記、待辦、體態、記帳），同一份程式邏輯自然適應不同使用者，不需要為「一般家人」與「Robin」寫兩套判斷邏輯。

**理由**：
- 決策 1：延續專案一貫的「圖表統一在 App 呈現、Telegram 端只做文字摘要」架構原則（FR-44、FR-29 皆同），避免同一份 `mood_journals` 資料在 Telegram 與未來 App 各自維護一套視覺化邏輯。
- 決策 2：先驗證「被動陪伴聊天」這個核心價值，範圍小、風險低；主動關懷需要額外定義「異常訊號判斷規則」與「推播頻率」，複雜度更高，延續專案一貫「先求穩、範圍蔓延風險留給下一個 Step」的慣例（比照 Step 3.2「先只做建題庫」）。
- 決策 3：「所有用到的功能模組」意味著好友模式的價值取決於使用者實際使用了哪些功能，寫死清單會讓 Robin 聊天時漏掉技術情報/證照進度這些他實際在乎的內容；動態判斷「這個使用者這個模組開了嗎、有資料嗎」比為每個使用者角色（Robin vs 家人）各寫一套模組清單更簡單，未來新增模組時也不需要回頭改好友模式的白名單。

**替代方案**：
- 決策 1 替代方案：現在就用繪圖套件或 LLM 生成圖片圖表——已否決，會產生跟未來 App 化圖表不一致的兩套邏輯，非本次 Robin 選擇的方向。
- 決策 2 替代方案：被動＋主動一起做——已否決，Robin 選擇先做被動模式，主動關懷的判斷規則需要更多討論，留待之後。
- 決策 3 替代方案：固定清單（僅心情/待辦/體態/記帳，排除 Robin 專屬模組）——已否決，Robin 選擇「所有用到的模組」，避免漏掉他自己實際在意的技術情報/證照進度。

**後果**：
- 好友聊天的 Prompt 組裝邏輯需要逐一呼叫各模組既有的「近期資料查詢」函式（例如 `mood.list_mood_journals()`、`body` 的體重/運動/飲食查詢、`finance` 的月度交易、`todo` 的完成狀況、`certificate_stats.compute_daily_period_stats()` 等），複用既有函式而非重新開發資料存取層；哪些模組「查無資料」就自然跳過，不特別提及。
- 「近期」的時間窗口這次先訂為 7 天（比照日常陪伴聊天的即時感，跟 FR-24 方向建議用的 30 天「深度分析」用途不同），純粹是程式常數，之後 Robin 覺得太短/太長可以再調整，不需要動資料表。
- 觸發詞「陪我聊聊」／`/friend_chat` 只做單輪生成完整回覆，不需要新增 `pending_*` 對話狀態機；使用者接續聊天視為一般聊天，不特別維持「好友模式」狀態，之後若要做主動關懷才需要新增排程與去重欄位。
- 不需要新增資料表；`friend_mode` 功能開關已存在於 `templates.FEATURE_LIST`（`owner_only=False`），沿用即可。

**狀態**：accepted

### ADR-23：`language`（語言學習）功能規劃暫時擱置，不排入目前 Roadmap

**背景**：2026-08-08 Robin 詢問 Phase 4 之後的開發項目時，Claude 盤點發現功能開關清單裡的 `language`（語言學習：英文口說練習、其他語言學習）自 2026-08-07 `skill_growth` 拆分三個開關（`tech_intel`／`certificate`／`language`）以來，只建立了開關本身，從未展開任何功能性需求（FR），也沒有排進 Phase 0～4 任何一個 Step。

**決策**：`language` 功能規劃正式擱置，不排入目前 Roadmap（Phase 0～4）。開關本身維持存在於 `feature_toggles`／`templates.FEATURE_LIST`，但功能上無作用（開/關都不影響任何實際行為，因為根本沒有對應功能）；何時展開、展開成什麼樣的內容，留待 Phase 4（求職模組＋Mobile App）全部完成後再另行討論定案。

**理由**：Robin 明確表示「language 這個可以先擱置」，優先完成已經排定的 Phase 4；比起花時間展開一個還沒想清楚的新功能，先把既有 Roadmap 走完更符合專案一貫「先求穩、範圍蔓延風險留給下一個階段」的慣例。

**替代方案**：現在就展開 `language` 功能規劃、插入 Phase 4 之前或之後——已否決，Robin 選擇先擱置。

**後果**：往後任何「清點剩餘工作」的回答都不該把 `language` 算進 Phase 4 的範圍內；未來真的要展開時，需要重新走一次完整的 SDD 流程（先確認需求細節、AskUserQuestion 定案設計，再排進 Roadmap）。此決議純屬規劃層級調整，未異動任何程式碼或資料表。

**狀態**：accepted

### ADR-24：Step 4.1（104 職缺爬蟲）開工前四項設計決策

**背景**：Step 4.1 開工前，Claude 盤點 FR-33～FR-36 原始規格，發現 FR-35「Gemini 以 Web Search 補充公司背景」與已經拿掉的 Google Search grounding（chat-core SPEC.md ADR-5）直接衝突，技術上走不通；同時 FR-33（搜尋條件數量）、FR-34a（列表 API 是否已含完整職缺內容）、求職模組使用範圍三點也需要在動工前定案。經與 Robin 多輪討論確認四項決策。

**決策**：

1. **FR-35 公司背景改採「Email 協作」機制，不用 Gemini Web Search**：每週爬完職缺後，Robinson 找出資料庫裡還沒有背景資料的新公司，先寫入資料庫（`background` 留空），組成 CSV（104公司ID／公司全名／地區／產業類型／背景）用 Email 寄給 Robin（自己的 `GMAIL_USER` 帳號自寄自收），寄信成功後私訊 Telegram 告知；Robin 自行上網查完背景、把 CSV 填好上傳到既有共用 Google Drive 資料夾（沿用 `GDRIVE_FOLDER_ID`），並在 Telegram 說「已上傳 XXX.csv」；Robinson 偵測到這句話後去 Drive 抓檔、解析、把背景欄位回填資料庫。當週若沒有任何新公司（都已有背景資料），整段流程完全跳過，不寄信不通知。
2. **求職模組僅 Robin 一人可用**：不支援其他家人各自求職，`templates.FEATURE_LIST` 的 `job_search` 開關屬性於 Step 4.1 實作時改為 `owner_only=True`，本節標題同步加註「僅 Robin 可用」。
3. **FR-33 允許同時存多組搜尋條件**：不是「一組、重新設定即覆蓋」的既有慣例（比照記帳預算／證照目標），而是可以同時儲存多組關鍵字/地區/薪資/產業別條件，各自獨立生效，每週排程對每組條件各自送出查詢。
4. **FR-34a 深度爬取先採兩階段架構**：沒有現成的 104 API 實測資料可依循，先假設列表 API（`/jobs/search/list`）只回傳摘要欄位，保守設計成「列表 API 抓清單 → 對每筆職缺 ID 再打一次詳情頁補齊完整內容/應徵條件/福利」；FR-34c 的 2～4 秒隨機延遲同時套用在列表分頁與詳情頁請求之間。待 Robin 之後提供實際 API 回應格式，若列表 API 其實已經夠完整，再簡化拿掉詳情頁請求。

**理由**：
- 決策 1：完全比照專案既有的「知識庫查無答案時，誠實不知道＋請使用者查完提供」模式（chat-core FR-4、ADR-5），把「不知道」換成「查公司背景」，同樣不需要任何外部 Search API、零成本零新技術風險；Email＋Drive 上傳／下載也是專案既有子模組（`submodules/email`、`submodules/gdrive`）已經驗證過的管道，只需擴充 `submodules/email` 的附件寄送能力。
- 決策 2：Robin 明確表示求職模組使用範圍先開給自己就好，架構單純很多，不需要處理多使用者各自履歷/條件/評分並行的複雜度。
- 決策 3：Robin 明確要求允許同時存多組條件（例如同時想找兩種不同類型的職缺），這跟記帳預算/證照目標「一人一份設定」的性質不同——求職條件本質上就可能同時有多個方向。
- 決策 4：sandbox 連不到 104 的網路，無法實測列表 API 實際回傳欄位，Robin 目前也沒有現成的 API 規格文件；「深入爬取」這個字面要求暗示列表 API 可能不夠，保守假設、之後視實測結果調整，比一開始就賭列表 API 已經夠用、上線後才發現內容缺漏更穩妥。

**替代方案**：
- 決策 1 替代方案：開通 Gemini grounding 計費額度、或串接第三方 Search API（如 SerpAPI）——已否決，會產生實際費用，違反 NFR-1「所有服務一律使用免費方案」；直接拿掉公司背景這個功能——Robin 選擇保留但用人力協作的方式取代自動化搜尋。
- 決策 2 替代方案：一開始就設計成多使用者可用——已否決，Robin 選擇先簡化，之後真有需求再擴充（比照專案一貫「先求穩」慣例）。
- 決策 4 替代方案：先當作列表 API 已經足夠、只做單階段——已否決，Robin 沒有反對兩階段的保守設計，且「深入爬取」字面上就暗示可能需要。

**後果**：
- `submodules/email` 需要新增支援附件的寄信方法（例如 `send_text_with_attachment()`），沿用標準函式庫 `email.mime`，不新增第三方套件。
- 需要新增「已上傳 {檔名}」這種帶動態檔名的觸發詞規則（比照 `router._CLEAN_TARGET_DIALOG_PATTERN` 用 regex 擷取參數的既有慣例）。
- 需要新增公司資料表（暫定 `job_companies`：104公司ID／公司全名／地區／產業類型／背景／建立時間）與搜尋條件表（暫定 `job_search_criteria`：支援多組，`user_id`／關鍵字／地區／薪資範圍／產業別），實際欄位與 migration SQL 於 Step 4.1 正式開工、依 ADR-10 流程提出時定案。
- CSV 解析採標準函式庫 `csv` module，不裝第三方套件（比照 `submodules/newsfeed` 用標準函式庫解析 RSS 而不裝 `feedparser` 的既有慣例）。
- `job_search` 開關屬性變更（`owner_only=True`）需要同步更新 `templates.py`／相關測試斷言。

**狀態**：accepted

### ADR-25：`skill_growth_digests` 改為「一天多筆、一筆一個來源管道」正規化設計（取代原單筆合併 `summary_text`）

**背景**：Step 3.1 上線後，Robin 回報實際推播內容有兩個問題：①三個來源（TLDR 電子報／IThome／TechCrunch）合併成單一 `summary_text` 欄位，完全無法分辨當天到底是哪個來源沒抓到內容、還是收集本身出了問題，例如 TLDR 電子報信箱掛掉，Robin 從推播訊息看不出來；②推播訊息把每則新聞/電子報的原文整理成完整條列文章，內容太長，Robin 只需要三行式的重點結論。

**決策**：
1. `skill_growth_digests` 新增 `source` 欄位（值為 `tldr`／`ithome`／`techcrunch`），約束改為 `UNIQUE (digest_date, source)`，一天最多寫入三筆，一筆對應一個來源；`summary_text` 保留，但只存單一來源當天的精簡總結（≤100 字，只給結論，不條列原文）。收集階段（23:00）三個來源各自獨立呼叫 Gemini、各自寫入一筆，任一來源當天沒有內容則寫入固定文字「今日無內容」而不是 `NULL`，藉此跟「這個 source 完全沒有列」（收集當下服務不可用）區分開來。
2. 推播訊息格式改為 Robin 指定的三行式：「1.TLDR 電子報總結分享：……」「2.ithome新聞總結分享：……」「3.TechCrunch新聞總結分享：……」，不再輸出原文條列內容。
3. 舊表直接 `DROP TABLE` 砍掉重建（見 `src/migrations/0052_recreate_skill_growth_digests_per_source.sql`），不做資料搬遷；Robin 確認舊表當時僅有 1 筆資料，重建成本可忽略。

**理由**：
- 決策 1：Claude 原提案是新增 3 個獨立欄位（`tldr_summary`／`ithome_summary`／`techcrunch_summary`）取代 `summary_text`，被 Robin 否決——理由是未來每新增一個來源就要 `ALTER TABLE` 加欄位，擴充性差；改成 `source` 欄位＋正規化多筆列的設計，新增來源只需要多寫一個 `source` 值，完全不用改 schema，也更貼合 Robin 一貫要求的「可擴充」原則。
- 決策 2：Robin 明確表示「不需要放那麼多字給我，我只需要技術總結」，並提供了具體的三行式格式範例。
- 決策 3：只有 1 筆既有資料，保留舊資料（例如標記 `source = NULL` 當作 legacy 列）的複雜度完全不值得，Robin 直接授權砍掉重建。

**替代方案**：
- 3 個獨立欄位（`tldr_summary`／`ithome_summary`／`techcrunch_summary`）——已否決，見決策 1 理由，Robin 認為擴充性差。
- 就地 `ALTER TABLE` 加 `source` 欄位、保留舊資料為 `source = NULL` 的 legacy 列——Claude 原提案，Robin 認為多此一舉（只有 1 筆資料），選擇直接砍掉重建。

**後果**：
- `src/bot/skill_growth.py` 全面重寫：`_get_digest()` → `_get_digests_for_date()`（回傳 list）；`build_summary_text()`／`_build_summary_prompt()` → `summarize_source()`／`_build_source_prompt()`（單一來源獨立摘要）；`collect_and_store_daily_digest()` 改為寫入三筆；`check_and_push_daily_digest()` 改為讀取三筆、用新增的 `_format_digest_message()` 組出三行式訊息，`source IS NULL` 的去重標記列邏輯沿用「完全查無資料」情境。
- 三個來源各自獨立呼叫 Gemini（一次收集最多 3 次 API 呼叫，取代原本 1 次），仍在免費額度內（NFR-1），但需留意 Gemini 免費層級的 QPS/RPM 限制，未來若加入更多來源要留意額度。
- `tests/bot/test_skill_growth.py` 全面重寫以配合新 schema 與函式簽名，重跑後 `src/bot/skill_growth.py` 維持 100% 覆蓋率。

**狀態**：accepted

### ADR-26：Step 4.2（契合度評分與技能缺口分析）開工前設計決策，並修正 FR-36 歸屬

**背景**：Step 4.2 開工前，Robin 要求 Claude 先把所有需要確認的問題一次列出。Claude 盤點 FR-36～FR-38 發現：① Roadmap 誤把「職缺內容解析」標成 FR-36（FR-36 實際是履歷記錄，職缺內容解析其實是 FR-34a），且 FR-56f 情境範例早已示範履歷收集是跟 FR-33 搜尋條件設定同一輪對話完成的，FR-36 應歸屬 Step 4.1 而非 Step 4.2 ② FR-37 契合度評分的比對維度（應徵人數、更新時間、年資、期望薪資）需要先確認哪些要開結構化欄位、哪些要等 Step 4.1 實測 104 API 才能知道是否可行 ③ FR-38 技能缺口分析的顆粒度、排名機制、交付方式都需要定案。經與 Robin 兩輪問答（Claude 先提出第一輪問題，Robin 回覆後 Claude 再收斂剩餘的 5 個關鍵問題，Robin 逐一確認）後，全部設計定案。

**決策**：

1. **FR-36 歸屬 Step 4.1**，與 FR-33（搜尋條件）同一輪對話流程收集，不歸屬 Step 4.2；FR-36 新增兩個結構化欄位：年資（`years_of_experience`，浮點數）、期望薪資下限／上限（`expected_salary_min`／`expected_salary_max`，數字），從原本的自由文字段落拆出來，不再靠 LLM 從自由文字猜測，比對更精準。
2. **FR-38 技能缺口分析以「104 職缺 ID」為單位**，不是以公司為單位——同一間公司底下可能有好幾個職缺、各自需要的技能不一樣，用公司當 key 會混在一起分不清楚。
3. **「應徵人數」「更新時間」兩項評分維度視 Step 4.1 實測結果而定**：Claude 先試著從 104 API／頁面擷取，若確實抓不到，評分時直接略過這兩個維度，不強行湊資料；不因此卡住整個 FR-37 評分邏輯。
4. **FR-37 契合度評分僅計算「所屬公司背景資料已回填完成」的職缺**（見 FR-35）；背景仍空白的職缺本次評分跳過，待未來背景補齊後於下次排程自然被納入，不會因為某幾間公司背景遲遲沒填而卡住整批評分或整個週排程。
5. **新增 `is_unliked`／`is_closed` 兩個欄位到職缺資料表**：`is_unliked` 由 Robin 透過 FR-38 的 Excel 人工標記（每週收到推薦後實際看過、不喜歡的標記 1）；`is_closed` 代表職缺是否已關閉，優先嘗試從 104 API／頁面自動判斷（Step 4.1 實測），若可行則系統自動維護、FR-38b 的 Excel 不會出現「是否關閉」這欄；若不可行，才保留這欄讓 Robin 到 104 網站人工確認後填寫。**FR-38a「前 30 名」排名時一律先排除 `is_unliked = TRUE` 與 `is_closed = TRUE` 的職缺**，隨著資料庫累積職缺越來越多，排除這兩類後候選池仍可控。**（2026-08-09 追加確認）**：Robin 於 Step 4.1 完工後實測 104 API，確認列表／詳情回應皆含 `jobSwitch`／`switch` 欄位可自動判斷，走「自動判斷」這條路線，已於 migration `0057` 新增 `job_postings.is_closed`（`is_unliked` 仍待 Step 4.2 開工時另行新增，維持人工標記）。
6. **FR-38a「前 30 名」採雙重排名機制**：① 全庫排名（資料庫所有已評分、未被排除的職缺）② 本週新職缺排名（僅本次排程新爬到的職缺）；FR-38b 的 Excel 兩張工作表「所有職缺推薦」「最新職缺推薦」分別對應這兩種排名，每週固定一起產出、一起寄送，不因為某一種排名本週沒有新內容就跳過寄信。
7. **FR-39（應徵成效追蹤，「ID=XXX 職缺已應徵」等 Telegram 語句）維持 Step 4.3 範圍**，本次僅記錄需求（Robin 已預告會用的三種狀態語句），細部設計（資料表欄位、狀態機、觸發語句 regex）留待 Step 4.3 開工時才展開，不在 Step 4.2 一併定案。

**理由**：
- 決策 1：履歷資料是契合度評分（FR-37）的必要輸入，FR-56f 範例已經證明履歷收集在使用者體驗上跟搜尋條件設定是同一輪對話，沒有理由拆到不同 Step；且讓 Step 4.2 開工時履歷資料已經存在，不需要額外處理「履歷還沒建立」的邊界情況。
- 決策 2：Robin 明確選擇「104職缺ID比較正確」，同公司多職缺技能需求本來就可能不同，用職缺當 key 才精準對應到 FR-38 原文「針對前 30 名職缺整理技能缺口」的字面意思。
- 決策 3：Robin 同意「先測試看看，如果不行再提出來討論」，跟 Step 4.1 的 FR-34a／ADR-24 決策 4「先保守假設、待實測調整」是同一種務實做法，不需要在完全沒有實測資料的情況下預先鎖死設計。
- 決策 4：Robin 明確表示「契合度評分確實要等公司背景填完才算」；用「只處理已有背景的職缺、背景空白的職缺留到下次」取代「整批等到全部填完才一次算」，是為了避免評分排程被少數遲填的公司卡住，同時仍滿足「背景填完才算」的原意。
- 決策 5：`is_unliked` 是 Robin 的主觀偏好判斷，沒有自動化替代方案，只能人工透過 Excel 回填；`is_closed` 優先嘗試自動化（減少 Robin 的人工負擔），退而求其次才用 FR-38b／FR-38e 比照 FR-35 既有的人工協作模式處理，這是專案一貫「能自動化就自動化、不行才用人力協作」的原則（同樣邏輯已用在 FR-35 公司背景）。
- 決策 6：Robin 明確要「兩個機制」——全庫一份看长期累積的推薦名單、本週新職缺一份看「這次新增的有什麼」，兩者用途不同（全庫版本可能包含幾週前還沒處理但仍然优质的職缺，本週新職缺版本讓 Robin 快速掌握「這次爬蟲新增了什麼」），不互相取代。
- 決策 7：FR-39／FR-40 屬於 Step 4.3 既定範圍，Robin 在這輪回覆中只是預告會用的語句格式、明確表示「細部設計留待 Step 4.3 開工時再展開即可」，遵守專案一貫「一次只定案一個 Step 的範圍，不過早展開後續 Step 細節」的節奏。

**替代方案**：
- 決策 4 替代方案：改成「事件驅動」——公司背景一填完（FR-35e 執行完成）就立刻觸發該公司底下職缺的評分，不用等到下次固定排程——已考慮但未採用，因為會多一套事件觸發機制，複雜度增加，且與專案目前全部排程都是「固定時間點、借用 `/healthz` 頻率」的既有慣例不一致；先採用「固定每週排程＋範圍篩選」的簡單做法，之後如果 Robin 覺得等待時間太長再改。
- 決策 6 替代方案：只做「本週新職缺」單一排名，不做全庫排名——已否決，Robin 明確要兩種機制併存。

**後果**：
- Step 4.1 開工時，除了原訂的 `job_companies`／`job_search_criteria` 表，還需要新增職缺本身的資料表（暫定 `job_postings`：104公司ID／104職缺ID／職缺名稱／地區／連結／薪資範圍／內容／要求年資／應徵人數〔若可取得〕／更新時間〔若可取得〕／首次入庫時間／`is_unliked`／`is_closed`／`score`／`rank`／`recommend_reason`／`skill_gap_note` 等），以及 `users` 或獨立 `job_search_profile` 表新增 `years_of_experience`／`expected_salary_min`／`expected_salary_max` 三欄；實際欄位與 migration SQL 於 Step 4.1／4.2 正式開工時依 ADR-10 流程逐一提出核准。
- FR-38b 的 Excel 需要用 `openpyxl`（比照既有 xlsx 技能慣例）產生三張工作表，`submodules/email` 沿用 ADR-24 已規劃的附件寄送能力（一套機制同時服務 FR-35b 與 FR-38b 兩種附件）。
- FR-38e 的回填流程需要能依副檔名／檔名關鍵字正確分流到「公司背景 CSV」或「職缺推薦 Excel」兩條獨立 pipeline，觸發語句 regex 設計需要能同時涵蓋兩種檔名樣式。
- `is_closed` 欄位是否出現在 Excel 屬於執行期動態決定（依 Step 4.1 實測結果），需要在程式邏輯裡做條件判斷，不是寫死的固定欄位清單。

**狀態**：accepted

### ADR-27：Step 4.3（應徵成效追蹤）開工前設計決策

**背景**：Step 4.2 完工後，Robin 詢問「4.3 有需要確認的部分嗎」。FR-39／FR-40 原本只記錄 Robin 預告會用的三種狀態語句（已應徵／已獲得面試／已拿到 Offer），細部設計完全空白，開工前有幾個問題必須先確認：Robin 打「ID=XXX」語句時 ID 從哪來（FR-38b 的推薦 Excel 目前沒有列出 104 職缺 ID）、狀態機是否要嚴格照順序推進、FR-40 提到的「並納入評分考量」要不要真的把 LinkedIn／Cake 等外部管道職缺送進 Gemini 評分、應徵狀態要用什麼資料結構存。經 AskUserQuestion 兩輪確認（第一輪確認 ID 來源／狀態機／是否評分／歷程表 4 題，第二輪針對「外部職缺也要評分」這個選擇追問資料結構要怎麼設計）大致定案，Claude 當下提案「外部管道職缺用獨立新表儲存，不借用既有 `job_postings`／`job_companies`」。**Robin 隨後推翻這個提案**，指出職缺資料應該放同一張表、用 `source` 欄位區分來源（`104`／`linkedin`／`cake`…），理由是「這樣設計才有擴充性」；Claude 認同這個修正並指出一個額外好處：統一表之後外部職缺可以直接沿用整套 FR-37／FR-38 評分與排名邏輯，不需要另外寫一套獨立批次流程。改動後追加確認一輪：兩表合一後，外部職缺會自然跟 104 職缺一起被排進每週推薦 Excel 前 30 名（而非分開處理），Robin 確認「可以，混在一起排」。

**決策**：

1. **推薦 Excel 兩張推薦表新增「104職缺ID」欄位**（FR-38b 原本只有「技能缺口」工作表列出 104 職缺 ID），Robin 直接從 Excel 抄 ID 打「ID=XXX」語句。
2. **應徵狀態任何時候都能直接設定，不強制順序**；除 Robin 預告的三種狀態外，新增第四種結束狀態「未錄取／已婉拒」。
3. **FR-40 外部管道（LinkedIn、Cake 等）職缺也要納入 Gemini 契合度評分**，不是純記錄用途。
4. **應徵狀態存成獨立歷程表**（非直接覆蓋 `job_postings` 單一欄位），每次狀態變更新增一筆紀錄＋時間戳，保留完整歷程供未來統計成效指標；不區分「104 職缺」或「外部職缺」兩種關聯，統一都指向 `job_postings.job_id_104`（見決策 5）。
5. **外部管道職缺與 104 職缺共用同一張 `job_postings`／`job_companies`，新增 `source` 欄位區分來源**（`104`／`linkedin`／`cake`…，預設 `104`），取代 Claude 原提案的「獨立新表」設計。外部職缺沒有 104 官方 ID，新增時由系統配發合成識別碼（例如 `EXT-3`）寫入既有的 `job_id_104`／`company_id_104` 欄位——欄位名稱維持不變，只是語意從「104 官方 ID」放寬為「不分來源的唯一識別碼」，加上 `COMMENT ON COLUMN` 註解說明，不做重新命名的破壞性 migration。公司背景、職缺內容等既有欄位直接沿用，Robin 新增外部職缺時手動填入。
6. **外部職缺與 104 職缺一起參與 FR-38a 每週排名機制**，會一起出現在同一份「所有職缺推薦」／「最新職缺推薦」Excel 前 30 名裡，不特別區分來源、不另外做「評分但不進排行榜」的排除邏輯。

**理由**：
- 決策 1：不加這欄，Robin 每次都要跳去「技能缺口」表對照 ID，多一道不必要的查找步驟。
- 決策 2：真實求職情境中公司不一定照 Robin 預期的順序發通知（例如沒有正式「面試邀約」訊息就直接約時間面試），嚴格線性狀態機會逼 Robin 補打不存在的中間狀態；新增「未錄取／已婉拒」讓成效統計（例如「應徵 20 家、幾家有面試」）更完整，不只有「進行中」的三種正向狀態。
- 決策 3：FR-40 原文明確寫「並納入評分考量」，不是單純記錄用途；Robin 選擇照字面意思落實。
- 決策 4：單一狀態欄位只能看到「目前狀態」，看不到「哪天投遞、哪天收到面試邀約」的時間軸，之後想算「平均幾天收到回覆」之類的指標會沒有資料可用；獨立歷程表一次到位，不用等以後真的要做統計時回頭補資料結構。
- 決策 5：Robin 明確指出獨立表設計擴充性差——之後每加一個新求職平台（例如 1111、Yourator）都要考慮是否要再開一張表；用 `source` 欄位統一是更常見、更具擴充性的正規化做法。這個改動還有一個 Claude 原提案沒想到的附帶好處：既有 FR-37（`list_scorable_jobs()`／`score_jobs()`／`apply_scores()`）與 FR-38a（`build_ranked_jobs()`）等邏輯都是直接操作 `job_postings`／`job_companies` 資料列、不區分來源，外部職缺只要符合同樣的資料形狀（`background` 已填、`content` 已填）就會自動被納入既有評分／排名流程，不需要為 FR-40b 另外開發一套獨立批次評分機制。
- 決策 6：Robin 明確選擇「混在一起排」，且這與決策 3「外部職缺也要納入評分考量」的原意一致——如果評分了卻不讓它有機會進入推薦名單，那評分的意義就打折扣；統一到同一份排行榜也讓 Robin 每週只需要看一份「目前最推薦的 30 個職缺」，不用分頭看兩份名單。

**替代方案**：
- 決策 5 替代方案：外部管道職缺用獨立新表儲存（Claude 原提案，理由是避免既有 104 專屬語意的欄位被挪作他用）——已考慮但被 Robin 否決，理由見上方決策 5。
- 決策 6 替代方案：外部職缺評分但不進 FR-38a 排行榜，需要另外查詢方式看分數——已考慮但未採用，Robin 明確選擇混在一起排。

**後果**：
- Step 4.3 開工時：`job_postings`／`job_companies` 各自新增 `source` 欄位（`TEXT NOT NULL DEFAULT '104'`），並新增應徵歷程表（狀態＋時間戳，關聯 `job_postings.job_id_104`），實際欄位與 migration SQL 依 ADR-10 流程於開工時提出核准。
- 觸發語句 regex 需要能解析「ID=<job_id_104 或合成識別碼>」，兩者統一走同一個查詢路徑（不用像原本獨立表設計那樣區分兩種命名空間查兩張表）。
- FR-38b 的 Excel 需要新增「104職缺ID」欄位到兩張推薦工作表；表頭文字沿用「104職缺ID」（既有慣例），但實際值可能是合成識別碼，不強求所有值都是真正的 104 官方 ID。
- 現有 FR-34（爬蟲 upsert）邏輯只處理 `source = '104'` 的資料列，新增外部職缺的對話流程需要確保寫入時正確標記 `source`，避免爬蟲下次執行時誤動到外部職缺資料（`crawl_and_upsert_jobs()`／`upsert_job_posting()` 的 `WHERE` 條件需要一併檢視，留待呈現實作計畫時確認）。
- `is_closed` 對外部職缺沒有自動判斷依據（沒有 104 API 可以查詢開放/關閉狀態），預設 `FALSE`，若之後真的關閉需要 Robin 手動處理，細節留待呈現實作計畫時定案。

**狀態**：accepted

## 實作計畫

> 分期原則見 ADR-4；每個 Phase 完成後才進入下一個 Phase 的詳細 spec 與 TDD 循環。本 spec 僅列到模組層級，各模組進入實作前應個別建立 `docs/specs/<feature-slug>/SPEC.md` 展開 API 設計與資料表結構。

### Phase 0：專案基礎建設

- [ ] Step 0.1：確認並補完專案目錄結構（`docs/`、`.env` 管理、`.gitignore`）
- [x] Step 0.1a：建立 `submodules/` 共用子模組骨架，統一四檔案結構（`llm/`、`cloudsql/`、`telegram/`，各自僅含 `client.py`/`README.md`/`requirements.txt`/`.env.example`），詳見 [docs/specs/submodules-core/SPEC.md](../submodules-core/SPEC.md)
- [x] Step 0.1b：建立 `src/schema/` 骨架（`db_schema.md`、`api_schema.md`），訂定記錄格式與 ADR-10 審核流程
- [ ] Step 0.2：申請並串接外部服務金鑰（Telegram Bot Token、Neon 連線、Google Service Account、Gemini x2、Gmail 應用程式密碼、GitHub Personal Access Token、YouTube Data API Key）
- [x] Step 0.3：`main.py` 提供 keep-alive 健康檢查端點，並部署到 Render —— 已確認上線：`https://life-assistant-bot-yhkm.onrender.com`
- [x] Step 0.4：於 cron-job.org 設定每 10 分鐘呼叫健康檢查端點 —— Robin 已設定完成並確認 API 正常
- [x] Step 0.5a：建立 `src/migrations/` 骨架與 `main.py` 的 migration runner（開機掃描未套用檔案、`schema_migrations` 追蹤表、自動執行），依 ADR-11
- [x] Step 0.5：Neon 資料庫初始化 —— 第一批 5 張表（`users`／`invite_codes`／`knowledge_base`／`conversation_logs`／`feature_toggles`）已經 Robin 審核核准，migration 檔案已 commit+push（`776802f..e440b7c`），Robin 已於 Render 部署 log 確認 5 筆 migration 全數套用成功，記錄於 `src/schema/db_schema.md`；後續其他模組（記帳、體態、TOEIC、YouTube、客訴等）的資料表待對應 Phase 展開時比照本流程逐一提案

### Phase 1（MVP）：核心平台 + 待辦事項 + 心情小記

- [x] Step 1.1：通關密碼驗證流程 + Owner 專屬引導式設定對話流 + 綁定成功歡迎訊息 + `/rule`、`/function` 內建指令（FR-5、FR-6～FR-6d、FR-55、FR-56，見 ADR-8、附錄 A/B；FR-7／FR-8 涉及排程調整權限，留待對應功能模組實作時處理）。獨立展開為 [docs/specs/platform-auth/SPEC.md](../platform-auth/SPEC.md)，49 個測試全過、`src/bot/` 覆蓋率 100%；**2026-07-30 更新**：`/function`（FR-56）因人格化語氣與按需展開的新規則（FR-56a～FR-56d），MVP 版本待 Step 1.3 整合 Gemini 後需重新實作，詳見 Step 1.3a
- [x] Step 1.2：功能開關系統（FR-2、FR-2a），展開為獨立 [docs/specs/feature-toggles/SPEC.md](../feature-toggles/SPEC.md)；`/my_toggles`（自管）、`/set_toggle`（Owner 代管）已完成 TDD 實作；實際攔截對話的邏輯待 Step 1.3 生效
- [x] Step 1.3：Gemini 對話核心，整合四類知識庫與資安隔離（FR-9～FR-12）、人格化語氣（FR-56c），展開為獨立 [docs/specs/chat-core/SPEC.md](../chat-core/SPEC.md)；查無答案時單次呼叫誠實回報不知道，建議使用者自行查詢後提供答案存入客製知識庫（**2026-07-31 修正**：原本為 Google Search grounding，已移除，見 chat-core SPEC.md ADR-5）；`GEMINI_API_IMAGE_KEY1`/`KEY2`/`GEMINI_API_TEXT_KEY` 三把 Key 依用途分流（ADR-12）留待 Step 1.3b／未來文字生成類功能實際用到時才接上
- [x] Step 1.3a：`/function` 重新實作為「總覽 + 按需深入 + 情境範例」（FR-56、FR-56a～FR-56h），展開為獨立 [docs/specs/chat-core/SPEC.md](../chat-core/SPEC.md) FR-9／ADR-4；取代 Step 1.1 的扁平清單版本；全專案 126 個測試全過、`src/bot/` 覆蓋率 100%
- [x] Step 1.3b：影像辨識基礎流程（FR-17、FR-17a～FR-17c）——先上傳 Google Drive、`Pillow` 壓縮至 1024×1024 內／JPEG 80%、影像雙 Key 隨機辨識（ADR-12、ADR-13）、不確定內容需詢問使用者、非圖片/音檔格式的友善提示；新增 `submodules/gdrive/`、`TelegramClient.get_file_bytes`、`src/bot/image.py`，`webhook.py`/`router.py` 完成整合；全專案 179 個測試全過、`src/bot/`／`submodules/gdrive`／`submodules/telegram`／`submodules/llm` 覆蓋率 100%
- [x] Step 1.4：語音轉文字流程（改用 Groq Whisper，`VOICE_API_KEY`，見 ADR-12）+ 10 分鐘上限 + 15 分鐘內文字修正限制（FR-14、FR-15）+ 語音檔上傳 Google Drive 備份（ADR-13）——新增 `submodules/voice/`（`VoiceClient`，用 `requests` 直打 Groq OpenAI 相容 REST API）、`src/bot/voice.py`（時長/修正窗口檢查、上傳＋轉文字）；轉出來的文字直接比照一般文字訊息呼叫既有 `handle_message()`，不重複指令/對話流程分派邏輯；`src/bot/media.py` 從 `image.py` 抽出共用的 `save_media_upload()`；**追加修正**：初版只處理 `message.voice`（錄音鍵語音訊息），Robin 回報「除了照片和音檔外的檔案格式才無效」才發現漏了 `message.audio`（使用者上傳的音檔，例如 MP3），與 FR-17 原文「僅支援圖片與音檔兩種檔案類型」承諾不符，補上 `webhook._extract_voice()` 同時偵測兩種類型並依 Telegram 回報的 `mime_type` 決定正確的 Drive 副檔名與轉錄請求格式；全專案 262 個測試全過、`src/bot/`／`submodules/llm`／`submodules/voice` 覆蓋率 100%
- [x] Step 1.5：個資偵測與刪除機制，Regex 硬規則 + LLM 語意雙層防線（FR-13、FR-13a～FR-13d），展開為獨立 [docs/specs/privacy-masking/SPEC.md](../privacy-masking/SPEC.md)；新增 `src/bot/privacy.py`，整合進 `chat.handle_chat_message()`（一般聊天文字）與 `image.handle_image_message()`（圖片說明文字），語音因統一轉文字後走 `handle_message()` 天然涵蓋；`/clean-target-dialog` 的搜尋主題刻意排除遮蔽（避免刪除功能失效）；全專案 326 個測試全過、覆蓋率 100%
- [x] Step 1.6（2026-08-02 完成）：基礎錯誤處理層 —— 對外「生病了」/「我康復了」用語、捕獲異常＋完整 Traceback 記錄、私訊 Robin 原始 log（FR-19a、FR-20、FR-21；FR-19b～FR-19i 的 AI 自主診斷、分級降級、重試機制延後至 Phase 2，見 Step 2.4 與 ADR-7）。新增 `src/bot/monitoring.py`（`NeonCapacityMonitor`）、`submodules/cloudsql/client.py` 的 `execute_query()` 逃生口、`commands.handle_recovered()`（`/recovered` Owner 專屬指令）、`webhook.py` 的 `_notify_robin_of_error()`／`_summarize_user_input()`；全專案 352 個測試全過、覆蓋率 100%
- [x] Step 1.7（2026-08-02 完成）：待辦事項模組 —— 自然語言新增（三輪反問：要不要記錄→什麼時候→要不要提前 30 分鐘提醒）、逾期自動標記、查詢清單＋標記完成/取消、每日 08:00 固定推播＋前 30 分鐘提醒（FR-31、FR-31a、FR-32）。新增 `todos` migration、`src/bot/todo.py`（純邏輯）、`chat.py` 的 `_REQUEST_TODO_MARKER`、`commands.py` 五個新 flow 處理函式、`router.py` 整合、`main.py` 的 `_check_todo_pushes()` 借用 `/healthz` 頻率；全專案 391 個測試全過、覆蓋率 100%
- [x] Step 1.8（2026-08-02 完成）：心情小記模組 —— 心情分類選單（固定 6 選一）→ 日記內容 → FR-50 個人成就三選一提示（可跳過），日記內容與個人成就皆套用 FR-13 個資遮蔽（FR-49、FR-50）。新增 `mood_journals` migration、`src/bot/mood.py`（純邏輯，不需要 LLM）、`commands.py` 三個新 flow 處理函式、`router.py` 整合；全專案 409 個測試全過、覆蓋率 100%
- [x] Step 1.9（2026-08-02 完成，Phase 1 全數 Step 完成）：客訴收集模組 —— `/complaint` 固定提問（不經 LLM）→ 客訴內容記錄（套用 FR-13 個資遮蔽）→ Gemini 分析私訊 Robin（刻意的隱私例外，不回傳給提出客訴的使用者本人）（FR-60～FR-63）。新增 `complaints` migration、`src/bot/complaint.py`（純邏輯）、`commands.py` 兩個新 flow 處理函式、`router.py` 整合；全專案 417 個測試全過、覆蓋率 100%

### Phase 2：記帳 + 體態管理 + 重要通知 + 系統韌性與自主診斷治理

- [x] Step 2.1：記帳模組（FR-41～FR-44，**2026-08-04 完成**）
- [x] Step 2.2：體態管理模組（FR-45～FR-48，可複用記帳的告警/圖表邏輯，**2026-08-04 完成**）
- [x] Step 2.3：重要通知模組（FR-53，生日/節日排程 + 排除對象邏輯，**2026-08-04 完成**）—— 固定節日（元旦/除夕/初一/掃墓提醒/中秋/端午/父親節/母親節）與家人生日提醒，固定台灣時間 08:00 推播，借用 `/healthz` 既有 10 分鐘 cron 頻率；新增 `users.birthday`、`important_notifications_log` migrations，新增 `src/bot/notifications.py`（純邏輯，農曆計算用 `lunarcalendar` 套件）、`commands.py`／`router.py` 的 Owner 專屬「設定家人生日」流程、`main.py` 的 `_check_important_notifications()`；全專案 703 個測試全過，`notifications.py` 覆蓋率 100%
- [x] Step 2.4：錯誤 log 雲端連結（FR-19b，**2026-08-05 改寫並完成，見 ADR-15，supersede 原「異常自主診斷與 GitHub PR 自動化」規劃**）—— 例外發生時，把完整 Traceback＋觸發功能＋使用者輸入摘要組成 log 檔案，複用既有 `GDriveClient` 上傳至 Google Drive，私訊 Robin 專屬連結；其他使用者維持既有「生病了」安全用語不變，不揭露任何技術細節或連結。**同日追加（見 ADR-16）**：新增 `submodules/email` 當 Telegram 本身故障時的獨立備援通知管道
- [x] Step 2.5（**2026-08-07 完成，見 FR-19i、submodules-core SPEC.md ADR-13**）：外部 API 重試機制（FR-19i，Max 3 次 + Exponential Backoff），做為所有外部 API 呼叫的共用底層邏輯——新增 `submodules/retry`，`llm`／`telegram`／`voice`／`gdrive`／`calendar`／`email` 六個既有子模組皆已套用；全專案 795 個測試全過
- [x] Step 2.6（**2026-08-07 完成，見 FR-19f～FR-19h**）：例外分級降級（FR-19f 一般感冒級、FR-19g 重大疾病級）與決策執行狀態閉環回饋（FR-19h），套用到 Phase 1 已完成的待辦事項/心情小記與本 Phase 的記帳/體態模組——`webhook.py` 新增 `_is_llm_failure()` 分類判斷式、`_GENERAL_COLD_REPLY`／`_MAJOR_ILLNESS_REPLY` 兩級固定範本、`_broadcast_major_illness_to_family()`；FR-19h 稽核確認屬架構層級已滿足，不需逐一修改各功能模組；全專案 810 個測試全過
- [x] Step 2.7（2026-08-05 新增並完成，見 FR-66、ADR-17）：Google Calendar 整合——新增 `submodules/calendar`，待辦事項（FR-66a）、重要通知（FR-66b）、體態目標期限（FR-66c）單向同步寫入家庭共用行事曆；`todos`／`body_goals` 新增 `sync_to_calendar`／`google_calendar_event_id` 欄位（`0031`／`0032` migration，Robin 依 ADR-10 核准）；待辦事項與體態目標建立流程各自新增一輪「要不要同步」反問（不預設），節日/生日全自動同步；家人共用權限固定「查看所有活動詳細資料」（唯讀），非程式碼限制

### Phase 3：個人技能成長（Robin only，含 YouTube 技術情報）+ 好友模式

- [x] Step 3.1（**2026-08-07 完成**）：每日重點技術分享（FR-22、FR-23）
- [x] Step 3.2（**2026-08-07 完成，見 FR-25a～FR-25f、ADR-18**）：TOEIC 雙軌題庫 Pipeline —— 軌道一拍照/音檔入庫（Gemini Vision 影像 Key + Groq Whisper 語音轉文字切割，見 ADR-12）、軌道二 Gemini 文字 Key 單字題即時生成、固定每週日 22:00 排程去重。經 AskUserQuestion 與 Robin 確認範圍：這次只建題庫，不含推播/作答/批改（FR-26～FR-30 留給 Step 3.3）。新增 `submodules/gdrive` 的 `list_files()`／`download_file()`（OAuth scope 擴大為 `drive.file + drive.readonly`，Robin 需重新走一次 `get_refresh_token.py`）、`submodules/voice` 的 `transcribe_with_segments()`；新增 `src/bot/toeic.py`（檔名解析/分類、Vision 解析、Whisper 切割、單字題生成、週排程進入點）；新增 `toeic_questions`／`toeic_vocab_questions` 表與 `users.toeic_weekly_question_count`／`toeic_pipeline_last_run_on` 欄位（`0035`～`0037` migration，Robin 核准）；`main.py` 新增 `_check_toeic_pipeline()`；Dockerfile 新增 `ffmpeg`（`pydub` 依賴，用於整包 MP3 切割）；33 個新測試全過（含用 `pydub` 產生真實靜音音檔驗證切割邏輯可正確解碼）
- [x] Step 3.3（**2026-08-07 規格定案見 FR-24、FR-26～FR-30、ADR-19；2026-08-08 全數完成**）：每日推播出題與批改（08:00 推播、20:00/23:00 提醒與跳過，FR-26～FR-28，ADR-20，2026-08-08 分兩批完成，見上方里程碑紀錄）、正解改用 Robin 拍照上傳的 `_ans` 答案照（延伸 Step 3.2 檔名比對機制，不用 AI 推論）、作答紀錄表串連軌道一/軌道二、FR-29 成效改為彈性自然語言文字問答（不做圖表，圖表統一交給 Phase 4 App FR-64，2026-08-08 完成）、FR-30 正式成績獨立建表（2026-08-08 完成）、FR-24 目標設定與方向建議（2026-08-08 完成）。**Step 3.3 剩餘範圍實作完成**：新增 `src/bot/certificate_exam_scores.py`／`certificate_stats.py`／`certificate_goals.py` 三個純邏輯模組（皆 100% 覆蓋率），`commands.py` 新增 6 組對話流程／單次查詢指令（`log_exam_score`／`my_exam_scores`／`set_certificate_goal`／`my_certificate_goals`／`certificate_advice`／`my_quiz_stats`），`router.py` 註冊對應觸發詞與 `pending_*` 狀態分派；`certificate_goals`／`exam_official_scores` 兩張表沿用 Step 3.3 開工前已建好的 `0041`／`0042` migration，本次無新增 migration；新增 86 個測試，全專案測試數來到 1185 個全過，Phase 3 個人技能成長主線（不含 YouTube 模組與好友模式）至此全數完成
- [x] Step 3.4：YouTube 技術情報模組（FR-57～FR-59，**2026-08-08 設計改版，見 ADR-21，supersede ADR-9；同日完成實作**）—— YouTube Data API 擷取（含統計數字）、多主題設定、LLM 語意判讀取代 Rule-based 篩選、多主題輪替公平性、每週四自動推播、配額監控與 Fallback 降級
- [x] Step 3.5（**2026-08-08 規格定案並完成實作，見 FR-51、FR-52、ADR-22；Phase 3 至此全數完成**）：好友模式——被動觸發的陪伴聊天（「陪我聊聊」／`/friend_chat`），動態讀取使用者已開啟且近期有資料的所有模組，LLM 生成含心情趨勢文字摘要的陪伴回覆；不含主動關懷推播

### Phase 4：求職模組 + Mobile App（BI Dashboard）

> **2026-08-04 更新**：原獨立拆出的 Phase 5「Notion 後台」已取消，Mobile App（React Native + Expo）併入本 Phase，見 ADR-14。Step 4.4／4.5 僅為 Placeholder，詳細規劃留待本 Phase 開工、對應 Step 展開獨立 spec（`docs/specs/mobile-app/SPEC.md`）時再確認。

- [x] Step 4.1（**2026-08-08 規格定案，見 FR-33～FR-36、ADR-24；2026-08-09 追加 FR-36 履歷/期望工作內容收集歸屬確認，見 ADR-26；2026-08-09 全數實作完成（FR-33～FR-36），詳見 PROGRESS.md 里程碑；2026-08-09 由 Robin 透過瀏覽器 DevTools 手動實測驗證 FR-34a 欄位對應，已修正並更新 `submodules/job104/client.py`；2026-08-09 依 Robin 回饋移除產業篩選、地區篩選改為爬蟲階段子字串比對，見 FR-33、FR-34a 註記**）：104 職缺爬蟲（FR-33 多組搜尋條件、FR-34a～FR-34d：無登入態直呼叫 AJAX API、兩階段列表+詳情頁、每週一次、UA/Referer + 2～4 秒隨機延遲、禁併發、ETL 去重、職缺內容解析）；FR-35 公司背景改採 Email＋CSV＋Drive 人力協作機制（詳見 ADR-24）；FR-36 個人履歷與期望工作內容收集（含新增的結構化年資／期望薪資欄位，見 ADR-26），與 FR-33 搜尋條件同一輪對話流程收集（見 FR-56f 情境範例），僅 Robin 可用（**2026-08-09 實作**：`src/bot/job_search.py`＋`src/bot/commands.py` 8 輪對話流程＋`router.py` 觸發詞僅放在 is_owner 分支＋`templates.py` `job_search.owner_only` 改為 `True`；DB migration `0053`～`0056` 見 `src/schema/db_schema.md`）
- [x] Step 4.2（**2026-08-09 規格定案，見 FR-37、FR-38、ADR-26；2026-08-09 全數實作完成（FR-37、FR-38），詳見 PROGRESS.md 里程碑**）：Gemini 批次契合度評分（FR-37）與技能缺口分析（FR-38），完成後整理成 Excel 寄送 Robin、Robin 標記喜好後上傳回補資料庫（FR-38b～FR-38e，人力協作模式比照 FR-35；「是否關閉」已可自動判斷，見 FR-34d）。**實作**：`src/bot/job_search.py` `list_scorable_jobs()`／`score_jobs()`／`apply_scores()`（FR-37）、`build_ranked_jobs()`／`build_job_recommendation_excel()`／`send_job_recommendation_email()`（FR-38a～FR-38c）、`parse_recommendation_excel()`／`apply_job_preferences()`（FR-38e）；`src/bot/commands.py` `handle_job_recommendation_excel_uploaded()`；`router.py` 擴充 `.xlsx`／「職缺推薦」檔名分流；`main.py` `_check_job_search_weekly_crawl()` 新增 `GEMINI_API_JOB_SEARCH_KEY`；DB migration `0058` 見 `src/schema/db_schema.md`；新增依賴 `openpyxl`（見 `requirements.txt`）
- [x] Step 4.3（**2026-08-09 規格定案並實作完成，見 FR-39、FR-40、ADR-27**）：應徵成效追蹤——Telegram 語句記錄應徵狀態（含新增「未錄取／已婉拒」狀態，任意狀態可直接設定，不強制順序，見 FR-39a～FR-39c）＋「我的應徵紀錄」查詢指令（FR-39d）；LinkedIn／Cake 等外部管道職缺對話式新增並納入 Gemini 評分，與 104 職缺共用同一張表（`source` 欄位區分來源，一起參與每週排名，見 FR-40a～FR-40c）。**實作**：migration `0059`（`source` 欄位）、`0060`（`job_applications` 表）；`src/bot/job_search.py` `add_external_job()`／`record_application_status()`／`list_latest_application_statuses()`／`format_application_statuses()`；`src/bot/commands.py` 六輪外部職缺新增流程＋查詢指令；`router.py` 應徵狀態更新 regex＋新增觸發詞
- [ ] Step 4.4（Placeholder）：Mobile App 基礎建設與登入機制（FR-65）—— 建立 `mobile/` Expo 專案骨架、`users.app_access_token` 建表（依 ADR-10 流程）、登入頁與 `/api/app/*` 驗證中介層
- [ ] Step 4.5（Placeholder）：BI Dashboard 圖表頁面（FR-64）—— 記帳/體態模組的圖表 API（消費圓餅圖、體重折線圖等）與對應的 App 頁面

### 語言學習（`language` 功能開關，**2026-08-08 決議擱置，見 ADR-23**）

> `language`（英文口說練習、其他語言學習）功能開關已於 2026-08-07 隨 `skill_growth` 拆分建立（見 feature-toggles SPEC.md FR-3 追記），但從未展開對應的功能性需求，也不在 Phase 0～4 任何 Step 內。**2026-08-08 Robin 明確決議「可以先擱置」**——目前規劃到 Phase 4（求職模組＋Mobile App）為止，`language` 何時展開、展開成什麼樣的功能，留待 Phase 4 完成後再另行討論定案，非目前 Roadmap 範圍，開關本身維持存在但功能上是無作用的（開/關都不影響任何行為）。

## 測試策略

> 各 Phase 進入實作前，於對應 feature spec 中展開詳細測試案例；此處先列出 Phase 1（MVP）關鍵路徑。

### Unit Tests
- [ ] 通關密碼驗證邏輯：正確密碼啟用、已使用密碼拒絕、Robin 免密碼路徑
- [ ] Owner 設定對話流狀態機：非 Robin 觸發 `/set_invite_codes` 應被拒絕；正常問答循環寫入 DB；「沒有了」正確結束流程（FR-6a～FR-6c）
- [ ] 個資偵測 Regex：8 類台灣格式（身分證/手機/市話/銀行帳戶/信用卡/健保卡/地址/車牌）正例與反例；生日、LINE ID 應不被遮蔽（FR-13a、FR-13c）
- [ ] 語音時長預檢查：10 分鐘邊界值（9:59 / 10:00 / 10:01）
- [ ] 語音修正限制窗口：15 分鐘邊界值（14:59 內用語音修正應拒絕 / 超過 15:00 用語音修正應放行）
- [ ] 重試機制：模擬外部 API 前 2 次失敗、第 3 次成功應正常回傳；3 次全部失敗應正確拋出例外並記錄等待時間為 1s/2s/4s（FR-19i）
- [ ] 例外分級判斷：LLM 呼叫正常但其他元件異常應歸類「一般感冒級」；LLM 呼叫本身拋例外應歸類「重大疾病級」（FR-19f、FR-19g）
- [ ] `/rule`、`/function` 觸發判斷：「我要看使用規則」與 `/rule` 應觸發相同回應；「我要看所有功能」與 `/function` 應觸發相同回應；兩者皆不應呼叫 LLM（FR-55、FR-56）
- [ ] YouTube Top 3 篩選邏輯：Shorts 與重複來源應被剔除；相關度+頻道權重評分排序正確；過去 30 天內已推播 `video_id` 應被過濾（FR-58a～FR-58c）
- [ ] `/complaint` 觸發判斷：「我要客訴你」與 `/complaint` 應觸發相同的固定提問，且不呼叫 LLM；觸發後的下一則訊息應被正確捕獲為客訴內容（FR-60、FR-61）

### Integration Tests
- [ ] Telegram webhook → 功能開關判斷 → 對應模組路由
- [ ] Gemini 對話呼叫 → 知識庫查詢隔離（使用者 A 無法讀到使用者 B 的客製知識庫/對話紀錄）
- [ ] 健康檢查端點回應 200 且回應時間符合 cron-job 逾時限制
- [x] TOEIC 軌道一：圖檔+音檔檔名比對成功 → 寫入完整題目（含圖片/音檔 URL）；整包 MP3 → STT 切割 → 逐段落入庫（FR-25a～FR-25c，2026-08-07 完成，見 `tests/bot/test_toeic.py`）
- [x] TOEIC 軌道二：Gemini 生成單字題 → 8 欄位齊全 → 寫入 DB；重複執行同週排程不應重複生成已存在題目（FR-25d～FR-25f，2026-08-07 完成）
- [ ] 104 爬蟲：呼叫 AJAX API 取得職缺列表 → 分頁請求間隔應落在 2～4 秒 → 確認未使用瀏覽器自動化套件；重複爬到同一職缺應更新既有紀錄而非新增（FR-34a～FR-34d）
- [ ] YouTube Data API 呼叫：確認單次搜尋消耗 100 Units 且被正確累計進每日配額；模擬超過 1,000 Units/日門檻應觸發 Fallback（FR-59a～FR-59c）

### E2E Tests
- [ ] 新使用者輸入通關密碼 → 啟用成功 → 立即收到附錄 A 歡迎訊息 → 建立待辦事項 → 收到前 30 分鐘提醒（FR-6c、FR-6d）
- [ ] 服務模擬錯誤 → 使用者端收到「生病了」訊息 → Robin 收到完整 Traceback log → 修復後群發「我康復了」（Phase 1，對應 FR-19a/FR-20）

> Phase 2 補充（Step 2.4～2.6）：
- [ ] 服務模擬「一般感冒級」錯誤 → 使用者收到感冒靜態語句、Robin 收到完整錯誤詳情，**未呼叫額外 LLM 生成回覆**（FR-19f）
- [ ] 服務模擬「重大疾病級」錯誤（如 LLM API Key 失效）→ 完全繞過 LLM、使用者與所有家人收到寫死的重大疾病廣播、Robin 收到最高等級告警（FR-19g）
- [ ] 服務模擬錯誤 → 使用者（含觸發者本人與所有其他家人）僅收到「生病了」安全用語，訊息中**不含**任何連結或技術細節 → Robin 額外收到 Google Drive log 連結 → 點開連結內容包含完整 Traceback／觸發功能／使用者輸入摘要（FR-19b）
- [ ] 模擬 Google Drive 上傳失敗（例如 API 逾時）→ 使用者仍正常收到「生病了」訊息、Robin 仍正常收到私訊（僅缺連結欄位），不因上傳失敗導致整個錯誤通知流程中斷（FR-19b 優雅降級）
- [ ] 使用者新增一筆記帳紀錄並確認 → 成功時收到明確成功訊息；模擬 DB 寫入逾時 → 收到感冒語句且該筆紀錄確實未寫入（FR-19h）

> Phase 3 補充（Step 3.4）：
- [ ] 每週四排程觸發 → Robin 收到 Top 3 影片的 Markdown 超連結推播，且不重複本月已推播過的影片（FR-58c、FR-59a）

> Phase 1 補充（Step 1.9）：
- [ ] 使用者輸入「我要客訴你」→ 收到固定提問 → 回覆客訴內容 → 資料庫寫入成功 → Robin 收到 Gemini 分析報告（問題點＋修正建議），且該分析報告**未**傳送給提出客訴的使用者本人（FR-60～FR-62）

## 風險與緩解

| 風險 | 嚴重度 | 機率 | 緩解方案 |
| --- | --- | --- | --- |
| Render 免費方案 15 分鐘無請求即休眠 | 中 | 高 | cron-job 每 10 分鐘打 keep-alive API（FR-3） |
| Neon 免費額度僅 0.5GB 容量耗盡 | 高 | 中 | 圖片一律存 GDrive、容量 80% 主動告警（NFR-3） |
| Gemini 免費額度被單一功能耗盡 | 高 | 中 | 對話/圖像金鑰分流 + 用量監控告警（ADR-2） |
| 通關密碼外洩或被轉發濫用 | 中 | 低 | 一次性使用機制、`is_used` 標記（ADR-3） |
| 使用者誤傳個資 | 高 | 中 | 即時偵測（Regex + LLM 雙層）+ 提示收回 + 刪除機制（FR-13a～FR-13d） |
| 104 網站反爬蟲或條款變更 | 中 | 低 | 不使用瀏覽器自動化、每週僅一次、標準 UA/Referer、分頁間 2～4 秒隨機延遲、禁併發（FR-34a～FR-34c） |
| 104 每週爬蟲重複寫入同一職缺，資料庫膨脹 | 中 | 中 | 以職缺唯一 ID/URL 做 ETL 去重，已存在則更新而非新增（FR-34d、NFR-11） |
| YouTube API 每日配額（10,000 Units）被單一功能耗盡，影響其他模組 | 中 | 低 | 每週僅執行一次、單次僅消耗 100 Units，並設每日 1,000 Units 上限門檻（FR-59b） |
| YouTube 推薦品質不佳（如關鍵字設定太寬泛、推到不相關影片） | 低 | 中 | LLM 判讀 Prompt 可事後調整（ADR-21 後果），只是換文字描述、不涉及重新訓練模型 |
| YouTube Data API 服務中斷或回應異常 | 低 | 低 | 依 FR-59c 走 FR-19i 重試機制與 FR-19f 分級降級，不影響其他模組運作 |
| 全功能一次開發導致 MVP 難產 | 高 | 中 | 採 ADR-4 分期策略，Phase 1 聚焦最小可用範圍 |
| AI 誤觸發自動修復、繞過人工審核直接改正式環境 | 高 | 低 | **2026-08-05 更新（見 ADR-15）**：此風險已隨 FR-19e（GitHub PR 自動化）整套取消而消除，Robinson 現在對正式環境程式碼完全不具備任何自動修改/部署能力，連「開 PR」這個較低風險的權限都沒有（NFR-8） |
| error log 上傳 Google Drive 沒有生命週期管理，長期可能累積大量檔案佔用 Robin 個人 Drive 容量 | 低 | 低 | 目前不特別處理，之後容量吃緊再視需要加清理機制或改用同一資料夾人工定期清除（見 ADR-15） |
| Telegram 與 Email（Gmail）備援管道剛好同時故障，Robin 完全收不到任何主動錯誤通知 | 低 | 低 | 兩者是不同公司、不同協定的獨立基礎設施，同時故障機率極低；已是最後一道防線，不再疊加第三層備援（見 ADR-16），殘餘風險接受，Robin 可定期查看 Render Dashboard 的應用程式 log 作為手動保底 |
| Owner 設定對話流被家人誤觸或惡意觸發 | 中 | 低 | 嚴格比對 `telegram_user_id` 是否為 Robin，非 Robin 觸發一律無效且不透露此指令存在（FR-6a） |
| TOEIC 軌道一檔名比對失敗或音檔/圖檔沒對齊，導致題目資料錯誤 | 中 | 中 | 比對失敗時不寫入資料庫，改私訊 Robin 請人工確認檔名，避免髒資料進知識庫 |
| 外部 API 重試機制參數設定不當，重試風暴反而加劇對方伺服器負擔 | 中 | 低 | 固定 Max 3 次 + Exponential Backoff（1/2/4 秒），不做無限重試（FR-19i） |
| 建表 SQL 未經 Robin 審核就被執行，或執行後忘記記錄到 `db_schema.md` | 中 | 低 | 依 ADR-10 流程，執行前必須先呈現 SQL 與理由並取得同意，執行後立即同步文件；此為硬性流程規範，不因趕時程而跳過 |
| 客訴功能被惡意灌水（大量無意義訊息）或當成一般聊天誤觸發 | 低 | 低 | 觸發詞需明確比對「我要客訴你」或 `/complaint`，避免一般對話誤判；灌水內容仍會如實記錄+分析，由 Robin 自行判斷是否為有效回饋 |

## 待確認事項（已於 2026-07-29 全數確認，Phase 1 正式解除阻塞）

> 依 AGENTS.md 硬規則，中大型實作前必須等使用者確認；以下 7 項 Robin 已全數回覆，保留原問題與回覆結果作為決策紀錄，供日後追溯。

- [x] 是否同意 ADR-4 的 MVP 分期順序？→ **同意**，維持 Phase 1：核心平台＋待辦＋心情小記；理由是先穩定 Telegram 連線、權限控制與資料庫基礎建設，避免後續記帳/體態擴充時失控
- [x] 通關密碼的分發方式？→ Robin 私訊告知家人；設定方式改為僅限 Owner 觸發的引導式對話流（見 FR-6a～FR-6c、ADR-8），不做後台表單
- [x] TOEIC 題庫來源？→ 雙軌混合架構：軌道一 Robin 拍照/音檔上傳 + Gemini Vision/STT 解析入庫、軌道二 Gemini 即時生成單字題（見 FR-25a～FR-25f）
- [x] 104 爬蟲的合規性？→ 不使用瀏覽器自動化、直接呼叫 AJAX/JSON API、每週僅一次、標準 UA/Referer、分頁間 2～4 秒隨機延遲、禁併發（見 FR-34a～FR-34c）
- [x] Notion 後台排程順序？→ 獨立拆成 **Phase 5**，排在全專案最終階段；Phase 0～4 期間僅需維持資料層 API 抽象化彈性（見 FR-54、實作計畫 Phase 5）。原訂 8/4 之後開始，因 2026-07-30 時程改為兩週制順延至 8/11 之後，同日再因新增 YouTube 模組追加 1 天緩衝，目前為 **8/12 之後**（見 PROGRESS.md）（**2026-08-04 更新**：此決策已由 ADR-14 取代——Notion 改為 Mobile App，Phase 5 取消、併入 Phase 4，詳見 ADR-14 與實作計畫）
- [x] 個資偵測規則的具體格式？→ Regex 硬規則 + LLM 語意辨識雙層防線，覆蓋 8 類台灣個資格式，排除生日與 LINE ID（見 FR-13a～FR-13d）
- [x] FR-19e「核准後執行修復」的執行機制範圍？→ Render 線上自主運維模組：AI 診斷後透過 GitHub API 開分支與 PR，Robin 在 GitHub 審核 Merge 後才觸發部署，Robinson 不具備直接推送 `main` 的權限（見 FR-19e-1～FR-19e-5、ADR-7）（**2026-08-05 更新**：此決策已由 ADR-15 取代——Step 2.4 開工前 Robin 重新評估後認為 AI 自主診斷＋GitHub PR 自動化太複雜、風險過高，且系統當時已無法使用 Gemini Search grounding（見 submodules-core SPEC.md ADR-8）導致 FR-19b「上網查詢」根本做不到，改為更輕量的「完整 log 上傳 Google Drive＋私訊 Robin 專屬連結」設計，詳見 ADR-15）

## 補充注意事項（2026-07-29 Robin 新增，非提問，直接採納為需求）

以下 3 點已直接寫入 FR-19f～FR-19i（例外分級降級、決策執行狀態閉環回饋、外部 API 重試機制），此處僅留存原始脈絡：

- 系統例外需依「LLM 是否還能正常推送訊息」分兩級：一般感冒級（LLM 正常，其他元件異常）與重大疾病級（LLM 本身崩潰，需完全繞過 LLM、用寫死靜態範本廣播）
- 所有資料異動操作，無論成功或失敗都必須明確回覆使用者，嚴禁靜默
- 所有外部 API 呼叫需有 Max 3 次重試 + Exponential Backoff（1/2/4 秒），重試耗盡才正式判定失敗

## 附錄 A：規範文本（歡迎訊息 / `/rule` 共用範本）

> 此範本由 Robin 於 2026-07-30 提供，為 FR-6d（通關密碼驗證成功歡迎訊息）與 FR-55（`/rule` 路由）共用的固定文字，**不經過 LLM 生成**，逐字回傳即可。

```
📋 以下是羅賓森的使用須知：

✨ 服務使用須知：
1. 本服務皆使用免費資源建置。
2. 每個功能皆設有開關：若開啟後發現暫時不需要使用，請直接關閉，避免消耗 AI 使用額度。
3. 支援「打字」或「語音」兩種訊息傳送方式。
4. 想清除您與羅賓森的對話紀錄（不含知識庫內容）時，可以輸入「我想要刪除所有對話紀錄」。

⚠️ 使用限制與規範：
1. 嚴禁記錄個人敏感隱私資訊（如身分證字號、電話號碼、信用卡號等）。
2. 圖片與語音檔案都可以上傳給羅賓森辨識，但僅支援這兩種格式喔！PDF、Excel、PPT 等其他檔案格式他沒辦法處理。
3. 上傳影像前請務必確認內容不包含個人資料（如證件、帳單等），若上傳含有個資的影像，後果需由您自行承擔。
4. 請勿拿來錄製長篇會議紀錄或演講（避免消耗大量 AI 使用額度）。
5. 羅賓森目前僅會根據「已知知識」做出回答。若需要即時上網查詢的資訊（例如：「國道有沒有塞車」、「下午天氣如何」等），請先自行搜尋。若是固定知識（例如：「威靈頓牛排食譜」或「澎湖行程規劃」），您可以把答案提供給羅賓森，他會幫忙記錄下來、學習更多新知識喔！

🔒 隱私承諾： 羅賓森非常注重「您的個人隱私」，絕對不會將您的個人資料與聊天記錄提供給其他人，包含「馬承安 (Robin)」本人也完全無法存取或查看喔！

-----------------------------------
💡 貼心小撇步：您可以長按這條訊息點選「釘選或置頂 (Pin)」，以後隨時查看規範更方便，又或是隨時在聊天室輸入「我要看使用規則」也能重新呼叫這份說明喔！如果您對羅賓森的服務有任何不滿意或想建議改進的地方，也歡迎隨時輸入「我要客訴你」告訴我們！
```

**變更紀錄**：
- 2026-07-30 開頭語句由「🎉 通關密碼驗證成功！歡迎使用羅賓森 AI 服務。」改為「📋 以下是羅賓森的使用須知：」，讓 FR-6d（歡迎訊息）與 FR-55（`/rule`）共用同一份文案時語境都通順；同時補上「我要客訴你」的觸發提示，呼應新增的 FR-60～FR-63 客訴收集功能。
- 2026-07-30 依 FR-17／FR-17a 更新：原本「請勿傳送證照題目以外的圖片」改為開放圖片與語音兩種格式上傳（不再限定證照題目），並新增個資影像警語「後果需由您自行承擔」（對應 FR-17a）；原有的第 2 點拆成三點，編號順延。
- 2026-08-01 新增第 4 點：告知使用者可輸入「我想要刪除所有對話紀錄」清除對話紀錄（對應 chat-core SPEC.md FR-10、`/clean-all-dialog` 路由）。

## 附錄 B：`/function` 路由待補文字模板

FR-56 的 `/function` 路由目前只定義了「回傳範圍」（所有功能清單 + Owner/使用者權限註記），尚未定義實際回覆的文字排版與措辭，原因是目前還沒有產品原型可參考版面呈現方式。待有原型後，需要 Robin 補充：
- [ ] 功能清單的分類/排版方式（例如：依模組分段、或依「大家都能用」vs「僅 Robin 能用」分兩區塊）
- [ ] 每個功能的簡短說明文字（一句話描述用途）
- [ ] 是否需要附上「怎麼開關這個功能」的操作提示

## 變更記錄

| 日期 | 變更內容 | 變更者 |
| --- | --- | --- |
| 2026-07-29 | 初版建立：彙整完整需求為 FR/NFR、6 個核心 ADR、Phase 0～4 分期實作計畫 | Claude（依 Robin 需求整理） |
| 2026-07-29 | 調整 FR-15：語音修正的「僅能打字」限制改為僅在語音送出後 15 分鐘內生效，超過 15 分鐘語音模式恢復可用；同步更新 ADR-5、Step 1.4、測試策略 | Robin |
| 2026-07-29 | 新增 Step 0.1a：建立 `submodules/` 共用子模組骨架，展開為獨立 spec [docs/specs/submodules-core/SPEC.md](../submodules-core/SPEC.md) | Robin |
| 2026-07-29 | Step 0.1a 更新：`submodules/` 依 Robin 指定樣板重構為 `llm`/`cloudsql`/`telegram` 三資料夾統一四檔案結構 | Robin |
| 2026-07-29 | 重寫 FR-19 為「捕獲異常→自主診斷→衝擊評估→建議報告→人工核准」5 步驟流程（FR-19a～FR-19e），新增 NFR-8、ADR-7；Phase 1 Step 1.6 縮小為基礎捕獲+Log+通知，AI 自主診斷延後至 Phase 2 新增的 Step 2.4；同步更新測試策略、風險表、待確認事項 | Robin |
| 2026-07-30 | 大改版：① 新增「重要資產（不可刪除）」記錄 `docs/profile/Robinson.png` ② FR-19d 補充程式碼異動紀錄要求 ③ 7 項待確認事項全數回覆並解除 Phase 1 阻塞 ④ FR-6 擴充為 Owner 引導式通關密碼設定對話流（新增 FR-6a～FR-6c、ADR-8）⑤ FR-13 擴充為 Regex+LLM 雙層個資遮蔽規則（新增 FR-13a～FR-13d）⑥ FR-25 擴充為 TOEIC 雙軌題庫 Pipeline（新增 FR-25a～FR-25f）⑦ FR-34 擴充為 104 爬蟲技術細節（新增 FR-34a～FR-34c，頻率改為每週一次）⑧ ADR-7／FR-19e 改為確定版：GitHub PR 治理機制，新增 GITHUB_TOKEN 金鑰 ⑨ 新增 FR-19f～FR-19i（例外分級降級、決策執行閉環回饋、外部 API 重試機制）與 NFR-9、NFR-10 ⑩ Notion 拆為獨立 Phase 5，Phase 4 僅剩求職模組；同步更新測試策略、風險表、實作計畫 | Robin |
| 2026-07-30 | 新增 FR-6d（通關密碼驗證成功歡迎訊息）、FR-55（`/rule` 路由）、FR-56（`/function` 路由，文字模板因無產品原型暫緩，見附錄 B）；新增「附錄 A：規範文本」存放 Robin 提供的固定歡迎訊息全文；概要新增「專案緣起」段落，記錄 Robin 2026-07-28 完成服務註冊/API 申請/Telegram 基礎設定與 Gemini 腦力激盪收斂 PRD 雛形，2026-07-29 才開始與 Claude Code 產出標準文件；時程由一週改為兩週（見 PROGRESS.md），Phase 5 Notion 順延至兩週後 | Robin |
| 2026-07-30 | 新增「YouTube 技術情報模組」：FR-57（輕量 API 擷取）、FR-58（三層 Top 3 篩選：格式過濾/相關度評分/歷史去重）、FR-59（每週四排程、配額控管、Fallback 降級），新增 ADR-9（輕量規則式篩選 vs ML/向量推薦）；新增 NFR-11「排程收集資料一律 ETL 去重」通則，回頭補上 FR-34d（104 職缺 ETL 去重）並於 FR-23、FR-25f 加註對應；新增 `YOUTUBE_API_KEY` 金鑰；Phase 3 新增 Step 3.4，時程順延 1 天 | Robin |
| 2026-07-30 | 概要新增「使用性質聲明」（個人非商業用途），新增 NFR-13；新增 ADR-10（資料庫 Schema 建立採先審核後執行流程）與 NFR-12，建立 `src/schema/db_schema.md`、`src/schema/api_schema.md` 骨架；新增客訴收集功能 FR-60～FR-63（`/complaint` 路由、客訴記錄、Gemini 分析私訊 Robin、人工決策），新增 Phase 1 Step 1.9、Phase 0 Step 0.1b；附錄 A 開頭語句改為「📋 以下是羅賓森的使用須知：」並補上「我要客訴你」提示語；同步更新測試策略、風險表 | Robin |
| 2026-07-30 | 新增 ADR-11：確認 Cowork sandbox 連不到 Neon/Telegram/GitHub REST API/Google API/Notion API（皆被 proxy 白名單擋下），但 `github.com`（git 協定）可連線且 `git push` 實測成功；因此 ADR-10 的執行機制改為「Migration 檔案（`src/migrations/`）+ Robin 同意後 Claude 自動 commit+push + Render 偵測 main 分支自動部署 + `main.py` 開機自動套用」，Robin 確認 Render 已開啟 push-to-main 自動部署；新增 Phase 0 Step 0.5a | Robin |
| 2026-07-30 | ADR-10 新增第 5 點決策：所有建表 SQL 必須用 `COMMENT ON TABLE`／`COMMENT ON COLUMN` 附上中文說明，直接寫在 SQL 裡，適用所有未來資料表 | Robin |
| 2026-07-30 | Phase 1 Step 1.1 完成：通關密碼驗證、Owner 對話式設定流程、`/rule`／`/function` 內建指令，展開為獨立 [docs/specs/platform-auth/SPEC.md](../platform-auth/SPEC.md)（含 ADR-1：Webhook 改用原生 JSON 解析、移除 `python-telegram-bot`；ADR-2：對話狀態存記憶體不落地資料庫）；49 個測試全過、`src/bot/` 覆蓋率 100% | Claude（依 Robin「請開始吧」指示） |
| 2026-07-30 | 大改版（多模態與人格化語氣）：① 新增四把 Gemini Key（`GEMINI_API_BOT_KEY`／`GEMINI_API_IMAGE_KEY1`／`GEMINI_API_IMAGE_KEY2`／`GEMINI_API_TEXT_KEY`，原 `GEMINI_API_TOEIC_KEY` 更名為 `GEMINI_API_IMAGE_KEY2`）與 `VOICE_API_KEY`（Groq Whisper），新增 ADR-12（依用途分流四把 Key＋語音改用 Groq Whisper，取代 FR-25b 原「一律用 Gemini」的決策）② 新增 ADR-13（影像/語音「先上雲端、後壓縮、再辨識」流程，`Pillow` 壓縮至 1024×1024／JPEG 80%，統一命名規則與 URL 入庫），`requirements.txt` 新增 `Pillow` ③ FR-17 全面修訂：開放一般圖片辨識（不再限定證照題目），新增 FR-17a（個資影像警語）、FR-17b（不確定內容須詢問使用者）、FR-17c（飲食分析誤差聲明）④ FR-56 全面改版：`/function` 由一次性完整清單改為「總覽＋按需深入＋情境範例」，新增 FR-56a～FR-56d（含 Robin 提供的記帳情境範例），並新增 FR-56c 人格化語氣規則（一般對話回覆須先參考人格背景知識庫，不可逐字照搬模板）⑤ Phase 1 新增 Step 1.3a（`/function` 改版）、Step 1.3b（影像辨識基礎流程）⑥ 附錄 A 同步更新使用限制條文（開放圖片/語音格式、新增個資警語），並同步更新 `src/bot/templates.py` 與對應測試 ⑦ 新增 `src/migrations/0006_seed_persona_and_family_knowledge.sql`，寫入 Robin 提供的 Robinson 人格背景與家人背景至 `knowledge_base` ⑧ 時程由兩週延長為三週（8/12 → 8/18），Phase 5 順延至 8/18 之後 | Robin |
| 2026-07-30 | 新增 FR-2a：確認 Step 1.2 功能開關權限模型——使用者可自行開關自己的功能，Owner 額外擁有代管權限可調整任何人的開關 | Robin |
| 2026-07-30 | **Phase 1 Step 1.2 完成**：功能開關系統，展開為獨立 [docs/specs/feature-toggles/SPEC.md](../feature-toggles/SPEC.md)（含 ADR-1：對話狀態 dict 新增 `flow` 欄位區分流程）；新增 `src/bot/toggles.py`、`/my_toggles`／`/set_toggle` 指令；78 個測試全過、`src/bot/` 覆蓋率 100% | Claude（依 Robin「照你說的先做」指示） |
| 2026-07-31 | **Phase 1 Step 1.3 完成**：Gemini 對話核心，展開為獨立 [docs/specs/chat-core/SPEC.md](../chat-core/SPEC.md)（含 ADR-1：查無答案時單次呼叫＋Google Search grounding，Robin 確認；ADR-2：`pending_kb_save` 狀態流程）；新增 `src/bot/knowledge.py`、`src/bot/chat.py`，`submodules/llm/client.py` 新增 `generate_with_search()`；`router.py` 最終 fallback 改呼叫聊天核心（移除 `_PLACEHOLDER_REPLY`）；全專案 104 個測試全過、覆蓋率 100% | Claude（依 Robin「繼續開發 Step 1.3 吧」指示） |
| 2026-07-31 | Robin 指出短記憶會忘記久遠對話，確認記憶架構改為「長記憶＋短記憶＋知識庫＋上網查資料」四部分並核准 `conversation_summaries` 建表 SQL；新增 ADR-3（見 chat-core SPEC.md）：長記憶採滾動式摘要，backlog ≥10 則觸發、呼叫 `GEMINI_API_TEXT_KEY`；新增 `src/bot/memory.py`；全專案 117 個測試全過、覆蓋率 100% | Robin |
| 2026-07-31 | Robin 提供待辦事項／求職／體態管理／心情小記四項功能的情境範例，新增 FR-56e～FR-56h（比照 FR-56d 格式逐字收錄）；同步補充相關業務規則：FR-31 新增模組歸屬歧義需反問使用者、新增 FR-31a（待辦逾期或使用者告知完成/取消時標記結束）、FR-32 補充提醒與否由記錄當下決定；FR-46 新增身高體重合理範圍檢查（成人身高約 140～220 公分、體重約 40 公斤以上）| Robin |
| 2026-07-31 | **Phase 1 Step 1.3a 完成**：`/function` 重新實作為「總覽＋按需深入＋情境範例」，展開為獨立 [docs/specs/chat-core/SPEC.md](../chat-core/SPEC.md) FR-9（含 ADR-4：總覽用獨立小型 LLM 呼叫，細節追問併入既有聊天核心，Robin 確認）；FR-56、FR-56a～FR-56h 全數完成；新增 `knowledge.get_persona_text()`，`commands.handle_function()` 改為 LLM 人格化總覽，`chat.py` prompt 固定附上功能手冊供按需細節追問；全專案 126 個測試全過、覆蓋率 100% | Claude（依 Robin「繼續開發吧」指示） |
| 2026-07-31 | Robin 實測時撞到 Gemini 429（額度超限），確認四把 Gemini Key 分屬四個獨立 Google Cloud 專案（ADR-12 分流設計有效），但發現 `webhook.py` 未攔截例外會讓 Telegram 自動重送同一則訊息、加速燒光額度；補充 FR-19 說明，新增 platform-auth SPEC.md FR-7（暫時性安全網：`try/except` + 固定安全用語 + 仍回 200），完整分級錯誤處理仍留給 Step 1.6；全專案 127 個測試全過、覆蓋率 100% | Claude（依 Robin「先加上最小安全網」指示） |
| 2026-07-31 | Robin 要求「該做的防呆要做好，不要因為程式碼關係浪費不必要的額度」，再補兩層防護：① platform-auth SPEC.md FR-7a：`update_id` 去重（LRU 上限 1000 筆），解決「沒出錯但被 Telegram 誤判逾時重送」也會重複打 Gemini 的問題 ② submodules-core SPEC.md FR-7／ADR-5：`LLMClient` 新增本地端節流保護（同一 `api_key` 最近 60 秒超過 8 次呼叫直接擋下、不送出請求，避免明知道會被官方 429 拒絕還是浪費額度嘗試）；FR-7 安全網範圍也擴大涵蓋 DB／LLM Client 建立與 Telegram 傳送失敗；全專案 137 個測試全過、覆蓋率 100% | Claude（依 Robin「該做的防呆要做好」指示） |
| 2026-07-31 | 確認 429 Traceback 為真實 Gemini 額度超限（非本地端節流誤判），安全網運作正常；Robin 確認 Step 1.3b（影像辨識）設計：新增 `media_uploads` 表統一記錄圖片/語音的 Google Drive 網址（Step 1.4 語音功能上線後共用）；修正 ADR-13 第 2、4 點——壓縮版圖片僅記憶體內即時處理、不落地存回 Google Drive，只保留原始檔 | Robin |
| 2026-07-31 | **Phase 1 Step 1.3b 完成**：影像辨識基礎流程，FR-17／FR-17a～FR-17c 全數完成；新增 `submodules/gdrive/`（Service Account 認證，僅上傳、不含下載/列表能力）、`TelegramClient.get_file_bytes()`（兩段式檔案下載）、`src/bot/image.py`（`Pillow` 壓縮＋隨機挑選影像 Key＋`[NEED_CONFIRM]` 標記慣例反問使用者）；`router.py` 新增 `handle_photo_message()`／`pending_image_confirm` 流程分派，`webhook.py` 新增 `_extract_photo()`／`_extract_unsupported_file()` 完成訊息類型分流；修正 `pytest.ini` 加 `--import-mode=importlib` 解決多個 `submodules/*/test_client.py` 同名模組衝突；全專案 179 個測試全過，`src/bot/`／`submodules/gdrive`／`submodules/telegram`／`submodules/llm` 覆蓋率 100% | Claude（依 Robin「你繼續開發你的，我明天再一次測試」指示） |
| 2026-08-01 | Robin 實測回報兩個調整需求並新增一個功能：① 打字誤植（同音字/形似字）原本「直接假設同一人並回答」改為「先反問確認再回答」，新增 chat-core SPEC.md ADR-7、`pending_name_confirm` 狀態 ② 回答太囉唆（例如問年齡/顏色會附加不必要的推算過程），新增 FR-3(f) 精簡回答規則 ③ 新增 `/clean-all-dialog` 指令（見 chat-core SPEC.md FR-10），使用者輸入「我想要刪除所有對話紀錄」可清除自己的對話紀錄（`conversation_logs`＋`conversation_summaries`），刻意不動知識庫內容，明確與規劃中、尚未實作的「刪除特定主題相關紀錄」（`/clean-target-dialog`，會連知識庫一起清）區隔；附錄 A 新增第 4 點使用須知 | Robin |
| 2026-08-01 | Robin 再回報代名詞指涉 bug：連續問「小雯有養動物嗎」→（中間插入一則不相關問題）→「范麗芳是誰」→「她老公是誰」，Robinson 誤把「她」理解成更早之前提過的小雯，而不是最近一次才明確點名問過的范麗芳；補強 chat-core SPEC.md FR-3(e)：代名詞一律以使用者「最近一次」明確點名的對象為準（即使中間插入其他問題也不可跳回更早的人），沒有百分之百把握就必須先反問使用者 | Robin |
| 2026-08-01 | Robin 測試又回報四個問題：① `/clean-all-dialog` 沒先確認就直接刪除，補強 chat-core SPEC.md FR-10：先告知目前對話紀錄筆數並反問確認，使用者確認後才真正執行 ② Robin 請 Robinson 把家庭成員背景新增到知識庫，Robinson 謊稱已新增（實際上沒有寫入路徑），新增 FR-3(g) 誠實性規則，禁止在沒有實際寫入的情況下宣稱已記錄 ③ 新增 migration 寫入阿牛（牛牛，Robin 家的狗）與龜龜（Robin 爸爸養的蘇卡達陸龜）兩筆寵物背景至 `general_family` 知識庫 ④ 問「阿牛是誰」被誤反問「你是說『吳凱吉』嗎？」，修正打字誤植反問規則，要求必須帶出資料中真實存在且高度相似的人名 | Robin |
| 2026-08-01 | Robin 指示「主動記知識的功能、/clean-target-dialog API 現在先開發吧」，展開 chat-core SPEC.md FR-11（主動新增知識）與 FR-12（`/clean-target-dialog`），新增 ADR-8：共用知識庫（`general_family`／`general_persona`）的寫入與刪除一律限定 Robin（Owner），非 Owner 只能操作自己的 `custom` 知識庫與自己的對話紀錄；新增 `knowledge_base.label` 分類/標籤欄位（`0012_add_label_to_knowledge_base.sql`）；沿用 ADR-6/ADR-7 的兩輪反問確認架構；全專案 219 個測試全過、覆蓋率 100% | Robin |
| 2026-07-31 | Robin 持續撞到 429，經 AI Studio Rate Limit 頁面實測發現 `gemini-flash-latest` 別名解析到的 Gemini 3.6 Flash 免費層只有 RPM 5／RPD 20，遠低於原本假設的 10～15 RPM／1500 RPD；新增 submodules-core SPEC.md ADR-6：改用明確指定版本的 `gemini-3.5-flash-lite`（實測 RPM 15／RPD 500，同屬 Gemini 家族、零相容性風險），Gemma 4（實測 RPM 30／RPD 14,400）與開通計費升級留待額度仍不夠用時再評估 | Claude（依 Robin「好啊，麻煩你了」指示） |
| 2026-08-01 | **Phase 1 Step 1.4 完成**：語音轉文字流程（FR-14、FR-15），新增 `submodules/voice/`（`VoiceClient`，用 `requests` 直打 Groq OpenAI 相容 REST API `https://api.groq.com/openai/v1/audio/transcriptions`，不安裝官方 `groq` SDK，比照 `submodules/telegram` 的作法）、`src/bot/voice.py`（`exceeds_duration_limit()`／`is_within_correction_window()`／`transcribe_and_upload()`）；架構決策：轉出來的文字不另建獨立流程，直接呼叫既有 `router.handle_message()` 走完整指令/pending flow/一般聊天分派，語音只負責「變成文字」；`src/bot/media.py` 從 `image.py` 抽出共用的 `save_media_upload()`，讓 `voice.py` 不需要依賴 `image.py`；`media_uploads` 表首次真正寫入 `media_type='audio'`（Step 1.3b 時已預留）；全專案 252 個測試全過、`src/bot/`／`submodules/llm`／`submodules/voice` 覆蓋率 100% | Claude（依 Robin「好」指示） |
| 2026-08-01 | **Step 1.4 追加修正**：Robin 測試時問「那現在能測試直接丟一個語音檔嗎」，Claude 誤以為 `message.audio`（上傳音檔）是範圍外的新功能並反問是否要開發；Robin 糾正「可是我記得我當初有說：除了照片和音檔外的檔案格式才無效誒」——FR-17 原文本來就承諾「僅支援圖片與音檔兩種檔案類型」，泛指所有音檔格式，不是只有錄音鍵那種，Step 1.4 完成當下只做了 `message.voice` 是範圍沒抓對 FR-17；修正 `webhook._extract_voice()` 改為同時偵測 `message.voice`／`message.audio` 並多回傳 `mime_type`，`voice.py`／`router.py` 一路透傳，新增 `voice._infer_extension()`（依 MIME type 對應正確副檔名，未知格式 fallback 為 `ogg`），避免使用者上傳的 MP3/M4A/WAV 被誤標成 `.ogg`；全專案 262 個測試全過、`src/bot/`／`submodules/llm`／`submodules/voice` 覆蓋率 100% | Claude（依 Robin 回報修正） |
| 2026-08-02 | Robin 問語音轉文字後是直接執行還是會先重發確認，得知是直接執行後提出風險情境：「使用者用語音說執行 A 決策，但 LLM 聽錯了，直接執行 B 決策，且已刪除的紀錄無法回頭補上」；選定「復誦＋最終執行前一定要打字答一次」方向，新增 FR-16a：`/clean-all-dialog`／`/clean-target-dialog`／主動記知識三個高風險 flow 判定 `CONFIRM` 後不再馬上執行，改為要求逐字打字輸入「確認執行」才真正動作，語音輸入這一步一律拒絕且不清除狀態，詳見 [chat-core SPEC.md](../chat-core/SPEC.md) ADR-9；全專案 274 個測試全過、覆蓋率 100% | Claude（依 Robin 選定方向實作） |
| 2026-08-02 | Robin 追問「如果卡在最終確認狀態時又發送一個新語音，這時會如何處理」，發現初版是先下載/轉錄才拒絕，浪費 Drive/Groq 額度；Robin 確認補上，`handle_voice_message()` 改為在下載/轉錄之前就短路拒絕，比照 FR-14/FR-15「先擋才不浪費額度」原則；全專案 275 個測試全過、覆蓋率 100% | Claude（依 Robin「補上吧」指示） |
| 2026-08-02 | Robin 指出印象中 FR-15 的 15 分鐘鎖定應該是「單次錄音超過 10 分鐘才觸發」，而不是「每次用語音都要等 15 分鐘」，與目前實作不符；核對後發現 FR-14／FR-15 原文其實是兩條獨立規則，目前只做了 FR-15（修正情境鎖定），漏了 FR-14 規則 1（單純超時就整體鎖定 15 分鐘），Robin 確認兩條都要做；新增 `voice.mark_duration_violation()`／`is_locked_out_from_duration_violation()`（獨立的記憶體 `ConversationStateStore` 儲存超時時間點）；`router.handle_voice_message()` 新增 `voice_lockout_store` 參數並整合檢查；`webhook.py` 新增長期持有的 `_voice_lockout_store`；全專案 284 個測試全過、覆蓋率 100% | Claude（依 Robin 確認的兩條規則實作） |
| 2026-08-02 | Robin 追問「語音功能被限制時／恢復時會提醒使用者嗎」；盤點後如實回覆：FR-14 規則 1 的拒絕回覆本來就有主動提示鎖定 15 分鐘，但 FR-15 修正窗口「開始」當下沒有主動提示，鎖定「到期」也完全沒有主動通知（機器人是被動回應訊息的架構，沒有排程/推播機制）；Robin 選擇先聚焦在較簡單的一項，回覆「好」；新增 `router._VOICE_TRANSCRIBED_REMINDER`，語音成功轉出文字後在回覆末尾主動附註 15 分鐘修正窗口提醒；鎖定到期主動通知維持現狀（需要額外排程機制，非本次範圍）；全專案 284 個測試全過、覆蓋率 100% | Claude（依 Robin「好」指示，聚焦範圍後實作） |
| 2026-08-02 | Robin 實測回報兩個部署後才浮現的問題：① `/function` 觸發 Telegram `sendMessage` 400 Bad Request，排查後確認根因是 `submodules/telegram/client.py` 的 `send_text()` 預設 `parse_mode="Markdown"`，但回覆文字多半由 LLM 自然語言生成、無法保證符合 Telegram 舊版 Markdown 語法，格式不符時 Telegram 會整則拒收——這個風險不限 `/function`，任何 LLM 生成的聊天回覆都可能中獎；Robin 選擇直接關閉 Markdown，`send_text()` 改為預設純文字傳送（詳見 [submodules-core SPEC.md](../submodules-core/SPEC.md) ADR-2 補充決策）② 語音功能因 `GDriveClient` 找不到 Service Account 金鑰檔（`FileNotFoundError: google_service_account.json`）而整段例外被安全網吞掉；確認 Robin 是把金鑰檔放在 Render 的 Secret Files 功能，而非環境變數——Render Secret Files 實際掛載路徑是 `/etc/secrets/<filename>`，但 `GDRIVE_KEY_FILE_PATH` 環境變數目前設定的是相對路徑 `google_service_account.json`，兩者對不上；這屬於 Render 部署環境變數設定問題，非程式碼邏輯錯誤，待 Robin 把 Render 上的 `GDRIVE_KEY_FILE_PATH` 改成 `/etc/secrets/google_service_account.json` 後應可解決，程式碼不需異動；全專案 285 個測試全過、覆蓋率 100% | Claude（依 Robin 回報排查並依選定方向修正） |
| 2026-08-02 | **Phase 1 Step 1.5 完成**：個資偵測與遮蔽機制（FR-13、FR-13a～FR-13d），展開為獨立 [docs/specs/privacy-masking/SPEC.md](../privacy-masking/SPEC.md)；語意層 LLM 呼叫用 Robin 確認的新申請專用 Key（`GEMINI_API_PRIVACY_KEY`），不佔用既有聊天配額（避免重演先前多次 429 的問題）；新增 `src/bot/privacy.py`（`mask_regex()`／`mask_with_llm()`／`mask_text()`），整合進 `chat.handle_chat_message()`（一般聊天含 `pending_user_knowledge`／`pending_name_confirm`／`pending_save_knowledge_confirm`）與 `image.handle_image_message()`（圖片說明文字）；語音因為統一轉文字後走既有 `handle_message()` 天然涵蓋；刻意排除 `/clean-target-dialog` 的搜尋主題（`topic`）不遮蔽，因為該指令本來就需要讓使用者用個資內容當關鍵字搜尋要刪除的紀錄，遮蔽會讓功能失效；全專案 326 個測試全過、覆蓋率 100% | Claude（依 Robin「先做吧」指示，經 AskUserQuestion 確認額度策略後實作） |
| 2026-08-02 | **gdrive 改用 OAuth 2.0**：Robin 實測語音上傳撞到 Google Drive API `403 storageQuotaExceeded`，查證後確認 Service Account 完全沒有 Drive 儲存額度，任何一般（非 Shared Drive）資料夾上傳皆會失敗，跟資料夾空間無關；Shared Drive 又需要付費 Google Workspace；經 AskUserQuestion 確認，Robin 選擇「改用 OAuth 以你本人身份上傳（推薦）」；新增 [submodules-core SPEC.md ADR-10](../submodules-core/SPEC.md)，`submodules/gdrive/client.py` 建構子改為 `refresh_token`／`client_id`／`client_secret`／`folder_id`，新增一次性本機互動授權腳本 `get_refresh_token.py`；`webhook.py` 兩處 `GDriveClient` 建構呼叫與環境變數同步更新（`GDRIVE_OAUTH_CLIENT_ID`／`GDRIVE_OAUTH_CLIENT_SECRET`／`GDRIVE_OAUTH_REFRESH_TOKEN`，取代 `GDRIVE_KEY_FILE_PATH`）；ADR-13 補充決策記錄本次變更；全專案 329 個測試全過、覆蓋率 100%（`get_refresh_token.py` 為一次性互動腳本，依 AGENTS.md 慣例排除於 TDD 範圍外） | Claude（依 Robin 於 AskUserQuestion 選定方向實作） |
| 2026-08-02 | **Phase 1 Step 1.6 完成**：基礎錯誤處理層（FR-19a、FR-20、FR-21）。經 AskUserQuestion 確認兩個範圍決策：① FR-20「我康復了」廣播改為新增 Owner 專屬指令 `/recovered`（Phase 1 沒有 AI 自主修復機制，由 Robin 自己判斷後手動觸發，廣播給所有已綁定家人、排除 Robin 自己）② FR-21 Gemini 免費額度監控 Phase 1 先跳過（官方無查詢即時用量的 API，本地節流計數器準確度不足，429 例外已經會走 FR-19a 私訊機制），只做 Neon 容量監控（`src/bot/monitoring.py` 的 `NeonCapacityMonitor`，借用 `/healthz` 既有的 10 分鐘 cron 頻率，達 80% 私訊 Robin、回落後重置避免重複告警）；FR-19a 簡化版通知：`webhook.py` 新增 `_notify_robin_of_error()`／`_summarize_user_input()`，例外發生時除了 log 額外私訊 Robin 完整 Traceback＋發生情境（不含 AI 自主診斷，留待 Step 2.4）；`submodules/cloudsql/client.py` 新增 `execute_query()` 逃生口供監控查詢使用；全專案 352 個測試全過、覆蓋率 100% | Claude（依 Robin 於 AskUserQuestion 選定方向實作） |
| 2026-08-02 | **Phase 1 Step 1.7 完成**：待辦事項模組（FR-31、FR-31a、FR-32）。經 AskUserQuestion 確認兩個範圍決策：① 待辦意圖偵測比照 FR-11「主動新增知識」的 LLM 標記模式，新增 `chat.py` 的 `_REQUEST_TODO_MARKER`（而非新增固定指令），符合 FR-31「自然語言描述」的精神 ② FR-31 跨模組歧義判斷 Phase 1 暫不實作（體態管理是 Phase 2、心情小記 Step 1.8 都還沒做，目前沒有其他模組可以比較），待那些模組做出來後再回頭補上。新增 `todos` migration（Robin 依 ADR-10 核准 SQL）；`src/bot/todo.py`（純邏輯：新增/查詢/標記/逾期/兩種推播判斷）；`chat.py` 新增待辦意圖偵測（三輪反問流程：`pending_todo_confirm`→`pending_todo_time`→`pending_todo_reminder`，時間解析不清楚時停留原地繼續反問，不硬存猜錯的時間）；`commands.py` 新增五個新 flow 處理函式（含查詢清單「我的待辦事項」／`/my_todos` 後標記完成/取消的 `pending_todo_list_action`／`pending_todo_action_confirm`）；`router.py` 整合觸發詞與 flow 分派；每日 08:00 固定推播與前 30 分鐘提醒都沒有獨立排程系統，比照 Step 1.6 借用 `/healthz` 既有的 10 分鐘 cron 頻率（`main.py` 新增 `_check_todo_pushes()`），但去重狀態刻意存在 `todos` 資料列本身（`reminded_30min_sent_at`／`daily_pushed_on`）而非記憶體 instance state，跟 Step 1.6 `NeonCapacityMonitor` 的取捨不同（Render 免費方案可能不定期重啟，待辦提醒的正確性值得多花欄位換取跨重啟持久性）；新增待辦不比照 FR-16a 的「逐字打字確認執行」關卡（低風險、可回頭用查詢清單修正，跟刪除紀錄/寫入知識庫的風險層級不同）；全專案 391 個測試全過、覆蓋率 100% | Claude（依 Robin「開始吧」指示，經 AskUserQuestion 確認範圍後實作） |
| 2026-08-02 | **Phase 1 Step 1.8 完成**：心情小記模組（FR-49、FR-50）。經 AskUserQuestion 確認兩個範圍決策：① 日記內容與 FR-50 個人成就回答都套用 FR-13 個資遮蔽（跟一般聊天／圖片說明文字／語音轉文字三個既有入口一致，新增第四個遮蔽入口）② 新建 `mood_journals` 表（Robin 依 ADR-10 核准 SQL）。流程分三輪：觸發「我想做心情筆記」／`/mood_journal` 先問心情分類（FR-56h 情境範例固定 6 選一：生氣/焦慮、難過/低落、疲倦/厭世、普通/平淡、平靜/放鬆、高興/興奮，接受編號或直接輸入分類名稱）→ 問完整日記內容並寫入 → 主動追問 FR-50 個人成就三選一提示（可用既有的「結束」／「沒有了」跳過，不強迫回答）；全程不需要呼叫 LLM（跟 Step 1.7 待辦事項需要解析模糊時間不同，心情分類固定 6 選一、個人成就有填就存沒填就跳過，純字串比對即可）；新增 `src/bot/mood.py`（純邏輯）、`commands.py` 三個新 flow 處理函式、`router.py` 整合觸發詞與 flow 分派；全專案 409 個測試全過、覆蓋率 100% | Claude（依 Robin「好，請繼續開發」指示，經 AskUserQuestion 確認範圍後實作） |
| 2026-08-02 | **Phase 1 Step 1.9 完成，Phase 1（MVP）全數 Step 完成**：客訴收集模組（FR-60～FR-63）。經 AskUserQuestion 確認兩個範圍決策：① 客訴內容仍套用 FR-13 個資遮蔽，即使 FR-62 是刻意的隱私例外——FR-62 的例外只針對 FR-10/FR-11「Robin 平常看不到家人個別對話」這條資料隔離規則，跟 FR-13「個資不能明碼存檔/送外部 API」是不同層面的隱私考量，兩者不衝突 ② 新建 `complaints` 表（Robin 依 ADR-10 核准 SQL），Gemini 分析結果只透過私訊送給 Robin、不落地存表。流程分兩輪：觸發「我要客訴你」／`/complaint` 固定提問（FR-60，不經過 LLM）→ 下一則訊息視為客訴內容，寫入 `complaints`（FR-61）後立即呼叫 Gemini 分析、私訊給 Robin（FR-62，分析報告不會回傳給提出客訴的使用者本人）；分析／私訊這段包一層 try/except，Gemini 額度用盡或 Telegram 傳送失敗都不影響「客訴已成功記錄」這個結果；FR-63 純屬 Robin 的人工產品決策，不涉及程式碼，不需要額外實作；新增 `src/bot/complaint.py`（純邏輯）、`commands.py` 兩個新 flow 處理函式、`router.py` 整合（含補上 `_dispatch_active_flow()` 原本缺少的 `telegram_client` 透傳參數）；全專案 417 個測試全過、覆蓋率 100% | Claude（依 Robin「好的，繼續開發吧」指示，經 AskUserQuestion 確認範圍後實作） |
| 2026-08-02 | **Bug 修正**：Robin 回報「打了『我要載妹妹到水里』，Robinson 完全不理我」，經比對截圖確認上一則訊息（問台中氣溫）先觸發了「不知道，請自行查詢」流程並設下 `pending_user_knowledge` 狀態，下一輪交給 Gemini 判斷這是新問題還是在回答；診斷根因：`webhook.py` 原本只有「拋例外」時才確保回覆非空（安全用語），沒拋例外但 `handle_message()` 剛好回傳空字串（例如 Gemini 那次生成剛好回空內容）時，`if reply:` 判斷為 False，完全不送出任何 Telegram 訊息，等於違反 FR-19h「嚴禁靜默或無明確狀態反饋」的精神；修正 `webhook.py` 新增獨立的空字串防呆（`not reply or not reply.strip()`），一律換成新增的 `_EMPTY_REPLY_FALLBACK`（措辭與例外安全語區分）並記警告 log；全專案 419 個測試全過、覆蓋率 100% | Claude（依 Robin 回報排查並修正） |
| 2026-08-02 | **Bug 追加修正（Robin 指出上一輪修的不是主因）**：Robin 實測完整重現：問氣溫觸發 `pending_user_knowledge` 後，緊接著講了一句完全無關的新事情「我要載妹妹到水里」（陳述句、不是問句），被誤判成「拒絕記錄」（回「好的，這次就不記錄囉！」），要再講一次才觸發正常的待辦流程；真正根因是 [chat-core SPEC.md](../chat-core/SPEC.md) ADR-6 三選一分流 prompt 裡「無關新內容」選項的措辭寫成「問一個新的『問題』」，用詞侷限在問句，使用者講陳述句時模型容易誤套進「拒絕」選項；修正把該選項改寫成「除了以上情況以外的任何內容」的 catch-all（詳見 chat-core SPEC.md ADR-6 追加修正）。同一次還一併修正 Robin 額外發現的兩個待辦事項問題：① 待辦時間解析（`commands._TODO_TIME_PARSE_PROMPT`）原本會在使用者只給「5:30」這種沒講上午/下午、也沒講哪一天的模糊時間時，自己猜成「今天下午」直接存檔，Robin 認為不該擅自猜測；改為明確要求日期與時段兩個條件都要有明確線索才算 CLEAR，否則一律 UNCLEAR 反問使用者講清楚 ② 建立待辦後固定回覆「到時候當天早上 8 點會主動提醒你一次」，但若建立當下已經過了今天的 8 點（例如中午設定當天下午要做的事），這句承諾其實不可能發生（`todo.check_and_push_daily_digest()` 只在剛好是 8 點那個小時才會觸發）；`commands.handle_todo_time_step()` 新增 `_now()`（比照 chat.py 同名函式方便測試 monkeypatch）判斷 due 日期是否為今天且現在是否已過 8 點，動態調整這句文案；全專案 421 個測試全過、覆蓋率 100% | Claude（依 Robin 回報排查並修正） |
| 2026-08-02 | **新增 FR-31b：待辦事項支援時間區間**：Robin 詢問「待辦事項是不是只能存單一時間點，不能存像『8/2 08:00～8/5 17:00』這種區間」，確認需要後開發。經 AskUserQuestion 確認三個設計決策：① `todos` 新增可選的 `start_at` 欄位（Robin 依 ADR-10 核准 `0016_add_start_at_to_todos.sql`），既有單一時間點待辦不受影響（`start_at` 為 NULL）② 前 30 分鐘提醒對區間待辦以 `start_at` 為基準（提醒「準備要開始了」）③ 每日 08:00 摘要對區間待辦只在開始日、結束日各出現一次，`todo.py` 的去重判斷從「曾經推播過就不再推播」改為「今天是否已經推播過」。`commands._TODO_TIME_PARSE_PROMPT` 新增選填的 `START_AT` 欄位，只有原始描述或回覆同時講出明確開始與結束時間才判斷為區間，開始/結束兩個時間點都要分別滿足既有的「日期明確」「時段不歧義」條件；`todo.py` 新增 `_format_when()`／`_format_digest_when()` 依是否為區間顯示不同文字，`check_and_push_reminders()` 改用 `COALESCE(start_at, due_at)` 判斷提醒基準；`commands.py` 新增 `_build_todo_time_confirmation_reply()` 依開始日/結束日的 8 點摘要是否還來得及組合不同措辭；全專案 436 個測試全過、覆蓋率 100% | Claude（依 Robin「現在就開始規劃設計」指示，經 AskUserQuestion 確認範圍與 SQL 後實作） |
| 2026-08-02 | **FR-49 補記/更新/刪除擴充**：Robin 提出「記帳、心情小記、體重、飲食、運動習慣都要有補記、更新、刪除、新增的功能」，經 AskUserQuestion 確認範圍：心情小記優先實作，記帳／體態管理（Phase 2 才開始的模組）從一開始就會內建 CRUD、不需要另外補。經 AskUserQuestion 確認兩個設計決策：① `mood_journals` 新增可選的 `entry_date` 欄位（Robin 依 ADR-10 核准 `0017_add_entry_date_to_mood_journals.sql`），設計比照 `todos.start_at`：一律由 app 端算好台灣時區日期後寫入，不依賴資料庫預設值 ② 刪除確認採簡單一輪 LLM CONFIRM/CANCEL（跟待辦事項完成/取消同一等級），不套用 FR-16a 逐字打字最終確認——FR-16a 保留給 `/clean-all-dialog`／`/clean-target-dialog`／主動記知識三個「一旦誤刪就大量、跨紀錄不可逆遺失資料」的高風險流程，心情小記單筆刪除錯了還能重新補記。新增「我要補記心情」／`/backfill_mood`（先問要補記哪一天，LLM 解析日期、只接受今天或過去，講清楚後接到既有分類/內容/成就三輪反問，寫入時 `entry_date` 用解析出的日期）與「我的心情紀錄」／`/my_mood_journals`（列出最近 10 筆，依 `entry_date` 新到舊排序，選編號後反問更新還是刪除——更新沿用原 `entry_date` 重新走一次分類/內容流程並改成 `UPDATE`，刪除走簡單一輪 CONFIRM/CANCEL）；`mood.py` 新增 `list_mood_journals()`／`format_mood_journal_list()`／`update_mood_journal()`／`delete_mood_journal()`，既有的 `create_mood_journal()` 新增必填的 `entry_date` 參數；`commands.py` 新增 6 個 flow 處理函式（`start_mood_backfill`／`handle_mood_backfill_date_step`／`start_mood_list`／`handle_mood_list_action_step`／`handle_mood_action_choice_step`／`handle_mood_delete_confirm_step`），既有的分類/內容兩步驟改為同時支援新增（`journal_id` 為 None）與編輯（`journal_id` 非 None，改用 `UPDATE`）；`router.py` 整合新觸發詞與 6 個新 flow 分派；全專案 465 個測試全過、覆蓋率 100% | Claude（依 Robin「繼續開發啊」指示，經 AskUserQuestion 確認範圍與 SQL 後實作） |
| 2026-08-04 | **Phase 2 Step 2.1 完成：記帳模組（FR-41～FR-44）**，Phase 2 第一個 Step。Robin 確認「下個階段就是 Phase 2 了」後說「請開始開發」，經 AskUserQuestion 確認範圍與 SQL：① FR-41「理財目標」解讀為「每月支出預算上限」，不需要收入-支出結餘概念，但交易紀錄本身仍支出/收入兩種都做 ② 交易分類採固定清單（比照心情小記）③ FR-44 視覺化這版先做文字摘要，不做圖表 ④ `users` 新增 `monthly_budget`／`budget_alert_50_sent_month`／`budget_alert_80_sent_month` 三欄（`0018_add_budget_fields_to_users.sql`）、新建 `transactions` 表（`0019_create_transactions_table.sql`，Robin 已核准兩份 SQL）⑤ FR-43 兩門檻觸發時機：50% 只在每月 15 日前檢查、80% 整月都檢查，各自每月最多推播一次。記帳從一開始就內建完整 CRUD（不像心情小記事後才補）：新增 `src/bot/finance.py`（分類清單/解析、交易 CRUD、月加總、FR-43 門檻判斷、FR-44 摘要組裝）、`commands.py` 12 個新 flow 處理函式（設定預算、新增/補記/更新/刪除記帳四步驟共用、查詢清單、摘要查詢）、`router.py` 整合 5 個新觸發詞與 9 個新 flow 分派、`main.py` 新增 `_check_finance_alerts()` 借用 `/healthz` 頻率觸發 FR-43 推播；全專案 539 個測試全過、覆蓋率 100% | Claude（依 Robin「請開始開發」指示，經 AskUserQuestion 確認範圍與 SQL 後實作） |
| 2026-08-04 | **Phase 2 Step 2.2 完成：體態管理模組（FR-45～FR-48）**。經 AskUserQuestion 確認四項設計：① 運動消耗卡路里改用 LLM 估算（而非 MET 公式），沿用 `GEMINI_API_BOT_KEY` ② 飲食三大營養素拆算同樣沿用 `GEMINI_API_BOT_KEY`（沒有食物資料庫，只能靠 LLM 語意判斷）③ FR-45 預警情境定案為目標達成通知（體重目標即時檢查、運動目標借用 `/healthz` 頻率排程加總累積分鐘數）＋目標期限前 7 天提醒＋BMI 異常提醒 ④ 三個子功能的目標設定共用一張 `body_goals` 表，用 `goal_type` 區分；運動目標單位由公里數改為累積運動分鐘數（Robin 指出「不是只有跑步」）。新建 `body_weight_logs`／`exercise_logs`／`diet_logs`／`body_goals` 四張表、`users` 新增 `height_cm`（`0023`～`0027` migration，Robin 依 ADR-10 核准）；新增 `src/bot/body.py`；身高體重/運動/飲食三個子功能從一開始就內建完整 CRUD；飲食目標因太主觀不做自動達成判斷，只能手動取消，是刻意的已知簡化；`commands.py`／`router.py`／`main.py` 完成整合；`src/bot/body.py` 達到 100% 覆蓋率，全專案 661 個測試全過 | Claude（經 AskUserQuestion 確認範圍與 SQL 後實作） |
| 2026-08-04 | **移除 Notion 後台，改採 Mobile App（React Native + Expo）**，新增 ADR-14（supersede ADR-1 的後台選型部分）。Robin 指示系統架構確立為「Telegram Bot（LUI）+ Mobile App（Rich GUI，唯讀 BI Dashboard）」；移除原 FR-54（Notion 相關描述），新增 FR-64（唯讀視覺化）、FR-65／FR-65a～FR-65c（多用戶登入機制：一般使用者 `user_name`／稱謂／`APP Access Token`，Robin 僅需 `user_name`／`APP Access Token`）；補充技術細節：`/api/app/*` API 設計原則（後端算好圖表 JSON 結構回傳，App 端只負責渲染）、React Native + Expo（Expo Router）基礎路由結構、資料模型補充（`users.app_access_token`）；登入與 App 詳細功能邏輯留待 Phase 4 對應 Step 開工時再深入展開，本次僅為 Placeholder。原獨立拆出的 Phase 5（Notion）取消，Mobile App 相關 Step 4.4／4.5（Placeholder）併入 Phase 4（與求職模組並列）；同步更新概要、系統架構總覽表、名詞定義（新增 APP Access Token）、NFR-1／NFR-5、ADR-4 理由 4、待確認事項 Notion 項次註記；本次僅為規格層級調整，未建立任何程式碼或資料表 | Claude（依 Robin 詳細指示調整規格） |
| 2026-08-04 | **Phase 2 Step 2.3 完成：重要通知模組（FR-53）**。Robin 提供完整需求：「超級重要通知（主角不能收到）」涵蓋家人生日與父親節/母親節，「重要通知（大家都收到）」涵蓋元旦、除夕/初一、固定 3/1 掃墓提醒、中秋、端午，各自附上固定文案；後續經 Robin 回覆補齊家人 `role`→生日對照（弟弟/大妹/小妹/爸爸/媽媽 5 位有明確生日，弟媳/大妹婿/小妹婿/阿姨 4 位生日不詳），經 AskUserQuestion 確認缺漏生日先跳過、改為新增自助指令補齊；經 AskUserQuestion 確認三項設計：① 農曆節日（除夕/初一/中秋/端午）改用 `lunarcalendar` 套件即時計算（純 Python、不需要網路），父親節固定西曆 8/8、母親節固定 5 月第二個星期日，皆不維護每年對照表 ② 固定台灣時間 08:00 推播，借用 `/healthz` 既有 10 分鐘 cron 頻率 ③ 父親節/母親節排除邏輯用 `users.role` 字串比對「爸爸」／「媽媽」，家人生日排除邏輯用 `user_id` 排除當事人自己。新增 `users.birthday`（`0028_add_birthday_to_users.sql`）、`important_notifications_log` 表（`0029_create_important_notifications_log_table.sql`，`UNIQUE(notification_key, year)` 年度去重）、`0030_seed_family_birthdays.sql`（寫入已知 5 位家人生日，Robin 已核准三份 SQL）；新增 `src/bot/notifications.py`（純邏輯：固定節日西曆日期計算、`FIXED_NOTIFICATIONS` 清單、收件人排除邏輯、生日比對、去重推播、`parse_birthday_input()` 生日格式解析）；新增 Owner 專屬「設定家人生日」／`/set_family_birthday` 指令（`commands.py`／`router.py`，流程比照既有 `/set_toggle`：先列出所有已綁定使用者選編號，再輸入生日）；`main.py` 新增 `_check_important_notifications()` 借用 `/healthz` 頻率；`src/bot/notifications.py` 達到 100% 覆蓋率，全專案 703 個測試全過 | Claude（依 Robin 提供的需求與 AskUserQuestion 確認範圍後實作） |
| 2026-08-05 | **Step 2.4 範疇簡化：取消 AI 自主診斷＋GitHub PR 自動化，新增 ADR-15（supersede ADR-7）**。開工前先盤點技術現況，發現 FR-19b「上網查詢」的前提（Gemini Search grounding）已因 submodules-core SPEC.md ADR-8 被整個移除、無法復原（Robin 不考慮開通計費帳戶），且 FR-19e 的 GitHub API 自動開分支/PR＋LLM 自動生成程式碼異動工程量與風險都偏高；跟 Robin 討論後，確認改用更輕量的方案：Robinson 只做「捕獲例外→完整 log（含 Traceback／觸發功能／使用者輸入摘要）上傳 Google Drive（複用既有 `GDriveClient`）→私訊 Robin 專屬連結」，其他使用者行為完全不變（僅收到既有「生病了」安全用語，不含任何連結或技術細節）；FR-19c／FR-19d／FR-19e 三條需求編號移除，FR-19b 改寫為新內容，FR-19f～FR-19i 不受影響；同步更新系統架構總覽表（移除「治理｜GitHub API」列）、NFR-5（`GITHUB_REPO` 移除，`GitHub Personal Access Token` 保留但註記用途限縮為 ADR-11 的 git push 驗證，非本次取消的 GitHub REST API 用途）、NFR-8（改寫為「完全不具備自動修改/部署能力」）、風險表（移除 AI 誤判/PR 逾時相關風險、新增 Drive log 生命週期風險）、測試策略 Phase 2 補充、實作計畫 Step 2.4 說明、待確認事項 FR-19e 項次註記；ADR-7 狀態改為 superseded；本次僅為規格層級調整，尚未動任何程式碼，實作待 Robin 確認 SPEC 內容後再進行 | Claude（依 Robin 提出的簡化方向調整規格，待確認後實作） |
| 2026-08-05 | **Phase 2 Step 2.4 完成：錯誤 log 雲端連結（FR-19b）**。Robin 確認 SPEC.md ADR-15 內容後指示「開始開發吧」。`webhook.py` 新增 `_upload_error_log()`（封裝 `GDriveClient.upload_file()` 呼叫，任何失敗——含 `GDRIVE_OAUTH_REFRESH_TOKEN`／`GDRIVE_OAUTH_CLIENT_ID`／`GDRIVE_OAUTH_CLIENT_SECRET`／`GDRIVE_FOLDER_ID` 環境變數未設定或 Drive API 暫時性錯誤——皆優雅降級回傳 `None`）與 `_ERROR_LOG_FILE_TEMPLATE`（完整、不截斷的 log 檔案內容，跟 Telegram 訊息本身的 3200 字元截斷版分開）；`_notify_robin_of_error()` 延伸為捕獲例外時額外組出 log 檔案內容並上傳，檔名格式 `error_log_{時間戳記}_{觸發功能}.log`，上傳成功則在私訊 Robin 的訊息末尾附加「📄 完整 log」連結行（`_ROBIN_ERROR_NOTIFY_TEMPLATE` 新增 `{log_link_line}` 欄位，無連結時為空字串）；其他使用者收到的 `_UNEXPECTED_ERROR_REPLY` 安全用語完全不受影響（兩條訊息路徑本來就完全獨立）。新增 6 個測試（`_upload_error_log()` 的成功/環境變數缺失/例外三種情境、`_notify_robin_of_error()` 的連結附加成功/Drive 上傳失敗優雅降級/環境變數缺失優雅降級），既有測試不需修改即全數通過；全專案 709 個測試全過，`webhook.py` 達到 100% 覆蓋率 | Claude（依 Robin「開始開發吧」指示實作） |
| 2026-08-05 | **新增 ADR-16：Telegram 故障時的 email 備援通知**。Robin 驗收 Step 2.4 時提出「如果壞掉的是 Telegram 本身，不就沒辦法通知？」，確認這是 FR-19b 設計時沒考慮到的單點故障。新增 `submodules/email`（見 submodules-core SPEC.md FR-11、ADR-11）：`EmailClient.send_text()` 用 `smtplib` 直打 Gmail SMTP（SSL），複用既有 `GMAIL_USER`／`GMAIL_PASSWORD`（原為 Phase 3 FR-23 預留但尚未使用）；`webhook.py` 新增 `_send_email_fallback()`，`_notify_robin_of_error()` 拆成「組裝內容」與「透過 Telegram 送達」兩段 try/except，只有後者失敗才觸發 email 備援，內容含完整 Traceback；email 本身也失敗只記 log，不再疊加第三層備援，這是刻意的設計邊界；同步更新 NFR-5（Gmail 密碼用途從預留變成實際使用）與風險表（新增「兩個備援管道同時故障」的低風險殘餘項目）；新增 11 個測試（`submodules/email/client.py` 5 個、`webhook.py` 6 個），全專案 720 個測試全過，`webhook.py`／`submodules/email/client.py` 皆達到 100% 覆蓋率 | Claude（依 Robin 提出的問題新增備援機制） |
| 2026-08-05 | **新增 Step 2.7、FR-66、ADR-17：Google Calendar 整合（規格層級，尚未實作）**。Robin 提出想加 Google Calendar 工具但不確定用途，討論後聚焦三個方向：待辦事項（FR-66a）、重要通知節日/生日（FR-66b）、體態目標期限（FR-66c）單向同步寫入行事曆；查證確認家人沒有 Google 帳號時可用私密 iCal 網址訂閱但延遲可能達 24 小時（不適合即時提醒，需與 Telegram 分工）、Calendar API 額度免費（10,000 次/分鐘，家庭規模用不到）；亦討論過「讀取行事曆做空檔查詢」（FR-66d）但因複雜度與隱私考量高出一個量級，明確排除本次範圍。確認設計：單一共用行事曆＋僅 Robin 帳號 OAuth 授權（比照 `gdrive` 模式，家人訂閱即可看，不需各自授權）；不拆分「待辦事項」與「行程」概念，MVP 先同步所有 `todos`；新增獨立 `submodules/calendar`，用專屬一組 OAuth 憑證（`calendar.events` 最小權限 scope），不與 `gdrive` 共用金鑰；同步更新系統架構總覽表、NFR-5（新增 3 把 Calendar 專屬金鑰）。本次僅為規格層級調整，尚未建立任何程式碼、子模組或資料表，實作待 Robin 完成 Google Cloud Console 設定與一次性授權後再進行 | Claude（依 Robin 討論方向撰寫規格） |
| 2026-08-05 | **Google Calendar 手動設定進行中：確認家人共用方式為免費 Google 帳號、補上隱私設計（ADR-17 決策 6／7）**。Robin 確認家人共用行事曆一律用免費 Google 帳號（非 iCal 訂閱備案）；新增 `submodules/calendar/get_refresh_token.py`（比照 `gdrive` 的一次性互動授權腳本，scope 固定 `calendar.events`，語法檢查通過，尚未串接 `client.py`）供 Robin 完成手動授權設定。Robin 提出兩個未涵蓋的設計缺口：① 家人若直接在 Google Calendar 編輯事件，Robinson 只寫不讀會完全不知道，且日後覆寫同一筆事件時會無聲蓋掉家人的手動修改；決議家人共用權限固定設為「查看所有活動詳細資料」（唯讀），純屬 Google Calendar 共用設定，不需要應用層程式碼 ② 部分待辦事項/體態目標可能是使用者不想讓其他家人看到的隱私；經 AskUserQuestion 確認 FR-66a／FR-66c 的建立流程各自新增一題「要不要同步到 Google 行事曆？」，每次明確詢問、不預設，體態目標比照待辦事項處理；FR-66b（節日/生日）維持全部自動同步，不涉及個人隱私。同步更新 ADR-17 決策 6／7、後果（新增 `todos.sync_to_calendar`／`body_goals.sync_to_calendar` 布林欄位規劃）；本次仍為規格層級調整＋一次性授權腳本，`CalendarClient` 本體與 DB migration 尚未動工 | Claude（依 Robin 提出的隱私與共用權限疑慮，AskUserQuestion 確認範圍後補上規格） |
| 2026-08-05 | **Phase 2 Step 2.7 完成：Google Calendar 整合（FR-66、ADR-17）**。Robin 完成 Google Cloud Console 手動設定（Calendar API、獨立 OAuth 用戶端、共用行事曆、家人以「查看所有活動詳細資料」唯讀權限共用）後指示開工。新增 `submodules/calendar/client.py`：`CalendarClient` 提供 `create_event()`／`update_event()`／`delete_event()`，全天事件用 `date`、有時間點事件用 `dateTime`+`Asia/Taipei` 時區；10 個測試，覆蓋率 100%。DB 依 ADR-10 核准 `0031_add_calendar_sync_to_todos.sql`／`0032_add_calendar_sync_to_body_goals.sql`：`todos`／`body_goals` 各自新增 `sync_to_calendar`（`BOOLEAN`）、`google_calendar_event_id`（`TEXT`）。整合三處：① `src/bot/commands.py` 待辦事項新增流程在 `pending_todo_reminder` 之後新增 `pending_todo_calendar_sync` 一輪反問，確認後才寫入並視情況建立事件（單一時間點待辦預設 30 分鐘時長，區間待辦用 `start_at`～`due_at`）；標記完成/取消時（`handle_todo_action_confirm_step`）如果有同步則刪除對應事件 ② `src/bot/notifications.py` 的 `check_and_push_important_notifications()` 新增 `calendar_client` 參數，固定節日/生日判斷通過時自動建立全天事件，不逐筆詢問（FR-66b） ③ `src/bot/body.py`／`commands.py` 體態目標設定流程比照待辦事項，只有講清楚期限的目標才會多問 `pending_goal_calendar_sync` 這一題，達成/取消時刪除對應事件。所有同步/刪除呼叫皆包 try/except 優雅降級（`calendar_client` 為 `None` 或 API 例外都不影響原本功能本身成功執行），`webhook.py`／`main.py` 新增 `_build_calendar_client()`，四個 `GOOGLE_CALENDAR_*` 環境變數未設定齊全時回傳 `None`。全專案 758 個測試全過，`submodules/calendar/client.py`／`src/bot/body.py`／`src/bot/notifications.py` 達到 100% 覆蓋率 | Claude（依 Robin「Google Calendar 已設定完，可以開工了」指示實作） |
| 2026-08-07 | **Phase 2 Step 2.5 完成：外部 API 重試機制（FR-19i）**。Robin 指示「請繼續做 Phase 2 Step 2-5」，經 AskUserQuestion 確認三個設計問題：① 程式碼放置方式選「抽成共用 retry 工具」（`submodules/retry`），是 submodules-core SPEC.md ADR-4「子模組彼此獨立、互不 import」的刻意例外 ② 重試判斷標準選「只重試暫時性錯誤」（連線失敗、逾時、HTTP 429／5xx），永久性錯誤直接往外拋 ③ 套用範圍確認這次只套用到 6 個既有子模組，104 求職爬蟲留到 Phase 4 開工時比照。新增 `submodules/retry`（`call_with_retry()`）；`llm`／`telegram`／`voice`／`gdrive`／`calendar`／`email` 六個 `client.py` 都套用，各自定義符合自己 SDK 例外型別的 `is_retryable` 判斷式；詳見 submodules-core SPEC.md ADR-13。全專案 795 個測試全過，7 個子模組（含新增的 `retry`）皆維持 100% 覆蓋率 | Claude（依 Robin「請繼續做 Phase 2 Step 2-5」指示，經 AskUserQuestion 確認範圍後實作） |
| 2026-08-07 | **Phase 2 Step 2.6 完成，Phase 2 全數 Step 完成：例外分級降級與決策執行狀態閉環回饋（FR-19f～FR-19h）**。Robin 指示「那接著開發 2-6，做完我再一起 git push」。`webhook.py` 新增 `_is_llm_failure(exc)`，用 `LLMQuotaGuardError`（本地端節流保護）與 `google.genai.errors.APIError`（涵蓋 Gemini 官方 `ServerError`／`ClientError`）兩種「唯獨呼叫 LLM 才會拋出」的例外型別判斷是否為 LLM 本身失敗；「一般感冒級」（`_GENERAL_COLD_REPLY`，其他元件異常）與「重大疾病級」（`_MAJOR_ILLNESS_REPLY`＋`_CRITICAL_SEVERITY_BANNER`＋`_broadcast_major_illness_to_family()` 廣播所有已綁定家人，LLM 本身失敗）分流；`_notify_robin_of_error()` 新增 `severity` 參數。FR-19h（決策執行狀態閉環回饋）經稽核確認屬架構層級已滿足：`finance.py`／`todo.py`／`mood.py`／`router.py` 皆無任何 `except` 包住 DB 寫入呼叫，資料異動失敗時例外會一路傳到 `webhook.py` 單一進入點被新增的分級邏輯接住，不需逐一修改各功能模組。全專案 810 個測試全過，`webhook.py` 維持 100% 覆蓋率；本次僅本地 commit，未 push（Robin 指示待後續一起 push） | Claude（依 Robin「那接著開發 2-6」指示實作） |
| 2026-08-07 | **Phase 3 Step 3.1 完成：每日重點技術分享（FR-22、FR-23）**。Robin 指示「從 3-1 開始吧」，經 AskUserQuestion 確認三個設計問題：① TLDR 電子報辨識方式選「寄件者網域比對」（`tldrnewsletter.com`）② IThome／TechCrunch 新聞來源選「RSS Feed」③ 去重機制核准於 `users` 表新增 `skill_growth_pushed_on`（DATE）欄位（依 ADR-10 流程，`0033_add_skill_growth_pushed_on_to_users.sql`），比照 `todos.daily_pushed_on` 慣例。`submodules/email` 新增 `fetch_yesterday_emails_from_domain()`（IMAP 讀信，見 submodules-core SPEC.md ADR-11 追記）；新增 `submodules/newsfeed`（`NewsFeedClient`，`requests`＋標準函式庫 `xml.etree.ElementTree` 解析 RSS，見 ADR-14）；新增 `src/bot/skill_growth.py`：`check_and_push_daily_digest()` 固定台灣時間 08:00 推播，三個來源（TLDR／IThome／TechCrunch）任一抓取失敗只記 log、視為當日無內容，不影響其他來源與整體推播；三個來源都沒內容時仍推播固定的「今天沒有新內容」訊息（NFR-10）；`skill_growth` 功能開關（`owner_only=True`）關閉時跳過；Gemini 呼叫改用新增的獨立 `GEMINI_API_SKILL_GROWTH_KEY`。`main.py` 新增 `_check_skill_growth_digest()` 借用 `/healthz` 既有頻率。同步補齊前次 Step 2.5／2.6 遺留未打勾的 Step 2.5／2.6／NFR-9／NFR-10 checkbox 與缺漏的變更記錄列。全專案 878 個測試全過（`src/bot/skill_growth.py`／`submodules/email/client.py`／`submodules/newsfeed/client.py` 皆達 100% 覆蓋率）；本次僅本地 commit，push 留待 Robin 之後一起處理 | Claude（依 Robin「從 3-1 開始吧」指示，經 AskUserQuestion 確認範圍後實作） |
| 2026-08-07 | **Step 3.1 當日修正：拆成「23:00 收集／08:00 推播」兩階段，改用 `skill_growth_digests` 表**。Robin 驗收時提出三點：① TLDR 電子報寄件者確認為 `dan@tldrnewsletter.com`（沿用既有的網域比對邏輯）② 排程改為固定台灣時間 23:00 收集「當天」的信件與新聞（不是原本 08:00 即時抓「昨天」），隔天 08:00 才推播，看板固定顯示「前一晚收集到的內容」③ 三個來源都沒抓到任何內容時，看板固定回覆「未獲得最新技術分享」（不是原本較長的口語化訊息）。經 AskUserQuestion 確認新的 DB 設計：新增 `skill_growth_digests` 表（`digest_date` UNIQUE 約束防止 23:00 那個小時內重複收集、`summary_text` 可為 `NULL` 代表當天三個來源都沒內容、`pushed_on` 記錄推播去重日期），取代原本規劃的 `users.skill_growth_pushed_on` 欄位（因尚未 push／套用過，直接修改 `0033` migration 內容，不留下加欄位又刪欄位的歷史包袱）。`submodules/email` 的 `fetch_yesterday_emails_from_domain()` 改為 `fetch_emails_from_domain_on_date(sender_domain, target_date)`，`submodules/newsfeed` 移除不再需要的 `fetch_yesterday_articles()` 便利方法（呼叫端一律指定日期，不假設「今天」或「昨天」）；`src/bot/skill_growth.py` 拆成 `collect_and_store_daily_digest()`（23:00，寫入 DB）與 `check_and_push_daily_digest()`（08:00，讀 DB 推播；找不到前一晚收集結果時同樣回覆固定訊息並補寫一筆去重標記，避免同一小時內重複推播）；`main.py` 對應拆成 `_check_skill_growth_collection()`／`_check_skill_growth_push()` 兩個 `/healthz` 檢查函式。全專案測試結果見下一則記錄 | Claude（依 Robin 驗收回饋，經 AskUserQuestion 確認 DB 設計後修正） |
| 2026-08-07 | **功能開關拆分：`skill_growth` 拆成 `tech_intel`／`certificate`／`language` 三個獨立開關**。Robin 驗收 Step 3.1 後回饋：TOEIC（證照準備）跟技術情報（YouTube 技術情報／新聞電子報分享）性質不同，一個是語言/硬實力學習追蹤、一個是資訊訂閱推播，不該共用同一把開關；並補充語言學習（英文口說、其他語言，尚未開發）也該獨立於證照準備之外。經 AskUserQuestion 確認 key 命名（`certificate`／`tech_intel`／`language`，比照既有 8 個開關「不加模組前綴」的命名風格）與既有資料處理方式（既有 `skill_growth` 開關資料搬移到 `tech_intel`，保留原本開啟狀態）。新增 migration `0034_split_skill_growth_toggle.sql`（Robin 依 ADR-10 核准）：動態尋找並移除 `feature_toggles.feature_key` 現有 CHECK 約束、新增涵蓋 10 個代號的新約束，`UPDATE ... SET feature_key = 'tech_intel' WHERE feature_key = 'skill_growth'`；`templates.FEATURE_LIST` 對應拆成三筆項目；`src/bot/skill_growth.py` 的 `_FEATURE_KEY` 改為 `"tech_intel"`；YouTube 技術情報模組（FR-57～59，尚未開發）確認共用 `tech_intel`，與每日技術分享同屬「技術情報訂閱」性質。測試更新：`test_skill_growth.py` 的 `feature_key` 斷言、`test_toggles.py`／`test_commands.py`／`test_router.py` 硬編碼的「8 個模組」改為「10 個模組」（含 `toggle_by_index` 邊界測試 index 由 9 改為 11）。全專案 888 個測試全過，`skill_growth.py`／`toggles.py`／`templates.py` 皆維持 100% 覆蓋率；本次先本地 commit，push 留待 Robin 之後一起處理 | Claude（依 Robin 提出的拆分需求，經 AskUserQuestion 確認命名與資料搬移方式後實作） |
| 2026-08-07 | **Phase 3 Step 3.2 完成：TOEIC 雙軌題庫 Pipeline（FR-24、FR-25a～FR-25f，新增 ADR-18），同日兩次追加修正（整包音檔切割排除說明語音、`exam_type` 泛用化改名 `certificate_questions`）**。詳細設計決策與實作內容見 ADR-18、上方 FR-25a～FR-25c 條文與 PROGRESS.md 對應里程碑；新增 `src/bot/toeic.py`、`toeic_questions`（後改名 `certificate_questions`）／`toeic_vocab_questions` 表（`0035`～`0038` migration）。全專案 942 個測試全過 | Claude（依 Robin「開發 3-2 吧」指示，經 AskUserQuestion 確認範圍後實作） |
| 2026-08-07 | **Step 3.3 規格定案（新增 ADR-19）＋第一階段實作：答案照片比對機制（FR-27 部分）**。經多輪對話與 AskUserQuestion 確認每日 08:00 推播、正解改用 Robin 拍照上傳的 `_ans` 答案照（取代 AI 推論）、FR-29 改為純文字彈性問答（不做圖表）、作答紀錄採統一表串連軌道一/軌道二等設計，詳見上方 ADR-19 全文；延伸 `src/bot/toeic.py` 完成 `_ans` 檔名比對補正解／詳解機制，新增 `answer_logs`／`certificate_goals`／`exam_official_scores` 三張表（`0039`～`0042` migration）。全專案 952 個測試全過 | Claude（依 Robin「都已經確認了，直接開工吧」指示定案規格並實作第一切片） |
| 2026-08-08 | **Production 事故修復：`/healthz` 逾時＋migration 累積未套用（根因 `CloudSQLClient.execute()` 對含 `%` 字元的 SQL 註解誤觸發格式化解析）**。詳見 PROGRESS.md 對應兩則里程碑與 submodules-core SPEC.md 變更記錄；`/healthz` 10 個排程檢查改丟背景 daemon thread、`CloudSQLClient.execute()`／`execute_query()` 改為 `params is None` 時不帶第二參數呼叫。全專案 958 個測試全過，push 後 Robin 確認 25 筆積壓 migration（`0018`～`0042`）一次套用成功 | Claude（依 Robin 回報的 production 錯誤診斷並修復） |
| 2026-08-08 | **Step 3.3 每日推播/作答細部設計定案（新增 ADR-20）＋每日 08:00 推播出題機制實作完成（FR-26）**。經多輪 AskUserQuestion 確認出題數量/比例依 `exam_type` 是否為 TOEIC 而不同、新題:複習題比例 7:3、作答格式限 A/B/C/D、23:00 靜默跳過、彈性排程比照 `budget_overrides` 三種語意，詳見上方 ADR-20 全文；新增 `certificate_daily_settings`／`certificate_daily_schedule_overrides`／`certificate_daily_assignments` 三張表（`0043`～`0045` migration）與 `src/bot/certificate_quiz.py`（出題比例拆分、複習池選題、`/healthz` 推播排程，決策 3/4/5 的對話觸發部分留待「作答與批改流程」實作）。全專案 993 個測試全過，`certificate_quiz.py` 達 100% 覆蓋率；本次先本地 commit，push 留待 Robin 之後一起處理 | Claude（延續 ADR-20 定案設計實作出題引擎） |
| 2026-08-08 | **彈性排程新增第四種語意「平攤到鄰近幾天」，ADR-20 決策 5/6 補充**。Robin 補充「把今天的平攤到其他天（儘量挑離今天近的日期）」的用法，並要求算完分攤方案要先給他確認、同意才寫入，不能自動生效；經 AskUserQuestion 確認演算法規則：明天起連續每天 +1 題、攤完為止，命中既有排程覆蓋則跳過往後找。規格層級調整，實際計算與確認對話流程留待「作答與批改對話流程」實作 | Claude（依 Robin 補充的需求，經 AskUserQuestion 確認演算法規則後更新規格） |
| 2026-08-08 | **Phase 2 體態管理擴充：新增腰圍設定（FR-46）**。Robin 要求新增「腰圍」，設計比照身高（初始設定、變動才修正，非每日紀錄）；明確定位為參考指標、非必要，BMI 計算不使用腰圍。經 AskUserQuestion 確認「記體重後順便問腰圍」的頻率：只有使用者從未設定過腰圍時才問，設定過之後不會每次記體重都重複問。新增 `users.waist_cm`（`0046_add_waist_to_users.sql`，合理範圍 40～200 公分）；`src/bot/body.py` 新增 `is_waist_reasonable()`／`set_waist()`／`get_waist()`，鏡射身高既有實作；`src/bot/commands.py` 新增獨立「設定腰圍」／`/set_waist` 單輪流程，並修改 `handle_weight_value_step()`：新增一筆體重紀錄（非 `/my_weight_logs` 觸發的更新）且使用者尚未設定腰圍時，順便詢問，回覆可直接輸入公分數字或任意方式跳過（不強迫明確拒絕）；`src/bot/router.py` 註冊對應觸發詞與狀態分派。TDD 全程，新增/更新 `test_body.py`／`test_body_commands.py`／`test_body_router.py`，`body.py` 與新增程式碼皆有測試覆蓋，全專案 1009 個測試全過 | Claude（依 Robin 提出的需求，經 AskUserQuestion 確認詢問頻率後實作） |
| 2026-08-08 | **Phase 4 Mobile App 新增功能說明：藍牙體重計整合（新增 FR-64a，規格層級，Phase 4 尚未開工不涉及程式碼）**。Robin 已購入支援藍牙廣播的體重計，並用 nRF Connect for Mobile 實測確認可從 Manufacturer Data 取得體重值，提供完整解析公式（取 hex 資料索引 2、3 組成 16 位元整數，除以 100 得公斤數）。記錄設計：App 端「開始測量」按鈕觸發 10 秒藍牙掃描，逾時顯示「未取得您的體重值」；體重紀錄維持雙入口（App 藍牙掃描或 Telegram 手動輸入皆可），兩者最終寫入同一張 `body_weight_logs`。這是 FR-64「App 不寫資料」原則的唯一例外（因量測動作天生發生在手機端），已同步修正 FR-64 條文加註例外說明；App 端裝置篩選、藍牙例外處理、寫入 API 路由細節留待 Phase 4 開工時展開 | Claude（依 Robin 提供的藍牙測試結果與解析公式撰寫規格） |
| 2026-08-08 | **Step 3.3 作答與批改流程 + 20:00 提醒 + 彈性排程對話流程實作完成（FR-27、FR-28，ADR-20 決策 3～6 全數落地）**。Robin 指示「腰圍設定已經開發好了，再來接著開發這個吧，開發完我一併 push」，並重申「平攤」語意的確認機制。新增 `answer_logs.assignment_id`／`users.certificate_answer_reminder_sent_on` 兩欄位（`0047`／`0048` migration）；新增 `src/bot/certificate_answer.py`（待作答清單查詢、題目呈現內容組裝、批改寫入、20:00 提醒推播）與 `src/bot/certificate_schedule.py`（MOVE/CANCEL/RANGE/SPREAD 四種語意純邏輯，SPREAD 支援依 Robin 回饋的天數重算）；`commands.py` 新增「開始作答」（一次一題、只接受 A/B/C/D、跨多個 exam_type 依序做完）與「調整出題排程」（先選 exam_type → 自由文字描述 → LLM 分類語意 → SPREAD 進入「列出方案 → 確認或依建議重算」迴圈，同意才寫入）兩組對話流程；`router.py` 註冊「開始作答」／`/start_quiz`、「調整出題排程」／`/adjust_quiz_schedule` 觸發詞與四個新 `pending_*` 狀態分派；`main.py` 新增 `_check_certificate_answer_reminder()` 掛上 `/healthz` 背景排程（第 11 個排程檢查）。全專案 1090 個測試全過，新增的 `certificate_answer.py`／`certificate_schedule.py` 與 `commands.py`／`router.py`／`main.py` 新增程式碼皆有對應測試覆蓋；本次僅本地 commit，push 留待 Robin 之後一併處理 | Claude（依 Robin「腰圍設定已經開發好了，再來接著開發這個吧」指示實作） |
