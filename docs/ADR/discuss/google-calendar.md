# Google Calendar 整合 討論紀錄

## 2026-08-05 [標籤：AI] ADR-17：新增 Google Calendar 整合，單一共用行事曆（Robin 帳號 OAuth），不做 per-user 授權

**狀態**：accepted

**背景**：Robin 想幫 Robinson 加一個 Google Calendar 工具，討論後聚焦出三個有價值的方向：待辦事項、重要通知（節日/生日）、體態目標期限單向同步寫入 Calendar，讓家人不用開口問就能在手機原生行事曆 App 看到全貌。過程中確認兩個關鍵前提：①家人不一定有 Google 帳號——Google Calendar 支援不需要帳號的「私密 iCal 網址訂閱」，但同步延遲可能長達 24 小時，不適合即時提醒用途 ②Calendar API 本身免費（額度每分鐘 10,000 次請求，家庭規模用量遠用不到）。

**決策**：①建一個獨立的「Robinson 家庭行事曆」，Robinson 只透過 Robin 一人的 OAuth 授權寫入，家人用「訂閱」的方式在自己手機看 ②家人若沒有 Google 帳號，建議直接申請一個免費帳號取得即時體驗，退而求其次用「私密 iCal 網址訂閱」（非即時、隨手瀏覽大局用途）③MVP 範圍只做「Robinson 單向寫入」，不做「讀取行事曆查空檔」④待辦事項同步不額外拆分「待辦事項」與「行程」兩種概念，MVP 先同步所有 `todos` ⑤新增獨立的 `submodules/calendar`（比照 `gdrive` 的 OAuth 2.0 模式），但用獨立一組憑證，scope 只申請 `calendar.events` ⑥（2026-08-05 補充）家人的共用權限固定設為「查看所有活動詳細資料」（唯讀），不給「進行變更」權限——避免 Robinson 不知道被家人改了什麼，又在下次覆寫時無聲蓋掉家人的手動修改 ⑦（2026-08-05 補充）待辦事項/體態目標的建立流程各自新增一題「要不要同步到 Google 行事曆？」，每次都明確詢問、不設預設值，避免忘記講而外洩隱私；重要通知（節日/生日）本質上就是要讓全家人知道的資訊，維持全部自動同步。

**理由**：單一共用行事曆＋Robin 一人授權，是複雜度最低、又能滿足「家人能在手機上看到全貌」這個核心需求的做法；per-user 授權要每個家人各自跑一次 OAuth 同意流程，複雜度直接跳到 Mobile App 等級；不拆分「行程」概念是刻意的最小可行版本。

**替代方案**：每個家人各自 OAuth 授權自己的 Google 帳號（已否決，複雜度跳級且家人不一定有 Google 帳號）；只用私密 iCal 網址訂閱（已否決，同步延遲問題無解，保留當備案）。

**後果**：新增 `submodules/calendar/`；`todos.google_calendar_event_id`／`todos.sync_to_calendar`、`body_goals.google_calendar_event_id`／`body_goals.sync_to_calendar` 四個新欄位；Robin 需要完成幾項一次性的手動設定（Google Cloud Console 開通 Calendar API、建立次要日曆、分享權限、跑一次互動式授權腳本）。
