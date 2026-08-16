"""重要日子 Telegram 流程測試（Phase 6 第二批 2b，見 docs/ADR/discuss/robinson.md）。

沿用 tests/services/test_app_important_days.py 的 FakeDatabase 寫法（不重現完整 SQL JOIN，
`execute_query` 固定回傳空清單），因為 AppImportantDayService 本身的驗證與序列化邏輯已在
那份測試完整覆蓋；這裡只驗證 Telegram 對話流程本身：多步驟輸入、摘要文字、按鈕分派與
呼叫 service 時組出的 payload 是否正確。
"""

from src.bot import important_days
from src.bot.state import ConversationStateStore


class FakeDatabase:
    def __init__(self):
        self.tables = {
            "important_days": [],
            "important_day_recipients": [],
            "important_day_occurrences": [],
            "users": [
                {"id": 1, "role": "Robin", "nickname": "Robin"},
                {"id": 10, "role": "爸爸", "family_title": "爸爸"},
            ],
        }
        self.next_id = 1

    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False):
        rows = list(self.tables[table])
        if where == "id = %s AND owner_user_id = %s":
            rows = [row for row in rows if row["id"] == params[0] and row["owner_user_id"] == params[1]]
        return (rows[0] if rows else None) if fetch_one else rows

    def insert(self, table, data, returning="id"):
        row = dict(data)
        if table == "important_days":
            row["id"] = self.next_id
            self.next_id += 1
        self.tables[table].append(row)
        return row.get(returning)

    def update(self, table, data, where, params):
        rows = self.select(table, where=where, params=params)
        for row in rows:
            row.update(data)
        return len(rows)

    def delete(self, table, where, params):
        key = "id" if table == "important_days" else "important_day_id"
        before = len(self.tables[table])
        self.tables[table] = [row for row in self.tables[table] if row[key] != params[0]]
        return before - len(self.tables[table])

    def execute_query(self, query, params=None):
        return []


TELEGRAM_USER_ID = 999
USER_ID = 1


def _run_step(db, store, text):
    return important_days.handle_step(db, store, TELEGRAM_USER_ID, USER_ID, text)


def test_add_fixed_annual_self_flow_creates_row():
    db = FakeDatabase()
    store = ConversationStateStore()
    important_days.start_add(store, TELEGRAM_USER_ID)

    _run_step(db, store, "媽媽生日")
    _run_step(db, store, "1")  # 每年固定日期
    _run_step(db, store, "8-15")  # 開始
    _run_step(db, store, "8-15")  # 結束
    _run_step(db, store, "是")  # 全天
    _run_step(db, store, "1")  # 提前 1 天
    _run_step(db, store, "1")  # 通知對象：只有自己
    text, keyboard = _run_step(db, store, "略過")  # 備註

    assert "請確認以下內容" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "important_days:confirm_save"

    reply, _ = important_days.handle_confirm_save(db, store, TELEGRAM_USER_ID, USER_ID)

    assert reply == "已新增重要日子！"
    assert len(db.tables["important_days"]) == 1
    row = db.tables["important_days"][0]
    assert row["title"] == "媽媽生日"
    assert row["recurrence_type"] == "fixed_annual"
    assert row["event_month"] == 8 and row["event_day"] == 15
    assert row["owner_user_id"] == USER_ID
    assert db.tables["important_day_recipients"] == [{"important_day_id": 1, "user_id": USER_ID}]


def test_add_one_time_event_with_time_and_specific_recipients():
    db = FakeDatabase()
    store = ConversationStateStore()
    important_days.start_add(store, TELEGRAM_USER_ID)

    _run_step(db, store, "同學婚禮")
    _run_step(db, store, "3")  # 單次事件
    _run_step(db, store, "2026-12-20")
    _run_step(db, store, "2026-12-20")
    _run_step(db, store, "否")  # 不是全天
    _run_step(db, store, "18:00")
    _run_step(db, store, "3")  # 提前 3 天
    _run_step(db, store, "3")  # 指定家人
    _run_step(db, store, "2")  # 選第 2 位（爸爸，id=10）
    _run_step(db, store, "略過")  # 備註
    important_days.handle_confirm_save(db, store, TELEGRAM_USER_ID, USER_ID)

    row = db.tables["important_days"][0]
    assert row["recurrence_type"] == "one_time"
    assert row["event_date"].isoformat() == "2026-12-20"
    assert row["is_all_day"] is False
    assert row["event_time"].strftime("%H:%M") == "18:00"
    assert row["reminder_days_before"] == 3
    assert row["audience_mode"] == "specific"
    assert {r["user_id"] for r in db.tables["important_day_recipients"]} == {10}


def test_add_flexible_annual_can_skip_occurrence_date():
    db = FakeDatabase()
    store = ConversationStateStore()
    important_days.start_add(store, TELEGRAM_USER_ID)

    _run_step(db, store, "農曆節日")
    _run_step(db, store, "2")  # 每年浮動日期
    _run_step(db, store, "略過")  # 尚不知道今年日期
    _run_step(db, store, "是")
    _run_step(db, store, "0")
    _run_step(db, store, "2")  # 全部家人
    _run_step(db, store, "略過")  # 備註
    important_days.handle_confirm_save(db, store, TELEGRAM_USER_ID, USER_ID)

    row = db.tables["important_days"][0]
    assert row["recurrence_type"] == "flexible_annual"
    assert row["audience_mode"] == "all"
    assert db.tables["important_day_occurrences"] == []


def test_invalid_recurrence_choice_reprompts_without_advancing_state():
    db = FakeDatabase()
    store = ConversationStateStore()
    important_days.start_add(store, TELEGRAM_USER_ID)
    _run_step(db, store, "隨便一個名稱")

    text, keyboard = _run_step(db, store, "9")

    assert "請輸入 1、2 或 3" in text
    assert keyboard is None
    assert store.get(TELEGRAM_USER_ID)["step"] == "awaiting_recurrence_type"


def test_invalid_date_shows_validation_message_and_keeps_step():
    db = FakeDatabase()
    store = ConversationStateStore()
    important_days.start_add(store, TELEGRAM_USER_ID)
    _run_step(db, store, "隨便一個名稱")
    _run_step(db, store, "3")  # 單次事件

    text, keyboard = _run_step(db, store, "not-a-date")

    assert "格式不正確" in text
    assert keyboard is None
    assert store.get(TELEGRAM_USER_ID)["step"] == "awaiting_start_date"


def test_exit_phrase_clears_state():
    db = FakeDatabase()
    store = ConversationStateStore()
    important_days.start_add(store, TELEGRAM_USER_ID)
    _run_step(db, store, "隨便一個名稱")

    text, keyboard = _run_step(db, store, "沒有了")

    assert "已結束重要日子設定" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "menu:main"
    assert store.get(TELEGRAM_USER_ID) is None


def test_handle_list_shows_edit_delete_buttons_only_for_owner():
    db = FakeDatabase()
    db.tables["important_days"] = [
        {
            "id": 1, "owner_user_id": USER_ID, "title": "我的事件", "recurrence_type": "one_time",
            "event_date": "2026-09-01", "event_end_date": "2026-09-01", "event_month": None, "event_day": None,
            "event_end_month": None, "event_end_day": None, "event_time": None, "is_all_day": True,
            "reminder_days_before": 1, "notes": None, "audience_mode": "self", "show_on_todo_calendar": True,
            "is_active": True, "updated_at": "2026-08-15",
        },
    ]

    class ListingFakeDatabase(FakeDatabase):
        def execute_query(self, query, params=None):
            rows = []
            for row in self.tables["important_days"]:
                enriched = dict(row)
                enriched["recipient_ids"] = [USER_ID]
                enriched["current_year_date"] = None
                enriched["current_year_end_date"] = None
                rows.append(enriched)
            return rows

    listing_db = ListingFakeDatabase()
    listing_db.tables = db.tables

    text, keyboard = important_days.handle_list(listing_db, USER_ID)

    assert "我的事件" in text
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "important_days:edit:1" in callback_datas
    assert "important_days:delete:1" in callback_datas


def test_handle_list_empty_prompts_to_add():
    db = FakeDatabase()

    text, keyboard = important_days.handle_list(db, USER_ID)

    assert "還沒有任何重要日子" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "menu:main"


def test_delete_requires_ownership():
    db = FakeDatabase()
    db.tables["important_days"] = [
        {"id": 1, "owner_user_id": 10, "title": "別人的事件"},
    ]
    store = ConversationStateStore()

    text, keyboard = important_days.start_delete_confirm(db, store, TELEGRAM_USER_ID, USER_ID, 1)

    assert "找不到" in text
    assert store.get(TELEGRAM_USER_ID) is None


def test_delete_confirm_then_execute_removes_row():
    db = FakeDatabase()
    db.tables["important_days"] = [
        {"id": 1, "owner_user_id": USER_ID, "title": "要刪除的事件"},
    ]
    store = ConversationStateStore()

    text, keyboard = important_days.start_delete_confirm(db, store, TELEGRAM_USER_ID, USER_ID, 1)
    assert "確定要刪除" in text
    assert store.get(TELEGRAM_USER_ID)["flow"] == "important_days_delete_confirm"

    reply, _ = important_days.handle_delete(db, store, TELEGRAM_USER_ID, USER_ID, 1)

    assert reply == "已刪除該筆重要日子。"
    assert db.tables["important_days"] == []
    assert store.get(TELEGRAM_USER_ID) is None


def test_delete_confirm_state_ignores_typed_text_and_cancels():
    store = ConversationStateStore()
    store.set(TELEGRAM_USER_ID, {"flow": "important_days_delete_confirm", "target_id": 1})

    text, keyboard = important_days.handle_delete_confirm_text(store, TELEGRAM_USER_ID)

    assert "請用上面的按鈕" in text
    assert store.get(TELEGRAM_USER_ID) is None


def test_edit_flow_prefills_title_prompt_and_updates_existing_row():
    db = FakeDatabase()
    db.tables["important_days"] = [
        {"id": 1, "owner_user_id": USER_ID, "title": "舊名稱"},
    ]
    store = ConversationStateStore()

    prompt = important_days.start_edit(db, store, TELEGRAM_USER_ID, USER_ID, 1)
    assert "舊名稱" in prompt

    _run_step(db, store, "新名稱")
    _run_step(db, store, "1")
    _run_step(db, store, "1-1")
    _run_step(db, store, "1-1")
    _run_step(db, store, "是")
    _run_step(db, store, "1")
    _run_step(db, store, "1")
    _run_step(db, store, "略過")

    reply, _ = important_days.handle_confirm_save(db, store, TELEGRAM_USER_ID, USER_ID)

    assert reply == "已更新該筆重要日子！"
    assert len(db.tables["important_days"]) == 1
    assert db.tables["important_days"][0]["title"] == "新名稱"


def test_reminder_days_out_of_range_rejected():
    db = FakeDatabase()
    store = ConversationStateStore()
    important_days.start_add(store, TELEGRAM_USER_ID)
    _run_step(db, store, "名稱")
    _run_step(db, store, "1")
    _run_step(db, store, "1-1")
    _run_step(db, store, "1-1")
    _run_step(db, store, "是")

    text, keyboard = _run_step(db, store, "400")

    assert "0～365" in text
    assert store.get(TELEGRAM_USER_ID)["step"] == "awaiting_reminder_days"
