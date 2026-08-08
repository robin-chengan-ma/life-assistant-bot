"""src/bot/friend_chat.py 的單元測試（對應 robinson SPEC.md FR-51、FR-52，ADR-22，Step 3.5）。"""
from datetime import date, datetime, timedelta, timezone

from src.bot import body, finance, friend_chat, mood
from src.bot import todo as todo_module

_TODAY = date(2026, 8, 8)


def _due_at(days_from_today: int, hour: int = 12) -> datetime:
    d = _TODAY + timedelta(days=days_from_today)
    return datetime(d.year, d.month, d.day, hour, tzinfo=timezone.utc)


# --- _mood_provider（透過 gather_recent_context 間接測試也可以，這裡直接測 provider 本身） ---


def test_mood_provider_builds_emoji_sequence_and_positive_trend(fake_db):
    mood.create_mood_journal(fake_db, 1, "happy_excited", "今天很開心", _TODAY)
    mood.create_mood_journal(fake_db, 1, "calm_relaxed", "還不錯", _TODAY - timedelta(days=1))

    summary = friend_chat._mood_provider(fake_db, 1, _TODAY)

    assert summary is not None
    assert "😄" in summary and "😌" in summary
    assert "整體偏正向" in summary
    assert "2 筆" in summary


def test_mood_provider_negative_trend(fake_db):
    mood.create_mood_journal(fake_db, 1, "sad_down", "不太好", _TODAY)
    mood.create_mood_journal(fake_db, 1, "angry_anxious", "很煩", _TODAY - timedelta(days=1))

    summary = friend_chat._mood_provider(fake_db, 1, _TODAY)

    assert "整體偏低落" in summary


def test_mood_provider_neutral_trend_when_balanced(fake_db):
    mood.create_mood_journal(fake_db, 1, "happy_excited", "開心", _TODAY)
    mood.create_mood_journal(fake_db, 1, "sad_down", "難過", _TODAY - timedelta(days=1))

    summary = friend_chat._mood_provider(fake_db, 1, _TODAY)

    assert "情緒起伏不定" in summary


def test_mood_provider_no_data_returns_none(fake_db):
    assert friend_chat._mood_provider(fake_db, 1, _TODAY) is None


def test_mood_provider_excludes_entries_outside_window(fake_db):
    old_date = _TODAY - timedelta(days=friend_chat.LOOKBACK_DAYS)
    mood.create_mood_journal(fake_db, 1, "happy_excited", "很久以前", old_date)

    assert friend_chat._mood_provider(fake_db, 1, _TODAY) is None


def test_mood_provider_only_counts_this_user(fake_db):
    mood.create_mood_journal(fake_db, 1, "happy_excited", "我的", _TODAY)
    mood.create_mood_journal(fake_db, 2, "sad_down", "別人的", _TODAY)

    summary = friend_chat._mood_provider(fake_db, 1, _TODAY)

    assert "1 筆" in summary


# --- _todo_provider ---


def test_todo_provider_lists_upcoming_within_window(fake_db):
    todo_module.create_todo(fake_db, 1, "交報告", _due_at(2), remind_before_30min=False)
    todo_module.create_todo(fake_db, 1, "買菜", _due_at(6), remind_before_30min=False)

    summary = friend_chat._todo_provider(fake_db, 1, _TODAY)

    assert "2 件" in summary
    assert "交報告" in summary and "買菜" in summary


def test_todo_provider_excludes_items_beyond_window(fake_db):
    todo_module.create_todo(fake_db, 1, "太久以後", _due_at(friend_chat.LOOKBACK_DAYS), remind_before_30min=False)

    assert friend_chat._todo_provider(fake_db, 1, _TODAY) is None


def test_todo_provider_excludes_completed_todos(fake_db):
    todo_id = todo_module.create_todo(fake_db, 1, "已完成", _due_at(1), remind_before_30min=False)
    todo_module.mark_status(fake_db, todo_id, "completed")

    assert friend_chat._todo_provider(fake_db, 1, _TODAY) is None


def test_todo_provider_no_data_returns_none(fake_db):
    assert friend_chat._todo_provider(fake_db, 1, _TODAY) is None


# --- _body_provider ---


def test_body_provider_combines_weight_exercise_diet(fake_db):
    body.create_weight_log(fake_db, 1, 65.5, _TODAY)
    body.create_exercise_log(fake_db, 1, "跑步", 30, None, 250.0, _TODAY)
    body.create_diet_log(fake_db, 1, "food", "雞胸肉便當", _TODAY)

    summary = friend_chat._body_provider(fake_db, 1, _TODAY)

    assert "體重紀錄 1 筆" in summary
    assert "65.5 公斤" in summary
    assert "運動紀錄 1 筆" in summary
    assert "30 分鐘" in summary
    assert "飲食/飲水紀錄 1 筆" in summary


def test_body_provider_no_data_returns_none(fake_db):
    assert friend_chat._body_provider(fake_db, 1, _TODAY) is None


def test_body_provider_only_weight_still_returns_summary(fake_db):
    body.create_weight_log(fake_db, 1, 70.0, _TODAY)

    summary = friend_chat._body_provider(fake_db, 1, _TODAY)

    assert "體重紀錄 1 筆" in summary
    assert "運動" not in summary
    assert "飲食" not in summary


def test_body_provider_excludes_entries_outside_window(fake_db):
    old_date = _TODAY - timedelta(days=friend_chat.LOOKBACK_DAYS)
    body.create_weight_log(fake_db, 1, 70.0, old_date)

    assert friend_chat._body_provider(fake_db, 1, _TODAY) is None


# --- _budget_provider ---


def test_budget_provider_sums_expense_and_income(fake_db):
    finance.create_transaction(fake_db, 1, "expense", "餐飲", 150.0, None, _TODAY)
    finance.create_transaction(fake_db, 1, "income", "薪水", 50000.0, None, _TODAY)

    summary = friend_chat._budget_provider(fake_db, 1, _TODAY)

    assert "2 筆" in summary
    assert "150 元" in summary
    assert "50000 元" in summary


def test_budget_provider_expense_only_no_income_phrase(fake_db):
    finance.create_transaction(fake_db, 1, "expense", "餐飲", 100.0, None, _TODAY)

    summary = friend_chat._budget_provider(fake_db, 1, _TODAY)

    assert "收入" not in summary


def test_budget_provider_no_data_returns_none(fake_db):
    assert friend_chat._budget_provider(fake_db, 1, _TODAY) is None


# --- _certificate_provider ---


def _seed_answer(fake_db, **overrides):
    row = {
        "user_id": 1, "certificate_question_id": 1, "vocab_question_id": None,
        "exam_type": "toeic", "question_type": "write", "is_correct": True,
        "answered_on": _TODAY, "assignment_id": None,
    }
    row.update(overrides)
    fake_db.insert("answer_logs", row)


def test_certificate_provider_no_exam_types_returns_none(fake_db):
    assert friend_chat._certificate_provider(fake_db, 1, _TODAY) is None


def test_certificate_provider_summarizes_accuracy(fake_db):
    _seed_answer(fake_db, is_correct=True)
    _seed_answer(fake_db, is_correct=False)

    summary = friend_chat._certificate_provider(fake_db, 1, _TODAY)

    assert "toeic" in summary
    assert "2 題" in summary
    assert "50%" in summary


def test_certificate_provider_known_type_but_no_answers_in_window_returns_none(fake_db):
    old_date = _TODAY - timedelta(days=friend_chat.LOOKBACK_DAYS)
    _seed_answer(fake_db, answered_on=old_date)

    assert friend_chat._certificate_provider(fake_db, 1, _TODAY) is None


# --- gather_recent_context ---


def test_gather_recent_context_skips_disabled_toggle(fake_db):
    mood.create_mood_journal(fake_db, 1, "happy_excited", "開心", _TODAY)
    fake_db.insert("feature_toggles", {"user_id": 1, "feature_key": "mood_journal", "is_enabled": False})

    context = friend_chat.gather_recent_context(fake_db, 1, _TODAY)

    assert "mood_journal" not in context


def test_gather_recent_context_skips_modules_without_data(fake_db):
    context = friend_chat.gather_recent_context(fake_db, 1, _TODAY)

    assert context == {}


def test_gather_recent_context_includes_multiple_enabled_modules_with_data(fake_db):
    mood.create_mood_journal(fake_db, 1, "happy_excited", "開心", _TODAY)
    finance.create_transaction(fake_db, 1, "expense", "餐飲", 100.0, None, _TODAY)

    context = friend_chat.gather_recent_context(fake_db, 1, _TODAY)

    assert set(context.keys()) == {"mood_journal", "budget"}


def test_gather_recent_context_toggle_enabled_still_included(fake_db):
    mood.create_mood_journal(fake_db, 1, "happy_excited", "開心", _TODAY)
    fake_db.insert("feature_toggles", {"user_id": 1, "feature_key": "mood_journal", "is_enabled": True})

    context = friend_chat.gather_recent_context(fake_db, 1, _TODAY)

    assert "mood_journal" in context


# --- build_companion_prompt ---


def test_build_companion_prompt_includes_role_and_context(fake_db):
    prompt = friend_chat.build_companion_prompt("媽媽", {"mood_journal": "最近心情不錯 😄"})

    assert "媽媽" in prompt
    assert "心情小記" in prompt
    assert "最近心情不錯 😄" in prompt
    assert str(friend_chat.LOOKBACK_DAYS) in prompt


def test_build_companion_prompt_empty_context_uses_fallback_text(fake_db):
    prompt = friend_chat.build_companion_prompt("主任", {})

    assert "沒有任何功能模組的紀錄資料" in prompt
