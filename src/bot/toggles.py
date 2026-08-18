"""功能開關純邏輯（對應 docs/specs/feature-toggles/SPEC.md FR-3、FR-4）。

負責：補齊新使用者的預設開關資料、查詢/切換開關狀態、組出給使用者看的文字清單。
不處理任何 Telegram 對話流程（那是 src/bot/commands.py 的責任），保持這個模組是純粹的資料操作。
"""
from src.bot import templates
from submodules.cloudsql.client import CloudSQLClient

# feature_toggles.feature_key 的 CHECK 限制只有這 8 個模組，不含「客訴回饋」
# （客訴是固定入口，不是可關閉的功能，見 docs/specs/feature-toggles/SPEC.md FR-3）。
# 名稱直接沿用 templates.FEATURE_LIST，避免同一份功能名稱在兩個地方各寫一次。
TOGGLE_FEATURE_KEYS = [f["key"] for f in templates.FEATURE_LIST]
FEATURE_NAMES = {f["key"]: f["name"] for f in templates.FEATURE_LIST}


def ensure_default_toggles(db: CloudSQLClient, user_id: int) -> None:
    """補齊該使用者缺少的 feature_toggles 資料，預設 is_enabled=TRUE；已存在的不覆蓋（冪等）。"""
    existing = db.select("feature_toggles", columns=("feature_key",), where="user_id = %s", params=(user_id,))
    existing_keys = {row["feature_key"] for row in existing}

    for key in TOGGLE_FEATURE_KEYS:
        if key not in existing_keys:
            db.insert("feature_toggles", {"user_id": user_id, "feature_key": key, "is_enabled": True})


def get_toggles(db: CloudSQLClient, user_id: int) -> list[dict]:
    """依 TOGGLE_FEATURE_KEYS 固定順序回傳該使用者的開關狀態；只回傳資料庫中已存在的項目。"""
    rows = db.select("feature_toggles", where="user_id = %s", params=(user_id,))
    by_key = {row["feature_key"]: row for row in rows}

    return [
        {"feature_key": key, "name": FEATURE_NAMES[key], "is_enabled": by_key[key]["is_enabled"]}
        for key in TOGGLE_FEATURE_KEYS
        if key in by_key
    ]


def format_toggle_list(toggle_list: list[dict]) -> str:
    """組出附編號的開關清單文字，供使用者輸入編號切換。"""
    lines = ["請輸入編號切換該功能的開關（開↔關）：", ""]
    for index, item in enumerate(toggle_list, start=1):
        status = "✅ 開啟" if item["is_enabled"] else "⬜ 關閉"
        lines.append(f"{index}. {item['name']}：{status}")
    return "\n".join(lines)


def toggle_by_index(db: CloudSQLClient, user_id: int, index: int) -> dict | None:
    """依畫面上顯示的編號（1-based）切換開關狀態，回傳更新後的項目；編號無效回傳 None。"""
    toggle_list = get_toggles(db, user_id)
    if index < 1 or index > len(toggle_list):
        return None

    target = toggle_list[index - 1]
    new_state = not target["is_enabled"]
    db.update(
        "feature_toggles",
        {"is_enabled": new_state},
        where="user_id = %s AND feature_key = %s",
        params=(user_id, target["feature_key"]),
    )
    target["is_enabled"] = new_state
    return target


def is_feature_enabled(db: CloudSQLClient, user_id: int, feature_key: str) -> bool:
    """查詢單一功能是否開啟；查無資料時預設視為開啟（防禦性，理論上不該發生）。"""
    row = db.select(
        "feature_toggles",
        where="user_id = %s AND feature_key = %s",
        params=(user_id, feature_key),
        fetch_one=True,
    )
    if row is None:
        return True
    return row["is_enabled"]
