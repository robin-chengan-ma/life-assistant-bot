"""角色選單矩陣（對應 docs/specs/SPEC.md FR-6e）。

資料驅動的選單定義，取代 router.py 過去「權限寫在 if 區塊裡」的作法：
一個項目要不要顯示，改成查 `owner_only` 欄位，而不是看它被放在程式碼的哪個分支裡。

2026-08-15（Phase 6 第二批 2a，見 docs/ADR/discuss/robinson.md）：這批只做主選單骨架，
`daily_log`／`query`／`todo`／`important_days`／`collections`／`achievements`／`schedule`
這七項先回覆「功能開發中」暫時訊息，實際邏輯留給 2b 之後遷移對應模組時才接上。
`rule`（FR-5）與 `permission`（FR-4）這批就接上真正的邏輯。

2026-08-15（Phase 6 第二批 2b，見 docs/ADR/discuss/robinson.md）：`important_days`
（重要日子）接上 `src/bot/important_days.py` 的真正邏輯，從 `_NOT_YET_IMPLEMENTED_KEYS`
移除；其餘六項維持「功能開發中」，依已定案順序留給後續子批次。

2026-08-16（Phase 6 第二批 2c，見 docs/ADR/discuss/robinson.md）：`daily_log`（日常紀錄）
接上真正邏輯，改回覆第二層子選單（見 `DAILY_LOG_MENU_ITEMS`）；子選單裡的 `mood`／
`exercise` 這批接上 `commands.py` 既有心情／運動流程（全面改選單觸發、移除舊文字觸發詞，
並補上摘要→二次確認），`diet`／`body`／`finance` 三項維持「功能開發中」。

2026-08-16（Phase 6 第二批 2d，見 docs/ADR/discuss/robinson.md）：`collections`
（收藏與旅遊）接上 `src/bot/collections.py`／`src/bot/trips.py` 的真正邏輯，從
`_NOT_YET_IMPLEMENTED_KEYS` 移除；子選單（收藏清單／新增收藏／旅遊行程）由
`collections.start_collections_menu()` 直接組出 Inline Keyboard，比照 `important_days`
的單層選單做法，不另外定義 `*_MENU_ITEMS` 常數。

2026-08-16（Phase 6 第二批 2e，見 docs/ADR/discuss/robinson.md）：`achievements`
（成果展示）接上 `src/bot/achievements.py` 的真正邏輯，從 `_NOT_YET_IMPLEMENTED_KEYS`
移除；子選單（查看成果／新增成果）由 `achievements.start_achievements_menu()` 直接組出
Inline Keyboard，比照 `collections` 的單層選單做法。候選機制維持被動（開啟清單才重新
掃描，不在目標達成當下主動推播），刪除採直接刪除、無二次確認、無復原（跟 Mobile App
既有的 5 秒復原不同，是本批刻意決策）。

2026-08-16（Phase 6 第二批 2f，見 docs/ADR/discuss/robinson.md）：`todo`（待辦事項）
接上 `src/bot/commands.py` 既有的待辦事項邏輯，從 `_NOT_YET_IMPLEMENTED_KEYS` 移除；
子選單（查看清單／新增）由 `commands.start_todo_menu()` 直接組出 Inline Keyboard，
比照 `important_days` 的單層選單做法。新增流程補上摘要→二次確認關卡，查詢清單改為
按鈕式標記完成/取消；自然語言偵測入口（chat.py，FR-31、FR-56e）維持不變，跟選單
「➕ 新增」按鈕共用同一套「時間→提醒→行事曆同步→確認」狀態機。

2026-08-16（Phase 6 第二批 2g，見 docs/ADR/discuss/robinson.md）：`diet`（飲食）接上
`src/bot/commands.py` 改寫過的飲食/飲水邏輯，從 `_DAILY_LOG_NOT_YET_IMPLEMENTED_KEYS`
移除；`body`／`finance` 維持「功能開發中」。飲食／飲水比照 Mobile App 的 single-daily
設計（同一天各自只能一筆），新增流程先問飲水再問食物（各自可跳過，已有紀錄的項目
直接跳過提問），食物內容支援文字／照片兩種輸入方式，並可選擇沿用 AI 估算或自己填寫
三大營養素與熱量；同批也把全站語音功能改成「轉錄成功先貼出文字給使用者確認，確認後
才接回原本流程」（見 `router.py` 的 `pending_voice_confirm`／`voice_confirm:accept`），
影響範圍不限於飲食，也涵蓋既有的心情／運動／待辦等語音入口。

2026-08-17（Phase 6 第二批 2h，見 docs/ADR/discuss/robinson.md）：`body`（體態）接上
`src/bot/commands.py` 改寫過的身高/腰圍/體重/目標邏輯，從 `_DAILY_LOG_NOT_YET_IMPLEMENTED_KEYS`
移除；`finance` 維持「功能開發中」。子選單（設定身高／設定腰圍／記錄體重／補記體重／我的體態
紀錄／🎯 目標／🔙 返回）由 `commands.start_body_menu()` 直接組出 Inline Keyboard，比照 `diet`
的單層子選單做法；運動／飲食子選單也各自補上一顆「🎯 目標」按鈕，統一導到體態模組共用的
`body:goal:*` 目標子流程。

2026-08-17（批次3，見 docs/ADR/discuss/robinson.md「批次3 開工前 SDD 計畫確認」）：
`goal_tracking`（🎯 目標追蹤）新增為主選單項目，直接接上真正邏輯（不進 `_NOT_YET_IMPLEMENTED_
KEYS`）；點擊後列出已支援目標功能的模組（見 `GOAL_TRACKING_MODULES`），選模組→選目標→顯示
`goal_summaries` 最新一份快取摘要，全程唯讀，由 `src/bot/commands.py` 的 `start_goal_tracking_*`
系列函式與 `src/bot/router.py` 的 `goal_tracking:*` 分派處理。

2026-08-18（批次4，見 docs/ADR/discuss/robinson.md「資料查詢開工前 SDD 計畫確認」，FR-9c／
FR-9d）：`query`（🔍 資料查詢）接上真正邏輯，從 `_NOT_YET_IMPLEMENTED_KEYS` 移除。可勾選範圍
只涵蓋 7 個本來就有日期區間概念的模組（見 `QUERY_MODULES`），直接複用 Mobile App 既有的
`AppAnalyticsService` 各模組唯讀查詢方法，不重寫查詢邏輯；重要日子／收藏與旅遊／成果展示／
目標追蹤維持只能從各自主選單查看，不併入資料查詢。子選單（選最終日期→模組複選→開始查詢）
由 `src/bot/query.py` 的 `start_query_menu()` 等函式直接組出 Inline Keyboard，比照
`important_days` 的做法；`router.py` 的 `query:*` 分派處理。

2026-08-18（批次5，見 docs/ADR/discuss/robinson.md「批次5 開工前 SDD 計畫確認」）：`finance`
（記帳）接上 `src/bot/commands.py` 改寫過的記帳邏輯，從 `_DAILY_LOG_NOT_YET_IMPLEMENTED_KEYS`
移除，日常紀錄五個子項目至此全數接上真正邏輯。子選單由 `commands.start_finance_menu()` 直接
組出 Inline Keyboard，比照 `body` 的單層子選單做法；新增／補記記帳流程補上摘要→二次確認關卡
（`finance:confirm_save`），我的記帳紀錄改為按鈕式編輯／刪除（`finance:edit:<id>`／
`finance:delete:<id>`），設定預算的月份覆蓋確認從自由文字 LLM 分類改成 ✅／❌ 按鈕
（`finance:budget_confirm_save`／`finance:budget_override_confirm_save`），舊有文字觸發詞
（「我要記帳」「設定記帳預算」等）全數移除，只留 `router.py` 既有的 `finance:goal:*` 目標子
流程不動。
"""

# key、label 依 FR-6e 定案順序；owner_only 決定這個項目是否只有 Owner 看得到。
MAIN_MENU_ITEMS = [
    {"key": "daily_log", "label": "📝 日常紀錄", "owner_only": False},
    {"key": "query", "label": "🔍 資料查詢", "owner_only": False},
    {"key": "todo", "label": "✅ 待辦事項", "owner_only": False},
    {"key": "important_days", "label": "📅 重要日子", "owner_only": False},
    {"key": "collections", "label": "🧭 收藏與旅遊", "owner_only": False},
    {"key": "achievements", "label": "🏆 成果展示", "owner_only": False},
    {"key": "goal_tracking", "label": "🎯 目標追蹤", "owner_only": False},
    {"key": "schedule", "label": "⏰ 排程設定", "owner_only": False},
    {"key": "rule", "label": "📋 使用規則", "owner_only": False},
    {"key": "permission", "label": "🔑 權限管理", "owner_only": True},
    {"key": "tech_intel", "label": "💡 Youtube 技術分享設定", "owner_only": True},
    {"key": "job_search", "label": "💼 求職設定", "owner_only": True},
    {"key": "certificate", "label": "📖 考試設定", "owner_only": True},
    {"key": "recovered", "label": "📢 發送康復通知", "owner_only": True},
]

# 尚未接上真正邏輯的項目，按下後只回覆固定的「開發中」訊息；2b 起逐批把 key 移出這裡。
_NOT_YET_IMPLEMENTED_KEYS = {
    "schedule", "recovered",
}

# 2026-08-18（批次4，FR-9c）：資料查詢可勾選的 7 個模組，`analytics_method` 對應
# `AppAnalyticsService` 上同名的唯讀查詢方法（`src/services/app_analytics.py`），直接複用、
# 不重寫查詢邏輯；`owner_only` 沿用該服務 `_MODULES` 裡的授權設定。順序依一般使用者/Owner
# 分組，跟 `MAIN_MENU_ITEMS` 的排序精神一致。
QUERY_MODULES = [
    {"key": "todos", "label": "待辦事項", "analytics_method": "todos", "owner_only": False},
    {"key": "body", "label": "體態分析（飲食／運動／體重）", "analytics_method": "body", "owner_only": False},
    {"key": "finance", "label": "記帳", "analytics_method": "finance", "owner_only": False},
    {"key": "mood", "label": "心情趨勢", "analytics_method": "mood", "owner_only": False},
    {"key": "skills", "label": "技術分享", "analytics_method": "skills", "owner_only": True},
    {"key": "jobs", "label": "求職分析", "analytics_method": "jobs", "owner_only": True},
    {"key": "exams", "label": "考試成績", "analytics_method": "exams", "owner_only": True},
]


def visible_query_modules(is_owner: bool) -> list[dict]:
    return [item for item in QUERY_MODULES if is_owner or not item["owner_only"]]


def is_valid_query_module_key(key: str, *, is_owner: bool) -> bool:
    return any(item["key"] == key for item in visible_query_modules(is_owner))

# 2026-08-16（Phase 6 第二批 2c）：日常紀錄第二層子選單，`callback_data` 固定格式
# `"daily_log:<key>"`；「日常紀錄」本身不分 Owner／一般使用者，五個子項目共用同一份定義。
DAILY_LOG_MENU_ITEMS = [
    {"key": "mood", "label": "😊 心情"},
    {"key": "exercise", "label": "🏃 運動"},
    {"key": "diet", "label": "🍚 飲食"},
    {"key": "body", "label": "⚖️ 體態"},
    {"key": "finance", "label": "💰 記帳"},
]

# 2026-08-16（Phase 6 第二批 2g）：`diet`（飲食）接上真正邏輯，移出開發中名單。
# 2026-08-17（Phase 6 第二批 2h）：`body`（體態）接上真正邏輯，移出開發中名單。
# 2026-08-18（Youtube 技術分享設定選單化，見 docs/ADR/discuss/robinson.md 與
# docs/ADR/discuss/youtube-intel.md 對應日期條目）：`tech_intel` 按鈕文字改為「💡 Youtube 技術分享
# 設定」，從 `_NOT_YET_IMPLEMENTED_KEYS` 移除，接上 `src/bot/commands.py` 新增的 YouTube 主題設定
# 子選單（`youtube_settings:*`，見 `router.py`）；主題新增/移除全面改選單觸發，`/my_youtube_topics`
# `/add_youtube_topic` `/remove_youtube_topic` 等舊文字觸發詞與對應處理函式已移除。
# 2026-08-18（批次5）：`finance`（記帳）接上真正邏輯，移出開發中名單；日常紀錄五個子項目
# 至此全數接上真正邏輯，這個集合暫時為空，保留供未來新增子項目沿用同一套機制。
_DAILY_LOG_NOT_YET_IMPLEMENTED_KEYS: set[str] = set()

DAILY_LOG_MENU_TEXT = "日常紀錄，請選擇要記錄的項目："


def build_daily_log_menu_keyboard() -> dict:
    buttons = [
        [{"text": item["label"], "callback_data": f"daily_log:{item['key']}"}]
        for item in DAILY_LOG_MENU_ITEMS
    ]
    buttons.append([{"text": "🔙 返回主選單", "callback_data": "menu:main"}])
    return {"inline_keyboard": buttons}


def is_valid_daily_log_key(key: str) -> bool:
    return any(item["key"] == key for item in DAILY_LOG_MENU_ITEMS)


def is_daily_log_not_yet_implemented(key: str) -> bool:
    return key in _DAILY_LOG_NOT_YET_IMPLEMENTED_KEYS

# 2026-08-17（批次3，FR-45a）：🎯 目標追蹤主選單，列出已支援目標功能的模組。`goal_source`／
# `goal_type` 決定 `commands.start_goal_tracking_module()` 要去哪張表查目標清單；體態/運動/飲食
# 共用 `body_goals`（用 `goal_type` 篩選），記帳/收藏清單用批次3新增的 `module_goals`，考試沿用
# 既有 `certificate_goals`（不用 `goal_type` 篩選，`exam_type` 本身就是目標的分類）。
GOAL_TRACKING_MODULES = [
    {"key": "diet", "label": "🍚 飲食", "goal_source": "body_goals", "goal_type": "diet"},
    {"key": "body", "label": "⚖️ 體態", "goal_source": "body_goals", "goal_type": "weight"},
    {"key": "exercise", "label": "🏃 運動", "goal_source": "body_goals", "goal_type": "exercise"},
    {"key": "finance", "label": "💰 記帳", "goal_source": "module_goals", "goal_type": "finance"},
    {"key": "collections", "label": "🧭 收藏清單", "goal_source": "module_goals", "goal_type": "collections"},
    {"key": "certificate", "label": "📖 考試", "goal_source": "certificate_goals", "goal_type": None},
]

GOAL_TRACKING_MENU_TEXT = "🎯 目標追蹤，請選擇要查看的模組："


def build_goal_tracking_menu_keyboard() -> dict:
    buttons = [
        [{"text": item["label"], "callback_data": f"goal_tracking:module:{item['key']}"}]
        for item in GOAL_TRACKING_MODULES
    ]
    buttons.append([{"text": "🔙 返回主頁面", "callback_data": "menu:main"}])
    return {"inline_keyboard": buttons}


def goal_tracking_module_by_key(key: str) -> dict | None:
    return next((item for item in GOAL_TRACKING_MODULES if item["key"] == key), None)


MAIN_MENU_TEXT = "請選擇功能："
_NOT_YET_IMPLEMENTED_REPLY = "這個功能還在開發中，敬請期待！可以先按下面按鈕回主選單。"


def build_main_menu_keyboard(is_owner: bool) -> dict:
    """依 FR-6e 組出主選單的 Inline Keyboard；一般使用者看不到 owner_only 項目。

    每個按鈕一列（比照現行 Telegram 選單常見排版，避免同一列擠太多字造成手機端跑版），
    `callback_data` 固定格式 `"menu:<key>"`。
    """
    buttons = [
        [{"text": item["label"], "callback_data": f"menu:{item['key']}"}]
        for item in MAIN_MENU_ITEMS
        if is_owner or not item["owner_only"]
    ]
    return {"inline_keyboard": buttons}


def back_to_main_menu_keyboard() -> dict:
    """只有一顆「返回主選單」按鈕，給尚未完整實作的功能／子選單當結尾用。"""
    return {"inline_keyboard": [[{"text": "🔙 返回主選單", "callback_data": "menu:main"}]]}


def is_valid_menu_key(key: str) -> bool:
    """檢查是不是 MAIN_MENU_ITEMS 裡定義過的合法 key，用於拒絕偽造／過期的 callback_data。"""
    return any(item["key"] == key for item in MAIN_MENU_ITEMS)


def is_owner_only_key(key: str) -> bool:
    """檢查這個 key 是不是 Owner 專屬；找不到 key 時保守回傳 True（不明項目一律當作需要授權）。"""
    for item in MAIN_MENU_ITEMS:
        if item["key"] == key:
            return item["owner_only"]
    return True


def is_not_yet_implemented(key: str) -> bool:
    return key in _NOT_YET_IMPLEMENTED_KEYS


def not_yet_implemented_reply() -> tuple[str, dict]:
    return _NOT_YET_IMPLEMENTED_REPLY, back_to_main_menu_keyboard()


def daily_log_not_yet_implemented_reply() -> tuple[str, dict]:
    """同 `not_yet_implemented_reply()`，但按鈕導回「日常紀錄」子選單而不是主選單。"""
    keyboard = {"inline_keyboard": [[{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}]]}
    return _NOT_YET_IMPLEMENTED_REPLY, keyboard
