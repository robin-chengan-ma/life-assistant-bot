# 服務健康與治理 討論紀錄

> Email 備援子模組（`submodules/email`）的技術實作細節已記錄於 `docs/ADR/discuss/submodules-core.md` ADR-11，本檔案只保留「為什麼需要這個備援」的產品層決策脈絡，不重複實作細節。

## 2026-07-29 [標籤：AI] 錯誤處理的對外用語（原記錄於 robinson SPEC.md ADR-6）

**狀態**：accepted

**背景**：使用者不需要（也不應該）知道系統的技術錯誤細節，但 Robin 需要完整資訊才能除錯。

**討論內容**：比較「回傳詳細錯誤訊息」（對非技術背景的家人不友善）與「完全不回應」（使用者會誤以為 Bot 失聯，體驗更差）等方案。

**決策**：對一般使用者一律回覆「生病了」等擬人化用語且不解釋原因；技術 log 僅回報 Robin；修復後主動群發「我康復了」。

**理由**：符合 Robinson 的人格設定，同時避免暴露系統架構給非技術使用者造成困惑或誤解。

**後果**：需要建立一個集中式的錯誤處理層，統一攔截例外並轉換為對外用語，同時寫入告警管道通知 Robin。

## 2026-07-29 [標籤：AI] 異常的自主診斷與人工核准修復流程（Human-in-the-Loop，GitHub PR 機制）（原記錄於 robinson SPEC.md ADR-7，已 superseded）

**狀態**：superseded by 2026-08-05 條目（Step 2.4 開工前 Robin 重新評估後認為 AI 自主診斷＋GitHub PR 自動化風險與工程量不成比例，且上網查詢前提已因 Gemini grounding 失效而不可行）

**背景**：Robin 希望 Robinson 不只是把錯誤丟給人看，而是能像資淺工程師一樣先做初步診斷——抓 log、上網查可能原因、評估修復影響範圍，再把「建議方案」交給 Robin 審核。

**決策**：FR-19 擴充為 FR-19a～FR-19i：捕獲異常與 Log→自主診斷與搜尋→衝擊評估→發送建議報告→核准後執行修復（GitHub PR 機制）→例外分級降級→決策執行狀態閉環回饋→外部 API 重試機制。「開 PR」視為產生建議方案的一部分，不算需要事先核准的「執行」；真正需要人工核准的動作是「Merge PR 到 main」。分兩個 Phase 交付：Phase 1（MVP）只做捕獲＋Log 與簡化版通知，Phase 2 才補上完整的 AI 診斷與 PR 自動化。

**替代方案**：Robinson 直接改正式環境檔案並自動部署（已否決，風險過高）；先在沙箱環境驗證再部署（已否決，超出免費方案資源）。

**理由**：用「開 PR 而非直接改 main」作為執行機制，把 AI 能自主做的事與只有人類能做的事用 Git 既有機制天然分開。

**後果**：需新增 `GITHUB_TOKEN` 敏感金鑰。（此方案後續於 2026-08-05 由更輕量的方案取代，見下方條目。）

## 2026-08-05 [標籤：AI] Step 2.4 取消 AI 自主診斷＋GitHub PR 自動化，改為「完整 log 上傳雲端＋Robin 專屬連結」（原記錄於 robinson SPEC.md ADR-15，supersede ADR-7）

**狀態**：accepted

**背景**：Step 2.4 開工前重新評估上一則條目的方案，發現兩個實際落地時的關鍵問題：①FR-19b 要求「上網查詢可能原因」，但 Gemini 的 Google Search grounding 功能已因新 Key 對 Gemini 2.5 世代 404 而被整個移除，Robin 明確表示不考慮開通計費帳戶，代表「即時上網查詢」技術上已經做不到 ②GitHub PR 自動化需要新建 `submodules/github/client.py`、串接 GitHub API、讓 LLM 讀取相關檔案內容生成 diff，工程量與風險都相當高，且 sandbox 環境連不到 `api.github.com`，無法在此直接驗證整合。Robin 評估後認為這套機制難度與風險不成比例。

**決策**：①FR-19b～FR-19e 整套機制取消，FR-19c／FR-19d／FR-19e 三條需求編號直接移除，FR-19b 改寫為「完整錯誤 log 上傳雲端＋私訊 Robin 專屬連結」②延伸既有 `webhook._notify_robin_of_error()`，例外發生時把完整 Traceback＋觸發功能＋使用者輸入摘要＋時間戳記組成 log 檔案內容，呼叫既有 `GDriveClient.upload_file()` 上傳，取得連結後附加在私訊 Robin 的訊息裡 ③其他使用者行為完全不變，一律只收到既有「生病了」安全用語 ④FR-19f～FR-19i（例外分級降級、決策執行狀態閉環回饋、外部 API 重試機制）不受影響 ⑤`GITHUB_REPO` 環境變數移除，但 `GITHUB_TOKEN` 保留（ADR-11／`src/migrations/` 的 git push 機制仍依賴它，跟本次取消的 GitHub REST API PR 自動化是兩件不相關的事，只是恰好共用同一把權杖）。

**替代方案**：維持原方案、FR-19b 改用其他免費搜尋 API（已否決，仍需額外整合成本且沒解決 GitHub PR 自動化本身的工程量問題）；開通 Gemini 計費帳戶恢復 grounding（已否決，涉及個人帳務決定）。

**理由**：Traceback 本身就完整包含「哪支 py 檔案、哪一行、呼叫堆疊」這些資訊，不需要額外的 AI 診斷或程式碼異動生成邏輯就能滿足 Robin 真正的需求；完全複用 Step 1.3b/1.4 已經上線驗證過的 `GDriveClient`，不需要新的 submodule、新的外部服務串接；風險大幅降低——正式環境程式碼的修改權限完全保留在 Robin 手上。

**後果**：`docs/specs/robinson/PROGRESS.md` 的 Step 2.4 說明同步簡化；系統架構總覽表移除「治理｜GitHub API」這一列；風險表移除「AI 自主診斷誤判」等隨此機制取消而消失的風險項目，新增「Drive log 檔案無生命週期管理」的低風險項目。

## 2026-08-05 [標籤：AI] Telegram 本身故障時的備援通知管道（原記錄於 robinson SPEC.md ADR-16）——產品層決策脈絡

**狀態**：accepted

**背景**：Robin 驗收 Step 2.4（FR-19b，錯誤 log 雲端連結）時提出一個關鍵問題：`_notify_robin_of_error()` 私訊 Robin 的機制完全建立在「Telegram 自己是正常運作的」這個假設上——如果今天壞掉的剛好是 Telegram API 本身，Robin 會完全收不到任何主動通知，只能自己去 Render Dashboard 翻 log。這是 FR-19b 設計時沒考慮到的單點故障。

**決策**：新增獨立於 Telegram 的 Email 備援通知管道，只有 Telegram 送達失敗才觸發；實作細節（`submodules/email`、`smtplib`、`GMAIL_USER`/`GMAIL_PASSWORD` 複用）見 `docs/ADR/discuss/submodules-core.md` ADR-11。

**後果**：這個備援機制的涵蓋範圍僅限「私訊 Robin 的錯誤通知」，不涵蓋一般使用者收到的「生病了」安全用語——一般使用者本來就沒有登記 email，這是 Telegram-only 架構的既有限制。

## 2026-08-15 [標籤：使用者] Email 備援送達狀態與錯誤管理呈現

**狀態**：accepted

**背景**：現行 Telegram 私訊 Robin 失敗時會將同一份錯誤內容寄到 `GMAIL_USER`，但寄信成功後沒有保存送達管道與時間；Telegram 恢復後也不會補發。若 Email 也失敗，只剩伺服器 Log，Robin 無法從系統錯誤管理畫面判斷通知是否曾送達。

**決策**：①Email 本身即為 Robin 的備援通知，成功後不得再發送「Email 已寄出」通知，也不在 Telegram 恢復後重複補發同一錯誤。②每筆 Owner 系統錯誤需記錄最後通知方式 `telegram`／`email`／`undelivered` 及最後通知時間。③「系統錯誤管理」須顯示通知方式與送達狀態；Email 成功時標示「已透過 Email 通知」。④Telegram 與 Email 都失敗時標示「未送達」，仍保留錯誤內容供 Owner 之後查看。⑤Email 備援只處理 Robin 專屬系統錯誤，不擴張為一般使用者通知備援。

**理由**：保存通知結果可以確認重要錯誤是否成功送達，又不需要增加第三種通知管道或產生「通知通知已寄出」的循環。

**後果**：實作時需以向前 Migration 擴充 `system_error_reports` 的通知管道與時間欄位，更新錯誤通知 Service、Owner 系統錯誤管理選單、API／DB Reference 與成功、Email fallback、雙重失敗測試。現行 `_send_email_fallback()` 尚未回傳或寫入成功狀態，在完成上述項目前不得宣稱已具備送達追蹤。
