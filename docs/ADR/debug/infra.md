# infra 排查紀錄

## 2026-08-24 `/healthz` 每次觸發都開 14 個獨立資料庫連線，疑似是 Neon compute CU-hours 額度快速消耗的主因

**現象**：Robin 收到 Neon 官方 email「You've used 80% of your monthly compute allowance」，`life-assistant-bot` 這個 project 本月已用 80.2／100 CU-hours。查 `src/bot/monitoring.py::NeonCapacityMonitor`（FR-21）才發現既有監控只涵蓋 Neon **儲存空間**（免費額度 0.5GB），完全沒有涵蓋 **compute CU-hours**（另一項獨立的免費額度上限），所以 Robin 完全沒收到過 Telegram 主動預警，只能等 Neon 官方寄 email 才知道。

**排查過程**：查 `main.py`，`/healthz` 端點被 cron-job.org 每 10 分鐘呼叫一次（一天 144 次），觸發 `_run_background_checks()`，依序呼叫 14 個 `_check_*()` 排程檢查函式（Neon 容量、待辦推播、記帳預警／月報、體態目標、目標摘要、重要通知、重要日子、技術摘要收集／推播、TOEIC pipeline、證照題庫推播、YouTube 週推播、求職模組週排程）。逐一檢查後發現每一個 `_check_*()` 都各自 `db = CloudSQLClient()` 建立一個全新的連線池、處理完在 `finally` 區塊各自 `db.close()`——完全沒有共用連線。也就是說每次 `/healthz` 觸發，都要跟 Neon 建立並關閉 **14 次獨立連線**，一天累積 `14 × 144 = 2016` 次連線建立／關閉。

**根因**：Neon 免費方案的 compute 在閒置一段時間後會自動休眠（suspend），有新連線進來就要喚醒（cold start）。這種高頻率、大量獨立連線開關的模式，會讓 compute 幾乎沒辦法真正休眠、頻繁被喚醒保持運算中，是 CU-hours（運算時數）被大量消耗的典型成因，跟資料庫查詢的資料量大小無關。這是純粹的架構疏漏：14 個排程檢查函式各自獨立開發，沒有共用連線的設計。

**修復方式**：`_run_background_checks()` 改成先檢查 `DATABASE_URL` 是否存在（沒有就整批跳過，不建立任何連線），接著統一建立**一個** `CloudSQLClient()`，依序傳給 14 個 `_check_*(db)` 共用，全部跑完才在最外層 `finally` 統一 `db.close()` 一次。14 個 `_check_*()` 函式簽名改成接受 `db` 參數，移除各自的 `CloudSQLClient()` 建立與 `db.close()`（連線生命週期交給呼叫端統一管理），個別函式內原本的 try/except（避免某一項出錯波及其他項）維持不變。這樣一天的連線次數從 2016 次降到 144 次，減少約 93%。見 `docs/specs/SPEC.md` FR-21a。

Neon compute CU-hours 本身目前沒有官方即時查詢 API（跟 Gemini 額度監控 Phase 1 暫緩的情況一樣），暫不新增主動監控，記錄在 `docs/specs/DRAFT.md` 待討論。

**驗證方式**：`tests/test_main.py` 全面更新——14 個 `_check_*()` 的測試改成直接傳入共用的 `fake_db = MagicMock()`，不再 monkeypatch `CloudSQLClient` 也不再各自斷言 `db.close()`；新增 `test_healthz_dispatches_all_checks_via_background_thread` 驗證每個 `_check_*()` 收到的是同一個共用 `db`（`fake.assert_called_once_with(fake_db)`）且最外層只 `close()` 一次；新增 `test_healthz_skips_all_checks_when_database_url_missing` 驗證沒有 `DATABASE_URL` 時整批跳過、連 `CloudSQLClient()` 都不建立。全專案 `pytest -q`（`/tmp/work` 沙盒環境）`tests/test_main.py` 35 passed；其餘既有失敗（`test_migration_sql.py` 沙盒環境限制、`tests/submodules/email/test_client.py` 沙盒暫存快取版本較舊）與本次改動無關。`ruff check main.py tests/test_main.py` 全過。**尚待 Robin 部署後觀察下週 Neon compute CU-hours 使用曲線是否明顯趨緩**。
