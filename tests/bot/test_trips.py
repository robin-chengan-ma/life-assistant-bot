"""旅遊行程 Telegram 流程測試（Phase 6 第二批 2d，見 docs/ADR/discuss/robinson.md）。

沿用 tests/bot/test_important_days.py 的 FakeDatabase 寫法：`AppLifeExplorationService`
本身的驗證邏輯已在 tests/services/test_app_life_exploration.py 完整覆蓋，這裡只驗證
Telegram 對話流程：目的地收藏候選清單、多選按鈕、分類預估支出多步驟輸入、狀態操作與
完成行程流程。
"""

from src.bot import trips
from src.bot.state import ConversationStateStore


class FakeDatabase:
    def __init__(self):
        self.tables = {
            "trips": [],
            "trip_collection_items": [],
            "collection_items": [],
            "important_days": [],
        }
        self.next_trip_id = 1
        self.next_link_id = 1

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        rows = list(self.tables[table])
        if table == "collection_items" and where == "user_id = %s AND deleted_at IS NULL AND country_name = %s AND city_name = %s":
            rows = [
                row for row in rows
                if row["user_id"] == params[0] and row.get("deleted_at") is None
                and row["country_name"] == params[1] and row["city_name"] == params[2]
            ]
        elif where == "id = %s AND user_id = %s AND deleted_at IS NULL":
            rows = [row for row in rows if row["id"] == params[0] and row["user_id"] == params[1] and row.get("deleted_at") is None]
        elif where == "id = %s AND user_id = %s":
            rows = [row for row in rows if row["id"] == params[0] and row["user_id"] == params[1]]
        elif where == "trip_id = %s":
            rows = [row for row in rows if row["trip_id"] == params[0]]
        elif table == "collection_items" and where and "id = %s AND user_id = %s" in where:
            rows = [row for row in rows if row["id"] == params[0] and row["user_id"] == params[1]]
        return (rows[0] if rows else None) if fetch_one else rows

    def insert(self, table, data, returning="id"):
        row = dict(data)
        if table == "trips":
            row["id"] = self.next_trip_id
            self.next_trip_id += 1
            row.setdefault("deleted_at", None)
        elif table == "trip_collection_items":
            row["id"] = self.next_link_id
            self.next_link_id += 1
        elif table == "exploration_events" or table == "important_days":
            row["id"] = len(self.tables.setdefault(table, [])) + 1
        self.tables.setdefault(table, []).append(row)
        return row.get(returning)

    def update(self, table, data, where, params):
        if where in ("id = %s AND user_id = %s", "id = %s AND user_id = %s AND deleted_at IS NULL"):
            rows = [row for row in self.tables[table] if row["id"] == params[0] and row["user_id"] == params[1]]
        elif where == "id = %s":
            rows = [row for row in self.tables[table] if row["id"] == params[0]]
        else:
            rows = self.tables[table]
        for row in rows:
            row.update(data)
        return len(rows)

    def delete(self, table, where, params):
        before = len(self.tables[table])
        if where == "trip_id = %s":
            self.tables[table] = [row for row in self.tables[table] if row.get("trip_id") != params[0]]
        else:
            self.tables[table] = [row for row in self.tables[table] if row["id"] != params[0]]
        return before - len(self.tables[table])

    def execute_query(self, query, params=None):
        if "app_life:list_trips" in query:
            rows = [dict(row) for row in self.tables["trips"] if row.get("deleted_at") is None]
            for row in rows:
                row.setdefault("actual_expense", 0)
                row.setdefault("actual_transport", 0)
                row.setdefault("actual_accommodation", 0)
                row.setdefault("actual_food", 0)
                row.setdefault("actual_tickets", 0)
                row.setdefault("actual_shopping", 0)
                row.setdefault("actual_other", 0)
            return rows
        if "app_life:trip_items" in query:
            trip_id = params[0]
            links = [row for row in self.tables["trip_collection_items"] if row["trip_id"] == trip_id]
            result = []
            for link in links:
                item = next((c for c in self.tables["collection_items"] if c["id"] == link["collection_item_id"]), {})
                result.append({
                    "collection_item_id": link["collection_item_id"], "sort_order": link.get("sort_order", 0),
                    "visit_status": link.get("visit_status"), "title_snapshot": link.get("title_snapshot"),
                    "item_type": item.get("item_type"), "country_name": item.get("country_name"),
                    "city_name": item.get("city_name"), "address": item.get("address"),
                })
            return result
        if "app_life:trip_candidate" in query or "achievement_candidates" in query:
            return []
        return []


TELEGRAM_USER_ID = 999
USER_ID = 1


def _seed_collections(db):
    db.tables["collection_items"] = [
        {"id": 1, "user_id": USER_ID, "item_type": "attraction", "title": "阿里山", "country_name": "台灣", "city_name": "嘉義", "deleted_at": None},
        {"id": 2, "user_id": USER_ID, "item_type": "restaurant", "title": "山產店", "country_name": "台灣", "city_name": "嘉義", "deleted_at": None},
    ]


def _run_step(db, store, text):
    return trips.handle_step(db, store, TELEGRAM_USER_ID, USER_ID, text)


def test_add_flow_with_item_selection_and_category_budgets():
    db = FakeDatabase()
    _seed_collections(db)
    store = ConversationStateStore()
    trips.start_add(store, TELEGRAM_USER_ID)

    _run_step(db, store, "嘉義小旅行")
    _run_step(db, store, "台灣")
    text, keyboard = _run_step(db, store, "嘉義")

    assert "請勾選" in text
    toggle_id_1 = keyboard["inline_keyboard"][0][0]["callback_data"]
    assert toggle_id_1 == "trips:toggle_item:1"

    trips.handle_toggle_item(store, TELEGRAM_USER_ID, 1)
    text, keyboard = trips.handle_items_done(store, TELEGRAM_USER_ID)
    assert "開始日期" in text

    _run_step(db, store, "略過")  # 日期全部略過
    _run_step(db, store, "否")  # 同步重要日子（測試不涉入 important_days 連動邏輯）
    _run_step(db, store, "1000")  # 交通
    _run_step(db, store, "2000")  # 住宿
    _run_step(db, store, "略過")  # 飲食
    _run_step(db, store, "略過")  # 門票
    _run_step(db, store, "略過")  # 購物
    text, keyboard = _run_step(db, store, "500")  # 其他
    assert "備註" in text

    text, keyboard = _run_step(db, store, "略過")  # 備註
    assert "合計" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "trips:confirm_save"

    reply, _ = trips.handle_confirm_save(db, store, TELEGRAM_USER_ID, USER_ID)

    assert reply == "已新增旅遊行程！"
    row = db.tables["trips"][0]
    assert row["title"] == "嘉義小旅行"
    assert row["estimated_transport"] == 1000
    assert row["estimated_accommodation"] == 2000
    assert row["estimated_other"] == 500
    assert db.tables["trip_collection_items"][0]["collection_item_id"] == 1


def test_no_matching_collections_aborts_flow():
    db = FakeDatabase()
    store = ConversationStateStore()
    trips.start_add(store, TELEGRAM_USER_ID)

    _run_step(db, store, "沒有收藏的行程")
    _run_step(db, store, "日本")
    text, _keyboard = _run_step(db, store, "東京")

    assert "沒有任何收藏項目" in text
    assert store.get(TELEGRAM_USER_ID) is None


def test_exit_phrase_clears_state():
    db = FakeDatabase()
    store = ConversationStateStore()
    trips.start_add(store, TELEGRAM_USER_ID)

    text, _keyboard = _run_step(db, store, "沒有了")

    assert "已結束旅遊行程設定" in text
    assert store.get(TELEGRAM_USER_ID) is None


def test_handle_list_empty_suggests_collections():
    db = FakeDatabase()

    text, _keyboard = trips.handle_list(db, USER_ID)

    assert "還沒有任何旅遊行程" in text


def test_handle_set_status_confirms_trip():
    db = FakeDatabase()
    db.tables["trips"] = [
        {
            "id": 1, "user_id": USER_ID, "title": "行程", "country_name": "台灣", "city_name": "嘉義",
            "start_date": "2026-09-01", "end_date": "2026-09-02", "status": "planning", "notes": None,
            "sync_to_important_day": False, "deleted_at": None,
            "estimated_transport": None, "estimated_accommodation": None, "estimated_food": None,
            "estimated_tickets": None, "estimated_shopping": None, "estimated_other": None,
        },
    ]

    text, _keyboard = trips.handle_set_status(db, USER_ID, 1, "confirmed")

    assert "已確認" in text
    assert db.tables["trips"][0]["status"] == "confirmed"


def test_delete_confirm_then_execute_removes_row():
    db = FakeDatabase()
    db.tables["trips"] = [
        {"id": 1, "user_id": USER_ID, "title": "要刪除的行程", "deleted_at": None, "sync_to_important_day": False, "status": "planning"},
    ]
    store = ConversationStateStore()

    text, _ = trips.start_delete_confirm(db, store, TELEGRAM_USER_ID, USER_ID, 1)
    assert "確定要刪除" in text

    reply, _ = trips.handle_delete(db, store, TELEGRAM_USER_ID, USER_ID, 1)

    assert reply == "已刪除該筆旅遊行程。"
    assert store.get(TELEGRAM_USER_ID) is None


def test_delete_confirm_state_ignores_typed_text_and_cancels():
    store = ConversationStateStore()
    store.set(TELEGRAM_USER_ID, {"flow": "trip_delete_confirm", "target_id": 1})

    text, _keyboard = trips.handle_delete_confirm_text(store, TELEGRAM_USER_ID)

    assert "請用上面的按鈕" in text
    assert store.get(TELEGRAM_USER_ID) is None


def test_complete_select_state_ignores_typed_text_and_cancels():
    store = ConversationStateStore()
    store.set(TELEGRAM_USER_ID, {"flow": "trip_complete_select", "data": {"trip_id": 1, "_candidates": [], "_selected_ids": []}})

    text, _keyboard = trips.handle_complete_select_text(store, TELEGRAM_USER_ID)

    assert "請用上面的按鈕" in text
    assert store.get(TELEGRAM_USER_ID) is None
