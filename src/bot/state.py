"""Owner /set_invite_codes 對話流程的暫存狀態。

依 ADR-2（docs/specs/platform-auth/SPEC.md）：狀態僅存於 process 記憶體，不落地資料庫。
服務重啟或休眠喚醒會清空所有進行中的狀態，這是刻意的取捨（詳見 ADR-2 理由）。
"""


class ConversationStateStore:
    """單一 process 內的對話狀態暫存區，key 為 telegram_user_id。"""

    def __init__(self):
        self._states: dict[int, dict] = {}

    def get(self, telegram_user_id: int) -> dict | None:
        """取得目前狀態；沒有進行中的對話則回傳 None。"""
        return self._states.get(telegram_user_id)

    def set(self, telegram_user_id: int, state: dict) -> None:
        """設定（覆蓋）目前狀態。"""
        self._states[telegram_user_id] = state

    def clear(self, telegram_user_id: int) -> None:
        """結束對話，清除狀態；若原本就沒有狀態也不會出錯。"""
        self._states.pop(telegram_user_id, None)
