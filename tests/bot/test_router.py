from datetime import date, datetime, timedelta, timezone
from io import BytesIO

from PIL import Image

from src.bot import commands, router, templates, voice
from src.bot.state import ConversationStateStore


ROBIN_ID = 8263904025
FAMILY_ID = 555
FAMILY_ID_2 = 556


class _FakeLLMClient:
    """模擬 submodules.llm.client.LLMClient，實作 chat.py 與 commands.handle_function 用的
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

def test_unknown_user_with_correct_code_gets_welcome_message(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    _seed_pending_invite(fake_db, code="secret123")
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "secret123")

    assert reply == templates.APPENDIX_A_TEXT
    bound = fake_db.select("users", where="telegram_user_id = %s", params=(FAMILY_ID,), fetch_one=True)
    assert bound is not None


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

def test_known_family_member_can_trigger_rule(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "/rule")

    assert reply == templates.APPENDIX_A_TEXT


def test_known_family_member_can_trigger_function_by_natural_language(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="這是人格化後的功能總覽")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "我要看所有功能", llm_client=llm_client)

    assert reply == "這是人格化後的功能總覽"


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
    logs = fake_db.select("conversation_logs", where="user_id = %s", params=(1,))
    assert len(logs) == 2


# --- Owner（Robin） ---

def test_owner_first_message_creates_owner_row(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, ROBIN_ID, "/rule")

    assert reply == templates.APPENDIX_A_TEXT
    owner_row = fake_db.select("users", where="telegram_user_id = %s", params=(ROBIN_ID,), fetch_one=True)
    assert owner_row is not None
    assert owner_row["is_owner"] is True


def test_owner_can_trigger_function_via_slash_command(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="這是人格化後的功能總覽")

    reply = router.handle_message(fake_db, store, ROBIN_ID, "/function", llm_client=llm_client)

    assert reply == "這是人格化後的功能總覽"


def test_owner_can_trigger_set_invite_codes(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, ROBIN_ID, "/set_invite_codes")

    assert store.get(ROBIN_ID) == {"flow": "set_invite_codes", "step": "awaiting_role"}
    assert "稱謂" in reply


def test_owner_mid_setup_flow_continues_state_machine(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()
    store.set(ROBIN_ID, {"flow": "set_invite_codes", "step": "awaiting_role"})

    reply = router.handle_message(fake_db, store, ROBIN_ID, "媽媽")

    assert store.get(ROBIN_ID) == {"flow": "set_invite_codes", "step": "awaiting_code", "role": "媽媽"}
    assert "媽媽" in reply


def test_owner_finishing_setup_writes_to_db_via_router(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()
    store.set(ROBIN_ID, {"flow": "set_invite_codes", "step": "awaiting_code", "role": "媽媽"})

    router.handle_message(fake_db, store, ROBIN_ID, "mom-code")

    invite = fake_db.select("invite_codes", where="code = %s AND is_used = FALSE", params=("mom-code",), fetch_one=True)
    assert invite is not None


# --- 功能開關（docs/specs/feature-toggles/SPEC.md）---


def test_family_member_binding_auto_creates_default_toggles(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    _seed_pending_invite(fake_db, code="secret123")
    store = ConversationStateStore()

    router.handle_message(fake_db, store, FAMILY_ID, "secret123")

    bound = fake_db.select("users", where="telegram_user_id = %s", params=(FAMILY_ID,), fetch_one=True)
    rows = fake_db.select("feature_toggles", where="user_id = %s", params=(bound["id"],))
    assert len(rows) == 10


def test_known_family_member_can_trigger_my_toggles(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "我的功能設定")

    assert "1. " in reply
    assert store.get(FAMILY_ID)["flow"] == "toggle"


def test_known_family_member_toggle_flow_continues_via_router(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    router.handle_message(fake_db, store, FAMILY_ID, "/my_toggles")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "1")

    assert "切換為" in reply
    assert store.get(FAMILY_ID) == {"flow": "toggle", "step": "awaiting_index", "target_user_id": user_id}


def test_known_family_member_cannot_trigger_owner_only_set_toggle(fake_db, monkeypatch):
    """權限邊界測試：家人輸入 Owner 專屬 /set_toggle，不應被授予代管他人開關的能力（改落入一般聊天核心）。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="我不太懂這個指令耶！")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "/set_toggle", llm_client=llm_client)

    assert reply == "我不太懂這個指令耶！"
    assert store.get(FAMILY_ID) is None


def test_owner_can_trigger_my_toggles_for_self(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, ROBIN_ID, "/my_toggles")

    assert "1. " in reply
    owner_row = fake_db.select("users", where="telegram_user_id = %s", params=(ROBIN_ID,), fetch_one=True)
    assert store.get(ROBIN_ID) == {"flow": "toggle", "step": "awaiting_index", "target_user_id": owner_row["id"]}


def test_owner_set_toggle_with_no_family_bound_yet(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, ROBIN_ID, "/set_toggle")

    assert "沒有" in reply
    assert store.get(ROBIN_ID) is None


def test_owner_can_delegate_toggle_for_family_member(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    dad_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    select_reply = router.handle_message(fake_db, store, ROBIN_ID, "/set_toggle")
    list_reply = router.handle_message(fake_db, store, ROBIN_ID, "1")
    toggle_reply = router.handle_message(fake_db, store, ROBIN_ID, "1")

    assert "爸爸" in select_reply
    assert "1. " in list_reply
    assert "切換為" in toggle_reply
    rows = fake_db.select("feature_toggles", where="user_id = %s", params=(dad_id,))
    assert any(not r["is_enabled"] for r in rows)


# --- 設定家人生日（FR-53，Step 2.3）---


def test_known_family_member_cannot_trigger_owner_only_set_family_birthday(fake_db, monkeypatch):
    """權限邊界測試：家人輸入 Owner 專屬 /set_family_birthday，不應被授予設定生日的能力（改落入一般聊天核心）。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="我不太懂這個指令耶！")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "/set_family_birthday", llm_client=llm_client)

    assert reply == "我不太懂這個指令耶！"
    assert store.get(FAMILY_ID) is None


def test_owner_can_complete_set_family_birthday_flow(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    sister_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "大妹婿", "is_owner": False})
    store = ConversationStateStore()

    select_reply = router.handle_message(fake_db, store, ROBIN_ID, "設定家人生日")
    date_reply = router.handle_message(fake_db, store, ROBIN_ID, "1")
    save_reply = router.handle_message(fake_db, store, ROBIN_ID, "1988-11-20")

    assert "大妹婿" in select_reply
    assert "幾月幾號" in date_reply
    assert "大妹婿" in save_reply
    assert store.get(ROBIN_ID) is None
    row = fake_db.select("users", where="id = %s", params=(sister_id,), fetch_one=True)
    assert row["birthday"] == date(1988, 11, 20)


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


# --- /recovered（FR-20，Step 1.6，Owner 專屬）---


class _FakeTelegramClientForRecovered:
    """模擬 submodules.telegram.client.TelegramClient，只實作 send_text（與下方 photo/voice
    測試用的 `_FakeTelegramClient`（只實作 `get_file_bytes`）刻意分開命名，避免同名覆蓋）。"""

    def __init__(self):
        self.sent = []

    def send_text(self, chat_id, text):
        self.sent.append((chat_id, text))


def test_recovered_command_broadcasts_to_family_when_owner(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "媽媽", "is_owner": False})
    store = ConversationStateStore()
    telegram_client = _FakeTelegramClientForRecovered()

    reply = router.handle_message(fake_db, store, ROBIN_ID, "/recovered", telegram_client=telegram_client)

    assert "1 位家人" in reply
    assert telegram_client.sent == [(FAMILY_ID, commands._RECOVERED_BROADCAST_TEXT)]


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


def test_chat_core_unknown_reply_sets_pending_user_knowledge_state(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="這個我目前不知道耶【NOT_FOUND】")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "今天天氣如何？", llm_client=llm_client)

    assert "這個我目前不知道耶" in reply
    assert "自行上網查詢" in reply
    assert store.get(FAMILY_ID) == {
        "flow": "pending_user_knowledge",
        "target_user_id": user_id,
        "original_question": "今天天氣如何？",
    }


def test_pending_user_knowledge_flow_saves_via_router_when_llm_judges_it_an_answer(fake_db, monkeypatch):
    # ADR-6：是否存檔改由 LLM 判斷（【SAVE_ANSWER】標記），router 要把 pending_question 傳進去
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(
        FAMILY_ID,
        {"flow": "pending_user_knowledge", "target_user_id": user_id, "original_question": "今天天氣如何？"},
    )
    llm_client = _FakeLLMClient(response_text="【SAVE_ANSWER】")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "今天台北是晴天", llm_client=llm_client)

    assert "記錄" in reply
    assert store.get(FAMILY_ID) is None
    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", user_id))
    assert len(rows) == 1
    assert rows[0]["content"] == "今天台北是晴天"


def test_pending_user_knowledge_flow_treats_unrelated_new_question_normally_via_router(fake_db, monkeypatch):
    # Robin 回報：問「陳東東是誰」被回不知道後換問「吳凱吉是誰」，被誤存成陳東東的答案；
    # 模型判斷是無關新問題時不輸出任何標記，router 應該照一般回答處理，不寫入知識庫。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(
        FAMILY_ID,
        {"flow": "pending_user_knowledge", "target_user_id": user_id, "original_question": "陳東東是誰"},
    )
    llm_client = _FakeLLMClient(response_text="吳凱吉是 Robin 的妹夫喔！")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "吳凱吉是誰", llm_client=llm_client)

    assert reply == "吳凱吉是 Robin 的妹夫喔！"
    assert store.get(FAMILY_ID) is None
    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", user_id))
    assert len(rows) == 0


def test_pending_name_confirm_flow_continues_via_router(fake_db, monkeypatch):
    # 2026-08-01（ADR-7）：打字誤植先反問確認，router 要正確帶 confirming_question 分派下去。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(
        FAMILY_ID,
        {"flow": "pending_name_confirm", "target_user_id": user_id, "original_question": "吳鎧吉是誰"},
    )
    llm_client = _FakeLLMClient(response_text="吳凱吉是 Robin 的妹夫喔！")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "對啊", llm_client=llm_client)

    assert reply == "吳凱吉是 Robin 的妹夫喔！"
    assert store.get(FAMILY_ID) is None


def test_owner_pending_user_knowledge_flow_declines_via_router(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()
    store.set(ROBIN_ID, {"flow": "pending_user_knowledge", "target_user_id": 1, "original_question": "陳東東是誰"})
    llm_client = _FakeLLMClient(response_text="【DECLINE_SAVE】")

    reply = router.handle_message(fake_db, store, ROBIN_ID, "不用紀錄啦", llm_client=llm_client)

    assert reply == "好的，這次就不記錄囉！"
    assert store.get(ROBIN_ID) is None
    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", 1))
    assert len(rows) == 0


# --- /clean-all-dialog（docs/specs/chat-core/SPEC.md FR-10，2026-08-01 起改為先確認再執行）---


def test_known_family_member_triggering_clean_all_dialog_only_asks_for_confirmation_first(fake_db, monkeypatch):
    # Robin 回報：原本一觸發 /clean-all-dialog 就直接刪除，沒有給反悔機會；改為先反問確認，
    # 並且要告知目前有幾筆對話紀錄，這一步驟本身不應該真的刪除任何東西。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    fake_db.insert("conversation_logs", {"user_id": user_id, "role": "user", "content": "早安", "deleted_at": None})
    fake_db.insert("conversation_logs", {"user_id": user_id, "role": "assistant", "content": "早安！", "deleted_at": None})
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "我想要刪除所有對話紀錄")

    assert "2 筆對話紀錄" in reply
    assert "確定要清除嗎" in reply
    assert store.get(FAMILY_ID) == {
        "flow": "pending_clean_all_dialog_confirm",
        "target_user_id": user_id,
    }
    logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(user_id,))
    assert len(logs) == 2  # 還沒真的刪除


def test_clean_all_dialog_confirm_flow_moves_to_final_confirm_when_user_confirms(fake_db, monkeypatch):
    # 2026-08-02（FR-16a）：第一輪 CONFIRM 只會進入最終確認狀態，不會馬上刪除。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    fake_db.insert("conversation_logs", {"user_id": user_id, "role": "user", "content": "早安", "deleted_at": None})
    store = ConversationStateStore()
    store.set(FAMILY_ID, {"flow": "pending_clean_all_dialog_confirm", "target_user_id": user_id})
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "對，刪掉吧", llm_client=llm_client)

    assert "確認執行" in reply
    assert store.get(FAMILY_ID) == {"flow": "pending_clean_all_dialog_final_confirm", "target_user_id": user_id}
    logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(user_id,))
    assert len(logs) == 1


def test_clean_all_dialog_final_confirm_flow_deletes_when_typed_keyword(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    fake_db.insert("conversation_logs", {"user_id": user_id, "role": "user", "content": "早安", "deleted_at": None})
    store = ConversationStateStore()
    store.set(FAMILY_ID, {"flow": "pending_clean_all_dialog_final_confirm", "target_user_id": user_id})

    reply = router.handle_message(fake_db, store, FAMILY_ID, "確認執行")

    assert reply == "已經幫你清除所有對話紀錄囉！你的知識庫內容不會受影響。"
    assert store.get(FAMILY_ID) is None
    logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(user_id,))
    assert logs == []


def test_clean_all_dialog_final_confirm_flow_rejects_voice_sourced_reply(fake_db, monkeypatch):
    # 語音轉出來的文字即使剛好是「確認執行」也不能通過最終確認，避免語音聽錯就誤刪不可逆的資料。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    fake_db.insert("conversation_logs", {"user_id": user_id, "role": "user", "content": "早安", "deleted_at": None})
    store = ConversationStateStore()
    store.set(FAMILY_ID, {"flow": "pending_clean_all_dialog_final_confirm", "target_user_id": user_id})

    reply = router.handle_message(fake_db, store, FAMILY_ID, "確認執行", via_voice=True)

    assert "打字" in reply
    assert store.get(FAMILY_ID) == {"flow": "pending_clean_all_dialog_final_confirm", "target_user_id": user_id}
    logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(user_id,))
    assert len(logs) == 1


def test_clean_all_dialog_confirm_flow_keeps_logs_when_user_cancels(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    fake_db.insert("conversation_logs", {"user_id": user_id, "role": "user", "content": "早安", "deleted_at": None})
    store = ConversationStateStore()
    store.set(FAMILY_ID, {"flow": "pending_clean_all_dialog_confirm", "target_user_id": user_id})
    llm_client = _FakeLLMClient(response_text="CANCEL")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "算了不要好了", llm_client=llm_client)

    assert reply == "好的，先不清除，你的對話紀錄都還在喔！"
    assert store.get(FAMILY_ID) is None
    logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(user_id,))
    assert len(logs) == 1


def test_pending_save_knowledge_confirm_flow_moves_to_final_confirm_via_router(fake_db, monkeypatch):
    # 2026-08-01（FR-11）：主動新增知識反問確認後，下一輪要正確分派到 commands。
    # 2026-08-02（FR-16a）：CONFIRM 後改為先進入最終確認，不會馬上寫入。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(
        FAMILY_ID,
        {"flow": "pending_save_knowledge_confirm", "target_user_id": user_id, "original_request": "幫我存SOP"},
    )
    llm_client = _FakeLLMClient(response_text="DECISION: CONFIRM\nCATEGORY: custom\nLABEL: SOP\nCONTENT: 內容")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "對", llm_client=llm_client)

    assert "確認執行" in reply
    assert store.get(FAMILY_ID)["flow"] == "pending_save_knowledge_final_confirm"
    assert fake_db.select("knowledge_base") == []

    final_reply = router.handle_message(fake_db, store, FAMILY_ID, "確認執行")

    assert "已經幫你存到你的個人知識庫囉" in final_reply
    assert store.get(FAMILY_ID) is None
    rows = fake_db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", user_id))
    assert len(rows) == 1


# --- 待辦事項（robinson SPEC.md FR-31、FR-31a、FR-32，Step 1.7）---


def test_my_todos_trigger_reports_empty_list(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, FAMILY_ID, "我的待辦事項")

    assert reply == "目前沒有待辦事項喔！"
    assert store.get(FAMILY_ID) is None


def test_todo_full_flow_from_natural_language_to_creation(fake_db, monkeypatch):
    # 2026-08-02（Step 1.7，見 FR-31、FR-56e 情境範例）：自然語言描述 → 確認要記錄 → 給時間
    # → 確認提醒設定，全程由 router 正確分派到 chat.py／commands.py。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    fake_db.insert("knowledge_base", {"category": "general_persona", "user_id": None, "content": "我是羅賓森"})
    fake_db.insert("knowledge_base", {"category": "general_family", "user_id": None, "content": "家人背景"})
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
    reply5 = router.handle_message(fake_db, store, FAMILY_ID, "不用", llm_client=llm_client)
    assert reply5 == "好的，已經幫你記錄好了！"
    assert store.get(FAMILY_ID) is None

    rows = fake_db.select("todos", where="user_id = %s AND status = %s", params=(user_id, "pending"))
    assert len(rows) == 1
    assert rows[0]["content"] == "買菜"
    assert rows[0]["remind_before_30min"] is True
    assert rows[0]["sync_to_calendar"] is False


def test_my_todos_trigger_lists_and_marks_completed_via_index_selection(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    due_at = datetime(2026, 8, 2, 7, 0, tzinfo=timezone.utc)
    todo_id = fake_db.insert(
        "todos",
        {"user_id": user_id, "content": "買菜", "due_at": due_at, "remind_before_30min": False, "status": "pending"},
    )
    store = ConversationStateStore()

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "我的待辦事項")
    assert "買菜" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_todo_list_action"

    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "1")
    assert "買菜" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_todo_action_confirm"

    llm_client = _FakeLLMClient(response_text="COMPLETE")
    reply3 = router.handle_message(fake_db, store, FAMILY_ID, "做完了", llm_client=llm_client)
    assert "完成" in reply3
    assert store.get(FAMILY_ID) is None
    assert fake_db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)["status"] == "completed"


# --- 心情小記（robinson SPEC.md FR-49、FR-50，Step 1.8）---


def test_mood_journal_full_flow_records_entry_and_achievement(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "我想做心情筆記")
    assert "請幫我選一個" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_category"

    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "高興/興奮")
    assert reply2 == "給我完整的日記內容："
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_content"

    reply3 = router.handle_message(fake_db, store, FAMILY_ID, "今天很開心")
    assert "已經紀錄了" in reply3
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_achievement"

    reply4 = router.handle_message(fake_db, store, FAMILY_ID, "完成了一份報告")
    assert reply4 == "已經幫你記錄好了！"
    assert store.get(FAMILY_ID) is None

    rows = fake_db.select("mood_journals", where="user_id = %s AND mood_category = %s", params=(user_id, "happy_excited"))
    assert len(rows) == 1
    assert rows[0]["content"] == "今天很開心"
    assert rows[0]["achievement_note"] == "完成了一份報告"


def test_mood_journal_achievement_can_be_skipped(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    router.handle_message(fake_db, store, FAMILY_ID, "/mood_journal")
    router.handle_message(fake_db, store, FAMILY_ID, "1")
    router.handle_message(fake_db, store, FAMILY_ID, "今天有點低落")
    reply = router.handle_message(fake_db, store, FAMILY_ID, "結束")

    assert reply == "好的，那先這樣吧！"
    rows = fake_db.select("mood_journals")
    assert rows[0]["achievement_note"] is None


def test_mood_backfill_full_flow_records_entry_with_given_date(fake_db, monkeypatch):
    """2026-08-02 追加（FR-49 補記擴充）：「我要補記心情」先問哪一天，再走既有分類/內容流程。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "我要補記心情")
    assert "哪一天" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_backfill_date"

    date_llm_client = _FakeLLMClient(response_text="STATUS: CLEAR\nDATE: 2026-07-30")
    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "前天", llm_client=date_llm_client)
    assert "請幫我選一個" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_category"

    router.handle_message(fake_db, store, FAMILY_ID, "2")
    router.handle_message(fake_db, store, FAMILY_ID, "那天有點難過")
    reply4 = router.handle_message(fake_db, store, FAMILY_ID, "結束")

    assert reply4 == "好的，那先這樣吧！"
    rows = fake_db.select("mood_journals")
    assert rows[0]["entry_date"].isoformat() == "2026-07-30"
    assert rows[0]["mood_category"] == "sad_down"


def test_mood_list_update_and_delete_full_flow(fake_db, monkeypatch):
    """2026-08-02 追加（FR-49 更新/刪除擴充）：「我的心情紀錄」查詢清單、選一筆、更新內容、
    再查詢一次、選同一筆、刪除。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    fake_db.insert(
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

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "我的心情紀錄")
    assert "更新或刪除" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_list_action"

    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "1")
    assert "更新" in reply2 and "刪除" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_action_choice"

    update_llm_client = _FakeLLMClient(response_text="UPDATE")
    reply3 = router.handle_message(fake_db, store, FAMILY_ID, "我要改內容", llm_client=update_llm_client)
    assert "重新選一次心情分類" in reply3
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_category"

    router.handle_message(fake_db, store, FAMILY_ID, "6")
    router.handle_message(fake_db, store, FAMILY_ID, "改過的內容")
    router.handle_message(fake_db, store, FAMILY_ID, "結束")

    rows = fake_db.select("mood_journals")
    assert len(rows) == 1
    assert rows[0]["content"] == "改過的內容"
    assert rows[0]["mood_category"] == "happy_excited"

    router.handle_message(fake_db, store, FAMILY_ID, "我的心情紀錄")
    router.handle_message(fake_db, store, FAMILY_ID, "1")
    delete_llm_client = _FakeLLMClient(response_text="DELETE")
    reply_delete_ask = router.handle_message(fake_db, store, FAMILY_ID, "刪掉", llm_client=delete_llm_client)
    assert "沒辦法復原" in reply_delete_ask
    assert store.get(FAMILY_ID)["flow"] == "pending_mood_delete_confirm"

    confirm_llm_client = _FakeLLMClient(response_text="CONFIRM")
    reply_deleted = router.handle_message(fake_db, store, FAMILY_ID, "對", llm_client=confirm_llm_client)
    assert "已經刪除" in reply_deleted
    assert fake_db.select("mood_journals") == []


# --- 記帳（robinson SPEC.md FR-41～FR-44，Step 2.1）---


def test_finance_set_budget_full_flow_global_scope(fake_db, monkeypatch):
    """FR-41a：選「全部月份」，第一次設定沒有舊值，直接問金額。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "設定記帳預算")
    assert "全部月份" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_finance_budget_scope"

    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "1")
    assert "每月支出預算上限" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_finance_budget_amount"

    reply3 = router.handle_message(fake_db, store, FAMILY_ID, "15000")
    assert "15000 元" in reply3
    assert store.get(FAMILY_ID) is None


def test_finance_set_budget_full_flow_months_scope_with_override_confirm(fake_db, monkeypatch):
    """FR-41a：選「只套用某幾個月」，指定的月份已有舊覆蓋值時要先反問確認才能改。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    commands.finance.set_budget_override(fake_db, user_id, 2026, 8, 43000)
    store = ConversationStateStore()

    router.handle_message(fake_db, store, FAMILY_ID, "設定記帳預算")
    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "2")
    assert "幾月" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_finance_budget_months"

    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "8,9")
    assert "8月：43000 元" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_finance_budget_override_confirm"

    confirm_llm_client = _FakeLLMClient(response_text="CONFIRM")
    reply3 = router.handle_message(fake_db, store, FAMILY_ID, "對", llm_client=confirm_llm_client)
    assert "多少金額" in reply3
    assert store.get(FAMILY_ID)["flow"] == "pending_finance_budget_amount"

    reply4 = router.handle_message(fake_db, store, FAMILY_ID, "50000")
    assert "8月、9月" in reply4
    assert store.get(FAMILY_ID) is None
    assert commands.finance.get_budget_override(fake_db, user_id, 2026, 8) == 50000.0
    assert commands.finance.get_budget_override(fake_db, user_id, 2026, 9) == 50000.0


def test_finance_set_budget_global_scope_with_existing_value_asks_confirm(fake_db, monkeypatch):
    """FR-41a：選「全部月份」，全局預設已有舊值時先反問確認。"""
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    commands.finance.set_monthly_budget(fake_db, user_id, 15000)
    store = ConversationStateStore()

    router.handle_message(fake_db, store, FAMILY_ID, "設定記帳預算")
    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "1")
    assert "15000 元" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_finance_budget_global_confirm"

    confirm_llm_client = _FakeLLMClient(response_text="CONFIRM")
    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "對", llm_client=confirm_llm_client)
    assert "多少" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_finance_budget_amount"

    reply3 = router.handle_message(fake_db, store, FAMILY_ID, "20000")
    assert "20000 元" in reply3
    assert commands.finance.get_monthly_budget(fake_db, user_id) == 20000.0


def test_finance_add_transaction_full_flow_records_entry(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "我要記帳")
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

    reply5 = router.handle_message(fake_db, store, FAMILY_ID, "午餐")
    assert reply5 == "已經幫你記錄好了！"
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

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "我要補記帳")
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

    rows = fake_db.select("transactions")
    assert rows[0]["transaction_date"].isoformat() == "2026-08-01"
    assert rows[0]["type"] == "income"
    assert rows[0]["category"] == "薪資"


def test_finance_list_update_and_delete_full_flow(fake_db, monkeypatch):
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
            "transaction_date": date(2026, 8, 1),
        },
    )
    store = ConversationStateStore()

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "我的記帳紀錄")
    assert "更新或刪除" in reply1
    assert store.get(FAMILY_ID)["flow"] == "pending_transaction_list_action"

    reply2 = router.handle_message(fake_db, store, FAMILY_ID, "1")
    assert "更新" in reply2 and "刪除" in reply2
    assert store.get(FAMILY_ID)["flow"] == "pending_transaction_action_choice"

    update_llm_client = _FakeLLMClient(response_text="UPDATE")
    reply3 = router.handle_message(fake_db, store, FAMILY_ID, "我要改內容", llm_client=update_llm_client)
    assert "重新選一次交易類型" in reply3
    assert store.get(FAMILY_ID)["flow"] == "pending_transaction_type"

    router.handle_message(fake_db, store, FAMILY_ID, "支出")
    router.handle_message(fake_db, store, FAMILY_ID, "交通")
    router.handle_message(fake_db, store, FAMILY_ID, "50")
    router.handle_message(fake_db, store, FAMILY_ID, "結束")

    rows = fake_db.select("transactions")
    assert len(rows) == 1
    assert rows[0]["category"] == "交通"
    assert rows[0]["amount"] == 50.0

    router.handle_message(fake_db, store, FAMILY_ID, "我的記帳紀錄")
    router.handle_message(fake_db, store, FAMILY_ID, "1")
    delete_llm_client = _FakeLLMClient(response_text="DELETE")
    reply_delete_ask = router.handle_message(fake_db, store, FAMILY_ID, "刪掉", llm_client=delete_llm_client)
    assert "沒辦法復原" in reply_delete_ask
    assert store.get(FAMILY_ID)["flow"] == "pending_transaction_delete_confirm"

    confirm_llm_client = _FakeLLMClient(response_text="CONFIRM")
    reply_deleted = router.handle_message(fake_db, store, FAMILY_ID, "對", llm_client=confirm_llm_client)
    assert "已經刪除" in reply_deleted
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

    reply = router.handle_message(fake_db, store, FAMILY_ID, "我的記帳摘要")

    assert "記帳摘要" in reply
    assert store.get(FAMILY_ID) is None


# --- 客訴收集（robinson SPEC.md FR-60～FR-63，Step 1.9）---


def test_complaint_full_flow_records_and_notifies_robin(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": ROBIN_ID, "role": "Robin", "is_owner": True})
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="分析報告內容")

    reply1 = router.handle_message(fake_db, store, FAMILY_ID, "我要客訴你")
    assert reply1 == "請問你覺得哪個地方需要改進呢？"
    assert store.get(FAMILY_ID)["flow"] == "pending_complaint_content"

    class _FakeTelegramClient:
        def __init__(self):
            self.sent = []

        def send_text(self, chat_id, text):
            self.sent.append((chat_id, text))

    telegram_client = _FakeTelegramClient()
    reply2 = router.handle_message(
        fake_db, store, FAMILY_ID, "客服態度不好",
        llm_client=llm_client, telegram_client=telegram_client,
    )

    assert "已經收到你的意見了" in reply2
    assert store.get(FAMILY_ID) is None
    rows = fake_db.select("complaints")
    assert len(rows) == 1
    assert rows[0]["content"] == "客服態度不好"
    assert len(telegram_client.sent) == 1
    assert telegram_client.sent[0][0] == ROBIN_ID


# --- /clean-target-dialog（docs/specs/chat-core/SPEC.md FR-12）---


def test_known_family_member_can_trigger_clean_target_dialog_by_natural_language(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    fake_db.insert("conversation_logs", {"user_id": user_id, "role": "user", "content": "范麗芳人很好", "deleted_at": None})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="1")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "我想刪除有關范麗芳的紀錄", llm_client=llm_client)

    assert "跟「范麗芳」有關" in reply
    assert "確定要清除嗎" in reply
    assert store.get(FAMILY_ID)["flow"] == "pending_clean_target_dialog_confirm"
    assert store.get(FAMILY_ID)["topic"] == "范麗芳"


def test_clean_target_dialog_topic_containing_pii_is_not_masked(fake_db, monkeypatch):
    # 2026-08-02（privacy-masking SPEC.md FR-7）：這支指令的 topic 刻意不遮蔽，因為使用者很可能
    # 就是要用個資內容當關鍵字搜尋要刪除的紀錄，遮蔽會讓比對用的關鍵字直接消失、功能失效。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    fake_db.insert(
        "conversation_logs",
        {"user_id": user_id, "role": "user", "content": "我的手機是 0912345678", "deleted_at": None},
    )
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="1")

    reply = router.handle_message(
        fake_db, store, FAMILY_ID, "我想刪除有關0912345678的紀錄", llm_client=llm_client,
    )

    # topic 明碼原樣送進比對用的 Prompt，沒有被換成 [已遮蔽個資]。
    assert "0912345678" in llm_client.last_prompt
    assert "[已遮蔽個資]" not in llm_client.last_prompt
    assert store.get(FAMILY_ID)["topic"] == "0912345678"
    assert "跟「0912345678」有關" in reply


def test_owner_can_trigger_clean_target_dialog_via_slash_command_with_topic(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    fake_db.insert("knowledge_base", {"category": "general_family", "user_id": None, "content": "范麗芳是媽媽"})
    store = ConversationStateStore()
    llm_client = _FakeLLMClient(response_text="1")

    reply = router.handle_message(fake_db, store, ROBIN_ID, "/clean-target-dialog 范麗芳", llm_client=llm_client)

    assert "范麗芳是媽媽" in llm_client.last_prompt  # Owner 觸發才會納入共用知識庫候選
    assert "跟「范麗芳」有關" in reply


def test_clean_target_dialog_confirm_flow_deletes_after_typed_final_confirm(fake_db, monkeypatch):
    # 2026-08-02（FR-16a）：CONFIRM 後先進入最終確認，要再打字輸入「確認執行」才會真的刪除。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    log_id = fake_db.insert(
        "conversation_logs", {"user_id": user_id, "role": "user", "content": "范麗芳人很好", "deleted_at": None}
    )
    store = ConversationStateStore()
    store.set(
        FAMILY_ID,
        {
            "flow": "pending_clean_target_dialog_confirm",
            "target_user_id": user_id,
            "topic": "范麗芳",
            "log_ids": [log_id],
            "kb_ids": [],
        },
    )
    llm_client = _FakeLLMClient(response_text="CONFIRM")

    reply = router.handle_message(fake_db, store, FAMILY_ID, "對，刪掉吧", llm_client=llm_client)

    assert "確認執行" in reply
    assert store.get(FAMILY_ID)["flow"] == "pending_clean_target_dialog_final_confirm"
    logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(user_id,))
    assert len(logs) == 1  # 還沒真的刪除

    final_reply = router.handle_message(fake_db, store, FAMILY_ID, "確認執行")

    assert "已經幫你清除跟「范麗芳」有關的" in final_reply
    assert store.get(FAMILY_ID) is None
    logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(user_id,))
    assert logs == []


def test_owner_can_trigger_clean_all_dialog_confirmation_via_slash_command(fake_db, monkeypatch):
    monkeypatch.setenv("ROBIN_TELEGRAM_TOKEN", str(ROBIN_ID))
    store = ConversationStateStore()

    reply = router.handle_message(fake_db, store, ROBIN_ID, "/clean-all-dialog")

    assert "0 筆對話紀錄" in reply
    assert "確定要清除嗎" in reply
    owner_row = fake_db.select("users", where="telegram_user_id = %s", params=(ROBIN_ID,), fetch_one=True)
    assert store.get(ROBIN_ID) == {
        "flow": "pending_clean_all_dialog_confirm",
        "target_user_id": owner_row["id"],
    }


# --- 圖片辨識（docs/specs/robinson/SPEC.md FR-17、ADR-13）---


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
    store.set(FAMILY_ID, {"flow": "pending_user_knowledge", "target_user_id": 1})
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
    def __init__(self, response_text="/rule"):
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
    voice_client = _FakeVoiceClient(response_text="/rule")

    reply = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice789", 30,
        _FakeTelegramClient(b"raw-ogg"), _FakeGDriveClient(), voice_client,
        voice_lockout_store=lockout_store,
    )

    assert reply == templates.APPENDIX_A_TEXT + router._VOICE_TRANSCRIBED_REMINDER
    assert voice_client.last_audio_bytes == b"raw-ogg"


def test_handle_voice_message_does_not_enforce_lockout_when_store_not_provided(fake_db, monkeypatch):
    # 呼叫端沒傳 voice_lockout_store（例如既有測試不關心這個行為）時，等同停用這個檢查，
    # 不會因為缺少這個參數就意外炸掉或誤鎖。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    voice_client = _FakeVoiceClient(response_text="/rule")

    reply = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice999", 30,
        _FakeTelegramClient(b"raw-ogg"), _FakeGDriveClient(), voice_client,
    )

    assert reply == templates.APPENDIX_A_TEXT + router._VOICE_TRANSCRIBED_REMINDER


def test_handle_voice_message_rejects_within_correction_window(fake_db, monkeypatch):
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

    reply = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice123", 30,
        telegram_client, _FakeGDriveClient(), _FakeVoiceClient(),
    )

    assert reply == router._VOICE_CORRECTION_WINDOW_REPLY
    assert telegram_client.last_file_id is None  # 修正窗口內不該去下載語音檔
    assert len(fake_db.select("media_uploads")) == 1  # 沒有新增第二筆


def test_handle_voice_message_transcribes_and_routes_as_text(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    telegram_client = _FakeTelegramClient(b"raw-ogg-bytes")
    voice_client = _FakeVoiceClient(response_text="/rule")

    reply = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice123", 30,
        telegram_client, _FakeGDriveClient(), voice_client,
    )

    # 轉出來的文字（"/rule"）比照一般文字訊息，走完整的指令分派；後面附註 FR-15 修正窗口提醒
    assert reply == templates.APPENDIX_A_TEXT + router._VOICE_TRANSCRIBED_REMINDER
    assert telegram_client.last_file_id == "voice123"
    assert voice_client.last_audio_bytes == b"raw-ogg-bytes"
    rows = fake_db.select("media_uploads")
    assert len(rows) == 1
    assert rows[0]["media_type"] == "audio"


def test_handle_voice_message_masks_pii_in_transcribed_text_before_logging(fake_db, monkeypatch):
    # 2026-08-02（privacy-masking SPEC.md）：語音轉出文字含個資時，天然經過
    # handle_message() → chat.handle_chat_message() 遮蔽，conversation_logs 存的不是明碼。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    telegram_client = _FakeTelegramClient(b"raw-ogg-bytes")
    voice_client = _FakeVoiceClient(response_text="我的手機是 0912345678")
    llm_client = _FakeLLMClient(response_text="收到！")

    reply = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice123", 30,
        telegram_client, _FakeGDriveClient(), voice_client, llm_client=llm_client,
    )

    assert "0912345678" not in reply
    logs = fake_db.select("conversation_logs", where="user_id = %s", params=(user_id,))
    assert logs[0]["content"] == "我的手機是 [已遮蔽個資]"


def test_handle_voice_message_passes_through_mime_type_for_uploaded_audio(fake_db, monkeypatch):
    # message.audio（上傳的音檔，例如 MP3）走同一支函式，mime_type 要正確透傳到轉錄請求
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    voice_client = _FakeVoiceClient(response_text="/rule")

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
    voice_client = _FakeVoiceClient(response_text="/rule")

    reply = router.handle_voice_message(
        fake_db, store, ROBIN_ID, "voice999", 30,
        _FakeTelegramClient(b"raw-ogg"), _FakeGDriveClient(), voice_client,
    )

    assert reply == templates.APPENDIX_A_TEXT + router._VOICE_TRANSCRIBED_REMINDER
    owner_row = fake_db.select("users", where="telegram_user_id = %s", params=(ROBIN_ID,), fetch_one=True)
    assert owner_row is not None


def test_handle_voice_message_clears_stale_pending_flow_first(fake_db, monkeypatch):
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    store = ConversationStateStore()
    store.set(FAMILY_ID, {"flow": "pending_user_knowledge", "target_user_id": 1})
    voice_client = _FakeVoiceClient(response_text="/rule")

    reply = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice123", 30,
        _FakeTelegramClient(b"raw-ogg"), _FakeGDriveClient(), voice_client,
    )

    assert reply == templates.APPENDIX_A_TEXT + router._VOICE_TRANSCRIBED_REMINDER
    assert store.get(FAMILY_ID) is None


def test_handle_voice_message_short_circuits_final_confirm_without_downloading_or_transcribing(
    fake_db, monkeypatch
):
    # 2026-08-02（FR-16a 追加優化）端到端驗證：使用者卡在「清除所有對話紀錄」的最終確認狀態時，
    # 新語音一定會被拒絕，所以在下載/轉錄之前就直接短路回覆——即使這次語音「內容」剛好會被
    # Whisper 轉成跟關鍵字一字不差的「確認執行」也不重要，因為根本不會走到轉錄這一步；
    # 比照 FR-14/FR-15「先擋才不浪費額度」原則，不該為了一個註定被拒絕的結果還先花 Drive/Groq 額度。
    monkeypatch.delenv("ROBIN_TELEGRAM_TOKEN", raising=False)
    user_id = fake_db.insert("users", {"telegram_user_id": FAMILY_ID, "role": "爸爸", "is_owner": False})
    fake_db.insert("conversation_logs", {"user_id": user_id, "role": "user", "content": "早安", "deleted_at": None})
    store = ConversationStateStore()
    store.set(FAMILY_ID, {"flow": "pending_clean_all_dialog_final_confirm", "target_user_id": user_id})
    telegram_client = _FakeTelegramClient(b"raw-ogg")
    voice_client = _FakeVoiceClient(response_text="確認執行")

    reply = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice123", 30,
        telegram_client, _FakeGDriveClient(), voice_client,
    )

    assert "打字" in reply
    assert store.get(FAMILY_ID) == {"flow": "pending_clean_all_dialog_final_confirm", "target_user_id": user_id}
    # 完全沒有下載、上傳、轉錄——不是「轉錄完才拒絕」，是「連轉錄都沒發生」。
    assert telegram_client.last_file_id is None
    assert voice_client.last_audio_bytes is None
    assert fake_db.select("media_uploads") == []
    logs = fake_db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(user_id,))
    assert len(logs) == 1


def test_handle_voice_message_short_circuits_final_confirm_even_within_correction_window(fake_db, monkeypatch):
    # 最終確認狀態的短路檢查排在 FR-15 修正窗口檢查之前，兩者都會拒絕，但要驗證的是回覆內容
    # 正確對應到最終確認的拒絕文案（而不是被 FR-15 的「15 分鐘內麻煩先用打字」蓋過去）。
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
    store.set(FAMILY_ID, {"flow": "pending_save_knowledge_final_confirm", "category": "custom", "label": None, "content": "x", "row_user_id": user_id})
    telegram_client = _FakeTelegramClient(b"raw-ogg")

    reply = router.handle_voice_message(
        fake_db, store, FAMILY_ID, "voice123", 30,
        telegram_client, _FakeGDriveClient(), _FakeVoiceClient(),
    )

    assert "打字" in reply
    assert reply != router._VOICE_CORRECTION_WINDOW_REPLY
    assert telegram_client.last_file_id is None
