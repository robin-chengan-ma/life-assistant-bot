"""src/bot/commands.py 證照目標設定/查詢/方向建議流程的單元測試（對應 robinson SPEC.md FR-24）。"""
from datetime import date

from src.bot import commands
from src.bot.state import ConversationStateStore


class _FakeLLMClient:
    def __init__(self, *responses):
        self._responses = list(responses)
        self.prompts = []

    def generate_text(self, prompt):
        self.prompts.append(prompt)
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


def _seed_answer(fake_db, **overrides):
    row = {
        "user_id": 1, "certificate_question_id": 1, "vocab_question_id": None,
        "exam_type": "toeic", "question_type": "write", "is_correct": True,
        "answered_on": date(2026, 8, 3), "assignment_id": None,
    }
    row.update(overrides)
    return fake_db.insert("answer_logs", row)


# --- start_set_certificate_goal / handle_certificate_goal_exam_type_step ---


def test_start_set_certificate_goal_no_candidates(fake_db):
    state_store = ConversationStateStore()
    reply = commands.start_set_certificate_goal(fake_db, state_store, 999, 1)

    assert "例如" in reply
    assert state_store.get(999)["flow"] == "pending_certificate_goal_exam_type"


def test_handle_certificate_goal_exam_type_step_moves_to_target_date(fake_db):
    state_store = ConversationStateStore()
    commands.start_set_certificate_goal(fake_db, state_store, 999, 1)

    reply = commands.handle_certificate_goal_exam_type_step(state_store, 999, "toeic")

    assert "目標考試時間" in reply
    assert state_store.get(999)["exam_type"] == "toeic"
    assert state_store.get(999)["flow"] == "pending_certificate_goal_target_date"


def test_handle_certificate_goal_exam_type_step_empty_reprompts(fake_db):
    state_store = ConversationStateStore()
    commands.start_set_certificate_goal(fake_db, state_store, 999, 1)

    reply = commands.handle_certificate_goal_exam_type_step(state_store, 999, "")

    assert "沒看懂" in reply


# --- handle_certificate_goal_target_date_step ---


def test_handle_certificate_goal_target_date_step_skip(fake_db):
    state_store = ConversationStateStore()
    commands.start_set_certificate_goal(fake_db, state_store, 999, 1)
    commands.handle_certificate_goal_exam_type_step(state_store, 999, "toeic")

    llm_client = _FakeLLMClient("STATUS: UNCLEAR")  # 不應該被呼叫，跳過分支直接判斷
    reply = commands.handle_certificate_goal_target_date_step(fake_db, llm_client, state_store, 999, "跳過")

    assert "目標分數" in reply
    assert state_store.get(999)["target_date"] is None
    assert llm_client.prompts == []


def test_handle_certificate_goal_target_date_step_clear(fake_db):
    state_store = ConversationStateStore()
    commands.start_set_certificate_goal(fake_db, state_store, 999, 1)
    commands.handle_certificate_goal_exam_type_step(state_store, 999, "toeic")

    llm_client = _FakeLLMClient("STATUS: CLEAR\nDATE: 2026-12-01")
    reply = commands.handle_certificate_goal_target_date_step(fake_db, llm_client, state_store, 999, "12/1")

    assert "目標分數" in reply
    assert state_store.get(999)["target_date"] == date(2026, 12, 1)


def test_handle_certificate_goal_target_date_step_clear_but_date_unparseable_reprompts(fake_db):
    state_store = ConversationStateStore()
    commands.start_set_certificate_goal(fake_db, state_store, 999, 1)
    commands.handle_certificate_goal_exam_type_step(state_store, 999, "toeic")

    llm_client = _FakeLLMClient("STATUS: CLEAR\nDATE: 不是日期格式")
    reply = commands.handle_certificate_goal_target_date_step(fake_db, llm_client, state_store, 999, "怪怪的輸入")

    assert "跳過" in reply
    assert state_store.get(999)["flow"] == "pending_certificate_goal_target_date"


def test_handle_certificate_goal_target_date_step_unclear_reprompts(fake_db):
    state_store = ConversationStateStore()
    commands.start_set_certificate_goal(fake_db, state_store, 999, 1)
    commands.handle_certificate_goal_exam_type_step(state_store, 999, "toeic")

    llm_client = _FakeLLMClient("STATUS: UNCLEAR")
    reply = commands.handle_certificate_goal_target_date_step(fake_db, llm_client, state_store, 999, "以後再說")

    assert "不太確定" in reply
    assert state_store.get(999)["flow"] == "pending_certificate_goal_target_date"


# --- handle_certificate_goal_target_score_step ---


def test_handle_certificate_goal_target_score_step_writes_goal(fake_db):
    state_store = ConversationStateStore()
    commands.start_set_certificate_goal(fake_db, state_store, 999, 1)
    commands.handle_certificate_goal_exam_type_step(state_store, 999, "toeic")
    llm_client = _FakeLLMClient("STATUS: CLEAR\nDATE: 2026-12-01")
    commands.handle_certificate_goal_target_date_step(fake_db, llm_client, state_store, 999, "12/1")

    reply = commands.handle_certificate_goal_target_score_step(fake_db, state_store, 999, "850")

    assert "記下" in reply
    assert state_store.get(999) is None
    row = fake_db.select("certificate_goals", where="user_id = %s AND exam_type = %s", params=(1, "toeic"), fetch_one=True)
    assert row["target_date"] == date(2026, 12, 1)
    assert row["target_score"] == "850"


def test_handle_certificate_goal_target_score_step_skip(fake_db):
    state_store = ConversationStateStore()
    commands.start_set_certificate_goal(fake_db, state_store, 999, 1)
    commands.handle_certificate_goal_exam_type_step(state_store, 999, "toeic")
    llm_client = _FakeLLMClient("STATUS: UNCLEAR")
    state = state_store.get(999)
    state["flow"] = "pending_certificate_goal_target_score"
    state["target_date"] = None
    state_store.set(999, state)

    reply = commands.handle_certificate_goal_target_score_step(fake_db, state_store, 999, "跳過")

    assert "記下" in reply
    row = fake_db.select("certificate_goals", where="user_id = %s AND exam_type = %s", params=(1, "toeic"), fetch_one=True)
    assert row["target_score"] is None


def test_handle_certificate_goal_target_score_step_empty_reprompts(fake_db):
    state_store = ConversationStateStore()
    state_store.set(999, {"flow": "pending_certificate_goal_target_score", "target_user_id": 1, "exam_type": "toeic", "target_date": None})

    reply = commands.handle_certificate_goal_target_score_step(fake_db, state_store, 999, "   ")

    assert "沒看懂" in reply
    assert state_store.get(999)["flow"] == "pending_certificate_goal_target_score"


# --- handle_my_certificate_goals ---


def test_handle_my_certificate_goals_empty(fake_db):
    assert "還沒有設定" in commands.handle_my_certificate_goals(fake_db, 1)


def test_handle_my_certificate_goals_lists(fake_db):
    fake_db.insert("certificate_goals", {"user_id": 1, "exam_type": "toeic", "target_date": date(2026, 12, 1), "target_score": "850"})

    reply = commands.handle_my_certificate_goals(fake_db, 1)

    assert "toeic" in reply
    assert "850" in reply


# --- start_certificate_advice / handle_certificate_advice_exam_type_step ---


def test_start_certificate_advice_no_data(fake_db):
    state_store = ConversationStateStore()
    llm_client = _FakeLLMClient("不重要")

    reply = commands.start_certificate_advice(fake_db, llm_client, state_store, 999, 1)

    assert "還沒有任何證照相關資料" in reply
    assert llm_client.prompts == []


def test_start_certificate_advice_single_candidate_generates_directly(fake_db):
    _seed_answer(fake_db, exam_type="toeic")
    state_store = ConversationStateStore()
    llm_client = _FakeLLMClient("繼續加油，多練習填空題！")

    reply = commands.start_certificate_advice(fake_db, llm_client, state_store, 999, 1)

    assert "toeic" in reply
    assert "繼續加油" in reply
    assert state_store.get(999) is None
    assert len(llm_client.prompts) == 1


def test_start_certificate_advice_multiple_candidates_asks(fake_db):
    _seed_answer(fake_db, exam_type="toeic")
    _seed_answer(fake_db, exam_type="gcp")
    state_store = ConversationStateStore()
    llm_client = _FakeLLMClient("不重要")

    reply = commands.start_certificate_advice(fake_db, llm_client, state_store, 999, 1)

    assert "gcp" in reply
    assert "toeic" in reply
    assert state_store.get(999)["flow"] == "pending_certificate_advice_exam_type"
    assert llm_client.prompts == []


def test_handle_certificate_advice_exam_type_step_generates(fake_db):
    _seed_answer(fake_db, exam_type="toeic")
    _seed_answer(fake_db, exam_type="gcp")
    state_store = ConversationStateStore()
    llm_client = _FakeLLMClient("不重要")
    commands.start_certificate_advice(fake_db, llm_client, state_store, 999, 1)

    llm_client2 = _FakeLLMClient("多加強聽力！")
    reply = commands.handle_certificate_advice_exam_type_step(fake_db, llm_client2, state_store, 999, "toeic")

    assert "toeic" in reply
    assert "多加強聽力" in reply
    assert state_store.get(999) is None


def test_handle_certificate_advice_exam_type_step_empty_reprompts(fake_db):
    _seed_answer(fake_db, exam_type="toeic")
    _seed_answer(fake_db, exam_type="gcp")
    state_store = ConversationStateStore()
    llm_client = _FakeLLMClient("不重要")
    commands.start_certificate_advice(fake_db, llm_client, state_store, 999, 1)

    reply = commands.handle_certificate_advice_exam_type_step(fake_db, llm_client, state_store, 999, "  ")

    assert "沒看懂" in reply
    assert state_store.get(999)["flow"] == "pending_certificate_advice_exam_type"
