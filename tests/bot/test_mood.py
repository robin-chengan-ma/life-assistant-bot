"""src/bot/mood.py 的單元測試（對應 robinson SPEC.md FR-49、FR-50，Step 1.8）。"""
from datetime import date, datetime, timezone

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
    journal_id = mood.create_mood_journal(
        fake_db, user_id=1, mood_category="happy_excited", content="今天很棒", entry_date=date(2026, 8, 2)
    )

    row = fake_db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True)
    assert row["user_id"] == 1
    assert row["mood_category"] == "happy_excited"
    assert row["content"] == "今天很棒"
    assert row["achievement_note"] is None
    assert row["entry_date"] == date(2026, 8, 2)


def test_set_achievement_note_updates_row(fake_db):
    journal_id = mood.create_mood_journal(fake_db, 1, "happy_excited", "今天很棒", date(2026, 8, 2))

    mood.set_achievement_note(fake_db, journal_id, "完成了一份報告")

    row = fake_db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True)
    assert row["achievement_note"] == "完成了一份報告"


def test_list_mood_journals_sorts_by_entry_date_descending(fake_db):
    old_id = mood.create_mood_journal(fake_db, 1, "sad_down", "難過的一天", date(2026, 7, 30))
    new_id = mood.create_mood_journal(fake_db, 1, "happy_excited", "開心的一天", date(2026, 8, 2))

    journals = mood.list_mood_journals(fake_db, 1)

    assert [row["id"] for row in journals] == [new_id, old_id]


def test_list_mood_journals_falls_back_to_created_at_when_entry_date_missing(fake_db):
    """新增 entry_date 欄位前的舊資料沒有這個欄位，讀取時要 fallback 用 created_at 的日期部分排序。"""
    legacy_id = fake_db.insert(
        "mood_journals",
        {
            "user_id": 1,
            "mood_category": "neutral",
            "content": "舊資料",
            "achievement_note": None,
            "entry_date": None,
            "created_at": datetime(2026, 7, 1, 3, 0, tzinfo=timezone.utc),  # 台灣時區 7/1 11:00
        },
    )
    new_id = mood.create_mood_journal(fake_db, 1, "happy_excited", "新資料", date(2026, 8, 2))

    journals = mood.list_mood_journals(fake_db, 1)

    assert [row["id"] for row in journals] == [new_id, legacy_id]


def test_list_mood_journals_limits_result_count(fake_db):
    for day in range(1, 6):
        mood.create_mood_journal(fake_db, 1, "neutral", f"第{day}天", date(2026, 8, day))

    journals = mood.list_mood_journals(fake_db, 1, limit=2)

    assert len(journals) == 2
    assert journals[0]["content"] == "第5天"


def test_format_mood_journal_list_empty():
    assert mood.format_mood_journal_list([]) == "目前還沒有心情小記紀錄喔！"


def test_format_mood_journal_list_shows_date_category_and_preview(fake_db):
    journal_id = mood.create_mood_journal(fake_db, 1, "happy_excited", "今天很棒", date(2026, 8, 2))
    journals = mood.list_mood_journals(fake_db, 1)

    text = mood.format_mood_journal_list(journals)

    assert "1. 2026/08/02 高興/興奮：今天很棒" in text
    assert journal_id


def test_format_mood_journal_list_truncates_long_content():
    long_content = "一" * 30
    journals = [{"id": 1, "entry_date": date(2026, 8, 2), "mood_category": "neutral", "content": long_content}]

    text = mood.format_mood_journal_list(journals)

    assert "一" * 20 + "…" in text
    assert long_content not in text


def test_update_mood_journal_changes_category_and_content(fake_db):
    journal_id = mood.create_mood_journal(fake_db, 1, "sad_down", "原本內容", date(2026, 8, 1))

    mood.update_mood_journal(fake_db, journal_id, "happy_excited", "改過的內容")

    row = fake_db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True)
    assert row["mood_category"] == "happy_excited"
    assert row["content"] == "改過的內容"
    assert row["entry_date"] == date(2026, 8, 1)  # entry_date 不受更新影響


def test_delete_mood_journal_removes_row(fake_db):
    journal_id = mood.create_mood_journal(fake_db, 1, "sad_down", "要刪除的內容", date(2026, 8, 1))

    mood.delete_mood_journal(fake_db, journal_id)

    row = fake_db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True)
    assert row is None
