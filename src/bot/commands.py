"""內建指令與對話式設定流程（對應 docs/specs/platform-auth/SPEC.md FR-4～FR-6、
docs/specs/feature-toggles/SPEC.md FR-1～FR-2）。"""
from submodules.cloudsql.client import CloudSQLClient

from src.bot import templates, toggles
from src.bot.state import ConversationStateStore

_EXIT_PHRASES = {"沒有了", "結束"}


def handle_rule() -> str:
    """/rule：回傳規範文本，不經過 LLM 生成。"""
    return templates.APPENDIX_A_TEXT


def handle_function() -> str:
    """/function：回傳目前功能清單，不經過 LLM 生成。"""
    return templates.build_function_list_text()


def start_set_invite_codes(state_store: ConversationStateStore, telegram_user_id: int) -> str:
    """Robin 觸發 /set_invite_codes：進入設定模式，詢問第一位家人的稱謂。"""
    state_store.set(telegram_user_id, {"flow": "set_invite_codes", "step": "awaiting_role"})
    return "請問要設定哪一位家人的稱謂？（例如：爸爸）"


def handle_set_invite_codes_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """依目前對話狀態處理 Robin 在設定模式中輸入的下一句話。"""
    state = state_store.get(telegram_user_id)
    step = state.get("step") if state else None

    if step == "awaiting_role":
        if text in _EXIT_PHRASES:
            state_store.clear(telegram_user_id)
            return "好的，已結束通關密碼設定模式！"

        state_store.set(telegram_user_id, {"flow": "set_invite_codes", "step": "awaiting_code", "role": text})
        return f"收到，請輸入『{text}』專屬的通關密碼："

    if step == "awaiting_code":
        role = state["role"]
        user_id = db.insert("users", {"telegram_user_id": None, "role": role, "is_owner": False})
        db.insert("invite_codes", {"code": text, "is_used": False, "user_id": user_id})

        state_store.set(telegram_user_id, {"flow": "set_invite_codes", "step": "awaiting_role"})
        return "已寫入！請問還有其他家人要設定嗎？"

    raise ValueError(f"未知的對話狀態：{state}")


def start_my_toggles(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    user_id: int,
) -> str:
    """/my_toggles：補齊使用者自己的預設開關資料，列出目前狀態並進入切換模式。"""
    toggles.ensure_default_toggles(db, user_id)
    toggle_list = toggles.get_toggles(db, user_id)
    state_store.set(telegram_user_id, {"flow": "toggle", "step": "awaiting_index", "target_user_id": user_id})
    return toggles.format_toggle_list(toggle_list)


def start_set_toggle(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int) -> str:
    """/set_toggle：僅 Owner 觸發，列出所有已綁定的非 Owner 使用者供選擇要代管誰的開關。"""
    candidates = [u for u in db.select("users") if u["telegram_user_id"] is not None and not u["is_owner"]]
    if not candidates:
        return "目前還沒有其他家人綁定成功，沒有可以代管的對象喔！"

    state_store.set(
        telegram_user_id,
        {"flow": "set_toggle", "step": "awaiting_user_selection", "candidates": [u["id"] for u in candidates]},
    )
    lines = ["請問要調整哪一位家人的功能開關？", ""]
    for index, user in enumerate(candidates, start=1):
        lines.append(f"{index}. {user['role']}")
    return "\n".join(lines)


def handle_toggle_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """依目前對話狀態處理 /my_toggles、/set_toggle 流程中輸入的下一句話。"""
    state = state_store.get(telegram_user_id)
    step = state.get("step") if state else None

    if step == "awaiting_user_selection":
        if text in _EXIT_PHRASES:
            state_store.clear(telegram_user_id)
            return "好的，已結束功能開關代管模式！"

        candidates = state["candidates"]
        if not text.isdigit() or not (1 <= int(text) <= len(candidates)):
            return f"請輸入 1～{len(candidates)} 之間的編號喔！"

        target_user_id = candidates[int(text) - 1]
        toggles.ensure_default_toggles(db, target_user_id)
        toggle_list = toggles.get_toggles(db, target_user_id)
        state_store.set(
            telegram_user_id,
            {"flow": "set_toggle", "step": "awaiting_index", "target_user_id": target_user_id},
        )
        return toggles.format_toggle_list(toggle_list)

    if step == "awaiting_index":
        if text in _EXIT_PHRASES:
            state_store.clear(telegram_user_id)
            return "好的，已結束功能開關設定模式！"

        target_user_id = state["target_user_id"]
        if not text.isdigit():
            return "請輸入數字編號喔！"

        result = toggles.toggle_by_index(db, target_user_id, int(text))
        if result is None:
            return "編號不存在，請重新輸入喔！"

        status = "開啟" if result["is_enabled"] else "關閉"
        toggle_list = toggles.get_toggles(db, target_user_id)
        return f"已將「{result['name']}」切換為{status}！\n\n{toggles.format_toggle_list(toggle_list)}"

    raise ValueError(f"未知的對話狀態：{state}")
