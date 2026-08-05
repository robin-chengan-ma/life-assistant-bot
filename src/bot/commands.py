"""內建指令與對話式設定流程（對應 docs/specs/platform-auth/SPEC.md FR-4～FR-6、
docs/specs/feature-toggles/SPEC.md FR-1～FR-2、docs/specs/chat-core/SPEC.md ADR-4、FR-10～FR-12、
docs/specs/robinson/SPEC.md FR-20、FR-31、FR-31a、FR-32、FR-41～FR-44、FR-41a、FR-42a、FR-45～FR-48、
FR-49、FR-50、FR-60～FR-63）。"""
import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from src.bot import auth, body, finance, knowledge, mood, notifications, privacy, templates, toggles
from src.bot import complaint as complaint_module
from src.bot import todo as todo_module
from src.bot.state import ConversationStateStore
from submodules.cloudsql.client import CloudSQLClient

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
    "這筆待辦事項可能是「單一時間點」（例如「明天下午三點」），也可能是「一段時間區間」（例如"
    "「這週五早上8點到下週一下午5點」「8/2到8/5」這種同時講出明確開始與結束的描述）；只有原始"
    "描述或這次回覆明確講出「開始」跟「結束」兩個時間點時，才算是區間，其餘一律當成單一時間點。\n"
    "請判斷使用者是否已經講清楚明確的日期與時間，並嚴格照下面格式輸出，每個欄位各自一行，"
    "不要輸出其他任何文字：\n"
    "STATUS: CLEAR 或 UNCLEAR。必須同時滿足下面兩個條件才能填 CLEAR，只要有一個條件不滿足就"
    "一律填 UNCLEAR，絕對不可以自己猜測、幫使用者補上「今天」或「上午/下午」；如果判斷是區間，"
    "以下兩個條件對「開始」跟「結束」兩個時間點都要分別成立才算 CLEAR，只要其中一個時間點不滿足"
    "就整體視為 UNCLEAR：\n"
    "  條件一（日期要明確）：『原始描述』或『這次回覆』裡面，至少有一項要明確提到是哪一天"
    "（例如「今天」「明天」「後天」「星期五」「8/5」等），如果完全沒提到任何日期線索，"
    "一律視為 UNCLEAR；\n"
    "  條件二（時段要明確）：時間本身不可以有上午/下午的歧義。小時數是 13～23（或 0 點/00:xx，"
    "代表午夜）的寫法本來就只可能是下午/晚上或凌晨，視為已經明確，不需要再額外加註時段字眼；"
    "但小時數是 1～12 的寫法（不論寫成「5:30」「05:30」還是「五點半」，只要小時數落在 1～12），"
    "一律必須額外明確講出時段（例如「上午/下午/中午/凌晨/早上/晚上」，例如「下午5:30」「下午"
    "五點半」）才算清楚；只要只給了「數字:數字」或「幾點幾分」卻沒有額外講時段，"
    "就一律視為 UNCLEAR，絕對不可以自己猜是上午還是下午。\n"
    "以上兩個條件都滿足時才填 CLEAR，換算並填寫下面欄位；否則兩個條件只要有一個不滿足，"
    "都填 UNCLEAR，並把 CONTENT／START_AT／DUE_AT 全部省略：\n"
    "CONTENT: 待辦事項內容摘要，精簡具體，不需要包含時間（STATUS 為 UNCLEAR 時可省略）\n"
    "START_AT: 只有判斷是「區間」時才需要填寫，換算後的區間開始時間，格式一律為 YYYY-MM-DD HH:MM"
    "（24 小時制）；如果是單一時間點，這一行整行不要輸出\n"
    "DUE_AT: 換算後的完整日期時間，格式一律為 YYYY-MM-DD HH:MM（24 小時制）。單一時間點時就是"
    "那個時間點本身；區間時則是區間的結束/截止時間（STATUS 為 UNCLEAR 時可省略）"
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


def _now() -> datetime:
    """回傳現在的台灣時間；獨立成函式方便測試用 monkeypatch 固定時間點
    （比照 chat.py 的同名私有函式，這裡獨立寫一份避免跨模組依賴對方的私有成員）。"""
    return datetime.now(_TAIWAN_TZ)


def _current_date_text() -> str:
    """跟 chat.py 的同名私有函式邏輯一致，但待辦時間解析發生在 commands.py，避免跨模組互相
    依賴對方的私有函式，這裡獨立寫一份最簡版本（只需要日期，不需要星期幾）。"""
    now = _now()
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


def _parse_todo_datetime(raw: str) -> datetime | None:
    """把 `_TODO_TIME_PARSE_PROMPT` 輸出的 `YYYY-MM-DD HH:MM` 字串換算成台灣時區 datetime；
    格式不對（或空字串）回傳 None，交由呼叫端視為 UNCLEAR 處理。"""
    if not raw:
        return None
    try:
        # 下一行刻意先解析成不帶時區的 datetime，緊接著用 .replace(tzinfo=...) 補上台灣時區。
        naive = datetime.strptime(raw, "%Y-%m-%d %H:%M")  # noqa: DTZ007
    except ValueError:
        return None
    return naive.replace(tzinfo=_TAIWAN_TZ)


def _format_ymd_hm(value: datetime) -> str:
    return f"{value.year}/{value.month:02d}/{value.day:02d} {value.hour:02d}:{value.minute:02d}"


def _digest_window_already_passed(day, now: datetime) -> bool:
    """判斷「某一天早上 8 點的每日摘要」是否已經不可能發生：那天已經是過去的日期、或那天就是
    今天但現在已經過了 8 點，都算已經錯過；今天還沒到 8 點、或那天是未來的日期，都還有機會。"""
    if day < now.date():
        return True
    return day == now.date() and now.hour >= 8


def _build_todo_time_confirmation_reply(start_at: datetime | None, due_at: datetime, now: datetime) -> str:
    """組合「已收到 XXX，到時候早上 8 點會提醒你...」這句確認訊息（FR-32、FR-31b）。

    2026-08-02 追加修正（Robin 回報：中午設定當天下午的待辦，卻還是講「當天早上 8 點會提醒」——
    這句是不可能發生的事，因為 8 點早就過了）：每日 08:00 摘要（見 todo.check_and_push_daily_digest）
    只在「現在剛好是 8 點那個小時」時才會觸發，所以只有『當天還沒到 8 點』或『日期是未來』這兩種
    情況，這句提醒才有機會真的發生；已經過了那天 8 點的話，就不能再講這句承諾了。

    2026-08-02 新增（FR-31b，區間待辦）：區間待辦的開始日、結束日各自是獨立的一次每日摘要機會
    （見 todo.py 的去重邏輯調整），所以要分別判斷兩天是否都還來得及，依結果給出不同措辭；
    開始日跟結束日是同一天（一日內區間）時，跟單一時間點待辦一樣只判斷一次。
    """
    if start_at is None:
        when_text = _format_ymd_hm(due_at)
        if _digest_window_already_passed(due_at.date(), now):
            digest_note = "由於現在已經過了今天的早上 8 點，這筆不會收到當天早上的提醒摘要囉，"
        else:
            digest_note = "到時候當天早上 8 點會主動提醒你一次，"
        return (
            f"已收到 {when_text}，{digest_note}你也可以隨時查詢待辦事項清單，"
            "需要在前 30 分鐘時再提醒你一次嗎？"
        )

    when_text = f"{_format_ymd_hm(start_at)} ～ {_format_ymd_hm(due_at)}"
    if start_at.date() == due_at.date():
        start_passed = due_passed = _digest_window_already_passed(start_at.date(), now)
    else:
        start_passed = _digest_window_already_passed(start_at.date(), now)
        due_passed = _digest_window_already_passed(due_at.date(), now)

    if not start_passed and not due_passed:
        digest_note = "到時候開始那天跟結束那天的早上 8 點都會主動提醒你一次，"
    elif start_passed and not due_passed:
        digest_note = "由於已經過了開始那天的早上 8 點，這筆只會在結束那天的早上 8 點提醒你一次，"
    else:
        # due_passed 為 True（不論 start_passed 是不是也 True）都保守視為兩邊都已經錯過：
        # 區間結構保證 start_at <= due_at，due 那天都過了，start 那天邏輯上不可能還沒過，
        # 這裡用 else 收斂成同一句，避免講出「還會被提醒」這種理論上不會發生、講了也沒意義的話。
        digest_note = "由於開始跟結束那天的早上 8 點都已經過了，這筆不會收到早上的提醒摘要囉，"

    return (
        f"已收到 {when_text}，{digest_note}你也可以隨時查詢待辦事項清單，"
        "需要在前 30 分鐘時再提醒你一次嗎？"
    )


def handle_todo_time_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_todo_time` 狀態下使用者提供的時間描述（FR-31、FR-31b、FR-56e 情境範例）。

    使用者可能一次講清楚（例如「三點」），也可能還是模糊，這種情況停留在原本的狀態繼續反問，
    不強迫往下一步走，避免存入一個猜錯的時間；也可能是一段時間區間（FR-31b），這種情況
    `_TODO_TIME_PARSE_PROMPT` 會多輸出一個 `START_AT` 欄位。
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

    due_at = _parse_todo_datetime(parsed.get("DUE_AT", ""))
    if due_at is None:
        return _TODO_TIME_UNCLEAR_REPLY

    # START_AT 是選填欄位（只有區間才會出現）：模型沒輸出、或輸出但格式錯誤，都當成單一時間點
    # 處理，不會因為這個選填欄位解析失敗就整輪打回 UNCLEAR（那樣反而會拒絕原本清楚的單一時間點）。
    start_at_raw = parsed.get("START_AT", "")
    start_at = _parse_todo_datetime(start_at_raw) if start_at_raw else None

    content = parsed.get("CONTENT") or original_text

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_todo_reminder",
            "target_user_id": target_user_id,
            "content": content,
            "due_at": due_at,
            "start_at": start_at,
        },
    )
    return _build_todo_time_confirmation_reply(start_at, due_at, _now())


def handle_todo_reminder_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_todo_reminder` 狀態下使用者對「需要在前 30 分鐘時提醒你嗎？」的回覆，
    確定後才真正寫入 todos（FR-31、FR-31b、FR-32）。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    content = state["content"]
    due_at = state["due_at"]
    start_at = state.get("start_at")
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_TODO_REMINDER_CONFIRM_PROMPT.format(text=text)).strip()
    remind_before_30min = decision == "CONFIRM"

    todo_module.create_todo(db, target_user_id, content, due_at, remind_before_30min, start_at=start_at)
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
#
# 2026-08-02 追加（見 robinson SPEC.md FR-49 補記/更新/刪除擴充）：Robin 提出「記帳、心情小記、
# 體重、飲食、運動習慣都要有補記、更新、刪除、新增的功能」，心情小記排在最優先實作，其餘三個
# Phase 2 才做的模組（記帳、體態管理）從一開始就會內建 CRUD，不需要另外補。
#
# 補記走一條新的三輪反問前置流程：pending_mood_backfill_date（先問是哪一天）→ 沿用既有的
# pending_mood_category → pending_mood_content → pending_mood_achievement，靠 state 裡的
# `entry_date`／`journal_id` 兩個欄位讓「一般新增」「補記新增」「編輯既有紀錄」共用同一組
# category/content/achievement 三步驟：`entry_date` 決定寫入哪一天、`journal_id` 是 None 時
# 代表新增（INSERT），非 None 時代表編輯（UPDATE，見 `handle_mood_action_choice_step`）。
#
# 更新/刪除則是「查詢清單 → 選編號 → 更新或刪除 → （更新時）走一次 category/content 流程／
# （刪除時）簡單一輪 CONFIRM/CANCEL」，整體結構比照 Step 1.7 待辦事項的
# `start_todo_list`／`handle_todo_list_action_step`／`handle_todo_action_confirm_step`。
# 刪除確認刻意採用簡單一輪 CONFIRM/CANCEL、不套用 FR-16a 的逐字打字最終確認（2026-08-02 與
# Robin 確認）：跟待辦事項完成/取消一樣屬於「錯了還能重新補記/修正」的中等風險操作，
# FR-16a 保留給 `/clean-all-dialog`／`/clean-target-dialog`／主動記知識這三個「一旦錯誤執行
# 就會大量、跨紀錄地不可逆遺失資料」的高風險流程。
# ---------------------------------------------------------------------------

_MOOD_BACKFILL_DATE_PARSE_PROMPT = (
    "使用者想要補記心情小記，Robinson 剛反問要補記哪一天，這是使用者這一則的回覆：「{date_reply}」。\n"
    "【現在的日期（台灣時區，計算相對日期時一律以此為準）】\n{current_date_text}\n\n"
    "請判斷使用者是否已經講清楚明確的日期，並嚴格照下面格式輸出，每個欄位各自一行，"
    "不要輸出其他任何文字：\n"
    "STATUS: CLEAR 或 UNCLEAR。使用者必須明確講出是哪一天（例如「昨天」「前天」「8/1」"
    "「2026-07-30」「上星期五」都算明確；只要含糊、沒有講清楚是哪一天，一律填 UNCLEAR，"
    "絕對不可以自己亂猜。\n"
    "DATE: 換算後的日期，格式一律為 YYYY-MM-DD（STATUS 為 UNCLEAR 時可省略）"
)

_MOOD_BACKFILL_DATE_UNCLEAR_REPLY = "不好意思，我還是不太確定是哪一天，可以再講清楚一點嗎？（例如：昨天、8/1）"

_MOOD_ACTION_CLASSIFY_PROMPT = (
    "使用者剛被 Robinson 反問要把選定的這筆心情紀錄「更新」還是「刪除」，這是使用者這一則的回覆："
    "「{text}」。\n"
    "請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 要更新內容 → UPDATE\n"
    "(2) 要刪除這筆 → DELETE\n"
    "(3) 都不是、看不懂、或其實在問別的事 → OTHER"
)

_MOOD_DELETE_CONFIRM_PROMPT = (
    "使用者剛被 Robinson 反問「確定要刪除這筆心情紀錄嗎？這個動作沒辦法復原喔！」，這是使用者這一則"
    "的回覆：「{text}」。\n"
    "請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 確定要刪除 → CONFIRM\n"
    "(2) 不要刪除、想取消、或其實在問別的事 → CANCEL"
)


def _parse_date_only(raw: str) -> date | None:
    """把 `_MOOD_BACKFILL_DATE_PARSE_PROMPT` 輸出的 `YYYY-MM-DD` 字串換算成 date；
    格式不對（或空字串）回傳 None，交由呼叫端視為 UNCLEAR 處理。"""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()  # noqa: DTZ007
    except ValueError:
        return None


def start_mood_journal(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我想做心情筆記」／`/mood_journal`：開始心情小記流程，先問心情分類（FR-49、FR-56h）。

    一般（非補記）新增：`entry_date` 固定是今天，`journal_id` 是 None（代表 INSERT）。
    """
    state_store.set(
        telegram_user_id,
        {"flow": "pending_mood_category", "target_user_id": user_id, "entry_date": _now().date(), "journal_id": None},
    )
    return mood.format_category_prompt()


def start_mood_backfill(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我要補記心情」／`/backfill_mood`：開始補記流程，先問要補記哪一天（FR-49 補記擴充）。"""
    state_store.set(telegram_user_id, {"flow": "pending_mood_backfill_date", "target_user_id": user_id})
    return "好的，要補記哪一天的心情呢？（例如：昨天、8/1）"


def handle_mood_backfill_date_step(
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_mood_backfill_date` 狀態下使用者提供的日期描述，講清楚後接著問心情分類。

    只接受今天或過去的日期——補記本來就是「補上之前忘記記的」，不能補記未來還沒發生的事。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]

    parsed = _parse_key_value_block(
        llm_client.generate_text(
            _MOOD_BACKFILL_DATE_PARSE_PROMPT.format(date_reply=text, current_date_text=_current_date_text())
        )
    )
    if parsed.get("STATUS") != "CLEAR":
        return _MOOD_BACKFILL_DATE_UNCLEAR_REPLY

    entry_date = _parse_date_only(parsed.get("DATE", ""))
    if entry_date is None:
        return _MOOD_BACKFILL_DATE_UNCLEAR_REPLY
    if entry_date > _now().date():
        return "不能補記還沒發生的未來日期喔，麻煩再講一次要補記哪一天！"

    state_store.set(
        telegram_user_id,
        {"flow": "pending_mood_category", "target_user_id": target_user_id, "entry_date": entry_date, "journal_id": None},
    )
    return mood.format_category_prompt()


def handle_mood_category_step(
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_mood_category` 狀態下使用者選擇的心情分類（接受編號或直接輸入分類名稱）。"""
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    entry_date = state["entry_date"]
    journal_id = state.get("journal_id")

    category = mood.resolve_category(text)
    if category is None:
        return "不好意思，我沒看懂，麻煩從下面選一個喔：\n\n" + mood.format_category_prompt()

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_mood_content",
            "target_user_id": target_user_id,
            "entry_date": entry_date,
            "journal_id": journal_id,
            "mood_category": category,
        },
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

    `journal_id` 是 None 時新增一筆（`entry_date` 可能是今天或補記的過去日期）；非 None 時代表
    這是編輯既有紀錄（見 `handle_mood_action_choice_step`），改為 UPDATE、沿用原本的 `entry_date`。

    `privacy_llm_client`（見 docs/specs/privacy-masking/SPEC.md FR-4）：日記內容可能含個資，
    寫入 `mood_journals` 前一律先過 `privacy.mask_text()`；`None` 時優雅降級成只跑免費的 Regex 層。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    entry_date = state["entry_date"]
    journal_id = state.get("journal_id")
    mood_category = state["mood_category"]

    masked_content, pii_detected = privacy.mask_text(text, privacy_llm_client)
    if journal_id is None:
        journal_id = mood.create_mood_journal(db, target_user_id, mood_category, masked_content, entry_date)
    else:
        mood.update_mood_journal(db, journal_id, mood_category, masked_content)

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


def start_mood_list(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    user_id: int,
) -> str:
    """「我的心情紀錄」／`/my_mood_journals`：列出最近的心情小記，並進入可更新/刪除的模式。"""
    journals = mood.list_mood_journals(db, user_id)
    listing = mood.format_mood_journal_list(journals)
    if not journals:
        return listing

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_mood_list_action",
            "target_user_id": user_id,
            "journal_ids": [item["id"] for item in journals],
        },
    )
    return f"{listing}\n\n如果要更新或刪除某一筆，請輸入編號；不需要的話輸入「結束」。"


def handle_mood_list_action_step(
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_mood_list_action` 狀態下使用者輸入的編號，選定要更新/刪除的那一筆。"""
    state = state_store.get(telegram_user_id)
    if text in _EXIT_PHRASES:
        state_store.clear(telegram_user_id)
        return "好的，已結束心情紀錄查詢模式！"

    journal_ids = state["journal_ids"]
    if not text.isdigit() or not (1 <= int(text) <= len(journal_ids)):
        return f"請輸入 1～{len(journal_ids)} 之間的編號，或輸入「結束」離開喔！"

    journal_id = journal_ids[int(text) - 1]
    state_store.set(
        telegram_user_id,
        {"flow": "pending_mood_action_choice", "target_user_id": state["target_user_id"], "journal_id": journal_id},
    )
    return "要更新這筆還是刪除呢？"


def handle_mood_action_choice_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_mood_action_choice` 狀態下使用者對「要更新這筆還是刪除呢？」的回覆。

    選更新時沿用原本記錄的 `entry_date`（找不到就 fallback 用 `created_at` 換算，理由同
    `mood._entry_date_of()`），重新走一次分類/內容兩輪反問，`journal_id` 帶著代表這是編輯而非新增。
    """
    state = state_store.get(telegram_user_id)
    journal_id = state["journal_id"]
    target_user_id = state["target_user_id"]

    decision = llm_client.generate_text(_MOOD_ACTION_CLASSIFY_PROMPT.format(text=text)).strip()
    if decision == "UPDATE":
        row = db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True)
        entry_date = row.get("entry_date") or row["created_at"].astimezone(_TAIWAN_TZ).date()
        state_store.set(
            telegram_user_id,
            {
                "flow": "pending_mood_category",
                "target_user_id": target_user_id,
                "entry_date": entry_date,
                "journal_id": journal_id,
            },
        )
        return "好的，那我們重新選一次心情分類：\n\n" + mood.format_category_prompt()
    if decision == "DELETE":
        state_store.set(
            telegram_user_id,
            {"flow": "pending_mood_delete_confirm", "target_user_id": target_user_id, "journal_id": journal_id},
        )
        return "確定要刪除這筆心情紀錄嗎？這個動作沒辦法復原喔！"

    state_store.clear(telegram_user_id)
    return "不好意思，我不太確定你的意思，這筆心情紀錄維持原狀，你可以再查詢一次心情紀錄清單重新選擇喔！"


def handle_mood_delete_confirm_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_mood_delete_confirm` 狀態下使用者對刪除確認的回覆（簡單一輪 CONFIRM/CANCEL，
    設計理由見本模組「心情小記」區塊開頭說明）。"""
    state = state_store.get(telegram_user_id)
    journal_id = state["journal_id"]
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_MOOD_DELETE_CONFIRM_PROMPT.format(text=text)).strip()
    if decision != "CONFIRM":
        return "好的，這筆心情紀錄保留，沒有刪除！"

    mood.delete_mood_journal(db, journal_id)
    return "好的，已經刪除這筆心情紀錄了！"


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


# ---------------------------------------------------------------------------
# 記帳（2026-08-04，Step 2.1，見 robinson SPEC.md FR-41～FR-44）
#
# 跟心情小記（Step 1.8）的補記/更新/刪除擴充同一套設計語言，但記帳從一開始就內建完整 CRUD
# （不像心情小記是事後才補上）：
# - 新增（一般）：pending_transaction_type → pending_transaction_category →
#   pending_transaction_amount → pending_transaction_note，`transaction_date` 固定是今天、
#   `transaction_id` 是 None（代表 INSERT）
# - 補記：多一個前置的 pending_transaction_backfill_date（先問哪一天，只接受今天或過去日期，
#   邏輯比照 `handle_mood_backfill_date_step`），講清楚後接進同一組 type/category/amount/note
# - 更新：查詢清單 pending_transaction_list_action 選一筆 → pending_transaction_action_choice
#   反問要更新還是刪除 → 選更新時沿用原本的 `transaction_date`、`transaction_id` 帶著代表這是
#   編輯，重新走一次 type/category/amount/note 四步（比心情小記的分類/內容兩步驟多，因為記帳
#   多了類型跟金額兩個欄位）
# - 刪除：pending_transaction_delete_confirm，簡單一輪 LLM CONFIRM/CANCEL（理由同心情小記：
#   中等風險、可事後補記修正，不套用 FR-16a 逐字打字最終確認）
#
# FR-41 設定預算、FR-43 門檻預警推播（`finance.check_and_push_budget_alerts()`，借用 `/healthz`
# 頻率，見 `main.py`）、FR-44 文字摘要查詢，三者都不需要 LLM；FR-42 的補記日期解析、更新/刪除
# 選擇、刪除確認才需要 LLM（跟待辦事項/心情小記一致，純固定選項的步驟不呼叫 LLM）。
#
# 2026-08-04 擴充（Robin 提出記帳模組使用回饋，見 robinson SPEC.md FR-41a/FR-42a）：
# - 設定預算改成多輪：pending_finance_budget_scope（全部月份／某幾個月）
#   → 選全部月份：若全局預設已有舊值 → pending_finance_budget_global_confirm 反問確認
#   → 選某幾個月：pending_finance_budget_months 問月份 → 若選定月份有舊覆蓋值 →
#     pending_finance_budget_override_confirm 反問確認 → pending_finance_budget_amount 問金額
#   確認步驟一樣是簡單一輪 LLM CONFIRM/CANCEL（風險等級同記帳刪除確認）。
# - FR-42a 每日 23:00 記帳提醒：`finance.check_and_push_finance_reminders()`，同樣借用 `/healthz`
#   頻率，不需要對話狀態機，也不需要 LLM。
# ---------------------------------------------------------------------------

_FINANCE_BACKFILL_DATE_PARSE_PROMPT = (
    "使用者想要補記帳，Robinson 剛反問要補記哪一天，這是使用者這一則的回覆：「{date_reply}」。\n"
    "【現在的日期（台灣時區，計算相對日期時一律以此為準）】\n{current_date_text}\n\n"
    "請判斷使用者是否已經講清楚明確的日期，並嚴格照下面格式輸出，每個欄位各自一行，"
    "不要輸出其他任何文字：\n"
    "STATUS: CLEAR 或 UNCLEAR。使用者必須明確講出是哪一天（例如「昨天」「前天」「8/1」"
    "「2026-07-30」「上星期五」都算明確；只要含糊、沒有講清楚是哪一天，一律填 UNCLEAR，"
    "絕對不可以自己亂猜。\n"
    "DATE: 換算後的日期，格式一律為 YYYY-MM-DD（STATUS 為 UNCLEAR 時可省略）"
)

_FINANCE_BACKFILL_DATE_UNCLEAR_REPLY = "不好意思，我還是不太確定是哪一天，可以再講清楚一點嗎？（例如：昨天、8/1）"

_TRANSACTION_ACTION_CLASSIFY_PROMPT = (
    "使用者剛被 Robinson 反問要把選定的這筆記帳紀錄「更新」還是「刪除」，這是使用者這一則的回覆："
    "「{text}」。\n"
    "請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 要更新內容 → UPDATE\n"
    "(2) 要刪除這筆 → DELETE\n"
    "(3) 都不是、看不懂、或其實在問別的事 → OTHER"
)

_TRANSACTION_DELETE_CONFIRM_PROMPT = (
    "使用者剛被 Robinson 反問「確定要刪除這筆記帳紀錄嗎？這個動作沒辦法復原喔！」，這是使用者這一則"
    "的回覆：「{text}」。\n"
    "請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 確定要刪除 → CONFIRM\n"
    "(2) 不要刪除、想取消、或其實在問別的事 → CANCEL"
)

# 2026-08-04 追加（記帳擴充，見 robinson SPEC.md FR-41a）：預算已有舊值時的覆蓋確認，簡單一輪
# LLM CONFIRM/CANCEL（風險等級同記帳刪除確認，理由同上）。
_FINANCE_BUDGET_CHANGE_CONFIRM_PROMPT = (
    "使用者剛被 Robinson 反問是否要把已經設定過的記帳預算改成新的金額，這是使用者這一則的回覆："
    "「{text}」。\n"
    "請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 確定要改 → CONFIRM\n"
    "(2) 不要改、想取消、或其實在問別的事 → CANCEL"
)


def _parse_amount(text: str) -> float | None:
    """把使用者輸入的金額文字換算成正數 float；接受「120」「120元」「NT$120」「1,200」等常見寫法，
    無法解析或非正數一律回傳 None，交由呼叫端反問。"""
    cleaned = text.strip()
    for token in ("NT$", "NTD", "$", "元", ","):
        cleaned = cleaned.replace(token, "")
    cleaned = cleaned.strip()
    try:
        amount = float(cleaned)
    except ValueError:
        return None
    return amount if amount > 0 else None


def start_finance_budget(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「設定記帳預算」／`/set_budget`：開始設定支出預算（FR-41／FR-41a）。

    2026-08-04 擴充（見 robinson SPEC.md FR-41a）：每次都先問套用範圍（全部月份 vs 只套用某幾個月），
    而不是直接問金額——理由是 Robin 提出某幾個月（報稅、包紅包）固定開銷較高，需要能單獨設定，
    又不想每次調整全局預設時被牽動。完整流程見本模組「記帳」區塊開頭的擴充說明。
    """
    state_store.set(telegram_user_id, {"flow": "pending_finance_budget_scope", "target_user_id": user_id})
    return finance.format_budget_scope_prompt()


def handle_finance_budget_scope_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_finance_budget_scope` 狀態下使用者選擇的套用範圍（FR-41a）。

    選「全部月份」：若全局預設已有舊值，先反問確認才能改；沒有舊值就直接問金額。
    選「只套用某幾個月」：接著問要套用哪幾個月。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]

    scope = finance.resolve_budget_scope(text)
    if scope is None:
        return "不好意思，我沒看懂，麻煩從下面選一個喔：\n\n" + finance.format_budget_scope_prompt()

    if scope == "months":
        state_store.set(telegram_user_id, {"flow": "pending_finance_budget_months", "target_user_id": target_user_id})
        return "好的，要套用在幾月呢？可以輸入多個，用逗號分隔（例如：8,9）："

    current = finance.get_monthly_budget(db, target_user_id)
    if current is not None:
        state_store.set(
            telegram_user_id,
            {"flow": "pending_finance_budget_global_confirm", "target_user_id": target_user_id},
        )
        return finance.format_budget_global_confirm_prompt(current)

    state_store.set(
        telegram_user_id,
        {"flow": "pending_finance_budget_amount", "target_user_id": target_user_id, "scope": "global"},
    )
    return "好的，請問每月支出預算上限是多少呢？（例如：15000）"


def handle_finance_budget_months_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_finance_budget_months` 狀態下使用者輸入的月份清單（FR-41a）。

    一律套用「今年」（今天所在的年份），這是本次的簡化假設，尚不支援跨年設定。若選定的月份中
    有已經設定過覆蓋值的，先組合成一則確認訊息列出舊值；沒有衝突就直接問金額。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]

    months = finance.parse_months(text)
    if months is None:
        return "不好意思，我沒看懂月份，可以用「8」或「8,9」這樣的方式告訴我嗎？（1~12）"

    year = _now().date().year
    conflicts = [
        (month, override)
        for month in months
        if (override := finance.get_budget_override(db, target_user_id, year, month)) is not None
    ]

    if conflicts:
        state_store.set(
            telegram_user_id,
            {
                "flow": "pending_finance_budget_override_confirm",
                "target_user_id": target_user_id,
                "months": months,
                "year": year,
            },
        )
        return finance.format_budget_override_confirm_prompt(conflicts)

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_finance_budget_amount",
            "target_user_id": target_user_id,
            "scope": "months",
            "months": months,
            "year": year,
        },
    )
    return "好的，請問要設定多少金額呢？（例如：15000）"


def handle_finance_budget_global_confirm_step(
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_finance_budget_global_confirm` 狀態下使用者對「要不要改全局預設預算」的回覆
    （簡單一輪 CONFIRM/CANCEL，理由見 `_FINANCE_BUDGET_CHANGE_CONFIRM_PROMPT`）。"""
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]

    decision = llm_client.generate_text(_FINANCE_BUDGET_CHANGE_CONFIRM_PROMPT.format(text=text)).strip()
    if decision != "CONFIRM":
        state_store.clear(telegram_user_id)
        return "好的，維持原本的預算不變！"

    state_store.set(
        telegram_user_id,
        {"flow": "pending_finance_budget_amount", "target_user_id": target_user_id, "scope": "global"},
    )
    return "好的，請問每月支出預算上限要改成多少呢？（例如：15000）"


def handle_finance_budget_override_confirm_step(
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_finance_budget_override_confirm` 狀態下使用者對「要不要改某幾個月的覆蓋預算」
    的回覆（簡單一輪 CONFIRM/CANCEL）。"""
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    months = state["months"]
    year = state["year"]

    decision = llm_client.generate_text(_FINANCE_BUDGET_CHANGE_CONFIRM_PROMPT.format(text=text)).strip()
    if decision != "CONFIRM":
        state_store.clear(telegram_user_id)
        return "好的，維持原本的預算不變！"

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_finance_budget_amount",
            "target_user_id": target_user_id,
            "scope": "months",
            "months": months,
            "year": year,
        },
    )
    return "好的，請問要改成多少金額呢？（例如：15000）"


def handle_finance_budget_amount_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_finance_budget_amount` 狀態下使用者提供的金額，依 `scope` 分別寫入全局預設
    （`finance.set_monthly_budget()`）或指定月份的覆蓋值（`finance.set_budget_override()`）。"""
    state = state_store.get(telegram_user_id)
    amount = _parse_amount(text)
    if amount is None:
        return "不好意思，我沒看懂金額，麻煩輸入一個數字喔（例如：15000）"

    target_user_id = state["target_user_id"]
    state_store.clear(telegram_user_id)

    if state["scope"] == "global":
        finance.set_monthly_budget(db, target_user_id, amount)
        return (
            f"好的，已經幫你把預設每月支出預算設定為 {amount:.0f} 元囉！之後每個月都會自動套用這個"
            "金額（除非你有針對某幾個月另外設定）。"
        )

    months = state["months"]
    year = state["year"]
    for month in months:
        finance.set_budget_override(db, target_user_id, year, month, amount)
    return f"好的，已經把 {finance.format_months_label(months)} 的支出預算設定為 {amount:.0f} 元囉！"


def start_finance_add(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我要記帳」／`/add_transaction`：開始記帳流程，先問交易類型（FR-42）。

    一般（非補記）新增：`transaction_date` 固定是今天，`transaction_id` 是 None（代表 INSERT）。
    """
    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_transaction_type",
            "target_user_id": user_id,
            "transaction_date": _now().date(),
            "transaction_id": None,
        },
    )
    return finance.format_type_prompt()


def start_finance_backfill(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我要補記帳」／`/backfill_transaction`：開始補記流程，先問要補記哪一天（FR-42）。"""
    state_store.set(telegram_user_id, {"flow": "pending_transaction_backfill_date", "target_user_id": user_id})
    return "好的，要補記哪一天的帳呢？（例如：昨天、8/1）"


def handle_transaction_backfill_date_step(
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_transaction_backfill_date` 狀態下使用者提供的日期描述，講清楚後接著問交易類型。

    只接受今天或過去的日期，理由同 `handle_mood_backfill_date_step()`。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]

    parsed = _parse_key_value_block(
        llm_client.generate_text(
            _FINANCE_BACKFILL_DATE_PARSE_PROMPT.format(date_reply=text, current_date_text=_current_date_text())
        )
    )
    if parsed.get("STATUS") != "CLEAR":
        return _FINANCE_BACKFILL_DATE_UNCLEAR_REPLY

    transaction_date = _parse_date_only(parsed.get("DATE", ""))
    if transaction_date is None:
        return _FINANCE_BACKFILL_DATE_UNCLEAR_REPLY
    if transaction_date > _now().date():
        return "不能補記還沒發生的未來日期喔，麻煩再講一次要補記哪一天！"

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_transaction_type",
            "target_user_id": target_user_id,
            "transaction_date": transaction_date,
            "transaction_id": None,
        },
    )
    return finance.format_type_prompt()


def handle_transaction_type_step(
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_transaction_type` 狀態下使用者選擇的交易類型（接受編號或「支出」／「收入」）。"""
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    transaction_date = state["transaction_date"]
    transaction_id = state.get("transaction_id")

    transaction_type = finance.resolve_type(text)
    if transaction_type is None:
        return "不好意思，我沒看懂，麻煩從下面選一個喔：\n\n" + finance.format_type_prompt()

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_transaction_category",
            "target_user_id": target_user_id,
            "transaction_date": transaction_date,
            "transaction_id": transaction_id,
            "transaction_type": transaction_type,
        },
    )
    return finance.format_category_prompt(transaction_type)


def handle_transaction_category_step(
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_transaction_category` 狀態下使用者選擇的分類（接受編號或直接輸入分類名稱）。"""
    state = state_store.get(telegram_user_id)
    transaction_type = state["transaction_type"]

    category = finance.resolve_category(transaction_type, text)
    if category is None:
        return "不好意思，我沒看懂，麻煩從下面選一個喔：\n\n" + finance.format_category_prompt(transaction_type)

    state_store.set(telegram_user_id, {**state, "flow": "pending_transaction_amount", "category": category})
    return "請問金額是多少呢？（例如：120）"


def handle_transaction_amount_step(
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_transaction_amount` 狀態下使用者提供的金額（FR-42）。"""
    state = state_store.get(telegram_user_id)
    amount = _parse_amount(text)
    if amount is None:
        return "不好意思，我沒看懂金額，麻煩輸入一個正數喔（例如：120）"

    state_store.set(telegram_user_id, {**state, "flow": "pending_transaction_note", "amount": amount})
    return "要加備註嗎？不需要的話輸入「沒有」或「結束」："


def handle_transaction_note_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
    privacy_llm_client=None,
) -> str:
    """處理 `pending_transaction_note` 狀態下使用者提供的備註（可選擇跳過），寫入後結束流程。

    `transaction_id` 是 None 時新增一筆；非 None 時代表這是編輯既有紀錄
    （見 `handle_transaction_action_choice_step`），改為 UPDATE、沿用原本的 `transaction_date`。

    `privacy_llm_client`（見 docs/specs/privacy-masking/SPEC.md FR-4）：備註可能含個資，寫入
    `transactions` 前一律先過 `privacy.mask_text()`；`None` 時優雅降級成只跑免費的 Regex 層。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    transaction_date = state["transaction_date"]
    transaction_id = state.get("transaction_id")
    transaction_type = state["transaction_type"]
    category = state["category"]
    amount = state["amount"]
    state_store.clear(telegram_user_id)

    pii_detected = False
    if text in _EXIT_PHRASES or text in ("沒有", "不用"):
        note = None
    else:
        note, pii_detected = privacy.mask_text(text, privacy_llm_client)

    if transaction_id is None:
        finance.create_transaction(db, target_user_id, transaction_type, category, amount, note, transaction_date)
    else:
        finance.update_transaction(db, transaction_id, transaction_type, category, amount, note)

    reply = "已經幫你記錄好了！"
    if pii_detected:
        reply += _PII_DETECTED_REMINDER
    return reply


def start_finance_list(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    user_id: int,
) -> str:
    """「我的記帳紀錄」／`/my_transactions`：列出最近的記帳紀錄，並進入可更新/刪除的模式。"""
    transactions = finance.list_transactions(db, user_id)
    listing = finance.format_transaction_list(transactions)
    if not transactions:
        return listing

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_transaction_list_action",
            "target_user_id": user_id,
            "transaction_ids": [item["id"] for item in transactions],
        },
    )
    return f"{listing}\n\n如果要更新或刪除某一筆，請輸入編號；不需要的話輸入「結束」。"


def handle_transaction_list_action_step(
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_transaction_list_action` 狀態下使用者輸入的編號，選定要更新/刪除的那一筆。"""
    state = state_store.get(telegram_user_id)
    if text in _EXIT_PHRASES:
        state_store.clear(telegram_user_id)
        return "好的，已結束記帳紀錄查詢模式！"

    transaction_ids = state["transaction_ids"]
    if not text.isdigit() or not (1 <= int(text) <= len(transaction_ids)):
        return f"請輸入 1～{len(transaction_ids)} 之間的編號，或輸入「結束」離開喔！"

    transaction_id = transaction_ids[int(text) - 1]
    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_transaction_action_choice",
            "target_user_id": state["target_user_id"],
            "transaction_id": transaction_id,
        },
    )
    return "要更新這筆還是刪除呢？"


def handle_transaction_action_choice_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_transaction_action_choice` 狀態下使用者對「要更新這筆還是刪除呢？」的回覆。

    選更新時沿用原本記錄的 `transaction_date`，重新走一次類型/分類/金額/備註四輪反問，
    `transaction_id` 帶著代表這是編輯而非新增。
    """
    state = state_store.get(telegram_user_id)
    transaction_id = state["transaction_id"]
    target_user_id = state["target_user_id"]

    decision = llm_client.generate_text(_TRANSACTION_ACTION_CLASSIFY_PROMPT.format(text=text)).strip()
    if decision == "UPDATE":
        row = db.select("transactions", where="id = %s", params=(transaction_id,), fetch_one=True)
        state_store.set(
            telegram_user_id,
            {
                "flow": "pending_transaction_type",
                "target_user_id": target_user_id,
                "transaction_date": row["transaction_date"],
                "transaction_id": transaction_id,
            },
        )
        return "好的，那我們重新選一次交易類型：\n\n" + finance.format_type_prompt()
    if decision == "DELETE":
        state_store.set(
            telegram_user_id,
            {"flow": "pending_transaction_delete_confirm", "target_user_id": target_user_id, "transaction_id": transaction_id},
        )
        return "確定要刪除這筆記帳紀錄嗎？這個動作沒辦法復原喔！"

    state_store.clear(telegram_user_id)
    return "不好意思，我不太確定你的意思，這筆記帳紀錄維持原狀，你可以再查詢一次記帳紀錄清單重新選擇喔！"


def handle_transaction_delete_confirm_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_transaction_delete_confirm` 狀態下使用者對刪除確認的回覆（簡單一輪
    CONFIRM/CANCEL，設計理由見本模組「記帳」區塊開頭說明）。"""
    state = state_store.get(telegram_user_id)
    transaction_id = state["transaction_id"]
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_TRANSACTION_DELETE_CONFIRM_PROMPT.format(text=text)).strip()
    if decision != "CONFIRM":
        return "好的，這筆記帳紀錄保留，沒有刪除！"

    finance.delete_transaction(db, transaction_id)
    return "好的，已經刪除這筆記帳紀錄了！"


def handle_finance_summary(db: CloudSQLClient, user_id: int) -> str:
    """「我的記帳摘要」／`/my_finance_summary`：查詢當月記帳文字摘要（FR-44），不經過對話狀態機。"""
    return finance.format_monthly_summary(db, user_id, _now().date())


# ---------------------------------------------------------------------------
# 體態管理（2026-08-04，Step 2.2，見 robinson SPEC.md FR-45～FR-48）
#
# 三個子功能（身高體重／運動／飲食）+ 共用一張目標表，設計語言比照記帳/心情小記：
# - 身高：`/set_height`，單輪（不合理範圍時原地重問，不是 LLM 分流，理由是純數字範圍檢查不需要
#   語意判斷）。
# - 體重：`/log_weight`（單輪，記錄後即時附上 BMI 說明與體重目標達成判斷）／`/backfill_weight`
#   （多一個前置問日期）／`/my_weight_logs`（查詢→更新/刪除，更新時重新走一次體重輸入）。
# - 運動：`/log_exercise`（活動→時長→心率三輪，記錄後呼叫 LLM 估算卡路里）／`/backfill_exercise`／
#   `/my_exercise_logs`。
# - 飲食：`/log_diet`（先選飲食/飲水→飲食問內容並呼叫 LLM 拆算營養、飲水問毫升數）／
#   `/backfill_diet`／`/my_diet_logs`。
# - 目標：`/set_body_goal`（先選類型→依類型分別問目標值/敘述→問期限→存檔）／`/my_body_goals`
#   （查詢→取消，這版不支援修改目標內容，要調整就取消重設）。
#
# 更新/刪除的「選一筆→要更新還是刪除→確認」三段式，跟記帳的
# pending_transaction_list_action／pending_transaction_action_choice／
# pending_transaction_delete_confirm 完全同一套設計。
# ---------------------------------------------------------------------------

_HEIGHT_UNREASONABLE_REPLY = "這個身高數字好像不太合理喔（成人身高大概在 140~220 公分之間），麻煩再確認一次告訴我："
_WEIGHT_UNREASONABLE_REPLY = "這個體重數字好像不太合理喔（成人體重大概要有 40 公斤以上），麻煩再確認一次告訴我："

_WEIGHT_ACTION_CLASSIFY_PROMPT = (
    "使用者剛被 Robinson 反問要把選定的這筆體重紀錄「更新」還是「刪除」，這是使用者這一則的回覆："
    "「{text}」。\n請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 要更新內容 → UPDATE\n(2) 要刪除這筆 → DELETE\n(3) 都不是、看不懂、或其實在問別的事 → OTHER"
)
_WEIGHT_DELETE_CONFIRM_PROMPT = (
    "使用者剛被 Robinson 反問「確定要刪除這筆體重紀錄嗎？這個動作沒辦法復原喔！」，這是使用者這一則"
    "的回覆：「{text}」。\n請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 確定要刪除 → CONFIRM\n(2) 不要刪除、想取消、或其實在問別的事 → CANCEL"
)
_EXERCISE_ACTION_CLASSIFY_PROMPT = _WEIGHT_ACTION_CLASSIFY_PROMPT.replace("體重紀錄", "運動紀錄")
_EXERCISE_DELETE_CONFIRM_PROMPT = _WEIGHT_DELETE_CONFIRM_PROMPT.replace("體重紀錄", "運動紀錄")
_DIET_ACTION_CLASSIFY_PROMPT = _WEIGHT_ACTION_CLASSIFY_PROMPT.replace("體重紀錄", "飲食紀錄")
_DIET_DELETE_CONFIRM_PROMPT = _WEIGHT_DELETE_CONFIRM_PROMPT.replace("體重紀錄", "飲食紀錄")
_GOAL_CANCEL_CONFIRM_PROMPT = (
    "使用者剛被 Robinson 反問「確定要取消這個體態目標嗎？」，這是使用者這一則的回覆：「{text}」。\n"
    "請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 確定要取消 → CONFIRM\n(2) 不要取消、想保留、或其實在問別的事 → CANCEL"
)

_BACKFILL_DATE_PARSE_PROMPT = (
    "使用者想要補記{feature_label}，Robinson 剛反問要補記哪一天，這是使用者這一則的回覆：「{date_reply}」。\n"
    "【現在的日期（台灣時區，計算相對日期時一律以此為準）】\n{current_date_text}\n\n"
    "請判斷使用者是否已經講清楚明確的日期，並嚴格照下面格式輸出，每個欄位各自一行，"
    "不要輸出其他任何文字：\n"
    "STATUS: CLEAR 或 UNCLEAR。使用者必須明確講出是哪一天（例如「昨天」「前天」「8/1」"
    "「2026-07-30」「上星期五」都算明確；只要含糊、沒有講清楚是哪一天，一律填 UNCLEAR，"
    "絕對不可以自己亂猜。\n"
    "DATE: 換算後的日期，格式一律為 YYYY-MM-DD（STATUS 為 UNCLEAR 時可省略）"
)
_BACKFILL_DATE_UNCLEAR_REPLY = "不好意思，我還是不太確定是哪一天，可以再講清楚一點嗎？（例如：昨天、8/1）"

_GOAL_DEADLINE_PARSE_PROMPT = (
    "使用者正在設定體態管理目標，Robinson 剛反問「有預計完成時間嗎？（例如：三個月內完成）」，"
    "這是使用者這一則的回覆：「{deadline_reply}」。\n"
    "【現在的日期（台灣時區，計算相對日期時一律以此為準）】\n{current_date_text}\n\n"
    "請判斷使用者的意思，並嚴格照下面格式輸出，每個欄位各自一行，不要輸出其他任何文字：\n"
    "STATUS: HAS_DEADLINE、NO_DEADLINE 或 UNCLEAR。使用者講出明確期限（例如「三個月內」"
    "「三個月後」「今年年底」「12/31」都算明確，請自行依現在日期換算）填 HAS_DEADLINE；"
    "使用者明確表示不需要期限（例如「沒有」「不用」）填 NO_DEADLINE；含糊看不出來則填 UNCLEAR。\n"
    "DATE: 換算後的日期，格式一律為 YYYY-MM-DD（STATUS 不是 HAS_DEADLINE 時可省略）"
)
_GOAL_DEADLINE_UNCLEAR_REPLY = "不好意思，我還是不太確定期限，可以再講清楚一點嗎？（例如：三個月內、沒有）"


def _parse_positive_int(text: str) -> int | None:
    """把使用者輸入的文字換算成正整數；接受純數字或帶單位（分鐘/下/毫升）的寫法，無法解析或非正數
    一律回傳 None，交由呼叫端反問。"""
    cleaned = text.strip()
    for token in ("分鐘", "下/分鐘", "下", "毫升", "ml", "ML", "cc", "CC"):
        cleaned = cleaned.replace(token, "")
    cleaned = cleaned.strip()
    if not cleaned.isdigit():
        return None
    value = int(cleaned)
    return value if value > 0 else None


def _parse_positive_float(text: str) -> float | None:
    """把使用者輸入的文字換算成正數 float；接受純數字或帶單位（公分/公斤/kg/cm）的寫法。"""
    cleaned = text.strip()
    for token in ("公分", "公斤", "kg", "KG", "cm", "CM"):
        cleaned = cleaned.replace(token, "")
    cleaned = cleaned.strip()
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if value > 0 else None


# --- 身高 ---


def start_set_height(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「設定身高」／`/set_height`：開始設定身高（FR-46）。"""
    state_store.set(telegram_user_id, {"flow": "pending_height_value", "target_user_id": user_id})
    return "好的，請告訴我你的身高（公分）："


def handle_height_value_step(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_height_value` 狀態下使用者提供的身高數值；不合理範圍原地反問，不清除狀態。"""
    state = state_store.get(telegram_user_id)
    height = _parse_positive_float(text)
    if height is None:
        return "不好意思，我沒看懂，麻煩輸入一個數字喔（例如：173）"
    if not body.is_height_reasonable(height):
        return _HEIGHT_UNREASONABLE_REPLY

    target_user_id = state["target_user_id"]
    state_store.clear(telegram_user_id)
    body.set_height(db, target_user_id, height)
    return f"好的，已經幫你記錄身高為 {height:.1f} 公分囉！"


# --- 體重 ---


def start_weight_log(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我要記錄體重」／`/log_weight`：開始記錄體重（FR-46），一般新增固定是今天。"""
    state_store.set(
        telegram_user_id,
        {"flow": "pending_weight_value", "target_user_id": user_id, "weight_date": _now().date(), "weight_id": None},
    )
    return "好的，請告訴我你的體重（公斤）："


def start_weight_backfill(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我要補記體重」／`/backfill_weight`：開始補記流程，先問要補記哪一天（FR-46）。"""
    state_store.set(telegram_user_id, {"flow": "pending_weight_backfill_date", "target_user_id": user_id})
    return "好的，要補記哪一天的體重呢？（例如：昨天、8/1）"


def handle_weight_backfill_date_step(llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_weight_backfill_date` 狀態下使用者提供的日期描述，講清楚後接著問體重數值。"""
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]

    parsed = _parse_key_value_block(
        llm_client.generate_text(
            _BACKFILL_DATE_PARSE_PROMPT.format(feature_label="體重", date_reply=text, current_date_text=_current_date_text())
        )
    )
    if parsed.get("STATUS") != "CLEAR":
        return _BACKFILL_DATE_UNCLEAR_REPLY

    weight_date = _parse_date_only(parsed.get("DATE", ""))
    if weight_date is None:
        return _BACKFILL_DATE_UNCLEAR_REPLY
    if weight_date > _now().date():
        return "不能補記還沒發生的未來日期喔，麻煩再講一次要補記哪一天！"

    state_store.set(
        telegram_user_id,
        {"flow": "pending_weight_value", "target_user_id": target_user_id, "weight_date": weight_date, "weight_id": None},
    )
    return "好的，請告訴我那天的體重（公斤）："


def handle_weight_value_step(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_weight_value` 狀態下使用者提供的體重數值；不合理範圍原地反問，不清除狀態。

    寫入成功後附上 BMI 說明（已設定身高才有）、體重目標達成判斷（FR-45），兩者都是「有才附加」，
    缺少身高或沒有進行中的體重目標都不影響體重紀錄本身成功寫入。
    """
    state = state_store.get(telegram_user_id)
    weight = _parse_positive_float(text)
    if weight is None:
        return "不好意思，我沒看懂，麻煩輸入一個數字喔（例如：75）"
    if not body.is_weight_reasonable(weight):
        return _WEIGHT_UNREASONABLE_REPLY

    target_user_id = state["target_user_id"]
    weight_date = state["weight_date"]
    weight_id = state.get("weight_id")
    state_store.clear(telegram_user_id)

    if weight_id is None:
        body.create_weight_log(db, target_user_id, weight, weight_date)
    else:
        body.update_weight_log(db, weight_id, weight)

    reply = f"好的，已經幫你記錄體重為 {weight:.1f} 公斤囉！"
    height = body.get_height(db, target_user_id)
    if height is not None:
        reply += "\n" + body.format_bmi_note(weight, height)
    goal_message = body.check_weight_goal_achieved(db, target_user_id, weight)
    if goal_message:
        reply += "\n\n" + goal_message
    return reply


def start_weight_list(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我的體重紀錄」／`/my_weight_logs`：列出最近的體重紀錄，並進入可更新/刪除的模式。"""
    logs = body.list_weight_logs(db, user_id)
    listing = body.format_weight_log_list(logs)
    if not logs:
        return listing

    state_store.set(
        telegram_user_id,
        {"flow": "pending_weight_list_action", "target_user_id": user_id, "weight_log_ids": [item["id"] for item in logs]},
    )
    return f"{listing}\n\n如果要更新或刪除某一筆，請輸入編號；不需要的話輸入「結束」。"


def handle_weight_list_action_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_weight_list_action` 狀態下使用者輸入的編號，選定要更新/刪除的那一筆。"""
    state = state_store.get(telegram_user_id)
    if text in _EXIT_PHRASES:
        state_store.clear(telegram_user_id)
        return "好的，已結束體重紀錄查詢模式！"

    ids = state["weight_log_ids"]
    if not text.isdigit() or not (1 <= int(text) <= len(ids)):
        return f"請輸入 1～{len(ids)} 之間的編號，或輸入「結束」離開喔！"

    state_store.set(
        telegram_user_id,
        {"flow": "pending_weight_action_choice", "target_user_id": state["target_user_id"], "weight_log_id": ids[int(text) - 1]},
    )
    return "要更新這筆還是刪除呢？"


def handle_weight_action_choice_step(db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_weight_action_choice` 狀態下使用者對「要更新這筆還是刪除呢？」的回覆。"""
    state = state_store.get(telegram_user_id)
    weight_log_id = state["weight_log_id"]
    target_user_id = state["target_user_id"]

    decision = llm_client.generate_text(_WEIGHT_ACTION_CLASSIFY_PROMPT.format(text=text)).strip()
    if decision == "UPDATE":
        row = db.select("body_weight_logs", where="id = %s", params=(weight_log_id,), fetch_one=True)
        state_store.set(
            telegram_user_id,
            {"flow": "pending_weight_value", "target_user_id": target_user_id, "weight_date": row["entry_date"], "weight_id": weight_log_id},
        )
        return "好的，請告訴我新的體重（公斤）："
    if decision == "DELETE":
        state_store.set(telegram_user_id, {"flow": "pending_weight_delete_confirm", "target_user_id": target_user_id, "weight_log_id": weight_log_id})
        return "確定要刪除這筆體重紀錄嗎？這個動作沒辦法復原喔！"

    state_store.clear(telegram_user_id)
    return "不好意思，我不太確定你的意思，這筆體重紀錄維持原狀，你可以再查詢一次體重紀錄清單重新選擇喔！"


def handle_weight_delete_confirm_step(db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_weight_delete_confirm` 狀態下使用者對刪除確認的回覆（簡單一輪 CONFIRM/CANCEL）。"""
    state = state_store.get(telegram_user_id)
    weight_log_id = state["weight_log_id"]
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_WEIGHT_DELETE_CONFIRM_PROMPT.format(text=text)).strip()
    if decision != "CONFIRM":
        return "好的，這筆體重紀錄保留，沒有刪除！"

    body.delete_weight_log(db, weight_log_id)
    return "好的，已經刪除這筆體重紀錄了！"


# --- 運動 ---


def start_exercise_log(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我要記錄運動」／`/log_exercise`：開始記錄運動（FR-47），先問項目。"""
    state_store.set(
        telegram_user_id,
        {"flow": "pending_exercise_activity", "target_user_id": user_id, "exercise_date": _now().date(), "exercise_id": None},
    )
    return "好的，你做了什麼運動呢？"


def start_exercise_backfill(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我要補記運動」／`/backfill_exercise`：開始補記流程，先問要補記哪一天（FR-47）。"""
    state_store.set(telegram_user_id, {"flow": "pending_exercise_backfill_date", "target_user_id": user_id})
    return "好的，要補記哪一天的運動呢？（例如：昨天、8/1）"


def handle_exercise_backfill_date_step(llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_exercise_backfill_date` 狀態下使用者提供的日期描述，講清楚後接著問運動項目。"""
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]

    parsed = _parse_key_value_block(
        llm_client.generate_text(
            _BACKFILL_DATE_PARSE_PROMPT.format(feature_label="運動", date_reply=text, current_date_text=_current_date_text())
        )
    )
    if parsed.get("STATUS") != "CLEAR":
        return _BACKFILL_DATE_UNCLEAR_REPLY

    exercise_date = _parse_date_only(parsed.get("DATE", ""))
    if exercise_date is None:
        return _BACKFILL_DATE_UNCLEAR_REPLY
    if exercise_date > _now().date():
        return "不能補記還沒發生的未來日期喔，麻煩再講一次要補記哪一天！"

    state_store.set(
        telegram_user_id,
        {"flow": "pending_exercise_activity", "target_user_id": target_user_id, "exercise_date": exercise_date, "exercise_id": None},
    )
    return "好的，你做了什麼運動呢？"


def handle_exercise_activity_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_exercise_activity` 狀態下使用者提供的運動項目（自由文字）。"""
    state = state_store.get(telegram_user_id)
    activity = text.strip()
    if not activity:
        return "不好意思，我沒看懂，麻煩告訴我運動項目是什麼呢？"

    state_store.set(telegram_user_id, {**state, "flow": "pending_exercise_duration", "activity": activity})
    return "運動了多久呢？（分鐘，例如：30）"


def handle_exercise_duration_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_exercise_duration` 狀態下使用者提供的運動時長（分鐘）。"""
    state = state_store.get(telegram_user_id)
    duration = _parse_positive_int(text)
    if duration is None:
        return "不好意思，我沒看懂，麻煩輸入一個正整數（分鐘），例如：30"

    state_store.set(telegram_user_id, {**state, "flow": "pending_exercise_heart_rate", "duration_minutes": duration})
    return "有心率紀錄嗎？有的話告訴我數字，沒有的話輸入「沒有」："


def handle_exercise_heart_rate_step(db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_exercise_heart_rate` 狀態下使用者提供的心率（選填），寫入前呼叫 LLM 估算卡路里
    （FR-47，決策①），估算失敗不擋下整筆紀錄，見 `body.estimate_exercise_calories()`。"""
    state = state_store.get(telegram_user_id)
    heart_rate = None
    if text.strip() not in ("沒有", "不用", "無"):
        heart_rate = _parse_positive_int(text)
        if heart_rate is None:
            return "不好意思，我沒看懂，麻煩輸入心率數字，或輸入「沒有」跳過："

    target_user_id = state["target_user_id"]
    exercise_date = state["exercise_date"]
    exercise_id = state.get("exercise_id")
    activity = state["activity"]
    duration_minutes = state["duration_minutes"]
    state_store.clear(telegram_user_id)

    estimated_calories = body.estimate_exercise_calories(llm_client, activity, duration_minutes, heart_rate)

    if exercise_id is None:
        body.create_exercise_log(db, target_user_id, activity, duration_minutes, heart_rate, estimated_calories, exercise_date)
    else:
        body.update_exercise_log(db, exercise_id, activity, duration_minutes, heart_rate, estimated_calories)

    if estimated_calories is not None:
        return f"OK，已經幫你記錄好了！這次運動大約消耗了 {estimated_calories:.0f} 大卡，這個數字只是估算值，不會到很準確喔！"
    return "OK，已經幫你記錄好了！這次沒能順利估算消耗的卡路里，不過紀錄已經存好了。"


def start_exercise_list(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我的運動紀錄」／`/my_exercise_logs`：列出最近的運動紀錄，並進入可更新/刪除的模式。"""
    logs = body.list_exercise_logs(db, user_id)
    listing = body.format_exercise_log_list(logs)
    if not logs:
        return listing

    state_store.set(
        telegram_user_id,
        {"flow": "pending_exercise_list_action", "target_user_id": user_id, "exercise_log_ids": [item["id"] for item in logs]},
    )
    return f"{listing}\n\n如果要更新或刪除某一筆，請輸入編號；不需要的話輸入「結束」。"


def handle_exercise_list_action_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_exercise_list_action` 狀態下使用者輸入的編號，選定要更新/刪除的那一筆。"""
    state = state_store.get(telegram_user_id)
    if text in _EXIT_PHRASES:
        state_store.clear(telegram_user_id)
        return "好的，已結束運動紀錄查詢模式！"

    ids = state["exercise_log_ids"]
    if not text.isdigit() or not (1 <= int(text) <= len(ids)):
        return f"請輸入 1～{len(ids)} 之間的編號，或輸入「結束」離開喔！"

    state_store.set(
        telegram_user_id,
        {"flow": "pending_exercise_action_choice", "target_user_id": state["target_user_id"], "exercise_log_id": ids[int(text) - 1]},
    )
    return "要更新這筆還是刪除呢？"


def handle_exercise_action_choice_step(db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_exercise_action_choice` 狀態下使用者對「要更新這筆還是刪除呢？」的回覆。"""
    state = state_store.get(telegram_user_id)
    exercise_log_id = state["exercise_log_id"]
    target_user_id = state["target_user_id"]

    decision = llm_client.generate_text(_EXERCISE_ACTION_CLASSIFY_PROMPT.format(text=text)).strip()
    if decision == "UPDATE":
        row = db.select("exercise_logs", where="id = %s", params=(exercise_log_id,), fetch_one=True)
        state_store.set(
            telegram_user_id,
            {"flow": "pending_exercise_activity", "target_user_id": target_user_id, "exercise_date": row["entry_date"], "exercise_id": exercise_log_id},
        )
        return "好的，那我們重新輸入一次，你做了什麼運動呢？"
    if decision == "DELETE":
        state_store.set(telegram_user_id, {"flow": "pending_exercise_delete_confirm", "target_user_id": target_user_id, "exercise_log_id": exercise_log_id})
        return "確定要刪除這筆運動紀錄嗎？這個動作沒辦法復原喔！"

    state_store.clear(telegram_user_id)
    return "不好意思，我不太確定你的意思，這筆運動紀錄維持原狀，你可以再查詢一次運動紀錄清單重新選擇喔！"


def handle_exercise_delete_confirm_step(db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_exercise_delete_confirm` 狀態下使用者對刪除確認的回覆（簡單一輪 CONFIRM/CANCEL）。"""
    state = state_store.get(telegram_user_id)
    exercise_log_id = state["exercise_log_id"]
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_EXERCISE_DELETE_CONFIRM_PROMPT.format(text=text)).strip()
    if decision != "CONFIRM":
        return "好的，這筆運動紀錄保留，沒有刪除！"

    body.delete_exercise_log(db, exercise_log_id)
    return "好的，已經刪除這筆運動紀錄了！"


# --- 飲食（含飲水） ---


def start_diet_log(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我要記錄飲食」／`/log_diet`：開始記錄飲食/飲水（FR-48），先問類型。"""
    state_store.set(
        telegram_user_id,
        {"flow": "pending_diet_entry_type", "target_user_id": user_id, "diet_date": _now().date(), "diet_id": None},
    )
    return body.format_diet_entry_type_prompt()


def start_diet_backfill(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我要補記飲食」／`/backfill_diet`：開始補記流程，先問要補記哪一天（FR-48）。"""
    state_store.set(telegram_user_id, {"flow": "pending_diet_backfill_date", "target_user_id": user_id})
    return "好的，要補記哪一天的飲食呢？（例如：昨天、8/1）"


def handle_diet_backfill_date_step(llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_diet_backfill_date` 狀態下使用者提供的日期描述，講清楚後接著問飲食/飲水類型。"""
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]

    parsed = _parse_key_value_block(
        llm_client.generate_text(
            _BACKFILL_DATE_PARSE_PROMPT.format(feature_label="飲食", date_reply=text, current_date_text=_current_date_text())
        )
    )
    if parsed.get("STATUS") != "CLEAR":
        return _BACKFILL_DATE_UNCLEAR_REPLY

    diet_date = _parse_date_only(parsed.get("DATE", ""))
    if diet_date is None:
        return _BACKFILL_DATE_UNCLEAR_REPLY
    if diet_date > _now().date():
        return "不能補記還沒發生的未來日期喔，麻煩再講一次要補記哪一天！"

    state_store.set(
        telegram_user_id,
        {"flow": "pending_diet_entry_type", "target_user_id": target_user_id, "diet_date": diet_date, "diet_id": None},
    )
    return body.format_diet_entry_type_prompt()


def handle_diet_entry_type_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_diet_entry_type` 狀態下使用者選擇的類型（飲食/飲水），分流到不同下一步。"""
    state = state_store.get(telegram_user_id)
    entry_type = body.resolve_diet_entry_type(text)
    if entry_type is None:
        return "不好意思，我沒看懂，麻煩從下面選一個喔：\n\n" + body.format_diet_entry_type_prompt()

    if entry_type == "food":
        state_store.set(telegram_user_id, {**state, "flow": "pending_diet_description", "entry_type": entry_type})
        return "好的，那你吃了什麼呢？可以描述食物內容（例如：雞胸肉便當一份）："

    state_store.set(telegram_user_id, {**state, "flow": "pending_diet_water_amount", "entry_type": entry_type})
    return "好的，喝了多少水呢？（毫升，例如：500）"


def handle_diet_description_step(db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str, privacy_llm_client=None) -> str:
    """處理 `pending_diet_description` 狀態下使用者提供的食物內容，呼叫 LLM 拆算三大營養素與熱量
    （FR-48，決策②），估算失敗不擋下整筆紀錄；務必附上 FR-17c 估算誤差聲明。"""
    state = state_store.get(telegram_user_id)
    description, pii_detected = privacy.mask_text(text, privacy_llm_client)

    target_user_id = state["target_user_id"]
    diet_date = state["diet_date"]
    diet_id = state.get("diet_id")
    state_store.clear(telegram_user_id)

    macros = body.estimate_diet_macros(llm_client, description)

    if diet_id is None:
        body.create_diet_log(db, target_user_id, "food", description, diet_date, macros=macros)
    else:
        body.delete_diet_log(db, diet_id)
        body.create_diet_log(db, target_user_id, "food", description, diet_date, macros=macros)

    reply = "好的，已經幫你記錄好了！" + body.format_diet_macro_note(macros)
    if pii_detected:
        reply += _PII_DETECTED_REMINDER
    return reply


def handle_diet_water_amount_step(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_diet_water_amount` 狀態下使用者提供的飲水量（毫升）。"""
    state = state_store.get(telegram_user_id)
    water_ml = _parse_positive_int(text)
    if water_ml is None:
        return "不好意思，我沒看懂，麻煩輸入一個正整數（毫升），例如：500"

    target_user_id = state["target_user_id"]
    diet_date = state["diet_date"]
    diet_id = state.get("diet_id")
    state_store.clear(telegram_user_id)

    if diet_id is None:
        body.create_diet_log(db, target_user_id, "water", "飲水", diet_date, water_ml=water_ml)
    else:
        body.delete_diet_log(db, diet_id)
        body.create_diet_log(db, target_user_id, "water", "飲水", diet_date, water_ml=water_ml)

    return f"好的，已經幫你記錄喝水 {water_ml} 毫升囉！"


def start_diet_list(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我的飲食紀錄」／`/my_diet_logs`：列出最近的飲食/飲水紀錄，並進入可更新/刪除的模式。"""
    logs = body.list_diet_logs(db, user_id)
    listing = body.format_diet_log_list(logs)
    if not logs:
        return listing

    state_store.set(
        telegram_user_id,
        {"flow": "pending_diet_list_action", "target_user_id": user_id, "diet_log_ids": [item["id"] for item in logs]},
    )
    return f"{listing}\n\n如果要更新或刪除某一筆，請輸入編號；不需要的話輸入「結束」。"


def handle_diet_list_action_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_diet_list_action` 狀態下使用者輸入的編號，選定要更新/刪除的那一筆。"""
    state = state_store.get(telegram_user_id)
    if text in _EXIT_PHRASES:
        state_store.clear(telegram_user_id)
        return "好的，已結束飲食紀錄查詢模式！"

    ids = state["diet_log_ids"]
    if not text.isdigit() or not (1 <= int(text) <= len(ids)):
        return f"請輸入 1～{len(ids)} 之間的編號，或輸入「結束」離開喔！"

    state_store.set(
        telegram_user_id,
        {"flow": "pending_diet_action_choice", "target_user_id": state["target_user_id"], "diet_log_id": ids[int(text) - 1]},
    )
    return "要更新這筆還是刪除呢？"


def handle_diet_action_choice_step(db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_diet_action_choice` 狀態下使用者對「要更新這筆還是刪除呢？」的回覆。

    選更新時重新走一次「選類型→內容/毫升數」，`diet_id` 帶著代表這是編輯（實作上用刪除舊列＋
    新增新列完成，理由是食物內容一旦改變，營養拆算本來就得重新呼叫 LLM，跟直接 UPDATE 沒有效率差異）。
    """
    state = state_store.get(telegram_user_id)
    diet_log_id = state["diet_log_id"]
    target_user_id = state["target_user_id"]

    decision = llm_client.generate_text(_DIET_ACTION_CLASSIFY_PROMPT.format(text=text)).strip()
    if decision == "UPDATE":
        row = db.select("diet_logs", where="id = %s", params=(diet_log_id,), fetch_one=True)
        state_store.set(
            telegram_user_id,
            {"flow": "pending_diet_entry_type", "target_user_id": target_user_id, "diet_date": row["entry_date"], "diet_id": diet_log_id},
        )
        return "好的，那我們重新選一次：\n\n" + body.format_diet_entry_type_prompt()
    if decision == "DELETE":
        state_store.set(telegram_user_id, {"flow": "pending_diet_delete_confirm", "target_user_id": target_user_id, "diet_log_id": diet_log_id})
        return "確定要刪除這筆飲食紀錄嗎？這個動作沒辦法復原喔！"

    state_store.clear(telegram_user_id)
    return "不好意思，我不太確定你的意思，這筆飲食紀錄維持原狀，你可以再查詢一次飲食紀錄清單重新選擇喔！"


def handle_diet_delete_confirm_step(db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_diet_delete_confirm` 狀態下使用者對刪除確認的回覆（簡單一輪 CONFIRM/CANCEL）。"""
    state = state_store.get(telegram_user_id)
    diet_log_id = state["diet_log_id"]
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_DIET_DELETE_CONFIRM_PROMPT.format(text=text)).strip()
    if decision != "CONFIRM":
        return "好的，這筆飲食紀錄保留，沒有刪除！"

    body.delete_diet_log(db, diet_log_id)
    return "好的，已經刪除這筆飲食紀錄了！"


# --- 體態目標（三個子功能共用） ---


def start_body_goal(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我要設定體態管理目標」／`/set_body_goal`：開始設定目標（FR-46～FR-48），先問類型。"""
    state_store.set(telegram_user_id, {"flow": "pending_goal_type", "target_user_id": user_id})
    return body.format_goal_type_prompt()


def handle_goal_type_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_goal_type` 狀態下使用者選擇的目標類型，依類型分流到不同的目標值問法。"""
    state = state_store.get(telegram_user_id)
    goal_type = body.resolve_goal_type(text)
    if goal_type is None:
        return "不好意思，我沒看懂，麻煩從下面選一個喔：\n\n" + body.format_goal_type_prompt()

    target_user_id = state["target_user_id"]
    if goal_type == "weight":
        state_store.set(telegram_user_id, {"flow": "pending_goal_weight_value", "target_user_id": target_user_id})
        return "好的，請告訴我目標體重是多少公斤？"
    if goal_type == "exercise":
        state_store.set(telegram_user_id, {"flow": "pending_goal_exercise_minutes", "target_user_id": target_user_id})
        return "好的，請告訴我這個目標要達成的累積運動分鐘數（例如：這個月運動滿 300 分鐘，就輸入 300）："

    state_store.set(telegram_user_id, {"flow": "pending_goal_diet_description", "target_user_id": target_user_id})
    return "好的，請用你自己的話告訴我飲食目標是什麼（例如：控制在每天 1800 大卡以內）："


def handle_goal_weight_value_step(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_goal_weight_value` 狀態下使用者提供的目標體重；`baseline_value` 取當下最新一筆
    體重紀錄（沒有紀錄時為 None，達成判斷會被跳過，見 `body.check_weight_goal_achieved()`）。"""
    state = state_store.get(telegram_user_id)
    target_value = _parse_positive_float(text)
    if target_value is None:
        return "不好意思，我沒看懂，麻煩輸入一個數字喔（例如：60）"

    target_user_id = state["target_user_id"]
    baseline_value = body.latest_weight(db, target_user_id)
    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_goal_deadline",
            "target_user_id": target_user_id,
            "goal_type": "weight",
            "target_value": target_value,
            "baseline_value": baseline_value,
            "target_description": f"目標體重 {target_value:.1f} 公斤",
        },
    )
    return "有預計完成時間嗎？（例如：三個月內完成，沒有的話輸入「沒有」）"


def handle_goal_exercise_minutes_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_goal_exercise_minutes` 狀態下使用者提供的目標累積運動分鐘數。"""
    state = state_store.get(telegram_user_id)
    target_value = _parse_positive_int(text)
    if target_value is None:
        return "不好意思，我沒看懂，麻煩輸入一個正整數（分鐘），例如：300"

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_goal_deadline",
            "target_user_id": state["target_user_id"],
            "goal_type": "exercise",
            "target_value": target_value,
            "baseline_value": None,
            "target_description": f"累積運動 {target_value} 分鐘",
        },
    )
    return "有預計完成時間嗎？（例如：三個月內完成，沒有的話輸入「沒有」）"


def handle_goal_diet_description_step(state_store: ConversationStateStore, telegram_user_id: int, text: str, privacy_llm_client=None) -> str:
    """處理 `pending_goal_diet_description` 狀態下使用者提供的飲食目標敘述（自由文字，決策④：
    飲食目標太主觀，不做自動達成判斷，`target_value` 固定為 None）。"""
    state = state_store.get(telegram_user_id)
    description = text.strip()
    if not description:
        return "不好意思，我沒看懂，麻煩用你自己的話告訴我飲食目標是什麼呢？"
    masked_description, _pii_detected = privacy.mask_text(description, privacy_llm_client)

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_goal_deadline",
            "target_user_id": state["target_user_id"],
            "goal_type": "diet",
            "target_value": None,
            "baseline_value": None,
            "target_description": masked_description,
        },
    )
    return "有預計完成時間嗎？（例如：三個月內完成，沒有的話輸入「沒有」）"


def handle_goal_deadline_step(db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_goal_deadline` 狀態下使用者對「有預計完成時間嗎？」的回覆，講清楚（或明確表示
    不需要）後正式寫入目標。"""
    state = state_store.get(telegram_user_id)

    parsed = _parse_key_value_block(
        llm_client.generate_text(_GOAL_DEADLINE_PARSE_PROMPT.format(deadline_reply=text, current_date_text=_current_date_text()))
    )
    status = parsed.get("STATUS")
    if status == "UNCLEAR":
        return _GOAL_DEADLINE_UNCLEAR_REPLY

    target_date = None
    if status == "HAS_DEADLINE":
        target_date = _parse_date_only(parsed.get("DATE", ""))
        if target_date is None:
            return _GOAL_DEADLINE_UNCLEAR_REPLY

    target_user_id = state["target_user_id"]
    goal_type = state["goal_type"]
    target_description = state["target_description"]
    target_value = state["target_value"]
    baseline_value = state["baseline_value"]
    state_store.clear(telegram_user_id)

    body.create_goal(db, target_user_id, goal_type, target_description, target_value, baseline_value, target_date)

    deadline_part = f"，期限是 {target_date:%Y/%m/%d}" if target_date else ""
    return f"好的，已經幫你記錄目標「{target_description}」了{deadline_part}，加油！"


def start_body_goal_list(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「我的體態目標」／`/my_body_goals`：列出進行中的目標，並進入可取消的模式（這版不支援修改
    目標內容，要調整就取消重設）。"""
    goals = body.list_active_goals(db, user_id)
    listing = body.format_goal_list(goals)
    if not goals:
        return listing

    state_store.set(
        telegram_user_id,
        {"flow": "pending_goal_list_action", "target_user_id": user_id, "goal_ids": [item["id"] for item in goals]},
    )
    return f"{listing}\n\n如果要取消某個目標，請輸入編號；不需要的話輸入「結束」。"


def handle_goal_list_action_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_goal_list_action` 狀態下使用者輸入的編號，選定要取消的那個目標。"""
    state = state_store.get(telegram_user_id)
    if text in _EXIT_PHRASES:
        state_store.clear(telegram_user_id)
        return "好的，已結束體態目標查詢模式！"

    ids = state["goal_ids"]
    if not text.isdigit() or not (1 <= int(text) <= len(ids)):
        return f"請輸入 1～{len(ids)} 之間的編號，或輸入「結束」離開喔！"

    state_store.set(telegram_user_id, {"flow": "pending_goal_cancel_confirm", "goal_id": ids[int(text) - 1]})
    return "確定要取消這個體態目標嗎？"


def handle_goal_cancel_confirm_step(db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_goal_cancel_confirm` 狀態下使用者對取消確認的回覆（簡單一輪 CONFIRM/CANCEL）。"""
    state = state_store.get(telegram_user_id)
    goal_id = state["goal_id"]
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_GOAL_CANCEL_CONFIRM_PROMPT.format(text=text)).strip()
    if decision != "CONFIRM":
        return "好的，這個體態目標保留，沒有取消！"

    body.cancel_goal(db, goal_id)
    return "好的，已經取消這個體態目標了！"


# ---------------------------------------------------------------------------
# 設定家人生日（2026-08-04，Step 2.3，見 robinson SPEC.md FR-53）
#
# 僅 Owner（Robin）能觸發，用來補齊 `0030_seed_family_birthdays.sql` 沒有涵蓋到的家人生日
# （弟媳/大妹婿/小妹婿/阿姨等）。流程比照 /set_toggle：先列出所有已綁定使用者供選編號
# （pending_family_birthday_select），選定後再問生日（pending_family_birthday_date），
# 格式解析交給 notifications.parse_birthday_input()，失敗就停留在原地反問，不清空狀態。
# ---------------------------------------------------------------------------


def start_set_family_birthday(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int) -> str:
    """/set_family_birthday：僅 Owner 觸發，列出所有已綁定使用者供選擇要設定誰的生日。"""
    members = notifications.list_family_members(db)
    if not members:
        return "目前還沒有任何已綁定的使用者，沒有可以設定生日的對象喔！"

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_family_birthday_select",
            "candidates": [member["id"] for member in members],
        },
    )
    return notifications.format_family_member_prompt(members)


def handle_family_birthday_select_step(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    """處理 `pending_family_birthday_select` 狀態下使用者輸入的編號，選定要設定生日的對象。"""
    state = state_store.get(telegram_user_id)
    if text in _EXIT_PHRASES:
        state_store.clear(telegram_user_id)
        return "好的，已結束設定家人生日模式！"

    candidates = state["candidates"]
    if not text.isdigit() or not (1 <= int(text) <= len(candidates)):
        return f"請輸入 1～{len(candidates)} 之間的編號，或輸入「結束」離開喔！"

    target_user_id = candidates[int(text) - 1]
    state_store.set(
        telegram_user_id,
        {"flow": "pending_family_birthday_date", "target_user_id": target_user_id},
    )
    return "請問生日是幾月幾號呢？可以直接給「YYYY-MM-DD」，不確定出生年份的話給「M/D」也可以！"


def handle_family_birthday_date_step(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    """處理 `pending_family_birthday_date` 狀態下使用者輸入的生日文字，解析失敗就停留原地反問。"""
    state = state_store.get(telegram_user_id)
    if text in _EXIT_PHRASES:
        state_store.clear(telegram_user_id)
        return "好的，已結束設定家人生日模式！"

    birthday = notifications.parse_birthday_input(text)
    if birthday is None:
        return "生日格式看不懂喔，麻煩用「YYYY-MM-DD」或「M/D」再給我一次！"

    target_user_id = state["target_user_id"]
    notifications.set_birthday(db, target_user_id, birthday)
    state_store.clear(telegram_user_id)

    target_user = db.select("users", where="id = %s", params=(target_user_id,), fetch_one=True)
    role = target_user["role"] if target_user else "這位家人"
    return f"已經記下 {role} 的生日了，之後到了會自動提醒大家喔！"
