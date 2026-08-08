"""src/bot/certificate_exam_scores.py 的單元測試（對應 robinson SPEC.md FR-30、ADR-19 決策 7）。"""
from datetime import date

from src.bot import certificate_exam_scores


def _seed_score(fake_db, **overrides):
    row = {"user_id": 1, "exam_type": "toeic", "exam_date": date(2026, 8, 1), "score": "850"}
    row.update(overrides)
    return fake_db.insert("exam_official_scores", row)


# --- record_score ---


def test_record_score_inserts_row(fake_db):
    row_id = certificate_exam_scores.record_score(fake_db, 1, "toeic", date(2026, 8, 1), "850")

    rows = fake_db.select("exam_official_scores")
    assert len(rows) == 1
    assert rows[0]["id"] == row_id
    assert rows[0]["exam_type"] == "toeic"
    assert rows[0]["exam_date"] == date(2026, 8, 1)
    assert rows[0]["score"] == "850"


def test_record_score_allows_multiple_entries_for_same_exam_type(fake_db):
    certificate_exam_scores.record_score(fake_db, 1, "toeic", date(2026, 3, 1), "700")
    certificate_exam_scores.record_score(fake_db, 1, "toeic", date(2026, 8, 1), "850")

    rows = fake_db.select("exam_official_scores")
    assert len(rows) == 2


# --- list_scores ---


def test_list_scores_filters_by_exam_type_and_sorts_desc(fake_db):
    _seed_score(fake_db, exam_type="toeic", exam_date=date(2026, 3, 1), score="700")
    _seed_score(fake_db, exam_type="toeic", exam_date=date(2026, 8, 1), score="850")
    _seed_score(fake_db, exam_type="gcp", exam_date=date(2026, 5, 1), score="通過")

    rows = certificate_exam_scores.list_scores(fake_db, 1, "toeic")

    assert [row["score"] for row in rows] == ["850", "700"]


def test_list_scores_without_exam_type_returns_all_sorted(fake_db):
    _seed_score(fake_db, exam_type="toeic", exam_date=date(2026, 8, 1), score="850")
    _seed_score(fake_db, exam_type="gcp", exam_date=date(2026, 5, 1), score="通過")

    rows = certificate_exam_scores.list_scores(fake_db, 1)

    assert len(rows) == 2


def test_list_scores_only_returns_this_user(fake_db):
    _seed_score(fake_db, user_id=1)
    _seed_score(fake_db, user_id=2)

    rows = certificate_exam_scores.list_scores(fake_db, 1)

    assert len(rows) == 1


def test_list_scores_empty_when_none(fake_db):
    assert certificate_exam_scores.list_scores(fake_db, 1, "toeic") == []


# --- distinct_exam_types ---


def test_distinct_exam_types_returns_sorted_unique(fake_db):
    _seed_score(fake_db, exam_type="toeic")
    _seed_score(fake_db, exam_type="gcp")
    _seed_score(fake_db, exam_type="toeic")

    assert certificate_exam_scores.distinct_exam_types(fake_db, 1) == ["gcp", "toeic"]


def test_distinct_exam_types_empty(fake_db):
    assert certificate_exam_scores.distinct_exam_types(fake_db, 1) == []


# --- format_scores_summary ---


def test_format_scores_summary_empty_with_exam_type():
    text = certificate_exam_scores.format_scores_summary("toeic", [])
    assert "toeic" in text
    assert "還沒有" in text


def test_format_scores_summary_empty_without_exam_type():
    text = certificate_exam_scores.format_scores_summary(None, [])
    assert "還沒有" in text


def test_format_scores_summary_lists_rows_with_exam_type():
    rows = [
        {"exam_type": "toeic", "exam_date": date(2026, 8, 1), "score": "850"},
        {"exam_type": "toeic", "exam_date": date(2026, 3, 1), "score": "700"},
    ]
    text = certificate_exam_scores.format_scores_summary("toeic", rows)
    assert "2026/8/1" in text
    assert "850" in text
    assert "2026/3/1" in text
    assert "700" in text


def test_format_scores_summary_lists_rows_without_exam_type_shows_type_prefix():
    rows = [{"exam_type": "gcp", "exam_date": date(2026, 5, 1), "score": "通過"}]
    text = certificate_exam_scores.format_scores_summary(None, rows)
    assert "gcp" in text
    assert "通過" in text
