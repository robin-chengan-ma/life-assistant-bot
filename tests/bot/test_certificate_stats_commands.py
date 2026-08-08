"""src/bot/commands.py 成效彈性文字問答流程的單元測試（對應 robinson SPEC.md FR-29、ADR-19 決策 4）。"""
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


def _seed_score(fake_db, **overrides):
    row = {"user_id": 1, "exam_type": "toeic", "exam_date": date(2026, 8, 1), "score": "850"}
    row.update(overrides)
    return fake_db.insert("exam_official_scores", row)


# --- start_quiz_stats_query ---


def test_start_quiz_stats_query_no_data(fake_db):
    state_store = ConversationStateStore()
    reply = commands.start_quiz_stats_query(fake_db, state_store, 999, 1)

    assert reply == commands._QUIZ_STATS_NO_DATA_REPLY
    assert state_store.get(999) is None


def test_start_quiz_stats_query_asks_initial_question(fake_db):
    _seed_answer(fake_db)
    state_store = ConversationStateStore()

    reply = commands.start_quiz_stats_query(fake_db, state_store, 999, 1)

    assert reply == commands._QUIZ_STATS_INITIAL_ASK
    state = state_store.get(999)
    assert state["flow"] == "pending_quiz_stats_query"
    assert state["history"] == []


def test_handle_quiz_stats_query_step_no_data_left_mid_flow(fake_db):
    """理論上很少見的邊界情境：開始問答時還有資料，使用者回覆之前資料被清空了（例如另一個流程
    刪除了所有作答紀錄），這裡驗證不會出錯，會直接優雅收斂成「沒有資料」的回覆。"""
    row_id = _seed_answer(fake_db)
    state_store = ConversationStateStore()
    commands.start_quiz_stats_query(fake_db, state_store, 999, 1)
    fake_db.delete("answer_logs", where="id = %s", params=(row_id,))

    llm_client = _FakeLLMClient("不應該被呼叫")
    reply = commands.handle_quiz_stats_query_step(fake_db, llm_client, state_store, 999, "上週答對幾題")

    assert reply == commands._QUIZ_STATS_NO_DATA_REPLY
    assert state_store.get(999) is None
    assert llm_client.prompts == []


# --- handle_quiz_stats_query_step：反問分支 ---


def test_handle_quiz_stats_query_step_need_exam_type(fake_db):
    _seed_answer(fake_db, exam_type="toeic")
    _seed_answer(fake_db, exam_type="gcp")
    state_store = ConversationStateStore()
    commands.start_quiz_stats_query(fake_db, state_store, 999, 1)

    llm_client = _FakeLLMClient("STATUS: NEED_EXAM_TYPE")
    reply = commands.handle_quiz_stats_query_step(fake_db, llm_client, state_store, 999, "上週答對幾題")

    assert "哪個證照" in reply
    assert "gcp" in reply and "toeic" in reply
    assert state_store.get(999)["flow"] == "pending_quiz_stats_query"
    assert state_store.get(999)["history"] == ["上週答對幾題"]


def test_handle_quiz_stats_query_step_need_scope(fake_db):
    _seed_answer(fake_db)
    state_store = ConversationStateStore()
    commands.start_quiz_stats_query(fake_db, state_store, 999, 1)

    llm_client = _FakeLLMClient("STATUS: NEED_SCOPE")
    reply = commands.handle_quiz_stats_query_step(fake_db, llm_client, state_store, 999, "toeic 上週")

    assert reply == commands._QUIZ_STATS_NEED_SCOPE_REPLY


def test_handle_quiz_stats_query_step_need_period(fake_db):
    _seed_answer(fake_db)
    state_store = ConversationStateStore()
    commands.start_quiz_stats_query(fake_db, state_store, 999, 1)

    llm_client = _FakeLLMClient("STATUS: NEED_PERIOD")
    reply = commands.handle_quiz_stats_query_step(fake_db, llm_client, state_store, 999, "toeic 小考成效")

    assert reply == commands._QUIZ_STATS_NEED_PERIOD_REPLY


def test_handle_quiz_stats_query_step_unclear(fake_db):
    _seed_answer(fake_db)
    state_store = ConversationStateStore()
    commands.start_quiz_stats_query(fake_db, state_store, 999, 1)

    llm_client = _FakeLLMClient("STATUS: UNCLEAR")
    reply = commands.handle_quiz_stats_query_step(fake_db, llm_client, state_store, 999, "今天天氣真好")

    assert reply == commands._QUIZ_STATS_UNCLEAR_REPLY
    assert state_store.get(999)["flow"] == "pending_quiz_stats_query"


def test_handle_quiz_stats_query_step_clear_but_exam_type_hallucinated_treated_as_unclear(fake_db):
    _seed_answer(fake_db, exam_type="toeic")
    state_store = ConversationStateStore()
    commands.start_quiz_stats_query(fake_db, state_store, 999, 1)

    llm_client = _FakeLLMClient(
        "STATUS: CLEAR\nEXAM_TYPE: ielts\nSCOPE: DAILY\nPERIOD_START: 2026-08-01\nPERIOD_END: 2026-08-07\nCOMPARE: NO"
    )
    reply = commands.handle_quiz_stats_query_step(fake_db, llm_client, state_store, 999, "ielts 上週成效")

    assert reply == commands._QUIZ_STATS_UNCLEAR_REPLY


def test_handle_quiz_stats_query_step_accumulates_history_across_turns(fake_db):
    _seed_answer(fake_db)
    state_store = ConversationStateStore()
    commands.start_quiz_stats_query(fake_db, state_store, 999, 1)

    llm_client = _FakeLLMClient("STATUS: NEED_PERIOD", "STATUS: NEED_PERIOD")
    commands.handle_quiz_stats_query_step(fake_db, llm_client, state_store, 999, "toeic 小考成效")
    commands.handle_quiz_stats_query_step(fake_db, llm_client, state_store, 999, "上週好了")

    assert "toeic 小考成效" in llm_client.prompts[-1]
    assert "上週好了" in llm_client.prompts[-1]


# --- handle_quiz_stats_query_step：CLEAR，日常小考 ---


def test_handle_quiz_stats_query_step_clear_daily_returns_summary(fake_db):
    _seed_answer(fake_db, answered_on=date(2026, 8, 3), is_correct=True)
    _seed_answer(fake_db, answered_on=date(2026, 8, 3), is_correct=False)
    state_store = ConversationStateStore()
    commands.start_quiz_stats_query(fake_db, state_store, 999, 1)

    llm_client = _FakeLLMClient(
        "STATUS: CLEAR\nEXAM_TYPE: toeic\nSCOPE: DAILY\nPERIOD_START: 2026-08-01\n"
        "PERIOD_END: 2026-08-07\nCOMPARE: NO"
    )
    reply = commands.handle_quiz_stats_query_step(fake_db, llm_client, state_store, 999, "上週答對幾題")

    assert "toeic" in reply
    assert "測驗 2 題" in reply
    assert "答對 1 題" in reply
    assert state_store.get(999) is None


def test_handle_quiz_stats_query_step_clear_daily_with_compare(fake_db):
    _seed_answer(fake_db, answered_on=date(2026, 8, 3), is_correct=True)
    _seed_answer(fake_db, answered_on=date(2026, 7, 27), is_correct=False)
    state_store = ConversationStateStore()
    commands.start_quiz_stats_query(fake_db, state_store, 999, 1)

    llm_client = _FakeLLMClient(
        "STATUS: CLEAR\nEXAM_TYPE: toeic\nSCOPE: DAILY\nPERIOD_START: 2026-08-01\n"
        "PERIOD_END: 2026-08-07\nCOMPARE: YES\nCOMPARE_START: 2026-07-25\nCOMPARE_END: 2026-07-31"
    )
    reply = commands.handle_quiz_stats_query_step(fake_db, llm_client, state_store, 999, "這週跟上週比")

    assert "對照" in reply
    assert state_store.get(999) is None


# --- handle_quiz_stats_query_step：CLEAR，正式測驗 ---


def test_handle_quiz_stats_query_step_clear_formal_returns_summary(fake_db):
    _seed_score(fake_db, exam_date=date(2026, 8, 5), score="900")
    state_store = ConversationStateStore()
    commands.start_quiz_stats_query(fake_db, state_store, 999, 1)

    llm_client = _FakeLLMClient(
        "STATUS: CLEAR\nEXAM_TYPE: toeic\nSCOPE: FORMAL\nPERIOD_START: 2026-08-01\n"
        "PERIOD_END: 2026-08-31\nCOMPARE: NO"
    )
    reply = commands.handle_quiz_stats_query_step(fake_db, llm_client, state_store, 999, "這個月正式考幾分")

    assert "900" in reply
    assert state_store.get(999) is None
