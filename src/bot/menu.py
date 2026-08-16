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
    "daily_log", "query", "todo", "collections",
    "achievements", "schedule", "tech_intel", "job_search", "certificate", "recovered",
}

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
