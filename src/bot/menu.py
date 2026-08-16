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
"""

# key、label 依 FR-6e 定案順序；owner_only 決定這個項目是否只有 Owner 看得到。
MAIN_MENU_ITEMS = [
    {"key": "daily_log", "label": "📝 日常紀錄", "owner_only": False},
    {"key": "query", "label": "🔍 資料查詢", "owner_only": False},
    {"key": "todo", "label": "✅ 待辦事項", "owner_only": False},
    {"key": "important_days", "label": "📅 重要日子", "owner_only": False},
    {"key": "collections", "label": "🧭 收藏與旅遊", "owner_only": False},
    {"key": "achievements", "label": "🏆 成果展示", "owner_only": False},
    {"key": "schedule", "label": "⏰ 排程設定", "owner_only": False},
    {"key": "rule", "label": "📋 使用規則", "owner_only": False},
    {"key": "permission", "label": "🔑 權限管理", "owner_only": True},
    {"key": "tech_intel", "label": "💡 技術分享", "owner_only": True},
    {"key": "job_search", "label": "💼 求職分析", "owner_only": True},
    {"key": "certificate", "label": "📖 考試成績", "owner_only": True},
    {"key": "recovered", "label": "📢 發送康復通知", "owner_only": True},
]

# 尚未接上真正邏輯的項目，按下後只回覆固定的「開發中」訊息；2b 起逐批把 key 移出這裡。
_NOT_YET_IMPLEMENTED_KEYS = {
    "query", "todo",
    "schedule", "tech_intel", "job_search", "certificate", "recovered",
}

# 2026-08-16（Phase 6 第二批 2c）：日常紀錄第二層子選單，`callback_data` 固定格式
# `"daily_log:<key>"`；「日常紀錄」本身不分 Owner／一般使用者，五個子項目共用同一份定義。
DAILY_LOG_MENU_ITEMS = [
    {"key": "mood", "label": "😊 心情"},
    {"key": "exercise", "label": "🏃 運動"},
    {"key": "diet", "label": "🍚 飲食"},
    {"key": "body", "label": "⚖️ 體態"},
    {"key": "finance", "label": "💰 記帳"},
]

_DAILY_LOG_NOT_YET_IMPLEMENTED_KEYS = {"diet", "body", "finance"}

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
