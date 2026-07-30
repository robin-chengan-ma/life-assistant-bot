from src.bot import toggles


def test_toggle_feature_keys_excludes_complaint():
    # 客訴回饋是固定入口，不是可關閉的功能模組，不該出現在開關清單裡
    assert "complaint" not in toggles.TOGGLE_FEATURE_KEYS
    assert len(toggles.TOGGLE_FEATURE_KEYS) == 8


def test_ensure_default_toggles_inserts_all_eight_for_new_user(fake_db):
    toggles.ensure_default_toggles(fake_db, user_id=1)

    rows = fake_db.select("feature_toggles", where="user_id = %s", params=(1,))
    assert len(rows) == 8
    assert all(row["is_enabled"] is True for row in rows)
    assert {row["feature_key"] for row in rows} == set(toggles.TOGGLE_FEATURE_KEYS)


def test_ensure_default_toggles_is_idempotent_and_keeps_existing_state(fake_db):
    fake_db.insert("feature_toggles", {"user_id": 1, "feature_key": "budget", "is_enabled": False})

    toggles.ensure_default_toggles(fake_db, user_id=1)

    rows = fake_db.select("feature_toggles", where="user_id = %s", params=(1,))
    assert len(rows) == 8
    budget_row = next(r for r in rows if r["feature_key"] == "budget")
    assert budget_row["is_enabled"] is False  # 已存在的設定不能被覆蓋回預設值


def test_get_toggles_returns_fixed_order_with_names(fake_db):
    toggles.ensure_default_toggles(fake_db, user_id=1)

    result = toggles.get_toggles(fake_db, user_id=1)

    assert [t["feature_key"] for t in result] == toggles.TOGGLE_FEATURE_KEYS
    assert all("name" in t and "is_enabled" in t for t in result)


def test_get_toggles_only_returns_existing_rows(fake_db):
    fake_db.insert("feature_toggles", {"user_id": 1, "feature_key": "budget", "is_enabled": True})

    result = toggles.get_toggles(fake_db, user_id=1)

    assert len(result) == 1
    assert result[0]["feature_key"] == "budget"


def test_format_toggle_list_shows_numbered_status(fake_db):
    toggles.ensure_default_toggles(fake_db, user_id=1)
    toggle_list = toggles.get_toggles(fake_db, user_id=1)

    text = toggles.format_toggle_list(toggle_list)

    assert "1. " in text
    assert "✅ 開啟" in text


def test_toggle_by_index_flips_state_from_enabled_to_disabled(fake_db):
    toggles.ensure_default_toggles(fake_db, user_id=1)

    result = toggles.toggle_by_index(fake_db, user_id=1, index=1)

    assert result["is_enabled"] is False
    stored = fake_db.select(
        "feature_toggles",
        where="user_id = %s AND feature_key = %s",
        params=(1, result["feature_key"]),
        fetch_one=True,
    )
    assert stored["is_enabled"] is False


def test_toggle_by_index_flips_state_back_to_enabled(fake_db):
    toggles.ensure_default_toggles(fake_db, user_id=1)
    toggles.toggle_by_index(fake_db, user_id=1, index=1)

    result = toggles.toggle_by_index(fake_db, user_id=1, index=1)

    assert result["is_enabled"] is True


def test_toggle_by_index_returns_none_for_out_of_range_index(fake_db):
    toggles.ensure_default_toggles(fake_db, user_id=1)

    assert toggles.toggle_by_index(fake_db, user_id=1, index=0) is None
    assert toggles.toggle_by_index(fake_db, user_id=1, index=9) is None


def test_is_feature_enabled_reflects_current_state(fake_db):
    toggles.ensure_default_toggles(fake_db, user_id=1)
    toggles.toggle_by_index(fake_db, user_id=1, index=1)
    disabled_key = toggles.TOGGLE_FEATURE_KEYS[0]

    assert toggles.is_feature_enabled(fake_db, user_id=1, feature_key=disabled_key) is False
    assert toggles.is_feature_enabled(fake_db, user_id=1, feature_key=toggles.TOGGLE_FEATURE_KEYS[1]) is True


def test_is_feature_enabled_defaults_true_when_row_missing(fake_db):
    # 防禦性：理論上不該發生（應該都先跑過 ensure_default_toggles），但缺資料時不能誤判成關閉
    assert toggles.is_feature_enabled(fake_db, user_id=1, feature_key="budget") is True
