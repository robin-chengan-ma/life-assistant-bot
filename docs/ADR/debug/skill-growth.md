# 技術情報／TOEIC 雙軌題庫 修復紀錄

> 同一功能的多次除錯都寫在同一個檔案，依時間往下附加新段落，不要開新檔案。不論有沒有改 code 都要記。

## 2026-08-24 TOEIC 單字題生成撞本地端節流上限

**現象**：Robin 提供 Render 正式環境錯誤 log，2026-08-23 14:02:15（UTC，換算台灣時間 22:02，正好對上 TOEIC 週排程「固定週日 22:00 執行」）記錄 `src.bot.toeic: Gemini 生成 TOEIC 單字題失敗`，例外是 `submodules.llm.client.LLMQuotaGuardError: 最近 60 秒內已呼叫 8 次，超過本地端節流門檻（8 次/分鐘），暫緩呼叫避免浪費額度`。

**排查過程**：讀 `src/bot/toeic.py::generate_track2_vocab_questions()`：預設每週要生成 `toeic_weekly_question_count`（預設 21）題，迴圈最多嘗試 `count * 3 = 63` 次，但兩次呼叫 `llm_client.generate_text()` 之間完全沒有延遲；`except Exception: continue` 把 `LLMQuotaGuardError`（本地端節流保護，見 `submodules/llm/client.py`，同一把 `GEMINI_API_TEXT_KEY` 60 秒內最多 8 次）當成一般失敗處理，被擋下時立刻進下一輪、不等待。結果是前 8 次幾乎在同一秒內打完，第 9～63 次全部在毫秒等級的時間內連續被節流擋下、瞬間燒光所有嘗試機會，`max_attempts=63` 形同虛設，實際只有前段極少數呼叫真正有機會生成成功。

**根因**：呼叫端對「本地端節流保護觸發」與「其他暫時性/永久性失敗」一視同仁地立即 `continue`，沒有針對節流觸發做等待，導致原本設計用來確保「多嘗試幾次總能湊到目標題數」的重試上限，在被節流擋下的瞬間就被燒光，失去原本的保護意義。

**修復方式**：`generate_track2_vocab_questions()` 新增可注入的 `sleep_func` 參數（預設 `time.sleep`）；捕捉 `submodules.llm.client.LLMQuotaGuardError` 時單獨處理：不計入 `attempts`（退回計數，不算浪費一次嘗試機會），並呼叫 `sleep_func(_QUOTA_GUARD_RETRY_DELAY_SECONDS)`（8 秒）等節流視窗消化一些額度再重試；其他例外（格式不符、DB 寫入衝突等）維持原本「記 log 略過、計入 attempts」的行為不變。

**驗證方式**：新增 `tests/bot/test_toeic.py::test_generate_track2_waits_and_retries_on_quota_guard_error_without_wasting_attempt`（驗證被節流擋下時會等待再重試、最終仍能成功）、`test_generate_track2_quota_guard_retries_do_not_count_toward_max_attempts`（驗證節流擋下不會消耗 `max_attempts`）。全專案 `pytest -q` 1621 passed（`test_migration_sql.py` 1 項因沙盒環境限制失敗，屬既有已知問題），`ruff check .` 對本次異動檔案全過。**尚待 Robin 在下次週排程（週日 22:00）觀察是否能穩定生成接近目標題數（21 題）的單字題**。
