# 平台核心入口 討論紀錄

> 同一功能的多次討論都寫在同一個檔案，依時間往下附加新段落。本檔案彙整原 `docs/specs/platform-auth/SPEC.md` 的 ADR，以及原記錄於 robinson 母 spec、與通關密碼機制相關的 ADR-3、ADR-8（因這兩則討論的是同一個功能，遷移時合併於此，robinson 端不重複保留）。

## 2026-07-29 [標籤：AI] 通關密碼機制選型

**狀態**：accepted

**背景**：家人共用同一個 Bot，需要輕量級但可控的准入機制，且不希望增加額外 UI（如註冊頁面）。

**討論內容**：比較「Telegram 白名單（手動加 chat_id）」「邀請連結（deep-link）」「Robin 私下分發一次性通關密碼」三種方案。白名單需要 Robin 手動取得每位家人的 chat_id，操作不直覺；邀請連結需額外實作 deep-link 與過期邏輯，超出 MVP 範圍。

**決策**：Robin 於資料庫預先建立通關密碼清單並私下分發；使用者第一次互動時在 Telegram 對話中輸入密碼即完成啟用，密碼使用後標記 `is_used=1` 失效。

**理由**：完全在聊天介面內完成，不需額外頁面；一次性設計避免密碼被轉發濫用。

**後果**：需設計密碼與使用者的一對一綁定資料表，並在密碼輸入錯誤時給予合理提示（不可洩漏密碼是否存在等資安細節）。

## 2026-07-30 [標籤：AI] 通關密碼設定改用對話式狀態機，不做後台表單

**狀態**：accepted

**背景**：原本 FR-6 只寫「Robin 於資料庫預先建立通關密碼清單」，沒有定義 Robin 實際上要怎麼操作。若新增網頁後台表單設定密碼，會違反「越少 UI 設定越好」的核心理念，也會多一套獨立的驗證/部署成本。

**討論內容**：比較「Robin 直接下 SQL 手動寫入」（最快但容易手誤、不符合聊天完成操作的體驗）與「引導式對話流」（複用 Telegram 介面，天然形成簡單的資料驗證）。

**決策**：新增僅限 Robin 觸發的「引導式設定對話流」（Conversation State Machine）：Robin 用 `/set_invite_codes` 或「設定通關密碼」文字觸發 → Robinson 逐一詢問稱謂與密碼 → 寫入 Neon DB → 循環直到 Robin 說「沒有了」結束。

**理由**：完全複用 Telegram 對話介面，不需要另外開發/部署任何網頁表單；對話式一問一答天然形成簡單的資料驗證，符合 Robin 一貫「用聊天完成大部分操作」的產品設計原則。

**後果**：需要在對話處理層實作一個簡單的「設定模式」狀態機，且必須確認只有 Robin 的 `telegram_user_id` 能觸發此模式，避免家人誤觸或惡意觸發。

## 2026-07-30 [標籤：AI] ADR-1：Webhook 訊息解析不依賴 `python-telegram-bot`，改用原生 dict 直接解析

**狀態**：accepted

**背景**：`requirements.txt` 原本列了 `python-telegram-bot`，但該套件是 async-first 設計（`Application`/`Dispatcher` 跑在自己的 asyncio event loop），塞進 Flask 這種同步 WSGI framework需要額外的 async/sync 橋接。

**討論內容**：比較方案 A（`python-telegram-bot` 的 `Update.de_json` + 手動呼叫 handler，有型別化物件但仍需引入整包相依）與方案 B（直接讀取原生 JSON dict，零額外相依但沒有型別檢查）。

**決策**：採方案 B，直接解析原生 JSON dict；`requirements.txt` 移除 `python-telegram-bot`。

**理由**：本專案目前只需要處理文字訊息與極少數指令，不需要 `python-telegram-bot` 提供的複雜功能；方案 B 更輕量、更好測試（純函式接 dict，不需要 mock 一整包 SDK）。

**後果**：`requirements.txt` 移除 `python-telegram-bot`；所有 webhook 解析寫在 `src/bot/webhook.py`，用 unit test 覆蓋各種缺欄位/格式錯誤的邊界情況。

## 2026-07-30 [標籤：AI] ADR-2：Owner 設定對話流的狀態存放於記憶體，不落地到資料庫

**狀態**：accepted

**背景**：FR-6b 的多輪對話（詢問稱謂→收密碼→循環）需要在多次 HTTP request 之間記住「現在問到哪一步」。Render 免費方案單一 process 執行，閒置會休眠，喚醒後記憶體會被清空。

**討論內容**：比較方案 A（存進 Neon 新表 `conversation_states`，重啟不遺失但多一張表、多一輪 ADR-10 審核）與方案 B（存在 process 記憶體的全域 dict，零額外資料表但重啟/休眠喚醒後中途狀態會遺失）。

**決策**：採方案 B。

**理由**：這個對話流只有 Robin 會用、使用頻率低（新增家人才觸發一次），且配合 cron-job.org keep-alive 很少真的進入休眠；就算遺失狀態，代價只是 Robin 重新走一次設定流程，不影響任何使用者資料正確性。

**後果**：若之後這個對話流變得複雜（例如要支援多人同時設定、或步驟變多），需要重新評估搬到資料庫；`src/bot/state.py` 需明確註明這是 in-memory、非持久化。
