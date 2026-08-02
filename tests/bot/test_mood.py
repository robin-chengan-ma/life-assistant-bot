"""src/bot/mood.py 的單元測試（對應 robinson SPEC.md FR-49、FR-50，Step 1.8）。"""
from src.bot import mood


def test_format_category_prompt_lists_all_six_categories_in_order():
    text = mood.format_category_prompt()

    assert "1. 生氣/焦慮" in text
    assert "6. 高興/興奮" in text


def test_resolve_category_accepts_valid_index():
    assert mood.resolve_category("6") == "happy_excited"
    assert mood.resolve_category("1") == "angry_anxious"


def test_resolve_category_rejects_out_of_range_index():
    assert mood.resolve_category("0") is None
    assert mood.resolve_category("7") is None


def test_resolve_category_accepts_exact_label_text():
    assert mood.resolve_category("高興/興奮") == "happy_excited"
    assert mood.resolve_category(" 平靜/放鬆 ") == "calm_relaxed"


def test_resolve_category_rejects_unrecognized_text():
    assert mood.resolve_category("很開心") is None


def test_category_label_returns_chinese_label():
    assert mood.category_label("happy_excited") == "高興/興奮"


def test_create_mood_journal_inserts_row_with_null_achievement_note(fake_db):
    journal_id = mood.create_mood_journal(fake_db, user_id=1, mood_category="happy_excited", content="今天很棒")

    row = fake_db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True)
    assert row["user_id"] == 1
    assert row["mood_category"] == "happy_excited"
    assert row["content"] == "今天很棒"
    assert row["achievement_note"] is None


def test_set_achievement_note_updates_row(fake_db):
    journal_id = mood.create_mood_journal(fake_db, 1, "happy_excited", "今天很棒")

    mood.set_achievement_note(fake_db, journal_id, "完成了一份報告")

    row = fake_db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True)
    assert row["achievement_note"] == "完成了一份報告"
