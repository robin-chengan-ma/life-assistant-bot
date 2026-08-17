"""成果展示 Telegram 流程測試（Phase 6 第二批 2e，見 docs/ADR/discuss/robinson.md）。

沿用 tests/bot/test_collections.py 的 FakeDatabase 寫法：不重現完整 SQL，
`AppLifeExplorationService` 本身的驗證與候選掃描邏輯已在
tests/services/test_app_life_exploration.py 完整覆蓋，這裡只驗證 Telegram
對話流程：手動新增多步驟輸入、清單顯示（候選＋已建立成果）、候選確認按鈕、
直接刪除（無二次確認、無復原）。
"""

from src.bot import achievements
from src.bot.state import ConversationStateStore


class FakeDatabase:
    def __init__(self):
        self.tables = {"user_achievements": [], "achievement_candidates": []}
        self.next_id = 1

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        rows = list(self.tables[table])
        if where == "user_id = %s AND deleted_at IS NULL":
            rows = [row for row in rows if row["user_id"] == params[0] and row.get("deleted_at") is None]
        elif where == "user_id = %s AND status = 'pending'":
            rows = [row for row in rows if row["user_id"] == params[0] and row.get("status") == "pending"]
        elif where == "id = %s AND user_id = %s":
            rows = [row for row in rows if row["id"] == params[0] and row["user_id"] == params[1]]
        return (rows[0] if rows else None) if fetch_one else rows

    def insert(self, table, data, returning="id"):
        row = dict(data)
        row["id"] = self.next_id
        self.next_id += 1
        row.setdefault("deleted_at", None)
        self.tables[table].append(row)
        return row.get(returning)

    def update(self, table, data, where, params):
        rows = self.select(table, where=where, params=params)
        for row in rows:
            row.update(data)
        return len(rows)

    def execute_query(self, query, params=None):
        return []


TELEGRAM_USER_ID = 999
USER_ID = 1


def _run_step(store, text):
    return achievements.handle_step(store, TELEGRAM_USER_ID, text)


def test_add_flow_creates_manual_achievement():
    db = FakeDatabase()
    store = ConversationStateStore()
    achievements.start_add(store, TELEGRAM_USER_ID)

    _run_step(store, "1")  # 體態
    _run_step(store, "體重達標")
    _run_step(store, "2026-08-01")
    _run_step(store, "略過")  # 說明
    text, keyboard = _run_step(store, "略過")  # 照片網址

    assert "請確認以下內容" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "achievements:confirm_save"

    reply, _ = achievements.handle_confirm_save(db, store, TELEGRAM_USER_ID, USER_ID)

    assert reply == "已新增成果！"
    row = db.tables["user_achievements"][0]
    assert row["category"] == "body"
    assert row["title"] == "體重達標"
    from datetime import date

    assert row["unlocked_on"] == date(2026, 8, 1)
    assert row["creation_source"] == "manual"


def test_invalid_date_reprompts_without_advancing_state():
    store = ConversationStateStore()
    achievements.start_add(store, TELEGRAM_USER_ID)
    _run_step(store, "3")
    _run_step(store, "名稱")

    text, keyboard = _run_step(store, "不是日期")

    assert "日期格式不正確" in text
    assert keyboard is None
    assert store.get(TELEGRAM_USER_ID)["step"] == "awaiting_completed_on"


def test_exit_phrase_clears_state():
    store = ConversationStateStore()
    achievements.start_add(store, TELEGRAM_USER_ID)
    text, keyboard = _run_step(store, "沒有了")

    assert "已結束成果設定" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "menu:main"
    assert store.get(TELEGRAM_USER_ID) is None


def test_handle_list_empty_prompts_to_add():
    db = FakeDatabase()

    text, keyboard = achievements.handle_list(db, USER_ID)

    assert "還沒有任何成果" in text
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "achievements:add" in callback_datas


def test_handle_list_shows_candidates_and_achievements_with_buttons():
    db = FakeDatabase()
    db.tables["achievement_candidates"] = [
        {
            "id": 5, "user_id": USER_ID, "category": "trip", "title": "完成旅遊行程：東京行",
            "completed_on": "2026-08-10", "status": "pending",
        },
    ]
    db.tables["user_achievements"] = [
        {
            "id": 1, "user_id": USER_ID, "category": "body", "title": "體重達標",
            "unlocked_on": "2026-07-01", "creation_source": "manual", "deleted_at": None,
        },
    ]

    text, keyboard = achievements.handle_list(db, USER_ID)

    assert "東京行" in text
    assert "體重達標" in text
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "achievements:candidate_accept:5" in callback_datas
    assert "achievements:candidate_reject:5" in callback_datas
    assert "achievements:delete:1" in callback_datas


def test_candidate_accept_creates_achievement_and_marks_accepted():
    db = FakeDatabase()
    db.tables["achievement_candidates"] = [
        {
            "id": 5, "user_id": USER_ID, "category": "trip", "title": "完成旅遊行程：東京行",
            "description": "已完成一趟旅遊行程", "completed_on": "2026-08-10", "source_type": "trip",
            "source_id": 3, "status": "pending",
        },
    ]

    text, _ = achievements.handle_candidate_decision(db, USER_ID, 5, True)

    assert text == "成果已建立"
    assert db.tables["achievement_candidates"][0]["status"] == "accepted"
    assert db.tables["user_achievements"][0]["title"] == "完成旅遊行程：東京行"
    assert db.tables["user_achievements"][0]["creation_source"] == "suggested"


def test_candidate_reject_marks_rejected_without_creating_achievement():
    db = FakeDatabase()
    db.tables["achievement_candidates"] = [
        {
            "id": 5, "user_id": USER_ID, "category": "trip", "title": "完成旅遊行程：東京行",
            "completed_on": "2026-08-10", "source_type": "trip", "source_id": 3, "status": "pending",
        },
    ]

    text, _ = achievements.handle_candidate_decision(db, USER_ID, 5, False)

    assert text == "已略過成果候選"
    assert db.tables["achievement_candidates"][0]["status"] == "rejected"
    assert db.tables["user_achievements"] == []


def test_delete_is_immediate_without_confirmation_step():
    db = FakeDatabase()
    db.tables["user_achievements"] = [
        {"id": 1, "user_id": USER_ID, "title": "要刪除的成果", "deleted_at": None},
    ]

    reply, _ = achievements.handle_delete(db, USER_ID, 1)

    assert reply == "已刪除該筆成果。"
    assert db.tables["user_achievements"][0]["deleted_at"] is not None


def test_delete_requires_ownership():
    db = FakeDatabase()
    db.tables["user_achievements"] = [
        {"id": 1, "user_id": 10, "title": "別人的成果", "deleted_at": None},
    ]

    text, _keyboard = achievements.handle_delete(db, USER_ID, 1)

    assert "找不到" in text
