# 羅賓森 Mobile App 討論紀錄

> 本檔案彙整原 `docs/specs/mobile-app/SPEC.md` 的 ADR-1，以及原記錄於 robinson 母 spec、與 Mobile App 架構/技術棧/登入機制選型相關的 ADR-14、ADR-28（因討論的是同一個功能，遷移時合併於此）。

## 2026-08-04 [標籤：AI] 視覺化後台改採 Mobile App（React Native + Expo），取代 Notion（原記錄於 robinson SPEC.md ADR-14，supersede ADR-1 的後台選型部分）

**狀態**：accepted

**背景**：原本選定 Notion 作為視覺化後台（上手快、適合非工程背景的家人瀏覽）。Robin 重新評估後，希望改用自建的 Mobile App，取得更客製化的 BI Dashboard 體驗與獨立的多用戶登入機制。

**決策**：①移除所有 Notion API 串接與資料同步邏輯 ②架構確立為「Telegram Bot（LUI）+ Mobile App（Rich GUI）」兩前台分工：Telegram 負責所有輸入與 CRUD 控制，Mobile App 專注 BI 圖表展示、唯讀，不提供任何寫入/CRUD 操作入口 ③技術棧確定採用 React Native + Expo ④新增多用戶登入機制（`user_name`／稱謂／`APP Access Token`）。

**替代方案**：維持 Notion（已否決，客製化程度低、多用戶登入機制需另外拼湊）；改建 Web Dashboard（已否決，家人主要透過手機使用，Native App 體驗更佳）。

**理由**：Notion 客製化互動式篩選能力弱、且沒有原生多用戶權限控管機制；React Native + Expo 是目前最成熟的跨平台方案之一，免費方案足敷家庭規模使用。

**後果**：Phase 5（Notion 後台）取消，併入 Phase 4；`users` 資料表未來需新增 `app_access_token` 欄位（後由 ADR-28 取代為 `password_hash`）。

## 2026-08-09 [標籤：AI] ADR-1：「客訴回饋」頁拆成「使用者客訴」與「系統錯誤回報」兩區塊，「解法」欄位只加在系統錯誤回報

**狀態**：accepted

**背景**：本文件初版誤將「解法」欄位設計加在 `complaints`（使用者客訴）上。Robin 後續澄清：使用者主動送出的客訴內容他只是查看，不需要解法欄位；真正需要追蹤處理進度的是系統主動推送給他的錯誤回報。Robin 同時要求解法的記錄不能只能在 App 操作，Telegram 也要能下指令記錄。

**決策**：①「客訴回饋」頁拆成「使用者客訴」（`complaints`，純唯讀）與「系統錯誤回報」（`system_error_reports`，含 `resolution` 欄位）兩個區塊 ②`resolution` 欄位同時支援 App 與 Telegram 兩種入口寫入，兩個入口呼叫同一支 service 層函式 ③`_notify_robin_of_error()` 私訊 Robin 時附上「錯誤ID=N」。

**替代方案**：`complaints` 表直接加 `resolution` 欄位（已否決，Robin 明確表示使用者客訴不需要這個欄位，混用會讓兩種性質不同的資料共用一張表）。

**理由**：使用者客訴與系統錯誤回報服務的目的完全不同；Robin 平常主要透過 Telegram 互動，收到錯誤通知當下直接回一行記錄解法比切到 App 更符合實際使用情境。

**後果**：robinson SPEC.md 新增 FR-19j；「客訴回饋頁」歸屬唯讀分析頁面的子 Step 開發，不另拆獨立 Step。

## 2026-08-09 [標籤：AI] Mobile App 範疇由「唯讀 BI Dashboard」擴大為「唯讀分析＋可編輯設定管理」，並改採帳密登入（原記錄於 robinson SPEC.md ADR-28，supersede ADR-14 相關部分）

**狀態**：accepted（2026-08-09 Robin 逐項追加確認）

**背景**：Phase 4 主線（求職模組）全數完成後，Robin 要求盤點現有所有功能模組再決定 App 要放哪些功能，並提出「APP 也可以設定目標和指標，以及各功能開關，不是只有 Telegram 可以設定而已」——這與原本「App 端原則上不提供新增/修改/刪除資料的操作入口」的唯讀定位直接牴觸。Robin 同時提出登入頁互動細節（使用者ID＋密碼、忘記密碼、保持登入），其中「忘記密碼→立刻寄出密碼到 Telegram」與「個人基本資訊頁面顯示密碼」隱含系統需要能取得使用者的密碼明碼，這與密碼安全最佳實踐（單向雜湊、不可逆）有衝突，屬於 Claude 需要主動指出並提出替代方案的技術判斷。

**決策**：①App 定位改為「唯讀分析頁面＋可編輯設定頁面」雙軌設計，新增目標與指標設定、功能開關、排程設定（僅 Robin）、APP設定四類可編輯頁面；高頻「記一筆」操作仍以 Telegram 為主 ②登入機制由 `APP Access Token` 改為帳密登入 ③密碼儲存採單向雜湊（bcrypt/argon2），「忘記密碼」改為「系統產生新隨機密碼覆蓋舊密碼並透過 Telegram 發送」（重設，非復原） ④保持登入採 Refresh Token 機制，效期 30 天，存於裝置本機 Expo SecureStore ⑤排程設定範疇限縮為 Robin 專屬的 6 項既有排程功能 ⑥目標與指標設定頁面補上盤點發現的 3 處遺漏（求職履歷/期望工作、證照每日出題設定、技術情報主題訂閱）。

**替代方案**：密碼採可逆加密儲存（已否決，一旦金鑰或資料庫外洩，所有密碼會同時明碼曝光，風險遠高於「忘記密碼」情境本身的體驗損失）；排程設定開放給所有使用者所有排程（已否決，需額外設計「每個使用者各自獨立排程」的資料模型，複雜度與實際需求不成比例）。

**理由**：App 端目前已經是使用者最常拿在手上的介面，結構化表單類設定用 App 操作體感更好，但高頻的「記一筆」操作留在 Telegram 因為一句話就能講完；忘記密碼流程要求系統能把可用密碼交給使用者，若採單向雜湊系統本身也無法還原明碼，只能重設為新密碼——這是資安最佳實踐與原始需求之間風險最低的折衷。

**後果**：`users` 表新增欄位規劃（`password_hash`、`refresh_token_hash`、`refresh_token_expires_at`）取代原本規劃的 `app_access_token`；Phase 4 開工時的實作規模比原規劃大，建議依風險與相依順序拆成更細的子 Step 逐一推進（登入與 Token 機制→唯讀分析頁面→個人基本資訊＋目標設定→功能開關＋APP設定→排程設定）。

## 2026-08-11 [標籤：AI] FR-64a 藍牙體重計方案終止：Web Bluetooth／Bluefy POC 失敗，全面移除 BLE 改為手動輸入體重

**狀態**：accepted（supersede robinson SPEC.md 2026-08-08 新增的 FR-64a 藍牙體重計規格）

**背景**：FR-64a 原規劃由 App 直接連藍牙體重計（廣播名稱 `Yoda1`）自動寫入體重。原生 BLE 版本已實作完成（`react-native-ble-plx` 掃描、Yoda1 穩定封包 `13 88 00 00 25 00` 解析、Big Endian 除以 100 換算公斤、`POST /api/app/body/weight-logs` 寫入），但原生 BLE 模組不支援 Web、Expo Go 與模擬器，必須做 Development Build 才能實機使用。Robin 因此提出零成本替代方案：改用 PWA＋Bluefy（iOS 上支援 Web Bluetooth 的第三方瀏覽器），這樣就不必走 Development Build 或 App Store／Google Play 發布。

**討論內容**：建立隔離的 `/ble-test` 診斷頁做相容性 POC，不動正式登入、首頁量測與體重寫入流程，並用免帳號 Cloudflare Quick Tunnel 提供臨時 HTTPS 網址給 iPhone 實測。三次 iPhone／Bluefy 3.9.3 實機測試結果：①第一次確認 HTTPS、`navigator.bluetooth`、Yoda1 裝置選擇與 `watchAdvertisements()` 全部可用 ②第二次 `requestDevice()` 能選到 Yoda1、`watchAdvertisements()` method 存在，但 15 秒內完全沒有觸發 `advertisementreceived`，也沒有 Manufacturer Data 空值或解析失敗紀錄——問題出在瀏覽器沒把廣播事件交給 Web App，而不是 Yoda1 parser ③追加 `navigator.bluetooth.requestLEScan()` 做最後相容性檢查，最終確認 Bluefy 不提供該 API，回退的 `watchAdvertisements()` 仍收不到任何事件。

**決策**：①PWA＋Bluefy 方案否決，不採用 ②同時決定連原生 BLE 一起全面移除：Android、iOS 與 Web 全平台不再掃描 Yoda1、不要求藍牙權限、不保留 Development Build 專用套件 ③體重改為手動輸入——首頁體重卡片按鈕由「開始量測」改為「記錄一下」，開啟 App 內 Modal 輸入，範圍固定 `40.0～150.0 kg`（含邊界）、統一四捨五入至小數點後第一位、第二層「XX.X 公斤是否正確？」確認後才呼叫 API ④API 邊界同步強制 `40～150 kg` 驗證與後端四捨五入，即使繞過前端直接呼叫也不能落地超範圍數值。

**替代方案**：走 Expo Development Build ＋原生 BLE（已否決，等同要求 Robin 與家人安裝非商店版本 App，維運與發布成本高於「手動輸入一個數字」省下的力氣）；維持 PWA＋Bluefy（已由三次實機 POC 否決，`Connectable: No` 的被動廣播體重計無法把資料交給 Web App）。

**理由**：Yoda1 是不可連線（`Connectable: No`）的被動廣播裝置，Web Bluetooth 在 Bluefy 上拿不到它的 Manufacturer Data，這是瀏覽器能力限制而非實作缺陷，沒有繞路空間；而保留原生 BLE 就得綁 Development Build，對一個家用小工具而言投報率不成比例。

**後果**：刪除 `mobile/src/services/weightScale*.ts`、`mobile/src/services/weightScaleProtocol.ts` 與 `mobile/app/ble-test.tsx`；`mobile/app.config.ts` 移除 BLE config plugin、iOS 藍牙用途文字與背景藍牙設定；`mobile/package.json`／`pnpm-lock.yaml` 移除 `react-native-ble-plx@3.5.1`、`expo-dev-client@57.0.11` 及 8 個相關安裝項目，並刪除只為此建立的 `mobile/pnpm-workspace.yaml`。實機驗證完成後已關閉 Cloudflare Quick Tunnel，臨時網址失效。SPEC.md 的 FR-64a 已同步改為「藍牙體重計整合已全面移除，改為手動輸入按鈕『記錄一下』」。

## 2026-08-12 [標籤：AI] FR-69／FR-70／FR-71（目標與指標設定／功能開關／排程設定頁）本輪整批跳過

**狀態**：accepted

**背景**：Step 4.4／4.5 主線開發（FR-64／FR-64a／FR-65／FR-67／FR-68／FR-72）由 Codex Desktop 完成並準備收尾，`docs/ADR/discuss/mobile-app.md` 2026-08-09 條目原規劃的四類可編輯設定頁面中，「目標與指標設定」（FR-69）、「功能開關」（FR-70）、「排程設定，僅 Robin」（FR-71）三頁尚未開工。Robin 明確指示本輪先不做，只完成 APP 設定（FR-72）與其餘既定範圍。

**決策**：FR-69、FR-70、FR-71 本輪全部跳過，不建立頁面、API 或資料表；右上角個人選單「APP 設定」直接接在「個人基本資訊」之後、登出之前，不預留這三項的入口。既有 Telegram 對話流程（`/set_body_goal`／`/my_toggles`／`/set_toggle` 等）維持原樣，不受影響，使用者仍可透過 Telegram 完成對應設定。

**替代方案**：本輪一併做完（已否決，Robin 評估這三頁的實作規模與目前優先順序不成比例，決定先讓已完成的部分正式上線，其餘留待未來有實際需求再排入）。

**理由**：「記一筆」等高頻操作已透過 Telegram 覆蓋；FR-69～FR-71 屬於低頻率的結構化設定操作，透過 Telegram 既有指令仍可達成同樣效果，App 端補齊的急迫性較低，優先讓已完成的登入/分析/個人資訊/APP設定盡快正式上線更符合效益。

**後果**：`docs/specs/SPEC.md`「羅賓森 Mobile App」區塊 FR-69～FR-71 標註為「依 Robin 指示跳過，不排入目前 Roadmap」；`docs/specs/PROGRESS.md` 時程與任務狀態表新增一列追蹤（狀態：待辦）。未來若要重新排入 Roadmap，需先確認實際需求並回到本檔案新增後續決策紀錄，不直接覆寫本條。

## 2026-08-12 [標籤：AI] 收藏清單／旅遊行程／探索地圖／成果展示新功能方向與地圖技術選型

**狀態**：pending（規格尚未走過確認流程、未收錄進 `docs/specs/SPEC.md`；索引見 `docs/specs/DRAFT.md` 待討論）

**背景**：Mobile App 主線（FR-64／FR-64a／FR-65／FR-67／FR-68／FR-72）落地後，Robin 提出一組規格範圍外的新方向：把「想去但還沒去」的餐廳、景點、山岳、住宿、活動先存成收藏清單，規劃時併進旅遊行程，實際去過之後變成探索地圖上的紀錄，符合條件再形成成果卡片。這組功能需要地圖能力，而目前實際交付方式是 Expo Web 網址（iPhone 與 Android 都用瀏覽器開），因此得先確認跨平台地圖方案可行才談功能規格。

**討論內容**：先做隔離的 `mobile/app/map-poc.tsx` 技術驗證頁（三筆假資料、不讀寫正式資料），比較 Leaflet＋OpenStreetMap 與 Expo Maps。之後接著完成收藏清單第一階段實作（`0071`～`0077` migration、`app_collections` Service／API、首頁收藏卡片與唯讀收藏頁），並在過程中把整組功能的產品邏輯談定。

**決策**：①地圖採 Leaflet 1.9.4＋OpenStreetMap 圖磚，不採 Expo Maps ②四項功能的生活流程定為「收藏清單 → 旅遊行程 → 探索紀錄 → 成果卡片」 ③首頁是三者的資料維護入口（新增／編輯／刪除），左側選單進入的頁面只負責顯示、篩選與分析 ④這三項不受「Mobile App 僅提供今日紀錄」限制，可異動不同日期的紀錄 ⑤旅行支出仍以既有 `transactions` 為唯一金額來源，用 `trip_id` 關聯行程，旅遊行程不另存一份相同支出 ⑥刪除行程時，收藏、探索事件與記帳只把 `trip_id` 設為 `NULL`，只有行程內專屬日程項目隨行程刪除 ⑦地址搜尋若後續由後端代理 OpenStreetMap Nominatim，必須遵守公開服務限制：由使用者明確按下搜尋才呼叫、不得做即時自動完成、全應用每秒最多一次請求、提供識別資訊與署名、快取結果，並保留日後替換搜尋服務的能力。

**替代方案**：Expo Maps（已否決，官方套件只支援 Android／iOS 原生、目前仍為 alpha、不支援 Expo Go，且 Android 需要 Google Maps SDK 設定，與「用瀏覽器開 Expo Web 網址」的實際交付方式不合）。

**理由**：Leaflet 是純前端方案，在 Expo Web 直接可用、免金鑰、免原生建置，Web bundle 也可延遲載入（實測延遲載入 bundle 約 149 KB、CSS 約 11 KB），對目前的交付方式最省事；OpenStreetMap 圖磚免費但屬公共服務，所以搜尋代理的使用限制必須一開始就寫進決策，避免日後被封鎖。

**後果**：`mobile/package.json` 新增正式依賴 `leaflet@1.9.4` 與型別依賴 `@types/leaflet@1.9.22`；正式功能的地圖必須顯示 OpenStreetMap 著作權署名。目前只有「收藏清單」完成正式輸入與 API 串接，「新增探索」與「新增成果」仍是待開發功能（不得以導頁至說明頁視為完成 CRUD）；`0071`～`0077` migration 檔案已建立但尚未手動套用。整組功能尚未走規格確認流程，也還沒收錄進 `docs/specs/SPEC.md`，需先定案才能排入 Roadmap。
