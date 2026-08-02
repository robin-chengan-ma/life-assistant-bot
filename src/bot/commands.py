"""內建指令與對話式設定流程（對應 docs/specs/platform-auth/SPEC.md FR-4～FR-6、
docs/specs/feature-toggles/SPEC.md FR-1～FR-2、docs/specs/chat-core/SPEC.md ADR-4、FR-10～FR-12、
docs/specs/robinson/SPEC.md FR-20、FR-31、FR-31a、FR-32、FR-49、FR-50、FR-60～FR-63）。"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from submodules.cloudsql.client import CloudSQLClient

from src.bot import auth, complaint as complaint_module, knowledge, mood, privacy, templates, toggles
from src.bot import todo as todo_module
from src.bot.state import ConversationStateStore

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")

# 2026-08-02（見 docs/specs/privacy-masking/SPEC.md FR-4）：跟 chat.py 的 _PII_DETECTED_REMINDER
# 文字完全一致，刻意在這裡獨立定義一份而不是從 chat.py 匯入——那是 chat 模組的私有常數，跨模組
# 依賴私有成員容易在對方調整內部實作時悄悄壞掉，這則提醒文案又短，重複定義的維護成本很低。
_PII_DETECTED_REMINDER = (
    "\n\n（提醒：這則訊息裡有偵測到疑似個人敏感資料，我已經自動遮蔽、不會存下明碼，"
    "但麻煩你盡快到對話紀錄裡手動刪除原始訊息喔，我沒辦法代為刪除你自己傳送的訊息！）"
)

_logger = logging.getLogger(__name__)

_EXIT_PHRASES = {"沒有了", "結束"}

# 2026-08-02（Step 1.6，見 robinson SPEC.md FR-20）：Robin 手動確認修復完成後用來廣播的固定
# 文案；Phase 1 沒有 Step 2.4 的 AI 自主修復流程，「有沒有修好」完全是 Robin 自己判斷，
# `/recovered` 只負責「廣播」這個動作本身。
_RECOVERED_BROADCAST_TEXT = "🎉 主任，我已經完全康復了！剛剛的問題已經修好，現在可以正常為大家服務囉！"

# 2026-08-02（robinson SPEC.md FR-16a）：所有「會實際刪除/寫入資料」的確認流程，在 LLM 判斷
# 使用者已經表達 CONFIRM 之後，不會馬上執行，而是多一層更嚴格的把關——要求逐字打字輸入這個
# 固定關鍵字才算數。背景：Robin 指出語音輸入可能被 Whisper 聽錯（例如把「不要」聽成「要」），
# 若聽錯的當下剛好命中一次就足以觸發的刪除動作，事後不可能回頭補救；單靠一次寬鬆的 LLM
# CONFIRM/CANCEL 語意分類撐不住這個風險，所以在「語意上的確認」之後，再加一道「逐字打字」的
# 硬性關卡，且這一關只接受打字（`via_voice=True` 一律拒絕，見各 `handle_*_final_confirm_step`）。
_FINAL_EXECUTE_KEYWORD = "確認執行"


def _final_execute_prompt_reply(preview: str) -> str:
    """組出「進入最終確認」這一輪的固定回覆格式，供三個高風險 flow 共用。"""
    return f"{preview}這個動作沒辦法復原，請直接打字輸入「{_FINAL_EXECUTE_KEYWORD}」來真正執行（這一步語音沒辦法完成）。"


def _voice_blocked_final_confirm_reply() -> str:
    """`pending_*_final_confirm` 狀態下收到語音輸入時的固定拒絕文案（不清除狀態，可直接補打字重試）。"""
    return f"這一步一定要用打字完成才能執行喔，請直接打字輸入「{_FINAL_EXECUTE_KEYWORD}」！"


def handle_rule() -> str:
    """/rule：回傳規範文本，不經過 LLM 生成。"""
    return templates.APPENDIX_A_TEXT


def handle_recovered(db: CloudSQLClient, telegram_client) -> str:
    """/recovered（Owner 專屬，見 robinson SPEC.md FR-20）：廣播「我康復了」給所有已綁定家人。

    刻意排除 Robin 自己（`is_owner = TRUE`）：他就是下這個指令的人，不需要廣播給自己，
    這個函式的回傳值（回覆給 Robin 的確認文字）已經算是給他的直接回饋。單一家人傳送失敗
    不影響其他人，逐一 try/except、記錄失敗但繼續廣播下一位，最後回報實際成功通知的人數。
    """
    family_users = db.select(
        "users",
        columns=("telegram_user_id",),
        where="telegram_user_id IS NOT NULL AND is_owner = FALSE",
    )
    notified_count = 0
    for user in family_users:
        try:
            telegram_client.send_text(chat_id=user["telegram_user_id"], text=_RECOVERED_BROADCAST_TEXT)
            notified_count += 1
        except Exception:
            _logger.exception("廣播「我康復了」給 telegram_user_id=%s 失敗", user["telegram_user_id"])
    return f"好的！已經通知 {notified_count} 位家人我恢復正常運作了！"


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

    2026-08-02（FR-16a）：這裡判斷出 `CONFIRM` 後**不會馬上刪除**，而是轉入
    `pending_clean_all_dialog_final_confirm`，見 `handle_clean_all_dialog_final_confirm_step()`。
    """
    state = state_store.get(telegram_user_id)
    user_id = state["target_user_id"]
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_CLEAN_ALL_DIALOG_CONFIRM_PROMPT.format(text=text)).strip()
    if decision != "CONFIRM":
        return "好的，先不清除，你的對話紀錄都還在喔！"

    state_store.set(telegram_user_id, {"flow": "pending_clean_all_dialog_final_confirm", "target_user_id": user_id})
    return _final_execute_prompt_reply("我理解你要清除所有對話紀錄，")


def handle_clean_all_dialog_final_confirm_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
    via_voice: bool = False,
) -> str:
    """處理 `pending_clean_all_dialog_final_confirm` 狀態下的最終執行確認（2026-08-02，FR-16a）。

    語音輸入一律拒絕、不清除狀態（讓使用者可以直接補一則打字訊息重試，不必整個流程重來）；
    打字但沒有逐字輸入 `_FINAL_EXECUTE_KEYWORD` 一律視為取消，保守優先、不誤刪。
    """
    if via_voice:
        return _voice_blocked_final_confirm_reply()

    state = state_store.get(telegram_user_id)
    user_id = state["target_user_id"]
    state_store.clear(telegram_user_id)

    if text.strip() != _FINAL_EXECUTE_KEYWORD:
        return "好的，先不清除，你的對話紀錄都還在喔！"
    return handle_clean_all_dialog(db, user_id)


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


_SAVE_KNOWLEDGE_CATEGORY_NAMES = {
    "custom": "你的個人知識庫",
    "general_family": "Robin 與家人背景知識庫",
    "general_persona": "Robinson 人格背景知識庫",
}

_SAVE_KNOWLEDGE_EXTRACT_PROMPT = (
    "使用者先前這樣要求 Robinson 記住/新增一筆知識：「{original_request}」，Robinson 已經反問"
    "確認過，這是使用者這一則的回覆：「{reply}」。\n"
    "{scope_hint}\n"
    "請判斷使用者是否確定要儲存，並整理出要儲存的內容與適合的分類標籤，嚴格照下面格式輸出，"
    "每個欄位各自一行，不要輸出其他任何文字：\n"
    "DECISION: CONFIRM 或 CANCEL\n"
    "CATEGORY: custom 或 general_family 或 general_persona（使用者確定要儲存時才需要填寫，"
    "取消的話這行可以省略）\n"
    "LABEL: 簡短的分類/標籤，例如 SOP、食譜、行程（取消的話可以省略）\n"
    "CONTENT: 要儲存的完整內容文字（取消的話可以省略）"
)

_SAVE_KNOWLEDGE_OWNER_SCOPE_HINT = (
    "使用者是 Robin（Owner），CATEGORY 可以填 custom、general_family 或 general_persona，"
    "請依內容判斷最適合的類別（家人背景相關 → general_family；Robinson 自身人格/行為相關 → "
    "general_persona；其餘個人筆記、SOP、生活知識等 → custom）。"
)
_SAVE_KNOWLEDGE_NON_OWNER_SCOPE_HINT = "使用者不是 Owner，CATEGORY 一律只能填 custom。"


def handle_save_knowledge_confirm_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_save_knowledge_confirm` 狀態下使用者對「主動新增知識」請求的確認回覆
    （2026-08-01 新增，見 chat-core SPEC.md FR-11、ADR-8）。

    用單次、完全對內部用（不會直接顯示給使用者）的 LLM 呼叫同時判斷「確定/取消」與整理出
    「分類、標籤、內容」三個欄位，比照 ADR-6／ADR-7 的單次呼叫慣例。是否為 Owner 一律用
    `auth.is_owner(telegram_user_id)` 現場判斷，不信任模型自己的判斷結果——即使模型回傳
    `general_family`／`general_persona`，非 Owner 使用者也會被強制改回 `custom`，這是最後一道
    伺服器端防線，避免任何情況下家人不小心（或被誘導）寫入全家共用的知識庫（依 Robin 決策：
    共用知識庫只有 Owner 能編輯）。

    2026-08-02（FR-16a）：判斷出 `CONFIRM` 後**不會馬上寫入**，權限強制（`category` 改回
    `custom`）已經在這裡做完，接著轉入 `pending_save_knowledge_final_confirm`，見
    `handle_save_knowledge_final_confirm_step()`——那一步不會重新判斷權限，只會照搬這裡已經
    算好的 `category`/`label`/`content`/`row_user_id`。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    original_request = state["original_request"]
    state_store.clear(telegram_user_id)

    is_owner_user = auth.is_owner(telegram_user_id)
    scope_hint = _SAVE_KNOWLEDGE_OWNER_SCOPE_HINT if is_owner_user else _SAVE_KNOWLEDGE_NON_OWNER_SCOPE_HINT
    prompt = _SAVE_KNOWLEDGE_EXTRACT_PROMPT.format(
        original_request=original_request, reply=text, scope_hint=scope_hint,
    )
    parsed = _parse_key_value_block(llm_client.generate_text(prompt))

    if parsed.get("DECISION") != "CONFIRM":
        return "好的，先不儲存這筆資訊！"

    category = parsed.get("CATEGORY", "custom").lower()
    if not is_owner_user or category not in _SAVE_KNOWLEDGE_CATEGORY_NAMES:
        category = "custom"
    label = parsed.get("LABEL") or None
    content = parsed.get("CONTENT") or original_request
    row_user_id = target_user_id if category == "custom" else None

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_save_knowledge_final_confirm",
            "category": category,
            "label": label,
            "content": content,
            "row_user_id": row_user_id,
        },
    )
    category_name = _SAVE_KNOWLEDGE_CATEGORY_NAMES[category]
    label_part = f"「{label}」分類、" if label else ""
    return _final_execute_prompt_reply(f"我理解你要存到{category_name}，{label_part}內容是：{content}，")


def handle_save_knowledge_final_confirm_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
    via_voice: bool = False,
) -> str:
    """處理 `pending_save_knowledge_final_confirm` 狀態下的最終儲存確認（2026-08-02，FR-16a）。

    寫入知識庫雖不像刪除紀錄那樣完全不可逆（事後仍可用 `/clean-target-dialog` 補刪），但錯誤
    寫入一樣會造成困擾，比照 `handle_clean_all_dialog_final_confirm_step()` 同樣的兩層確認架構。
    """
    if via_voice:
        return _voice_blocked_final_confirm_reply()

    state = state_store.get(telegram_user_id)
    category = state["category"]
    label = state["label"]
    content = state["content"]
    row_user_id = state["row_user_id"]
    state_store.clear(telegram_user_id)

    if text.strip() != _FINAL_EXECUTE_KEYWORD:
        return "好的，先不儲存這筆資訊！"

    knowledge.save_knowledge(db, category=category, content=content, label=label, user_id=row_user_id)

    category_name = _SAVE_KNOWLEDGE_CATEGORY_NAMES[category]
    label_part = f"「{label}」分類、" if label else ""
    return f"已經幫你存到{category_name}囉！{label_part}內容是：{content}"


def _parse_key_value_block(raw: str) -> dict:
    """解析單次內部 LLM 呼叫回傳的 `KEY: value` 格式區塊（每行一個欄位），供本模組內部共用。"""
    data: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip().upper()] = value.strip()
    return data


_CLEAN_TARGET_MATCH_PROMPT = (
    "以下是使用者的對話紀錄與知識庫資料候選清單，每一項前面有編號：\n"
    "{candidates}\n\n"
    "請找出所有跟主題「{topic}」有關的項目（只要內容有提到、談到、或與這個主題明顯相關就算）。\n"
    "整則回覆只能輸出符合的編號，用逗號分隔（例如：1,3,5），不要輸出其他任何文字；"
    "如果完全沒有符合的項目，只回傳：NONE"
)

_CLEAN_TARGET_CONFIRM_PROMPT = (
    "使用者剛被 Robinson 反問「確定要清除跟『{topic}』有關的紀錄嗎？」，這是使用者這一則的回覆："
    "「{reply}」。\n"
    "請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 確定要清除 → CONFIRM\n"
    "(2) 不要清除、想取消、還沒想清楚、或其實在問別的事 → CANCEL"
)


def start_clean_target_dialog_confirm(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    user_id: int,
    is_owner: bool,
    topic: str,
) -> str:
    """`/clean-target-dialog`／「我想刪除有關 OOO 的紀錄」：清除跟指定主題相關的對話紀錄與知識庫
    資料（2026-08-01 新增，見 chat-core SPEC.md FR-12、ADR-8）。

    與 FR-10 的 `/clean-all-dialog` 不同：這支「也會」清知識庫，不是只清對話。範圍依 Robin 決策：
    一般使用者只會檢視、清除「自己的」`conversation_logs` 與自己的 `custom` 知識庫；只有 Owner
    （Robin）觸發時才會額外把共用的 `general_family`／`general_persona` 資料也納入候選（`is_owner`
    由呼叫端的 `router.py` 現場判斷後傳入，這裡不重複判斷，也不信任其他來源）。

    判斷「哪些資料跟主題相關」交給單次 LLM 呼叫（比照 ADR-6 的單次呼叫慣例），把候選資料編號列出、
    請模型回傳符合的編號；真正的刪除動作留到下一輪使用者確認後才執行，見
    `handle_clean_target_dialog_confirm_step()`。
    """
    candidates: list[dict] = []
    for row in db.select("conversation_logs", where="user_id = %s AND deleted_at IS NULL", params=(user_id,)):
        candidates.append({"kind": "log", "id": row["id"], "content": row["content"]})
    for row in db.select("knowledge_base", where="category = %s AND user_id = %s", params=("custom", user_id)):
        candidates.append({"kind": "kb", "id": row["id"], "content": row["content"]})
    if is_owner:
        for row in db.select("knowledge_base", where="category = %s", params=("general_family",)):
            candidates.append({"kind": "kb", "id": row["id"], "content": row["content"]})
        for row in db.select("knowledge_base", where="category = %s", params=("general_persona",)):
            candidates.append({"kind": "kb", "id": row["id"], "content": row["content"]})

    if not candidates:
        return "目前沒有任何對話紀錄或知識庫資料，不需要清除喔！"

    listing = "\n".join(f"{i}. {c['content'][:200]}" for i, c in enumerate(candidates, start=1))
    raw = llm_client.generate_text(_CLEAN_TARGET_MATCH_PROMPT.format(topic=topic, candidates=listing))
    matched_indexes = _parse_index_list(raw, len(candidates))

    if not matched_indexes:
        return f"目前沒有找到任何跟「{topic}」有關的對話紀錄或知識庫資料喔！"

    matched = [candidates[i - 1] for i in matched_indexes]
    log_ids = [c["id"] for c in matched if c["kind"] == "log"]
    kb_ids = [c["id"] for c in matched if c["kind"] == "kb"]

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_clean_target_dialog_confirm",
            "target_user_id": user_id,
            "topic": topic,
            "log_ids": log_ids,
            "kb_ids": kb_ids,
        },
    )
    return f"找到 {len(log_ids)} 則對話紀錄、{len(kb_ids)} 筆知識庫資料跟「{topic}」有關，確定要清除嗎？"


def handle_clean_target_dialog_confirm_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_clean_target_dialog_confirm` 狀態下使用者對主題式清除的確認回覆。

    任何非 `CONFIRM` 的判定結果一律視為取消，保守優先、不誤刪。

    2026-08-02（FR-16a）：判斷出 `CONFIRM` 後**不會馬上刪除**，轉入
    `pending_clean_target_dialog_final_confirm`，真正的軟刪除／硬刪除動作留給
    `handle_clean_target_dialog_final_confirm_step()` 執行。
    """
    state = state_store.get(telegram_user_id)
    topic = state["topic"]
    log_ids = state["log_ids"]
    kb_ids = state["kb_ids"]
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_CLEAN_TARGET_CONFIRM_PROMPT.format(topic=topic, reply=text)).strip()
    if decision != "CONFIRM":
        return "好的，先不清除，這些資料都還在喔！"

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_clean_target_dialog_final_confirm",
            "topic": topic,
            "log_ids": log_ids,
            "kb_ids": kb_ids,
        },
    )
    return _final_execute_prompt_reply(
        f"我理解你要清除跟「{topic}」有關的 {len(log_ids)} 則對話紀錄與 {len(kb_ids)} 筆知識庫資料，"
    )


def handle_clean_target_dialog_final_confirm_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
    via_voice: bool = False,
) -> str:
    """處理 `pending_clean_target_dialog_final_confirm` 狀態下的最終執行確認（2026-08-02，FR-16a）。

    對話紀錄比照 FR-10 軟刪除（`deleted_at`）；知識庫資料則直接硬刪除。語音輸入一律拒絕、不清除
    狀態；打字但沒有逐字輸入 `_FINAL_EXECUTE_KEYWORD` 一律視為取消。
    """
    if via_voice:
        return _voice_blocked_final_confirm_reply()

    state = state_store.get(telegram_user_id)
    topic = state["topic"]
    log_ids = state["log_ids"]
    kb_ids = state["kb_ids"]
    state_store.clear(telegram_user_id)

    if text.strip() != _FINAL_EXECUTE_KEYWORD:
        return "好的，先不清除，這些資料都還在喔！"

    now = datetime.now(timezone.utc)
    for log_id in log_ids:
        db.update("conversation_logs", {"deleted_at": now}, where="id = %s", params=(log_id,))
    for kb_id in kb_ids:
        db.delete("knowledge_base", where="id = %s", params=(kb_id,))

    return f"已經幫你清除跟「{topic}」有關的 {len(log_ids)} 則對話紀錄與 {len(kb_ids)} 筆知識庫資料囉！"


def _parse_index_list(raw: str, max_index: int) -> list[int]:
    """解析 `_CLEAN_TARGET_MATCH_PROMPT` 回傳的編號清單（逗號分隔，或 NONE）。"""
    cleaned = raw.strip()
    if cleaned.upper() == "NONE":
        return []
    result = []
    for token in cleaned.replace("，", ",").split(","):
        token = token.strip()
        if token.isdigit():
            n = int(token)
            if 1 <= n <= max_index:
                result.append(n)
    return result


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


# ---------------------------------------------------------------------------
# 待辦事項（2026-08-02，Step 1.7，見 robinson SPEC.md FR-31、FR-31a、FR-32、FR-56e）
#
# 新增流程分三輪反問（比照 FR-56e 情境範例）：chat.py 偵測到自然語言描述先問「要不要記錄」
# （pending_todo_confirm）→ 確定後問「什麼時候」（pending_todo_time，時間還講不清楚時會停留在
# 原地繼續反問，不會硬存一個猜錯的時間）→ 問「要不要提前 30 分鐘提醒」（pending_todo_reminder），
# 使用者這一輪回覆後才真正呼叫 todo.create_todo() 寫入，全程沒有 FR-16a 的「逐字打字確認執行」
# 關卡——新增待辦屬於低風險、可回頭用查詢清單流程取消/完成修正的操作，跟刪除紀錄／寫入知識庫的
# 風險層級不同，故不比照那三個 flow 額外加上最終確認關卡。
#
# 查詢＋標記完成/取消走另一條路：「我的待辦事項」／`/my_todos` 觸發 start_todo_list()，
# 選定編號後（pending_todo_list_action）反問要標記完成還是取消，由 LLM 判斷使用者這句話的意思
# （pending_todo_action_confirm），比照全專案既有的 CONFIRM/CANCEL 單次呼叫慣例。
# ---------------------------------------------------------------------------

_TODO_INTENT_CONFIRM_PROMPT = (
    "使用者剛被 Robinson 反問「要幫你紀錄到待辦事項嗎？」，這是使用者這一則的回覆：「{text}」。\n"
    "請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 確定要記錄 → CONFIRM\n"
    "(2) 不要記錄、想取消、或其實在問別的事 → CANCEL"
)

_TODO_TIME_PARSE_PROMPT = (
    "使用者想要記錄一筆待辦事項，原始描述是：「{original_text}」，Robinson 反問了確切時間，"
    "這是使用者這一則的回覆：「{time_reply}」。\n"
    "【現在的日期（台灣時區，計算相對日期時間一律以此為準）】\n{current_date_text}\n\n"
    "請判斷使用者是否已經講清楚明確的日期與時間，並嚴格照下面格式輸出，每個欄位各自一行，"
    "不要輸出其他任何文字：\n"
    "STATUS: CLEAR 或 UNCLEAR（這則回覆完全沒有講到具體時間、或還是很模糊、無法換算出確切日期"
    "時間時填 UNCLEAR）\n"
    "CONTENT: 待辦事項內容摘要，精簡具體，不需要包含時間（STATUS 為 UNCLEAR 時可省略）\n"
    "DUE_AT: 換算後的完整日期時間，格式一律為 YYYY-MM-DD HH:MM（24 小時制，STATUS 為 UNCLEAR 時"
    "可省略）"
)

_TODO_REMINDER_CONFIRM_PROMPT = (
    "Robinson 剛詢問使用者「需要在前 30 分鐘時提醒你嗎？」，這是使用者這一則的回覆：「{text}」。\n"
    "請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 需要提醒 → CONFIRM\n"
    "(2) 不需要提醒 → CANCEL"
)

_TODO_ACTION_CLASSIFY_PROMPT = (
    "使用者剛被 Robinson 反問要把待辦事項「{content}」標記為完成還是取消，這是使用者這一則的回覆："
    "「{text}」。\n"
    "請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 標記為已完成 → COMPLETE\n"
    "(2) 標記為取消 → CANCEL\n"
    "(3) 都不是、看不懂、或其實在問別的事 → OTHER"
)

_TODO_TIME_UNCLEAR_REPLY = "不好意思，我還是不太確定時間，可以再講清楚一點嗎？（例如：明天下午三點）"


def _current_date_text() -> str:
    """跟 chat.py 的同名私有函式邏輯一致，但待辦時間解析發生在 commands.py，避免跨模組互相
    依賴對方的私有函式，這裡獨立寫一份最簡版本（只需要日期，不需要星期幾）。"""
    now = datetime.now(_TAIWAN_TZ)
    return f"{now.year}年{now.month}月{now.day}日"


def handle_todo_confirm_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_todo_confirm` 狀態下使用者對「要幫你紀錄到待辦事項嗎？」的回覆。"""
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    original_text = state["original_text"]
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_TODO_INTENT_CONFIRM_PROMPT.format(text=text)).strip()
    if decision != "CONFIRM":
        return "好的，這次就不記錄囉！"

    state_store.set(
        telegram_user_id,
        {"flow": "pending_todo_time", "target_user_id": target_user_id, "original_text": original_text},
    )
    return "好的，請問是什麼時候呢？"


def handle_todo_time_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_todo_time` 狀態下使用者提供的時間描述（FR-31、FR-56e 情境範例）。

    使用者可能一次講清楚（例如「三點」），也可能還是模糊，這種情況停留在原本的狀態繼續反問，
    不強迫往下一步走，避免存入一個猜錯的時間。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    original_text = state["original_text"]

    parsed = _parse_key_value_block(
        llm_client.generate_text(
            _TODO_TIME_PARSE_PROMPT.format(
                original_text=original_text, time_reply=text, current_date_text=_current_date_text()
            )
        )
    )

    if parsed.get("STATUS") != "CLEAR":
        return _TODO_TIME_UNCLEAR_REPLY

    try:
        # 下一行刻意先解析成不帶時區的 datetime，緊接著用 .replace(tzinfo=...) 補上台灣時區。
        due_at_naive = datetime.strptime(parsed.get("DUE_AT", ""), "%Y-%m-%d %H:%M")  # noqa: DTZ007
    except ValueError:
        return _TODO_TIME_UNCLEAR_REPLY
    due_at = due_at_naive.replace(tzinfo=_TAIWAN_TZ)
    content = parsed.get("CONTENT") or original_text

    state_store.set(
        telegram_user_id,
        {"flow": "pending_todo_reminder", "target_user_id": target_user_id, "content": content, "due_at": due_at},
    )
    return (
        f"已收到 {due_at.year}/{due_at.month:02d}/{due_at.day:02d} {due_at.hour:02d}:{due_at.minute:02d}，"
        "到時候當天早上 8 點會主動提醒你一次，你也可以隨時查詢待辦事項清單，"
        "需要在前 30 分鐘時再提醒你一次嗎？"
    )


def handle_todo_reminder_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_todo_reminder` 狀態下使用者對「需要在前 30 分鐘時提醒你嗎？」的回覆，
    確定後才真正寫入 todos（FR-31、FR-32）。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    content = state["content"]
    due_at = state["due_at"]
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_TODO_REMINDER_CONFIRM_PROMPT.format(text=text)).strip()
    remind_before_30min = decision == "CONFIRM"

    todo_module.create_todo(db, target_user_id, content, due_at, remind_before_30min)
    return "好的，已經幫你記錄好了！"


def start_todo_list(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    user_id: int,
) -> str:
    """「我的待辦事項」／`/my_todos`：列出目前待處理清單，並進入可標記完成/取消的模式（FR-32）。"""
    pending_todos = todo_module.list_pending_todos(db, user_id)
    listing = todo_module.format_todo_list(pending_todos)
    if not pending_todos:
        return listing

    state_store.set(
        telegram_user_id,
        {"flow": "pending_todo_list_action", "target_user_id": user_id, "todo_ids": [t["id"] for t in pending_todos]},
    )
    return f"{listing}\n\n如果要標記某一筆為完成或取消，請輸入編號；不需要的話輸入「結束」。"


def handle_todo_list_action_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_todo_list_action` 狀態下使用者輸入的編號，選定要標記完成/取消的那一筆。"""
    state = state_store.get(telegram_user_id)
    if text in _EXIT_PHRASES:
        state_store.clear(telegram_user_id)
        return "好的，已結束待辦事項查詢模式！"

    todo_ids = state["todo_ids"]
    if not text.isdigit() or not (1 <= int(text) <= len(todo_ids)):
        return f"請輸入 1～{len(todo_ids)} 之間的編號，或輸入「結束」離開喔！"

    todo_id = todo_ids[int(text) - 1]
    row = db.select("todos", where="id = %s", params=(todo_id,), fetch_one=True)
    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_todo_action_confirm",
            "target_user_id": state["target_user_id"],
            "todo_id": todo_id,
            "content": row["content"],
        },
    )
    return f"要把「{row['content']}」標記為完成還是取消呢？"


def handle_todo_action_confirm_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_todo_action_confirm` 狀態下使用者對完成/取消的回覆（FR-31a）。"""
    state = state_store.get(telegram_user_id)
    todo_id = state["todo_id"]
    content = state["content"]
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_TODO_ACTION_CLASSIFY_PROMPT.format(content=content, text=text)).strip()
    if decision not in ("COMPLETE", "CANCEL"):
        return "不好意思，我不太確定你的意思，這筆待辦維持原狀，你可以再查詢一次待辦事項清單重新標記喔！"

    new_status = "completed" if decision == "COMPLETE" else "cancelled"
    todo_module.mark_status(db, todo_id, new_status)
    label = "完成" if new_status == "completed" else "取消"
    return f"好的，已經把「{content}」標記為{label}囉！"


# ---------------------------------------------------------------------------
# 心情小記（2026-08-02，Step 1.8，見 robinson SPEC.md FR-49、FR-50、FR-56h）
#
# 流程分三輪（比照 FR-56h 情境範例）：觸發後先問心情分類（pending_mood_category，固定 6 選一，
# 純字串比對不需要 LLM）→ 問日記內容（pending_mood_content）→ 記錄完成後主動問 FR-50 個人成就
# 三選一提示（pending_mood_achievement，使用者可用既有的 _EXIT_PHRASES 跳過，不強迫回答）。
# 全程不需要呼叫 LLM（跟 Step 1.7 待辦事項需要解析模糊時間不同），但日記內容／個人成就都是自由
# 文字、可能含個資，依 2026-08-02 與 Robin 確認的範圍決策，寫入 `mood_journals` 前一律先過
# `privacy.mask_text()`，跟一般聊天／圖片說明文字／語音轉文字三個既有入口的防線一致。
# ---------------------------------------------------------------------------


def start_mood_journal(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我想做心情筆記」／`/mood_journal`：開始心情小記流程，先問心情分類（FR-49、FR-56h）。"""
    state_store.set(telegram_user_id, {"flow": "pending_mood_category", "target_user_id": user_id})
    return mood.format_category_prompt()


def handle_mood_category_step(
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_mood_category` 狀態下使用者選擇的心情分類（接受編號或直接輸入分類名稱）。"""
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]

    category = mood.resolve_category(text)
    if category is None:
        return "不好意思，我沒看懂，麻煩從下面選一個喔：\n\n" + mood.format_category_prompt()

    state_store.set(
        telegram_user_id, {"flow": "pending_mood_content", "target_user_id": target_user_id, "mood_category": category}
    )
    return "給我完整的日記內容："


def handle_mood_content_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
    privacy_llm_client=None,
) -> str:
    """處理 `pending_mood_content` 狀態下使用者提供的日記內容，寫入後接著問 FR-50 個人成就。

    `privacy_llm_client`（見 docs/specs/privacy-masking/SPEC.md FR-4）：日記內容可能含個資，
    寫入 `mood_journals` 前一律先過 `privacy.mask_text()`；`None` 時優雅降級成只跑免費的 Regex 層。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    mood_category = state["mood_category"]

    masked_content, pii_detected = privacy.mask_text(text, privacy_llm_client)
    journal_id = mood.create_mood_journal(db, target_user_id, mood_category, masked_content)

    state_store.set(
        telegram_user_id,
        {"flow": "pending_mood_achievement", "target_user_id": target_user_id, "journal_id": journal_id},
    )
    reply = (
        "好的，已經紀錄了！要不要順便回顧一下今天：完成了什麼一句話總結／挑一件有感覺的事／"
        "寫下啟發或下次想改變的地方（選一項就好，不想回答也可以輸入「結束」跳過）："
    )
    if pii_detected:
        reply += _PII_DETECTED_REMINDER
    return reply


def handle_mood_achievement_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
    privacy_llm_client=None,
) -> str:
    """處理 `pending_mood_achievement` 狀態下使用者對 FR-50 個人成就提示的回覆（可選擇跳過）。

    `privacy_llm_client`：理由同 `handle_mood_content_step()`，個人成就一樣是自由文字，可能含個資。
    """
    state = state_store.get(telegram_user_id)
    journal_id = state["journal_id"]
    state_store.clear(telegram_user_id)

    if text in _EXIT_PHRASES:
        return "好的，那先這樣吧！"

    masked_note, pii_detected = privacy.mask_text(text, privacy_llm_client)
    mood.set_achievement_note(db, journal_id, masked_note)

    reply = "已經幫你記錄好了！"
    if pii_detected:
        reply += _PII_DETECTED_REMINDER
    return reply


# ---------------------------------------------------------------------------
# 客訴收集（2026-08-02，Step 1.9，見 robinson SPEC.md FR-60～FR-63）
#
# 流程分兩輪：觸發「我要客訴你」／`/complaint` 固定提問（不經過 LLM，FR-60）→ 下一則訊息視為
# 客訴內容，寫入 `complaints`（FR-61）後立即呼叫 Gemini 分析、私訊給 Robin（FR-62，刻意的隱私
# 例外——只有 FR-10/FR-11「Robin 平常看不到家人個別對話」這條規則被排除，客訴內容本身仍套用
# FR-13 個資遮蔽，兩者是不同層面的隱私考量，見 2026-08-02 與 Robin 確認的範圍決策）。分析報告
# 只私訊 Robin，不回傳給提出客訴的使用者本人；FR-63 的人工決策與後續討論純粹是 Robin 自己的
# 產品判斷，不涉及程式碼，不需要額外實作。
# ---------------------------------------------------------------------------

_COMPLAINT_ASK_TEXT = "請問你覺得哪個地方需要改進呢？"

_COMPLAINT_NOTIFY_TEMPLATE = (
    "📝 收到一則客訴/意見回饋\n"
    "使用者：{role}（telegram_user_id={telegram_user_id}）\n"
    "原始內容：{content}\n\n"
    "AI 分析：\n{analysis}"
)


def start_complaint(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我要客訴你」／`/complaint`：固定提問，不經過 LLM 生成（FR-60）。任何身分皆可觸發。"""
    state_store.set(telegram_user_id, {"flow": "pending_complaint_content", "target_user_id": user_id})
    return _COMPLAINT_ASK_TEXT


def handle_complaint_content_step(
    db: CloudSQLClient,
    llm_client,
    telegram_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
    privacy_llm_client=None,
) -> str:
    """處理 `pending_complaint_content` 狀態下使用者回覆的客訴內容：寫入、分析、私訊 Robin
    （FR-61、FR-62）。

    客訴內容一定會先寫入成功（FR-61 是硬性要求），分析＋私訊這段包一層 try/except——Gemini
    額度用盡或 Telegram 傳送失敗都不該讓「客訴已經被記錄下來」這個結果打折扣，失敗時只記錄
    log，使用者仍會收到已收到回饋的確認訊息。找不到 Robin 的 `users` 記錄（理論上不該發生，
    Robin 只要互動過一次就會有記錄，防禦性處理）時，同樣只是跳過私訊這一步。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    state_store.clear(telegram_user_id)

    masked_content, pii_detected = privacy.mask_text(text, privacy_llm_client)
    complaint_module.create_complaint(db, target_user_id, masked_content)

    try:
        robin = db.select("users", where="is_owner = %s", params=(True,), fetch_one=True)
        if robin is not None and robin.get("telegram_user_id") is not None:
            analysis = llm_client.generate_text(complaint_module.build_analysis_prompt(masked_content))
            complainant = db.select("users", where="id = %s", params=(target_user_id,), fetch_one=True)
            role = complainant["role"] if complainant is not None else "未知"
            telegram_client.send_text(
                chat_id=robin["telegram_user_id"],
                text=_COMPLAINT_NOTIFY_TEMPLATE.format(
                    role=role, telegram_user_id=telegram_user_id, content=masked_content, analysis=analysis
                ),
            )
    except Exception:
        _logger.exception("客訴分析或私訊 Robin 失敗（telegram_user_id=%s），客訴內容已成功記錄不受影響", telegram_user_id)

    reply = "已經收到你的意見了，謝謝你的回饋，我會把這件事轉達給 Robin 知道！"
    if pii_detected:
        reply += _PII_DETECTED_REMINDER
    return reply
