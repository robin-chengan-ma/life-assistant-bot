"""src/bot/commands.py 證照題庫作答與彈性排程調整流程的單元測試
（對應 robinson SPEC.md FR-27、FR-26 決策 5、6，Step 3.3）。
"""
from datetime import date, datetime

from src.bot import commands
from src.bot.state import ConversationStateStore

_FIXED_NOW = datetime(2026, 8, 8, 10, 0, tzinfo=commands._TAIWAN_TZ)


class _FakeLLMClient:
    """模擬 submodules.llm.client.LLMClient；`responses` 依序回傳，最後一筆重複使用，
    讓同一個測試裡多輪分類呼叫（例如 SPREAD 反覆調整）可以各自對應不同回覆。
    """

    def __init__(self, *responses):
        self._responses = list(responses)
        self.prompts = []

    def generate_text(self, prompt):
        self.prompts.append(prompt)
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


def _seed_certificate_question(fake_db, **overrides):
    row = {
        "exam_type": "ielts", "question_type": "write", "test_id": "0001", "question_number": 1,
        "question_text": "What is the capital of France?",
        "options": ["A. Paris", "B. London", "C. Berlin", "D. Rome"],
        "correct_answer": "A", "explanation": "巴黎是法國首都。",
    }
    row.update(overrides)
    return fake_db.insert("certificate_questions", row)


def _seed_assignment(fake_db, **overrides):
    row = {
        "user_id": 1, "exam_type": "ielts", "assigned_date": date(2026, 8, 8),
        "certificate_question_id": None, "vocab_question_id": None, "is_review": False,
    }
    row.update(overrides)
    return fake_db.insert("certificate_daily_assignments", row)


def _seed_settings(fake_db, **overrides):
    row = {
        "user_id": 1, "exam_type": "ielts", "daily_question_count": 6,
        "review_ratio_new": 7, "review_ratio_review": 3,
    }
    row.update(overrides)
    return fake_db.insert("certificate_daily_settings", row)


# --- start_quiz_answer / handle_quiz_answer_step（FR-27）---


def test_start_quiz_answer_returns_no_pending_reply_when_nothing_to_answer(fake_db):
    state_store = ConversationStateStore()
    reply = commands.start_quiz_answer(fake_db, state_store, 999, 1)

    assert reply == commands._QUIZ_NO_PENDING_QUESTIONS_REPLY
    assert state_store.get(999) is None


def test_start_quiz_answer_presents_first_question_and_sets_state(fake_db):
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid)
    state_store = ConversationStateStore()

    reply = commands.start_quiz_answer(fake_db, state_store, 999, 1)

    assert "第 1/1 題" in reply
    assert "What is the capital of France?" in reply
    state = state_store.get(999)
    assert state["flow"] == "pending_quiz_answer"
    assert state["position"] == 0


def test_handle_quiz_answer_step_invalid_letter_reprompts(fake_db):
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid)
    state_store = ConversationStateStore()
    commands.start_quiz_answer(fake_db, state_store, 999, 1)

    reply = commands.handle_quiz_answer_step(fake_db, state_store, 999, "隨便")

    assert reply == commands._QUIZ_ANSWER_FORMAT_REPROMPT
    assert state_store.get(999)["position"] == 0


def test_handle_quiz_answer_step_correct_answer_shows_feedback_and_finishes(fake_db):
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid)
    state_store = ConversationStateStore()
    commands.start_quiz_answer(fake_db, state_store, 999, 1)

    reply = commands.handle_quiz_answer_step(fake_db, state_store, 999, "a")

    assert "✅ 答對了" in reply
    assert "巴黎是法國首都" in reply
    assert commands.certificate_answer.ALL_DONE_MESSAGE in reply
    assert state_store.get(999) is None
    logs = fake_db.select("answer_logs")
    assert len(logs) == 1
    assert logs[0]["is_correct"] is True


def test_handle_quiz_answer_step_wrong_answer_shows_feedback(fake_db):
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid)
    state_store = ConversationStateStore()
    commands.start_quiz_answer(fake_db, state_store, 999, 1)

    reply = commands.handle_quiz_answer_step(fake_db, state_store, 999, "B")

    assert "❌ 答錯了" in reply
    logs = fake_db.select("answer_logs")
    assert logs[0]["is_correct"] is False


def test_handle_quiz_answer_step_moves_to_next_question(fake_db):
    qid1 = _seed_certificate_question(fake_db, question_number=1, question_text="Q1")
    qid2 = _seed_certificate_question(fake_db, question_number=2, question_text="Q2")
    _seed_assignment(fake_db, certificate_question_id=qid1)
    _seed_assignment(fake_db, certificate_question_id=qid2)
    state_store = ConversationStateStore()
    commands.start_quiz_answer(fake_db, state_store, 999, 1)

    reply = commands.handle_quiz_answer_step(fake_db, state_store, 999, "A")

    assert "第 2/2 題" in reply
    assert "Q2" in reply
    state = state_store.get(999)
    assert state["position"] == 1


def test_start_quiz_answer_skips_question_with_unparseable_correct_answer(fake_db):
    bad_qid = _seed_certificate_question(fake_db, question_number=1, correct_answer="無法辨識")
    good_qid = _seed_certificate_question(fake_db, question_number=2, question_text="Q2")
    _seed_assignment(fake_db, certificate_question_id=bad_qid)
    _seed_assignment(fake_db, certificate_question_id=good_qid)
    state_store = ConversationStateStore()

    reply = commands.start_quiz_answer(fake_db, state_store, 999, 1)

    assert "Q2" in reply
    state = state_store.get(999)
    assert state["position"] == 1


def test_handle_quiz_answer_step_recomputes_view_when_not_cached(fake_db):
    qid = _seed_certificate_question(fake_db)
    _seed_assignment(fake_db, certificate_question_id=qid)
    state_store = ConversationStateStore()
    commands.start_quiz_answer(fake_db, state_store, 999, 1)
    # 模擬 state 裡沒有快取 current_view 的情境（例如 process 重啟後從外部儲存還原的舊 state）。
    state = state_store.get(999)
    state["current_view"] = None
    state_store.set(999, state)

    reply = commands.handle_quiz_answer_step(fake_db, state_store, 999, "A")

    assert "✅ 答對了" in reply


def test_handle_quiz_answer_step_skips_deleted_assignment(fake_db):
    qid1 = _seed_certificate_question(fake_db, question_number=1)
    qid2 = _seed_certificate_question(fake_db, question_number=2, question_text="Q2")
    _seed_assignment(fake_db, certificate_question_id=qid1)
    a2 = _seed_assignment(fake_db, certificate_question_id=qid2)
    state_store = ConversationStateStore()
    commands.start_quiz_answer(fake_db, state_store, 999, 1)

    fake_db.delete("certificate_daily_assignments", where="id = %s", params=(a2,))
    reply = commands.handle_quiz_answer_step(fake_db, state_store, 999, "A")

    assert reply.endswith(commands.certificate_answer.ALL_DONE_MESSAGE)
    assert state_store.get(999) is None


def test_handle_quiz_answer_step_skips_when_current_assignment_deleted_before_answering(fake_db):
    """呈現題目後、使用者實際回覆之前，這題就被刪除（例如透過排程調整流程被取消），
    應該跳過這題而不是報錯，見 handle_quiz_answer_step() 內的防線說明。"""
    qid1 = _seed_certificate_question(fake_db, question_number=1)
    qid2 = _seed_certificate_question(fake_db, question_number=2, question_text="Q2")
    a1 = _seed_assignment(fake_db, certificate_question_id=qid1)
    _seed_assignment(fake_db, certificate_question_id=qid2)
    state_store = ConversationStateStore()
    commands.start_quiz_answer(fake_db, state_store, 999, 1)

    fake_db.delete("certificate_daily_assignments", where="id = %s", params=(a1,))
    reply = commands.handle_quiz_answer_step(fake_db, state_store, 999, "A")

    assert "Q2" in reply
    state = state_store.get(999)
    assert state["position"] == 1


# --- start_quiz_schedule_adjust / handle_quiz_schedule_exam_type_choice_step ---


def test_start_quiz_schedule_adjust_no_exam_type(fake_db):
    state_store = ConversationStateStore()
    reply = commands.start_quiz_schedule_adjust(fake_db, state_store, 999, 1)

    assert reply == commands._QUIZ_SCHEDULE_NO_EXAM_TYPE_REPLY
    assert state_store.get(999) is None


def test_start_quiz_schedule_adjust_single_exam_type_skips_choice(fake_db):
    _seed_certificate_question(fake_db)
    state_store = ConversationStateStore()

    reply = commands.start_quiz_schedule_adjust(fake_db, state_store, 999, 1)

    assert reply == commands._QUIZ_SCHEDULE_INTENT_ASK
    state = state_store.get(999)
    assert state["flow"] == "pending_quiz_schedule_intent"
    assert state["exam_type"] == "ielts"


def test_start_quiz_schedule_adjust_multiple_exam_types_asks_choice(fake_db):
    _seed_certificate_question(fake_db, exam_type="ielts")
    _seed_certificate_question(fake_db, exam_type="toeic", question_number=1)
    state_store = ConversationStateStore()

    reply = commands.start_quiz_schedule_adjust(fake_db, state_store, 999, 1)

    assert "1. ielts" in reply
    assert "2. toeic" in reply
    state = state_store.get(999)
    assert state["flow"] == "pending_quiz_schedule_exam_type_choice"
    assert state["exam_type_options"] == ["ielts", "toeic"]


def test_handle_quiz_schedule_exam_type_choice_step_invalid_index(fake_db):
    _seed_certificate_question(fake_db, exam_type="ielts")
    _seed_certificate_question(fake_db, exam_type="toeic", question_number=1)
    state_store = ConversationStateStore()
    commands.start_quiz_schedule_adjust(fake_db, state_store, 999, 1)

    reply = commands.handle_quiz_schedule_exam_type_choice_step(state_store, 999, "9")

    assert reply == commands._QUIZ_SCHEDULE_INVALID_INDEX_REPLY


def test_handle_quiz_schedule_exam_type_choice_step_valid_index(fake_db):
    _seed_certificate_question(fake_db, exam_type="ielts")
    _seed_certificate_question(fake_db, exam_type="toeic", question_number=1)
    state_store = ConversationStateStore()
    commands.start_quiz_schedule_adjust(fake_db, state_store, 999, 1)

    reply = commands.handle_quiz_schedule_exam_type_choice_step(state_store, 999, "2")

    assert reply == commands._QUIZ_SCHEDULE_INTENT_ASK
    state = state_store.get(999)
    assert state["flow"] == "pending_quiz_schedule_intent"
    assert state["exam_type"] == "toeic"


# --- handle_quiz_schedule_intent_step ---


def _start_intent_state(fake_db, state_store, exam_type="ielts"):
    _seed_certificate_question(fake_db, exam_type=exam_type)
    commands.start_quiz_schedule_adjust(fake_db, state_store, 999, 1)


def test_handle_quiz_schedule_intent_step_cancel(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: _FIXED_NOW)
    state_store = ConversationStateStore()
    _start_intent_state(fake_db, state_store)
    _seed_assignment(fake_db, certificate_question_id=_seed_certificate_question(fake_db, question_number=2))
    llm_client = _FakeLLMClient("INTENT: CANCEL")

    reply = commands.handle_quiz_schedule_intent_step(fake_db, llm_client, state_store, 999, "今天不想做了，取消")

    assert "取消" in reply
    assert "ielts" in reply
    assert state_store.get(999) is None
    overrides = fake_db.select("certificate_daily_schedule_overrides")
    assert any(o["daily_question_count"] == 0 for o in overrides)


def test_handle_quiz_schedule_intent_step_move_valid_date(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: _FIXED_NOW)
    state_store = ConversationStateStore()
    _start_intent_state(fake_db, state_store)
    llm_client = _FakeLLMClient("INTENT: MOVE\nMOVE_DATE: 2026-08-10")

    reply = commands.handle_quiz_schedule_intent_step(fake_db, llm_client, state_store, 999, "改到8/10")

    assert "8/10" in reply
    assert state_store.get(999) is None
    overrides = fake_db.select("certificate_daily_schedule_overrides")
    assert any(o["start_date"] == date(2026, 8, 10) for o in overrides)


def test_handle_quiz_schedule_intent_step_move_past_date_reprompts(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: _FIXED_NOW)
    state_store = ConversationStateStore()
    _start_intent_state(fake_db, state_store)
    llm_client = _FakeLLMClient("INTENT: MOVE\nMOVE_DATE: 2026-08-01")

    reply = commands.handle_quiz_schedule_intent_step(fake_db, llm_client, state_store, 999, "改到之前")

    assert reply == commands._QUIZ_SCHEDULE_INVALID_DATE_REPLY
    assert state_store.get(999)["flow"] == "pending_quiz_schedule_intent"


def test_handle_quiz_schedule_intent_step_range_valid(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: _FIXED_NOW)
    state_store = ConversationStateStore()
    _start_intent_state(fake_db, state_store)
    llm_client = _FakeLLMClient("INTENT: RANGE\nRANGE_START: 2026-08-10\nRANGE_END: 2026-08-15\nRANGE_COUNT: 3")

    reply = commands.handle_quiz_schedule_intent_step(fake_db, llm_client, state_store, 999, "8/10到8/15改成3題")

    assert "3 題" in reply
    assert state_store.get(999) is None
    overrides = fake_db.select("certificate_daily_schedule_overrides")
    assert any(o["daily_question_count"] == 3 for o in overrides)


def test_handle_quiz_schedule_intent_step_range_invalid_reprompts(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: _FIXED_NOW)
    state_store = ConversationStateStore()
    _start_intent_state(fake_db, state_store)
    llm_client = _FakeLLMClient("INTENT: RANGE\nRANGE_START: \nRANGE_END: \nRANGE_COUNT: ")

    reply = commands.handle_quiz_schedule_intent_step(fake_db, llm_client, state_store, 999, "看不懂")

    assert reply == commands._QUIZ_SCHEDULE_INVALID_RANGE_REPLY
    assert state_store.get(999)["flow"] == "pending_quiz_schedule_intent"


def test_handle_quiz_schedule_intent_step_unclear_reprompts(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: _FIXED_NOW)
    state_store = ConversationStateStore()
    _start_intent_state(fake_db, state_store)
    llm_client = _FakeLLMClient("INTENT: UNCLEAR")

    reply = commands.handle_quiz_schedule_intent_step(fake_db, llm_client, state_store, 999, "今天天氣真好")

    assert reply == commands._QUIZ_SCHEDULE_UNCLEAR_REPLY
    assert state_store.get(999)["flow"] == "pending_quiz_schedule_intent"


def test_handle_quiz_schedule_intent_step_spread_computes_proposal(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: _FIXED_NOW)
    state_store = ConversationStateStore()
    _start_intent_state(fake_db, state_store)
    _seed_settings(fake_db, daily_question_count=3)
    llm_client = _FakeLLMClient("INTENT: SPREAD")

    reply = commands.handle_quiz_schedule_intent_step(fake_db, llm_client, state_store, 999, "平攤到最近幾天")

    assert "8/9" in reply
    state = state_store.get(999)
    assert state["flow"] == "pending_quiz_schedule_spread_confirm"
    assert len(state["plan"]) == 3


# --- handle_quiz_schedule_spread_confirm_step ---


def _start_spread_confirm_state(fake_db, state_store):
    _start_intent_state(fake_db, state_store)
    _seed_settings(fake_db, daily_question_count=3)
    llm_client = _FakeLLMClient("INTENT: SPREAD")
    commands.handle_quiz_schedule_intent_step(fake_db, llm_client, state_store, 999, "平攤")


def test_handle_quiz_schedule_spread_confirm_step_confirm_writes_plan(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: _FIXED_NOW)
    state_store = ConversationStateStore()
    _start_spread_confirm_state(fake_db, state_store)
    llm_client = _FakeLLMClient("STATUS: CONFIRM")

    reply = commands.handle_quiz_schedule_spread_confirm_step(fake_db, llm_client, state_store, 999, "OK")

    assert "完成" in reply
    assert state_store.get(999) is None
    overrides = fake_db.select("certificate_daily_schedule_overrides")
    assert len(overrides) == 4  # 今天歸零 + 3 天分攤


def test_handle_quiz_schedule_spread_confirm_step_cancel(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: _FIXED_NOW)
    state_store = ConversationStateStore()
    _start_spread_confirm_state(fake_db, state_store)
    llm_client = _FakeLLMClient("STATUS: CANCEL")

    reply = commands.handle_quiz_schedule_spread_confirm_step(fake_db, llm_client, state_store, 999, "算了")

    assert "先不調整" in reply
    assert state_store.get(999) is None
    assert fake_db.select("certificate_daily_schedule_overrides") == []


def test_handle_quiz_schedule_spread_confirm_step_custom_days_recomputes(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: _FIXED_NOW)
    state_store = ConversationStateStore()
    _start_spread_confirm_state(fake_db, state_store)
    llm_client = _FakeLLMClient("STATUS: CUSTOM_DAYS\nDAYS: 2")

    reply = commands.handle_quiz_schedule_spread_confirm_step(fake_db, llm_client, state_store, 999, "攤成2天就好")

    state = state_store.get(999)
    assert state["flow"] == "pending_quiz_schedule_spread_confirm"
    assert len(state["plan"]) == 2
    assert "8/9" in reply
    assert "8/10" in reply


def test_handle_quiz_schedule_spread_confirm_step_custom_days_invalid(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: _FIXED_NOW)
    state_store = ConversationStateStore()
    _start_spread_confirm_state(fake_db, state_store)
    llm_client = _FakeLLMClient("STATUS: CUSTOM_DAYS\nDAYS: ")

    reply = commands.handle_quiz_schedule_spread_confirm_step(fake_db, llm_client, state_store, 999, "嗯…幾天好呢")

    assert reply == commands._QUIZ_SCHEDULE_SPREAD_INVALID_DAYS_REPLY
    assert state_store.get(999)["flow"] == "pending_quiz_schedule_spread_confirm"


def test_handle_quiz_schedule_spread_confirm_step_unclear(fake_db, monkeypatch):
    monkeypatch.setattr(commands, "_now", lambda: _FIXED_NOW)
    state_store = ConversationStateStore()
    _start_spread_confirm_state(fake_db, state_store)
    llm_client = _FakeLLMClient("STATUS: UNCLEAR")

    reply = commands.handle_quiz_schedule_spread_confirm_step(fake_db, llm_client, state_store, 999, "嗯…")

    assert reply == commands._QUIZ_SCHEDULE_SPREAD_UNCLEAR_REPLY
    assert state_store.get(999)["flow"] == "pending_quiz_schedule_spread_confirm"
