# infra 排查紀錄

## 2026-08-24 `/healthz` 每次觸發都開 14 個獨立資料庫連線，疑似是 Neon compute CU-hours 額度快速消耗的主因

**現象**：Robin 收到 Neon 官方 email「You've used 80% of your monthly compute allowance」，`life-assistant-bot` 這個 project 本月已用 80.2／100 CU-hours。查 `src/bot/monitoring.py::NeonCapacityMonitor`（FR-21）才發現既有監控只涵蓋 Neon **儲存空間**（免費額度 0.5GB），完全沒有涵蓋 **compute CU-hours**（另一項獨立的免費額度上限），所以 Robin 完全沒收到過 Telegram 主動預警，只能等 Neon 官方寄 email 才知道。

**排查過程**：查 `main.py`，`/healthz` 端點被 cron-job.org 每 10 分鐘呼叫一次（一天 144 次），觸發 `_run_background_checks()`，依序呼叫 14 個 `_check_*()` 排程檢查函式（Neon 容量、待辦推播、記帳預警／月報、體態目標、目標摘要、重要通知、重要日子、技術摘要收集／推播、TOEIC pipeline、證照題庫推播、YouTube 週推播、求職模組週排程）。逐一檢查後發現每一個 `_check_*()` 都各自 `db = CloudSQLClient()` 建立一個全新的連線池、處理完在 `finally` 區塊各自 `db.close()`——完全沒有共用連線。也就是說每次 `/healthz` 觸發，都要跟 Neon 建立並關閉 **14 次獨立連線**，一天累積 `14 × 144 = 2016` 次連線建立／關閉。

**根因**：Neon 免費方案的 compute 在閒置一段時間後會自動休眠（suspend），有新連線進來就要喚醒（cold start）。這種高頻率、大量獨立連線開關的模式，會讓 compute 幾乎沒辦法真正休眠、頻繁被喚醒保持運算中，是 CU-hours（運算時數）被大量消耗的典型成因，跟資料庫查詢的資料量大小無關。這是純粹的架構疏漏：14 個排程檢查函式各自獨立開發，沒有共用連線的設計。

**修復方式**：`_run_background_checks()` 改成先檢查 `DATABASE_URL` 是否存在（沒有就整批跳過，不建立任何連線），接著統一建立**一個** `CloudSQLClient()`，依序傳給 14 個 `_check_*(db)` 共用，全部跑完才在最外層 `finally` 統一 `db.close()` 一次。14 個 `_check_*()` 函式簽名改成接受 `db` 參數，移除各自的 `CloudSQLClient()` 建立與 `db.close()`（連線生命週期交給呼叫端統一管理），個別函式內原本的 try/except（避免某一項出錯波及其他項）維持不變。這樣一天的連線次數從 2016 次降到 144 次，減少約 93%。見 `docs/specs/SPEC.md` FR-21a。

Neon compute CU-hours 本身目前沒有官方即時查詢 API（跟 Gemini 額度監控 Phase 1 暫緩的情況一樣），暫不新增主動監控，記錄在 `docs/specs/DRAFT.md` 待討論。

**驗證方式**：`tests/test_main.py` 全面更新——14 個 `_check_*()` 的測試改成直接傳入共用的 `fake_db = MagicMock()`，不再 monkeypatch `CloudSQLClient` 也不再各自斷言 `db.close()`；新增 `test_healthz_dispatches_all_checks_via_background_thread` 驗證每個 `_check_*()` 收到的是同一個共用 `db`（`fake.assert_called_once_with(fake_db)`）且最外層只 `close()` 一次；新增 `test_healthz_skips_all_checks_when_database_url_missing` 驗證沒有 `DATABASE_URL` 時整批跳過、連 `CloudSQLClient()` 都不建立。全專案 `pytest -q`（`/tmp/work` 沙盒環境）`tests/test_main.py` 35 passed；其餘既有失敗（`test_migration_sql.py` 沙盒環境限制、`tests/submodules/email/test_client.py` 沙盒暫存快取版本較舊）與本次改動無關。`ruff check main.py tests/test_main.py` 全過。**尚待 Robin 部署後觀察下週 Neon compute CU-hours 使用曲線是否明顯趨緩**。

## 2026-08-26 續：部署後兩天內用量又打滿 100 CU-hrs，找到真正主因——不是連線數，是 5 分鐘自動休眠延遲

**現象**：8/24 才部署完上面的連線共用修復，8/26 Robin 又收到 Neon「已用 100% compute CU-hours」信件，`life-assistant-bot` project 從 8/1 到 8/26（26 天）累計用掉 `101.28 / 100 CU-hrs`，平均每天約 3.9 CU-hr，代表上次修復雖然方向正確，但沒有解決主要驅動因素。

**排查過程**：請 Robin 到 Neon 後台截圖確認幾項關鍵資訊：①「Computes」頁面顯示 Primary compute 目前是 `SUSPENDED`（2 分鐘前才休眠）——證明自動休眠機制本身確實有在運作，推翻了「被 `/healthz` 卡住整天醒著、完全無法休眠」的假設 ②「Monitoring → Metrics」頁面的 CPU 用量圖顯示過去一天內 CPU 使用率幾乎全程趨近於 0（只有一個小尖峰），代表 compute 實際運算量非常低 ③「Compute settings」／「Compute defaults」明確顯示 **Autosuspend delay（Scale to zero）= 5 minutes（固定預設值，Free 方案鎖死無法調整，需升級付費方案才能自訂）**。

把這三項資訊放在一起重新計算：Neon 的自動休眠是「持續閒置滿 5 分鐘才真正休眠」，不是「查詢一做完就立刻休眠」——也就是說每一次有任何活動（包含 `/healthz` 觸發的查詢，不管查詢本身多快做完），compute 都會被計費「活躍」滿 5 分鐘、計時器歸零重算，之後才會真的進入休眠。`/healthz` 由 cron-job.org 每 10 分鐘觸發一次，一天 144 次：`144 次 × 5 分鐘 = 720 分鐘 = 12 小時`，等於一天有整整一半時間都在被計費「活躍」，即使系統其實幾乎沒在做任何運算（跟上面那張趨近於 0 的 CPU 用量圖完全吻合）。`12 小時 × 最低規格 0.25 CU = 3 CU-hr/天`，跟實測平均 3.9 CU-hr/天非常接近（差額推估是 Telegram／Mobile App 真實流量與週排程等其他正常使用）。

**根因（修正 8/24 條目的結論）**：真正的主要驅動因素是「`/healthz` 10 分鐘觸發頻率」撞上「Neon Free 方案鎖死 5 分鐘自動休眠延遲」這個組合——不管每次觸發只開 1 條連線還是 14 條連線，只要有任何一次活動，compute 就會被迫維持活躍計費滿 5 分鐘，而 10 分鐘的觸發間隔只夠讓它休眠約 5 分鐘就又被下一次觸發喚醒，形成「幾乎有一半時間都在陪榜計費」的固定成本，且這個成本幾乎與連線數、查詢量無關。8/24 那次修復（14 條連線併成 1 條）方向正確、確實減少了連線建立/關閉的額外開銷，但沒有觸及真正的主要成本來源，所以效果有限。

**修復方式**：本次**不修改程式碼**。因為 Free 方案無法調整 Autosuspend delay（升級付費方案可以解鎖自訂，但要花錢），改成調整外部排程頻率——`/healthz` 的 10 分鐘觸發間隔是設定在 **cron-job.org**（外部排程服務）後台，不是寫死在程式碼裡；經跟 Robin 討論待辦提醒即時性 vs. 免費之間的取捨後，Robin 選擇「完全不花錢，接受提醒可能變慢/沒那麼準」，決定由 Robin 自行到 cron-job.org 後台把觸發間隔拉長（技術上只要不超過 `check_and_push_reminders()` 現有 30 分鐘的提醒緩衝視窗 `_REMINDER_WINDOW`，理論上不會真的漏推，只是提前量可能從穩定的「約 30 分鐘前」變成「介於 1～30 分鐘前」不等，每日 08:00 摘要與其他排程檢查也會等比例延遲被觸發）。這個決策與後續評估記錄於 `docs/ADR/discuss/infra.md` 2026-08-26 條目。

**驗證方式**：無程式碼異動，不需要跑測試。待 Robin 調整 cron-job.org 觸發頻率後，觀察下個月 Neon compute CU-hours 用量曲線是否明顯降低，以及待辦提醒／每日摘要的實際延遲是否在可接受範圍內。
