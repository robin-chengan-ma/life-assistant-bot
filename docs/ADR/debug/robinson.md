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

## 2026-09-06 `93ed786` 誤刪聽力題文字隱藏邏輯，聽力題會顯示文字題目導致洩題

**現象**：Robin 反映「開始作答」實機驗收時完全沒看到聽力題，Claude 排查過程中一開始誤判為 ADR-32（聽力題目庫改版：`_cutoff` 切割、解答照片統一驅動、聽力題禁止顯示文字）三項功能都沒有實作完成，原因是分析時用的是雲端工作區裡過期的檔案快照，沒有重新從 Robin 電腦拉取最新版本。Robin 多次追問下，Claude 改用 `device_bash` 直接查詢電腦上 repo 的實際 HEAD 狀態，確認 `_cutoff` 檔名解析、`_process_listen_questions()`（解答照片一次性建題）皆已存在且邏輯正確，先前的「未實作」結論是誤判。

Robin 進一步追問「你確定現在的程式碼可以處理這些情境嗎」，促使 Claude 重新從電腦拉取 `src/bot/certificate_answer.py` 與對應測試 `tests/bot/test_certificate_answer.py` 到雲端沙箱執行 `pytest`，結果 2 項失敗：`test_build_question_view_hides_question_text_and_options_for_listen_question`、`test_build_question_view_shows_image_but_not_text_for_listen_question_with_photo`。

**排查過程**：`git log -p -- src/bot/certificate_answer.py` 逐次比對，發現 ADR-32 對應 commit `387eb66` 原本有正確寫入「`question_type == "listen"` 時 `prompt_lines = []`（完全不顯示文字題目/選項），否則才組文字」這段分流；但本次 session 稍早的 commit `93ed786`（「開始作答」入口修正，新增 `format_question_prompt()` 的 `exam_type` 標示）在改動 `_build_certificate_question_view()` 時，把這段分流誤刪、退化成不分 `question_type` 一律組文字題目/選項。`93ed786` 當時只執行了 `pytest tests/bot/test_router.py tests/bot/test_certificate_answer_commands.py`，沒有跑到直接測試這支函式的 `tests/bot/test_certificate_answer.py`，所以這個迴歸沒被抓到，也沒有寫進當時的 commit 摘要或 PROGRESS.md。

**根因**：Claude 在 `93ed786` 修改 `certificate_answer.py` 時，只關注自己這次要新增的 `exam_type` 參數，直接複製/簡化了整個函式本體，沒有注意到原本已有的 `question_type` 分流邏輯，且提交前的測試範圍選得太窄（只選了看起來與本次改動直接相關的測試檔案），沒有跑到同一模組的既有單元測試，才讓迴歸漏網。

**修復方式**：`src/bot/certificate_answer.py` 的 `_build_certificate_question_view()` restore `question_type == "listen"` 時 `prompt_lines = []`、否則才顯示 `question_text`／`options_text` 的分流，並補回原本被砍掉的函式說明註解，額外註明這次迴歸與修正的來龍去脈。

**驗證方式**：`pytest tests/bot/test_toeic.py tests/bot/test_certificate_answer.py tests/bot/test_certificate_answer_commands.py tests/bot/test_router.py -q` 210 passed；`pytest tests/bot -q` 全量 1143 passed、4 項既有已知環境問題失敗（`test_job_search.py`，與本次異動無關，詳見本檔案先前條目）；`ruff check src/bot/certificate_answer.py` 通過。

**未驗證範圍**：Robin 上傳的 `monster01` 聽力題（Part 1 六題有圖＋Part 2 靠解答照片建題）尚未確認今晚（2026-09-06 週日 22:00 台灣時間）的 `run_weekly_pipeline()` 排程實際跑過並成功建題；待 Robin 隔天查詢 `users.toeic_pipeline_last_run_on` 是否推進到 `2026-09-06`，以及 `certificate_questions` 是否出現 `question_type='listen'` 的資料列。若當晚仍未成功（例如 Google/Gemini/Voice API 金鑰過期），需另案排查，不在本次修復範圍內。

**經驗教訓**：往後涉及「重新確認某段既有邏輯是否還在」的問題時，必須優先用 `device_bash` 直接查詢 Robin 電腦上的真實檔案／`git log`，不能依賴雲端工作區裡可能過期的快照下結論；修改既有函式時，即使只是新增一個參數，也要完整跑過同一模組的既有單元測試，不能只挑跟本次改動「表面相關」的測試檔案。

## 2026-09-06 續：週日排程真的觸發了，但整包音檔在裁切前就先被送去 Groq 轉錄，超大檔案被 413 拒絕

**現象**：上一條目修復並 commit 後，Robin 沒有再追查排程有沒有跑成功，而是直接拿到 Render 正式環境的錯誤 log 貼過來：

```
ERROR src.bot.toeic: 整包 MP3 切割失敗（exam_type=toeic, test_id=monster01），這批聽力題暫緩處理，下次排程重試
requests.exceptions.HTTPError: 413 Client Error: Payload Too Large for url: https://api.groq.com/openai/v1/audio/transcriptions
```

這證實了兩件事：①今晚（2026-09-06 週日 22:00 台灣時間）`run_weekly_pipeline()` 確實有觸發、且掃描到了 `monster01` 這批檔案，先前對「Render 睡眠導致排程沒跑到」的猜測不成立（或者已經因為升級 Starter 方案解決）；②真正卡住的地方是另一個獨立的 bug，出在 `_split_whole_audio()`。

**排查過程**：對照 `src/bot/toeic.py` 的 `_split_whole_audio()`，發現執行順序是「先呼叫 `voice_client.transcribe_with_segments(audio_bytes, ...)` 把 `gdrive_client.download_file()` 下載回來、完全沒剪過的整份原始音檔送去 Groq 轉錄，成功拿到逐句時間軸之後，才用 `cutoff_seconds` 裁切音檔本身跟過濾時間軸」。`cutoff_seconds` 這個欄位當初（ADR-32）設計的本意就是「Robin 想直接丟整份 ~45 分鐘錄音，只自動處理前面 Part 1+2 那段，忽略後面用不到的 Part 3/4」，但因為裁切是在「送出去之後」才做，實際送去 Groq 轉錄 API 的仍然是完整未裁切的整份錄音——Robin 的錄音檔案大小超過 Groq API 的上傳限制，一開始的 HTTP 請求就直接被拒絕（`413 Payload Too Large`），裁切邏輯完全沒有機會執行到，跟 `cutoff_seconds` 設定多少完全無關。

**根因**：ADR-32 實作時，`cutoff_seconds` 的用途被誤解成「只是拿來事後過濾 Whisper 回傳的逐句時間軸」，忽略了它同時也應該用來限制「送出去給第三方 API 的檔案大小」——這是實作當時就寫錯順序，不是後續哪次改動造成的迴歸。

**修復方式**：`_split_whole_audio()` 改成有 `cutoff_seconds` 時，先用 `pydub` 把音檔裁到指定秒數，只把裁過、小很多的那段位元組送去 `voice_client.transcribe_with_segments()`；沒有 `cutoff_seconds`（`None`）維持原行為，整支都送去轉錄。新增 `tests/bot/test_toeic.py::test_split_whole_audio_transcribes_trimmed_bytes_not_the_full_file_when_cutoff_set`，直接斷言「有 cutoff 時，送進 `transcribe_with_segments()` 的位元組長度必須小於原始整份音檔」，鎖定這個順序不會再退化回去。

**驗證方式**：`pytest tests/bot/test_toeic.py -q` 60 passed（含新增 1 項）；全專案 `pytest tests/bot -q` 1144 passed（另有 4 項既有 `test_job_search.py` 失敗屬雲端沙盒暫存快取版本較舊，與本次改動無關）；`ruff check src/bot/toeic.py tests/bot/test_toeic.py` 通過。

**未驗證範圍**：Groq API 對單一檔案的確切大小上限（依帳號方案可能不同）沒有查證，這裡只確認「裁切後檔案明顯變小」，沒有針對「裁切後仍可能超過上限」這種極端情況（例如 `cutoff_seconds` 設定得太大）額外處理，屆時應該還是會拿到同樣的 413 錯誤，只是機率大幅降低。`monster01` 這批題目要等下週日（2026-09-13）22:00 排程再次自動觸發才會重新嘗試，或由 Robin 自行找方式提前觸發；待 Robin 屆時再次確認 `certificate_questions` 是否成功出現 `question_type='listen'` 的資料列。

## 2026-09-14：`monster01` 第 1~3 題「憑空消失」——下載解答照片沒包 try/except，一遇網路抖動就把整批同步中斷掉

**現象**：Robin 用新版「Number N 標記＋不確定就跳過」邏輯在本機重跑 `monster01` 後，第一次執行途中遇到 `IncompleteRead`（下載 Google Drive 檔案時網路中斷）整個腳本掛掉，Robin 直接重跑第二次，這次順利跑完。查詢 `certificate_questions` 發現第 4～31 題（扣掉 11、12、21、22 這 4 題）都正確建立，但第 1～3 題完全不見——不只沒進 `certificate_questions`，連新增的 `certificate_listen_split_failures`（記錄「切不出邊界、放棄」）裡也找不到，兩張表都查無資料，跟 11、12、21、22（有明確記錄「找不到標記」）性質不同。**Robin 事後補充：Google Drive 上也沒有這 3 題切割後的小段音檔**（`toeic_monster01_listen_1.mp3`～`_3.mp3` 都不存在），這點修正了原本的排查方向（見下方根因說明）。

**重現方式**：模擬 `gdrive_client.download_file()` 在下載某一題解答照片時拋出例外（`ConnectionError`／`IncompleteRead` 這類暫時性網路錯誤），觀察 `sync_track1_from_drive()` 的行為。

**排查過程**：檢查 `_process_listen_questions()`（以及同模式的 `_process_write_questions()`、`_process_answer_keys()`）逐一比對每一行下載呼叫，發現 `gdrive_client.download_file(answer_file["id"])`（下載解答／題目照片那一行）從最初實作以來就完全沒有包 try/except，跟緊接在它前面的「上傳切割後聽力小檔」那段（`upload_file`，有 try/except、失敗會記 log 後 `continue`）待遇不一致。一旦這裡拋出例外，會直接往外傳穿過整個函式、穿過 `sync_track1_from_drive()`，讓當次呼叫直接中止——**不是「這一題失敗、跳過繼續處理下一題」，而是「從這一題開始，後面所有還沒處理到的題目，這次呼叫完全不會被碰到」**，而且因為程式在寫入資料庫或記錄失敗之前就已經中斷，這些題目不會出現在 `certificate_questions`，也不會出現在任何失敗記錄表裡，等於「什麼紀錄都沒有、憑空消失」。比對 Robin 第一次執行時的 traceback，錯誤就是發生在下載解答照片這一行，一開始判斷時間點與「後續第 1～3 題完全查不到」吻合。

**追加排查（Drive 上也沒有切割後的小段音檔）**：這點很關鍵——`gdrive_client.upload_file()`（上傳切割後小段音檔）發生在下載解答照片**之前**（見 `_process_listen_questions()` 逐題迴圈順序：先切好的音檔上傳、再下載解答照片解析）。如果單純是「下載解答照片時崩潰」，這 3 題的切割音檔應該已經成功上傳到 Drive 才對；但 Drive 上也沒有，代表這 3 題極可能連上傳這一步都沒有走完，或者上傳當時就已經失敗。`upload_file` 這段呼叫本身**早就有** try/except（失敗記 log、`continue`，不會讓例外往外傳），所以如果失敗點真的在這裡，並不會讓整個同步流程中斷——這跟 Robin 第一次執行時「整個腳本真的掛掉」的觀察還是對得上：比較合理的推測是，第一次執行時，這 3 題當中有一題確實在下載解答照片這一步（走到這裡代表它自己的上傳已經成功）遇到 `IncompleteRead` 而讓整批中斷；但另外一兩題則是在各自嘗試上傳音檔時就先遇到暫時性網路問題、被既有的 try/except 悄悄接住記了一行 log、`continue` 掉，沒有留下任何資料庫或失敗表的紀錄（這是既有設計本來就如此：上傳失敗只留 log、不特別記錄，因為判斷屬於可重試的暫時性問題）。也就是說，這 3 題很可能是「兩種既有的沒有紀錄的失敗路徑（上傳失敗被吞掉、下載失敗把整批打斷）」混在同一次執行裡同時發生，不是單一原因。**根因未完全確認**——由於當時沒有保留完整的執行 log（腳本只印設計好的摘要行，沒有把 log 等級調到能完整顯示 `_logger.exception`／`_logger.warning` 的輸出），沒辦法回頭精確判斷這 3 題各自實際卡在哪一步，這裡的說明是根據程式碼行為與時間線做的合理推斷，不是百分之百還原的事實。

**根因**：`_process_write_questions()`／`_process_listen_questions()`（兩處）／`_process_answer_keys()` 這四個下載呼叫點，只有「上傳切割後音檔」那個步驟有做例外處理，下載步驟從一開始就沒有——這是既有設計的疏漏，不是本次「Number N 標記」或「切割失敗永久放棄」改動造成的迴歸，只是這次測試時剛好用網路不穩定的環境跑，才把這個原本潛藏的問題暴露出來。這個疏漏至少造成一次整批同步中斷，是確定發生過的事實；但它是否是這 3 題「兩種都沒紀錄」的唯一原因，如上一段所述並不是 100% 確定（也可能是既有的上傳失敗吞噬路徑同時發生），修復下載這一段本身仍然是正確且必要的，只是這裡誠實記錄根因判斷的不確定性，避免把推測寫成確定結論。

**修復方式**：新增共用小函式 `_download_file_or_none(gdrive_client, file_id, context)`，把 `gdrive_client.download_file()` 包一層 try/except，下載失敗記 log（含用途、`exam_type`/`test_id`/`qnum` 等上下文方便排查）並回傳 `None`，呼叫端跳過這一題即可，不影響同一批次裡的其他題目。四個呼叫點（`_process_write_questions()` 1 處、`_process_listen_questions()` 2 處、`_process_answer_keys()` 1 處）全部改用這支共用函式。這種失敗刻意**不**記錄進 `certificate_listen_split_failures`（那張表是給「切不出音檔邊界」這種確定性失敗用的）——單純下載失敗多半是暫時性網路問題，沒有寫入 `source_image_filename`／`answer_source_filename`，下次排程掃描時會自動重試，這跟原本既有的重試設計一致，值得繼續自動重試。

**驗證方式**：新增 `tests/bot/test_toeic.py::test_sync_recovers_from_transient_download_failure_on_one_answer_photo`，模擬其中一題下載解答照片拋出例外，斷言：①同一批次裡其他題目不受影響、正常寫入；②失敗的那題兩張表都沒有紀錄；③下次同步（網路恢復）該題自動重試成功。`pytest tests/bot/test_toeic.py -q` 60 passed；全專案 `pytest tests/bot -q` 1144 passed（4 項既有 `test_job_search.py` 失敗與本次無關）；`ruff check src/bot/toeic.py tests/bot/test_toeic.py` 通過。

**未驗證範圍**：這次只補強了 `src/bot/toeic.py` 裡的下載呼叫，沒有排查專案其他模組是否有類似「下載/外部 API 呼叫沒包例外處理」的模式；`gdrive_client.upload_file()`／`voice_client.transcribe_with_segments()` 等其他外部呼叫本身各自已有既有的 try/except 或由呼叫端整批捕捉，這次沒有重新檢視。Robin 的 `monster01` 第 1～3 題實際上仍需要重新排程／手動重跑一次才會補上（这次修復只是讓「以後再遇到同樣網路問題」不會再憑空消失，不會自動回填這次已經漏掉的 3 題），待 Robin 重跑後確認。

**續（同日）：真正的根因確認——`GDriveClient.list_files()` 沒有處理 Google Drive API 分頁**

上面的修復（下載例外處理）是真實存在、確定發生過的 bug，值得修，但後續驗證發現它**不是**第 1～3 題消失的完整解釋。Robin 套用上述修復後重跑同步指令，結果是「新增題目數：0，本次新記錄為『放棄不重試』的題目數：0」——代表第 1、2、3 題根本**沒有被嘗試處理過**，不是「處理途中失敗」。這點推翻了上面「兩種既有沒有紀錄的失敗路徑混在一起」的推測。

**排查過程**：先請 Robin 用截圖確認第 1～3 題在 Google Drive 上的來源檔案（`toeic_monster01_listen_1.jpeg`／`_1_ans.jpeg`／`_2.jpeg`／`_2_ans.jpeg`／`_3.jpeg`／`_3_ans.jpeg`）是否在先前手動清理壞掉的切割音檔時被誤刪——screenshot 確認 6 個檔案都還在，排除誤刪的可能。接著檢查 `submodules/gdrive/client.py` 的 `list_files()`：這支方法只呼叫一次 `self._service.files().list(q=query, fields="files(id, name, mimeType, webViewLink)")`，完全沒有處理 Google Drive API v3 回應裡的 `nextPageToken`。Drive API 單次呼叫預設最多回傳約 100 筆結果，超過這個數量的檔案會落在「下一頁」，但因為程式碼從未檢查、也從未請求下一頁，這些檔案對呼叫端來說**連出現在列表裡都沒有**——不是抓到了處理失敗，而是根本不知道它們存在。透過 AskUserQuestion 向 Robin 確認資料夾內檔案總數，Robin 回覆「超過 100 個」，這就是第 1～3 題（依檔名排序可能剛好落在第一頁之外，或受 Drive API 回傳順序影響落在後面幾頁）100% 每次重跑都抓不到、也不會留下任何失敗記錄的確定性根因——這不是機率性的網路問題，是結構性、每次都會重現的分頁遺漏。

**根因（已確認，取代上面「未完全確認」的推斷）**：`GDriveClient.list_files()` 缺少分頁處理，資料夾內檔案數超過 API 單頁上限時，後面幾頁的檔案完全不會出現在回傳結果中。這是比「下載例外處理」更根本的問題：即使下載邏輯完全正確，只要 `list_files()` 從一開始就沒把該檔案列出來，後面的處理迴圈永遠不會嘗試碰它，自然也就不會留下任何成功或失敗的紀錄。這能完整解釋「新增 0、放棄不重試 0」——因為第 1～3 題的來源檔案根本不在 `classify_drive_files()` 拿到的清單裡。上面的「追加排查」段落中「上傳失敗被吞掉、下載失敗把整批打斷混在一起」的推測，現在看來並不是主要原因（那次的 `IncompleteRead` 是另一次真實發生但性質不同的暫時性網路問題），這裡予以修正：第 1～3 題消失的主因是分頁遺漏，下載例外處理的修復本身仍然正確且必要，但兩者是各自獨立的缺陷，不是同一個根因的兩種說法。

**修復方式**：`GDriveClient.list_files()` 改成用 `while` 迴圈搭配 `nextPageToken`／`pageToken` 抓完所有分頁，`pageSize` 明確設為 API 上限 1000（減少來回呼叫次數），直到某一頁的回應沒有 `nextPageToken` 才停止，回傳所有分頁 `files` 陣列串接後的結果。`fields` 參數同步加上 `nextPageToken`（原本只有 `files(...)`）。

**驗證方式**：新增 `tests/submodules/gdrive/test_client.py::test_list_files_follows_pagination_until_no_next_page_token`，模擬兩頁回應（第一頁有 `nextPageToken` 與 1 個檔案，第二頁沒有 `nextPageToken` 與 2 個檔案），斷言回傳結果是兩頁串接、且第二次呼叫確實把第一頁拿到的 `nextPageToken` 當作 `pageToken` 傳入；同步更新既有的 `test_list_files_sends_correct_query_and_fields` 斷言新的 `fields`/`pageSize`/`pageToken` 內容。`pytest tests/submodules/gdrive/test_client.py -q` 21 passed；全專案 `pytest tests/bot tests/submodules -q` 1321 passed（13 項失敗均為既有、與本次無關：4 項 `test_job_search.py` 與 9 項 `tests/submodules/email/test_client.py`，後者是既有程式碼缺少 `smtplib` import 屬性導致，與本次 Drive 分頁改動無關）；`ruff check submodules/gdrive/client.py tests/submodules/gdrive/test_client.py` 通過。已確認全專案只有 `src/bot/commands.py`（2 處）與 `src/bot/toeic.py`（1 處）呼叫 `list_files()`，這次的 `fields` 變更是純粹疊加（多要一個欄位），不影響既有呼叫端的行為。

**未驗證範圍**：Robin 尚未在本機重新套用這個修復並重跑同步指令，第 1、2、3 題最終是否被正確切割（或正確判定為放棄不重試）仍待 Robin 實際重跑後用聽力內容驗證確認。另外，`src/bot/commands.py` 的兩處 `list_files()` 呼叫用途是搜尋特定檔名（`name_contains=filename`），理論上也曾受同一個分頁 bug 影響（如果目標檔案恰好落在第一頁之外），但這次沒有額外測試這兩個呼叫點的實際案例，只是確認修復後的分頁邏輯對它們同樣適用（`name_contains` 篩選後理論上結果集通常很小，命中分頁問題的機率遠低於掃描整個資料夾的 `toeic.py` 用法，但沒有到 100% 排除）。
