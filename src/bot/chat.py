"""Gemini 對話核心（對應 docs/specs/chat-core/SPEC.md FR-1～FR-8）。

一般聊天訊息（不是任何已知指令、也沒有進行中的對話流程）的最終處理邏輯：
組 prompt（短記憶＋長記憶＋知識庫） → 呼叫 LLM（純文字，不查網路） →
若模型誠實回報不知道，附加「請自行查詢後提供答案」的建議並進入 `pending_user_knowledge` 狀態 →
寫入對話紀錄 → 視 backlog 情況更新長記憶摘要。

2026-07-31：移除 Google Search grounding（見 docs/specs/submodules-core/SPEC.md ADR-8，
supersede ADR-7）——新產生的 Gemini API Key 對 Gemini 2.5 世代模型回傳 404
「no longer available to new users」，grounding 整條路走不通，改為誠實回答不知道，
詳見 chat-core SPEC.md ADR-5（supersede ADR-1）。

2026-07-31 追加修正：Robin 回報問「今天幾月幾號」時，模型憑印象瞎掰了一個錯誤日期，還編造
「剛好是我生日」這種知識庫裡根本沒有的內容——LLM 本身沒有即時時鐘，移除 grounding 後更沒有
管道查證，只會憑訓練資料的印象亂猜。修正方式：日期是伺服器本地就能算出來的資訊，根本不需要
呼叫任何外部 API，直接把真實日期算好塞進 prompt，並加強「不可捏造具體事實」的規則，見
chat-core SPEC.md FR-3 補充。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from submodules.cloudsql.client import CloudSQLClient

from src.bot import knowledge, memory, templates
from src.bot.state import ConversationStateStore

# 系統內部標記，只用來讓程式碼判斷「模型誠實回報不知道」，不會出現在使用者看到的回覆裡
# （prompt 已明確指示模型不要跟使用者解釋這個標記）。
_UNKNOWN_MARKER = "【NOT_FOUND】"
_UNKNOWN_SUFFIX = "\n\n你可以先自行上網查詢，查到後把答案打給我，我會幫你記錄到知識庫喔！"

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_WEEKDAY_NAMES = ["一", "二", "三", "四", "五", "六", "日"]


def _now() -> datetime:
    """回傳現在的台灣時間；獨立成函式方便測試用 monkeypatch 固定時間點。"""
    return datetime.now(_TAIWAN_TZ)


def _current_date_text() -> str:
    now = _now()
    return f"{now.year}年{now.month}月{now.day}日 星期{_WEEKDAY_NAMES[now.weekday()]}"


def handle_chat_message(
    db: CloudSQLClient,
    llm_client,
    text_llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    user_id: int,
    text: str,
) -> str:
    """處理一般聊天訊息，回傳要回覆的文字。

    `llm_client` 用於本次回覆（`GEMINI_API_BOT_KEY`）；`text_llm_client` 只有在長記憶
    摘要需要更新時才會被呼叫（`GEMINI_API_TEXT_KEY`，見 ADR-12／ADR-3）。
    """
    context = knowledge.build_context(db, user_id)
    long_memory = memory.get_summary(db, user_id)
    prompt = _build_prompt(context, long_memory, text)
    reply_text = llm_client.generate_text(prompt)

    knowledge.log_message(db, user_id, "user", text)

    if _UNKNOWN_MARKER in reply_text:
        final_reply = reply_text.replace(_UNKNOWN_MARKER, "").rstrip() + _UNKNOWN_SUFFIX
        state_store.set(
            telegram_user_id,
            {"flow": "pending_user_knowledge", "target_user_id": user_id},
        )
    else:
        final_reply = reply_text

    knowledge.log_message(db, user_id, "assistant", final_reply)

    # 長記憶摘要更新放在回覆算完、對話紀錄寫入之後才執行，且內部會吞掉例外（見 ADR-3），
    # 確保就算摘要更新失敗，使用者仍然會收到這次的正常回覆。
    memory.maybe_update_summary(db, text_llm_client, user_id)

    return final_reply


def handle_pending_user_knowledge_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理「不知道答案」後，使用者主動提供答案的下一則回覆（chat-core SPEC.md ADR-5）。

    不需要額外的 yes/no 確認：使用者會被明確告知「查到後把答案打給我」，
    所以下一則訊息本身就是要存進客製知識庫的內容。
    """
    state = state_store.get(telegram_user_id)
    state_store.clear(telegram_user_id)

    knowledge.save_custom_knowledge(db, state["target_user_id"], text)
    return "已經幫你記錄到知識庫囉！"


def _build_prompt(context: dict, long_memory: str, user_message: str) -> str:
    custom_text = "\n".join(f"- {item}" for item in context["custom"]) or "（無）"
    logs_text = "\n".join(
        f"{'使用者' if log['role'] == 'user' else 'Robinson'}：{log['content']}"
        for log in context["recent_logs"]
    ) or "（無）"

    return (
        "你是 Robinson，請完全依照下方的人格背景設定來回答，用溫暖、有同理心、邏輯清晰、直入重點的語氣回覆，"
        "不要用條列式照本宣科的方式回答，也不要說自己是語言模型。\n\n"
        f"【現在的日期（台灣時區，回答日期／星期相關問題一律以此為準）】\n{_current_date_text()}\n\n"
        f"【Robinson 人格背景】\n{context['persona']}\n\n"
        f"【Robin 與家人背景】\n{context['family']}\n\n"
        f"【這位使用者的客製知識庫】\n{custom_text}\n\n"
        f"【長記憶摘要（更早以前聊過的重點，僅供參考，可能不完全精確）】\n{long_memory or '（無）'}\n\n"
        f"【最近對話紀錄】\n{logs_text}\n\n"
        f"【功能手冊（見 chat-core SPEC.md ADR-4）】\n{templates.build_function_manual_text()}\n\n"
        "回答規則：只根據以上資料回答，你沒有查詢網路的能力；日期／星期問題只能依上方「現在的日期」回答，"
        "不可以自己推算或憑印象亂猜；除了以上資料明確提到的內容，絕對不能捏造任何具體事實"
        "（例如生日、事件細節、數字），寧可誠實說不知道也不要瞎掰聽起來合理的答案；"
        "如果以上資料不足以回答使用者的問題，你必須誠實地告訴使用者你目前不知道，並且一定要在回覆的最後"
        f"加上這個固定標記文字：「{_UNKNOWN_MARKER}」（這是系統內部用的標記，使用者看不到，不用跟使用者解釋這個標記代表什麼）。"
        "使用者用代名詞（他／她／牠／它／那個人）追問時，一律理解成【最近對話紀錄】裡使用者剛剛在問、"
        "討論的那個主體，不要因為上一輪回答內容裡「順便提到」了其他人名（例如照顧者、配偶、親屬）就誤判"
        "代名詞指向那個人；如果使用者明確糾正（例如「我說的是 OOO」），代表你上一句答錯對象了，這一輪"
        "要針對 OOO 重新回答使用者原本在問的問題（例如年齡、近況等），不能只是重複貼上一輪答過的舊內容；"
        "如果真的無法判斷代名詞指的是誰，直接反問使用者是指誰，不要用可能錯誤的假設硬答。計算年齡等數值"
        "時，一律用上方「現在的日期」跟該人物在知識庫中的正確生日相減計算，不要算錯對象或憑印象亂猜。"
        "功能手冊只有在使用者明確詢問「某個功能可以做什麼／怎麼用」時才拿來用，"
        "回答時要附上至少一組情境範例（若該功能尚無範例就照實說明還沒有範例），並用你自己的口吻改寫，"
        "不要逐字照抄手冊原文；使用者沒有主動問功能細節時，不要主動提起這份手冊內容。\n\n"
        f"使用者現在說：{user_message}"
    )
