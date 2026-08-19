# 羅賓森 Mobile App 修復紀錄

> 同一功能的多次除錯都寫在同一個檔案，依時間往下附加新段落，不要開新檔案。不論有沒有改 code 都要記。
> 本檔初版整併自 `docs/specs/_archive/codex.md`（Codex 開發異動紀錄）中屬於「問題／修復」性質的段落；決策性質的段落已改放 `docs/ADR/discuss/mobile-app.md`。

## 2026-08-11 本機登入預覽環境 `APP_JWT_SECRET` 長度不足導致身分辨識回傳 503

**現象**：本機重新啟動 Flask 後，Mobile App 預覽登入失敗，`POST /api/app/auth/identify` 回傳 `503`；畫面看起來像是使用者 ID 或密碼錯誤。

**排查過程**：確認前端 Expo Web 回傳 `200`、後端程序有在跑，再回頭檢查 `AppAuthService` 的啟動檢查條件，發現重新啟動的程序只載入既有環境設定，`APP_JWT_SECRET` 沒設定或不足 32 字元。

**根因**：FR-65 的 `AppAuthService` 規定 `APP_JWT_SECRET` 至少 32 字元，缺少或長度不足時會拒絕建立認證服務（安全設計，非 bug）；本機啟動環境沒有提供合格的 Secret，因此所有認證路由都回 `503`。

**修復方式**：未改 code。停止該錯誤設定的 Flask 程序，改用 `openssl rand -hex 32` 在啟動當下產生不輸出的臨時 Secret，以 `/private/tmp/life-assistant-bot-backend` 隔離環境重新啟動後端。臨時 Secret 只存在程序記憶體，未寫入 `.env`、`.env.example` 或任何專案檔案。

**驗證方式**：`POST /api/app/auth/identify` 以 `user01` 回傳 `200`，Expo Web 回傳 `200`，登入預覽恢復。後端重啟後既有 Token 會失效，需重新登入。

## 2026-08-11 登入頁跨流程錯誤狀態殘留（密碼錯誤訊息卡在忘記密碼流程）

**現象**：使用者先觸發一次密碼錯誤，再點「忘記密碼」且未填使用者 ID 時，畫面同時顯示「請輸入使用者ID」與上一輪殘留的密碼錯誤訊息。

**排查過程**：檢視 `mobile/app/login.tsx` 的錯誤狀態管理，發現忘記密碼流程只設定 `userIdError`，沒有清掉前一次登入流程留下的 `passwordError`。

**根因**：兩條流程共用同一組錯誤 state，但忘記密碼進入點沒有重置與自己無關的錯誤欄位。

**修復方式**：`mobile/app/login.tsx` — 忘記密碼流程開始前先清除 `passwordError`。

**驗證方式**：未輸入使用者 ID 點忘記密碼時，只顯示使用者 ID 紅框與「請輸入使用者ID」，不再殘留密碼錯誤訊息。

## 2026-08-11 React Native Web 上 `Alert.alert` 多按鈕 callback 不可靠，登出確認無法執行

**現象**：Web 版點「登出」跳出的原生 `Alert.alert` 確認視窗，按下按鈕後 callback 不一定被執行，使用者可能停在首頁沒有真的登出。

**排查過程**：確認登出 API 與 Token 清除邏輯本身正確，問題只發生在 Web 平台；`Alert.alert` 的多按鈕形式在 React Native Web 沒有可靠實作。

**根因**：跨平台元件差異——`Alert.alert` 的多按鈕 callback 在 React Native Web 無法可靠執行。

**修復方式**：`mobile/src/components/AppShell.tsx` — 移除原生 `Alert.alert`，改為 App 內自訂 Modal（標題「確認登出？」＋取消／登出兩顆按鈕）；確認登出後等待本機 Session 清除，再明確執行 `router.replace('/login')`。同時在 `mobile/src/context/AuthContext.tsx` 把登出 API 例外收進 `finally`，即使後端暫時不可用也一定會清掉 Access Token、Refresh Token 與本機登入狀態。

**驗證方式**：Mobile TypeScript 與 Expo Web production export 通過；瀏覽器實測確認取消只關視窗、確認才登出並導回登入頁。

## 2026-08-11 待辦查詢回傳「日期區間必須介於 7 到 30 天」（前後端日期規則不一致）

**現象**：待辦頁前端已改為允許 1～7 天區間，但實際查詢單日或 2～6 天時，API 回傳錯誤「日期區間必須介於 7 到 30 天」。

**排查過程**：比對前端 `DateRangeFilter` 的 `minDays`／`maxDays` 參數與後端 `app_analytics` 的日期解析路徑，發現待辦 API 仍走共用的 `parse_date_range()`。

**根因**：待辦的新日期規則只改了前端，後端待辦端點仍沿用所有分析模組共用的 7～30 天、禁止未來日期解析器。

**修復方式**：`src/services/app_analytics.py` 新增待辦專屬的 `parse_todo_date_range()`（ISO 解析、起迄順序、1～7 天，不檢查未來日期上限）；`src/api/app_analytics.py` 讓 `/api/app/analytics/todos` 改用該解析器，其他模組維持原解析器不受影響。

**驗證方式**：新增後端測試——單日、7 天、跨到未來年份皆接受；8 天、起迄顛倒與非法格式皆拒絕；API 測試確認未來單日回 `200`、8 天回 `400` 與「日期區間必須介於 1 到 7 天」，且 finance 短於 7 天仍回原本的 7～30 天錯誤（規則沒有互相污染）。後端服務／API 測試 34 項全部通過。

## 2026-08-11 預覽服務無回應（HTTP 000），誤以為是頁面路由錯誤

**現象**：使用者回報無法開啟預覽頁面。

**排查過程**：檢查 `localhost:8080`（Flask）與 `localhost:8081`（Expo Web）均回傳 HTTP code `000`，代表根本沒有程序在回應，不是路由或畫面錯誤。

**根因**：本機開發程序（後端與 Expo Web）已停止。

**修復方式**：未改 code。以只載入、不輸出 `.env` 的方式重新啟動 Flask 後端，並重新啟動 Expo Web（Metro 完成 1174 modules bundle）。

**驗證方式**：前端回傳 `200`；後端受保護的 `/api/app/dashboard` 未帶 Token 回傳預期 `401`。migration runner 回報 schema 已是最新狀態，沒有重複套用。

## 2026-08-11 Dashboard 聚合查詢參數數量與位置不一致

**現象**：以實際 PostgreSQL 驗證 Dashboard 查詢時，新增摘要欄位後查詢失敗。

**排查過程**：對照 SQL 佔位符與傳入參數列表，發現新增欄位後參數數量與位置對不上。

**根因**：Dashboard 聚合查詢一次新增多組日期條件，參數是以位置傳入，改動後沒有同步調整順序與數量。

**修復方式**：`src/services/app_analytics.py` — 改為明確的 14 組日期參數＋最新體重單參數＋3 組日期參數。

**驗證方式**：實際 Neon／PostgreSQL 唯讀查詢成功回傳全部 18 個摘要欄位；驗證過程未新增、修改或刪除正式資料。

## 2026-08-11～2026-08-12 本機工具鏈重複踩雷：`node` 不在 PATH 與 pnpm store 不一致

**現象**：多輪開發中反覆出現 `node: not found`、`ERR_PNPM_UNEXPECTED_STORE`、`npx` 找不到、非互動終端觸發 pnpm modules purge 保護等錯誤，導致 `typecheck`／`build:web`／Expo 指令中止。

**排查過程**：確認錯誤都發生在指令啟動階段而非程式執行階段；`pnpm install && pnpm exec tsc` 放同一行時，PATH assignment 只作用於前一段；`mobile/node_modules` 連結的是 `/Users/robinma/Library/pnpm/store/v11`，而指令預設改用專案 `.pnpm-store/v11`。

**根因**：本機 Shell 沒有全域 `node`／`npm`／`npx`；且既有 `node_modules` 與指令預設的 pnpm store 路徑不同，屬工具環境差異，不是專案程式或依賴錯誤。

**修復方式**：未改專案 code。統一改用 Codex 工作區既有的 bundled Node／pnpm runtime 絕對路徑執行，且指令分段跑而不是串在同一個 shell command；安裝套件時以 `--store-dir` 明確指定既有 store（例如 `pnpm add expo-image-picker@~57.0.9 --store-dir ../.pnpm-store`），全程不刪除或重建使用者的 `node_modules`。

**驗證方式**：重跑後 TypeScript `tsc --noEmit` 與 Expo Web production export 全數通過，未新增或下載任何正式依賴。

## 2026-08-12 實體手機照片辨識回傳 404（舊 Flask 程序未載入新路由）

**現象**：手機實測「拍照」與「從相簿選擇」都顯示「操作失敗，請稍後再試」。

**排查過程**：代理存取紀錄確認兩者都有正確送出 `POST /api/app/diet/recognize-photo`，但回傳 HTTP `404`，排除手機權限、圖片格式與 Gemini 回應問題。

**根因**：本機後端仍在跑「載入照片辨識路由之前」就啟動的舊 Flask 程序，新路由根本不存在於該程序。

**修復方式**：未改 code。經使用者明確允許後，以只載入、不輸出 `.env` 的方式重新啟動 Flask，並補上不寫入檔案的本機預覽專用 JWT Secret 與 HTTPS 預覽 CORS origin。重新啟動時 migration runner 首次補套用 `0069_create_important_days.sql` 與 `0070_add_date_ranges_to_important_days.sql`；再次啟動確認 schema 已最新、沒有重複套用。

**驗證方式**：公開 HTTPS 預覽 `/healthz` 回 `200`、`user01` 身分辨識回 `200`；未帶 Token 呼叫照片辨識路由回預期 `401`，證明路由已載入且受登入保護，不再是 404。因 JWT Secret 重設，手機需重新登入後再測。

## 2026-08-12 使用者 ID 失焦驗證造成登入按鈕完全無回應

**現象**：使用者輸入尚未辨識的 ID 後直接點「登入」，畫面既沒有送出登入驗證，也沒有顯示「很抱歉，我無法辨識您」，按鈕像是完全沒反應。

**排查過程**：追事件順序發現點擊登入時，輸入框會先觸發 `onBlur`，把 ID 驗證狀態改成 `checking`。

**根因**：登入按鈕原本在 `checking` 狀態會立即被設為 disabled，導致同一次點擊的 `onPress` 在事件送達前就被取消。

**修復方式**：`mobile/app/login.tsx` — 登入按鈕不再因背景 ID 辨識處於 `checking` 而禁用，只在真正送出登入或忘記密碼處理期間禁用；`handleLogin()` 仍會等待 `validateUserId()` 完成，ID 確認存在後才檢查密碼。密碼欄在 ID 未確認或確認不存在時仍維持不可輸入。

**驗證方式**：TypeScript 型別檢查與 Expo Web production export 通過；瀏覽器實測輸入不存在的 `user10`、不輸入密碼直接點登入，使用者 ID 欄正確顯示「很抱歉，我無法辨識您」，不會誤顯示缺少密碼。同時發現該預覽程序的 `APP_JWT_SECRET` 長度不足導致身分辨識 API 服務錯誤，已用符合 FR-65 最低長度的本機預覽 Secret 重啟後端（未寫入程式碼或 `.env.example`）。

## 2026-08-12 首頁心情趨勢卡片被撐成異常高度

**現象**：首頁「心情趨勢」滿寬卡片高度異常拉長。

**排查過程**：檢查卡片樣式繼承鏈，發現心情卡片放在直向容器時仍繼承雙欄卡片的 `flexBasis: 46%`。

**根因**：`flexBasis: 46%` 在直向 flex 容器中會被套用到「高度」方向，因此把卡片縱向撐開。

**修復方式**：`mobile/app/home.tsx` — 心情卡片改用專屬樣式 `flexBasis: auto`、`flexGrow: 0`、`width: 100%`，高度回復由內容與既有 padding 決定。

**驗證方式**：TypeScript `tsc --noEmit` 與 Expo Web production export 通過；重新載入 `http://localhost:8081/home`，瀏覽器量測心情卡片約 700×94 px，已無異常縱向撐張。

## 2026-08-12 Web 預覽登入無法連線（三個疊在一起的問題）

**現象**：`http://localhost:8081` 頁面與 `/healthz`、`/api/app/auth/identify` 都回 `200`，後端也能正常辨識 `user01`，但畫面上的登入與身分辨識請求就是失敗；修正過程中還一度整頁全白。

**排查過程**：比對「頁面可開啟」與「請求失敗」的落差，檢查 Web bundle 內容發現內嵌了舊網址；全白畫面則從 React 錯誤 `Rendered fewer hooks than expected` 追到 Hook 呼叫順序；換 bundle 後仍偶發白畫面，再確認是瀏覽器沿用了舊的 `index.html`。

**根因**：① 舊 Web bundle 仍內嵌前一個已失效的 Cloudflare Quick Tunnel 網址，請求被送往過期網址（與使用者 ID、密碼或資料庫帳號無關） ② 自動辨識的 `useEffect` 被放在「已登入即 Redirect」的條件回傳之後，Refresh Token 成功還原工作階段時會少執行一個 Hook，觸發 React 中止渲染 ③ 外部瀏覽器快取了舊 `index.html`，新 bundle hash 換掉後舊 HTML 參照到不存在的資源。

**修復方式**：`mobile/src/services/authApi.ts` — Web 平台 API Base URL 改用目前頁面的 `window.location.origin`，本機 `localhost`、新 HTTPS Tunnel 或正式網址都走同一 origin 下的 `/api/*`；iOS／Android 原生建置仍沿用 `EXPO_PUBLIC_API_BASE_URL`。`mobile/app/login.tsx` — 把 Redirect 判斷移到所有 Hook 之後，讓每次 render 的 Hook 數量穩定；同時加上使用者 ID 停止輸入 350ms 後自動辨識。本機暫存預覽代理 `/private/tmp/robinson_mobile_preview.py` 靜態回應補上 `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`、`Pragma: no-cache`、`Expires: 0`（該代理屬本機預覽工具，不是正式專案原始碼）。

**驗證方式**：重新產生 `mobile/dist` 並確認 bundle 已不含過期 Tunnel 網址；重啟預覽後 `/login`、Web bundle 與 `/healthz` 均回 `200`，登入頁 DOM 完整顯示；TypeScript 與 Expo Web export 通過（Hook 修正後 Metro 完成 1200 modules，新 bundle hash 為獨立版本）；瀏覽器實測 `user01` 辨識後，密碼欄由「請先確認使用者ID」切換為可輸入的「請輸入密碼」。

## 2026-08-14 Expo 本機預覽登入 API 回傳 404

**現象**：新啟動的 `http://localhost:8082/login` 可顯示登入頁，但使用者辨識與登入無法完成。
**排查過程**：直接呼叫預覽站的 `/api/app/auth/identify`，確認回傳 HTTP 404；比對 `authApi.ts` 的 Web API Base URL 選擇邏輯。
**根因**：Web 平台一律使用 `window.location.origin`，Expo 開發伺服器只有前端靜態資源、沒有 Flask `/api/*` 路由，因此請求被送到錯誤的 8082 連接埠。
**修復方式**：`mobile/src/services/authApi.ts` 在 localhost／127.0.0.1 預覽時改用 `EXPO_PUBLIC_API_BASE_URL`；正式同網域部署仍使用 `window.location.origin`，原生 App 亦維持使用設定值。
**驗證方式**：TypeScript typecheck 通過；Expo 於 `http://localhost:8081` 重啟；正式 API 對 localhost Origin 回傳 CORS 與 `{"recognized": true}`；瀏覽器實測輸入 `user01` 後點登入，密碼欄由停用改為可輸入。

## 2026-08-14 首頁「新增收藏」Modal 在手機窄螢幕跑版

**現象**：實體手機開啟首頁「收藏清單」的「新增收藏」視窗後，類型按鈕換行時「其他」與下一個「國家」標題重疊；捲動到底部時，取消／確認按鈕覆蓋備註輸入框，造成欄位與操作區無法正常閱讀。

**排查過程**：依使用者提供的兩張實體手機截圖與 `CollectionModal` 樣式定位；類型容器雖可換行，但表單欄位曾帶伸展樣式，底部操作區也未與捲動內容保留穩定間距。

**根因**：窄螢幕下欄位容器與選項換行高度互相擠壓；操作區位於同一捲動內容但留白不足，導致備註框與按鈕視覺重疊。

**修復方式**：調整 `mobile/src/components/CollectionModal.tsx`：移除欄位不必要的伸展、固定表單與操作區間距、保留 Modal 內 ScrollView，並同步移除已取消的優先程度／日期／縣市／手動狀態欄位。

**驗證方式**：TypeScript typecheck 通過；仍需 Robin 以手機窄螢幕實機確認類型按鈕換行、完整欄位捲動，以及底部操作列不遮擋輸入內容。

## 2026-08-14 探索地圖誤標為全部完成

**現象**：`PROGRESS.md` 將 FR-73～FR-76a Phase 5 整體標示為完成，但新建收藏只保存地址，Mobile 表單沒有取得經緯度；探索地圖只能顯示既有座標資料，無座標造訪會進入「無法定位」清單。

**排查過程**：核對 `SPEC.md` 技術棧、`CollectionModal.tsx`、`app_collections.py` 與 `app_life_exploration.py`。確認後端資料結構可接收與保存 `latitude`／`longitude`，Leaflet 地圖也能呈現既有座標，但專案沒有 Nominatim Geocoding API，Mobile 表單不會產生座標，探索地址更新也只更新文字欄位。

**根因**：開發驗收只確認 Leaflet 地圖、探索快照、篩選、標記聚合與無法定位清單，誤將「可以保存無座標資料」視為完整定位流程，漏查地址轉座標與重新定位的端到端路徑。

**修復方式**：本次只校正文件：`SPEC.md` 補列 Leaflet／OpenStreetMap 為使用中、Nominatim 為待開發，FR-75 改為部分完成；`PROGRESS.md` 降級 Phase 5 狀態；`api_schema.md` 明確標示尚無 Geocoding／重新定位 API。程式碼尚未異動。

**驗證方式**：以程式碼搜尋確認目前僅資料欄位與地圖呈現層使用經緯度，沒有 Nominatim 呼叫或 Geocoding API；待後續完成定位功能後，需重新驗證新增收藏定位、定位失敗、修改地址後重新定位、快取與每秒一次限制。

## 2026-08-14 補齊 FR-75 地址定位端到端流程

**現象**：承接前一筆誤標紀錄，收藏地址與探索快照缺少可實際產生、更新座標的端到端流程。

**排查過程**：依 FR-75／NFR-15 與 Nominatim 公開服務政策核對表單、API、Service、Migration 與探索地圖資料流；另發現修改地址、國家或區域／城市時若未清除舊座標，地圖會繼續顯示失效位置。

**根因**：原流程只保存文字地址與選填座標，未建立 Geocoding Service、明確定位操作、快取與重新定位入口，也未處理地址異動後的座標失效。

**修復方式**：新增 `src/services/geocoding.py`、`0080_create_geocoding_cache.sql`、收藏 Geocoding API 與探索重新定位 API；Mobile 收藏表單新增明確定位按鈕，探索編輯提供「僅儲存／儲存並重新定位」。地址、國家或區域／城市改變時清除舊座標；後端使用識別 User-Agent、每秒一次節流與 PostgreSQL 快取，定位失敗仍允許保存至無法定位清單。

**驗證方式**：Geocoding／收藏／探索相關後端 34 項測試通過，包含快取、User-Agent、每秒一次、找不到、斷線、API 身分與地址異動清除舊座標；Mobile TypeScript typecheck 與 Expo Web export 通過。尚待部署套用 `0080`、設定 `NOMINATIM_USER_AGENT` 並以實際地址驗收。

## 2026-08-14 台中市北屯區軍福十六路 356 號無法定位

**現象**：Mobile App 新增收藏時輸入「台中市北屯區軍福十六路356號」，按下「定位地址」後顯示找不到。

**排查過程**：以正式程式相同的 Nominatim Search API 查詢完整地址，以及拆分為「軍福十六路356號、北屯區、台中市、台灣」，兩者皆回傳空陣列；移除門牌、只查「軍福十六路、北屯區、台中市、台灣」則可取得該道路資料。

**根因**：OpenStreetMap／Nominatim 目前有軍福十六路道路資料，但沒有可匹配 356 號的門牌節點或地址插值資料；不是 App 查詢參數或字串組合錯誤。

**修復方式**：依 Robin 核准的新規則，Geocoding 改為精確門牌、道路、城市逐級放寬；完整門牌找不到時移除門牌號碼查詢道路，並在 Mobile 顯示「道路近似位置」及 Nominatim 實際名稱。地址改為選填，未填地址可用國家與區域／城市執行「定位區域」。

**驗證方式**：新增精確、道路 fallback、無地址城市定位與完全找不到測試；實際 Nominatim 查詢確認「軍福十六路, 台中市北屯區, 台灣」可回傳道路座標 `24.1750552, 120.7247448`。

## 2026-08-14 收藏清單「標記已造訪／刪除」按鈕無反應

**現象**：成功新增收藏後，在 Mobile Web 收藏清單點擊「標記已造訪」或「刪除」皆沒有可見反應。

**排查過程**：核對 `mobile/app/collections.tsx` 的三個卡片操作。編輯會直接開啟自製 Modal；標記已造訪與刪除則共同依賴 React Native `Alert.alert()` 的多按鈕確認回呼，實際 API 呼叫只寫在 Alert 按鈕的 `onPress` 內。

**根因**：Expo Web／PWA 環境未可靠執行 React Native `Alert.alert()` 多按鈕確認流程，導致確認視窗或按鈕回呼沒有觸發；兩個功能因此同時失效，後端 API 並未收到請求。

**修復方式**：以專案既有樣式的跨平台自製確認 Modal 取代兩處 `Alert.alert()`，保留刪除二次確認、5 秒復原、標記造訪確認、防連點及 API 成功／失敗訊息。

**驗證方式**：TypeScript typecheck、Expo Web export 與相關後端 39 項測試均通過。尚待 Robin 實機驗證兩種確認、取消、API 成功、API 失敗及刪除復原流程。

## 2026-08-14 探索地圖「刪除」按鈕無反應

**現象**：在 Mobile Web／PWA 的探索地圖下方造訪紀錄卡片點擊「刪除」後沒有可見反應，探索紀錄未刪除。

**排查過程**：核對 `mobile/app/exploration.tsx`，確認刪除 API 已存在，但前端把實際 `deleteExploration()` 呼叫放在 React Native `Alert.alert()` 多按鈕確認回呼內；此寫法與先前收藏清單「標記已造訪／刪除」無反應的實作模式相同。

**根因**：Expo Web／PWA 環境未可靠執行 React Native `Alert.alert()` 多按鈕確認流程，因此刪除確認回呼沒有觸發，後端 API 未收到請求。

**修復方式**：已在 `mobile/app/exploration.tsx` 改用跨平台自製確認 Modal，並補上防連點、處理中、成功／失敗訊息及刪除後 5 秒復原。

**驗證方式**：Python 語法編譯、`git diff --check`、Mobile TypeScript typecheck 與 Expo Web export 通過；目前 Python 環境缺少 pytest，後端自動測試及 Robin 實機確認／取消／刪除／失敗重試／復原流程仍待執行。
## 2026-08-14 探索地圖篩選器與定位提示漏套用
**現象**：探索地圖「走過的地方，都留在地圖上」區塊下方未顯示定位精度提醒，國家與區域／城市仍以橫向按鈕呈現，未改為可搜尋、可選擇的下拉選單。
**排查過程**：比對 `mobile/app/exploration.tsx`、`mobile/src/components/CollectionModal.tsx` 與 `mobile/src/components/SearchableSelect.tsx`，確認定位提醒及組合式下拉選單只套用於收藏表單，探索地圖仍保留舊 `Filter` 元件。
**根因**：上一輪實作只完成收藏與旅遊行程的地點欄位，漏掉探索地圖篩選畫面。
**修復方式**：`mobile/app/exploration.tsx` 改用共用 `SearchableSelect`，並補上已定案的定位精度提醒；`SearchableSelect` 新增篩選情境需要的「全部」與禁止自訂值選項。
**驗證方式**：Mobile TypeScript typecheck 通過；仍待實機驗證國家切換清除城市、全部／空值恢復完整地圖，以及深淺色與手機窄螢幕顯示。

## 2026-08-14 新增旅遊行程行事曆漏顯示今日樣式
**現象**：新增／編輯旅遊行程的行事曆雖已顯示休假日、節日與重要日子，但今日日期沒有比照其他行事曆顯示紅底白字。
**排查過程**：比對 `mobile/app/trips.tsx` 的自訂 `dayComponent` 與 `DateRangeFilter`、重要日子設定頁的今日判斷，確認旅遊行程日期格沒有計算 `isToday`，亦未套用今日樣式。
**根因**：行程行事曆整合共用日曆資料時，只移植活動標籤，漏掉今日視覺規則。
**修復方式**：`mobile/app/trips.tsx` 補上台灣時區今日判斷及紅底白字樣式；今日樣式置於區間樣式之後，確保落在選取區間時仍優先顯示。
**驗證方式**：Mobile TypeScript typecheck 通過；仍待實機驗證今日未選取、位於區間起點／中間／終點時的視覺結果。

## 2026-08-14 重要日子設定 API 回傳 503
**現象**：進入「重要日子設定」頁面時顯示「重要日子目前無法載入，請稍後再試」。
**排查過程**：確認該訊息由 `GET /api/app/important-days` 捕捉未預期例外後回傳 503；查詢直接引用較新 migration 才加入的 `important_day_occurrences.occurrence_end_date`，部署資料庫若有欄位版本落差會在整份清單載入前失敗，且原 API 未留下伺服器端例外日誌，無法從安全的使用者訊息辨識原因。
**根因**：部署環境的實際例外仍須推版後由 Render 日誌確認；程式層已確認存在對 occurrence 區間欄位的硬相依，且缺少安全診斷日誌，會讓 schema 落差直接表現為無資訊的 503。
**修復方式**：`src/services/app_important_days.py` 改用 `TO_JSONB(o)` 安全讀取可選的結束日欄位，舊 schema 缺欄位時退回單日行為；`src/api/app_important_days.py` 新增只寫入伺服器端的例外日誌，對使用者仍維持安全訊息。
**驗證方式**：Python compileall 通過；本機環境缺 pytest，Service／API 自動測試未執行。需部署後驗證空清單、既有事件、行程連動事件與通知對象，並以 Render 日誌確認是否仍有其他資料庫例外。

## 2026-08-14 重要日子家庭成員查詢誤用不存在欄位
**現象**：進入「重要日子設定」頁面時顯示「重要日子目前無法載入，請稍後再試」；Render 日誌顯示查詢 `users.app_user_id` 時發生 `UndefinedColumn`。
**排查過程**：比對 `src/services/app_important_days.py`、登入使用者 ID 規則與正式 migration，確認 App 使用者 ID 是由 `users.id` 動態格式化為 `user01`、`user10`，`users` 表並沒有持久化 `app_user_id` 欄位。
**根因**：`family_users()` 誤將衍生值 `app_user_id` 當成資料庫實體欄位查詢；既有 FakeDatabase 測試資料也自行加入該欄位，未能反映正式 schema。
**修復方式**：`src/services/app_important_days.py` 改為只讀取 `users.id`、`users.role`，再依 FR-65 規則由資料庫 ID 動態產生 `user01`、`user10`；同步移除測試假資料中不存在的欄位並新增格式回歸測試。
**驗證方式**：Python compileall、直接格式化檢查與 `git diff --check` 通過。環境缺少 pytest／bcrypt，Service／API 自動測試未執行；仍待部署後確認重要日子頁面及指定家人清單可載入。

## 2026-08-14 求職分析查詢錯用契合度欄位名稱
**現象**：「求職分析」頁面持續顯示「資料目前無法載入，請稍後再試」，重新載入仍回傳相同錯誤。
**排查過程**：比對 `src/services/app_analytics.py` 的求職分析 SQL 與 `0058_add_scoring_fields_to_job_postings.sql`，確認正式欄位名稱為 `score`，分析 SQL 與測試假資料卻使用 `match_score`；分析 API 的未預期例外目前未寫入伺服器日誌。
**根因**：求職分析 SQL 查詢不存在的 `job_postings.match_score`，且測試 fixture 沿用同一錯誤欄位名稱，未能攔截 schema 漂移。
**修復方式**：`src/services/app_analytics.py` 改查詢正式欄位 `score AS match_score`，維持 Mobile API 既有輸出格式；新增 SQL 防回歸斷言。`src/api/app_analytics.py` 補上只寫入伺服器端的分析模組例外日誌，App 仍只收到安全通用訊息。
**驗證方式**：Python compileall 與 `git diff --check` 通過，並以靜態斷言確認 SQL 使用 `score AS match_score`。環境缺少 pytest／lunarcalendar，Service／API 自動測試未執行；仍待部署後驗證求職分布、推薦清單與應徵時間軸。

## 2026-08-19 分析圖表缺軸名與目標摘要順序錯誤
**現象**：實機圖表已有 X／Y 軸刻度，但未標示「日期」、「台幣金額(元)」或「熱量(大卡)」等軸名；目標摘要也放在日期篩選之後。
**排查過程**：`Charts.tsx` 只繪製刻度數字，元件介面沒有軸名參數；分析頁的 `DateRangeFilter` 在模組內容之前繪製，而目標摘要放在模組內容中。
**根因**：第一批只實作了刻度與去重，漏了軸名；目標摘要沒有提升至頁面層級。
**修復方式**：`Charts.tsx` 新增 X／Y 軸名參數與繪製；分析頁於頁面層級繪製目標摘要，再顯示頁籤與日期篩選。
**驗證方式**：Mobile TypeScript typecheck、Service／API 62 項測試與聚焦 `ruff` 通過；尚待 Robin 實機驗證。
**未驗證範圍**：iOS／Android 實機窄螢幕的軸名排版。

## 2026-08-19 分析頁首次載入先顯示不完整畫面
**現象**：進入體態分析或記帳分析時，先只出現日期區間與轉圈，資料回來後才補上目標摘要、頁籤及圖表，造成版面跳動；共用頁面的其他分析模組也有相同風險。
**排查過程**：檢查 `mobile/app/analytics/[module].tsx`，確認 `loading` 初始為 `false`，日期篩選器又不依賴 `payload`，因此第一次 Effect 發出 API 請求前會先渲染半成品畫面。
**根因**：首次載入狀態與後續重新整理共用同一個布林值，且日期篩選器沒有等待第一份資料契約。
**修復方式**：首次狀態改為 loading；尚無 payload 時只顯示完整載入畫面，資料完成後一次呈現頁面。後續切換日期則保留既有內容，避免再次清空整頁。此修正一次涵蓋 todos、body、finance、mood、jobs、exams、skills 七個共用分析頁。
**驗證方式**：Mobile TypeScript typecheck、Expo Web export、全專案 1806 項 pytest 與 Ruff 均通過；實機驗收待完成。
**未驗證範圍**：正式 Vercel／iOS PWA 的首次冷啟動與慢速網路體感。
