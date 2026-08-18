"""Telegram「功能開關與排程設定」選單。"""

from src.bot import toggles
from submodules.cloudsql.client import CloudSQLClient

OWNER_FEATURES = (
    ("tech_intel", "技術分享"),
    ("job_search", "求職設定"),
    ("certificate", "考試設定"),
)

SYSTEM_JOBS = (
    ("Neon 容量監控", "每 10 分鐘"),
    ("待辦逾期標記", "每 10 分鐘"),
    ("目標達成與日期提醒檢查", "每 10 分鐘"),
    ("目標摘要生成", "每日 01:00"),
    ("技術摘要推播", "每日 08:00"),
    ("考試出題推播", "每日 08:00"),
    ("求職分析", "每週一 08:00"),
    ("Youtube 推薦", "每週四 08:00"),
    ("月底記帳月報", "每月最後一天 21:00"),
    ("TOEIC 題庫 Pipeline", "每週日 22:00"),
    ("技術摘要收集", "每日 23:00"),
)

NOTIFICATION_SCHEDULES = (
    ("todo", "待辦提醒", "每日 08:00 摘要＋單筆提前提醒", False),
    ("important_day", "重要日子（含目標與旅遊日期）", "依事件提前天數，預設 08:00", False),
    ("budget_alert", "預算 50%／80% 警示", "每 10 分鐘檢查門檻", False),
    ("monthly_report", "月底記帳月報", "每月最後一天 21:00", False),
    ("tech_digest", "技術摘要推播", "每日 08:00", True),
    ("youtube", "Youtube 推薦", "每週四 08:00", True),
    ("job_search", "求職分析通知", "每週一 08:00", True),
    ("exam_quiz", "考試出題通知", "每日 08:00", True),
)


def start_menu(*, is_owner: bool) -> tuple[str, dict]:
    buttons = []
    if is_owner:
        buttons.append([{"text": "🔘 功能開關", "callback_data": "schedule:features"}])
    buttons.append([{"text": "⏰ 我的排程", "callback_data": "schedule:notifications"}])
    if is_owner:
        buttons.append([{"text": "🛠 系統工作", "callback_data": "schedule:system"}])
    buttons.append([{"text": "🔙 返回主選單", "callback_data": "menu:main"}])
    return "⏰ 功能開關與排程設定，請選擇要查看的項目：", {"inline_keyboard": buttons}


def feature_menu(db: CloudSQLClient, user_id: int) -> tuple[str, dict]:
    toggles.ensure_default_toggles(db, user_id)
    lines = ["🔘 功能開關", "關閉功能會停止收集、產生內容與推播：", ""]
    buttons = []
    for feature_key, label in OWNER_FEATURES:
        enabled = toggles.is_feature_enabled(db, user_id, feature_key)
        status = "✅ 開啟" if enabled else "⬜ 關閉"
        lines.append(f"{label}：{status}")
        buttons.append([{"text": f"{status}｜{label}", "callback_data": f"schedule:feature:{feature_key}"}])
    buttons.append([{"text": "🔙 返回", "callback_data": "menu:schedule"}])
    return "\n".join(lines), {"inline_keyboard": buttons}


def toggle_feature(db: CloudSQLClient, user_id: int, feature_key: str) -> tuple[str, dict]:
    valid_keys = {key for key, _label in OWNER_FEATURES}
    if feature_key not in valid_keys:
        return feature_menu(db, user_id)
    toggles.ensure_default_toggles(db, user_id)
    enabled = toggles.is_feature_enabled(db, user_id, feature_key)
    db.update(
        "feature_toggles",
        {"is_enabled": not enabled},
        where="user_id = %s AND feature_key = %s",
        params=(user_id, feature_key),
    )
    return feature_menu(db, user_id)


def system_jobs_menu() -> tuple[str, dict]:
    lines = ["🛠 系統工作（僅供管理者查看，固定頻率不可修改）", ""]
    lines.extend(f"• {name}：{schedule}" for name, schedule in SYSTEM_JOBS)
    return "\n".join(lines), {
        "inline_keyboard": [[{"text": "🔙 返回", "callback_data": "menu:schedule"}]]
    }


def notification_menu(db: CloudSQLClient, user_id: int, *, is_owner: bool) -> tuple[str, dict]:
    lines = ["⏰ 我的排程", "關閉只停止通知，來源功能與背景工作仍照常執行：", ""]
    buttons = []
    for key, label, schedule, owner_only in NOTIFICATION_SCHEDULES:
        if owner_only and not is_owner:
            continue
        enabled = is_notification_enabled(db, user_id, key)
        status = "✅ 接收" if enabled else "⬜ 關閉"
        lines.append(f"{label}：{status}（{schedule}）")
        buttons.append([{
            "text": f"{status}｜{label}",
            "callback_data": f"schedule:notification:{key}",
        }])
    buttons.append([{"text": "🔙 返回", "callback_data": "menu:schedule"}])
    return "\n".join(lines), {"inline_keyboard": buttons}


def is_notification_enabled(db: CloudSQLClient, user_id: int, notification_key: str) -> bool:
    row = db.select(
        "notification_preferences",
        where="user_id = %s AND notification_key = %s",
        params=(user_id, notification_key),
        fetch_one=True,
    )
    return True if row is None else bool(row["is_enabled"])


def toggle_notification(
    db: CloudSQLClient, user_id: int, notification_key: str, *, is_owner: bool
) -> tuple[str, dict]:
    valid = {key for key, _label, _schedule, owner_only in NOTIFICATION_SCHEDULES if is_owner or not owner_only}
    if notification_key not in valid:
        return notification_menu(db, user_id, is_owner=is_owner)
    row = db.select(
        "notification_preferences",
        where="user_id = %s AND notification_key = %s",
        params=(user_id, notification_key),
        fetch_one=True,
    )
    if row is None:
        db.insert("notification_preferences", {
            "user_id": user_id,
            "notification_key": notification_key,
            "is_enabled": False,
        })
    else:
        db.update(
            "notification_preferences",
            {"is_enabled": not row["is_enabled"]},
            where="user_id = %s AND notification_key = %s",
            params=(user_id, notification_key),
        )
    return notification_menu(db, user_id, is_owner=is_owner)


def feature_disabled_reply(feature_key: str) -> tuple[str, dict]:
    label = dict(OWNER_FEATURES)[feature_key]
    return (
        f"若要使用{label}功能，請至功能開關與排程設定打開！",
        {"inline_keyboard": [[{"text": "⏰ 前往設定", "callback_data": "menu:schedule"}]]},
    )
