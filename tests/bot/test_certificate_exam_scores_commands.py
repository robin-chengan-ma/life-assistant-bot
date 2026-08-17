"""src/bot/commands.py 正式成績記錄／查詢流程的單元測試（對應 robinson SPEC.md FR-30）。"""
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


def _seed_score(fake_db, **overrides):
    row = {"user_id": 1, "exam_type": "toeic", "exam_date": date(2026, 8, 1), "score": "850"}
    row.update(overrides)
    return fake_db.insert("exam_official_scores", row)


# --- start_log_exam_score / handle_exam_score_exam_type_step ---


def test_start_log_exam_score_no_candidates_asks_free_text(fake_db):
    state_store = ConversationStateStore()
    reply = commands.start_log_exam_score(fake_db, state_store, 999, 1)

    assert "例如" in reply
    assert state_store.get(999)["flow"] == "pending_exam_score_exam_type"
    assert state_store.get(999)["exam_type_options"] == []


def test_start_log_exam_score_lists_candidates(fake_db):
    _seed_score(fake_db, exam_type="gcp")
    state_store = ConversationStateStore()

    reply = commands.start_log_exam_score(fake_db, state_store, 999, 1)

    assert "1. gcp" in reply


def test_handle_exam_score_exam_type_step_by_index(fake_db):
    _seed_score(fake_db, exam_type="gcp")
    state_store = ConversationStateStore()
    commands.start_log_exam_score(fake_db, state_store, 999, 1)

    reply = commands.handle_exam_score_exam_type_step(state_store, 999, "1")

    assert "應考是什麼時候" in reply
    assert state_store.get(999)["exam_type"] == "gcp"
    assert state_store.get(999)["flow"] == "pending_exam_score_date"


def test_handle_exam_score_exam_type_step_free_text_lowercased(fake_db):
    state_store = ConversationStateStore()
    commands.start_log_exam_score(fake_db, state_store, 999, 1)

    commands.handle_exam_score_exam_type_step(state_store, 999, "TOEIC")

    assert state_store.get(999)["exam_type"] == "toeic"


def test_handle_exam_score_exam_type_step_empty_reprompts(fake_db):
    state_store = ConversationStateStore()
    commands.start_log_exam_score(fake_db, state_store, 999, 1)

    reply = commands.handle_exam_score_exam_type_step(state_store, 999, "   ")

    assert "沒看懂" in reply
    assert state_store.get(999)["flow"] == "pending_exam_score_exam_type"


# --- handle_exam_score_date_step ---


def test_handle_exam_score_date_step_clear_moves_to_value(fake_db):
    state_store = ConversationStateStore()
    commands.start_log_exam_score(fake_db, state_store, 999, 1)
    commands.handle_exam_score_exam_type_step(state_store, 999, "toeic")

    llm_client = _FakeLLMClient("STATUS: CLEAR\nDATE: 2026-08-01")
    reply = commands.handle_exam_score_date_step(fake_db, llm_client, state_store, 999, "8/1")

    assert "成績或結果" in reply
    assert state_store.get(999)["exam_date"] == date(2026, 8, 1)
    assert state_store.get(999)["flow"] == "pending_exam_score_value"


def test_handle_exam_score_date_step_clear_but_date_unparseable_reprompts(fake_db):
    state_store = ConversationStateStore()
    commands.start_log_exam_score(fake_db, state_store, 999, 1)
    commands.handle_exam_score_exam_type_step(state_store, 999, "toeic")

    llm_client = _FakeLLMClient("STATUS: CLEAR\nDATE: 不是日期格式")
    reply = commands.handle_exam_score_date_step(fake_db, llm_client, state_store, 999, "怪怪的輸入")

    assert reply == commands._CERTIFICATE_DATE_UNCLEAR_REPLY
    assert state_store.get(999)["flow"] == "pending_exam_score_date"


def test_handle_exam_score_date_step_unclear_reprompts(fake_db):
    state_store = ConversationStateStore()
    commands.start_log_exam_score(fake_db, state_store, 999, 1)
    commands.handle_exam_score_exam_type_step(state_store, 999, "toeic")

    llm_client = _FakeLLMClient("STATUS: UNCLEAR")
    reply = commands.handle_exam_score_date_step(fake_db, llm_client, state_store, 999, "改天")

    assert "不太確定" in reply
    assert state_store.get(999)["flow"] == "pending_exam_score_date"


# --- handle_exam_score_value_step ---


def test_handle_exam_score_value_step_records_and_confirms(fake_db):
    state_store = ConversationStateStore()
    commands.start_log_exam_score(fake_db, state_store, 999, 1)
    commands.handle_exam_score_exam_type_step(state_store, 999, "toeic")
    llm_client = _FakeLLMClient("STATUS: CLEAR\nDATE: 2026-08-01")
    commands.handle_exam_score_date_step(fake_db, llm_client, state_store, 999, "8/1")

    reply = commands.handle_exam_score_value_step(fake_db, state_store, 999, "850 分")

    assert "toeic" in reply
    assert "2026/8/1" in reply
    assert "850 分" in reply
    assert state_store.get(999) is None
    rows = fake_db.select("exam_official_scores")
    assert len(rows) == 1
    assert rows[0]["score"] == "850 分"
    assert rows[0]["user_id"] == 1


def test_handle_exam_score_value_step_appends_achievement_message(fake_db):
    """2026-08-17 補做（Robin 要求不得漏做）：輸入實際分數若達成目標分數，回覆要多附一句恭喜。"""
    from src.bot import certificate_goals

    certificate_goals.set_goal(fake_db, 1, "toeic", date(2026, 12, 1), "800")
    state_store = ConversationStateStore()
    commands.start_log_exam_score(fake_db, state_store, 999, 1)
    commands.handle_exam_score_exam_type_step(state_store, 999, "toeic")
    llm_client = _FakeLLMClient("STATUS: CLEAR\nDATE: 2026-08-01")
    commands.handle_exam_score_date_step(fake_db, llm_client, state_store, 999, "8/1")

    reply = commands.handle_exam_score_value_step(fake_db, state_store, 999, "850")

    assert "恭喜" in reply
    assert "800" in reply


def test_handle_exam_score_value_step_below_target_no_achievement_message(fake_db):
    from src.bot import certificate_goals

    certificate_goals.set_goal(fake_db, 1, "toeic", date(2026, 12, 1), "800")
    state_store = ConversationStateStore()
    commands.start_log_exam_score(fake_db, state_store, 999, 1)
    commands.handle_exam_score_exam_type_step(state_store, 999, "toeic")
    llm_client = _FakeLLMClient("STATUS: CLEAR\nDATE: 2026-08-01")
    commands.handle_exam_score_date_step(fake_db, llm_client, state_store, 999, "8/1")

    reply = commands.handle_exam_score_value_step(fake_db, state_store, 999, "700")

    assert "恭喜" not in reply


def test_handle_exam_score_value_step_empty_reprompts(fake_db):
    state_store = ConversationStateStore()
    commands.start_log_exam_score(fake_db, state_store, 999, 1)
    commands.handle_exam_score_exam_type_step(state_store, 999, "toeic")
    llm_client = _FakeLLMClient("STATUS: CLEAR\nDATE: 2026-08-01")
    commands.handle_exam_score_date_step(fake_db, llm_client, state_store, 999, "8/1")

    reply = commands.handle_exam_score_value_step(fake_db, state_store, 999, "   ")

    assert "沒看懂" in reply
    assert state_store.get(999)["flow"] == "pending_exam_score_value"
    assert fake_db.select("exam_official_scores") == []


# --- handle_my_exam_scores ---


def test_handle_my_exam_scores_empty(fake_db):
    reply = commands.handle_my_exam_scores(fake_db, 1)
    assert "還沒有" in reply


def test_handle_my_exam_scores_lists_rows(fake_db):
    _seed_score(fake_db, exam_type="toeic", exam_date=date(2026, 8, 1), score="850")
    _seed_score(fake_db, exam_type="gcp", exam_date=date(2026, 5, 1), score="通過")

    reply = commands.handle_my_exam_scores(fake_db, 1)

    assert "toeic" in reply
    assert "850" in reply
    assert "gcp" in reply
    assert "通過" in reply
