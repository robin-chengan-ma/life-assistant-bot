# 基礎設施（Neon／Render／排程） 討論紀錄

> 同一主題的多次討論附加於同一檔案，依時間往下附加新段落，不要開新檔案。

## 2026-08-26 [標籤：使用者] Neon compute CU-hours 超額——接受降低待辦提醒即時性，換取不花錢

**狀態**：accepted

**背景**：`life-assistant-bot` 這個 Neon project 本月（8/1～8/26，26 天）compute CU-hours 用量打到 `101.28 / 100`，免費額度用完，插入／更新／查詢即將開始出錯。8/24 才剛部署過一次相關修復（`dc1e50c`，把 `/healthz` 14 條獨立連線併成 1 條共用連線），但兩天後用量依然打滿，代表那次修復沒有解決主要成本來源。經排查（見 `docs/ADR/debug/infra.md` 2026-08-26 續篇條目）確認真正主因：Neon Free 方案的 Autosuspend delay（自動休眠延遲）鎖死 5 分鐘、無法調整，而 `/healthz` 由 cron-job.org 每 10 分鐘觸發一次，兩者疊加導致 compute 一天有約一半時間都在被計費「活躍」，這個成本幾乎與連線數、查詢量無關，純粹是「觸發頻率」跟「固定 5 分鐘休眠延遲」的組合效應。

**決策**：不升級付費方案（Launch，$0.106/CU-hr），改為由 Robin 自行到 cron-job.org 後台把 `/healthz` 的觸發間隔拉長（不超過 `src/bot/todo.py` `check_and_push_reminders()` 現有 30 分鐘的 `_REMINDER_WINDOW` 緩衝視窗），維持完全不花錢；代價是接受待辦事項「30 分鐘前提醒」的實際提前量會變得不穩定（可能介於 1～30 分鐘之間，不再穩定接近 30 分鐘），每日 08:00 摘要、證照每日推播等其他借用 `/healthz` 頻率的排程檢查也會等比例延遲被觸發（例如摘要可能到 08:20 才真正送出，而不是準時 08:00～08:10 之間）。此為外部排程服務（cron-job.org）的設定調整，不涉及本專案程式碼異動，不需要 commit。

**理由**：Robin 明確表示「完全不花錢但提醒可能變慢/沒那麼準」優先於「維持現在的即時性、每月多付一點點錢」；調整外部排程頻率是零風險、隨時可逆的操作（Robin 自己在 cron-job.org 後台就能改回來），不需要改動或部署任何程式碼；相較於方向 A（升級付費方案解鎖自訂 Autosuspend delay）雖然能維持現有即時性，但要開始產生持續性費用，Robin 選擇先用不花錢的方式應對。

**替代方案**：升級 Neon Launch 付費方案，解鎖自訂 Autosuspend delay，維持 `/healthz` 現有 10 分鐘觸發頻率不變（已否決，Robin 選擇不花錢）；改寫 `/healthz` 排程架構，把不需要高頻率的檢查跟需要高頻率的檢查拆開，用不同觸發來源分別排程（尚未評估，屬於更大的架構調整，若未來降頻後提醒延遲情況超出可接受範圍，可以回頭考慮這個方向，需要另外提出實作計畫）。

**後果**：`docs/ADR/debug/infra.md` 同步記錄根因排查的修正結論；本次沒有程式碼或文件之外的異動，`docs/specs/PROGRESS.md` 記一筆純文件治理／決策條目。待 Robin 實際調整 cron-job.org 頻率後，觀察下個月 Neon 用量曲線是否明顯降低，以及各項排程通知的實際延遲是否在可接受範圍內；若延遲情況比預期嚴重（例如摘要常態延遲超過 30 分鐘、提醒常態變成「事後才收到」），需要回頭重新討論是否改採升級付費方案或调整 `/healthz` 架構。

**補充（2026-08-26 續）：確認 cron-job.org 沒有 25 分鐘這個選項、盤點所有借用 `/healthz` 頻率的排程檢查在 30 分鐘下是否安全**。Robin 詢問「改 25 分鐘可不可以」，逐一盤點目前所有依賴 `/healthz` 觸發頻率的排程檢查後確認 25 分鐘安全；但 Robin 實際到 cron-job.org 後台設定時發現介面的「Execution schedule」下拉選項只有固定的 1／2／5／10／15／30 分鐘與 1／2／3／4／6／8／12 小時（無法自訂成 25 分鐘），因此改採 **30 分鐘**，重新盤點如下：

- 「整點檢查」類型（`src/bot/certificate_quiz.py`、`src/bot/finance.py`、`src/bot/job_search.py`、`src/bot/notifications.py`、`src/bot/scheduled_notifications.py`、`src/bot/skill_growth.py`（收集／推播兩處）、`src/bot/todo.py`（每日摘要）、`src/bot/toeic.py`、`src/bot/youtube.py`、`src/services/goal_summary_job.py`）：邏輯都是「`now_local.hour != 固定小時`」（`toeic.py`／`job_search.py`／`youtube.py` 另外還多檢查 `weekday()`），只要觸發間隔小於 60 分鐘，該小時內必定命中至少 2 次，30 分鐘遠低於 60 分鐘上限，安全。
- 「30 分鐘提醒視窗」類型（`src/bot/todo.py::check_and_push_reminders()` 的 `_REMINDER_WINDOW`）：理論上只要間隔不超過 30 分鐘就不會出現視窗間的空隙，30 分鐘剛好等於視窗大小本身，**沒有安全緩衝**——如果 cron-job.org 實際觸發時間出現些微漂移（例如外部服務忙碌延遲數十秒），理論上有極小機率出現視窗縫隙、漏掉一次提醒判定。這是選 30 分鐘（而非更保守的 15 分鐘）需要承擔的已知取捨，Robin 已知情並接受。

確認以上兩種類型的排程都不會因為改成 30 分鐘而系統性地漏掉推播（提醒視窗有前述極小機率邊界風險），只會讓「主動推播」類（提醒、每日摘要、週排程）的實際觸發時間點變得不固定；使用者「主動使用」Bot／Mobile App（Telegram Webhook、Mobile App REST API）走的是完全不同的即時路徑，不受這次調整影響，仍然秒回（Neon compute 若剛好休眠中，最多是幾秒等級的冷啟動延遲，不是分鐘級）。Robin 最終確認採用 **30 分鐘**；若後續實際觀察到提醒偶爾漏推，可以回頭調降為 15 分鐘（用量降幅較小，但緩衝更充足）。
