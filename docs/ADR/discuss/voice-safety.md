# 語音訊息安全機制 討論紀錄

> 本檔案彙整原記錄於 robinson SPEC.md ADR-5（語音部分）的討論；語音最終執行確認（FR-16a）的討論記錄於 `docs/ADR/discuss/chat-core.md` ADR-9，不在此重複。

## 2026-07-29 [標籤：AI] 語音時長與修正窗口的安全護欄

**狀態**：accepted

**背景**：語音轉文字若無限制易消耗大量 Token（如誤傳會議錄音）。

**討論內容**：比較「事後人工審查」（不即時、無法防止額度已被消耗）與「完全禁止語音修正」（使用者體驗差，且不符合需求描述）等方案。

**決策**：語音超過 10 分鐘強制中斷並提示；語音轉文字結果的修正僅接受文字輸入，且此限制僅在該筆語音送出後 15 分鐘內生效，超過 15 分鐘語音模式即恢復正常使用。

**理由**：對應 Robin 明確列出的「Robinson 警察證」規則，屬於安全與成本雙重考量的硬性限制。

**後果**：需要在對話流程中加入語音時長預檢查邏輯（`src/bot/voice.py` 的 `exceeds_duration_limit()`／`is_within_correction_window()`）。

## 2026-08-02 [標籤：AI] FR-14 規則 1 補強：單次語音本身超時的全面鎖定，與 FR-15 修正情境鎖定是兩條獨立規則

**狀態**：accepted

**背景**：Robin 指出印象中「15 分鐘鎖定」應該是「單次錄音超過 10 分鐘才觸發」，而不是「每次用語音都要等 15 分鐘」，與目前實作不符。核對後發現 FR-14／FR-15 原文其實是兩條獨立規則，先前只做了 FR-15（修正情境鎖定），漏了 FR-14 規則 1（單純超時就整體鎖定 15 分鐘）。

**決策**：單次語音「本身」超過 10 分鐘時，語音功能整體鎖定 15 分鐘，這段期間任何語音訊息都拒絕（不限於修正情境），與 FR-15 的「修正情境」鎖定是獨立的兩條規則。

**後果**：新增 `voice.mark_duration_violation()`／`is_locked_out_from_duration_violation()`，用獨立的 `ConversationStateStore` 記憶體儲存最近一次超時的時間點（因為超時的語音一開始就不會寫入 `media_uploads`，無法沿用 FR-15 查 DB 時間戳記的作法）。

## 2026-08-02 [標籤：AI] 語音功能鎖定/恢復的主動提示範圍

**狀態**：accepted

**背景**：Robin 追問「語音功能被限制時／恢復時會提醒使用者嗎」；盤點後如實回覆：FR-14 規則 1 的拒絕回覆本來就有主動提示鎖定 15 分鐘，但 FR-15 修正窗口「開始」當下沒有主動提示，鎖定「到期」也完全沒有主動通知（機器人是被動回應訊息的架構，沒有排程/推播機制）。

**決策**：Robin 選擇先聚焦在較簡單的一項——語音成功轉出文字後，在回覆末尾主動附註 15 分鐘修正窗口提醒（`router._VOICE_TRANSCRIBED_REMINDER`）；鎖定到期主動通知維持現狀，需要額外排程機制，非本次範圍。

## 2026-08-16 [標籤：AI] 全站語音轉文字確認機制（併入 Phase 6 第二批 2g 一起開工）

**狀態**：accepted

**背景**：Robin 在飲食（2g）情境流程討論中指出，語音辨識（Groq Whisper）轉出來的文字可能跟使用者實際講的內容有落差，如果直接當成輸入內容送進既有的 pending flow／自由聊天，AI 聽錯的內容會被誤當成使用者的真實輸入，寫進資料庫或觸發不對的分支。Robin 要求「Telegram 所有套用到語音的功能都要有這個確認流程」，範圍是全站（不限 2g 飲食），因為 `handle_voice_message()` 是全域單一入口，所有既有語音功能（待辦、心情、運動、記帳、證照、求職、收藏旅遊、自由聊天…）都共用同一套「轉文字→直接當打字輸入」的邏輯。

**討論內容**：比較「只套用到 2g 飲食新流程」（風險小但無法解決既有功能同樣的問題，且使用者明確要求全站）與「全站一併套用」（影響既有已上線功能行為，但架構上只需要改單一攔截點 `handle_voice_message()`，不用逐一修改 130 多個既有 pending flow 函式）。因為 `handle_voice_message()` 轉錄成功後本來就是統一呼叫 `handle_message()` 分派，改成「先存一個 `pending_voice_confirm` 狀態、包住轉錄前原本卡在的 `resume_state`」这個單一攔截點方案，下游所有既有邏輯完全不用改。

**決策**：語音轉錄成功後，不直接把轉錄文字送進 `handle_message()`，改成：
1. 貼出轉錄文字＋「✅ 正確，繼續」按鈕（`voice_confirm:accept`），並把轉錄前原本卡在的狀態存進 `pending_voice_confirm` 的 `resume_state`（可能是任何一個既有 pending flow，也可能是 `None`＝自由聊天）。
2. 使用者按「✅ 正確，繼續」：還原 `resume_state`，用轉錄文字接回原本流程（`handle_callback_query()` 的 `voice_confirm:accept` 分支）。
3. 使用者不按按鈕、直接打字：視為用打字修正剛剛聽錯的內容，同樣還原 `resume_state`，改用這次打的文字接回（`_dispatch_active_flow()` 的 `pending_voice_confirm` 分支）。

這個機制跟既有 FR-14（語音超時鎖定）／FR-16a（`_FINAL_CONFIRM_FLOWS` 一律拒絕語音）互不衝突，那兩個檢查仍在轉錄之前就短路擋下，不受影響；FR-15（15 分鐘修正窗口）解決的是「使用者想用語音改前面內容」，跟這次「AI 聽錯」是不同問題，兩者疊加使用。

**後果**：`src/bot/router.py` 的 `handle_voice_message()`／`handle_callback_query()`／`_dispatch_active_flow()`、`src/bot/webhook.py` 的 callback_query 分支（原本不需要 LLM/Telegram/GDrive Client，現在為了接回語音確認後的任意流程而補齊注入）都需要修改，影響範圍涵蓋所有已上線的語音入口（2c 心情/運動、2f 待辦事項等），語音使用體驗多了一輪確認。詳見 `docs/specs/SPEC.md` FR-14／FR-15／FR-17 段落與 `docs/specs/PROGRESS.md` Phase 6 第二批 2g 記錄。
