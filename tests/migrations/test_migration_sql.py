from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "src" / "migrations"


def test_0084_does_not_add_note_column_created_by_0025():
    original_sql = (_MIGRATIONS_DIR / "0025_create_exercise_logs_table.sql").read_text(encoding="utf-8")
    sql = (_MIGRATIONS_DIR / "0084_redesign_exercise_categories.sql").read_text(encoding="utf-8")

    assert "note TEXT" in original_sql
    assert "ADD COLUMN note" not in sql
    assert "ADD COLUMN category_id" in sql
