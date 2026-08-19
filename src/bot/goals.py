"""批次3新增模組（記帳／收藏清單）的目標子流程（對應 docs/specs/SPEC.md FR-45a）。

`module_goals` 表（0085 migration）給記帳／收藏清單兩個模組共用，用 `module_key` 區分，設計
精神比照 `src/bot/body.py` 的 `body_goals`（體態/運動/飲食共用一張表）。體態/運動/飲食沿用
`body.py`，考試沿用 `certificate_goals.py`，這裡刻意不重工。

達成判斷邏輯（方案A，見 `src/services/goal_parser.py`）：
- 記帳（finance）：`target_value` 是「淨結餘變化金額」，`baseline_value` 固定為 0——判斷時
  直接查「目標建立日期之後」的收入總額減支出總額是否 ≥ `target_value`，不用「目前淨結餘 -
  基準淨結餘」的做法，避免要另外記錄基準當下的絕對淨結餘（一律以 0 為基準、算「這段期間賺了
  多少」，語意更直覺，也不用擔心使用者過去負債或存款的絕對值）。
- 收藏清單（collections）：`target_value` 是「新完成收藏項目數」，`baseline_value` 是設定
  目標當下已經 `visited` 的項目數；判斷時「目前 visited 數 - baseline_value ≥ target_value」。
- 兩者皆為 `target_value IS NULL`（LLM 解析不出結構化數值）時，不做自動判斷，維持純文字目標，
  只能透過「刪除」結束，本批次不新增「手動標記完成」按鈕（範圍聚焦在方案A解析與六模組泛化，
  UI 精緻化留待之後視需要再談，屬於刻意簡化）。
"""
import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from src.services.goal_important_day_sync import sync_module_goal
from submodules.cloudsql.client import CloudSQLClient

_logger = logging.getLogger(__name__)
_TAIWAN_TZ = ZoneInfo("Asia/Taipei")

MODULE_LABELS: dict[str, str] = {"finance": "記帳", "collections": "收藏清單"}


def module_label(module_key: str) -> str:
    return MODULE_LABELS.get(module_key, module_key)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_goal(
    db: CloudSQLClient,
    user_id: int,
    module_key: str,
    target_description: str,
    target_value: float | None,
    target_unit: str | None,
    baseline_value: float | None,
    target_date: date | None,
    sync_to_calendar: bool = False,
) -> int:
    """新增一筆通用模組目標，回傳新建列的 id。目標達成/期限提醒後續由重要日子模組同步顯示，
    比照 `body.create_goal()` 的做法呼叫 `sync_module_goal()`，失敗降級不擋主流程。

    `sync_to_calendar`（2026-08-17 補做，Robin 要求不得漏做）：只在「有期限」的新目標詢問過
    使用者是否要同步至 Google 家庭行事曆後才會是 True；實際建立 Calendar 事件、寫入
    `google_calendar_event_id` 由呼叫端（`commands.handle_module_goal_confirm_save()`）在拿到
    `goal_id` 後另外呼叫 `set_calendar_event_id()`，此函式本身不建立 Calendar 事件（比照
    `body.create_goal()` 的既有分工）。"""
    goal_id = db.insert(
        "module_goals",
        {
            "user_id": user_id,
            "module_key": module_key,
            "target_description": target_description,
            "target_value": target_value,
            "target_unit": target_unit,
            "baseline_value": baseline_value,
            "target_date": target_date,
            "status": "active",
            "achieved_notified": False,
            "deadline_reminder_sent": False,
            "sync_to_calendar": sync_to_calendar,
        },
    )
    if target_date is not None:
        try:
            sync_module_goal(db, goal_id)
        except Exception:
            _logger.exception("模組目標（id=%s）同步至重要日子失敗，目標本身已成功建立", goal_id)
    return goal_id


def update_goal(
    db: CloudSQLClient,
    goal_id: int,
    target_description: str,
    target_value: float | None,
    target_unit: str | None,
    target_date: date | None,
) -> None:
    """「✏️ 編輯」：重新走一次目標值/期限輸入，`baseline_value` 沿用建立當下的值不變動
    （理由同 body.py 的目標編輯決策：介面完全對稱、都重新走一次輸入，但基準值是「當下狀態的
    快照」，編輯不代表要重新量測基準）。編輯不重問 Calendar 同步（比照 body.py：只在新建時
    詢問），`sync_to_calendar`／`google_calendar_event_id` 維持原值不動。"""
    db.update(
        "module_goals",
        {
            "target_description": target_description,
            "target_value": target_value,
            "target_unit": target_unit,
            "target_date": target_date,
            "achieved_notified": False,
            "deadline_reminder_sent": False,
        },
        where="id = %s",
        params=(goal_id,),
    )
    try:
        sync_module_goal(db, goal_id)
    except Exception:
        _logger.exception("模組目標（id=%s）編輯後同步至重要日子失敗，目標本身已成功更新", goal_id)


def set_calendar_event_id(db: CloudSQLClient, goal_id: int, event_id: str) -> None:
    """建立 Google Calendar 事件成功後，把事件 id 寫回目標列（比照 `body.set_calendar_event_id()`）。"""
    db.update("module_goals", {"google_calendar_event_id": event_id}, where="id = %s", params=(goal_id,))


def get_goal(db: CloudSQLClient, goal_id: int) -> dict | None:
    return db.select("module_goals", where="id = %s", params=(goal_id,), fetch_one=True)


def list_active_goals(db: CloudSQLClient, user_id: int, module_key: str) -> list[dict]:
    return db.select(
        "module_goals",
        where="user_id = %s AND module_key = %s AND status = %s",
        params=(user_id, module_key, "active"),
    )


def format_goal_list(goals: list[dict]) -> str:
    if not goals:
        return "目前沒有進行中的目標。"
    lines = ["🎯 進行中的目標", ""]
    for index, item in enumerate(goals, start=1):
        deadline_part = f"（期限 {item['target_date']:%Y/%m/%d}）" if item.get("target_date") else ""
        lines.append(f"{index}. {item['target_description']}{deadline_part}")
    return "\n".join(lines)


def cancel_goal(db: CloudSQLClient, goal_id: int) -> None:
    db.update("module_goals", {"status": "cancelled"}, where="id = %s", params=(goal_id,))
    try:
        sync_module_goal(db, goal_id)
    except Exception:
        _logger.exception("模組目標（id=%s）取消後停用重要日子失敗", goal_id)


def mark_goal_achieved(db: CloudSQLClient, goal_id: int, user_id: int, calendar_client=None) -> bool:
    row = get_goal(db, goal_id)
    if row is None or row["user_id"] != user_id or row.get("status") != "active":
        return False
    affected = db.update(
        "module_goals",
        {"status": "achieved", "achieved_notified": True, "completed_at": datetime.now(timezone.utc)},
        where="id = %s AND user_id = %s AND status = %s",
        params=(goal_id, user_id, "active"),
    )
    if not affected:
        return False
    try:
        sync_module_goal(db, goal_id)
    except Exception:
        _logger.exception("模組目標（id=%s）手動完成後停用重要日子失敗", goal_id)
    if row.get("google_calendar_event_id") and calendar_client is not None:
        try:
            calendar_client.delete_event(event_id=row["google_calendar_event_id"])
        except Exception:
            _logger.exception("模組目標（id=%s）完成後刪除 Google Calendar 事件失敗", goal_id)
    return True


def _mark_goal_achieved(db: CloudSQLClient, goal_id: int) -> None:
    db.update("module_goals", {"status": "achieved", "achieved_notified": True, "completed_at": datetime.now(timezone.utc)}, where="id = %s", params=(goal_id,))
    try:
        sync_module_goal(db, goal_id)
    except Exception:
        _logger.exception("模組目標（id=%s）達成後停用重要日子失敗", goal_id)


# ---------------------------------------------------------------------------
# 達成判斷
# ---------------------------------------------------------------------------


def check_finance_goal_achievement(db: CloudSQLClient, user_id: int) -> str | None:
    """記帳新增交易後呼叫（FR-45 精神比照體態/運動）：檢查這個使用者所有 active 的記帳目標，
    「目標建立日期之後的收入總額 - 支出總額」是否 ≥ `target_value`；只回傳第一個新達成的目標的
    恭喜文字（同一次交易理論上頂多讓一個目標剛好跨過門檻就已經很罕見，多個一起達成時其餘的下次
    寫入交易再檢查一次即可，不特別處理，避免一次回覆塞多段恭喜文字）。"""
    goals = db.select(
        "module_goals", where="user_id = %s AND module_key = %s AND status = %s", params=(user_id, "finance", "active")
    )
    for goal in goals:
        target_value = goal.get("target_value")
        if target_value is None:
            continue
        since_date = goal["created_at"].astimezone(_TAIWAN_TZ).date()
        rows = db.execute_query(
            "SELECT type, COALESCE(SUM(amount), 0) AS total FROM transactions "
            "WHERE user_id = %s AND transaction_date >= %s GROUP BY type",
            (user_id, since_date),
        )
        totals = {row["type"]: float(row["total"]) for row in rows}
        net = totals.get("income", 0.0) - totals.get("expense", 0.0)
        if net >= float(target_value):
            _mark_goal_achieved(db, goal["id"])
            return f"🎉 恭喜你達成記帳目標「{goal['target_description']}」了！"
    return None


def check_collections_goal_achievement(db: CloudSQLClient, user_id: int) -> str | None:
    """收藏項目被標記 `visited` 後呼叫：檢查這個使用者所有 active 的收藏清單目標，「目前已
    visited 的項目數 - baseline_value」是否 ≥ `target_value`。"""
    goals = db.select(
        "module_goals",
        where="user_id = %s AND module_key = %s AND status = %s",
        params=(user_id, "collections", "active"),
    )
    for goal in goals:
        target_value = goal.get("target_value")
        if target_value is None:
            continue
        baseline_value = goal.get("baseline_value") or 0
        current = db.execute_query(
            "SELECT COUNT(*) AS total FROM collection_items WHERE user_id = %s AND status = 'visited'",
            (user_id,),
        )[0]["total"]
        if (current - baseline_value) >= float(target_value):
            _mark_goal_achieved(db, goal["id"])
            return f"🎉 恭喜你達成收藏清單目標「{goal['target_description']}」了！"
    return None


def compute_collections_baseline(db: CloudSQLClient, user_id: int) -> int:
    """設定收藏清單目標當下，已 `visited` 的項目數，當作 `baseline_value`。"""
    return db.execute_query(
        "SELECT COUNT(*) AS total FROM collection_items WHERE user_id = %s AND status = 'visited'", (user_id,)
    )[0]["total"]
