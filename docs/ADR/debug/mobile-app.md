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
