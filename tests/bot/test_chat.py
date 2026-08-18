from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.bot import chat
from src.bot.state import ConversationStateStore


class _FakeLLMClient:
    def __init__(self, response="收到"):
        self.response = response
        self.last_prompt = None

    def generate_text(self, prompt):
        self.last_prompt = prompt
        return self.response


@pytest.fixture(autouse=True)
def _clear_context():
    chat._context_by_user.clear()
    yield
    chat._context_by_user.clear()


def _handle(fake_db, llm, text="請整理這段內容", telegram_user_id=1, store=None):
    return chat.handle_chat_message(
        fake_db,
        llm,
        None,
        store or ConversationStateStore(),
        telegram_user_id,
        1,
        text,
    )


def test_chat_handles_message_without_persisting_it(fake_db):
    _handle(fake_db, _FakeLLMClient())


def test_chat_prompt_has_static_persona_and_product_boundaries(fake_db):
    llm = _FakeLLMClient()
    _handle(fake_db, llm)

    assert "你是 Robinson" in llm.last_prompt
    assert "不能上網查詢" in llm.last_prompt
    assert "不得聲稱已新增、修改、刪除或儲存" in llm.last_prompt
    assert "資料查詢" in llm.last_prompt


def test_chat_masks_pii_before_external_llm(fake_db):
    llm = _FakeLLMClient()
    reply = _handle(fake_db, llm, "我的手機是 0912345678")

    assert "0912345678" not in llm.last_prompt
    assert "[已遮蔽個資]" in llm.last_prompt
    assert "敏感資料" in reply


def test_chat_keeps_short_context_in_memory(fake_db):
    _handle(fake_db, _FakeLLMClient("第一個回答"), "第一個問題")
    llm = _FakeLLMClient("第二個回答")
    _handle(fake_db, llm, "第二個問題")

    assert "使用者：第一個問題" in llm.last_prompt
    assert "Robinson：第一個回答" in llm.last_prompt


def test_chat_drops_context_after_ten_minutes(fake_db, monkeypatch):
    first = datetime(2026, 8, 18, 10, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    monkeypatch.setattr(chat, "_now", lambda: first)
    _handle(fake_db, _FakeLLMClient("第一個回答"), "第一個問題")
    monkeypatch.setattr(chat, "_now", lambda: first + timedelta(minutes=11))
    llm = _FakeLLMClient("第二個回答")
    _handle(fake_db, llm, "第二個問題")

    assert "第一個問題" not in llm.last_prompt


def test_chat_context_is_isolated_by_telegram_user(fake_db):
    _handle(fake_db, _FakeLLMClient("私人回答"), "私人內容", telegram_user_id=1)
    llm = _FakeLLMClient()
    _handle(fake_db, llm, telegram_user_id=2)

    assert "私人內容" not in llm.last_prompt


def test_unknown_marker_reports_no_reliable_data_without_teaching_flow(fake_db):
    store = ConversationStateStore()
    reply = _handle(fake_db, _FakeLLMClient("不知道【NOT_FOUND】"), store=store)

    assert "沒有可靠資料" in reply
    assert store.get(1) is None


def test_todo_marker_only_enters_confirm_flow(fake_db):
    store = ConversationStateStore()
    reply = _handle(fake_db, _FakeLLMClient("要進入待辦事項嗎？【REQUEST_TODO】"), store=store)

    assert "REQUEST_TODO" not in reply
    assert store.get(1)["flow"] == "pending_todo_confirm"


def test_clear_short_context_removes_history(fake_db):
    _handle(fake_db, _FakeLLMClient("回答"), "內容")
    chat.clear_short_context(1)
    llm = _FakeLLMClient()
    _handle(fake_db, llm)

    assert "使用者：內容" not in llm.last_prompt
