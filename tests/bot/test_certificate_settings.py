from datetime import date

from src.bot import certificate_settings
from src.bot.state import ConversationStateStore


def _profile(fake_db, key="toeic", name="TOEIC", builtin=True):
    return fake_db.insert(
        "certificate_profiles",
        {
            "user_id": 1,
            "certificate_key": key,
            "display_name": name,
            "is_active": True,
            "is_builtin": builtin,
        },
    )


def test_menu_has_four_settings_entries():
    _, keyboard = certificate_settings.start_menu()
    callbacks = [row[0]["callback_data"] for row in keyboard["inline_keyboard"]]
    assert callbacks[:4] == [
        "certificate_settings:profiles",
        "certificate_settings:goals",
        "certificate_settings:daily",
        "certificate_settings:scores",
    ]


def test_custom_profile_requires_confirmation(fake_db):
    store = ConversationStateStore()
    certificate_settings.start_profile_add(store, 99, 1)
    reply, keyboard = certificate_settings.handle_profile_add_text(
        store, 99, " AWS SAA "
    )
    assert "確認" in reply
    assert fake_db.select("certificate_profiles") == []
    assert (
        keyboard["inline_keyboard"][0][0]["callback_data"]
        == "certificate_settings:profile:confirm_add"
    )
    certificate_settings.confirm_profile_add(fake_db, store, 99)
    assert fake_db.select("certificate_profiles")[0]["certificate_key"] == "aws saa"


def test_builtin_profile_cannot_be_disabled(fake_db):
    profile_id = _profile(fake_db)
    store = ConversationStateStore()
    reply, _ = certificate_settings.start_profile_toggle(
        fake_db, store, 99, 1, profile_id
    )
    assert "無法" in reply
    assert fake_db.select(
        "certificate_profiles", where="id = %s", params=(profile_id,), fetch_one=True
    )["is_active"]


def test_custom_profile_toggle_requires_confirmation(fake_db):
    profile_id = _profile(fake_db, key="aws", name="AWS", builtin=False)
    store = ConversationStateStore()

    reply, keyboard = certificate_settings.start_profile_toggle(
        fake_db, store, 99, 1, profile_id
    )

    assert "確認" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"].endswith(str(profile_id))
    assert fake_db.select(
        "certificate_profiles", where="id = %s", params=(profile_id,), fetch_one=True
    )["is_active"]

    certificate_settings.confirm_profile_toggle(fake_db, store, 99, 1, profile_id)
    assert not fake_db.select(
        "certificate_profiles", where="id = %s", params=(profile_id,), fetch_one=True
    )["is_active"]


def test_certificate_without_question_bank_can_still_set_daily_count(fake_db):
    profile_id = _profile(fake_db, key="aws", name="AWS", builtin=False)
    profile = certificate_settings.profile_by_id(fake_db, 1, profile_id)

    reply, keyboard = certificate_settings.daily_summary(fake_db, 1, profile)

    assert "不會推播" in reply
    callbacks = [row[0]["callback_data"] for row in keyboard["inline_keyboard"]]
    assert f"certificate_settings:daily:set:{profile_id}" in callbacks


def test_toeic_daily_counts_are_saved_after_confirmation(fake_db):
    profile_id = _profile(fake_db)
    profile = certificate_settings.profile_by_id(fake_db, 1, profile_id)
    store = ConversationStateStore()
    certificate_settings.start_daily_set(store, 99, 1, profile)
    certificate_settings.handle_daily_text(store, 99, "2")
    certificate_settings.handle_daily_text(store, 99, "3")
    certificate_settings.handle_daily_text(store, 99, "5")
    assert fake_db.select("certificate_daily_settings") == []
    certificate_settings.confirm_daily(fake_db, store, 99)
    row = fake_db.select("certificate_daily_settings")[0]
    assert (
        row["toeic_listen_count"],
        row["toeic_write_count"],
        row["toeic_vocab_count"],
    ) == (2, 3, 5)
    assert row["daily_question_count"] == 10


def test_overlapping_range_is_rejected(fake_db):
    profile_id = _profile(fake_db)
    profile = certificate_settings.profile_by_id(fake_db, 1, profile_id)
    fake_db.insert(
        "certificate_daily_schedule_overrides",
        {
            "user_id": 1,
            "exam_type": "toeic",
            "start_date": date(2026, 8, 10),
            "end_date": date(2026, 8, 20),
            "daily_question_count": 0,
        },
    )
    store = ConversationStateStore()
    certificate_settings.start_range_edit(fake_db, store, 99, 1, profile)
    certificate_settings.handle_range_text(fake_db, store, 99, "2026-08-15")
    reply = certificate_settings.handle_range_text(fake_db, store, 99, "2026-08-25")
    assert "重疊" in reply


def test_score_with_note_requires_confirmation(fake_db):
    profile_id = _profile(fake_db)
    profile = certificate_settings.profile_by_id(fake_db, 1, profile_id)
    store = ConversationStateStore()
    certificate_settings.start_score_add(store, 99, 1, profile)
    certificate_settings.handle_score_text(store, 99, "2026-08-01")
    certificate_settings.handle_score_text(store, 99, "850")
    certificate_settings.handle_score_text(store, 99, "第一次正式應考")
    assert fake_db.select("exam_official_scores") == []
    certificate_settings.confirm_score(fake_db, store, 99)
    assert fake_db.select("exam_official_scores")[0]["note"] == "第一次正式應考"
