from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.services.app_records import (
    AppRecordService,
    DuplicateRecordError,
    HistoricalRecordError,
    RecordNotFoundError,
    RecordValidationError,
)

TAIPEI = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 8, 11, 12, 0, tzinfo=TAIPEI)


class FakeDatabase:
    def __init__(self, rows=None):
        self.rows = rows or {}
        self.inserted = []
        self.updated = []
        self.deleted = []

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        rows = list(self.rows.get(table, []))
        if where and "id = %s AND user_id = %s" in where:
            record_id, user_id = params
            rows = [row for row in rows if row["id"] == record_id and row["user_id"] == user_id]
        elif where and "created_at >= %s" in where:
            user_id, cutoff = params
            rows = [row for row in rows if row["user_id"] == user_id and row["created_at"] >= cutoff]
        elif where and "entry_date = %s" in where:
            user_id, entry_date, *entry_type = params
            rows = [row for row in rows if row["user_id"] == user_id and row["entry_date"] == entry_date]
            if entry_type:
                rows = [row for row in rows if row.get("entry_type") == entry_type[0]]
        elif where == "id = %s":
            (record_id,) = params
            rows = [row for row in rows if row["id"] == record_id]
        elif where == "normalized_name = %s":
            (normalized,) = params
            rows = [row for row in rows if row.get("normalized_name") == normalized]
        return rows[0] if fetch_one and rows else None if fetch_one else rows

    def insert(self, table, data, returning="id"):
        self.inserted.append((table, data))
        return 99

    def update(self, table, data, where, params):
        self.updated.append((table, data, params))
        return 1

    def delete(self, table, where, params):
        self.deleted.append((table, params))
        return 1


def test_finance_create_rounds_half_up_and_uses_today():
    db = FakeDatabase()

    result = AppRecordService(db, now=NOW).create(
        "finance", 1, {"type": "expense", "category": "餐飲", "amount": 520.5}
    )

    assert result["id"] == 99
    assert db.inserted[0][1]["amount"] == 521
    assert db.inserted[0][1]["transaction_date"] == date(2026, 8, 11)


def test_duplicate_within_ten_minutes_requires_explicit_override():
    db = FakeDatabase({"transactions": [{"id": 1, "user_id": 1, "type": "expense", "category": "餐飲",
                                           "amount": 520, "created_at": NOW - timedelta(minutes=5)}]})
    service = AppRecordService(db, now=NOW)

    with pytest.raises(DuplicateRecordError):
        service.create("finance", 1, {"type": "expense", "category": "餐飲", "amount": 520})

    service.create("finance", 1, {"type": "expense", "category": "餐飲", "amount": 520}, allow_duplicate=True)
    assert len(db.inserted) == 1


def test_historical_non_todo_cannot_be_updated_or_deleted():
    db = FakeDatabase({"mood_journals": [{"id": 7, "user_id": 1, "entry_date": date(2026, 8, 10)}]})
    service = AppRecordService(db, now=NOW)

    with pytest.raises(HistoricalRecordError):
        service.update("mood", 7, 1, {"mood_category": "neutral", "content": ""})
    with pytest.raises(HistoricalRecordError):
        service.delete("mood", 7, 1)


def test_todo_can_edit_historical_date_but_cannot_access_another_user_record():
    old_due = datetime(2026, 7, 1, 9, 0, tzinfo=TAIPEI)
    db = FakeDatabase({"todos": [{"id": 3, "user_id": 1, "due_at": old_due, "created_at": NOW - timedelta(days=1)}]})
    service = AppRecordService(db, now=NOW)

    service.update("todo", 3, 1, {"content": "看醫生", "due_at": "2026-09-01T10:00:00+08:00", "status": "completed"})
    assert db.updated[0][1]["content"] == "看醫生"
    assert db.updated[0][1]["status"] == "completed"
    with pytest.raises(RecordNotFoundError):
        service.delete("todo", 3, 2)


def test_todo_date_range_stores_start_and_end_with_shared_time():
    db = FakeDatabase()

    AppRecordService(db, now=NOW).create(
        "todo",
        1,
        {
            "content": "家族旅遊",
            "start_at": "2026-08-20T09:00:00+08:00",
            "due_at": "2026-08-23T09:00:00+08:00",
            "status": "pending",
        },
    )

    assert db.inserted[0][1]["start_at"].date() == date(2026, 8, 20)
    assert db.inserted[0][1]["due_at"].date() == date(2026, 8, 23)


def test_update_duplicate_detection_excludes_the_record_being_edited():
    rows = [
        {"id": 1, "user_id": 1, "type": "expense", "category": "餐飲", "amount": 100,
         "transaction_date": date(2026, 8, 11), "created_at": NOW - timedelta(minutes=2)},
    ]
    service = AppRecordService(FakeDatabase({"transactions": rows}), now=NOW)

    service.update("finance", 1, 1, {"type": "expense", "category": "餐飲", "amount": 100})

    rows.append({"id": 2, "user_id": 1, "type": "expense", "category": "餐飲", "amount": 100,
                 "transaction_date": date(2026, 8, 11), "created_at": NOW - timedelta(minutes=1)})
    with pytest.raises(DuplicateRecordError):
        service.update("finance", 1, 1, {"type": "expense", "category": "餐飲", "amount": 100})


@pytest.mark.parametrize("kind,table,payload", [
    ("diet", "diet_logs", {"description": "雞胸肉"}),
    ("weight", "body_weight_logs", {"weight_kg": 70}),
    ("mood", "mood_journals", {"mood_category": "neutral", "content": ""}),
])
def test_single_daily_records_must_update_latest_instead_of_creating(kind, table, payload):
    row = {"id": 8, "user_id": 1, "entry_date": date(2026, 8, 11)}
    if kind == "diet":
        row["entry_type"] = "food"
    db = FakeDatabase({table: [row]})

    with pytest.raises(RecordValidationError, match="今日已有紀錄"):
        AppRecordService(db, now=NOW).create(kind, 1, payload)


def test_diet_accepts_reviewed_nutrition_without_calling_llm_again():
    class FailingLlm:
        def generate_text(self, prompt):
            raise AssertionError("不應再次呼叫 Gemini")

    db = FakeDatabase()
    AppRecordService(db, llm_client=FailingLlm(), now=NOW).create(
        "diet",
        1,
        {
            "description": "雞胸肉便當",
            "nutrition": {"estimated_calories": 520, "protein_g": 36.2, "carbs_g": 58, "fat_g": 14},
        },
    )

    assert db.inserted[0][1]["estimated_calories"] == 520.0
    assert db.inserted[0][1]["protein_g"] == 36.2


def test_diet_stores_water_as_separate_record_without_sending_it_to_nutrition():
    db = FakeDatabase()

    AppRecordService(db, now=NOW).create(
        "diet",
        1,
        {"description": "雞胸肉便當", "water_ml": 1200},
    )

    assert db.inserted[0][1]["entry_type"] == "food"
    assert db.inserted[0][1]["water_ml"] is None
    assert db.inserted[1][1] == {
        "user_id": 1,
        "entry_type": "water",
        "description": "飲水",
        "water_ml": 1200,
        "nutrition_source": "manual",
        "estimated_calories": None,
        "protein_g": None,
        "carbs_g": None,
        "fat_g": None,
        "entry_date": date(2026, 8, 11),
    }


def test_diet_update_updates_existing_water_record():
    food = {"id": 8, "user_id": 1, "entry_type": "food", "description": "早餐", "entry_date": date(2026, 8, 11), "created_at": NOW}
    water = {"id": 9, "user_id": 1, "entry_type": "water", "description": "飲水", "water_ml": 500, "entry_date": date(2026, 8, 11), "created_at": NOW}
    db = FakeDatabase({"diet_logs": [food, water]})

    AppRecordService(db, now=NOW).update("diet", 8, 1, {"description": "早餐", "water_ml": 800})

    assert any(params == (9, 1) and data["water_ml"] == 800 for table, data, params in db.updated if table == "diet_logs")


def test_diet_rejects_invalid_reviewed_nutrition():
    with pytest.raises(RecordValidationError, match="營養估算"):
        AppRecordService(FakeDatabase(), now=NOW).create(
            "diet", 1, {"description": "雞胸肉", "nutrition": {"estimated_calories": -1}}
        )


def test_diet_manual_nutrition_rounds_values_and_records_source_without_llm():
    class FailingLlm:
        def generate_text(self, prompt):
            raise AssertionError("人工輸入不應呼叫 Gemini")

    db = FakeDatabase()
    AppRecordService(db, llm_client=FailingLlm(), now=NOW).create(
        "diet",
        1,
        {
            "description": "雞胸肉便當",
            "nutrition_source": "manual",
            "nutrition": {
                "estimated_calories": 520.5,
                "protein_g": 36.26,
                "carbs_g": 0,
                "fat_g": 14.04,
            },
        },
    )

    saved = db.inserted[0][1]
    assert saved["nutrition_source"] == "manual"
    assert saved["estimated_calories"] == 521
    assert saved["protein_g"] == 36.3
    assert saved["carbs_g"] == 0.0
    assert saved["fat_g"] == 14.0


@pytest.mark.parametrize(
    "nutrition",
    [
        {"estimated_calories": 0, "protein_g": 1, "carbs_g": 1, "fat_g": 1},
        {"estimated_calories": 10001, "protein_g": 1, "carbs_g": 1, "fat_g": 1},
        {"estimated_calories": 500, "protein_g": 1000.1, "carbs_g": 1, "fat_g": 1},
        {"estimated_calories": 500, "protein_g": 1, "carbs_g": None, "fat_g": 1},
    ],
)
def test_diet_manual_nutrition_enforces_required_ranges(nutrition):
    with pytest.raises(RecordValidationError):
        AppRecordService(FakeDatabase(), now=NOW).create(
            "diet",
            1,
            {"description": "便當", "nutrition_source": "manual", "nutrition": nutrition},
        )


@pytest.mark.parametrize("water_ml", [0, 10001])
def test_diet_water_enforces_confirmed_range(water_ml):
    with pytest.raises(RecordValidationError, match="飲水量"):
        AppRecordService(FakeDatabase(), now=NOW).create(
            "diet", 1, {"description": "便當", "water_ml": water_ml}
        )


def test_exercise_manual_calories_rounds_and_does_not_call_llm():
    class FailingLlm:
        def generate_text(self, prompt):
            raise AssertionError("人工輸入不應呼叫 Gemini")

    db = FakeDatabase({"exercise_categories": [{"id": 1, "name": "跑步", "normalized_name": "跑步"}]})
    AppRecordService(db, llm_client=FailingLlm(), now=NOW).create(
        "exercise",
        1,
        {"category_id": 1, "duration_minutes": 30, "use_ai_calorie": False, "calories": 320.5},
    )

    saved = db.inserted[0][1]
    assert saved["activity"] == "跑步"
    assert saved["calorie_source"] == "manual"
    assert saved["estimated_calories"] == 321
    assert saved["duration_minutes"] == 30


@pytest.mark.parametrize("calories", [0, 5001])
def test_exercise_manual_calories_enforces_range(calories):
    db = FakeDatabase({"exercise_categories": [{"id": 1, "name": "跑步", "normalized_name": "跑步"}]})
    with pytest.raises(RecordValidationError, match="消耗熱量"):
        AppRecordService(db, now=NOW).create(
            "exercise",
            1,
            {"category_id": 1, "duration_minutes": 30, "use_ai_calorie": False, "calories": calories},
        )


def test_exercise_ai_calorie_passes_note_and_custom_category_merges(monkeypatch):
    captured = {}

    def fake_estimate(_llm, activity, duration, heart_rate, note=None):
        captured.update(activity=activity, duration=duration, heart_rate=heart_rate, note=note)
        return 280

    monkeypatch.setattr("src.services.app_records.body.estimate_exercise_calories", fake_estimate)

    def fake_find_or_create(_db, _llm, name):
        captured["custom_name"] = name
        return {"id": 42, "name": name, "normalized_name": name}

    monkeypatch.setattr("src.services.app_records.body.find_or_create_exercise_category", fake_find_or_create)

    db = FakeDatabase()
    AppRecordService(db, llm_client=object(), now=NOW).create(
        "exercise",
        1,
        {
            "custom_category": "重量訓練",
            "duration_minutes": 45,
            "note": "深蹲 60 公斤 5 組，每組 8 下",
        },
    )

    assert captured["custom_name"] == "重量訓練"
    assert captured["note"] == "深蹲 60 公斤 5 組，每組 8 下"
    assert db.inserted[0][1]["category_id"] == 42
    assert db.inserted[0][1]["activity"] == "重量訓練"
    assert db.inserted[0][1]["calorie_source"] == "ai"
    assert db.inserted[0][1]["estimated_calories"] == 280


def test_exercise_requires_category_selection():
    with pytest.raises(RecordValidationError, match="運動類別"):
        AppRecordService(FakeDatabase(), now=NOW).create(
            "exercise", 1, {"duration_minutes": 30}
        )


def test_weight_accepts_optional_waist_and_preserves_existing_waist_when_cleared():
    row = {"id": 5, "user_id": 1, "weight_kg": 70, "waist_cm": 82.5,
           "entry_date": date(2026, 8, 11), "created_at": NOW}
    db = FakeDatabase({"body_weight_logs": [row]})
    service = AppRecordService(db, now=NOW)

    service.update("weight", 5, 1, {"weight_kg": 69.8, "waist_cm": None})

    assert db.updated[0][1]["weight_kg"] == 69.8
    assert "waist_cm" not in db.updated[0][1]


def test_weight_updates_user_height_without_duplicating_height_in_daily_log():
    db = FakeDatabase({"users": [{"id": 1, "height_cm": 175}]})

    AppRecordService(db, now=NOW).create(
        "weight",
        1,
        {"height_cm": 176.2, "weight_kg": 70, "waist_cm": 82},
    )

    assert db.updated[0] == ("users", {"height_cm": 176.2}, (1,))
    assert "height_cm" not in db.inserted[0][1]
    assert db.inserted[0][1]["waist_cm"] == 82.0


def test_only_latest_legacy_daily_record_can_be_changed():
    rows = [
        {"id": 5, "user_id": 1, "weight_kg": 70, "entry_date": date(2026, 8, 11), "created_at": NOW},
        {"id": 6, "user_id": 1, "weight_kg": 72, "entry_date": date(2026, 8, 11), "created_at": NOW},
    ]
    service = AppRecordService(FakeDatabase({"body_weight_logs": rows}), now=NOW)

    with pytest.raises(HistoricalRecordError, match="最新一筆"):
        service.update("weight", 5, 1, {"weight_kg": 69})
    service.update("weight", 6, 1, {"weight_kg": 71})


@pytest.mark.parametrize("waist_cm", [49.9, 150.1, "80"])
def test_weight_rejects_invalid_waist(waist_cm):
    with pytest.raises(RecordValidationError, match="腰圍"):
        AppRecordService(FakeDatabase(), now=NOW).create(
            "weight", 1, {"weight_kg": 70, "waist_cm": waist_cm}
        )


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("finance", {"type": "expense", "category": "薪資", "amount": 100}),
        ("exercise", {"category_id": None, "custom_category": "", "duration_minutes": 30}),
        ("weight", {"weight_kg": 151}),
        ("mood", {"mood_category": "unknown", "content": ""}),
    ],
)
def test_invalid_record_fields_are_rejected(kind, payload):
    with pytest.raises(RecordValidationError):
        AppRecordService(FakeDatabase(), now=NOW).create(kind, 1, payload)
