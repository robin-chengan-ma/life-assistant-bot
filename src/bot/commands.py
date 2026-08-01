"""內建指令與對話式設定流程（對應 docs/specs/platform-auth/SPEC.md FR-4～FR-6、
docs/specs/feature-toggles/SPEC.md FR-1～FR-2、docs/specs/chat-core/SPEC.md ADR-4、FR-10）。"""
from datetime import datetime, timezone

from submodules.cloudsql.client import CloudSQLClient

from src.bot import knowledge, templates, toggles
from src.bot.state import ConversationStateStore

_EXIT_PHRASES = {"沒有了", "結束"}


def handle_rule() -> str:
    """/rule：回傳規範文本，不經過 LLM 生成。"""
    return templates.APPENDIX_A_TEXT


_CLEAN_ALL_DIALOG_CONFIRM_PROMPT = (
    "使用者剛被 Robinson 反問「確定要清除所有對話紀錄嗎？」，這是使用者這一則的回覆：「{text}」。\n"
    "請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 確定要清除 → CONFIRM\n"
    "(2) 不要清除、想取消、還沒想清楚、或其實在問別的事 → CANCEL"
)


def start_clean_all_dialog_confirm(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    user_id: int,
) -> str:
    """/clean-all-dialog 觸發時先反問確認，不直接執行刪除（2026-08-01 追加，見 chat-core SPEC.md FR-10 追加修正）。

    Robin 回報原本一觸發就直接刪除，沒有給使用者反悔機會，違反「任何操作都要先確認再執行」的原則
    （FR-16）。改為先查出目前有幾筆未刪除的 `conversation_logs` 告知使用者，進入
    `pending_clean_all_dialog_confirm` 狀態，等使用者下一則訊息確認後才真正執行刪除。
    """
    count = len(db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(user_id,)))
    state_store.set(telegram_user_id, {"flow": "pending_clean_all_dialog_confirm", "target_user_id": user_id})
    return f"你目前有 {count} 筆對話紀錄，確定要清除嗎？（不會影響你的知識庫內容）"


def handle_clean_all_dialog_confirm_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_clean_all_dialog_confirm` 狀態下使用者對刪除確認的回覆。

    用單次 LLM 呼叫判斷使用者是「確定」還是「取消」（沿用 ADR-6／ADR-7 已建立的單次呼叫＋
    固定標記慣例），避免關鍵字窮舉不了「好啊刪掉吧」「不用了」等各種講法；判斷不出來或任何非
    `CONFIRM` 的回覆一律視為取消，寧可保守也不要誤刪。
    """
    state = state_store.get(telegram_user_id)
    user_id = state["target_user_id"]
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_CLEAN_ALL_DIALOG_CONFIRM_PROMPT.format(text=text)).strip()
    if decision == "CONFIRM":
        return handle_clean_all_dialog(db, user_id)
    return "好的，先不清除，你的對話紀錄都還在喔！"


def handle_clean_all_dialog(db: CloudSQLClient, user_id: int) -> str:
    """清除使用者自己的全部對話紀錄（短記憶＋長記憶摘要），對應 FR-10。

    只清「對話」——`conversation_logs`（軟刪除，比照既有 `deleted_at` 慣例）與
    `conversation_summaries`（重置為空白摘要，watermark 歸零）。刻意不動 `knowledge_base`：
    這是與「刪除特定主題相關紀錄」（規劃中的 `/clean-target-dialog`，會同時清知識庫）不同的指令，
    見 chat-core SPEC.md FR-10 備註。**2026-08-01 起不再由觸發詞直接呼叫**，一律先經過
    `start_clean_all_dialog_confirm()` 反問確認，使用者確認後才由 `handle_clean_all_dialog_confirm_step()`
    呼叫這個函式執行實際刪除。
    """
    db.update(
        "conversation_logs",
        {"deleted_at": datetime.now(timezone.utc)},
        where="user_id = %s AND deleted_at IS NULL",
        params=(user_id,),
    )
    db.update(
        "conversation_summaries",
        {"summary": "", "summarized_up_to_log_id": 0, "updated_at": datetime.now(timezone.utc)},
        where="user_id = %s",
        params=(user_id,),
    )
    return "已經幫你清除所有對話紀錄囉！你的知識庫內容不會受影響。"


def handle_function(db: CloudSQLClient, llm_client) -> str:
    """/function：回傳「功能總覽」（見 chat-core SPEC.md ADR-4）。

    只回傳功能名稱＋一句話簡述＋權限標記，不展開細節或範例（FR-56）；使用者針對特定
    功能追問時，改由一般聊天核心處理（見 `chat._build_prompt` 的功能手冊區塊，FR-56a／b）。
    依 FR-56c，這裡不能把 `templates.build_function_overview_raw_text()` 的原始清單直接
    回傳給使用者，一定要先參考人格背景、經過一次 LLM 呼叫改寫成口語才回覆。
    """
    persona = knowledge.get_persona_text(db)
    raw_overview = templates.build_function_overview_raw_text()
    prompt = (
        "你是 Robinson，請完全依照下方的人格背景設定來回答，用溫暖、自然口語的語氣。\n\n"
        f"【Robinson 人格背景】\n{persona}\n\n"
        "以下是目前所有功能的原始清單資料（僅供你參考組織內容，不可逐字照抄）：\n"
        f"{raw_overview}\n\n"
        "請把這份清單改寫成給使用者看的『功能總覽』：條列每個功能的名稱與一句話說明，"
        "並清楚標示哪些功能僅 Robin 本人可用、哪些全體使用者皆可用；不要展開任何功能的細節或範例，"
        "使用者之後若想深入了解特定功能，可以直接追問。"
    )
    return llm_client.generate_text(prompt)


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
