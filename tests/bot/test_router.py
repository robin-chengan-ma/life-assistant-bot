from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from PIL import Image

from src.bot import commands, menu, router, templates, voice
from src.bot.state import ConversationStateStore

ROBIN_ID = 8263904025
FAMILY_ID = 555
FAMILY_ID_2 = 556


class _FakeLLMClient:
    """模擬 submodules.llm.client.LLMClient，實作 chat.py 與對話流程使用的
    generate_text（2026-07-31 移除 generate_with_search，見 chat-core SPEC.md ADR-5）。"""

    def __init__(self, response_text="這是聊天核心的回答"):
        self.response_text = response_text
        self.last_prompt = None

    def generate_text(self, prompt):
        self.last_prompt = prompt
        return self.response_text


def _seed_pending_invite(fake_db, role="爸爸", code="secret123"):
    user_id = fake_db.insert("users", {"telegram_user_id": None, "role": role, "is_owner": False})
    fake_db.insert("invite_codes", {"code": code, "is_used": False, "user_id": user_id})
    return user_id


# --- 未知使用者 ---

def test_unknown_user_without_start_is_not_bound_even_with_correct_code(fake_db, monkeypatch):
    """FR-3：改為 /start 閘控後，沒按過 /start 就直接輸入正確密碼也不會被綁定，見下方
    test_start_then_correct_passcode_binds_user 才是完整成功流程。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    _seed_pending_invite(fake_db, code="secret123")
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "secret123")

    assert reply == router._NOT_BOUND_REPLY
    bound = fake_db.select("users", where="telegram_user_id = %s", params=(FAMILY_ID,), fetch_one=True)
    assert bound is None


def test_unknown_user_with_wrong_code_gets_prompt(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "wrong-code")

    assert "通關密碼" in reply


def test_unknown_user_with_empty_text_gets_prompt(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "")

    assert "通關密碼" in reply


# --- 已綁定的一般使用者 ---

def test_removed_slash_commands_fall_back_to_chat_core(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="我不太懂這個指令耶！")

    for command in ("/rule", "/my_toggles", "/set_toggle", "/set_family_birthday", "/friend_chat"):
        reply = router.handle_message(fake_db, store, FAMILY_ID, command, llm_client=llm_client)

        assert reply == "我不太懂這個指令耶！"
        assert store.get(FAMILY_ID) is None


def test_known_family_member_cannot_trigger_owner_only_setup_flow(fake_db, monkeypatch):
    """權限邊界測試：家人輸入 Owner 專屬指令，不應該被授予設定通關密碼的能力（改落入一般聊天核心）。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="我不太懂這個指令耶！")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "/set_invite_codes", llm_client=llm_client)

    assert reply == "我不太懂這個指令耶！"
    assert store.get(FAMILY_ID) is None


def test_known_family_member_other_text_gets_chat_core_reply(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="今天台北是晴天喔！")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "今天天氣如何", llm_client=llm_client)

    assert reply == "今天台北是晴天喔！"


def test_switching_to_menu_clears_short_chat_context(fake_db, monkeypatch):
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    cleared_user_ids = []
    monkeypatch.setattr(router.chat, "clear_short_context", cleared_user_ids.append)

    router.handle_callback_query(fake_db, store, FAMILY_ID, "menu:main")

    assert cleared_user_ids == [FAMILY_ID]


# --- Owner（Robin） ---

def test_owner_first_message_creates_owner_row(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()

    reply, _keyboard = router.handle_message(fake_db, store, ROBIN_ID, "/start")

    assert reply == menu.MAIN_MENU_TEXT
    owner_row = fake_db.select("users", where="telegram_user_id = %s", params=(ROBIN_ID,), fetch_one=True)
    assert owner_row is not None
    assert owner_row["is_owner"] is True


def test_start_shows_main_menu_for_owner(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()

    reply, keyboard = router.handle_message(fake_db, store, ROBIN_ID, "/start")

    assert reply == menu.MAIN_MENU_TEXT
    assert keyboard == menu.build_main_menu_keyboard(is_owner=True)
    owner_row = fake_db.select("users", where="telegram_user_id = %s", params=(ROBIN_ID,), fetch_one=True)
    assert owner_row is not None


def test_start_prompts_passcode_for_unbound_user(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "/start")

    assert reply == router._AWAITING_PASSCODE_REPLY
    assert store.get(FAMILY_ID) == {"flow": "awaiting_passcode"}


def test_passcode_only_accepted_right_after_start(fake_db, monkeypatch):
    """FR-3：沒按過 /start 就直接輸入密碼，不會被當成密碼驗證，只會拿到通用未綁定提示。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    _seed_pending_invite(fake_db, code="secret123")
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "secret123")

    assert reply == router._NOT_BOUND_REPLY
    bound = fake_db.select("users", where="telegram_user_id = %s", params=(FAMILY_ID,), fetch_one=True)
    assert bound is None


def test_start_then_correct_passcode_binds_user(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    _seed_pending_invite(fake_db, code="secret123")
    store = ConversationStateStore()

    router.handle_message(fake_db, store, FAMILY_ID, "/start")
    reply = router.handle_message(fake_db, store, FAMILY_ID, "secret123")

    assert reply == templates.APPENDIX_A_TEXT
    bound = fake_db.select("users", where="telegram_user_id = %s", params=(FAMILY_ID,), fetch_one=True)
    assert bound is not None
    assert store.get(FAMILY_ID) is None


def test_start_then_wrong_passcode_gets_bind_failed_reply(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    router.handle_message(fake_db, store, FAMILY_ID, "/start")
    reply = router.handle_message(fake_db, store, FAMILY_ID, "wrong-code")

    assert reply == router._PASSCODE_BIND_FAILED_REPLY


def test_start_shows_main_menu_for_bound_family_member(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply, keyboard = router.handle_message(fake_db, store, FAMILY_ID, "/start")

    assert reply == menu.MAIN_MENU_TEXT
    assert keyboard == menu.build_main_menu_keyboard(is_owner=False)


# --- 權限管理選單（FR-4，取代舊版 /set_invite_codes）---


def test_permission_create_flow_writes_new_user_and_invite(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, ROBIN_ID, "permission:create")
    assert keyboard is None
    assert store.get(ROBIN_ID) == {"flow": "permission_create", "step": "awaiting_family_title"}

    router.handle_message(fake_db, store, ROBIN_ID, "媽媽")
    assert store.get(ROBIN_ID)["step"] == "awaiting_nickname"

    reply = router.handle_message(fake_db, store, ROBIN_ID, "略過")

    assert "媽媽" in reply
    assert store.get(ROBIN_ID) is None
    new_user = fake_db.select("users", where="family_title = %s", params=("媽媽",), fetch_one=True)
    assert new_user is not None
    invite = fake_db.select(
        "invite_codes", where="user_id = %s AND is_used = FALSE", params=(new_user["id"],), fetch_one=True
    )
    assert invite is not None
    assert invite["expires_at"] is not None


def test_permission_disable_flow_deactivates_selected_user(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert(
        "users",
        {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False, "is_active": True, "nickname": "爸爸"},
    )
    store = ConversationStateStore()

    reply, _keyboard = router.handle_callback_query(fake_db, store, ROBIN_ID, "permission:disable")
    assert "爸爸" in reply

    router.handle_message(fake_db, store, ROBIN_ID, "1")

    updated = fake_db.select("users", where="telegram_user_id = %s", params=(FAMILY_ID,), fetch_one=True)
    assert updated["is_active"] is False
    assert store.get(ROBIN_ID) is None


def test_permission_menu_denied_for_non_owner(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "menu:permission")

    assert reply == router._PERMISSION_DENIED_REPLY


def test_set_invite_codes_command_no_longer_recognized(fake_db, monkeypatch):
    """`/set_invite_codes` 已於 2a 移除，Owner 輸入這串文字會直接落入一般聊天核心，不再是專屬指令。"""
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="我不太懂這個指令耶！")

    reply = router.handle_message(fake_db, store, ROBIN_ID, "/set_invite_codes", llm_client=llm_client)

    assert reply == "我不太懂這個指令耶！"
    assert store.get(ROBIN_ID) is None


# --- 功能開關（docs/specs/feature-toggles/SPEC.md）---


def test_family_member_binding_auto_creates_default_toggles(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    _seed_pending_invite(fake_db, code="secret123")
    store = ConversationStateStore()

    router.handle_message(fake_db, store, FAMILY_ID, "/start")
    router.handle_message(fake_db, store, FAMILY_ID, "secret123")

    bound = fake_db.select("users", where="telegram_user_id = %s", params=(FAMILY_ID,), fetch_one=True)
    rows = fake_db.select("feature_toggles", where="user_id = %s", params=(bound["id"],))
    assert len(rows) == 10


# --- 一般聊天核心（docs/specs/chat-core/SPEC.md）---


def test_known_family_member_general_message_routes_to_chat_core(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="記帳功能可以幫你記錄每天的花費喔！")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "記帳功能是什麼？", llm_client=llm_client)

    assert reply == "記帳功能可以幫你記錄每天的花費喔！"
    assert store.get(FAMILY_ID) is None


def test_owner_general_message_routes_to_chat_core(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="早安！")

    reply = router.handle_message(fake_db, store, ROBIN_ID, "早安", llm_client=llm_client)

    assert reply == "早安！"


def test_general_message_with_pii_gets_masked_and_reminder(fake_db, monkeypatch):
    # 2026-08-02（privacy-masking SPEC.md FR-4）：一般聊天訊息含個資時，經 router 分派後
    # 應該由 chat.handle_chat_message() 遮蔽並附加提醒，驗證 privacy_llm_client 有正確透傳。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="收到！")

    reply = router.handle_message(
        fake_db, store, FAMILY_ID, "我的手機是 0912345678", llm_client=llm_client,
    )

    assert "0912345678" not in llm_client.last_prompt
    assert "提醒" in reply


# --- 舊 /recovered 入口已移除（FR-20）---


class _FakeTelegramClientForRecovered:
    """模擬 submodules.telegram.client.TelegramClient，只實作 send_text（與下方 photo/voice
    測試用的 `_FakeTelegramClient`（只實作 `get_file_bytes`）刻意分開命名，避免同名覆蓋）。"""

    def __init__(self):
        self.sent = []

    def send_text(self, chat_id, text):
        self.sent.append((chat_id, text))


def test_recovered_command_is_no_longer_a_broadcast_for_owner(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "媽媽", "is_owner": False})
    store = ConversationStateStore()
    telegram_client = _FakeTelegramClientForRecovered()

    llm_client = _FakeLLMClient(response_text="請使用主選單。")
    reply = router.handle_message(
        fake_db, store, ROBIN_ID, "/recovered", telegram_client=telegram_client, llm_client=llm_client,
    )

    assert reply == "請使用主選單。"
    assert telegram_client.sent == []


def test_recovered_command_ignored_for_non_owner(fake_db, monkeypatch):
    # 非 Owner 傳「/recovered」不應該觸發廣播，只會落入一般聊天核心當成一般文字處理。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    telegram_client = _FakeTelegramClientForRecovered()
    llm_client = _FakeLLMClient(response_text="收到！")

    router.handle_message(
        fake_db, store, FAMILY_ID, "/recovered", llm_client=llm_client, telegram_client=telegram_client,
    )

    assert telegram_client.sent == []


# --- 待辦事項（robinson SPEC.md FR-31、FR-31a、FR-32，Step 1.7）---


def test_todo_menu_key_not_in_not_yet_implemented_set():
    """已完成的待辦、查詢與排程設定都不得留在「開發中」名單。"""
    assert not menu.is_not_yet_implemented("todo")
    assert not menu.is_not_yet_implemented("query")
    assert not menu.is_not_yet_implemented("schedule")


def test_todo_submenu_shows_list_and_add_buttons(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "menu:todo")

    assert "待辦事項" in reply
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "todo:list" in callback_datas
    assert "todo:add" in callback_datas


def test_todo_list_reports_empty_list(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "todo:list")

    assert reply == "目前沒有待辦事項喔！"
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "menu:todo"


def test_todo_full_flow_from_natural_language_to_creation(fake_db, monkeypatch):
    # 2026-08-02（Step 1.7，見 FR-31、FR-56e 情境範例；2026-08-16 Phase 6 第二批 2f 補上摘要→
    # 二次確認）：自然語言描述 → 確認要記錄 → 給時間 → 確認提醒設定 → 行事曆同步 → 按鈕確認送出，
    # 全程由 router 正確分派到 chat.py／commands.py。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    llm_client = _FakeLLMClient(response_text="要幫你紀錄到待辦事項嗎？【REQUEST_TODO】")
    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "我下午要去買菜", llm_client=llm_client)
    assert reply1 == "要幫你紀錄到待辦事項嗎？"
    assert store.get(FAMILY_ID)["flow"] == "pending_todo_confirm"

    llm_client.response_text = "CONFIRM"
    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "好", llm_client=llm_client)
    assert reply2 == "好的，請問是什麼時候呢？"
    assert store.get(FAMILY_ID)["flow"] == "pending_todo_time"

    llm_client.response_text = "STATUS: CLEAR\nCONTENT: 買菜\nDUE_AT: 2026-08-02 15:00"
    reply3 = router.handle_message(fake_db, store, FAMILY_ID, "三點", llm_client=llm_client)
    assert "2026/08/02 15:00" in reply3
    assert store.get(FAMILY_ID)["flow"] == "pending_todo_reminder"

    llm_client.response_text = "CONFIRM"
    reply4 = router.handle_message(fake_db, store, FAMILY_ID, "好", llm_client=llm_client)
    assert "同步到 Google 家庭行事曆" in reply4
    assert store.get(FAMILY_ID)["flow"] == "pending_todo_calendar_sync"

    # 2026-08-05（FR-66a、ADR-17）：多一輪同步詢問，這裡選擇不同步（calendar_client 沒有注入時
    # 也要能正常運作，模擬環境變數未設定的優雅降級情境）。
    llm_client.response_text = "CANCEL"
    reply5, keyboard5 = router.handle_message(fake_db, store, FAMILY_ID, "不用", llm_client=llm_client)
    assert "請確認以下待辦事項內容" in reply5
    assert "買菜" in reply5
    assert keyboard5["inline_keyboard"][0][0]["callback_data"] == "todo:confirm_save"
    assert store.get(FAMILY_ID)["flow"] == "pending_todo_confirm_save"
    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(user_id, "pending"))
    assert len(rows) == 0  # 還沒真正寫入，要等按下「✅ 確認送出」才寫入

    reply6, _keyboard6 = router.handle_callback_query(fake_db, store, FAMILY_ID, "todo:confirm_save")
    assert reply6 == "好的，已經幫你記錄好了！"
    assert store.get(FAMILY_ID) is None

    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(user_id, "pending"))
    assert len(rows) == 1
    assert rows[0]["content"] == "買菜"
    assert rows[0]["remind_before_30min"] is True
    assert rows[0]["sync_to_calendar"] is False


def test_todo_add_button_skips_confirm_step_and_asks_content(fake_db, monkeypatch):
    # 2026-08-16（Phase 6 第二批 2f）：選單「➕ 新增」按鈕略過「要不要記錄」這輪反問，
    # 先問「要記什麼事」，才接到既有的時間反問，跟自然語言入口共用同一套狀態機。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "todo:add")
    assert keyboard is None
    assert "要記什麼事" in reply
    assert store.get(FAMILY_ID)["flow"] == "pending_todo_new_content"

    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "買菜")
    assert reply2 == "好的，請問是什麼時候呢？"
    assert store.get(FAMILY_ID) == {"flow": "pending_todo_time", "target_user_id": store.get(FAMILY_ID)["target_user_id"], "original_text": "買菜"}


def test_todo_confirm_save_typed_text_cancels_flow(fake_db, monkeypatch):
    # pending_todo_confirm_save 只接受按鈕，打字比照 2b～2e 的保守做法直接取消並導回主選單。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(FAMILY_ID, {
        "flow": "pending_todo_confirm_save", "target_user_id": user_id, "content": "買菜",
        "due_at": datetime(2026, 8, 2, 15, 0, tzinfo=timezone.utc), "start_at": None,
        "remind_before_30min": True, "sync_to_calendar": False,
    })

    reply, keyboard = router.handle_message(fake_db, store, FAMILY_ID, "隨便打字")

    assert "先幫你取消了" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "menu:main"
    assert store.get(FAMILY_ID) is None
    assert fake_db.select("todos", where="user_id = %s", params=(user_id,)) == []


def test_todo_list_marks_completed_via_button(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    due_at = datetime(2026, 8, 2, 7, 0, tzinfo=timezone.utc)
    todo_id = fake_db.insert(
        "todos",
        {"user_id": user_id, "content": "買菜", "due_at": due_at, "remind_before_30min": False, "status": "pending"},
    )
    store = ConversationStateStore()

    reply1, keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "todo:list")
    assert "買菜" in reply1
    assert keyboard1["inline_keyboard"][0][0]["callback_data"] == f"todo:complete:{todo_id}"

    reply2, _keyboard2 = router.handle_callback_query(fake_db, store, FAMILY_ID, f"todo:complete:{todo_id}")
    assert "完成" in reply2
    assert fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)["status"] == "completed"


def test_todo_list_rejects_other_users_todo_via_forged_callback(fake_db, monkeypatch):
    # FR-6c：偽造/過期的 callback_data 想標記別人的待辦事項，重新查一次 user_id 要擋下來。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    other_user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID_2, "role": "媽媽", "is_owner": False})
    due_at = datetime(2026, 8, 2, 7, 0, tzinfo=timezone.utc)
    todo_id = fake_db.insert(
        "todos",
        {"user_id": other_user_id, "content": "別人的待辦", "due_at": due_at, "remind_before_30min": False, "status": "pending"},
    )
    store = ConversationStateStore()

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, f"todo:complete:{todo_id}")

    assert "找不到" in reply
    assert fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)["status"] == "pending"


# --- 心情小記（robinson SPEC.md FR-49、FR-50；2026-08-16 Phase 6 第二批 2c 改為全選單觸發，
# 見 docs/ADR/discuss/robinson.md）---


def test_daily_log_submenu_shows_mood_and_exercise_buttons(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "menu:daily_log")

    assert reply == menu.DAILY_LOG_MENU_TEXT
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "daily_log:mood" in callback_datas
    assert "daily_log:exercise" in callback_datas
    assert "daily_log:diet" in callback_datas


def test_daily_log_finance_starts_finance_menu(fake_db, monkeypatch):
    """2026-08-18（批次5）：finance 已接上真正邏輯，`daily_log:finance` 進入記帳子選單，日常紀錄
    五個子項目至此全數接上真正邏輯，跟 body（2h）／diet（2g）一致。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "daily_log:finance")

    assert "記帳" in reply
    callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "finance:budget" in callbacks


def test_daily_log_body_starts_body_menu(fake_db, monkeypatch):
    """2026-08-17（Phase 6 第二批 2h）：body 已接上真正邏輯，`daily_log:body` 進入體態子選單，
    完整流程見 tests/bot/test_body_router.py。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "daily_log:body")

    assert "體態" in reply
    callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "body:height" in callbacks


def test_daily_log_diet_starts_diet_menu(fake_db, monkeypatch):
    """2026-08-16（Phase 6 第二批 2g）：diet 已接上真正邏輯，`daily_log:diet` 進入飲食子選單。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "daily_log:diet")

    assert "飲食紀錄" in reply
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "diet:new" in callback_datas


def test_mood_journal_full_flow_records_entry_and_achievement(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply0, keyboard0 = router.handle_callback_query(fake_db, store, FAMILY_ID, "daily_log:mood")
    assert reply0 == "心情，請選擇要進行的操作："
    assert keyboard0["inline_keyboard"][0][0]["callback_data"] == "mood:new"

    reply1, keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "mood:new")
    assert keyboard1 is None
    assert "請幫我選一個" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_category"

    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "高興/興奮")
    assert reply2 == "給我完整的日記內容："
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_content"

    reply3, keyboard3 = router.handle_message(fake_db, store, FAMILY_ID, "今天很開心")
    assert "請確認以下內容" in reply3
    assert keyboard3["inline_keyboard"][0][0]["callback_data"] == "mood:confirm_save"
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_confirm"

    reply4, _keyboard4 = router.handle_callback_query(fake_db, store, FAMILY_ID, "mood:confirm_save")
    assert "已經紀錄了" in reply4
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_achievement"

    reply5 = router.handle_message(fake_db, store, FAMILY_ID, "完成了一份報告")
    assert reply5 == "已經幫你記錄好了！"
    assert store.get(FAMILY_ID) is None

    rows = fake_db.select("mood_journals", where="user_id = %s AND mood_category = %s", params=(user_id, "happy_excited"))
    assert len(rows) == 1
    assert rows[0]["content"] == "今天很開心"
    assert rows[0]["achievement_note"] == "完成了一份報告"


def test_mood_journal_achievement_can_be_skipped(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "mood:new")
    router.handle_message(fake_db, store, FAMILY_ID, "1")
    router.handle_message(fake_db, store, FAMILY_ID, "今天有點低落")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "mood:confirm_save")
    reply = router.handle_message(fake_db, store, FAMILY_ID, "結束")

    assert reply == "好的，那先這樣吧！"
    rows = fake_db.select("mood_journals")
    assert rows[0]["achievement_note"] is None


def test_mood_journal_confirm_step_rejects_stray_text(fake_db, monkeypatch):
    """2026-08-16（Phase 6 第二批 2c）：摘要確認這一步只接受按鈕，打字要優雅取消而不是拋例外。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "mood:new")
    router.handle_message(fake_db, store, FAMILY_ID, "1")
    router.handle_message(fake_db, store, FAMILY_ID, "今天有點低落")
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_confirm"

    reply, keyboard = router.handle_message(fake_db, store, FAMILY_ID, "亂打字")

    assert "請用上面的按鈕" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "menu:daily_log"
    assert store.get(FAMILY_ID) is None
    assert fake_db.select("mood_journals") == []


def test_mood_backfill_full_flow_records_entry_with_given_date(fake_db, monkeypatch):
    """2026-08-02 追加（FR-49 補記擴充）：「補記」按鈕先問哪一天，再走既有分類/內容流程。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply1, keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "mood:backfill")
    assert keyboard1 is None
    assert "哪一天" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_backfill_date"

    date_llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nDATE: 2026-07-30")
    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "前天", llm_client=date_llm_client)
    assert "請幫我選一個" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_category"

    router.handle_message(fake_db, store, FAMILY_ID, "2")
    router.handle_message(fake_db, store, FAMILY_ID, "那天有點難過")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "mood:confirm_save")
    reply4 = router.handle_message(fake_db, store, FAMILY_ID, "結束")

    assert reply4 == "好的，那先這樣吧！"
    rows = fake_db.select("mood_journals")
    assert rows[0]["entry_date"].isoformat() == "2026-07-30"
    assert rows[0]["mood_category"] == "sad_down"


def test_mood_list_update_and_delete_full_flow(fake_db, monkeypatch):
    """2026-08-02 追加（FR-49 更新/刪除擴充；2026-08-16 改成選單按鈕觸發）：「查看清單」列出、
    選一筆編輯、再查一次、選同一筆刪除（走摘要確認／刪除確認兩顆按鈕）。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    journal_id = fake_db.insert(
        "mood_journals",
        {
            "user_id": user_id,
            "mood_category": "sad_down",
            "content": "原本內容",
            "achievement_note": None,
            "entry_date": date(2026, 8, 1),
        },
    )
    store = ConversationStateStore()

    _reply1, keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "mood:list")
    callback_datas = [button["callback_data"] for row in keyboard1["inline_keyboard"] for button in row]
    assert f"mood:edit:{journal_id}" in callback_datas
    assert f"mood:delete:{journal_id}" in callback_datas

    reply2, _keyboard2 = router.handle_callback_query(fake_db, store, FAMILY_ID, f"mood:edit:{journal_id}")
    assert "請幫我選一個" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_category"

    router.handle_message(fake_db, store, FAMILY_ID, "6")
    router.handle_message(fake_db, store, FAMILY_ID, "改過的內容")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "mood:confirm_save")
    router.handle_message(fake_db, store, FAMILY_ID, "結束")

    rows = fake_db.select("mood_journals")
    assert len(rows) == 1
    assert rows[0]["content"] == "改過的內容"
    assert rows[0]["mood_category"] == "happy_excited"

    router.handle_callback_query(fake_db, store, FAMILY_ID, "mood:list")
    reply_delete_ask, keyboard_delete = router.handle_callback_query(
        fake_db, store, FAMILY_ID, f"mood:delete:{journal_id}"
    )
    assert "沒辦法復原" in reply_delete_ask
    assert keyboard_delete["inline_keyboard"][0][0]["callback_data"] == f"mood:confirm_delete:{journal_id}"
    assert store.get(FAMILY_ID)["flow"] == "mood_delete_confirm"

    reply_deleted, _keyboard = router.handle_callback_query(
        fake_db, store, FAMILY_ID, f"mood:confirm_delete:{journal_id}"
    )
    assert "已經刪除" in reply_deleted
    assert fake_db.select("mood_journals") == []


def test_mood_delete_only_owner_can_target_own_journal(fake_db, monkeypatch):
    """FR-6c：`mood:delete:<id>`／`mood:confirm_delete:<id>` 都要重新驗證擁有者。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    other_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID_2, "role": "媽媽", "is_owner": False})
    journal_id = fake_db.insert(
        "mood_journals",
        {
            "user_id": other_id,
            "mood_category": "sad_down",
            "content": "別人的心情",
            "achievement_note": None,
            "entry_date": date(2026, 8, 1),
        },
    )
    store = ConversationStateStore()

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, f"mood:delete:{journal_id}")
    assert "找不到" in reply


# --- 運動（robinson SPEC.md FR-47；2026-08-16 Phase 6 第二批 2c 新增選單流程，
# 見 docs/ADR/discuss/robinson.md）---


def test_exercise_new_flow_records_entry_with_confirm_gate(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    category_id = fake_db.insert("exercise_categories", {"name": "跑步", "normalized_name": "跑步"})
    store = ConversationStateStore()

    reply0, keyboard0 = router.handle_callback_query(fake_db, store, FAMILY_ID, "daily_log:exercise")
    assert reply0 == "運動，請選擇要進行的操作："
    assert keyboard0["inline_keyboard"][0][0]["callback_data"] == "exercise:new"

    reply1, _keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "exercise:new")
    assert "選擇類別" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_category"

    _reply1b, _keyboard1b = router.handle_callback_query(fake_db, store, FAMILY_ID, f"exercise:cat:{category_id}")
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_duration"

    reply2, _keyboard2 = router.handle_message(fake_db, store, FAMILY_ID, "30")
    assert "心率" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_heart_rate"

    reply3, _keyboard3 = router.handle_message(fake_db, store, FAMILY_ID, "skip")
    assert "補充" in reply3
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_note"

    _reply3b, keyboard3b = router.handle_message(fake_db, store, FAMILY_ID, "skip")
    assert "AI 估算" in keyboard3b["inline_keyboard"][0][0]["text"]
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_calorie_choice"

    _reply4, keyboard4 = router.handle_callback_query(fake_db, store, FAMILY_ID, "exercise:calorie:ai")
    assert keyboard4["inline_keyboard"][0][0]["callback_data"] == "exercise:confirm_save"
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_confirm"

    reply5, _keyboard5 = router.handle_callback_query(fake_db, store, FAMILY_ID, "exercise:confirm_save")
    assert "已經" in reply5
    assert store.get(FAMILY_ID) is None

    rows = fake_db.select("exercise_logs", where="user_id = %s", params=(user_id,))
    assert len(rows) == 1
    assert rows[0]["activity"] == "跑步"
    assert rows[0]["category_id"] == category_id
    assert rows[0]["duration_minutes"] == 30


def test_exercise_confirm_step_rejects_stray_text(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    category_id = fake_db.insert("exercise_categories", {"name": "跑步", "normalized_name": "跑步"})
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "exercise:new")
    router.handle_callback_query(fake_db, store, FAMILY_ID, f"exercise:cat:{category_id}")
    router.handle_message(fake_db, store, FAMILY_ID, "30")
    router.handle_message(fake_db, store, FAMILY_ID, "skip")
    router.handle_message(fake_db, store, FAMILY_ID, "skip")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "exercise:calorie:ai")
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_confirm"

    reply, keyboard = router.handle_message(fake_db, store, FAMILY_ID, "亂打字")

    assert "請用上面的按鈕" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "menu:daily_log"
    assert store.get(FAMILY_ID) is None
    assert fake_db.select("exercise_logs") == []


def test_exercise_list_edit_and_delete_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    category_id = fake_db.insert("exercise_categories", {"name": "游泳", "normalized_name": "游泳"})
    other_category_id = fake_db.insert("exercise_categories", {"name": "跑步", "normalized_name": "跑步"})
    exercise_log_id = fake_db.insert(
        "exercise_logs",
        {
            "user_id": user_id,
            "category_id": category_id,
            "activity": "游泳",
            "duration_minutes": 20,
            "heart_rate": None,
            "note": None,
            "calorie_source": "ai",
            "estimated_calories": None,
            "entry_date": date(2026, 8, 1),
        },
    )
    store = ConversationStateStore()

    _reply1, keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "exercise:list")
    callback_datas = [button["callback_data"] for row in keyboard1["inline_keyboard"] for button in row]
    assert f"exercise:edit:{exercise_log_id}" in callback_datas
    assert f"exercise:delete:{exercise_log_id}" in callback_datas

    router.handle_callback_query(fake_db, store, FAMILY_ID, f"exercise:edit:{exercise_log_id}")
    assert store.get(FAMILY_ID)["flow"] == "pending_exercise_category"
    router.handle_callback_query(fake_db, store, FAMILY_ID, f"exercise:cat:{other_category_id}")
    router.handle_message(fake_db, store, FAMILY_ID, "45")
    router.handle_message(fake_db, store, FAMILY_ID, "skip")
    router.handle_message(fake_db, store, FAMILY_ID, "skip")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "exercise:calorie:ai")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "exercise:confirm_save")

    rows = fake_db.select("exercise_logs")
    assert len(rows) == 1
    assert rows[0]["activity"] == "跑步"
    assert rows[0]["category_id"] == other_category_id
    assert rows[0]["duration_minutes"] == 45

    router.handle_callback_query(fake_db, store, FAMILY_ID, "exercise:list")
    reply_delete_ask, keyboard_delete = router.handle_callback_query(
        fake_db, store, FAMILY_ID, f"exercise:delete:{exercise_log_id}"
    )
    assert "沒辦法復原" in reply_delete_ask
    assert keyboard_delete["inline_keyboard"][0][0]["callback_data"] == f"exercise:confirm_delete:{exercise_log_id}"
    assert store.get(FAMILY_ID)["flow"] == "exercise_delete_confirm"

    reply_deleted, _keyboard = router.handle_callback_query(
        fake_db, store, FAMILY_ID, f"exercise:confirm_delete:{exercise_log_id}"
    )
    assert "已經刪除" in reply_deleted
    assert fake_db.select("exercise_logs") == []


def test_exercise_delete_only_owner_can_target_own_log(fake_db, monkeypatch):
    """FR-6c：`exercise:delete:<id>`／`exercise:confirm_delete:<id>` 都要重新驗證擁有者。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    other_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID_2, "role": "媽媽", "is_owner": False})
    exercise_log_id = fake_db.insert(
        "exercise_logs",
        {
            "user_id": other_id,
            "activity": "別人的運動",
            "duration_minutes": 10,
            "heart_rate": None,
            "estimated_calories": None,
            "entry_date": date(2026, 8, 1),
        },
    )
    store = ConversationStateStore()

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, f"exercise:delete:{exercise_log_id}")
    assert "找不到" in reply


# --- 記帳（robinson SPEC.md FR-41～FR-44，Step 2.1）---


def test_finance_menu_shows_buttons(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:menu")

    assert "記帳" in reply
    callbacks = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert callbacks == [
        "finance:budget", "finance:add", "finance:backfill", "finance:list", "finance:summary",
        "finance:goal", "menu:daily_log",
    ]


def test_finance_set_budget_full_flow_global_scope(fake_db, monkeypatch):
    """FR-41a：選「全部月份」，第一次設定沒有舊值，直接問金額。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply1, _keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:budget")
    assert "全部月份" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_finance_budget_scope"

    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "1")
    assert "每月支出預算上限" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_finance_budget_amount"

    reply3 = router.handle_message(fake_db, store, FAMILY_ID, "15000")
    assert "15000 元" in reply3
    assert store.get(FAMILY_ID) is None


def test_finance_set_budget_full_flow_months_scope_with_override_confirm(fake_db, monkeypatch):
    """FR-41a：選「只套用某幾個月」，指定的月份已有舊覆蓋值時要先反問確認才能改（2026-08-18
    批次5改成按鈕確認，不再是自由文字 LLM CONFIRM/CANCEL）。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    commands.finance.set_budget_override(fake_db, user_id, 2026, 8, 43000)
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:budget")
    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "2")
    assert "幾月" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_finance_budget_months"

    reply2, keyboard2 = router.handle_message(fake_db, store, FAMILY_ID, "8,9")
    assert "8月：43000 元" in reply2
    assert keyboard2["inline_keyboard"][0][0]["callback_data"] == "finance:budget_override_confirm_save"
    assert store.get(FAMILY_ID)["flow"] == "pending_finance_budget_override_confirm"

    reply3, _keyboard3 = router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:budget_override_confirm_save")
    assert "多少金額" in reply3
    assert store.get(FAMILY_ID)["flow"] == "pending_finance_budget_amount"

    reply4 = router.handle_message(fake_db, store, FAMILY_ID, "50000")
    assert "8月、9月" in reply4
    assert store.get(FAMILY_ID) is None
    assert commands.finance.get_budget_override(fake_db, user_id, 2026, 8) == 50000.0
    assert commands.finance.get_budget_override(fake_db, user_id, 2026, 9) == 50000.0


def test_finance_set_budget_global_scope_with_existing_value_asks_confirm(fake_db, monkeypatch):
    """FR-41a：選「全部月份」，全局預設已有舊值時先反問確認（2026-08-18 批次5改成按鈕確認）。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    commands.finance.set_monthly_budget(fake_db, user_id, 15000)
    store = ConversationStateStore()

    router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:budget")
    reply1, keyboard1 = router.handle_message(fake_db, store, FAMILY_ID, "1")
    assert "15000 元" in reply1
    assert keyboard1["inline_keyboard"][0][0]["callback_data"] == "finance:budget_confirm_save"
    assert store.get(FAMILY_ID)["flow"] == "pending_finance_budget_global_confirm"

    reply2, _keyboard2 = router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:budget_confirm_save")
    assert "多少" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_finance_budget_amount"

    reply3 = router.handle_message(fake_db, store, FAMILY_ID, "20000")
    assert "20000 元" in reply3
    assert commands.finance.get_monthly_budget(fake_db, user_id) == 20000.0


def test_finance_add_transaction_full_flow_records_entry_only_after_confirm(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply1, _keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:add")
    assert "1. 支出" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_transaction_type"

    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "支出")
    assert "1. 餐飲" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_transaction_category"

    reply3 = router.handle_message(fake_db, store, FAMILY_ID, "1")
    assert reply3 == "請問金額是多少呢？（例如：120）"
    assert store.get(FAMILY_ID)["flow"] == "pending_transaction_amount"

    reply4 = router.handle_message(fake_db, store, FAMILY_ID, "120")
    assert "備註" in reply4
    assert store.get(FAMILY_ID)["flow"] == "pending_transaction_note"

    reply5, keyboard5 = router.handle_message(fake_db, store, FAMILY_ID, "午餐")
    assert "請確認以下內容" in reply5
    assert keyboard5["inline_keyboard"][0][0]["callback_data"] == "finance:confirm_save"
    assert store.get(FAMILY_ID)["flow"] == "pending_transaction_confirm"
    assert fake_db.select("transactions", where="user_id = %s", params=(user_id,)) == []  # 確認前不寫入

    reply6, _keyboard6 = router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:confirm_save")
    assert reply6.startswith("已經幫你記錄好了！")
    assert store.get(FAMILY_ID) is None

    rows = fake_db.select("transactions", where="user_id = %s", params=(user_id,))
    assert len(rows) == 1
    assert rows[0]["category"] == "餐飲"
    assert rows[0]["amount"] == 120.0
    assert rows[0]["note"] == "午餐"


def test_finance_backfill_full_flow_records_entry_with_given_date(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply1, _keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:backfill")
    assert "哪一天" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_transaction_backfill_date"

    date_llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nDATE: 2026-08-01")
    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "前天", llm_client=date_llm_client)
    assert "1. 支出" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_transaction_type"

    router.handle_message(fake_db, store, FAMILY_ID, "收入")
    router.handle_message(fake_db, store, FAMILY_ID, "薪資")
    router.handle_message(fake_db, store, FAMILY_ID, "50000")
    router.handle_message(fake_db, store, FAMILY_ID, "沒有")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:confirm_save")

    rows = fake_db.select("transactions")
    assert rows[0]["transaction_date"].isoformat() == "2026-08-01"
    assert rows[0]["type"] == "income"
    assert rows[0]["category"] == "薪資"


def test_finance_list_edit_and_delete_full_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    transaction_id = fake_db.insert(
        "transactions",
        {
            "user_id": user_id,
            "type": "expense",
            "category": "餐飲",
            "amount": 100,
            "note": None,
            "transaction_date": date(2026, 8, 1),
        },
    )
    store = ConversationStateStore()

    reply1, keyboard1 = router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:list")
    assert "2026/08/01" in reply1
    buttons = keyboard1["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == f"finance:edit:{transaction_id}"
    assert buttons[1]["callback_data"] == f"finance:delete:{transaction_id}"

    reply2, _keyboard2 = router.handle_callback_query(fake_db, store, FAMILY_ID, f"finance:edit:{transaction_id}")
    assert "重新選一次交易類型" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_transaction_type"

    router.handle_message(fake_db, store, FAMILY_ID, "支出")
    router.handle_message(fake_db, store, FAMILY_ID, "交通")
    router.handle_message(fake_db, store, FAMILY_ID, "50")
    router.handle_message(fake_db, store, FAMILY_ID, "沒有")
    router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:confirm_save")

    rows = fake_db.select("transactions")
    assert len(rows) == 1
    assert rows[0]["category"] == "交通"
    assert rows[0]["amount"] == 50.0

    reply3, keyboard3 = router.handle_callback_query(fake_db, store, FAMILY_ID, f"finance:delete:{transaction_id}")
    assert "沒辦法復原" in reply3
    assert keyboard3["inline_keyboard"][0][0]["callback_data"] == f"finance:confirm_delete:{transaction_id}"
    assert store.get(FAMILY_ID)["flow"] == "finance_transaction_delete_confirm"

    reply4, _keyboard4 = router.handle_callback_query(fake_db, store, FAMILY_ID, f"finance:confirm_delete:{transaction_id}")
    assert "已經刪除" in reply4
    assert fake_db.select("transactions") == []


def test_finance_summary_returns_text_without_flow(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    fake_db.insert(
        "transactions",
        {
            "user_id": user_id,
            "type": "expense",
            "category": "餐飲",
            "amount": 100,
            "note": None,
            "transaction_date": datetime.now(timezone.utc).date(),
        },
    )
    store = ConversationStateStore()

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "finance:summary")

    assert "記帳摘要" in reply
    assert store.get(FAMILY_ID) is None


# --- 客訴收集（robinson SPEC.md FR-60～FR-63，Step 1.9）---


class _FakeImageLLMClient:
    def __init__(self, response_text="這是一張貓咪的照片"):
        self.response_text = response_text
        self.last_prompt = None
        self.last_image_bytes = None

    def generate_with_image(self, prompt, image_bytes, mime_type="image/jpeg"):
        self.last_prompt = prompt
        self.last_image_bytes = image_bytes
        return self.response_text


class _FakeGDriveClient:
    def __init__(self, url="https://drive.google.com/file/d/fake/view"):
        self.url = url

    def upload_file(self, filename, content, mime_type):
        return self.url


def _make_test_image_bytes() -> bytes:
    image_obj = Image.new("RGB", (200, 150), color=(255, 0, 0))
    buffer = BytesIO()
    image_obj.save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeTelegramClient:
    def __init__(self, file_bytes=None):
        self.file_bytes = file_bytes if file_bytes is not None else _make_test_image_bytes()
        self.last_file_id = None

    def get_file_bytes(self, file_id):
        self.last_file_id = file_id
        return self.file_bytes


def test_handle_photo_message_rejects_unbound_family_member(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    reply = router.handle_photo_message(
        fake_db, store, FAMILY_ID, "file123", None, _FakeTelegramClient(), _FakeGDriveClient(), []
    )

    assert "通關密碼" in reply


def test_handle_photo_message_happy_path_for_known_family_member(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    telegram_client = _FakeTelegramClient()
    llm_client = _FakeImageLLMClient(response_text="這是一盤義大利麵")

    reply = router.handle_photo_message(
        fake_db, store, FAMILY_ID, "file123", "這是什麼？", telegram_client, _FakeGDriveClient(), [llm_client]
    )

    assert reply == "這是一盤義大利麵"
    assert telegram_client.last_file_id == "file123"
    rows = fake_db.select("media_uploads")
    assert len(rows) == 1
    assert rows[0]["media_type"] == "image"


def test_handle_photo_message_works_for_owner(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()
    llm_client = _FakeImageLLMClient(response_text="這是羅賓森本人")

    reply = router.handle_photo_message(
        fake_db, store, ROBIN_ID, "file999", None, _FakeTelegramClient(), _FakeGDriveClient(), [llm_client]
    )

    assert reply == "這是羅賓森本人"
    owner_row = fake_db.select("users", where="telegram_user_id = %s", params=(ROBIN_ID,), fetch_one=True)
    assert owner_row is not None


def test_handle_photo_message_clears_stale_pending_flow_first(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(FAMILY_ID, {"flow": "pending_mood_content", "target_user_id": 1})
    llm_client = _FakeImageLLMClient(response_text="新的一張圖")

    reply = router.handle_photo_message(
        fake_db, store, FAMILY_ID, "file123", None, _FakeTelegramClient(), _FakeGDriveClient(), [llm_client]
    )

    assert reply == "新的一張圖"
    assert store.get(FAMILY_ID) is None


def test_pending_image_confirm_flow_continues_via_router(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeImageLLMClient(response_text="確認後：這是茄子")
    store.set(
        FAMILY_ID,
        {
            "flow": "pending_image_confirm",
            "image_bytes": b"fake-compressed-bytes",
            "original_caption": "這是什麼食材？",
            "target_user_id": 1,
            "llm_client_index": 0,
        },
    )

    reply = router.handle_message(
        fake_db, store, FAMILY_ID, "是紫色的那個", image_llm_clients=[llm_client]
    )

    assert reply == "確認後：這是茄子"
    assert store.get(FAMILY_ID) is None


# --- 語音辨識（robinson SPEC.md FR-14、FR-15、Step 1.4）---


class _FakeVoiceClient:
    def __init__(self, response_text="我要記帳"):
        self.response_text = response_text
        self.last_audio_bytes = None
        self.last_filename = None
        self.last_mime_type = None

    def transcribe(self, audio_bytes, filename="audio.ogg", mime_type="audio/ogg"):
        self.last_audio_bytes = audio_bytes
        self.last_filename = filename
        self.last_mime_type = mime_type
        return self.response_text


def test_handle_voice_message_rejects_unbound_family_member(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    store = ConversationStateStore()

    reply = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice123", 30,
        _FakeTelegramClient(b"raw-ogg"), _FakeGDriveClient(), _FakeVoiceClient(),
    )

    assert "通關密碼" in reply


def test_handle_voice_message_rejects_when_over_duration_limit(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    telegram_client = _FakeTelegramClient(b"raw-ogg")

    reply = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice123", 601,
        telegram_client, _FakeGDriveClient(), _FakeVoiceClient(),
    )

    assert reply == router._VOICE_DURATION_LIMIT_REPLY
    assert telegram_client.last_file_id is None  # 超過上限不該去下載語音檔
    assert fake_db.select("media_uploads") == []


# --- FR-14 規則 1：單次語音超過 10 分鐘觸發 15 分鐘全面鎖定（2026-08-02 追加，與 FR-15 修正窗口是獨立規則）---


def test_handle_voice_message_marks_lockout_when_over_duration_limit(fake_db, monkeypatch):
    # 超時的這一則本身照樣被 FR-14 擋下，但這次還要記錄鎖定時間點，供下一則語音判斷。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    lockout_store = ConversationStateStore()
    telegram_client = _FakeTelegramClient(b"raw-ogg")

    reply = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice123", 601,
        telegram_client, _FakeGDriveClient(), _FakeVoiceClient(),
        voice_lockout_store=lockout_store,
    )

    assert reply == router._VOICE_DURATION_LIMIT_REPLY
    assert voice.is_locked_out_from_duration_violation(lockout_store, FAMILY_ID) is True


def test_handle_voice_message_rejects_subsequent_voice_within_lockout_even_if_short(fake_db, monkeypatch):
    # 鎖定期間內，即使這次語音長度完全合法（沒超過 10 分鐘），也一樣要被拒絕——
    # 鎖定的是「語音功能整體」，不是只針對超時的那一則。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    lockout_store = ConversationStateStore()
    voice.mark_duration_violation(lockout_store, FAMILY_ID)
    telegram_client = _FakeTelegramClient(b"raw-ogg")

    reply = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice456", 30,
        telegram_client, _FakeGDriveClient(), _FakeVoiceClient(),
        voice_lockout_store=lockout_store,
    )

    assert reply == router._VOICE_DURATION_LOCKOUT_REPLY
    assert telegram_client.last_file_id is None  # 鎖定中不該去下載語音檔
    assert fake_db.select("media_uploads") == []


def test_handle_voice_message_allows_voice_again_after_lockout_expires(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    lockout_store = ConversationStateStore()
    voice.mark_duration_violation(lockout_store, FAMILY_ID, now=datetime.now(timezone.utc) - timedelta(minutes=16))
    voice_client = _FakeVoiceClient(response_text="我要記帳")

    reply, keyboard = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice789", 30,
        _FakeTelegramClient(b"raw-ogg"), _FakeGDriveClient(), voice_client,
        voice_lockout_store=lockout_store,
    )

    # 2026-08-16（全站語音確認機制）：轉錄成功先貼出文字＋確認按鈕，不直接分派；
    # 按下「✅ 正確，繼續」後才真的接回原本流程並拿到最終回覆。
    assert "我要記帳" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "voice_confirm:accept"
    assert voice_client.last_audio_bytes == b"raw-ogg"

    final_reply, _final_keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "voice_confirm:accept")
    assert final_reply == "要進入「記帳」功能嗎？"


def test_handle_voice_message_does_not_enforce_lockout_when_store_not_provided(fake_db, monkeypatch):
    # 呼叫端沒傳 voice_lockout_store（例如既有測試不關心這個行為）時，等同停用這個檢查，
    # 不會因為缺少這個參數就意外炸掉或誤鎖。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    voice_client = _FakeVoiceClient(response_text="我要記帳")

    reply, keyboard = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice999", 30,
        _FakeTelegramClient(b"raw-ogg"), _FakeGDriveClient(), voice_client,
    )

    assert "我要記帳" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "voice_confirm:accept"

    final_reply, _final_keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "voice_confirm:accept")
    assert final_reply == "要進入「記帳」功能嗎？"


def test_handle_voice_message_allows_immediate_rerecording(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    fake_db.insert(
        "media_uploads",
        {
            "user_id": user_id,
            "media_type": "audio",
            "gdrive_url": "https://drive/prev",
            "created_at": datetime.now(timezone.utc),
        },
    )
    store = ConversationStateStore()
    telegram_client = _FakeTelegramClient(b"raw-ogg")

    reply, keyboard = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice123", 30,
        telegram_client, _FakeGDriveClient(), _FakeVoiceClient(),
    )

    assert "我聽到的內容" in reply
    assert keyboard is not None
    assert telegram_client.last_file_id == "voice123"
    assert len(fake_db.select("media_uploads")) == 2


def test_handle_uploaded_audio_ignores_voice_duration_limit(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    telegram_client = _FakeTelegramClient(b"long-audio")

    reply, keyboard = router.handle_voice_message(
        fake_db,
        store,
        FAMILY_ID,
        "audio123",
        3600,
        telegram_client,
        _FakeGDriveClient(),
        _FakeVoiceClient(),
        mime_type="audio/mpeg",
        is_uploaded_audio=True,
    )

    assert "我聽到的內容" in reply
    assert keyboard is not None
    assert telegram_client.last_file_id == "audio123"


def test_handle_voice_message_transcribes_and_routes_as_text(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    telegram_client = _FakeTelegramClient(b"raw-ogg-bytes")
    voice_client = _FakeVoiceClient(response_text="我要記帳")

    reply, keyboard = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice123", 30,
        telegram_client, _FakeGDriveClient(), voice_client,
    )

    # 2026-08-16（全站語音確認機制）：轉錄成功先貼出文字＋確認按鈕請使用者確認，不直接分派。
    assert "我要記帳" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "voice_confirm:accept"
    assert telegram_client.last_file_id == "voice123"
    assert voice_client.last_audio_bytes == b"raw-ogg-bytes"
    rows = fake_db.select("media_uploads")
    assert len(rows) == 1
    assert rows[0]["media_type"] == "audio"

    # 按下「✅ 正確，繼續」後，轉錄的功能別名比照一般文字訊息走選單導引。
    final_reply, _final_keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "voice_confirm:accept")
    assert final_reply == "要進入「記帳」功能嗎？"


def test_handle_voice_message_masks_pii_without_persisting_chat(fake_db, monkeypatch):
    # 2026-08-02（privacy-masking SPEC.md）：語音轉出文字含個資時，天然經過
    # handle_message() → chat.handle_chat_message() 後才套用個資遮蔽。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    telegram_client = _FakeTelegramClient(b"raw-ogg-bytes")
    voice_client = _FakeVoiceClient(response_text="我的手機是 0912345678")
    llm_client = _FakeLLMClient(response_text="收到！")

    _reply, keyboard = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice123", 30,
        telegram_client, _FakeGDriveClient(), voice_client, llm_client=llm_client,
    )

    # 轉錄文字本身（含個資）會先原封不動貼出來讓使用者確認是否聽對，這一步還沒進到
    # handle_message() 的遮蔽邏輯，所以這裡不斷言遮蔽；遮蔽發生在使用者按下確認之後。
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "voice_confirm:accept"

    final_reply, _final_keyboard = router.handle_callback_query(
        fake_db, store, FAMILY_ID, "voice_confirm:accept", llm_client=llm_client
    )
    assert "0912345678" not in final_reply


def test_handle_voice_message_passes_through_mime_type_for_uploaded_audio(fake_db, monkeypatch):
    # message.audio（上傳的音檔，例如 MP3）走同一支函式，mime_type 要正確透傳到轉錄請求
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    voice_client = _FakeVoiceClient(response_text="我要記帳")

    router.handle_voice_message(
        fake_db, store, FAMILY_ID, "audio123", 180,
        _FakeTelegramClient(b"raw-mp3-bytes"), _FakeGDriveClient(), voice_client,
        mime_type="audio/mpeg",
    )

    assert voice_client.last_mime_type == "audio/mpeg"
    assert voice_client.last_filename == "voice.mp3"


def test_handle_voice_message_works_for_owner(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()
    voice_client = _FakeVoiceClient(response_text="我要記帳")

    reply, keyboard = router.handle_voice_message(
        fake_db, store, ROBIN_ID, "voice999", 30,
        _FakeTelegramClient(b"raw-ogg"), _FakeGDriveClient(), voice_client,
    )

    assert "我要記帳" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "voice_confirm:accept"

    final_reply, _final_keyboard = router.handle_callback_query(fake_db, store, ROBIN_ID, "voice_confirm:accept")
    assert final_reply == "要進入「記帳」功能嗎？"
    owner_row = fake_db.select("users", where="telegram_user_id = %s", params=(ROBIN_ID,), fetch_one=True)
    assert owner_row is not None

def _seed_certificate_question_for_router(fake_db, **overrides):
    row = {
        "exam_type": "ielts", "question_type": "write", "test_id": "0001", "question_number": 1,
        "question_text": "題目", "options": ["A", "B", "C", "D"], "correct_answer": "A",
    }
    row.update(overrides)
    return fake_db.insert("certificate_questions", row)


def _seed_certificate_assignment_for_router(fake_db, user_id, **overrides):
    row = {
        "user_id": user_id, "exam_type": "ielts", "assigned_date": commands._now().date(),
        "certificate_question_id": None, "vocab_question_id": None, "is_review": False,
    }
    row.update(overrides)
    return fake_db.insert("certificate_daily_assignments", row)


def test_main_menu_quiz_button_presents_question_and_sets_state(fake_db, monkeypatch):
    # 2026-09-06：「▶️ 開始作答」從「考試設定→每日題數設定→選證照」深處移到主選單獨立項目
    # （`menu:quiz`），取代已移除的 `certificate_settings:quiz:start` callback，見
    # docs/ADR/discuss/robinson.md 對應日期條目。
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    owner_row = fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    qid = _seed_certificate_question_for_router(fake_db)
    _seed_certificate_assignment_for_router(fake_db, owner_row, certificate_question_id=qid)
    store = ConversationStateStore()

    reply, _keyboard = router.handle_callback_query(fake_db, store, ROBIN_ID, "menu:quiz")

    assert "【ielts】第 1/1 題" in reply
    assert store.get(ROBIN_ID)["flow"] == "pending_quiz_answer"


def test_quiz_answer_text_trigger_presents_question_and_sets_state(fake_db, monkeypatch):
    # 2026-09-06：修正每日 08:00 推播訊息承諾「回覆『開始作答』開始吧」卻沒有對應文字路由的 bug
    # （原本會掉進一般聊天），見 docs/ADR/discuss/robinson.md 對應日期條目。
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    owner_row = fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    qid = _seed_certificate_question_for_router(fake_db)
    _seed_certificate_assignment_for_router(fake_db, owner_row, certificate_question_id=qid)
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, ROBIN_ID, "開始作答")

    assert "【ielts】第 1/1 題" in reply
    assert store.get(ROBIN_ID)["flow"] == "pending_quiz_answer"


def test_pending_quiz_answer_flow_dispatches_through_router(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    owner_row = fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    qid = _seed_certificate_question_for_router(fake_db)
    _seed_certificate_assignment_for_router(fake_db, owner_row, certificate_question_id=qid)
    store = ConversationStateStore()
    router.handle_callback_query(fake_db, store, ROBIN_ID, "menu:quiz")

    reply = router.handle_message(fake_db, store, ROBIN_ID, "A")

    assert "✅ 答對了" in reply
    assert store.get(ROBIN_ID) is None


# --- 2026-08-18（Youtube 技術分享設定選單化，見 docs/ADR/discuss/robinson.md、
# docs/ADR/discuss/youtube-intel.md 對應日期條目）：YouTube 主題設定改選單觸發，
# 舊文字觸發詞流程（`test_my_youtube_topics_trigger_empty`、
# `test_add_youtube_topic_trigger_and_flow_dispatches_through_router`、
# `test_remove_youtube_topic_trigger_and_flow_dispatches_through_router`）已隨設計變更移除，
# 改用 `menu:tech_intel`／`youtube_settings:*` callback 走選單＋二次確認模式，見下方測試。


def test_menu_tech_intel_shows_youtube_settings_overview(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, ROBIN_ID, "menu:tech_intel")

    assert "還沒有設定" in reply
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "youtube_settings:add" in callback_datas
    assert "youtube_settings:remove" not in callback_datas


def test_youtube_settings_add_flow_round_trips_through_router(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    owner_row = fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    store = ConversationStateStore()

    ask_topic, _keyboard = router.handle_callback_query(fake_db, store, ROBIN_ID, "youtube_settings:add")
    assert store.get(ROBIN_ID)["flow"] == "youtube_topic_add"
    assert "主題" in ask_topic

    confirm_reply = router.handle_message(fake_db, store, ROBIN_ID, "AI Agent")
    if isinstance(confirm_reply, tuple):
        confirm_reply = confirm_reply[0]
    assert "AI Agent" in confirm_reply
    assert store.get(ROBIN_ID) is None
    rows = fake_db.select("youtube_topics", where="user_id = %s", params=(owner_row,))
    assert [r["topic"] for r in rows] == ["AI Agent"]

    overview_reply, _keyboard = router.handle_callback_query(fake_db, store, ROBIN_ID, "youtube_settings:menu")
    assert "AI Agent" in overview_reply


def test_youtube_settings_remove_flow_requires_confirm_button(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    owner_row = fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    topic_id = fake_db.insert(
        "youtube_topics", {"user_id": owner_row, "topic": "AI Agent", "last_recommended_on": None}
    )
    store = ConversationStateStore()

    _list_reply, list_keyboard = router.handle_callback_query(fake_db, store, ROBIN_ID, "youtube_settings:remove")
    list_button_texts = [button["text"] for row in list_keyboard["inline_keyboard"] for button in row]
    assert any("AI Agent" in text for text in list_button_texts)

    confirm_ask, _keyboard = router.handle_callback_query(
        fake_db, store, ROBIN_ID, f"youtube_settings:remove_select:{topic_id}"
    )
    assert "確定要移除" in confirm_ask
    assert store.get(ROBIN_ID)["flow"] == "youtube_topic_remove_confirm"

    # 取消（按鈕回主選單前，還沒真的刪除）
    _cancel_reply, _keyboard = router.handle_callback_query(fake_db, store, ROBIN_ID, "youtube_settings:menu")
    assert store.get(ROBIN_ID) is None
    assert len(fake_db.select("youtube_topics", where="user_id = %s", params=(owner_row,))) == 1

    # 重新選擇並實際按下確認才會刪除
    router.handle_callback_query(fake_db, store, ROBIN_ID, f"youtube_settings:remove_select:{topic_id}")
    confirm_reply, _keyboard = router.handle_callback_query(
        fake_db, store, ROBIN_ID, f"youtube_settings:confirm_remove:{topic_id}"
    )
    assert "移除" in confirm_reply
    assert store.get(ROBIN_ID) is None
    assert fake_db.select("youtube_topics", where="user_id = %s", params=(owner_row,)) == []


# --- 好友模式（Step 3.5，見 robinson SPEC.md FR-51、FR-52、ADR-22） ---


def test_friend_chat_trigger_dispatches_through_router_for_owner(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    owner_row = fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    fake_db.insert(
        "mood_journals",
        {"user_id": owner_row, "mood_category": "happy_excited", "content": "今天不錯", "entry_date": commands._now().date()},
    )
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="主任最近心情看起來不錯耶，繼續保持喔！")

    reply = router.handle_message(fake_db, store, ROBIN_ID, "陪我聊聊", llm_client=llm_client)

    assert reply == "主任最近心情看起來不錯耶，繼續保持喔！"
    assert "Robin" in llm_client.last_prompt
    assert store.get(ROBIN_ID) is None


def test_friend_chat_trigger_dispatches_through_router_for_family_member(fake_db):
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="爸爸最近過得如何呀？")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "陪我聊聊", llm_client=llm_client)

    assert reply == "爸爸最近過得如何呀？"
    assert "爸爸" in llm_client.last_prompt


# --- 求職模組（Step 4.1，見 robinson SPEC.md FR-33、FR-36、ADR-24） ---


def test_job_search_menu_dispatches_through_router_for_owner(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, ROBIN_ID, "menu:job_search")

    assert "求職設定" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "job_search:profile:resume"


def test_uploaded_company_csv_trigger_dispatches_for_owner(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    fake_db.insert(
        "job_companies", {"company_id_104": "100", "company_name": "A 公司", "region": "台北市", "background": None}
    )
    csv_bytes = "104公司ID,公司全名,地區,產業類型,背景\n100,A 公司,台北市,軟體業,做電商平台的新創\n".encode(
        "utf-8-sig"
    )

    class _FakeGDriveClient:
        def list_files(self, name_contains=None):
            return [{"id": "drive-1", "name": "2026-08-09-104職缺公司.csv", "mimeType": "text/csv"}]

        def download_file(self, file_id):
            return csv_bytes

    store = ConversationStateStore()

    reply = router.handle_message(
        fake_db, store, ROBIN_ID, "已上傳2026-08-09-104職缺公司.csv", gdrive_client=_FakeGDriveClient()
    )

    assert "1 家公司" in reply
    row = fake_db.select("job_companies", where="company_id_104 = %s", params=("100",), fetch_one=True)
    assert row["background"] == "做電商平台的新創"


def test_uploaded_company_csv_trigger_gracefully_degrades_when_gdrive_client_none(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, ROBIN_ID, "已上傳2026-08-09-104職缺公司.csv")

    assert "還沒設定好" in reply


# --- 職缺推薦 Excel 回填（Step 4.2，見 robinson SPEC.md FR-38e、ADR-26） ---


def test_uploaded_recommendation_excel_trigger_dispatches_for_owner(fake_db, monkeypatch):
    import io as _io

    import openpyxl as _openpyxl

    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    fake_db.insert(
        "job_postings",
        {
            "job_id_104": "1", "company_id_104": "100", "title": "AI 工程師", "region": "台北市",
            "url": "https://www.104.com.tw/job/1", "is_unliked": False,
        },
    )
    workbook = _openpyxl.Workbook()
    workbook.active.title = "所有職缺推薦"
    workbook.active.append(
        ["104公司ID", "公司全名", "地區", "產業類型", "職缺", "評分", "排名", "推薦原因", "連結", "是否喜歡"]
    )
    workbook.active.append(["100", "A 公司", "台北市", "軟體業", "AI 工程師", 90.0, 1, "很符合", "https://www.104.com.tw/job/1", "1"])
    workbook.create_sheet("最新職缺推薦").append(
        ["104公司ID", "公司全名", "地區", "產業類型", "職缺", "評分", "排名", "推薦原因", "連結", "是否喜歡"]
    )
    buffer = _io.BytesIO()
    workbook.save(buffer)
    xlsx_bytes = buffer.getvalue()

    class _FakeGDriveClient:
        def list_files(self, name_contains=None):
            return [{"id": "drive-2", "name": "2026-08-09-104職缺推薦.xlsx", "mimeType": "application/octet-stream"}]

        def download_file(self, file_id):
            return xlsx_bytes

    store = ConversationStateStore()

    reply = router.handle_message(
        fake_db, store, ROBIN_ID, "已上傳2026-08-09-104職缺推薦.xlsx", gdrive_client=_FakeGDriveClient()
    )

    assert "1 筆職缺" in reply
    row = fake_db.select("job_postings", where="job_id_104 = %s", params=("1",), fetch_one=True)
    assert row["is_unliked"] is True


def test_uploaded_recommendation_excel_trigger_gracefully_degrades_when_gdrive_client_none(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, ROBIN_ID, "已上傳2026-08-09-104職缺推薦.xlsx")

    assert "還沒設定好" in reply


def test_job_search_menu_denies_family_member(fake_db):
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    reply, _ = router.handle_callback_query(fake_db, store, FAMILY_ID, "menu:job_search")

    assert "無法使用" in reply


# --- 外部管道職缺與應徵成效追蹤（Step 4.3，見 robinson SPEC.md FR-39、FR-40、ADR-27） ---


def test_add_external_job_callback_dispatches_through_router_for_owner(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    store = ConversationStateStore()

    reply, _ = router.handle_callback_query(fake_db, store, ROBIN_ID, "job_search:external:add")

    assert "管道" in reply
    assert store.get(ROBIN_ID)["flow"] == "pending_external_job_channel"


def test_application_status_callback_lists_empty_for_owner(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    store = ConversationStateStore()

    reply, _ = router.handle_callback_query(fake_db, store, ROBIN_ID, "job_search:status:applied")

    assert "目前沒有" in reply


def test_application_status_callback_updates_status_and_replies(fake_db, monkeypatch):
    from src.bot import job_search

    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    job_id = job_search.add_external_job(
        fake_db, "linkedin", "後端工程師", "某新創公司", "https://linkedin.com/jobs/1", "內容", "背景",
    )
    store = ConversationStateStore()

    reply, _ = router.handle_callback_query(fake_db, store, ROBIN_ID, f"job_search:status:set:{job_id}:applied")

    assert "已應徵" in reply
    rows = fake_db.select("job_applications", where=None)
    assert len(rows) == 1
    assert rows[0]["status"] == "applied"


def test_application_status_callback_accepts_offer(fake_db, monkeypatch):
    from src.bot import job_search

    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    job_id = job_search.add_external_job(
        fake_db, "linkedin", "後端工程師", "某新創公司", "https://linkedin.com/jobs/1", "內容", "背景",
    )
    store = ConversationStateStore()

    reply, _ = router.handle_callback_query(fake_db, store, ROBIN_ID, f"job_search:status:set:{job_id}:offer")

    assert "已拿到 Offer" in reply
    rows = fake_db.select("job_applications", where=None)
    assert rows[0]["status"] == "offer"


def test_application_status_callback_reports_not_found(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    store = ConversationStateStore()

    reply, _ = router.handle_callback_query(fake_db, store, ROBIN_ID, "job_search:status:set:not-exist:applied")

    assert "找不到" in reply
    assert store.get(FAMILY_ID) is None


# --- 系統錯誤管理（FR-19j～FR-19l） ---


def test_system_error_menu_is_owner_only(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})

    text, keyboard = router.handle_callback_query(
        fake_db, ConversationStateStore(), ROBIN_ID, "menu:system_errors"
    )

    assert "系統錯誤管理" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "system_errors:list:pending:0"


def test_system_error_callback_rejects_non_owner(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})

    text, _ = router.handle_callback_query(
        fake_db, ConversationStateStore(), FAMILY_ID, "system_errors:list:pending:0"
    )

    assert text == "無法使用這個功能。"


# --- 重要日子（Phase 6 第二批 2b，見 docs/ADR/discuss/robinson.md，FR-6e／FR-6h）---


def test_important_days_menu_key_not_in_not_yet_implemented_set():
    """2b 應該把 important_days 從 2a 留下的「開發中」名單移除；daily_log 之後在 2c 也移除，
    collections 在 2d 也移除，achievements 在 2e 也移除，todo 在 2f 也移除，query 在批次4也移除，
    schedule 本批也接上真正邏輯。"""
    assert not menu.is_not_yet_implemented("important_days")
    assert not menu.is_not_yet_implemented("daily_log")
    assert not menu.is_not_yet_implemented("collections")
    assert not menu.is_not_yet_implemented("achievements")
    assert not menu.is_not_yet_implemented("todo")
    assert not menu.is_not_yet_implemented("query")
    assert not menu.is_not_yet_implemented("schedule")


def test_schedule_menu_is_implemented():
    assert not menu.is_not_yet_implemented("schedule")


def test_disabled_owner_feature_keeps_menu_entry_but_blocks_opening(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"id": 1, "telegram_user_id": ROBIN_ID, "is_owner": True})
    fake_db.insert("feature_toggles", {"user_id": 1, "feature_key": "job_search", "is_enabled": False})
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, ROBIN_ID, "menu:job_search")

    assert reply == "若要使用求職設定功能，請至功能開關與排程設定打開！"
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "menu:schedule"


def test_important_days_submenu_shows_list_and_add_buttons(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, ROBIN_ID, "menu:important_days")

    assert "重要日子" in reply
    callback_datas = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]
    assert "important_days:list" in callback_datas
    assert "important_days:add" in callback_datas


def test_important_days_add_flow_creates_row_for_general_user(fake_db, monkeypatch):
    """FR-3：一般使用者（非 Owner）也能直接使用重要日子，不是 Owner 專屬功能。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False, "is_active": True})
    store = ConversationStateStore()

    reply, keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "important_days:add")
    assert keyboard is None
    assert "名稱" in reply

    router.handle_message(fake_db, store, FAMILY_ID, "爸爸生日")
    router.handle_message(fake_db, store, FAMILY_ID, "1")  # 每年固定日期
    router.handle_message(fake_db, store, FAMILY_ID, "3-5")
    router.handle_message(fake_db, store, FAMILY_ID, "3-5")
    router.handle_message(fake_db, store, FAMILY_ID, "是")
    router.handle_message(fake_db, store, FAMILY_ID, "1")
    router.handle_message(fake_db, store, FAMILY_ID, "1")  # 只有自己
    reply, keyboard = router.handle_message(fake_db, store, FAMILY_ID, "略過")

    assert "請確認以下內容" in reply
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "important_days:confirm_save"

    reply, _keyboard = router.handle_callback_query(fake_db, store, FAMILY_ID, "important_days:confirm_save")

    assert reply == "已新增重要日子！"
    row = fake_db.select("important_days", where=None, params=None)
    assert len(row) == 1
    assert row[0]["title"] == "爸爸生日"


def test_important_days_delete_confirm_only_owner_can_target_own_event(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    other_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID_2, "role": "媽媽", "is_owner": False})
    fake_db.insert("important_days", {
        "owner_user_id": other_id, "title": "別人的事件", "recurrence_type": "one_time",
        "event_date": None, "is_all_day": True, "reminder_days_before": 1,
        "audience_mode": "self", "is_active": True,
    })
    important_day_id = fake_db.select("important_days", where=None, params=None)[0]["id"]
    store = ConversationStateStore()

    reply, _keyboard = router.handle_callback_query(
        fake_db, store, FAMILY_ID, f"important_days:delete:{important_day_id}"
    )

    assert "找不到" in reply
