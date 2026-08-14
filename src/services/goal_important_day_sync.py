"""將具有明確日期的體態／證照目標同步至 Mobile App 重要日子。"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from src.services.app_important_days import AppImportantDayService


class GoalSyncDatabase(Protocol):
    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False): ...
    def update(self, table, data, where, params): ...


def sync_body_goal(db: GoalSyncDatabase, goal_id: int) -> int | None:
    goal = db.select("body_goals", where="id = %s", params=(goal_id,), fetch_one=True)
    if not goal:
        return None
    return _sync(
        db,
        table="body_goals",
        row=goal,
        owner_user_id=goal["user_id"],
        title=f"體態目標：{goal['target_description']}",
        target_date=goal.get("target_date"),
        active=goal.get("status") == "active",
        notes="由體態目標自動同步",
    )


def sync_certificate_goal(db: GoalSyncDatabase, goal_id: int) -> int | None:
    goal = db.select("certificate_goals", where="id = %s", params=(goal_id,), fetch_one=True)
    if not goal:
        return None
    score = f"（目標：{goal['target_score']}）" if goal.get("target_score") else ""
    return _sync(
        db,
        table="certificate_goals",
        row=goal,
        owner_user_id=goal["user_id"],
        title=f"{goal['exam_type']} 考試目標{score}",
        target_date=goal.get("target_date"),
        active=goal.get("target_date") is not None,
        notes="由考試／證照目標自動同步",
    )


def deactivate_linked_important_day(db: GoalSyncDatabase, important_day_id: int | None, owner_user_id: int) -> None:
    if important_day_id is None:
        return
    db.update(
        "important_days",
        {"is_active": False},
        where="id = %s AND owner_user_id = %s",
        params=(important_day_id, owner_user_id),
    )


def _sync(
    db: GoalSyncDatabase,
    *,
    table: str,
    row: dict[str, Any],
    owner_user_id: int,
    title: str,
    target_date: date | None,
    active: bool,
    notes: str,
) -> int | None:
    important_day_id = row.get("important_day_id")
    if target_date is None or not active:
        deactivate_linked_important_day(db, important_day_id, owner_user_id)
        return important_day_id

    payload = {
        "title": title,
        "recurrence_type": "one_time",
        "event_date": target_date.isoformat(),
        "event_end_date": target_date.isoformat(),
        "is_all_day": True,
        "reminder_days_before": 1,
        "audience_mode": "self",
        "recipient_ids": [],
        "show_on_todo_calendar": True,
        "is_active": True,
        "notes": notes,
    }
    service = AppImportantDayService(db)
    if important_day_id:
        existing = service._owned(important_day_id, owner_user_id)
        payload.update({
            "reminder_days_before": existing.get("reminder_days_before", 1),
            "audience_mode": existing.get("audience_mode", "self"),
            "show_on_todo_calendar": existing.get("show_on_todo_calendar", True),
        })
        if payload["audience_mode"] == "specific":
            recipients = db.select(
                "important_day_recipients",
                columns=("user_id",),
                where="important_day_id = %s",
                params=(important_day_id,),
            )
            payload["recipient_ids"] = [item["user_id"] for item in recipients]
        service.update(important_day_id, owner_user_id, payload)
        return important_day_id

    result = service.create(owner_user_id, payload)
    db.update(table, {"important_day_id": result["id"]}, where="id = %s", params=(row["id"],))
    return result["id"]
