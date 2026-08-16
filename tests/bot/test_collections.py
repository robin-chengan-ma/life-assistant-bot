"""收藏清單 Telegram 流程測試（Phase 6 第二批 2d，見 docs/ADR/discuss/robinson.md）。

沿用 tests/bot/test_important_days.py 的 FakeDatabase 寫法：不重現完整 SQL，
`AppCollectionService` 本身的驗證邏輯已在 tests/services/test_app_collections.py
完整覆蓋，這裡只驗證 Telegram 對話流程：多步驟輸入、地址定位按鈕、摘要文字、
按鈕分派與呼叫 service 時組出的 payload 是否正確。
"""

from src.bot import collections
from src.bot.state import ConversationStateStore


class FakeDatabase:
    def __init__(self):
        self.tables = {"collection_items": [], "geocoding_cache": [], "exploration_events": []}
        self.next_id = 1
        self.next_event_id = 1

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        rows = list(self.tables[table])
        if where == "id = %s AND user_id = %s AND deleted_at IS NULL":
            rows = [
                row for row in rows
                if row["id"] == params[0] and row["user_id"] == params[1] and row.get("deleted_at") is None
            ]
        elif where == "id = %s AND user_id = %s":
            rows = [row for row in rows if row["id"] == params[0] and row["user_id"] == params[1]]
        elif where == "query_key = %s":
            rows = [row for row in rows if row.get("query_key") == params[0]]
        return (rows[0] if rows else None) if fetch_one else rows

    def insert(self, table, data, returning="id"):
        row = dict(data)
        if table == "collection_items":
            row["id"] = self.next_id
            self.next_id += 1
            row.setdefault("deleted_at", None)
        elif table == "exploration_events":
            row["id"] = self.next_event_id
            self.next_event_id += 1
        self.tables[table].append(row)
        return row.get(returning)

    def update(self, table, data, where, params):
        rows = self.select(table, where=where, params=params) if where in (
            "id = %s AND user_id = %s AND deleted_at IS NULL",
        ) else [row for row in self.tables[table] if row["id"] == params[0]]
        for row in rows:
            row.update(data)
        return len(rows)

    def delete(self, table, where, params):
        before = len(self.tables[table])
        self.tables[table] = [row for row in self.tables[table] if row["id"] != params[0]]
        return before - len(self.tables[table])

    def execute_query(self, query, params=None):
        if "app_collections:list" in query:
            return [row for row in self.tables["collection_items"] if row.get("deleted_at") is None]
        return []


TELEGRAM_USER_ID = 999
USER_ID = 1


def _run_step(db, store, text):
    return collections.handle_step(db, store, TELEGRAM_USER_ID, USER_ID, text)


def test_add_flow_skip_address_creates_row():
    db = FakeDatabase()
    store = ConversationStateStore()
    collections.start_add(store, TELEGRAM_USER_ID)

    _run_step(db, store, "2")  # 景點
    _run_step(db, store, "阿里山")
    _run_step(db, store, "台灣")
    _run_step(db, store, "嘉義")
    _run_step(db, store, "略過")  # 地址
    _run_step(db, store, "略過")  # 網址
    _run_step(db, store, "略過")  # 費用
    text, keyboard = _run_step(db, store, "略過")  # 備註

    assert "請確認以下內容" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "collections:confirm_save"

    reply, _ = collections.handle_confirm_save(db, store, TELEGRAM_USER_ID, USER_ID)

    assert reply == "已新增收藏！"
    row = db.tables["collection_items"][0]
    assert row["item_type"] == "attraction"
    assert row["title"] == "阿里山"
    assert row["country_name"] == "台灣" and row["city_name"] == "嘉義"
    assert row["address"] is None


def test_add_flow_with_address_and_skip_geocode():
    db = FakeDatabase()
    store = ConversationStateStore()
    collections.start_add(store, TELEGRAM_USER_ID)

    _run_step(db, store, "1")  # 餐廳
    _run_step(db, store, "美味小吃")
    _run_step(db, store, "台灣")
    _run_step(db, store, "台北")
    text, keyboard = _run_step(db, store, "忠孝東路一段1號")  # 地址

    assert "要立即定位嗎" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "collections:geocode"
    assert keyboard["inline_keyboard"][1][0]["callback_data"] == "collections:skip_geocode"

    text, keyboard = collections.handle_geocode_choice(db, store, TELEGRAM_USER_ID, False)
    assert "參考網址" in text
    assert store.get(TELEGRAM_USER_ID)["step"] == "awaiting_source_url"

    _run_step(db, store, "略過")
    _run_step(db, store, "500")
    _run_step(db, store, "略過")
    reply, _ = collections.handle_confirm_save(db, store, TELEGRAM_USER_ID, USER_ID)

    assert reply == "已新增收藏！"
    row = db.tables["collection_items"][0]
    assert row["address"] == "忠孝東路一段1號"
    assert row["estimated_cost"] == 500


def test_invalid_estimated_cost_reprompts_without_advancing_state():
    db = FakeDatabase()
    store = ConversationStateStore()
    collections.start_add(store, TELEGRAM_USER_ID)
    _run_step(db, store, "3")
    _run_step(db, store, "名稱")
    _run_step(db, store, "台灣")
    _run_step(db, store, "台北")
    _run_step(db, store, "略過")
    _run_step(db, store, "略過")

    text, keyboard = _run_step(db, store, "不是數字")

    assert "請輸入數字" in text
    assert keyboard is None
    assert store.get(TELEGRAM_USER_ID)["step"] == "awaiting_estimated_cost"


def test_exit_phrase_clears_state():
    db = FakeDatabase()
    store = ConversationStateStore()
    collections.start_add(store, TELEGRAM_USER_ID)
    text, keyboard = _run_step(db, store, "沒有了")

    assert "已結束收藏設定" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "menu:main"
    assert store.get(TELEGRAM_USER_ID) is None


def test_handle_list_empty_prompts_to_add():
    db = FakeDatabase()

    text, keyboard = collections.handle_list(db, USER_ID)

    assert "還沒有任何收藏" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "collections:add"


def test_handle_list_shows_edit_delete_buttons():
    db = FakeDatabase()
    db.tables["collection_items"] = [
        {
            "id": 1, "user_id": USER_ID, "item_type": "restaurant", "title": "美味小吃",
            "country_name": "台灣", "city_name": "台北", "address": None, "status": "saved",
            "deleted_at": None,
        },
    ]

    text, keyboard = collections.handle_list(db, USER_ID)

    assert "美味小吃" in text
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "collections:edit:1" in callback_datas
    assert "collections:delete:1" in callback_datas


def test_delete_requires_ownership():
    db = FakeDatabase()
    db.tables["collection_items"] = [
        {"id": 1, "user_id": 10, "title": "別人的收藏", "deleted_at": None},
    ]
    store = ConversationStateStore()

    text, keyboard = collections.start_delete_confirm(db, store, TELEGRAM_USER_ID, USER_ID, 1)

    assert "找不到" in text
    assert store.get(TELEGRAM_USER_ID) is None


def test_delete_confirm_then_execute_soft_deletes_row():
    db = FakeDatabase()
    db.tables["collection_items"] = [
        {"id": 1, "user_id": USER_ID, "title": "要刪除的收藏", "deleted_at": None},
    ]
    store = ConversationStateStore()

    text, _ = collections.start_delete_confirm(db, store, TELEGRAM_USER_ID, USER_ID, 1)
    assert "確定要刪除" in text
    assert store.get(TELEGRAM_USER_ID)["flow"] == "collection_delete_confirm"

    reply, _ = collections.handle_delete(db, store, TELEGRAM_USER_ID, USER_ID, 1)

    assert reply == "已刪除該筆收藏。"
    assert store.get(TELEGRAM_USER_ID) is None


def test_delete_confirm_state_ignores_typed_text_and_cancels():
    store = ConversationStateStore()
    store.set(TELEGRAM_USER_ID, {"flow": "collection_delete_confirm", "target_id": 1})

    text, keyboard = collections.handle_delete_confirm_text(store, TELEGRAM_USER_ID)

    assert "請用上面的按鈕" in text
    assert store.get(TELEGRAM_USER_ID) is None


def test_edit_flow_prefills_title_prompt_and_updates_existing_row():
    db = FakeDatabase()
    db.tables["collection_items"] = [
        {"id": 1, "user_id": USER_ID, "title": "舊名稱", "deleted_at": None},
    ]
    store = ConversationStateStore()

    prompt = collections.start_edit(db, store, TELEGRAM_USER_ID, USER_ID, 1)
    assert "舊名稱" in prompt

    _run_step(db, store, "3")
    _run_step(db, store, "新名稱")
    _run_step(db, store, "台灣")
    _run_step(db, store, "台北")
    _run_step(db, store, "略過")
    _run_step(db, store, "略過")
    _run_step(db, store, "略過")
    reply, _ = _run_step(db, store, "略過")

    reply, _ = collections.handle_confirm_save(db, store, TELEGRAM_USER_ID, USER_ID)

    assert reply == "已更新該筆收藏！"
    assert db.tables["collection_items"][0]["title"] == "新名稱"


def test_visit_flow_creates_exploration_event_and_marks_status():
    """2026-08-16 補修（見 docs/ADR/debug/robinson.md）：Telegram 標記已造訪，
    不經行程也能把收藏加入探索地圖，並帶入收藏既有的座標。"""
    db = FakeDatabase()
    db.tables["collection_items"] = [
        {
            "id": 1, "user_id": USER_ID, "title": "阿里山", "item_type": "attraction",
            "country_name": "台灣", "city_name": "嘉義", "address": "阿里山鄉",
            "latitude": 23.5, "longitude": 120.8, "status": "saved", "deleted_at": None,
        },
    ]
    store = ConversationStateStore()

    text, keyboard = collections.start_visit(db, store, TELEGRAM_USER_ID, USER_ID, 1)
    assert "阿里山" in text
    assert store.get(TELEGRAM_USER_ID)["flow"] == "collection_visit"

    text, keyboard = collections.handle_visit_step(db, store, TELEGRAM_USER_ID, USER_ID, "2026-08-10")
    assert "備註" in text

    reply, _ = collections.handle_visit_step(db, store, TELEGRAM_USER_ID, USER_ID, "略過")

    assert "已標記造訪" in reply
    assert store.get(TELEGRAM_USER_ID) is None
    event = db.tables["exploration_events"][0]
    assert event["collection_item_id"] == 1
    assert event["latitude"] == 23.5 and event["longitude"] == 120.8
    assert db.tables["collection_items"][0]["status"] == "visited"


def test_visit_flow_today_phrase_uses_current_date():
    db = FakeDatabase()
    db.tables["collection_items"] = [
        {
            "id": 1, "user_id": USER_ID, "title": "阿里山", "item_type": "attraction",
            "country_name": "台灣", "city_name": "嘉義", "address": None,
            "latitude": None, "longitude": None, "status": "saved", "deleted_at": None,
        },
    ]
    store = ConversationStateStore()
    collections.start_visit(db, store, TELEGRAM_USER_ID, USER_ID, 1)

    text, _ = collections.handle_visit_step(db, store, TELEGRAM_USER_ID, USER_ID, "今天")
    assert "備註" in text

    reply, _ = collections.handle_visit_step(db, store, TELEGRAM_USER_ID, USER_ID, "略過")
    assert "已標記造訪" in reply
    assert db.tables["exploration_events"][0]["latitude"] is None


def test_visit_already_visited_item_rejected():
    db = FakeDatabase()
    db.tables["collection_items"] = [
        {"id": 1, "user_id": USER_ID, "title": "已造訪過的地點", "status": "visited", "deleted_at": None},
    ]
    store = ConversationStateStore()

    text, keyboard = collections.start_visit(db, store, TELEGRAM_USER_ID, USER_ID, 1)

    assert "已經標記過造訪" in text
    assert store.get(TELEGRAM_USER_ID) is None
