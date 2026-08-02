"""Gemini 對話核心（對應 docs/specs/chat-core/SPEC.md FR-1～FR-10）。

一般聊天訊息（不是任何已知指令、也沒有進行中的對話流程）的最終處理邏輯：
組 prompt（短記憶＋長記憶＋知識庫） → 呼叫 LLM（純文字，不查網路） →
若模型誠實回報不知道，附加「請自行查詢後提供答案」的建議並進入 `pending_user_knowledge` 狀態 →
寫入對話紀錄 → 視 backlog 情況更新長記憶摘要。

2026-07-31：移除 Google Search grounding（見 docs/specs/submodules-core/SPEC.md ADR-8，
supersede ADR-7）——新產生的 Gemini API Key 對 Gemini 2.5 世代模型回傳 404
「no longer available to new users」，grounding 整條路走不通，改為誠實回答不知道，
詳見 chat-core SPEC.md ADR-5（supersede ADR-1）。

2026-07-31 追加修正（日期幻覺）：Robin 回報問「今天幾月幾號」時，模型憑印象瞎掰了一個錯誤
日期，還編造「剛好是我生日」這種知識庫裡根本沒有的內容——LLM 本身沒有即時時鐘，移除 grounding
後更沒有管道查證，只會憑訓練資料的印象亂猜。修正方式：日期是伺服器本地就能算出來的資訊，根本
不需要呼叫任何外部 API，直接把真實日期算好塞進 prompt，並加強「不可捏造具體事實」的規則。

2026-07-31 追加修正（`pending_user_knowledge` 三個邏輯漏洞，見 chat-core SPEC.md ADR-6）：
Robin 回報進入「不知道，請提供答案」狀態後，下一則訊息不管是什麼都會被無條件存進知識庫——
包含使用者其實換了個全新問題、或使用者明確表示「不用紀錄啦」。原設計把「使用者下一則訊息＝
要存的答案」這個假設寫死在程式碼裡，完全沒有判斷空間。改為把「使用者現在是在提供答案、拒絕、
還是問了新問題」這個判斷交給同一次 LLM 呼叫（用 `【SAVE_ANSWER】`／`【DECLINE_SAVE】` 標記，
沒有標記則視為全新訊息、照一般規則正常回答），不再另外開一支「無條件存檔」的函式。

2026-08-01 追加修正（見 chat-core SPEC.md ADR-7、FR-3(f)）：
1. 打字誤植（如「凱」打成「鎧」）原本是「直接假設是同一人並回答」，Robin 覺得應該先反問確認
   比較保險，改為輸出 `【CONFIRM_NAME】` 標記進入 `pending_name_confirm` 狀態，等使用者確認
   後才真正回答，不再自作主張假設。
2. 回答太囉唆——問「Robin 幾歲」不需要複述生日和計算過程，問「牛牛是什麼顏色」不需要整段
   描述，只回核心答案就好；補充精簡原則到 prompt。

2026-08-01 追加修正（代名詞指涉跳回更早的人，見 chat-core SPEC.md FR-3(e) 追加修正）：
Robin 回報連續問「小雯有養動物嗎」→（中間插入「小猴是誰」不知道＋拒絕記錄）→「范麗芳是誰」→
「她老公是誰」，Robinson 誤把「她」理解成更早之前提過的小雯，而不是最近一次才明確點名問過的
范麗芳。原本的代名詞規則只處理「上一輪回答順便提到其他人名」這種情況，沒有明確規範「該用哪一輪
的主體」，也沒有強制「沒把握就要反問」。改為明確要求一律以使用者最近一次明確點名的對象為準
（即使中間隔了其他問題），且只要沒有百分之百把握就必須先反問使用者，不能用可能錯誤的假設硬答。

2026-08-01 再追加修正（見 chat-core SPEC.md FR-3(g)、ADR-7 追加修正）：
1. Robin 回報請 Robinson 把家庭成員背景「新增到知識庫」，Robinson 回覆已經新增，但實際上完全
   沒有對應的寫入路徑——目前唯一真的會寫進 `knowledge_base` 的管道只有 `pending_user_knowledge`
   的 `【SAVE_ANSWER】` 流程。Robinson 等於謊報成功。新增誠實性規則：除了那個流程以外，即使
   使用者明確要求「記住」「新增到知識庫」，也不能宣稱已經記錄，要老實說目前沒辦法主動寫入，
   請使用者轉告 Robin 手動新增。
2. Robin 回報問「阿牛是誰」（知識庫裡當時還沒有這個人／寵物）時，Robinson 反問「你是說『吳凱吉』
   嗎？」——「阿牛」跟「吳凱吉」毫無相似之處，原因是 prompt 裡反問規則的範例寫死了一個真實家人
   姓名「吳凱吉」，模型會照抄這個範例而不是真的去比對知識庫內容。改為要求反問句必須帶出「資料中
   真實存在且真的高度相似」的人名，且明確規定知識庫裡沒有相似人名時要直接走「不知道」規則，
   不可以誤觸發反問機制。

2026-08-01 新增功能（見 chat-core SPEC.md FR-11、ADR-8）：主動新增知識。Robin 要求開發「使用者
主動說要記住某個資訊」的功能（前一輪修正只解決了「不可以謊報已儲存」，還沒有真正提供儲存能力）。
新增 `_REQUEST_SAVE_MARKER`：偵測到使用者明確要求記住/新增/儲存資訊時，先反問確認內容與分類/
標籤，並設定 `pending_save_knowledge_confirm` 狀態；真正的寫入動作留到下一輪由
`commands.handle_save_knowledge_confirm_step()` 執行（沿用 ADR-7 建立的「先反問、下一輪才真的
動作」模式）。依 Robin 決策：只有 Owner（Robin）可以選擇寫入共用的 `general_family`／
`general_persona`，其他使用者一律只能寫入自己的 `custom` 知識庫；因此上方誠實性規則（FR-3g）
也一併更新，改為涵蓋這個新流程，不再只提「請轉告 Robin 手動新增」。

2026-08-02 新增（見 docs/specs/privacy-masking/SPEC.md FR-4）：文字進入這裡的第一件事就是先
呼叫 `privacy.mask_text()`，把疑似個資的內容換成固定遮蔽文字，後續組 Prompt、寫入
`conversation_logs`、（若走 `pending_save_knowledge_confirm` 流程）存進 `knowledge_base` 的
`original_request`，一律用遮蔽後的版本，明碼不會送到 Gemini、也不會落地存下來；有偵測到的話，
在最終回覆最後附加提醒文案，請使用者盡快到 Telegram 對話中自行刪除原始訊息（機器人沒有權限
代為刪除使用者自己傳送的訊息）。`/clean-target-dialog` 的搜尋主題刻意不套用這個遮蔽（見
privacy-masking SPEC.md FR-7），因為那支指令本來就需要讓使用者用個資內容當關鍵字搜尋要刪除
的紀錄，遮蔽反而會讓功能失效。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from submodules.cloudsql.client import CloudSQLClient

from src.bot import auth, knowledge, memory, privacy, templates
from src.bot.state import ConversationStateStore

# 2026-08-02（privacy-masking SPEC.md FR-4）：偵測到疑似個資時附加在回覆最後的固定提醒文案。
_PII_DETECTED_REMINDER = (
    "\n\n（提醒：這則訊息裡有偵測到疑似個人敏感資料，我已經自動遮蔽、不會存下明碼，"
    "但麻煩你盡快到對話紀錄裡手動刪除原始訊息喔，我沒辦法代為刪除你自己傳送的訊息！）"
)

# 系統內部標記，只用來讓程式碼判斷模型的判斷結果，不會出現在使用者看到的回覆裡
# （prompt 已明確指示模型不要跟使用者解釋這些標記）。
_UNKNOWN_MARKER = "【NOT_FOUND】"
_UNKNOWN_SUFFIX = "\n\n你可以先自行上網查詢，查到後把答案打給我，我會幫你記錄到知識庫喔！"
_SAVE_MARKER = "【SAVE_ANSWER】"
_DECLINE_MARKER = "【DECLINE_SAVE】"
_CONFIRM_NAME_MARKER = "【CONFIRM_NAME】"
_REQUEST_SAVE_MARKER = "【REQUEST_SAVE】"

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
    pending_question: str | None = None,
    confirming_question: str | None = None,
    privacy_llm_client=None,
) -> str:
    """處理一般聊天訊息，回傳要回覆的文字。

    `llm_client` 用於本次回覆（`GEMINI_API_BOT_KEY`）；`text_llm_client` 只有在長記憶
    摘要需要更新時才會被呼叫（`GEMINI_API_TEXT_KEY`，見 ADR-12／ADR-3）。

    `pending_question`：不是 None 時，代表使用者上一輪被回覆「不知道 {pending_question}」，
    這一輪由 router 的 `pending_user_knowledge` 分支呼叫（見 ADR-6），交給模型判斷這則新訊息
    是在提供答案、拒絕記錄、還是其實問了個無關的新問題，三種情況分別處理，不再無條件當成答案存檔。

    `confirming_question`：不是 None 時，代表使用者上一輪問了 {confirming_question}，其中的
    人名疑似打字誤植，Robinson 已經反問確認過是不是問知識庫裡最相近的那個人，這一輪由 router 的
    `pending_name_confirm` 分支呼叫（見 ADR-7），交給模型判斷使用者是在確認／回覆，還是問了別的事。

    `privacy_llm_client`（2026-08-02，見 privacy-masking SPEC.md ADR-1／ADR-2）：個資遮蔽 LLM
    語意層專用的獨立 Key（`GEMINI_API_PRIVACY_KEY`），不佔用 `llm_client`／`text_llm_client` 的
    配額；`None` 時 `privacy.mask_text()` 會優雅降級成只跑免費的 Regex 層，不影響其餘邏輯。
    """
    is_owner = auth.is_owner(telegram_user_id)
    text, pii_detected = privacy.mask_text(text, privacy_llm_client)

    context = knowledge.build_context(db, user_id)
    long_memory = memory.get_summary(db, user_id)
    prompt = _build_prompt(context, long_memory, text, pending_question, confirming_question, is_owner)
    reply_text = llm_client.generate_text(prompt)

    knowledge.log_message(db, user_id, "user", text)
    in_pending_flow = pending_question is not None or confirming_question is not None

    if pending_question is not None and _SAVE_MARKER in reply_text:
        knowledge.save_custom_knowledge(db, user_id, text)
        final_reply = "已經幫你記錄到知識庫囉！"
        state_store.clear(telegram_user_id)
    elif pending_question is not None and _DECLINE_MARKER in reply_text:
        final_reply = "好的，這次就不記錄囉！"
        state_store.clear(telegram_user_id)
    elif _CONFIRM_NAME_MARKER in reply_text:
        final_reply = reply_text.replace(_CONFIRM_NAME_MARKER, "").rstrip()
        state_store.set(
            telegram_user_id,
            {"flow": "pending_name_confirm", "target_user_id": user_id, "original_question": text},
        )
    elif _REQUEST_SAVE_MARKER in reply_text:
        # 2026-08-01（FR-11）：使用者主動要求記住/新增知識，先反問確認內容與分類，真正的寫入
        # 動作留到下一輪由 commands.handle_save_knowledge_confirm_step() 執行，這裡不寫資料庫。
        final_reply = reply_text.replace(_REQUEST_SAVE_MARKER, "").rstrip()
        state_store.set(
            telegram_user_id,
            {"flow": "pending_save_knowledge_confirm", "target_user_id": user_id, "original_request": text},
        )
    elif _UNKNOWN_MARKER in reply_text:
        # 保險起見先去掉模型自己可能已經從對話紀錄裡學著複誦出來的建議句，避免跟下面
        # 補上去的固定版本重複兩次（Robin 實測遇過模型看了之前的回覆紀錄就有樣學樣）。
        cleaned = reply_text.replace(_UNKNOWN_MARKER, "").replace(_UNKNOWN_SUFFIX.strip(), "").rstrip()
        final_reply = cleaned + _UNKNOWN_SUFFIX
        state_store.set(
            telegram_user_id,
            {"flow": "pending_user_knowledge", "target_user_id": user_id, "original_question": text},
        )
    else:
        final_reply = reply_text
        if in_pending_flow:
            # 模型判斷這是全新、無關的問題（沒有任何標記），已經照一般規則正常回答了，
            # 不該再讓舊的 pending 狀態留在原地卡住下一輪對話。
            state_store.clear(telegram_user_id)

    knowledge.log_message(db, user_id, "assistant", final_reply)

    # 長記憶摘要更新放在回覆算完、對話紀錄寫入之後才執行，且內部會吞掉例外（見 ADR-3），
    # 確保就算摘要更新失敗，使用者仍然會收到這次的正常回覆。
    memory.maybe_update_summary(db, text_llm_client, user_id)

    # 2026-08-02（privacy-masking SPEC.md FR-4）：提醒文案只附加在「回給使用者看」的這次回傳值，
    # 不寫進 conversation_logs（比照 router._VOICE_TRANSCRIBED_REMINDER 的做法），避免提醒文字
    # 汙染對話紀錄本身、也避免之後被當成對話上下文重新餵給 LLM。
    if pii_detected:
        return final_reply + _PII_DETECTED_REMINDER
    return final_reply


def _build_prompt(
    context: dict,
    long_memory: str,
    user_message: str,
    pending_question: str | None = None,
    confirming_question: str | None = None,
    is_owner: bool = False,
) -> str:
    custom_text = "\n".join(f"- {item}" for item in context["custom"]) or "（無）"
    logs_text = "\n".join(
        f"{'使用者' if log['role'] == 'user' else 'Robinson'}：{log['content']}"
        for log in context["recent_logs"]
    ) or "（無）"

    pending_block = ""
    if pending_question is not None:
        pending_block = (
            "【特別狀況（優先判斷）】使用者上一則訊息問了「" + pending_question + "」，"
            "你已經誠實回覆不知道，並請使用者提供答案。請先判斷使用者這則新訊息屬於下面哪一種情況，"
            "並嚴格只依照對應規則輸出，不要混用：\n"
            "(1) 使用者正在提供上述問題的答案／相關資訊 → 整則回覆只能輸出這個固定標記，"
            f"不要輸出其他任何文字：「{_SAVE_MARKER}」\n"
            "(2) 使用者表示不想提供、不用記錄、想跳過（例如「不用了」「算了」「不用紀錄啦」）→ "
            f"整則回覆只能輸出這個固定標記，不要輸出其他任何文字：「{_DECLINE_MARKER}」\n"
            "(3) 使用者其實是在問一個新的、跟上面那題無關的問題 → 完全忽略這個特別狀況，"
            "把這則新訊息當成一則全新的一般聊天訊息，依照下方所有規則正常回答（該不知道就不知道、"
            "該回答就回答），不要輸出任何標記，也不要假設使用者在回答上一題。\n\n"
        )
    elif confirming_question is not None:
        pending_block = (
            "【特別狀況（優先判斷）】使用者上一則訊息問了「" + confirming_question + "」，裡面的人名"
            "疑似打字誤植，你已經反問確認是不是問知識庫裡最相近的那個人，還沒有真正回答問題。"
            "請先判斷使用者這則新訊息屬於下面哪一種情況：\n"
            "(1) 使用者確認你的猜測、或直接講出更明確的名字 → 針對「" + confirming_question + "」"
            "這個問題，用知識庫裡對應的正確人物資料完整回答，不要再輸出任何標記，也不要再反問一次\n"
            "(2) 使用者否認你的猜測、或其實在問別的事 → 完全忽略這個特別狀況，把這則新訊息當成一則"
            "全新的一般聊天訊息，依照下方所有規則正常回答，不要假設使用者在回答上一題。\n\n"
        )

    if is_owner:
        save_scope_rule = (
            "使用者是 Robin（Owner）：如果內容明顯是關於 Robin 家人的背景資訊（例如新增家庭成員、"
            "寵物、家人近況），可以主動建議存到全家共用的『Robin 與家人背景』；如果內容是關於"
            "Robinson 你自己的人格／行為設定，可以建議存到『Robinson 人格背景』；其餘一般筆記、"
            "SOP、生活知識等個人用途的資訊，建議存到 Robin 自己的個人知識庫；三種都可以選，"
            "依內容判斷最合適的一種，並在反問時講清楚你打算存到哪一種。"
        )
    else:
        save_scope_rule = (
            "這位使用者不是 Robin（Owner）：這一律只會存到使用者自己的個人知識庫，不會影響全家"
            "共用的資料，反問時要讓使用者知道存的是他自己的知識庫。"
        )

    return (
        "你是 Robinson，請完全依照下方的人格背景設定來回答，用溫暖、有同理心、邏輯清晰、直入重點的語氣回覆，"
        "不要用條列式照本宣科的方式回答，也不要說自己是語言模型。回答務必精簡直接：像「幾歲」「什麼顏色」"
        "「是誰」這類單純的事實性問題，只需要給出核心答案本身（例如「快要滿 29 歲」「黑色」），不要主動"
        "附加你是怎麼推算、查到的過程或不必要的背景說明／形容詞堆疊；只有使用者明確要求解釋原因、過程，"
        "或問題本身就需要完整說明時，才展開講詳細一點。\n\n"
        f"{pending_block}"
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
        "使用者問到人名時，只有當這個名字明顯只是輕微的打字誤植（同音字、形似字，例如「凱」打成"
        "「鎧」），且【Robinson 人格背景】／【Robin 與家人背景】／【這位使用者的客製知識庫】裡面"
        "真的存在一個高度相似的真實人名時，才不要直接回答、也不要直接說不知道，先反問確認是不是在問"
        "那個真正相似的人（反問句裡一定要帶出以上資料中真實存在的那個人名，絕對不可以套用其他"
        "不相關、不相似、你自己想到的人名——寧可謹慎判斷相似度，也不要亂猜一個不相干的名字），"
        "並在回覆最後加上這個固定標記文字："
        f"「{_CONFIRM_NAME_MARKER}」（這是系統內部用的標記，使用者看不到，等使用者確認後你才會被要求真正回答）；"
        "如果以上資料裡根本沒有任何跟使用者打的名字相似的人名，代表這是真的不知道，直接依照下面的"
        "「不知道」規則回答即可，不要誤觸發這個反問機制；"
        "如果使用者這則訊息是明確要求你把某個資訊記住／新增／儲存到知識庫（不是在問問題，而是主動"
        "要求你儲存新資訊），不要直接說已經存了（這一輪還沒有真的寫入，見下方誠實性規則），也不要"
        "假裝什麼都沒聽到，而是先用自然口語跟使用者確認：你打算儲存的內容摘要、以及一個簡短的"
        f"分類/標籤（例如「SOP」「食譜」「行程」，依內容自行判斷合適的標籤）。{save_scope_rule}"
        "確認句講完後，在回覆最後加上這個固定標記文字："
        f"「{_REQUEST_SAVE_MARKER}」（這是系統內部用的標記，使用者看不到，等使用者下一輪確認後，"
        "才會由系統真正執行寫入）；"
        "你自己這一輪的回覆，不管是回答問題、反問確認、或任何情況，都絕對不能宣稱『已經記錄』"
        "『已經新增』『已經儲存』『已經存好了』——資料庫的實際寫入只會發生在使用者對上述反問句"
        "回覆確認之後的下一輪（由系統執行，不是你直接做的），你自己永遠沒有立即寫入資料庫的能力；"
        "如果使用者用一般聊天的方式要求「清除」「刪除」對話紀錄或知識庫資料，你也不能假裝已經刪除，"
        "要引導使用者改用「我想要刪除所有對話紀錄」或「我想刪除有關 OOO 的紀錄」這樣的固定講法，"
        "才會真的觸發系統的刪除流程。"
        "如果以上資料不足以回答使用者的問題，你必須誠實地告訴使用者你目前不知道，並且一定要在回覆的最後"
        f"加上這個固定標記文字：「{_UNKNOWN_MARKER}」（這是系統內部用的標記，使用者看不到，不用跟使用者解釋這個標記代表什麼）。"
        "使用者用代名詞（他／她／牠／它／那個人）追問時，一律理解成使用者「最近一次」明確點名問過的那個人"
        "（用完整姓名、稱謂或已經確認過的對象問過的那一輪），即使中間曾經插入其他不相關的問題（例如中途"
        "問了別的人、別的事），也要以那之後最新一次明確點名的對象為準，不可以跳回更早之前提過的人；"
        "不要因為上一輪回答內容裡「順便提到」了其他人名（例如照顧者、配偶、親屬）就誤判代名詞指向那個人；"
        "如果使用者明確糾正（例如「我說的是 OOO」），代表你上一句答錯對象了，這一輪"
        "要針對 OOO 重新回答使用者原本在問的問題（例如年齡、近況等），不能只是重複貼上一輪答過的舊內容；"
        "只要你自己沒有百分之百把握代名詞指的是誰（例如最近幾輪對話中出現過不只一個人名，容易搞混），"
        "絕對不要用可能錯誤的假設硬答，一定要先反問使用者清楚是指誰（例如「你是說范麗芳嗎？」），"
        "寧可多問一句確認，也不要答錯對象。計算年齡等數值"
        "時，一律用上方「現在的日期」跟該人物在知識庫中的正確生日相減計算，不要算錯對象或憑印象亂猜。"
        "功能手冊只有在使用者明確詢問「某個功能可以做什麼／怎麼用」時才拿來用，"
        "回答時要附上至少一組情境範例（若該功能尚無範例就照實說明還沒有範例），並用你自己的口吻改寫，"
        "不要逐字照抄手冊原文；使用者沒有主動問功能細節時，不要主動提起這份手冊內容。\n\n"
        f"使用者現在說：{user_message}"
    )
