# Robinson（Telegram Bot）修復紀錄

> 同一功能的多次除錯都寫在同一個檔案，依時間往下附加新段落，不要開新檔案。不論有沒有改 code 都要記。

## 2026-08-16 Telegram 新增的收藏不會出現在探索地圖

**現象**：Robin 在 Telegram 用「🧭 收藏與旅遊」新增一筆收藏（已填國家、區域／城市），到 Mobile App「探索地圖」可以看到這筆收藏出現在清單，但地圖上沒有對應的圓形位置標記；之後回去把詳細地址補上並在 Telegram 點擊「📍 定位地址」定位成功，回探索地圖查看仍然沒有標記。

**排查過程**：對照 `docs/specs/SPEC.md` FR-75「探索地圖不提供獨立新增入口，探索紀錄只能由收藏標記已造訪或完成行程時產生」，確認地圖標記的資料來源是 `exploration_events` 表，不是 `collection_items` 表本身的經緯度欄位。檢查 `src/services/app_life_exploration.py` 的 `_create_visit()`：只有呼叫 `visit_collection()`（單筆標記已造訪）或 `complete_trip()`（完成行程時對已勾選項目呼叫）才會寫入 `exploration_events`，並把 `collection_items` 目前的 `latitude`／`longitude` 快照進去。再檢查 2d 新增的 `src/bot/collections.py`／`src/bot/trips.py`：`collections.py` 只有新增／編輯／刪除收藏，沒有任何呼叫 `visit_collection()` 的入口；`trips.py` 的「完成行程」流程有呼叫 `complete_trip()`，但那要求收藏必須先被加進一個行程才能觸發。Mobile App 的收藏清單卡片上另外有一顆獨立的「標記已造訪」按鈕（不經行程），這顆入口在 Telegram 端的 2d 實作計畫裡漏掉了。

**根因**：2d 實作計畫的收藏 CRUD 範圍只涵蓋 FR-73（新增／編輯／刪除／地址定位），沒有涵蓋「收藏可以不經行程、直接標記已造訪」這個 Mobile 既有入口，導致 Telegram 使用者新增收藏後，除非把它加進行程並完成行程，否則永遠不會產生 `exploration_events` 紀錄，探索地圖自然不會顯示標記——這跟收藏本身有沒有定位成功無關（地址定位只是把座標存到 `collection_items`，不會自動建立探索事件）。

**修復方式**：`src/bot/collections.py` 新增「🧭 標記已造訪」動作：收藏清單每一筆狀態非 `visited` 的項目都會顯示這顆按鈕（`collections:visit:<id>`），按下後走「造訪日期（可輸入「今天」）→造訪備註（可略過）」兩步驟，直接呼叫既有 `AppLifeExplorationService.visit_collection()`（不重寫邏輯，符合 FR-6h）；`src/bot/router.py` 新增 `collections:visit:<id>` callback 分派與 `collection_visit` flow 分支。新增 `tests/bot/test_collections.py` 三項測試（標記造訪成功並帶入既有座標、輸入「今天」使用當下日期、已造訪過的項目擋下重複標記）。

**驗證方式**：Robin 本機執行 `python3 -m pytest tests/bot/test_collections.py -v`，13 項全數通過（含本次新增 3 項）。待 Robin 在 Telegram 實機重新測試：先在收藏清單新增一筆有定位成功的收藏，按「🧭 標記已造訪」，回 Mobile App 探索地圖確認出現圓形標記；再測一次「先無地址新增收藏→標記已造訪→之後才補地址定位」的順序，確認邏輯上仍然只有標記已造訪之後才會產生地圖標記（若先標記造訪、事後才補定位，探索地圖不會自動回填座標，因為 `exploration_events` 是快照而非即時關聯——這點若 Robin 認為需要改善，屬於新的產品決策，需另外討論，不在本次修復範圍）。

## 2026-08-16 補述：`docs/ADR/discuss/robinson.md` 2d 附帶迴歸修正與發現兩項與本次修復無關的既有問題

**現象**：Robin 執行完整 `python3 -m pytest tests/` 回報 22 項失敗。逐項比對後分成三類：

①**本次補修直接造成的迴歸（1 項）**：`tests/bot/test_router.py::test_important_days_menu_key_not_in_not_yet_implemented_set` 斷言 `collections` 仍在「開發中」名單，但 2d 已把它移出，斷言本身沒跟上——這是 2d 主批次遺漏更新的既有測試，不是這次補修新引入的，只是這次才第一次跑到完整測試套件才浮現。
②**與本次修復無關的既有失敗（16 項）**：`tests/bot/test_body_commands.py`／`tests/bot/test_body_router.py`／`tests/bot/test_commands.py` 共 16 項失敗，錯誤集中在心情（`mood`）與運動（`exercise`）相關函式——`handle_mood_content_step()`／`handle_exercise_heart_rate_step()` 呼叫時「got multiple values for argument 'telegram_user_id'」（呼叫端與函式簽章的參數順序或關鍵字用法對不上），以及 `commands` 模組已經沒有 `start_mood_list`／`handle_mood_list_action_step`／`handle_mood_action_choice_step`／`handle_mood_delete_confirm_step` 這幾個函式（對照 `docs/ADR/discuss/robinson.md` 2026-08-16「Phase 6 第二批 2c」設計內容⑤，這些函式在 2c 就已經正式移除，改用按鈕 callback 取代）。這些測試檔案本身完全沒有被本次（2d／2d 補修）異動過，判斷是 2c 那批（commit `8d0ba92`）遺留下來、沒有跟著移除或改寫的舊測試——2c 的「開工完成」補述裡記錄「Claude 沙箱還原完整依賴後執行 `tests/` 全數 155 項通過」，跟現在 1801 項裡就有 16 項屬於這個問題的落差，推測 2c 沙箱驗證當時涵蓋的測試範圍或依賴狀態跟 Robin 本機現況不同，實際原因待進一步排查確認，這裡先如實記錄現象與初步比對結果，不做未經查證的根因臆測。
③**環境限制、不是程式問題（3 項）**：`tests/bot/test_toeic.py` 3 項因本機沒有安裝 `ffmpeg`（`FileNotFoundError: No such file or directory: 'ffmpeg'`）失敗，這是既有已知環境問題（`docs/specs/PROGRESS.md` 2026-08-14 那筆任務備註已提過同樣狀況），與任何程式碼異動無關。

**根因**：①已修復（見下）；②尚未排查根因，只確認範圍屬於 2c 遺留、與本次 2d／補修無關；③非程式問題，環境缺少 `ffmpeg` 執行檔。

**修復方式**：①已修正 `tests/bot/test_router.py` 該斷言，把 `collections` 從「應維持開發中」清單移到「應確認已移出」清單。②③本次不修復——②需要另外排查是 2c 當時就沒發現，還是後續有其他改動造成，屬於獨立的除錯任務，建議 Robin 另外排時間讓 Claude 或 Codex 專案排查；③需要 Robin 自行 `brew install ffmpeg`（若要在本機跑 TOEIC 語音相關測試）。

**驗證方式**：Robin 本機重新執行完整 `python3 -m pytest tests/`，確認失敗項目只剩②③兩類（16＋3＝19 項），①的 1 項迴歸已消失。
