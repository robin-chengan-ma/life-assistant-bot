"""固定功能名稱／別名入口：只詢問是否開啟選單，不執行資料異動。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeatureEntry:
    key: str
    label: str
    callback_data: str
    aliases: frozenset[str]
    owner_only: bool = False


_ENTRIES = (
    FeatureEntry("daily_log", "日常紀錄", "menu:daily_log", frozenset({"日常紀錄", "我要記錄"})),
    FeatureEntry("mood", "心情", "daily_log:mood", frozenset({"心情", "心情紀錄", "我要記心情"})),
    FeatureEntry("exercise", "運動", "daily_log:exercise", frozenset({"運動", "運動紀錄", "我要記運動"})),
    FeatureEntry("diet", "飲食", "daily_log:diet", frozenset({"飲食", "飲食紀錄", "我要記飲食"})),
    FeatureEntry("body", "體態", "daily_log:body", frozenset({"體態", "體態紀錄", "我要記體重"})),
    FeatureEntry("finance", "記帳", "daily_log:finance", frozenset({"記帳", "我要記帳", "新增記帳"})),
    FeatureEntry("query", "資料查詢", "menu:query", frozenset({"資料查詢", "查詢資料"})),
    FeatureEntry("todo", "待辦事項", "menu:todo", frozenset({"待辦", "待辦事項", "新增待辦", "我要新增待辦"})),
    FeatureEntry("important_days", "重要日子", "menu:important_days", frozenset({"重要日子", "新增重要日子"})),
    FeatureEntry("collections", "收藏與旅遊", "menu:collections", frozenset({"收藏", "收藏與旅遊", "旅遊行程"})),
    FeatureEntry("achievements", "成果展示", "menu:achievements", frozenset({"成果", "成果展示"})),
    FeatureEntry("goal_tracking", "目標追蹤", "menu:goal_tracking", frozenset({"目標", "目標追蹤"})),
    FeatureEntry("schedule", "功能開關與排程設定", "menu:schedule", frozenset({"排程設定", "功能開關", "功能開關與排程設定"})),
    FeatureEntry("permission", "權限管理", "menu:permission", frozenset({"權限管理"}), True),
    FeatureEntry("tech_intel", "Youtube 技術分享設定", "menu:tech_intel", frozenset({"youtube設定", "youtube技術分享設定", "技術分享設定"}), True),
    FeatureEntry("job_search", "求職設定", "menu:job_search", frozenset({"求職", "求職設定"}), True),
    FeatureEntry("certificate", "考試設定", "menu:certificate", frozenset({"考試設定", "證照設定"}), True),
    FeatureEntry("recovered", "發送康復通知", "menu:recovered", frozenset({"康復通知", "發送康復通知"}), True),
)


def detect(text: str, *, is_owner: bool) -> FeatureEntry | None:
    """只接受完整的固定名稱或別名，不作模糊推測。"""
    normalized = "".join(text.strip().lower().split())
    for entry in _ENTRIES:
        if entry.owner_only and not is_owner:
            continue
        if normalized in {"".join(alias.lower().split()) for alias in entry.aliases}:
            return entry
    return None


def confirmation(entry: FeatureEntry) -> tuple[str, dict]:
    return (
        f"要進入「{entry.label}」功能嗎？",
        {
            "inline_keyboard": [
                [{"text": "✅ 進入功能", "callback_data": f"feature_entry:open:{entry.key}"}],
                [{"text": "❌ 取消", "callback_data": "feature_entry:cancel"}],
            ]
        },
    )


def by_key(key: str, *, is_owner: bool) -> FeatureEntry | None:
    return next((entry for entry in _ENTRIES if entry.key == key and (is_owner or not entry.owner_only)), None)
