"""一般對話核心：唯讀協助、內容整理與功能導引，不持久化自由聊天。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock
from zoneinfo import ZoneInfo

from src.bot import privacy
from src.bot.state import ConversationStateStore
from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_CONTEXT_TTL = timedelta(minutes=10)
_MAX_CONTEXT_MESSAGES = 10
_UNKNOWN_MARKER = "【NOT_FOUND】"
_REQUEST_TODO_MARKER = "【REQUEST_TODO】"
_PII_DETECTED_REMINDER = (
    "\n\n（提醒：這則訊息裡有偵測到疑似個人敏感資料，我已經自動遮蔽，"
    "但麻煩你盡快到對話紀錄裡手動刪除原始訊息喔！）"
)
_SYSTEM_PROMPT = """你是 Robinson，一位溫暖、直接、重視事實的家庭生活助手。
一般對話只能解釋、摘要、改寫、翻譯、整理或分析使用者提供的內容，協助理解自己的生活紀錄，
以及在需求不明確時導向正確的可見選單。需要正式查詢時，引導使用「資料查詢」選單。

你不能上網查詢即時新聞、天氣、路況、價格或營業資訊；無資料時誠實說無法確認。
不得聲稱已新增、修改、刪除或儲存正式資料；資料異動必須引導到對應選單。
不得要求使用者教你並永久記住答案，也沒有家庭知識庫或跨時間聊天記憶。
不得輸出密碼、Token、內部識別值、SQL 或大量匯出資料。
若使用者描述明確待辦，只能詢問是否進入「待辦事項」選單並在最後輸出【REQUEST_TODO】。
若資訊不足，在最後輸出【NOT_FOUND】，不得虛構。回答精簡自然。
"""


@dataclass(frozen=True)
class _ContextTurn:
    role: str
    content: str
    created_at: datetime


_context_by_user: dict[int, deque[_ContextTurn]] = {}
_context_lock = Lock()


def _now() -> datetime:
    return datetime.now(_TAIWAN_TZ)


def _recent_context(telegram_user_id: int, now: datetime) -> list[_ContextTurn]:
    with _context_lock:
        turns = _context_by_user.get(telegram_user_id, deque())
        valid = deque(
            (turn for turn in turns if now - turn.created_at < _CONTEXT_TTL),
            maxlen=_MAX_CONTEXT_MESSAGES,
        )
        if valid:
            _context_by_user[telegram_user_id] = valid
        else:
            _context_by_user.pop(telegram_user_id, None)
        return list(valid)


def _append_context(telegram_user_id: int, role: str, content: str, now: datetime) -> None:
    with _context_lock:
        turns = _context_by_user.setdefault(telegram_user_id, deque(maxlen=_MAX_CONTEXT_MESSAGES))
        turns.append(_ContextTurn(role=role, content=content, created_at=now))


def clear_short_context(telegram_user_id: int) -> None:
    with _context_lock:
        _context_by_user.pop(telegram_user_id, None)


def handle_chat_message(
    db: CloudSQLClient,
    llm_client,
    text_llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    user_id: int,
    text: str,
    pending_question: str | None = None,
    confirming_question: str | None = None,
    privacy_llm_client=None,
) -> str:
    """處理一般對話；舊參數暫留以相容呼叫端，但不讀寫知識或對話資料表。"""
    del db, text_llm_client, pending_question, confirming_question
    masked_text, pii_detected = privacy.mask_text(text, privacy_llm_client)
    now = _now()
    context_text = "\n".join(
        f"{'使用者' if turn.role == 'user' else 'Robinson'}：{turn.content}"
        for turn in _recent_context(telegram_user_id, now)
    ) or "（無）"
    prompt = (
        f"{_SYSTEM_PROMPT}\n現在時間：{now.strftime('%Y-%m-%d %H:%M')}（Asia/Taipei）\n"
        f"最近 10 分鐘對話：\n{context_text}\n\n使用者現在說：{masked_text}"
    )
    reply = llm_client.generate_text(prompt).strip()
    if _REQUEST_TODO_MARKER in reply:
        reply = reply.replace(_REQUEST_TODO_MARKER, "").rstrip()
        state_store.set(
            telegram_user_id,
            {"flow": "pending_todo_confirm", "target_user_id": user_id, "original_text": masked_text},
        )
    if _UNKNOWN_MARKER in reply:
        reply = reply.replace(_UNKNOWN_MARKER, "").rstrip()
        reply += "\n\n我目前沒有可靠資料可以確認這件事。"
    _append_context(telegram_user_id, "user", masked_text, now)
    _append_context(telegram_user_id, "assistant", reply, now)
    return reply + _PII_DETECTED_REMINDER if pii_detected else reply
