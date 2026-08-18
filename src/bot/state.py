"""Telegram 功能模式與未送出草稿的 process 記憶體儲存。

依 ADR-2（docs/specs/platform-auth/SPEC.md）：狀態僅存於 process 記憶體，不落地資料庫。
服務重啟或休眠喚醒會清空所有進行中的狀態，這是刻意的取捨（詳見 ADR-2 理由）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_MODE_TTL = timedelta(minutes=10)
_DRAFT_TTL = timedelta(minutes=30)

_FLOW_FEATURE_PREFIXES = {
    "pending_todo_": "todo",
    "pending_mood_": "mood",
    "pending_exercise_": "exercise",
    "pending_diet_": "diet",
    "pending_body_": "body",
    "pending_goal_": "body",
    "pending_transaction_": "finance",
    "pending_finance_": "finance",
    "pending_module_goal_": "goals",
    "pending_important_day_": "important_days",
    "pending_collection_": "collections",
    "pending_trip_": "collections",
    "pending_achievement_": "achievements",
    "pending_exam_score_": "certificate",
    "pending_certificate_goal_": "certificate",
    "pending_quiz_schedule_": "certificate",
    "pending_job_": "job_search",
    "pending_external_job_": "job_search",
}
_DRAFT_DATA_KEYS = {
    "content",
    "original_text",
    "title",
    "description",
    "category",
    "mood_category",
    "activity",
    "duration_minutes",
    "water_ml",
    "food_description",
    "weight_kg",
    "height_cm",
    "waist_cm",
    "amount",
    "transaction_type",
    "target_value",
    "target_description",
    "target_date",
    "exam_date",
    "score",
    "company_name",
    "job_title",
    "resume_text",
}
_TRANSIENT_FLOWS = {"awaiting_passcode", "pending_voice_confirm", "pending_image_confirm"}


def _infer_feature(state: dict) -> str | None:
    flow = str(state.get("flow") or "")
    return next((feature for prefix, feature in _FLOW_FEATURE_PREFIXES.items() if flow.startswith(prefix)), None)


def _contains_draft_data(state: dict) -> bool:
    return any(key in state and state[key] not in (None, "", [], {}) for key in _DRAFT_DATA_KEYS)


@dataclass
class _ActiveMode:
    state: dict
    updated_at: datetime
    feature: str | None = None
    is_draft: bool = False


@dataclass
class _Draft:
    state: dict
    updated_at: datetime


class ConversationStateStore:
    """單一 process 內的對話狀態暫存區，key 為 telegram_user_id。"""

    def __init__(self, now: Callable[[], datetime] | None = None):
        self._states: dict[int, _ActiveMode] = {}
        self._drafts: dict[int, dict[str, _Draft]] = {}
        self._expired_modes: dict[int, dict] = {}
        self._now = now or (lambda: datetime.now(timezone.utc))

    def get(self, telegram_user_id: int) -> dict | None:
        """取得目前狀態；沒有進行中的對話則回傳 None。"""
        active = self._states.get(telegram_user_id)
        if active is None:
            return None
        if self._now() - active.updated_at <= _MODE_TTL:
            return active.state

        self._states.pop(telegram_user_id, None)
        if active.is_draft and active.feature:
            self.save_draft(telegram_user_id, active.feature, active.state, updated_at=active.updated_at)
        self._expired_modes[telegram_user_id] = {
            "feature": active.feature,
            "had_draft": bool(active.is_draft and active.feature),
        }
        return None

    def set(
        self,
        telegram_user_id: int,
        state: dict,
        *,
        feature: str | None = None,
        is_draft: bool = False,
    ) -> None:
        """設定（覆蓋）目前狀態。"""
        previous = self._states.get(telegram_user_id)
        inferred_feature = _infer_feature(state)
        is_transient = state.get("flow") in _TRANSIENT_FLOWS
        resolved_feature = None if is_transient else (
            feature if feature is not None else inferred_feature or (previous.feature if previous else None)
        )
        resolved_is_draft = False if is_transient else (
            is_draft or _contains_draft_data(state) or bool(previous and previous.is_draft)
        )
        now = self._now()
        self._states[telegram_user_id] = _ActiveMode(state, now, resolved_feature, resolved_is_draft)
        if resolved_is_draft and resolved_feature:
            self.save_draft(telegram_user_id, resolved_feature, state, updated_at=now)

    def clear(self, telegram_user_id: int, *, preserve_draft: bool = False) -> None:
        """結束對話；成功送出或取消時預設連同目前功能草稿清除。"""
        active = self._states.pop(telegram_user_id, None)
        if not preserve_draft and active and active.feature:
            self.discard_draft(telegram_user_id, active.feature)

    def save_draft(
        self,
        telegram_user_id: int,
        feature: str,
        state: dict,
        *,
        updated_at: datetime | None = None,
    ) -> None:
        """保存或覆蓋指定功能的唯一草稿。"""
        drafts = self._drafts.setdefault(telegram_user_id, {})
        drafts[feature] = _Draft(state.copy(), updated_at or self._now())

    def get_draft(self, telegram_user_id: int, feature: str) -> dict | None:
        """取得尚未逾時的草稿；逾時時惰性清除。"""
        drafts = self._drafts.get(telegram_user_id)
        if not drafts or feature not in drafts:
            return None
        draft = drafts[feature]
        if self._now() - draft.updated_at <= _DRAFT_TTL:
            return draft.state.copy()
        self.discard_draft(telegram_user_id, feature)
        return None

    def discard_draft(self, telegram_user_id: int, feature: str) -> None:
        """放棄指定功能草稿，不影響其他功能。"""
        drafts = self._drafts.get(telegram_user_id)
        if not drafts:
            return
        drafts.pop(feature, None)
        if not drafts:
            self._drafts.pop(telegram_user_id, None)

    def restore_draft(self, telegram_user_id: int, feature: str) -> dict | None:
        """將有效草稿還原為作用中模式。"""
        state = self.get_draft(telegram_user_id, feature)
        if state is None:
            return None
        self.set(telegram_user_id, state, feature=feature, is_draft=True)
        return state

    def pop_expired_mode(self, telegram_user_id: int) -> dict | None:
        """取出一次性的模式逾時通知資料。"""
        return self._expired_modes.pop(telegram_user_id, None)

    def active_feature(self, telegram_user_id: int) -> str | None:
        """取得目前作用中功能；讀取時同樣套用惰性逾時。"""
        if self.get(telegram_user_id) is None:
            return None
        active = self._states.get(telegram_user_id)
        return active.feature if active else None

    @staticmethod
    def summarize(state: dict) -> str:
        """用不含內部識別值的已輸入欄位組成草稿摘要。"""
        hidden = {"flow", "target_user_id", "user_id", "id", "resume_state"}
        parts = []
        for key, value in state.items():
            if key in hidden or key.endswith("_id") or value in (None, "", [], {}):
                continue
            rendered = str(value)
            if len(rendered) > 80:
                rendered = rendered[:77] + "..."
            parts.append(f"{key}: {rendered}")
        return "\n".join(parts) if parts else "已輸入的資料"
