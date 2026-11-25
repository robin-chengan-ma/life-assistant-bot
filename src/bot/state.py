"""Telegram 對話狀態的 process 記憶體儲存。

依 ADR-2（docs/specs/platform-auth/SPEC.md）：狀態僅存於 process 記憶體，不落地資料庫。
服務重啟或休眠喚醒會清空所有進行中的狀態，這是刻意的取捨（詳見 ADR-2 理由）。

2026-11（功能大幅精簡）：Telegram 機器人只剩下 `/start` 通關密碼綁定與 Owner 專屬的權限管理
對話流程（`permission_create`／`permission_disable`／`permission_enable`／`permission_resend`），
兩者都只需要「目前卡在哪一步、還沒逾時」這個最小功能，拿掉舊版草稿暫存
（`save_draft`／`get_draft`／`restore_draft`）與功能推斷（`_infer_feature`）這些只服務於已刪除
的多功能選單系統（運動、飲食、記帳、待辦等各自的草稿續寫）的機制，避免維護一堆永遠不會再被
呼叫的程式碼。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

_MODE_TTL = timedelta(minutes=10)


@dataclass
class _ActiveState:
    state: dict
    updated_at: datetime


class ConversationStateStore:
    """單一 process 內的對話狀態暫存區，key 為 telegram_user_id。"""

    def __init__(self, now: Callable[[], datetime] | None = None):
        self._states: dict[int, _ActiveState] = {}
        self._now = now or (lambda: datetime.now(UTC))

    def get(self, telegram_user_id: int) -> dict | None:
        """取得目前狀態；沒有進行中的對話，或已逾時（10 分鐘未互動），則回傳 None。"""
        active = self._states.get(telegram_user_id)
        if active is None:
            return None
        if self._now() - active.updated_at <= _MODE_TTL:
            return active.state
        self._states.pop(telegram_user_id, None)
        return None

    def set(self, telegram_user_id: int, state: dict) -> None:
        """設定（覆蓋）目前狀態。"""
        self._states[telegram_user_id] = _ActiveState(state, self._now())

    def clear(self, telegram_user_id: int) -> None:
        """結束對話。"""
        self._states.pop(telegram_user_id, None)
