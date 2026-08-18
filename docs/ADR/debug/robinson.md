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

**根因**：①已修復（見上一段）；②已排查完成（見下）；③非程式問題，環境缺少 `ffmpeg` 執行檔，本次不修復，需要 Robin 自行 `brew install ffmpeg`。

**修復方式**：①已修正 `tests/bot/test_router.py` 該斷言，把 `collections` 從「應維持開發中」清單移到「應確認已移出」清單。

## 2026-08-16 補述之二：16 項心情／運動既有測試失敗根因確認與修復

**根因**：確認是 Phase 6 第二批 2c（commit `8d0ba92`）把心情、運動改成「摘要→二次確認」關卡與按鈕式清單/編輯/刪除後，`tests/bot/test_commands.py`／`tests/bot/test_body_commands.py`／`tests/bot/test_body_router.py` 三個測試檔案沒有跟著同步：
- `handle_mood_content_step()`／`handle_exercise_heart_rate_step()` 2c 之後改成回傳 `(摘要文字, keyboard)`、只組摘要並轉進 `pending_mood_confirm`／`pending_exercise_confirm`，不再直接寫入 DB（要等 `mood:confirm_save`／`exercise:confirm_save` 按鈕觸發 `handle_mood_confirm_save()`／`handle_exercise_confirm_save()` 才真正寫入）；舊測試仍假設呼叫這兩個函式當下就會寫入，且呼叫參數順序／簽章對不上現行版本（`handle_mood_content_step` 少了 `fake_db` 參數；`handle_exercise_heart_rate_step` 少了 `fake_db` 參數）。
- `start_mood_list`／`handle_mood_list_action_step`／`handle_mood_action_choice_step`／`handle_mood_delete_confirm_step` 確認在 2c 就已經正式移除（改用 `mood:list`／`mood:edit:<id>`／`mood:delete:<id>`／`mood:confirm_delete:<id>` 按鈕 callback 取代），對照 2c 的「開工完成」補述「改寫 `tests/bot/test_router.py` 心情 4 項整合測試為按鈕驅動」，確認 `tests/bot/test_router.py` 當時已經有對應的按鈕驅動整合測試（`test_mood_list_update_and_delete_full_flow()`、`test_mood_delete_only_owner_can_target_own_journal()`），但舊的 `tests/bot/test_commands.py` 直接呼叫這四個函式的測試沒有一併移除，屬於 2c 收尾時遺漏的清理項目。
- `tests/bot/test_body_router.py` 的 `test_log_exercise_full_flow`／`test_my_exercise_logs_full_flow_delete` 使用舊文字觸發詞「我要記錄運動」／「我的運動紀錄」，2c 已把運動全面改成選單按鈕觸發（`daily_log:exercise` → `exercise:new`／`exercise:list`），這兩句文字觸發詞已經不會被 router 攔截，會落到一般聊天核心處理，因為測試沒帶 `llm_client` 才報 `AttributeError`。

**修復方式**：
- `tests/bot/test_commands.py`：把 4 項 `handle_mood_content_step` 測試改寫成兩段式——先驗證內容步驟只組摘要、回傳 `pending_mood_confirm` 狀態且不寫入 DB，再呼叫 `handle_mood_confirm_save()` 驗證實際寫入結果（新增／補記日期／編輯既有列／PII 遮蔽內容），涵蓋範圍與修復前相同；刪除呼叫 `start_mood_list`／`handle_mood_list_action_step`／`handle_mood_action_choice_step`／`handle_mood_delete_confirm_step` 這 11 項測試，確認對應流程已由 `tests/bot/test_router.py` 完整覆蓋，沒有測試覆蓋率缺口。
- `tests/bot/test_body_commands.py`：修正 `test_exercise_full_log_flow_with_calorie_estimate`，`handle_exercise_heart_rate_step` 呼叫拿掉多餘的 `fake_db` 參數並改為兩段式（先驗證摘要與 `pending_exercise_confirm` 狀態，再呼叫 `handle_exercise_confirm_save()` 驗證寫入）。
- `tests/bot/test_body_router.py`：`test_log_exercise_full_flow` 改用 `router.handle_callback_query(fake_db, store, FAMILY_ID, "daily_log:exercise")` → `"exercise:new"` 進入新增流程，末端改呼叫 `"exercise:confirm_save"`；`test_my_exercise_logs_full_flow_delete` 改用 `"exercise:list"` → `"exercise:delete:<id>"` → `"exercise:confirm_delete:<id>"` 按鈕流程，取代原本的文字觸發詞與 LLM 對話式刪除確認。

**驗證方式**：Claude 沙箱只還原到部分依賴（`from src.bot import auth` 等模組未同步在沙箱內，執行 `pytest` 會在 collection 階段就因 `ImportError: cannot import name 'auth'` 失敗，判斷是沙箱環境本身缺依賴而非程式碼問題），已對三個測試檔案執行 `python3 -m py_compile` 語法檢查通過。Robin 本機執行：

```
python3 -m pytest tests/bot/test_commands.py tests/bot/test_body_commands.py tests/bot/test_body_router.py -v
python3 -m pytest tests/ -q
```

第一輪 `test_body_router.py::test_log_exercise_full_flow` 因忘記拆解 `router.handle_message` 在 `pending_exercise_heart_rate` 這一步回傳的 `(文字, keyboard)` tuple 而失敗一次，已修正（改成 `reply4, _keyboard4 = router.handle_message(...)`）；Robin 重新測試後前者 201 項全過，後者 1787 passed／3 failed（僅剩既有 `ffmpeg` 環境問題，與本次無關），本次修復確認完成。

## 2026-08-16 飲食補記日期解析 NameError（2g 部署後實機驗收發現）

**現象**：Robin 部署 commit `a6b49ba`（2g 飲食功能）後實機驗收，先在「🍚 飲食」新增今天一筆飲食紀錄，接著按「🕐 補記」，在對話框直接輸入「昨天」，Telegram 回覆系統錯誤訊息，Robin 私訊收到完整 Traceback：

```
File "src/bot/commands.py", line 2768, in handle_diet_backfill_date_step
    parsed = _parse_date_description(llm_client, text)
NameError: name '_parse_date_description' is not defined
```

**排查過程**：`commands.py` 裡其餘三個「補記日期」步驟（`handle_weight_backfill_date_step()`、`handle_exercise_backfill_date_step()`，以及待辦事項／重要日子等模組各自的補記步驟）都是呼叫 `_parse_key_value_block(llm_client.generate_text(_BACKFILL_DATE_PARSE_PROMPT.format(feature_label=..., date_reply=text, current_date_text=_current_date_text())))` 這套既有的日期解析慣例，`commands.py` 裡從來沒有定義過 `_parse_date_description()` 這個函式；2g 撰寫 `handle_diet_backfill_date_step()` 時誤植了一個不存在的函式名稱，屬於單純的手誤，且完全沒有對應的單元測試涵蓋補記步驟（`tests/bot/test_body_commands.py` 只有飲食新增流程的測試，漏了補記），所以 Claude 沙箱的 `ast.parse` 語法檢查（只驗證語法樹合法，不執行程式碼、不做名稱解析）與 Robin 本機 `pytest tests/ -q`（1805 passed）都沒有抓到這個執行期才會炸掉的 `NameError`，直到部署後實機驗收才第一次真的呼叫到這行程式碼。

**根因**：2g 撰寫 `handle_diet_backfill_date_step()` 時對照既有補記步驟慣例手誤打錯函式名稱（`_parse_date_description` 不存在，正確應為 `_parse_key_value_block(llm_client.generate_text(_BACKFILL_DATE_PARSE_PROMPT.format(...)))`），且沒有對應單元測試覆蓋這個函式，導致這個純語法上合法、但執行期一定會炸的錯誤一路漏到實機驗收階段才浮現。

**修復方式**：`src/bot/commands.py` 的 `handle_diet_backfill_date_step()` 改成比照 `handle_exercise_backfill_date_step()` 的既有寫法：呼叫 `_parse_key_value_block(llm_client.generate_text(_BACKFILL_DATE_PARSE_PROMPT.format(feature_label="飲食", date_reply=text, current_date_text=_current_date_text())))`，並補上 `parsed.get("STATUS") != "CLEAR"` 時回傳既有的 `_BACKFILL_DATE_UNCLEAR_REPLY`（原本漏掉這個分支，日期講不清楚時會直接把 `None` 傳進 `_parse_date_only()` 的上一步就沒有攔到「STATUS 不是 CLEAR」的情況）。新增 `tests/bot/test_body_commands.py::test_handle_diet_backfill_date_step_clear_asks_water_for_that_date` 補上這個函式原本完全沒有的單元測試覆蓋，驗證「昨天」這類描述能正確解析並接著問飲水。

**驗證方式**：Claude 沙箱執行 `ast.parse` 語法檢查通過；待 Robin 本機執行 `python3 -m pytest tests/ -q` 確認新增測試通過且無新增迴歸，並在部署後於 Telegram 重新測試「新增今天飲食紀錄→補記昨天→輸入『昨天』」這個原本會炸掉的路徑，確認能正常接著問飲水/食物。

## 2026-08-18 0084 重複新增 note 阻塞後續 Migration

**現象**：Render 啟動時執行 migration，PostgreSQL 回報 `exercise_logs.note` 已存在，migration runner 隨即停止；應用程式因啟動流程容錯仍持續提供服務，但 `/healthz` 的目標期限檢查又回報 `module_goals` 不存在。原定由 0094 刪除的四張取消功能資料表也仍存在。

**排查過程**：查詢正式資料庫 `schema_migrations`，確認沒有任何 `0084` 以上的紀錄；再查 `exercise_logs` 欄位，確認仍是 0084 前結構：已有 `note`、`input_mode`、`training_details`，但沒有 `category_id`。靜態比對 migration 後確認 `0025_create_exercise_logs_table.sql` 已建立 `note`，未曾成功套用的 `0084_redesign_exercise_categories.sql` 卻再次執行 `ADD COLUMN note TEXT`。也逐檔檢查 0085～0094，未發現第二個同類的明顯重複加欄問題。

**根因**：0084 對既有 schema 的前置假設錯誤，重複新增 0025 已建立的欄位。Migration runner 採順序執行且遇錯即停止，因此 0085～0094 全數未套用；`main.py` 捕捉 migration 例外後仍啟動服務，使部署表面可用但 DB schema 落後。

**修復方式**：移除 0084 的 `ADD COLUMN note TEXT`，改為明確註解沿用 0025 既有欄位；保留已定案的清空舊運動紀錄、新增 `category_id` 與其餘 schema 轉換。新增 `tests/migrations/test_migration_sql.py`，鎖定 0025 已有 `note` 且 0084 不得再次新增。

**驗證方式**：TDD RED 階段聚焦測試如預期 1 failed；修正後聚焦測試為 1 passed。全專案 `pytest -q` 為 1823 passed、1 項第三方 `pydub` warning；`ruff check .` 與 `git diff --check` 通過。正式環境重新部署後的 0084～0094 套用結果仍待驗證。

**部署驗證**：Robin push `07e986a` 與文件 commit `b67cce0` 後，Render 於 2026-08-18 12:25 依序記錄 0084～0094 共 11 筆 migration 全數完成，接著 Flask 服務正常啟動並通過平台的根路徑 HEAD 檢查。這證明 0084 不再因重複欄位中斷，0085 的 `module_goals` 與 0094 的取消功能資料表清理均已執行。

**未驗證範圍**：尚未另外執行資料庫查詢逐表核對 schema，也尚未觀察下一輪 `/healthz` 背景檢查紀錄；若後續仍出現資料表不存在或 migration 錯誤，需另案排查。
