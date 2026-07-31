"""Gemini 對話核心（對應 docs/specs/chat-core/SPEC.md FR-1～FR-5）。

一般聊天訊息（不是任何已知指令、也沒有進行中的對話流程）的最終處理邏輯：
組 prompt → 呼叫 LLM（帶 Google Search 工具） → 視情況詢問是否存檔 → 寫入對話紀錄。
"""
from submodules.cloudsql.client import CloudSQLClient

from src.bot import knowledge
from src.bot.state import ConversationStateStore

_SAVE_CONFIRM_PHRASES = {"要", "好", "記錄", "儲存", "存"}
_SAVE_PROMPT_SUFFIX = "\n\n這個答案我剛剛上網查的，要不要幫你記錄到你的知識庫呢？（回覆「要」即可）"


def handle_chat_message(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    user_id: int,
    text: str,
) -> str:
    """處理一般聊天訊息，回傳要回覆的文字。"""
    context = knowledge.build_context(db, user_id)
    prompt = _build_prompt(context, text)
    reply_text, used_search = llm_client.generate_with_search(prompt)

    knowledge.log_message(db, user_id, "user", text)

    if used_search:
        final_reply = reply_text + _SAVE_PROMPT_SUFFIX
        state_store.set(
            telegram_user_id,
            {"flow": "pending_kb_save", "content": reply_text, "target_user_id": user_id},
        )
    else:
        final_reply = reply_text

    knowledge.log_message(db, user_id, "assistant", final_reply)
    return final_reply


def handle_pending_kb_save_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理「要不要存檔」詢問的下一則回覆（FR-4）。"""
    state = state_store.get(telegram_user_id)
    state_store.clear(telegram_user_id)

    if text in _SAVE_CONFIRM_PHRASES:
        knowledge.save_custom_knowledge(db, state["target_user_id"], state["content"])
        return "已經幫你記錄到知識庫囉！"

    return "好的，這次就不記錄囉！"


def _build_prompt(context: dict, user_message: str) -> str:
    custom_text = "\n".join(f"- {item}" for item in context["custom"]) or "（無）"
    logs_text = "\n".join(
        f"{'使用者' if log['role'] == 'user' else 'Robinson'}：{log['content']}"
        for log in context["recent_logs"]
    ) or "（無）"

    return (
        "你是 Robinson，請完全依照下方的人格背景設定來回答，用溫暖、有同理心、邏輯清晰、直入重點的語氣回覆，"
        "不要用條列式照本宣科的方式回答，也不要說自己是語言模型。\n\n"
        f"【Robinson 人格背景】\n{context['persona']}\n\n"
        f"【Robin 與家人背景】\n{context['family']}\n\n"
        f"【這位使用者的客製知識庫】\n{custom_text}\n\n"
        f"【最近對話紀錄】\n{logs_text}\n\n"
        "回答規則：優先根據以上資料回答；如果以上資料不足以回答，才使用 Google Search 工具查詢網路取得正確資訊，"
        "並確實根據查到的內容回答。\n\n"
        f"使用者現在說：{user_message}"
    )
