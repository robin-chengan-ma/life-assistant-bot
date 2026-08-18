# YouTube 技術情報模組 討論紀錄

## 2026-07-30 [標籤：AI] YouTube 技術情報採「三層輕量規則式篩選」，不用 ML/向量推薦（原記錄於 robinson SPEC.md ADR-9，已 superseded）

**狀態**：superseded by 2026-08-08 條目（Step 3.4 開工前 Robin 釐清原始需求——他要的是「LLM 讀標題/說明欄判斷是否符合主題」而非本條目討論並否決的「下載影片＋Gemini 摘要」，兩者成本量級差異很大，前者其實可以做）

**背景**：需要從 YouTube 上找出「最新技術趨勢」與「經典高技術含量影片」中最優質的內容，但完整下載/轉錄影音分析內容成本過高，需要一個幾乎零邊際成本的篩選方式。

**決策**：採用「API 相關度初篩 + 彈性品質評分（Rule-based Weight）+ 歷史去重」三層輕量篩選架構，只用 API 回傳的中繼資料做排序，不下載、不轉錄、不做語意向量比對。

**替代方案**：下載影片並用 Gemini 做內容摘要/語意分析後排序（已否決，成本高且大量消耗免費額度）；用 Embedding 做語意向量相似度推薦（已否決，對「每週 3 支影片」規模是過度設計）。

**理由**：YouTube Data API 的 `search.list` 呼叫本身已經是 Google 的相關度演算法結果；Rule-based Weight 不需要訓練或維護模型，符合全部免費方案的成本限制。

## 2026-08-08 [標籤：AI] ADR-21：YouTube 技術情報改採「LLM 語意判讀 + 多維度指標 + 多主題輪替」，取代原「純 Rule-based 規則式篩選」（supersede 上方條目）

**狀態**：accepted

**背景**：Step 3.4 開工前跟 Robin 確認 FR-57～FR-59 細節，發現書面規格跟 Robin 原始想法有落差——原本定案「Rule-based Weight」，但 Robin 澄清他要的其實是「LLM 讀候選影片的標題和說明欄，判斷是否符合我想看的主題」，並非上方條目討論並否決的「下載/轉錄影片內容」，兩者成本量級完全不同——前者只是把 API 已經回傳的文字 metadata 餵給 LLM 做一次分類判斷，跟專案其他模組用 LLM 的方式同量級，並不昂貴。Robin 也提出希望額外參考觀看次數/讚數/留言數等數據，以及支援多組主題。

**決策**：①LLM 完全取代 Rule-based Weight——把候選影片的標題、說明欄、頻道名稱、發布時間、觀看次數、讚數、留言數一次交給 LLM 判斷是否符合主題並給出排序 ②只讀文字與統計數字，不下載/轉錄影片本身，維持零邊際成本的精神 ③支援多組主題，每組各自蒐集候選 ④多主題分配採「保底 + 輪替」——只有 1 組主題時 3 支都出自該組；2 組主題時各保底 1 支、剩餘 1 個名額給分數最高者；3 組以上主題時優先選「距離上次被推播最久」的 3 組各推 1 支 ⑤不刻意排除 Shorts 短影音，時長不設限，品質高低完全交給 LLM 判讀決定。

**理由**：Robin 要的判讀方式本來就沒有踩到原本否決方案的成本紅線，屬於書面規格記錄跟原始需求有落差需要修正；「保底 + 輪替」比「永遠只推固定幾個主題」更符合「技術情報訂閱」的初衷，避免冷門但 Robin 有興趣的主題永遠被熱門主題排擠掉；「品質」與「時長」是兩件事，用時長一刀切反而可能誤刪真正高品質的短影片。

**替代方案**：LLM 疊加在 Rule-based 之上（已否決，判斷邏輯更單純、不用維護兩套排序邏輯）；固定只推「候選分數最高的 3 組」，不考慮輪替（已否決，Robin 選擇能兼顧公平曝光的輪替設計）；沿用原本的時長門檻（已否決，不符合 Robin 實際想要的「品質優先」判斷標準）。

**後果**：新增主題設定資料表 `youtube_topics`（`user_id`／`topic`／`last_recommended_on`）；FR-57 新增一次 `videos.list` 呼叫查統計數字，Pipeline 從單一 API 呼叫變成兩階段；原始三層規則式篩選設計正式作廢，不再需要維護 Rule-based Weight 的評分程式碼。

## 2026-08-18 [標籤：使用者] `tech_intel` 主選單按鈕接上 YouTube 主題設定子選單，主題數量加上限並改按鈕式二次確認刪除

**狀態**：accepted

**背景**：主選單「💡 技術分享」按鈕原本仍在 `_NOT_YET_IMPLEMENTED_KEYS`（回覆「功能開發中」），主題新增/移除/查詢實際上只能靠三個獨立文字觸發詞（`/my_youtube_topics`／`/add_youtube_topic`／`/remove_youtube_topic`）操作，跟 Phase 6 第二批已經全面選單化的其他模組（`collections.py`／`achievements.py`）體驗不一致，也沒有主題數量上限保護。

**決策**：①主選單按鈕文字改為「💡 Youtube 技術分享設定」，`tech_intel` 從 `_NOT_YET_IMPLEMENTED_KEYS` 移除 ②新增 `src/bot/commands.py` 內的 `youtube_settings:*` 子選單，設計比照 `collections.py`／`achievements.py` 的單層選單＋狀態機模式：總覽列出目前主題＋「➕ 新增主題」／「➖ 移除主題」按鈕 ③主題數量上限 `youtube.MAX_TOPICS`＝5，達上限時「➕ 新增主題」按鈕隱藏，`youtube.add_topic()` 內同步擋下（雙重保護），回覆「已達上限 5 個主題」④移除流程改成「選主題按鈕→確定要移除「{topic}」嗎？✅ 確認移除／❌ 取消」二次確認畫面，才會真正呼叫 `youtube.remove_topic()`，不再是舊版「打編號直接刪除」⑤舊文字觸發詞（`/my_youtube_topics`、`/add_youtube_topic`、`/remove_youtube_topic` 及對應中文別名）與 `router.py`／`commands.py` 內對應的舊處理函式／狀態全數移除，不提供相容期。

**理由**：跟其餘 Phase 6 模組維持一致的選單 UX（單層選單＋按鈕式二次確認刪除），降低使用者記憶文字指令的負擔；5 組上限避免主題無限膨脹拖慢 FR-58c 每週分配演算法與影響推播精準度；刪除改二次確認降低誤觸風險（跟 `collections.py` 收藏刪除的保守設計一致，比 `achievements.py` 的直接刪除更保守，因為主題設定屬於長期訂閱設定而非單筆紀錄）。

**替代方案**：沿用舊版文字觸發詞不做選單化（已否決，不符合 Phase 6 主選單全面選單化的既定方向）；移除比照 `achievements.py` 直接刪除不加二次確認（已否決，主題設定改動頻率低、誤刪代價相對「重新輸入一次主題名稱」不算太高，但比照收藏清單刪除的保守做法仍加上二次確認）。

**後果**：`src/bot/youtube.py` 新增 `MAX_TOPICS` 常數，`add_topic()` 回傳值新增 `limit_reached` 欄位；`src/bot/commands.py` 新增 `start_youtube_settings_menu()`／`start_youtube_topic_add()`／`handle_youtube_topic_add_step()`（改寫）／`start_youtube_topic_remove_menu()`／`start_youtube_topic_remove_confirm()`／`handle_youtube_topic_remove_confirm_text()`／`handle_youtube_topic_remove_confirmed()`；`src/bot/router.py` 新增 `menu:tech_intel`／`youtube_settings:*` 分派與 `youtube_topic_add`／`youtube_topic_remove_confirm` 兩個 flow 分支，移除舊版三個觸發詞常數與 `pending_youtube_topic_add`／`pending_youtube_topic_remove` flow 分支；程式碼已完成，**測試尚未執行**，未 commit／push／部署，見 PROGRESS.md 2026-08-18 條目。
