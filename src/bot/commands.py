"""內建指令與對話式設定流程（對應 docs/specs/platform-auth/SPEC.md FR-4～FR-6、
docs/specs/feature-toggles/SPEC.md FR-1～FR-2、docs/specs/chat-core/SPEC.md ADR-4、FR-10～FR-12、
docs/specs/robinson/SPEC.md FR-20、FR-31、FR-31a、FR-32、FR-41～FR-44、FR-41a、FR-42a、FR-45～FR-48、
FR-49、FR-50、FR-60～FR-63）。"""
import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from src.bot import auth, body, finance, friend_chat, knowledge, menu, mood, notifications, privacy, templates, toggles
from src.bot import certificate_answer, certificate_quiz, certificate_schedule
from src.bot import certificate_exam_scores, certificate_goals, certificate_stats
from src.bot import complaint as complaint_module
from src.bot import job_search
from src.bot import todo as todo_module
from src.bot import youtube
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


# ---------------------------------------------------------------------------
# 權限管理（2026-08-15，Phase 6 第二批 2a，取代舊版 /set_invite_codes，
# 見 docs/specs/SPEC.md FR-4、FR-4a～FR-4d、docs/ADR/discuss/robinson.md）
# 選單觸發，callback_data 走 "permission:<action>"；四個操作共用同一組 flow 前綴
# "permission_<action>"，接上 Phase 6 第一批已寫好的 auth.create_user_and_invite()／
# auth.resend_passcode()／auth.set_user_active()。
# ---------------------------------------------------------------------------

_PERMISSION_ACTION_PROMPTS = {
    "disable": "請問要停用哪一位使用者？請輸入編號：",
    "enable": "請問要恢復哪一位使用者？請輸入編號：",
    "resend": "請問要重發通關密碼給哪一位使用者？請輸入編號：",
}


def start_permission_menu() -> tuple[str, dict]:
    """FR-4：Owner 專屬「權限管理」選單首頁。不需要 db／state_store，純粹回覆固定選單。"""
    keyboard = {
        "inline_keyboard": [
            [{"text": "➕ 建立使用者", "callback_data": "permission:create"}],
            [{"text": "⛔ 停用使用者", "callback_data": "permission:disable"}],
            [{"text": "✅ 恢復使用者", "callback_data": "permission:enable"}],
            [{"text": "🔁 重發通關密碼", "callback_data": "permission:resend"}],
            [{"text": "🔙 返回主選單", "callback_data": "menu:main"}],
        ]
    }
    return "請選擇要進行的權限管理操作：", keyboard


def handle_permission_callback(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    action: str,
) -> tuple[str, dict | None]:
    """權限管理選單按下其中一個操作按鈕後的分派，開始對應的引導式文字流程。"""
    if action == "create":
        state_store.set(telegram_user_id, {"flow": "permission_create", "step": "awaiting_family_title"})
        return "請問要新增哪一位家人？請輸入家庭稱謂（例如：爸爸）：", None

    if action in ("disable", "enable", "resend"):
        candidates = [u for u in db.select("users") if not u["is_owner"]]
        if not candidates:
            return "目前還沒有任何一般使用者，沒有可以操作的對象喔！", menu.back_to_main_menu_keyboard()

        state_store.set(
            telegram_user_id,
            {"flow": f"permission_{action}", "step": "awaiting_target", "candidates": [u["id"] for u in candidates]},
        )
        lines = [_PERMISSION_ACTION_PROMPTS[action], ""]
        for index, user in enumerate(candidates, start=1):
            status = "啟用中" if user.get("is_active", True) else "已停用"
            display_name = user.get("nickname") or user.get("family_title") or user["role"]
            lines.append(f"{index}. {display_name}（{status}）")
        return "\n".join(lines), None

    raise ValueError(f"未知的權限管理操作：{action}")


def handle_permission_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """依目前對話狀態處理權限管理流程中輸入的下一句話。"""
    state = state_store.get(telegram_user_id)
    flow = state.get("flow") if state else None
    step = state.get("step") if state else None

    if flow == "permission_create":
        if text in _EXIT_PHRASES:
            state_store.clear(telegram_user_id)
            return "好的，已結束權限管理模式！"

        if step == "awaiting_family_title":
            state_store.set(
                telegram_user_id,
                {"flow": "permission_create", "step": "awaiting_nickname", "family_title": text},
            )
            return f"收到，請問「{text}」的暱稱是？（不需要的話輸入「略過」）"

        if step == "awaiting_nickname":
            family_title = state["family_title"]
            nickname = None if text in {"略過", "skip"} else text
            result = auth.create_user_and_invite(db, family_title=family_title, nickname=nickname)
            state_store.clear(telegram_user_id)
            nickname_line = f"暱稱：{result['nickname']}\n" if result["nickname"] else ""
            return (
                f"已建立「{family_title}」！\n"
                f"{nickname_line}"
                f"使用者 ID：{result['mobile_user_id']}\n"
                f"通關密碼：{result['passcode']}\n"
                "（此密碼僅能使用一次，24 小時內有效，請盡快提供給本人）"
            )

    if flow in ("permission_disable", "permission_enable", "permission_resend"):
        if text in _EXIT_PHRASES:
            state_store.clear(telegram_user_id)
            return "好的，已結束權限管理模式！"

        candidates = state["candidates"]
        if not text.isdigit() or not (1 <= int(text) <= len(candidates)):
            return f"請輸入 1～{len(candidates)} 之間的編號喔！"

        target_user_id = candidates[int(text) - 1]
        state_store.clear(telegram_user_id)

        if flow == "permission_disable":
            auth.set_user_active(db, target_user_id, active=False)
            return "已停用該使用者，Mobile Refresh Token 也一併撤銷了。"
        if flow == "permission_enable":
            auth.set_user_active(db, target_user_id, active=True)
            return "已恢復該使用者，對方需要重新登入或重新綁定。"
        new_code = auth.resend_passcode(db, target_user_id)
        return f"已重發通關密碼：{new_code}\n（舊密碼已立即失效，此密碼僅能使用一次，24 小時內有效）"

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
# 待辦事項（2026-08-02，Step 1.7，見 robinson SPEC.md FR-31、FR-31a、FR-32、FR-56e；
# 2026-08-16 選單化，Phase 6 第二批 2f，見 docs/ADR/discuss/robinson.md）
#
# 新增有兩個入口，共用同一段「時間→提醒→行事曆同步」多輪反問：
# ①自然語言偵測（chat.py 偵測到「什麼時候要做什麼事」主動反問，FR-31、FR-56e 既有規格，
#   2f 決策維持不變）：先問「要不要記錄」（pending_todo_confirm），確認後把使用者原話當
#   `original_text` 直接進入時間反問；②選單「➕ 新增」按鈕（`todo:new`）：略過「要不要記錄」
#   這輪（按鈕本身就是明確意圖），改先反問「要記什麼事」（pending_todo_new_content），使用者
#   這輪回覆存成 `original_text` 後同樣接到時間反問，兩個入口自此共用同一套狀態機。
#
# 時間反問（pending_todo_time，時間講不清楚時停留原地繼續反問，不硬存猜錯的時間）→ 提醒反問
# （pending_todo_reminder）→ 行事曆同步反問（pending_todo_calendar_sync）之後，2f 新增一層
# 摘要＋「✅ 確認送出／❌ 取消」按鈕（pending_todo_confirm_save，比照 2b～2e 的「摘要→二次確認」
# 結構），使用者按確認才真正呼叫 `todo.create_todo()` 寫入；打字視為取消，導回待辦事項選單
# （比照 2b `important_days.handle_delete_confirm_text()` 的保守做法）。
#
# 查詢＋標記完成/取消（2f 前）：「我的待辦事項」／`/my_todos` 觸發 start_todo_list()，選定編號
# 後反問要標記完成還是取消，交給 LLM 判斷使用者這句話的意思。2f 起改成清單每筆附「✅ 完成」
# 「🚫 取消」按鈕（`todo:complete:<id>`／`todo:cancel:<id>`），取代編號輸入＋LLM 分類這兩輪自由
# 文字，移除 `_TODO_ACTION_CLASSIFY_PROMPT`；`/my_todos`、「我的待辦事項」文字觸發詞一併移除，
# 不提供相容期（比照 2c／2d 決策）。
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

# 2026-08-05（見 robinson SPEC.md FR-66a、ADR-17）：待辦事項新增流程最後追加一輪反問，每次都
# 明確詢問、不預設，避免使用者忘記講而讓私密待辦意外曝光在家庭共用行事曆上（ADR-17 決策 7）。
_TODO_CALENDAR_SYNC_PROMPT = (
    "Robinson 剛詢問使用者「要不要同步到 Google 家庭行事曆呢？」，這是使用者這一則的回覆："
    "「{text}」。\n"
    "請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 要同步 → CONFIRM\n"
    "(2) 不要同步 → CANCEL"
)

# FR-66a：預設事件時長（分鐘），單一時間點待辦（沒有 start_at）在行事曆上顯示成一個時間區塊，
# 而不是零長度事件；區間待辦則直接用 start_at～due_at 當作事件的起訖時間，不套用這個預設值。
_TODO_CALENDAR_DEFAULT_DURATION = timedelta(minutes=30)

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


def start_todo_menu() -> tuple[str, dict]:
    """主選單按下「✅ 待辦事項」後的子選單首頁（2f，見模組上方區塊說明）。"""
    keyboard = {
        "inline_keyboard": [
            [{"text": "📋 查看清單", "callback_data": "todo:list"}],
            [{"text": "➕ 新增", "callback_data": "todo:add"}],
            [{"text": "🔙 返回主選單", "callback_data": "menu:main"}],
        ]
    }
    return "待辦事項，請選擇要進行的操作：", keyboard


def start_todo_new(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """選單「➕ 新增」按鈕觸發：略過自然語言入口的「要不要記錄」這輪反問（按鈕本身就是明確
    意圖），先問「要記什麼事」，回覆後接到既有的時間反問（`pending_todo_time`）。"""
    state_store.set(telegram_user_id, {"flow": "pending_todo_new_content", "target_user_id": user_id})
    return "好的！這筆待辦事項要記什麼事呢？"


def handle_todo_new_content_step(
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
) -> str:
    """處理 `pending_todo_new_content` 狀態下使用者輸入的待辦內容，講清楚後接到時間反問。"""
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]

    content = text.strip()
    if not content:
        return "內容不可以是空白，請重新輸入："

    state_store.set(
        telegram_user_id,
        {"flow": "pending_todo_time", "target_user_id": target_user_id, "original_text": content},
    )
    return "好的，請問是什麼時候呢？"


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
    """處理 `pending_todo_reminder` 狀態下使用者對「需要在前 30 分鐘時提醒你嗎？」的回覆
    （FR-31、FR-31b、FR-32）。

    2026-08-05 起（見 FR-66a、ADR-17）不在這一步就寫入 `todos`，改為再多問一輪「要不要同步到
    Google 家庭行事曆」（`pending_todo_calendar_sync`），確定後才真正呼叫 `create_todo()`。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    content = state["content"]
    due_at = state["due_at"]
    start_at = state.get("start_at")

    decision = llm_client.generate_text(_TODO_REMINDER_CONFIRM_PROMPT.format(text=text)).strip()
    remind_before_30min = decision == "CONFIRM"

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_todo_calendar_sync",
            "target_user_id": target_user_id,
            "content": content,
            "due_at": due_at,
            "start_at": start_at,
            "remind_before_30min": remind_before_30min,
        },
    )
    return "好的！最後想問一下，這筆待辦事項要不要同步到 Google 家庭行事曆呢？（家人會在自己手機上看到）"


def _todo_calendar_window(due_at: datetime, start_at: datetime | None) -> tuple[str, str]:
    """把待辦事項的時間換算成 Calendar 事件的起訖 ISO 8601 字串（FR-66a）。

    區間待辦（`start_at` 非 None）直接用 `start_at`～`due_at` 當起訖；單一時間點待辦沒有天然的
    區間概念，套用 `_TODO_CALENDAR_DEFAULT_DURATION`（30 分鐘）當作事件時長，避免建立零長度事件。
    """
    if start_at is not None:
        return start_at.isoformat(), due_at.isoformat()
    return due_at.isoformat(), (due_at + _TODO_CALENDAR_DEFAULT_DURATION).isoformat()


def _format_todo_time_summary_line(due_at: datetime, start_at: datetime | None) -> str:
    """摘要畫面用的時間文字，格式跟 `todo.py`／`_build_todo_time_confirmation_reply` 的
    `YYYY/MM/DD HH:MM` 表示法一致，方便使用者對照前一輪反問看到的內容。"""
    if start_at is None:
        return _format_ymd_hm(due_at)
    return f"{_format_ymd_hm(start_at)} ～ {_format_ymd_hm(due_at)}"


def _todo_summary_text(content: str, due_at: datetime, start_at: datetime | None, remind_before_30min: bool, sync_to_calendar: bool) -> str:
    reminder_line = "會" if remind_before_30min else "不會"
    sync_line = "會" if sync_to_calendar else "不會"
    return (
        "請確認以下待辦事項內容：\n\n"
        f"內容：{content}\n"
        f"時間：{_format_todo_time_summary_line(due_at, start_at)}\n"
        f"提前 30 分鐘提醒：{reminder_line}\n"
        f"同步 Google 家庭行事曆：{sync_line}"
    )


def handle_todo_calendar_sync_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
    calendar_client=None,
) -> tuple[str, dict]:
    """處理 `pending_todo_calendar_sync` 狀態下使用者對「要不要同步到 Google 家庭行事曆」的回覆。

    2026-08-16（Phase 6 第二批 2f）起這一步不再直接寫入 `todos`，改成組出完整摘要＋
    「✅ 確認送出／❌ 取消」按鈕（`pending_todo_confirm_save`，比照 2b～2e 的「摘要→二次確認」
    結構），使用者按確認才真正呼叫 `todo.create_todo()`。`calendar_client` 沿用既有的參數位置，
    實際建立 Calendar 事件延後到 `handle_todo_confirm_save()` 才發生。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    content = state["content"]
    due_at = state["due_at"]
    start_at = state.get("start_at")
    remind_before_30min = state["remind_before_30min"]

    decision = llm_client.generate_text(_TODO_CALENDAR_SYNC_PROMPT.format(text=text)).strip()
    sync_to_calendar = decision == "CONFIRM"

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_todo_confirm_save",
            "target_user_id": target_user_id,
            "content": content,
            "due_at": due_at,
            "start_at": start_at,
            "remind_before_30min": remind_before_30min,
            "sync_to_calendar": sync_to_calendar,
        },
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ 確認送出", "callback_data": "todo:confirm_save"}],
            [{"text": "❌ 取消", "callback_data": "menu:todo"}],
        ]
    }
    return _todo_summary_text(content, due_at, start_at, remind_before_30min, sync_to_calendar), keyboard


def handle_todo_confirm_save_text(state_store: ConversationStateStore, telegram_user_id: int) -> tuple[str, dict]:
    """`pending_todo_confirm_save` 這個狀態只接受按鈕操作；使用者改用打字時，比照
    `important_days.handle_delete_confirm_text()` 的保守做法，直接取消流程並導回待辦事項選單。"""
    state_store.clear(telegram_user_id)
    return "確認送出請用上面的按鈕操作喔，這次先幫你取消了。", menu.back_to_main_menu_keyboard()


def handle_todo_confirm_save(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    calendar_client=None,
) -> tuple[str, dict]:
    """處理 `pending_todo_confirm_save` 狀態下「✅ 確認送出」按鈕，這一步才真正寫入 `todos`
    （FR-66a、ADR-17）。

    同步到 Calendar 是額外的加值功能，任何失敗（`calendar_client` 為 `None`，代表環境變數未設定；
    或底層 API 呼叫拋例外）都優雅降級為「待辦事項已成功記錄，但沒有出現在 Calendar 上」，不影響
    待辦事項本身寫入成功、也不把技術細節暴露給使用者，只記警告 log（比照
    `webhook._upload_error_log()` 的降級哲學）。
    """
    state = state_store.get(telegram_user_id)
    if not state or state.get("flow") != "pending_todo_confirm_save":
        return "目前沒有進行中的待辦事項設定。", menu.back_to_main_menu_keyboard()

    target_user_id = state["target_user_id"]
    content = state["content"]
    due_at = state["due_at"]
    start_at = state.get("start_at")
    remind_before_30min = state["remind_before_30min"]
    sync_to_calendar = state["sync_to_calendar"]
    state_store.clear(telegram_user_id)

    todo_id = todo_module.create_todo(
        db, target_user_id, content, due_at, remind_before_30min, start_at=start_at,
        sync_to_calendar=sync_to_calendar,
    )

    if sync_to_calendar and calendar_client is not None:
        try:
            start_iso, end_iso = _todo_calendar_window(due_at, start_at)
            event_id = calendar_client.create_event(
                summary=content, start=start_iso, end=end_iso, description="來自 Robinson 待辦事項",
            )
            todo_module.set_calendar_event_id(db, todo_id, event_id)
        except Exception:
            _logger.exception(
                "待辦事項（id=%s）同步到 Google Calendar 失敗，待辦本身已成功記錄不受影響", todo_id
            )

    return "好的，已經幫你記錄好了！", menu.back_to_main_menu_keyboard()


def _format_todo_item_when(item: dict) -> str:
    """跟 `todo.py` 私有函式 `_format_when()` 邏輯一致，這裡獨立寫一份避免跨模組依賴對方的
    私有成員（比照本模組 `_now()`／`_current_date_text()` 的既有慣例）。"""
    due_local = item["due_at"].astimezone(_TAIWAN_TZ)
    start_at = item.get("start_at")
    if start_at is None:
        return f"{due_local:%Y/%m/%d %H:%M}"
    start_local = start_at.astimezone(_TAIWAN_TZ)
    return f"{start_local:%Y/%m/%d %H:%M} ～ {due_local:%Y/%m/%d %H:%M}"


def start_todo_list(db: CloudSQLClient, user_id: int) -> tuple[str, dict]:
    """「📋 查看清單」：列出目前待處理清單，每筆附「✅ 完成」「🚫 取消」按鈕（FR-32，2f 改按鈕式）。"""
    pending_todos = todo_module.list_pending_todos(db, user_id)
    if not pending_todos:
        keyboard = {"inline_keyboard": [[{"text": "🔙 返回待辦事項", "callback_data": "menu:todo"}]]}
        return "目前沒有待辦事項喔！", keyboard

    lines = ["這是你目前的待辦事項：", ""]
    buttons = []
    for index, item in enumerate(pending_todos, start=1):
        lines.append(f"{index}. {item['content']}（{_format_todo_item_when(item)}）")
        buttons.append([
            {"text": f"✅ 完成 {index}", "callback_data": f"todo:complete:{item['id']}"},
            {"text": f"🚫 取消 {index}", "callback_data": f"todo:cancel:{item['id']}"},
        ])
    buttons.append([{"text": "🔙 返回待辦事項", "callback_data": "menu:todo"}])
    return "\n".join(lines), {"inline_keyboard": buttons}


def handle_todo_status_action(
    db: CloudSQLClient,
    user_id: int,
    todo_id: int,
    new_status: str,
    calendar_client=None,
) -> tuple[str, dict]:
    """處理清單「✅ 完成」／「🚫 取消」按鈕（FR-31a）。

    比照 2b `important_days.handle_delete()` 的做法，重新查一次 `user_id` 比對是否為本人的
    待辦事項（FR-6c，不假設清單畫面篩過就安全，避免偽造/過期 callback_data 誤傷其他家人的紀錄）。

    2026-08-05 起（見 FR-66a、ADR-17）：這筆待辦事項如果當初有同步到 Calendar
    （`google_calendar_event_id` 非空），標記完成/取消時一併刪除對應事件——不管是完成還是取消，
    這筆待辦都不再需要出現在家庭共用行事曆上。刪除失敗（`calendar_client` 為 `None`或 API 例外）
    優雅降級，不影響待辦事項本身的狀態更新。
    """
    row = db.select("todos", where="id = %s AND user_id = %s", params=(todo_id, user_id), fetch_one=True)
    if row is None:
        return "找不到這筆待辦事項，可能已經被處理過了。", menu.back_to_main_menu_keyboard()

    todo_module.mark_status(db, todo_id, new_status)

    google_calendar_event_id = row.get("google_calendar_event_id")
    if google_calendar_event_id and calendar_client is not None:
        try:
            calendar_client.delete_event(event_id=google_calendar_event_id)
        except Exception:
            _logger.exception(
                "刪除待辦事項（id=%s）對應的 Google Calendar 事件失敗，待辦狀態已成功更新不受影響",
                todo_id,
            )

    label = "完成" if new_status == "completed" else "取消"
    return f"好的，已經把「{row['content']}」標記為{label}囉！", menu.back_to_main_menu_keyboard()


# ---------------------------------------------------------------------------
# 心情小記（2026-08-02，Step 1.8，見 robinson SPEC.md FR-49、FR-50、FR-56h；
# 2026-08-16 全面改選單觸發＋補摘要確認，Phase 6 第二批 2c，見 docs/ADR/discuss/robinson.md）
#
# 流程：選單「😊 心情」→ 新增／補記／查看清單。新增與補記共用 pending_mood_category →
# pending_mood_content → **pending_mood_confirm**（新增，摘要→二次確認，2c 新增）→ 寫入後
# 主動問 FR-50 個人成就三選一提示（pending_mood_achievement，使用者可用既有的 _EXIT_PHRASES
# 跳過，不強迫回答）。`entry_date`／`journal_id` 兩個欄位讓「一般新增」「補記新增」
# 「編輯既有紀錄」共用同一組 category/content/confirm/achievement 步驟：`entry_date` 決定
# 寫入哪一天、`journal_id` 是 None 時代表新增（INSERT），非 None 時代表編輯（UPDATE）。
#
# 查看清單（`handle_list`）直接列出每一筆＋「✏️ 編輯」「🗑 刪除」按鈕（比照 2b 重要日子的
# `important_days.handle_list()` 作法），不再需要「查詢清單 → 輸入編號 → LLM 判斷要更新還是
# 刪除」這三段式反問；刪除也改成按鈕二次確認（`mood:confirm_delete:<id>`），移除原本
# `_MOOD_ACTION_CLASSIFY_PROMPT`／`_MOOD_DELETE_CONFIRM_PROMPT` 這兩個 LLM 分類 Prompt——
# 選單按鈕本身就是明確意圖，不需要再靠 LLM 猜使用者是要更新還是刪除。
#
# 日記內容／個人成就都是自由文字、可能含個資，依 2026-08-02 與 Robin 確認的範圍決策，寫入
# `mood_journals` 前一律先過 `privacy.mask_text()`，跟一般聊天／圖片說明文字／語音轉文字三個
# 既有入口的防線一致；摘要確認畫面顯示的也是遮蔽後的內容，避免個資在畫面上重複曝光。
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


def _parse_date_only(raw: str) -> date | None:
    """把 `_MOOD_BACKFILL_DATE_PARSE_PROMPT` 輸出的 `YYYY-MM-DD` 字串換算成 date；
    格式不對（或空字串）回傳 None，交由呼叫端視為 UNCLEAR 處理。"""
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()  # noqa: DTZ007
    except ValueError:
        return None


def start_mood_menu() -> tuple[str, dict]:
    """主選單「📝 日常紀錄」→「😊 心情」子選單首頁。"""
    keyboard = {
        "inline_keyboard": [
            [{"text": "➕ 新增", "callback_data": "mood:new"}],
            [{"text": "🕐 補記", "callback_data": "mood:backfill"}],
            [{"text": "📋 查看清單", "callback_data": "mood:list"}],
            [{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}],
        ]
    }
    return "心情，請選擇要進行的操作：", keyboard


def start_mood_journal(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「➕ 新增」：開始心情小記流程，先問心情分類（FR-49、FR-56h）。

    一般（非補記）新增：`entry_date` 固定是今天，`journal_id` 是 None（代表 INSERT）。
    """
    state_store.set(
        telegram_user_id,
        {"flow": "pending_mood_category", "target_user_id": user_id, "entry_date": _now().date(), "journal_id": None},
    )
    return mood.format_category_prompt()


def start_mood_backfill(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「🕐 補記」：開始補記流程，先問要補記哪一天（FR-49 補記擴充）。"""
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
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
    privacy_llm_client=None,
) -> tuple[str, dict]:
    """處理 `pending_mood_content` 狀態下使用者提供的日記內容，先遮蔽個資、組出摘要，回傳
    確認／取消按鈕，不在這一步直接寫入（2c 新增的摘要→二次確認關卡）。

    `journal_id` 是 None 時代表新增（`entry_date` 可能是今天或補記的過去日期）；非 None 時
    代表這是編輯既有紀錄，確認後改為 UPDATE、沿用原本的 `entry_date`。

    `privacy_llm_client`（見 docs/specs/privacy-masking/SPEC.md FR-4）：日記內容可能含個資，
    確認畫面與寫入 `mood_journals` 都使用遮蔽後的內容；`None` 時優雅降級成只跑免費的 Regex 層。
    """
    state = state_store.get(telegram_user_id)
    mood_category = state["mood_category"]

    masked_content, pii_detected = privacy.mask_text(text, privacy_llm_client)
    state_store.set(telegram_user_id, {**state, "flow": "pending_mood_confirm", "masked_content": masked_content, "pii_detected": pii_detected})

    summary = (
        "請確認以下內容：\n\n"
        f"心情：{mood.category_label(mood_category)}\n"
        f"日記內容：{masked_content}"
    )
    if pii_detected:
        summary += _PII_DETECTED_REMINDER
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ 確認送出", "callback_data": "mood:confirm_save"}],
            [{"text": "❌ 取消", "callback_data": "menu:daily_log"}],
        ]
    }
    return summary, keyboard


def handle_mood_confirm_save(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int) -> str:
    """`mood:confirm_save`：實際寫入心情小記（新增或編輯），接著問 FR-50 個人成就。"""
    state = state_store.get(telegram_user_id)
    if not state or state.get("flow") != "pending_mood_confirm":
        return "目前沒有進行中的心情紀錄設定。"

    target_user_id = state["target_user_id"]
    entry_date = state["entry_date"]
    journal_id = state.get("journal_id")
    mood_category = state["mood_category"]
    masked_content = state["masked_content"]

    if journal_id is None:
        journal_id = mood.create_mood_journal(db, target_user_id, mood_category, masked_content, entry_date)
    else:
        mood.update_mood_journal(db, journal_id, mood_category, masked_content)

    state_store.set(
        telegram_user_id,
        {"flow": "pending_mood_achievement", "target_user_id": target_user_id, "journal_id": journal_id},
    )
    return (
        "好的，已經紀錄了！要不要順便回顧一下今天：完成了什麼一句話總結／挑一件有感覺的事／"
        "寫下啟發或下次想改變的地方（選一項就好，不想回答也可以輸入「結束」跳過）："
    )


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


def handle_mood_list(db: CloudSQLClient, user_id: int) -> tuple[str, dict]:
    """「📋 查看清單」：列出最近的心情小記，每一筆附「✏️ 編輯」「🗑 刪除」按鈕。"""
    journals = mood.list_mood_journals(db, user_id)
    if not journals:
        return "目前還沒有任何心情紀錄，可以按「➕ 新增」建立第一筆！", {
            "inline_keyboard": [[{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}]]
        }

    listing = mood.format_mood_journal_list(journals)
    buttons = [
        [
            {"text": f"✏️ 編輯 {index}", "callback_data": f"mood:edit:{item['id']}"},
            {"text": f"🗑 刪除 {index}", "callback_data": f"mood:delete:{item['id']}"},
        ]
        for index, item in enumerate(journals, start=1)
    ]
    buttons.append([{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}])
    return listing, {"inline_keyboard": buttons}


def start_mood_edit(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, journal_id: int) -> str:
    """「✏️ 編輯」：沿用原本記錄的 `entry_date`（找不到就 fallback 用 `created_at` 換算，理由同
    `mood.entry_date_of()`），重新走一次分類/內容兩輪反問，`journal_id` 帶著代表這是編輯而非新增。
    """
    row = db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True)
    if row is None or row.get("user_id") != user_id:
        return "找不到這筆心情紀錄，可能已經被刪除了。"

    entry_date = row.get("entry_date") or row["created_at"].astimezone(_TAIWAN_TZ).date()
    state_store.set(
        telegram_user_id,
        {"flow": "pending_mood_category", "target_user_id": user_id, "entry_date": entry_date, "journal_id": journal_id},
    )
    return "好的，那我們重新選一次心情分類：\n\n" + mood.format_category_prompt()


def start_mood_delete_confirm(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, journal_id: int) -> tuple[str, dict]:
    row = db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True)
    if row is None or row.get("user_id") != user_id:
        return "找不到這筆心情紀錄，可能已經被刪除了。", {"inline_keyboard": [[{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}]]}

    state_store.set(telegram_user_id, {"flow": "mood_delete_confirm", "journal_id": journal_id})
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ 確認刪除", "callback_data": f"mood:confirm_delete:{journal_id}"}],
            [{"text": "❌ 取消", "callback_data": "mood:list"}],
        ]
    }
    return "確定要刪除這筆心情紀錄嗎？這個動作沒辦法復原喔！", keyboard


def handle_mood_delete(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, journal_id: int) -> str:
    """`mood:confirm_delete:<id>` 觸發時重新驗證擁有者（FR-6c：callback_data 一律重新驗證權限，
    不能只靠上一步 `start_mood_delete_confirm` 篩過就假設安全）。"""
    state_store.clear(telegram_user_id)
    row = db.select("mood_journals", where="id = %s", params=(journal_id,), fetch_one=True)
    if row is None or row.get("user_id") != user_id:
        return "找不到這筆心情紀錄，可能已經被刪除了。"
    mood.delete_mood_journal(db, journal_id)
    return "好的，已經刪除這筆心情紀錄了！"


def handle_mood_confirm_text(state_store: ConversationStateStore, telegram_user_id: int) -> tuple[str, dict]:
    """`pending_mood_confirm`／`mood_delete_confirm` 這兩個狀態只接受按鈕操作；使用者改用
    打字時，比照 `important_days.handle_delete_confirm_text()` 的保守做法，直接結束流程並
    導回日常紀錄選單，不當成未知狀態拋例外。"""
    state_store.clear(telegram_user_id)
    keyboard = {"inline_keyboard": [[{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}]]}
    return "這個步驟請用上面的按鈕操作喔，這次先幫你取消了。", keyboard


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
# - 腰圍（2026-08-08 追加，FR-46 擴充）：`/set_waist`，單輪，設計與身高完全對稱（初始設定、
#   變動才修正，非每日紀錄）；額外在 `/log_weight` 記錄體重後，若使用者從未設定過腰圍，順便問
#   一次要不要記錄（`pending_waist_offer`），問過一次後不會每次記體重都重複問。腰圍只是參考
#   指標、非必要欄位，BMI 計算不使用腰圍。
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
# 2026-08-08 追加（FR-46 擴充）：腰圍為參考指標、非必要欄位，措辭刻意比身高/體重柔和，強調可跳過。
_WAIST_UNREASONABLE_REPLY = "這個腰圍數字好像不太合理喔（大概在 40~200 公分之間），麻煩再確認一次告訴我（不想記錄的話也可以直接跟我說「跳過」）："
_WAIST_OFFER_PROMPT = "順便問一下，要不要也記錄一下腰圍呢？（可直接輸入公分數字，不想記錄的話回覆「跳過」或任何話都可以，之後想記錄再跟我說「設定腰圍」就好）"
_WAIST_OFFER_SKIPPED_REPLY = "好的，那就先不記錄腰圍，之後想記錄的話直接跟我說「設定腰圍」即可！"

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
# 2026-08-16（Phase 6 第二批 2c）：運動改選單觸發＋按鈕式編輯／刪除，原本的
# _EXERCISE_ACTION_CLASSIFY_PROMPT／_EXERCISE_DELETE_CONFIRM_PROMPT（LLM 判斷更新/刪除意圖）
# 已隨 handle_exercise_action_choice_step／handle_exercise_delete_confirm_step 一併移除，
# 選單按鈕本身就是明確意圖，不需要再靠 LLM 猜。
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


# --- 腰圍（2026-08-08 追加，FR-46 擴充）---
#
# 設計比照身高：獨立指令「設定腰圍」／`/set_waist` 可隨時主動設定/更新；另外在
# handle_weight_value_step() 記錄體重後，若使用者「從未設定過腰圍」，會順便問一次要不要記錄
# （見 _WAIST_OFFER_PROMPT／handle_waist_offer_step()），問過一次之後除非使用者自己再更新，
# 不會每次記體重都重複問，避免每天打擾。腰圍只是參考指標，跳過完全不影響其他功能。


def start_set_waist(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「設定腰圍」／`/set_waist`：開始設定腰圍（FR-46 擴充）。"""
    state_store.set(telegram_user_id, {"flow": "pending_waist_value", "target_user_id": user_id})
    return "好的，請告訴我你的腰圍（公分）："


def handle_waist_value_step(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_waist_value` 狀態下使用者提供的腰圍數值；不合理範圍原地反問，不清除狀態。"""
    state = state_store.get(telegram_user_id)
    waist = _parse_positive_float(text)
    if waist is None:
        return "不好意思，我沒看懂，麻煩輸入一個數字喔（例如：80）"
    if not body.is_waist_reasonable(waist):
        return _WAIST_UNREASONABLE_REPLY

    target_user_id = state["target_user_id"]
    state_store.clear(telegram_user_id)
    body.set_waist(db, target_user_id, waist)
    return f"好的，已經幫你記錄腰圍為 {waist:.1f} 公分囉！"


def handle_waist_offer_step(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_waist_offer` 狀態下使用者對「順便問要不要記錄腰圍」的回覆（見
    handle_weight_value_step()）。

    這一步刻意不用 LLM 分類「要/不要」，直接嘗試把回覆解析成數字：能解析出合理範圍內的數字就
    當作腰圍存起來；解析出數字但超出合理範圍則原地反問一次（不清除狀態，比照身高/體重的既有
    寫法）；完全無法解析成數字（包含「跳過」「不用」等任何說法）一律視為跳過，直接結束這輪，
    不強迫使用者一定要明確拒絕——腰圍本來就是可有可無的參考指標，低摩擦比嚴謹分類更重要。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    waist = _parse_positive_float(text)

    if waist is None:
        state_store.clear(telegram_user_id)
        return _WAIST_OFFER_SKIPPED_REPLY
    if not body.is_waist_reasonable(waist):
        return _WAIST_UNREASONABLE_REPLY

    state_store.clear(telegram_user_id)
    body.set_waist(db, target_user_id, waist)
    return f"好的，已經幫你記錄腰圍為 {waist:.1f} 公分囉！"


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


def handle_weight_value_step(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str, calendar_client=None
) -> str:
    """處理 `pending_weight_value` 狀態下使用者提供的體重數值；不合理範圍原地反問，不清除狀態。

    寫入成功後附上 BMI 說明（已設定身高才有）、體重目標達成判斷（FR-45），兩者都是「有才附加」，
    缺少身高或沒有進行中的體重目標都不影響體重紀錄本身成功寫入。

    `calendar_client`（2026-08-05，見 FR-66c、ADR-17）：透傳給 `body.check_weight_goal_achieved()`，
    達成時順便刪除對應的 Calendar 事件。

    2026-08-08 追加（FR-46 擴充）：只有「新增一筆體重紀錄」（`weight_id is None`，排除
    `/my_weight_logs` 觸發的更新流程）且「使用者從未設定過腰圍」時，才會順便問一次要不要記錄
    腰圍（見 handle_waist_offer_step()）；問過一次之後除非使用者自己再更新，不會每次記體重都
    重複問。這種情況下刻意不清除對話狀態，改成切到 `pending_waist_offer`，讓使用者下一則回覆
    被導去處理腰圍，而不是直接結束這輪對話。
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

    is_new_entry = weight_id is None
    if is_new_entry:
        body.create_weight_log(db, target_user_id, weight, weight_date)
    else:
        body.update_weight_log(db, weight_id, weight)

    reply = f"好的，已經幫你記錄體重為 {weight:.1f} 公斤囉！"
    height = body.get_height(db, target_user_id)
    if height is not None:
        reply += "\n" + body.format_bmi_note(weight, height)
    goal_message = body.check_weight_goal_achieved(db, target_user_id, weight, calendar_client=calendar_client)
    if goal_message:
        reply += "\n\n" + goal_message

    should_offer_waist = is_new_entry and body.get_waist(db, target_user_id) is None
    if should_offer_waist:
        state_store.set(telegram_user_id, {"flow": "pending_waist_offer", "target_user_id": target_user_id})
        reply += "\n\n" + _WAIST_OFFER_PROMPT
    else:
        state_store.clear(telegram_user_id)
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


def start_exercise_menu() -> tuple[str, dict]:
    """主選單「📝 日常紀錄」→「🏃 運動」子選單首頁。"""
    keyboard = {
        "inline_keyboard": [
            [{"text": "➕ 新增", "callback_data": "exercise:new"}],
            [{"text": "🕐 補記", "callback_data": "exercise:backfill"}],
            [{"text": "📋 查看清單", "callback_data": "exercise:list"}],
            [{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}],
        ]
    }
    return "運動，請選擇要進行的操作：", keyboard


def start_exercise_log(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「➕ 新增」：開始記錄運動（FR-47），先問項目。"""
    state_store.set(
        telegram_user_id,
        {"flow": "pending_exercise_activity", "target_user_id": user_id, "exercise_date": _now().date(), "exercise_id": None},
    )
    return "好的，你做了什麼運動呢？"


def start_exercise_backfill(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「🕐 補記」：開始補記流程，先問要補記哪一天（FR-47）。"""
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


def handle_exercise_heart_rate_step(llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> tuple[str, dict]:
    """處理 `pending_exercise_heart_rate` 狀態下使用者提供的心率（選填），估算卡路里後組出摘要，
    回傳確認／取消按鈕，不在這一步直接寫入（2c 新增的摘要→二次確認關卡）。估算失敗不擋下整筆
    紀錄，見 `body.estimate_exercise_calories()`。"""
    state = state_store.get(telegram_user_id)
    heart_rate = None
    if text.strip() not in ("沒有", "不用", "無"):
        heart_rate = _parse_positive_int(text)
        if heart_rate is None:
            return "不好意思，我沒看懂，麻煩輸入心率數字，或輸入「沒有」跳過：", None

    activity = state["activity"]
    duration_minutes = state["duration_minutes"]
    estimated_calories = body.estimate_exercise_calories(llm_client, activity, duration_minutes, heart_rate)

    state_store.set(
        telegram_user_id,
        {**state, "flow": "pending_exercise_confirm", "heart_rate": heart_rate, "estimated_calories": estimated_calories},
    )

    calorie_line = f"{estimated_calories:.0f} 大卡（估算值，不會到很準確）" if estimated_calories is not None else "沒能順利估算"
    summary = (
        "請確認以下內容：\n\n"
        f"項目：{activity}\n"
        f"時長：{duration_minutes} 分鐘\n"
        f"心率：{heart_rate if heart_rate is not None else '（無）'}\n"
        f"消耗熱量：{calorie_line}"
    )
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ 確認送出", "callback_data": "exercise:confirm_save"}],
            [{"text": "❌ 取消", "callback_data": "menu:daily_log"}],
        ]
    }
    return summary, keyboard


def handle_exercise_confirm_save(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int) -> str:
    """`exercise:confirm_save`：實際寫入運動紀錄（新增或編輯）。"""
    state = state_store.get(telegram_user_id)
    if not state or state.get("flow") != "pending_exercise_confirm":
        return "目前沒有進行中的運動紀錄設定。"

    target_user_id = state["target_user_id"]
    exercise_date = state["exercise_date"]
    exercise_id = state.get("exercise_id")
    activity = state["activity"]
    duration_minutes = state["duration_minutes"]
    heart_rate = state["heart_rate"]
    estimated_calories = state["estimated_calories"]
    state_store.clear(telegram_user_id)

    if exercise_id is None:
        body.create_exercise_log(db, target_user_id, activity, duration_minutes, heart_rate, estimated_calories, exercise_date)
    else:
        body.update_exercise_log(db, exercise_id, activity, duration_minutes, heart_rate, estimated_calories)

    if estimated_calories is not None:
        return f"OK，已經幫你記錄好了！這次運動大約消耗了 {estimated_calories:.0f} 大卡，這個數字只是估算值，不會到很準確喔！"
    return "OK，已經幫你記錄好了！這次沒能順利估算消耗的卡路里，不過紀錄已經存好了。"


def handle_exercise_list(db: CloudSQLClient, user_id: int) -> tuple[str, dict]:
    """「📋 查看清單」：列出最近的運動紀錄，每一筆附「✏️ 編輯」「🗑 刪除」按鈕。"""
    logs = body.list_exercise_logs(db, user_id)
    if not logs:
        return "目前還沒有任何運動紀錄，可以按「➕ 新增」建立第一筆！", {
            "inline_keyboard": [[{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}]]
        }

    listing = body.format_exercise_log_list(logs)
    buttons = [
        [
            {"text": f"✏️ 編輯 {index}", "callback_data": f"exercise:edit:{item['id']}"},
            {"text": f"🗑 刪除 {index}", "callback_data": f"exercise:delete:{item['id']}"},
        ]
        for index, item in enumerate(logs, start=1)
    ]
    buttons.append([{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}])
    return listing, {"inline_keyboard": buttons}


def start_exercise_edit(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, exercise_log_id: int) -> str:
    """「✏️ 編輯」：沿用原本記錄的 `entry_date`，重新走一次項目/時長/心率三輪反問，
    `exercise_id` 帶著代表這是編輯而非新增。"""
    row = db.select("exercise_logs", where="id = %s", params=(exercise_log_id,), fetch_one=True)
    if row is None or row.get("user_id") != user_id:
        return "找不到這筆運動紀錄，可能已經被刪除了。"

    state_store.set(
        telegram_user_id,
        {"flow": "pending_exercise_activity", "target_user_id": user_id, "exercise_date": row["entry_date"], "exercise_id": exercise_log_id},
    )
    return "好的，那我們重新輸入一次，你做了什麼運動呢？"


def start_exercise_delete_confirm(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, exercise_log_id: int) -> tuple[str, dict]:
    row = db.select("exercise_logs", where="id = %s", params=(exercise_log_id,), fetch_one=True)
    if row is None or row.get("user_id") != user_id:
        return "找不到這筆運動紀錄，可能已經被刪除了。", {"inline_keyboard": [[{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}]]}

    state_store.set(telegram_user_id, {"flow": "exercise_delete_confirm", "exercise_log_id": exercise_log_id})
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ 確認刪除", "callback_data": f"exercise:confirm_delete:{exercise_log_id}"}],
            [{"text": "❌ 取消", "callback_data": "exercise:list"}],
        ]
    }
    return "確定要刪除這筆運動紀錄嗎？這個動作沒辦法復原喔！", keyboard


def handle_exercise_delete(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, exercise_log_id: int) -> str:
    """`exercise:confirm_delete:<id>` 觸發時重新驗證擁有者（理由同 `handle_mood_delete`）。"""
    state_store.clear(telegram_user_id)
    row = db.select("exercise_logs", where="id = %s", params=(exercise_log_id,), fetch_one=True)
    if row is None or row.get("user_id") != user_id:
        return "找不到這筆運動紀錄，可能已經被刪除了。"
    body.delete_exercise_log(db, exercise_log_id)
    return "好的，已經刪除這筆運動紀錄了！"


def handle_exercise_confirm_text(state_store: ConversationStateStore, telegram_user_id: int) -> tuple[str, dict]:
    """`pending_exercise_confirm`／`exercise_delete_confirm` 只接受按鈕操作，理由同
    `handle_mood_confirm_text`。"""
    state_store.clear(telegram_user_id)
    keyboard = {"inline_keyboard": [[{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}]]}
    return "這個步驟請用上面的按鈕操作喔，這次先幫你取消了。", keyboard


# --- 飲食（含飲水） ---
#
# 2026-08-16（Phase 6 第二批 2g，見 docs/ADR/discuss/robinson.md「Phase 6 第二批 2g」）：
# 全面改選單觸發，取代原 `/log_diet`／`/backfill_diet`／`/my_diet_logs`，不提供舊指令相容期。
# 飲食（`food`）、飲水（`water`）比照 Mobile App 的 single-daily 設計，同一天各自只能有一筆，
# 已有的話新增流程會導向查看清單的編輯功能；新增流程改成先問飲水、再問食物（各自可跳過），
# 食物內容支援文字／照片兩種輸入方式，算完營養素後可選擇沿用 AI 估算或自己填寫
# （`nutrition_source`），最後組摘要走「確認送出／取消」關卡才真的寫入。


def _diet_menu_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "➕ 新增", "callback_data": "diet:new"}],
            [{"text": "🕐 補記", "callback_data": "diet:backfill"}],
            [{"text": "📋 查看清單", "callback_data": "diet:list"}],
            [{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}],
        ]
    }


def start_diet_menu() -> tuple[str, dict]:
    """「🍚 飲食」子選單首頁：➕ 新增／🕐 補記／📋 查看清單／🔙 返回。"""
    return "飲食紀錄，請選擇要做什麼：", _diet_menu_keyboard()


def _diet_entries_for_date(db: CloudSQLClient, user_id: int, entry_date: date) -> dict:
    """查出某使用者某一天已存在的食物／飲水紀錄（single-daily，最多各一筆），回傳
    `{"food": row_or_None, "water": row_or_None}`，供新增流程判斷要問哪些題目。"""
    rows = db.select("diet_logs", where="user_id = %s AND entry_date = %s", params=(user_id, entry_date))
    return {
        "food": next((row for row in rows if row["entry_type"] == "food"), None),
        "water": next((row for row in rows if row["entry_type"] == "water"), None),
    }


def _start_diet_new_for_date(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, diet_date: date) -> tuple[str, dict]:
    """依指定日期（今天或補記日期）判斷食物／飲水各自是否已記過，決定新增流程要問哪些題目
    （FR-48，比照 Mobile App single-daily 設計）。"""
    existing = _diet_entries_for_date(db, user_id, diet_date)
    base_state = {
        "target_user_id": user_id, "diet_date": diet_date,
        "water_ml": None, "food_description": None, "food_nutrition_source": None, "food_macros": None,
    }

    if existing["food"] is not None and existing["water"] is not None:
        return (
            "你今天已經記過飲食和飲水囉，要修改的話請用『📋 查看清單』裡的編輯功能喔！",
            {"inline_keyboard": [[{"text": "📋 查看清單", "callback_data": "diet:list"}], [{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}]]},
        )
    if existing["water"] is not None:
        # 飲水已記過，跳過飲水提問，直接問食物。
        state_store.set(telegram_user_id, {**base_state, "flow": "pending_diet_food_choice"})
        return "要記錄食物嗎？", {"inline_keyboard": [[{"text": "✅ 要", "callback_data": "diet:food_yes"}, {"text": "❌ 不用", "callback_data": "diet:food_no"}]]}
    if existing["food"] is not None:
        # 食物已記過，跳過食物提問，直接問飲水。
        state_store.set(telegram_user_id, {**base_state, "flow": "pending_diet_water_choice"})
        return "要記錄飲水嗎？", {"inline_keyboard": [[{"text": "✅ 要", "callback_data": "diet:water_yes"}, {"text": "❌ 不用", "callback_data": "diet:water_no"}]]}

    state_store.set(telegram_user_id, {**base_state, "flow": "pending_diet_water_choice"})
    return "要記錄飲水嗎？", {"inline_keyboard": [[{"text": "✅ 要", "callback_data": "diet:water_yes"}, {"text": "❌ 不用", "callback_data": "diet:water_no"}]]}


def start_diet_log(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> tuple[str, dict]:
    """`diet:new`：開始記錄今天的飲食/飲水（FR-48）。"""
    return _start_diet_new_for_date(db, state_store, telegram_user_id, user_id, _now().date())


def start_diet_backfill(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """`diet:backfill`：開始補記流程，先問要補記哪一天（FR-48）。"""
    state_store.set(telegram_user_id, {"flow": "pending_diet_backfill_date", "target_user_id": user_id})
    return "好的，那我們補記一下，請問是哪一天呢？"


def handle_diet_backfill_date_step(db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str | tuple[str, dict]:
    """處理 `pending_diet_backfill_date` 狀態下使用者提供的日期描述，講清楚後依該日期判斷要問
    哪些題目（沿用 `_start_diet_new_for_date()`）。"""
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    parsed = _parse_date_description(llm_client, text)
    diet_date = _parse_date_only(parsed.get("DATE", ""))
    if diet_date is None:
        return "不好意思，我沒看懂是哪一天，可以再說清楚一點嗎？（例如：8/1、昨天、上週三）"
    if diet_date > _now().date():
        return "補記的日期不能是未來喔，麻煩重新輸入！"

    return _start_diet_new_for_date(db, state_store, telegram_user_id, target_user_id, diet_date)


def handle_diet_water_choice_step(state_store: ConversationStateStore, telegram_user_id: int, action: str) -> tuple[str, dict]:
    """`diet:water_yes`／`diet:water_no`：要不要記錄飲水。"""
    state = state_store.get(telegram_user_id)
    if action == "water_yes":
        state_store.set(telegram_user_id, {**state, "flow": "pending_diet_water_amount"})
        return "好的，這次喝了多少毫升的水呢？", None
    return _advance_to_food_choice(state_store, telegram_user_id, state)


def _advance_to_food_choice(state_store: ConversationStateStore, telegram_user_id: int, state: dict) -> tuple[str, dict]:
    if state.get("diet_id") is not None:
        # 編輯流程：這筆本來就只會是 food 或 water 其中一種，不重問另一項，直接結摘要。
        return handle_diet_build_summary(state_store, telegram_user_id)
    state_store.set(telegram_user_id, {**state, "flow": "pending_diet_food_choice"})
    return "要記錄食物嗎？", {"inline_keyboard": [[{"text": "✅ 要", "callback_data": "diet:food_yes"}, {"text": "❌ 不用", "callback_data": "diet:food_no"}]]}


def handle_diet_water_amount_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str | tuple[str, dict]:
    """處理 `pending_diet_water_amount` 狀態下使用者提供的飲水量（毫升），問完接著判斷要不要
    再問食物（編輯流程則直接結摘要，見 `_advance_to_food_choice()`）。"""
    state = state_store.get(telegram_user_id)
    water_ml = _parse_positive_int(text)
    if water_ml is None:
        return "不好意思，我沒看懂，麻煩輸入正整數的毫升數："

    state = {**state, "water_ml": water_ml}
    state_store.set(telegram_user_id, state)
    return _advance_to_food_choice(state_store, telegram_user_id, state)


def handle_diet_food_choice_step(state_store: ConversationStateStore, telegram_user_id: int, action: str) -> tuple[str, dict]:
    """`diet:food_yes`／`diet:food_no`：要不要記錄食物。"""
    state = state_store.get(telegram_user_id)
    if action == "food_yes":
        state_store.set(telegram_user_id, {**state, "flow": "pending_diet_food_input_mode"})
        return "食物內容要用文字輸入還是傳照片呢？", {
            "inline_keyboard": [[{"text": "📝 文字", "callback_data": "diet:food_text"}, {"text": "📷 照片", "callback_data": "diet:food_photo"}]]
        }
    return handle_diet_build_summary(state_store, telegram_user_id)


def handle_diet_food_input_mode_step(state_store: ConversationStateStore, telegram_user_id: int, action: str) -> str | tuple[str, dict]:
    """`diet:food_text`／`diet:food_photo`：食物內容要用文字還是照片輸入。"""
    state = state_store.get(telegram_user_id)
    if action == "food_photo":
        state_store.set(telegram_user_id, {**state, "flow": "pending_diet_photo"})
        return "請傳一張食物的照片給我：", None
    state_store.set(telegram_user_id, {**state, "flow": "pending_diet_description"})
    return "請輸入食物內容：", None


def handle_diet_description_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> tuple[str, dict]:
    """處理 `pending_diet_description` 狀態下使用者提供的食物內容（文字輸入或語音轉出來的文字
    皆可），套用個資遮蔽後接著問要 AI 估算還是自己填寫營養素。"""
    state = state_store.get(telegram_user_id)
    description, _detected = privacy.mask_text(text.strip())
    if not description:
        return "不好意思，內容好像是空的，麻煩重新輸入食物內容：", None

    state = {**state, "flow": "pending_diet_nutrition_source", "food_description": description}
    state_store.set(telegram_user_id, state)
    return "營養素怎麼算？", {
        "inline_keyboard": [[{"text": "🤖 AI 估算", "callback_data": "diet:nutrition_ai"}, {"text": "✍️ 我要自己填", "callback_data": "diet:nutrition_manual"}]]
    }


def handle_diet_photo_wait_step(state_store: ConversationStateStore, telegram_user_id: int) -> tuple[str, dict]:
    """`pending_diet_photo` 狀態下收到的是文字（含語音轉出來的文字）而不是照片——這一步要傳
    照片，文字在這裡沒有意義，提醒使用者並提供「改用文字輸入」的退路，避免卡住。"""
    state = state_store.get(telegram_user_id)
    state_store.set(telegram_user_id, {**state, "flow": "pending_diet_food_input_mode"})
    return "這一步要傳照片喔，如果想改用文字輸入食物內容，請按下面按鈕：", {
        "inline_keyboard": [[{"text": "📝 改用文字輸入", "callback_data": "diet:food_text"}]]
    }


def handle_diet_photo_message(db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, image_bytes: bytes, mime_type: str) -> str | tuple[str, dict]:
    """`pending_diet_photo` 狀態下收到照片：複用 Mobile App 既有的
    `src/services/app_diet_photo.recognize_diet_photo()` 辨識邏輯，把辨識出的內容＋不確定項目
    貼出來讓使用者確認或修正。"""
    import base64

    from src.services import app_diet_photo

    state = state_store.get(telegram_user_id)

    try:
        result = app_diet_photo.recognize_diet_photo(llm_client, base64.b64encode(image_bytes).decode("ascii"), mime_type)
    except app_diet_photo.DietPhotoError as exc:
        return str(exc)

    state_store.set(
        telegram_user_id,
        {**state, "flow": "pending_diet_photo_confirm", "food_description": result["description"]},
    )
    lines = [f"我看到的內容是：{result['description']}"]
    if result["uncertain_items"]:
        lines.append("")
        lines.append("有幾個地方不太確定：")
        lines.extend(f"- {item}" for item in result["uncertain_items"])
    lines.append("")
    lines.append("如果沒問題請回覆「好的」，需要修改的話請直接輸入完整正確的內容：")
    return "\n".join(lines)


def handle_diet_photo_confirm_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> tuple[str, dict]:
    """處理 `pending_diet_photo_confirm` 狀態下使用者的確認／修正回覆。"""
    state = state_store.get(telegram_user_id)
    text = text.strip()
    if text not in ("好的", "OK", "ok", "確認", "沒問題"):
        description, _detected = privacy.mask_text(text)
        if not description:
            return "不好意思，內容好像是空的，麻煩重新輸入完整的食物內容：", None
        state = {**state, "food_description": description}

    state = {**state, "flow": "pending_diet_nutrition_source"}
    state_store.set(telegram_user_id, state)
    return "營養素怎麼算？", {
        "inline_keyboard": [[{"text": "🤖 AI 估算", "callback_data": "diet:nutrition_ai"}, {"text": "✍️ 我要自己填", "callback_data": "diet:nutrition_manual"}]]
    }


def handle_diet_nutrition_source_step(llm_client, state_store: ConversationStateStore, telegram_user_id: int, action: str) -> str | tuple[str, dict]:
    """`diet:nutrition_ai`／`diet:nutrition_manual`：營養素要 AI 估算還是自己填寫。"""
    state = state_store.get(telegram_user_id)
    if action == "nutrition_manual":
        state_store.set(telegram_user_id, {**state, "flow": "pending_diet_manual_macros"})
        return "請依序輸入熱量（大卡）、蛋白質（g）、碳水化合物（g）、脂肪（g），用逗號分隔，例如：650,30,80,20", None

    macros = body.estimate_diet_macros(llm_client, state["food_description"])
    state = {**state, "food_nutrition_source": "ai", "food_macros": macros}
    state_store.set(telegram_user_id, state)
    return handle_diet_build_summary(state_store, telegram_user_id)


def _parse_manual_macros(text: str) -> dict | None:
    """解析人工填寫的「熱量,蛋白質,碳水,脂肪」四個數字，範圍比照 migration 0078 的 CHECK 限制
    （熱量 1～10000、三大營養素各 0～1000）；格式或範圍不對回傳 None。"""
    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 4:
        return None
    try:
        calories, protein, carbs, fat = (float(part) for part in parts)
    except ValueError:
        return None
    if not (0 < calories <= 10000):
        return None
    if not all(0 <= value <= 1000 for value in (protein, carbs, fat)):
        return None
    return {"estimated_calories": calories, "protein_g": protein, "carbs_g": carbs, "fat_g": fat}


def handle_diet_manual_macros_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> tuple[str, dict]:
    """處理 `pending_diet_manual_macros` 狀態下使用者輸入的四個數字。"""
    state = state_store.get(telegram_user_id)
    macros = _parse_manual_macros(text)
    if macros is None:
        return "請確認四個數字都有填、格式正確再試一次（熱量 1～10000、三大營養素 0～1000，用逗號分隔）：", None

    state = {**state, "food_nutrition_source": "manual", "food_macros": macros}
    state_store.set(telegram_user_id, state)
    return handle_diet_build_summary(state_store, telegram_user_id)


def handle_diet_build_summary(state_store: ConversationStateStore, telegram_user_id: int) -> tuple[str, dict]:
    """把 state 裡目前收集到的飲水／食物內容組成摘要，進入 `pending_diet_confirm` 二次確認關卡。
    兩項都沒有記的話不寫入，直接回到日常紀錄選單。"""
    state = state_store.get(telegram_user_id)
    water_ml = state.get("water_ml")
    description = state.get("food_description")
    macros = state.get("food_macros")
    nutrition_source = state.get("food_nutrition_source")

    if water_ml is None and description is None:
        state_store.clear(telegram_user_id)
        return "這次沒有要記錄的內容喔！", {"inline_keyboard": [[{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}]]}

    lines = ["請確認以下內容：", ""]
    if water_ml is not None:
        lines.append(f"飲水：{water_ml} 毫升")
    if description is not None:
        lines.append(f"食物：{description}")
        source_label = "AI 估算" if nutrition_source == "ai" else "人工填寫"
        lines.append(f"營養素來源：{source_label}")
        lines.append(body.format_diet_macro_note(macros, nutrition_source=nutrition_source or "ai"))

    state_store.set(telegram_user_id, {**state, "flow": "pending_diet_confirm"})
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ 確認送出", "callback_data": "diet:confirm_save"}],
            [{"text": "❌ 取消", "callback_data": "menu:daily_log"}],
        ]
    }
    return "\n".join(lines), keyboard


def handle_diet_confirm_save(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int) -> str:
    """`diet:confirm_save`：實際寫入這次收集到的飲水／食物紀錄（新增或編輯）。"""
    state = state_store.get(telegram_user_id)
    if not state or state.get("flow") != "pending_diet_confirm":
        return "目前沒有進行中的飲食紀錄設定。"

    target_user_id = state["target_user_id"]
    diet_date = state["diet_date"]
    diet_id = state.get("diet_id")
    water_ml = state.get("water_ml")
    description = state.get("food_description")
    macros = state.get("food_macros")
    nutrition_source = state.get("food_nutrition_source")
    state_store.clear(telegram_user_id)

    saved = []
    if diet_id is not None:
        # 編輯流程：這筆紀錄本來就只會是 food 或 water 其中一種，用「刪除舊列＋新增」達成更新。
        body.delete_diet_log(db, diet_id)
    if water_ml is not None:
        body.create_diet_log(db, target_user_id, "water", "飲水", diet_date, water_ml=water_ml)
        saved.append("飲水")
    if description is not None:
        body.create_diet_log(db, target_user_id, "food", description, diet_date, macros=macros, nutrition_source=nutrition_source or "ai")
        saved.append("飲食")

    return f"OK，已經幫你記錄好了！這次記錄的{'、'.join(saved)}都存好囉！"


def start_diet_list(db: CloudSQLClient, user_id: int) -> tuple[str, dict]:
    """`diet:list`：列出最近的飲食/飲水紀錄，每一筆附「✏️ 編輯」「🗑 刪除」按鈕。"""
    logs = body.list_diet_logs(db, user_id)
    if not logs:
        return "目前還沒有任何飲食紀錄，可以按「➕ 新增」建立第一筆！", {
            "inline_keyboard": [[{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}]]
        }

    listing = body.format_diet_log_list(logs)
    buttons = [
        [
            {"text": f"✏️ 編輯 {index}", "callback_data": f"diet:edit:{item['id']}"},
            {"text": f"🗑 刪除 {index}", "callback_data": f"diet:delete:{item['id']}"},
        ]
        for index, item in enumerate(logs, start=1)
    ]
    buttons.append([{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}])
    return listing, {"inline_keyboard": buttons}


def start_diet_edit(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, diet_log_id: int) -> tuple[str, dict]:
    """「✏️ 編輯」：這筆紀錄本來就只會是 `food` 或 `water` 其中一種，不重問「要不要記另一項」，
    直接依 `entry_type` 跳進對應子流程；沿用原本的 `entry_date`，`diet_id` 帶著代表這是編輯。"""
    row = db.select("diet_logs", where="id = %s", params=(diet_log_id,), fetch_one=True)
    if row is None or row.get("user_id") != user_id:
        return "找不到這筆飲食紀錄，可能已經被刪除了。", {"inline_keyboard": [[{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}]]}

    base_state = {
        "target_user_id": user_id, "diet_date": row["entry_date"], "diet_id": diet_log_id,
        "water_ml": None, "food_description": None, "food_nutrition_source": None, "food_macros": None,
    }
    if row["entry_type"] == "water":
        state_store.set(telegram_user_id, {**base_state, "flow": "pending_diet_water_amount"})
        return "好的，那我們重新輸入一次，這次喝了多少毫升的水呢？", None

    state_store.set(telegram_user_id, {**base_state, "flow": "pending_diet_food_input_mode"})
    return "好的，那我們重新輸入一次，食物內容要用文字輸入還是傳照片呢？", {
        "inline_keyboard": [[{"text": "📝 文字", "callback_data": "diet:food_text"}, {"text": "📷 照片", "callback_data": "diet:food_photo"}]]
    }


def start_diet_delete_confirm(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, diet_log_id: int) -> tuple[str, dict]:
    row = db.select("diet_logs", where="id = %s", params=(diet_log_id,), fetch_one=True)
    if row is None or row.get("user_id") != user_id:
        return "找不到這筆飲食紀錄，可能已經被刪除了。", {"inline_keyboard": [[{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}]]}

    state_store.set(telegram_user_id, {"flow": "diet_delete_confirm", "diet_log_id": diet_log_id})
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ 確認刪除", "callback_data": f"diet:confirm_delete:{diet_log_id}"}],
            [{"text": "❌ 取消", "callback_data": "diet:list"}],
        ]
    }
    return "確定要刪除這筆飲食紀錄嗎？這個動作沒辦法復原喔！", keyboard


def handle_diet_delete(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, diet_log_id: int) -> str:
    """`diet:confirm_delete:<id>` 觸發時重新驗證擁有者（理由同 `handle_exercise_delete`）。"""
    state_store.clear(telegram_user_id)
    row = db.select("diet_logs", where="id = %s", params=(diet_log_id,), fetch_one=True)
    if row is None or row.get("user_id") != user_id:
        return "找不到這筆飲食紀錄，可能已經被刪除了。"
    body.delete_diet_log(db, diet_log_id)
    return "好的，已經刪除這筆飲食紀錄了！"


def handle_diet_confirm_text(state_store: ConversationStateStore, telegram_user_id: int) -> tuple[str, dict]:
    """`pending_diet_confirm`／`diet_delete_confirm` 只接受按鈕操作，理由同
    `handle_exercise_confirm_text`。"""
    state_store.clear(telegram_user_id)
    keyboard = {"inline_keyboard": [[{"text": "🔙 返回日常紀錄", "callback_data": "menu:daily_log"}]]}
    return "這個步驟請用上面的按鈕操作喔，這次先幫你取消了。", keyboard


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
    不需要）後正式寫入目標。

    2026-08-05 起（見 FR-66c、ADR-17）：只有講清楚期限的目標才有意義同步到 Calendar（沒有日期就
    沒有事件可以建），所以只有 `target_date` 不是 `None` 時才多問一輪「要不要同步」
    （`pending_goal_calendar_sync`）；沒有期限的目標維持原本行為，這一步就直接寫入。
    """
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

    if target_date is not None:
        state_store.set(
            telegram_user_id,
            {
                "flow": "pending_goal_calendar_sync",
                "target_user_id": target_user_id,
                "goal_type": goal_type,
                "target_description": target_description,
                "target_value": target_value,
                "baseline_value": baseline_value,
                "target_date": target_date,
            },
        )
        return "好的！最後想問一下，這個目標要不要同步到 Google 家庭行事曆呢？（家人會在自己手機上看到）"

    state_store.clear(telegram_user_id)
    body.create_goal(db, target_user_id, goal_type, target_description, target_value, baseline_value, target_date)
    return f"好的，已經幫你記錄目標「{target_description}」了，加油！"


def handle_goal_calendar_sync_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
    calendar_client=None,
) -> str:
    """處理 `pending_goal_calendar_sync` 狀態下使用者對「要不要同步到 Google 家庭行事曆」的回覆，
    這一步才真正寫入 `body_goals`（FR-66c、ADR-17），只有有期限的目標才會走到這一步。

    同步失敗（`calendar_client` 為 `None` 或 API 例外）優雅降級，理由與
    `commands.handle_todo_calendar_sync_step()` 一致：目標本身已成功記錄，只是不會出現在
    Calendar 上，不把技術細節暴露給使用者，只記警告 log。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    goal_type = state["goal_type"]
    target_description = state["target_description"]
    target_value = state["target_value"]
    baseline_value = state["baseline_value"]
    target_date = state["target_date"]
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_TODO_CALENDAR_SYNC_PROMPT.format(text=text)).strip()
    sync_to_calendar = decision == "CONFIRM"

    goal_id = body.create_goal(
        db, target_user_id, goal_type, target_description, target_value, baseline_value, target_date,
        sync_to_calendar=sync_to_calendar,
    )

    if sync_to_calendar and calendar_client is not None:
        try:
            event_id = calendar_client.create_event(
                summary=target_description,
                start=target_date.isoformat(),
                end=(target_date + timedelta(days=1)).isoformat(),
                description="來自 Robinson 體態目標",
                all_day=True,
            )
            body.set_calendar_event_id(db, goal_id, event_id)
        except Exception:
            _logger.exception(
                "體態目標（id=%s）同步到 Google Calendar 失敗，目標本身已成功記錄不受影響", goal_id
            )

    return f"好的，已經幫你記錄目標「{target_description}」了，期限是 {target_date:%Y/%m/%d}，加油！"


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


def handle_goal_list_action_step(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    """處理 `pending_goal_list_action` 狀態下使用者輸入的編號，選定要取消的那個目標。

    2026-08-05 起（見 FR-66c、ADR-17）：`db` 改為必要參數，多查一次該筆目標的
    `google_calendar_event_id`，供下一步取消時判斷要不要刪除對應 Calendar 事件。
    """
    state = state_store.get(telegram_user_id)
    if text in _EXIT_PHRASES:
        state_store.clear(telegram_user_id)
        return "好的，已結束體態目標查詢模式！"

    ids = state["goal_ids"]
    if not text.isdigit() or not (1 <= int(text) <= len(ids)):
        return f"請輸入 1～{len(ids)} 之間的編號，或輸入「結束」離開喔！"

    goal_id = ids[int(text) - 1]
    row = db.select("body_goals", where="id = %s", params=(goal_id,), fetch_one=True)
    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_goal_cancel_confirm",
            "goal_id": goal_id,
            "google_calendar_event_id": row.get("google_calendar_event_id") if row else None,
        },
    )
    return "確定要取消這個體態目標嗎？"


def handle_goal_cancel_confirm_step(
    db: CloudSQLClient,
    llm_client,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
    calendar_client=None,
) -> str:
    """處理 `pending_goal_cancel_confirm` 狀態下使用者對取消確認的回覆（簡單一輪 CONFIRM/CANCEL）。

    2026-08-05 起（見 FR-66c、ADR-17）：如果這個目標當初有同步到 Calendar，取消時一併刪除對應
    事件，見 `body.cancel_goal()`。
    """
    state = state_store.get(telegram_user_id)
    goal_id = state["goal_id"]
    google_calendar_event_id = state.get("google_calendar_event_id")
    state_store.clear(telegram_user_id)

    decision = llm_client.generate_text(_GOAL_CANCEL_CONFIRM_PROMPT.format(text=text)).strip()
    if decision != "CONFIRM":
        return "好的，這個體態目標保留，沒有取消！"

    body.cancel_goal(
        db, goal_id, calendar_client=calendar_client, google_calendar_event_id=google_calendar_event_id
    )
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


# ---------------------------------------------------------------------------
# 證照題庫作答與彈性排程調整（2026-08-08 追加，Step 3.3，見 robinson SPEC.md FR-27、FR-28、
# FR-26、ADR-20 決策 3～6）
#
# - 作答：「開始作答」／`/start_quiz`，一次一題（依序作答，答完才給下一題，經 Robin 確認）；
#   只接受回覆 A/B/C/D，格式不符原地反問（決策 3）；跨多個 exam_type 依序做完一個再做下一個
#   （`certificate_answer.get_pending_assignments()` 已依 exam_type 排序）。
# - 彈性排程調整：「調整出題排程」／`/adjust_quiz_schedule`，先選 exam_type（只有一個時跳過這
#   一題）→ 自由描述想怎麼調整 → LLM 分類成四種語意之一（MOVE／CANCEL／RANGE／SPREAD，經 Robin
#   確認採 LLM 判斷語意而非固定指令）。前三種語意是使用者已經明確下的指令，直接套用不需要額外
#   確認；SPREAD（平攤）語意需要先算出提案、列出「幾月幾號各要多幾題」給 Robin 確認，同意才寫
#   入，有調整意見（例如指定想攤成幾天）則依建議重算再次確認，直到 Robin 同意或取消為止（經
#   Robin 明確要求，見 ADR-20 決策 5④、6）。
# ---------------------------------------------------------------------------

_QUIZ_ANSWER_FORMAT_REPROMPT = "請回覆 A、B、C 或 D 其中一個字母喔："
_QUIZ_NO_PENDING_QUESTIONS_REPLY = "目前沒有題目待作答喔！"

_QUIZ_SCHEDULE_NO_EXAM_TYPE_REPLY = "目前題庫裡還沒有任何有正解的題目，沒有可以調整的排程喔。"
_QUIZ_SCHEDULE_EXAM_TYPE_ASK_TEMPLATE = "你目前有多個證照題庫，這次要調整哪一個的出題排程呢？請輸入編號：\n{options}"
_QUIZ_SCHEDULE_INVALID_INDEX_REPLY = "不好意思，麻煩輸入清單裡的編號喔："
_QUIZ_SCHEDULE_INTENT_ASK = (
    "好的，今天的題目你想怎麼調整呢？可以直接跟我說，例如：\n"
    "・改到別天（例如：今天不想做，改明天）\n"
    "・直接取消今天的\n"
    "・某個時間區間的每日題數要改成幾題\n"
    "・平攤到最近幾天"
)
_QUIZ_SCHEDULE_UNCLEAR_REPLY = "不好意思，我還是不太確定你想怎麼調整，可以再講清楚一點嗎？"
_QUIZ_SCHEDULE_INVALID_DATE_REPLY = "這個日期好像不是未來的日期喔，麻煩再確認一次告訴我要改到哪一天："
_QUIZ_SCHEDULE_INVALID_RANGE_REPLY = "不好意思，我沒有完全聽懂區間跟題數，可以再講清楚一點嗎？（例如：8/10 到 8/15 每天改成 3 題）"
_QUIZ_SCHEDULE_SPREAD_UNCLEAR_REPLY = "不好意思，我還是不太確定，你可以回覆「OK」同意這個方案，或直接跟我說想怎麼調整（例如攤成幾天）："
_QUIZ_SCHEDULE_SPREAD_INVALID_DAYS_REPLY = "不好意思，我沒聽懂你想攤成幾天，可以再講一次嗎？（例如：攤成 3 天）"

_QUIZ_SCHEDULE_INTENT_CLASSIFY_PROMPT = (
    "使用者正在調整證照題庫每日出題排程，Robinson 剛反問「今天的題目你想怎麼調整？」，這是使用者"
    "這一則的回覆：「{text}」。\n"
    "【現在的日期（台灣時區，計算相對日期時一律以此為準）】\n{current_date_text}\n\n"
    "請判斷使用者想要下面五種語意中的哪一種，並嚴格照下面格式輸出，每個欄位各自一行，"
    "不要輸出其他任何文字：\n"
    "INTENT: MOVE（今天的題目整批挪到指定的某一天）／CANCEL（今天的題目直接取消，不補不挪）／"
    "RANGE（某個日期區間的每日出題數量改成 N 題）／SPREAD（今天的題目平攤到接下來幾天，"
    "使用者不需要自己講出要攤幾天或哪幾天，這是 Robinson 自己算的）／UNCLEAR（看不出來、"
    "或講的是其他事情）\n"
    "MOVE_DATE: 若為 MOVE，目標日期，格式 YYYY-MM-DD（其他情況可省略）\n"
    "RANGE_START: 若為 RANGE，區間起始日期，格式 YYYY-MM-DD（其他情況可省略）\n"
    "RANGE_END: 若為 RANGE，區間結束日期，格式 YYYY-MM-DD（其他情況可省略）\n"
    "RANGE_COUNT: 若為 RANGE，每日題數，純數字（其他情況可省略）"
)
_QUIZ_SCHEDULE_SPREAD_CONFIRM_CLASSIFY_PROMPT = (
    "使用者剛看到 Robinson 算出來的「平攤方案」提案（把今天的題目分攤到接下來幾天），這是使用者"
    "這一則的回覆：「{text}」。\n"
    "請判斷使用者的意思，並嚴格照下面格式輸出，每個欄位各自一行，不要輸出其他任何文字：\n"
    "STATUS: CONFIRM（同意這個方案）／CANCEL（不想調整了，取消這次操作）／"
    "CUSTOM_DAYS（明確講出想攤成幾天，不是目前這個方案的天數）／UNCLEAR（看不懂、或想法還不明確）\n"
    "DAYS: 若為 CUSTOM_DAYS，使用者想要攤成的天數，純數字（其他情況可省略）"
)


# --- 作答 ---


def _parse_answer_letter(text: str) -> str | None:
    """只接受 A/B/C/D（大小寫皆可），不用 LLM 解析口語化回答（ADR-20 決策 3）。"""
    cleaned = text.strip().upper()
    return cleaned if cleaned in ("A", "B", "C", "D") else None


def _present_current_quiz_question(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int) -> str:
    """呈現目前佇列位置的題目；資料異常（`certificate_answer.build_question_view()` 回傳
    `None`，理論上不該發生，是最後一道防線）或題目已被刪除（例如透過排程調整流程被取消）時自動
    跳過，找下一題；全部跑完就清除狀態並回覆完成訊息。"""
    state = state_store.get(telegram_user_id)
    assignment_ids = state["assignment_ids"]
    total = len(assignment_ids)
    position = state["position"]

    while position < total:
        assignment_id = assignment_ids[position]
        assignment = db.select(
            "certificate_daily_assignments", where="id = %s", params=(assignment_id,), fetch_one=True
        )
        view = certificate_answer.build_question_view(db, assignment) if assignment else None
        if view is not None:
            state["position"] = position
            state["current_view"] = view
            state_store.set(telegram_user_id, state)
            return certificate_answer.format_question_prompt(view, position + 1, total)
        if assignment is None:
            _logger.warning("assignment id=%s 在作答流程中已不存在，跳過", assignment_id)
        else:
            _logger.warning("assignment id=%s 對應的題目資料異常（正解無法解析），跳過", assignment_id)
        position += 1

    state_store.clear(telegram_user_id)
    return certificate_answer.ALL_DONE_MESSAGE


def start_quiz_answer(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「開始作答」／`/start_quiz`：依序作答目前所有待作答的題目（FR-27，一次一題）。"""
    pending = certificate_answer.get_pending_assignments(db, user_id)
    if not pending:
        return _QUIZ_NO_PENDING_QUESTIONS_REPLY

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_quiz_answer", "target_user_id": user_id,
            "assignment_ids": [row["id"] for row in pending], "position": 0, "current_view": None,
        },
    )
    return _present_current_quiz_question(db, state_store, telegram_user_id)


def handle_quiz_answer_step(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_quiz_answer` 狀態下使用者的作答回覆；只接受 A/B/C/D，格式不符原地反問，
    不清除狀態、也不算跳題（ADR-20 決策 3）。"""
    state = state_store.get(telegram_user_id)
    letter = _parse_answer_letter(text)
    if letter is None:
        return _QUIZ_ANSWER_FORMAT_REPROMPT

    assignment_ids = state["assignment_ids"]
    position = state["position"]
    assignment_id = assignment_ids[position]
    assignment = db.select(
        "certificate_daily_assignments", where="id = %s", params=(assignment_id,), fetch_one=True
    )
    view = state.get("current_view")
    if view is None and assignment is not None:
        view = certificate_answer.build_question_view(db, assignment)

    if assignment is None or view is None:
        # 這題在呈現之後、作答之前被刪除或資料異常（例如透過排程調整流程被取消），跳過這題。
        state["position"] = position + 1
        state_store.set(telegram_user_id, state)
        return _present_current_quiz_question(db, state_store, telegram_user_id)

    is_correct = certificate_answer.grade_answer(letter, view)
    certificate_answer.record_answer(db, state["target_user_id"], assignment, view, is_correct, _now().date())
    feedback = certificate_answer.format_grading_feedback(is_correct, view)

    state["position"] = position + 1
    state_store.set(telegram_user_id, state)
    next_prompt = _present_current_quiz_question(db, state_store, telegram_user_id)
    return f"{feedback}\n\n{next_prompt}"


# --- 彈性排程調整 ---


def start_quiz_schedule_adjust(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「調整出題排程」／`/adjust_quiz_schedule`：開始彈性排程調整流程（FR-26 決策 5）。"""
    exam_types = certificate_quiz.distinct_exam_types_with_questions(db)
    if not exam_types:
        return _QUIZ_SCHEDULE_NO_EXAM_TYPE_REPLY

    if len(exam_types) == 1:
        state_store.set(
            telegram_user_id,
            {"flow": "pending_quiz_schedule_intent", "target_user_id": user_id, "exam_type": exam_types[0]},
        )
        return _QUIZ_SCHEDULE_INTENT_ASK

    state_store.set(
        telegram_user_id,
        {"flow": "pending_quiz_schedule_exam_type_choice", "target_user_id": user_id, "exam_type_options": exam_types},
    )
    options_text = "\n".join(f"{i}. {exam_type}" for i, exam_type in enumerate(exam_types, start=1))
    return _QUIZ_SCHEDULE_EXAM_TYPE_ASK_TEMPLATE.format(options=options_text)


def handle_quiz_schedule_exam_type_choice_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_quiz_schedule_exam_type_choice` 狀態下使用者選擇的 exam_type 編號。"""
    state = state_store.get(telegram_user_id)
    options = state["exam_type_options"]
    cleaned = text.strip()
    if not cleaned.isdigit() or not (1 <= int(cleaned) <= len(options)):
        return _QUIZ_SCHEDULE_INVALID_INDEX_REPLY

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_quiz_schedule_intent", "target_user_id": state["target_user_id"],
            "exam_type": options[int(cleaned) - 1],
        },
    )
    return _QUIZ_SCHEDULE_INTENT_ASK


def handle_quiz_schedule_intent_step(
    db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    """處理 `pending_quiz_schedule_intent` 狀態下使用者對「今天的題目你想怎麼調整？」的自由描述
    回覆，用 LLM 分類成四種語意之一（見模組 docstring）。MOVE／CANCEL／RANGE 直接套用；SPREAD
    需要先算提案進入 `pending_quiz_schedule_spread_confirm` 等待確認。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    exam_type = state["exam_type"]
    today = _now().date()

    parsed = _parse_key_value_block(
        llm_client.generate_text(
            _QUIZ_SCHEDULE_INTENT_CLASSIFY_PROMPT.format(text=text, current_date_text=_current_date_text())
        )
    )
    intent = parsed.get("INTENT", "UNCLEAR")

    if intent == "CANCEL":
        certificate_schedule.apply_cancel(db, target_user_id, exam_type, today)
        state_store.clear(telegram_user_id)
        return f"好的，已經取消今天「{exam_type}」的題目囉，不補也不挪。"

    if intent == "MOVE":
        target_date = _parse_date_only(parsed.get("MOVE_DATE", ""))
        if target_date is None or target_date <= today:
            return _QUIZ_SCHEDULE_INVALID_DATE_REPLY
        certificate_schedule.apply_move(db, target_user_id, exam_type, today, target_date)
        state_store.clear(telegram_user_id)
        return f"好的，已經把今天「{exam_type}」的題目挪到 {target_date.month}/{target_date.day} 囉！"

    if intent == "RANGE":
        start = _parse_date_only(parsed.get("RANGE_START", ""))
        end = _parse_date_only(parsed.get("RANGE_END", ""))
        count_raw = parsed.get("RANGE_COUNT", "").strip()
        if start is None or end is None or start > end or not count_raw.isdigit():
            return _QUIZ_SCHEDULE_INVALID_RANGE_REPLY
        count = int(count_raw)
        certificate_schedule.apply_range_override(db, target_user_id, exam_type, today, start, end, count)
        state_store.clear(telegram_user_id)
        return f"好的，{start.month}/{start.day} 到 {end.month}/{end.day} 這段期間「{exam_type}」每天的出題數量已經改成 {count} 題囉！"

    if intent == "SPREAD":
        plan = certificate_schedule.compute_spread_plan(db, target_user_id, exam_type, today)
        state_store.set(
            telegram_user_id,
            {
                "flow": "pending_quiz_schedule_spread_confirm", "target_user_id": target_user_id,
                "exam_type": exam_type, "plan": plan,
            },
        )
        return certificate_schedule.format_spread_proposal(plan)

    return _QUIZ_SCHEDULE_UNCLEAR_REPLY


def handle_quiz_schedule_spread_confirm_step(
    db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    """處理 `pending_quiz_schedule_spread_confirm` 狀態下使用者對「平攤方案」提案的回覆
    （ADR-20 決策 5④、6）：同意才真正寫入；有調整意見（目前支援明確講出想攤成幾天）則依建議
    重算，再次列出方案等待確認，反覆直到 Robin 同意或取消為止。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    exam_type = state["exam_type"]
    plan = state["plan"]
    today = _now().date()

    parsed = _parse_key_value_block(
        llm_client.generate_text(_QUIZ_SCHEDULE_SPREAD_CONFIRM_CLASSIFY_PROMPT.format(text=text))
    )
    status = parsed.get("STATUS", "UNCLEAR")

    if status == "CONFIRM":
        certificate_schedule.apply_spread_plan(db, target_user_id, exam_type, today, plan)
        state_store.clear(telegram_user_id)
        return "好的，已經照這個方案分攤完成囉！"

    if status == "CANCEL":
        state_store.clear(telegram_user_id)
        return "好的，那這次先不調整。"

    if status == "CUSTOM_DAYS":
        days_raw = parsed.get("DAYS", "").strip()
        if not days_raw.isdigit() or int(days_raw) <= 0:
            return _QUIZ_SCHEDULE_SPREAD_INVALID_DAYS_REPLY
        new_plan = certificate_schedule.compute_spread_plan(
            db, target_user_id, exam_type, today, num_days=int(days_raw)
        )
        state["plan"] = new_plan
        state_store.set(telegram_user_id, state)
        return certificate_schedule.format_spread_proposal(new_plan)

    return _QUIZ_SCHEDULE_SPREAD_UNCLEAR_REPLY


# ---------------------------------------------------------------------------
# 證照題庫成效問答、目標設定與正式成績（2026-08-08 追加，Step 3.3 剩餘範圍，見 robinson SPEC.md
# FR-29、FR-24、FR-30、ADR-19）
#
# - FR-30 正式成績：「我要記錄正式成績」／「我的正式成績」，資料表 `exam_official_scores`
#   （0042 migration，已存在）。查詢只做列表，不含修改／刪除（2026-08-08 經 AskUserQuestion 與
#   Robin 確認範圍：正式成績是「考完就定案」的歷史紀錄，不像體重/記帳需要常態修正，先求簡單）。
# - FR-24 目標設定與方向建議：「設定證照目標」／「我的證照目標」／「給我讀書建議」，資料表
#   `certificate_goals`（0041 migration，已存在，UPSERT，重新設定即覆蓋）；方向建議依近 30 天
#   FR-29 統計出的成效與目標時間長短，用 LLM 生成客製化文字，不走固定範本。
# - FR-29 成效彈性文字問答：「查詢我的成效」，多輪對話直到 exam_type／正式-小考/期間都夠清楚為止
#   ——每輪把使用者已經講過的內容全部疊加起來重新丟給 LLM 解析（而非死板的單欄位反問），讓使用者
#   可以一次講清楚也可以分次補充；不做圖表（ADR-19 決策 4，圖表統一交給 Phase 4 App FR-64）。
# ---------------------------------------------------------------------------

_CERTIFICATE_ADVICE_LOOKBACK_DAYS = 30

_SKIP_KEYWORDS = {"跳過", "不確定", "不知道", "沒有", "沒想法", "無"}


def _is_skip_reply(text: str) -> bool:
    return text.strip() in _SKIP_KEYWORDS


def _certificate_exam_type_candidates(db: CloudSQLClient, user_id: int) -> list[str]:
    """回傳這個使用者目前跟證照相關的所有已知 `exam_type`（題庫、作答紀錄、正式成績、既有目標
    四個來源聯集），供「這是哪個證照類型」反問時列出候選清單。"""
    candidates = set(certificate_quiz.distinct_exam_types_with_questions(db))
    candidates |= set(certificate_stats.known_exam_types(db, user_id))
    candidates |= {row["exam_type"] for row in certificate_goals.list_goals(db, user_id)}
    candidates |= set(certificate_exam_scores.distinct_exam_types(db, user_id))
    return sorted(candidates)


def _exam_type_ask_text(candidates: list[str]) -> str:
    if not candidates:
        return "這是哪一個證照類型呢？（例如 toeic、gcp，直接輸入名稱即可）："
    options_text = "\n".join(f"{i}. {c}" for i, c in enumerate(candidates, start=1))
    return f"這是哪一個證照類型呢？可以輸入編號，或直接輸入證照類型名稱：\n{options_text}"


def _resolve_exam_type_input(options: list[str], text: str) -> str | None:
    """把使用者輸入換算成 `exam_type`：清單裡的編號直接對應；其他任何非空文字視為使用者自行輸入
    的證照類型名稱（統一轉小寫比對，因為既有 `exam_type` 皆為小寫字串，見 SPEC.md ADR-18 決策
    4）。完全空白（或無法辨識）回傳 `None`。"""
    cleaned = text.strip()
    if not cleaned:
        return None
    if options and cleaned.isdigit() and 1 <= int(cleaned) <= len(options):
        return options[int(cleaned) - 1]
    return cleaned.lower()


_CERTIFICATE_DATE_PARSE_PROMPT = (
    "使用者正在{context}，這是使用者這一則的回覆：「{date_reply}」。\n"
    "【現在的日期（台灣時區，計算相對日期時一律以此為準）】\n{current_date_text}\n\n"
    "請判斷使用者是否已經講清楚明確的日期，並嚴格照下面格式輸出，每個欄位各自一行，"
    "不要輸出其他任何文字：\n"
    "STATUS: CLEAR 或 UNCLEAR。使用者必須明確講出是哪一天（例如「昨天」「8/1」「2026-12-01」"
    "「明年 3 月」都算明確；只要含糊、沒有講清楚是哪一天，一律填 UNCLEAR，絕對不可以自己亂猜。\n"
    "DATE: 換算後的日期，格式一律為 YYYY-MM-DD（STATUS 為 UNCLEAR 時可省略）"
)
_CERTIFICATE_DATE_UNCLEAR_REPLY = "不好意思，我還是不太確定日期，可以再講清楚一點嗎？"


# --- FR-30：正式成績 ---


def start_log_exam_score(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int
) -> str:
    """「我要記錄正式成績」／`/log_exam_score`：開始記錄正式應考成績流程（FR-30）。"""
    candidates = _certificate_exam_type_candidates(db, user_id)
    state_store.set(
        telegram_user_id,
        {"flow": "pending_exam_score_exam_type", "target_user_id": user_id, "exam_type_options": candidates},
    )
    return _exam_type_ask_text(candidates)


def handle_exam_score_exam_type_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    state = state_store.get(telegram_user_id)
    exam_type = _resolve_exam_type_input(state["exam_type_options"], text)
    if exam_type is None:
        return "不好意思，我沒看懂，麻煩再告訴我一次證照類型："

    state_store.set(
        telegram_user_id,
        {"flow": "pending_exam_score_date", "target_user_id": state["target_user_id"], "exam_type": exam_type},
    )
    return "這次應考是什麼時候呢？可以直接告訴我日期（例如：8/1、2026-08-01）："


def handle_exam_score_date_step(
    db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    state = state_store.get(telegram_user_id)
    parsed = _parse_key_value_block(
        llm_client.generate_text(
            _CERTIFICATE_DATE_PARSE_PROMPT.format(
                context="記錄正式應考日期", date_reply=text, current_date_text=_current_date_text()
            )
        )
    )
    if parsed.get("STATUS") != "CLEAR":
        return _CERTIFICATE_DATE_UNCLEAR_REPLY

    exam_date = _parse_date_only(parsed.get("DATE", ""))
    if exam_date is None:
        return _CERTIFICATE_DATE_UNCLEAR_REPLY

    state["flow"] = "pending_exam_score_value"
    state["exam_date"] = exam_date
    state_store.set(telegram_user_id, state)
    return "這次的成績或結果是？（例如：850 分、通過）："


def handle_exam_score_value_step(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    score = text.strip()
    if not score:
        return "不好意思，我沒看懂成績，麻煩再告訴我一次："

    state = state_store.get(telegram_user_id)
    certificate_exam_scores.record_score(db, state["target_user_id"], state["exam_type"], state["exam_date"], score)
    state_store.clear(telegram_user_id)

    exam_date = state["exam_date"]
    return f"已經幫你記錄「{state['exam_type']}」{exam_date.year}/{exam_date.month}/{exam_date.day} 的正式成績：{score} 囉！"


def handle_my_exam_scores(db: CloudSQLClient, user_id: int) -> str:
    """「我的正式成績」／`/my_exam_scores`：列出所有正式應考紀錄，不分證照類型一次列完
    （2026-08-08 經 AskUserQuestion 與 Robin 確認本次只做查詢列表，不含修改／刪除）。"""
    rows = certificate_exam_scores.list_scores(db, user_id)
    return certificate_exam_scores.format_scores_summary(None, rows)


# --- FR-24：目標設定 ---


def start_set_certificate_goal(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int
) -> str:
    """「設定證照目標」／`/set_certificate_goal`：開始設定證照準備目標流程（FR-24）。"""
    candidates = _certificate_exam_type_candidates(db, user_id)
    state_store.set(
        telegram_user_id,
        {"flow": "pending_certificate_goal_exam_type", "target_user_id": user_id, "exam_type_options": candidates},
    )
    return _exam_type_ask_text(candidates)


def handle_certificate_goal_exam_type_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    state = state_store.get(telegram_user_id)
    exam_type = _resolve_exam_type_input(state["exam_type_options"], text)
    if exam_type is None:
        return "不好意思，我沒看懂，麻煩再告訴我一次證照類型："

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_certificate_goal_target_date", "target_user_id": state["target_user_id"],
            "exam_type": exam_type,
        },
    )
    return "這個證照的目標考試時間是什麼時候呢？可以直接告訴我日期（例如：12/1、2026-12-01），不確定的話也可以回覆「跳過」："


def handle_certificate_goal_target_date_step(
    db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    state = state_store.get(telegram_user_id)
    if _is_skip_reply(text):
        target_date = None
    else:
        parsed = _parse_key_value_block(
            llm_client.generate_text(
                _CERTIFICATE_DATE_PARSE_PROMPT.format(
                    context="設定證照準備目標的考試時間", date_reply=text, current_date_text=_current_date_text()
                )
            )
        )
        if parsed.get("STATUS") != "CLEAR":
            return f"{_CERTIFICATE_DATE_UNCLEAR_REPLY}（不確定的話也可以回覆「跳過」）"
        target_date = _parse_date_only(parsed.get("DATE", ""))
        if target_date is None:
            return f"{_CERTIFICATE_DATE_UNCLEAR_REPLY}（不確定的話也可以回覆「跳過」）"

    state["flow"] = "pending_certificate_goal_target_score"
    state["target_date"] = target_date
    state_store.set(telegram_user_id, state)
    return "目標分數或成績是？（例如：850 分、通過就好，不確定的話也可以回覆「跳過」）："


def handle_certificate_goal_target_score_step(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    state = state_store.get(telegram_user_id)
    if _is_skip_reply(text):
        target_score = None
    else:
        cleaned = text.strip()
        if not cleaned:
            return "不好意思，我沒看懂，麻煩再告訴我一次（或回覆「跳過」）："
        target_score = cleaned

    result = certificate_goals.set_goal(db, state["target_user_id"], state["exam_type"], state["target_date"], target_score)
    state_store.clear(telegram_user_id)
    return certificate_goals.format_goal_set_reply(state["exam_type"], result)


def handle_my_certificate_goals(db: CloudSQLClient, user_id: int) -> str:
    """「我的證照目標」／`/my_certificate_goals`：列出目前設定的所有證照準備目標（FR-24）。"""
    return certificate_goals.format_goals_summary(certificate_goals.list_goals(db, user_id))


# --- FR-24：方向建議 ---


def _generate_certificate_advice(db: CloudSQLClient, llm_client, user_id: int, exam_type: str) -> str:
    today = _now().date()
    goal = certificate_goals.get_goal(db, user_id, exam_type)
    period_start = today - timedelta(days=_CERTIFICATE_ADVICE_LOOKBACK_DAYS - 1)
    stats = certificate_stats.compute_daily_period_stats(db, user_id, exam_type, period_start, today)
    prompt = certificate_goals.build_advice_prompt(exam_type, goal, stats, today)
    advice = llm_client.generate_text(prompt).strip()
    return f"💡 「{exam_type}」讀書建議\n\n{advice}"


def start_certificate_advice(
    db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, user_id: int
) -> str:
    """「給我讀書建議」／`/certificate_advice`：依近 30 天成效與目標，用 LLM 生成方向建議（FR-24）。"""
    candidates = _certificate_exam_type_candidates(db, user_id)
    if not candidates:
        return "目前還沒有任何證照相關資料，等有題庫或成績紀錄後我再幫你分析方向建議喔！"

    if len(candidates) == 1:
        return _generate_certificate_advice(db, llm_client, user_id, candidates[0])

    state_store.set(
        telegram_user_id,
        {"flow": "pending_certificate_advice_exam_type", "target_user_id": user_id, "exam_type_options": candidates},
    )
    return _exam_type_ask_text(candidates)


def handle_certificate_advice_exam_type_step(
    db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    state = state_store.get(telegram_user_id)
    exam_type = _resolve_exam_type_input(state["exam_type_options"], text)
    if exam_type is None:
        return "不好意思，我沒看懂，麻煩再告訴我一次證照類型："

    state_store.clear(telegram_user_id)
    return _generate_certificate_advice(db, llm_client, state["target_user_id"], exam_type)


# --- FR-29：成效彈性文字問答 ---

_QUIZ_STATS_INITIAL_ASK = (
    "想問哪方面的成效呢？直接跟我說就可以了，例如：\n"
    "・上週答對幾題\n"
    "・這個月 TOEIC 平均正確率\n"
    "・這次跟上次模考成績比較一下"
)
_QUIZ_STATS_NO_DATA_REPLY = "目前還沒有任何證照的作答或成績紀錄，沒有東西可以查詢喔！"
_QUIZ_STATS_UNCLEAR_REPLY = "不好意思，我還是不太確定你想問什麼，可以再講清楚一點嗎？"
_QUIZ_STATS_NEED_PERIOD_REPLY = "麻煩告訴我你想查詢的時間範圍喔（例如：上週、這個月、8/1 到 8/7）："
_QUIZ_STATS_NEED_SCOPE_REPLY = "你是想問正式測驗的成績，還是平常每日小考的作答成效呢？"

_QUIZ_STATS_PARSE_PROMPT = (
    "使用者正在查詢證照題庫的成效，這是使用者目前為止已經講過的內容（可能經過多輪反問，由上到下"
    "依序疊加）：\n「{text}」\n\n"
    "【目前有資料的證照類型】{known_exam_types}\n"
    "【現在的日期（台灣時區，計算相對日期時一律以此為準）】\n{current_date_text}\n\n"
    "請依序判斷以下四件事，只要有一件事不確定就整體判斷為對應的狀態（優先順序：先確認 "
    "①EXAM_TYPE，再確認 ②SCOPE，再確認 ③PERIOD，四件事都確定了才是 CLEAR）：\n"
    "① 使用者想查詢哪一種證照類型（EXAM_TYPE，必須是【目前有資料的證照類型】清單裡的其中一個；"
    "如果清單只有一種，直接視為那一種，不需要使用者特別講出名字；如果清單有多種、使用者沒有明確"
    "講出是哪一種、或提到的名字對不到清單裡任何一項，狀態填 NEED_EXAM_TYPE）\n"
    "② 使用者問的是「正式測驗成績」還是「平常每日小考的作答成效」（SCOPE：DAILY 或 FORMAL；沒有"
    "明確提到、無法判斷是哪一種，狀態填 NEED_SCOPE）\n"
    "③ 使用者想查詢的時間範圍（PERIOD_START／PERIOD_END；使用者完全沒有提到任何時間範圍、或講得"
    "含糊不清無法換算成明確的起訖日期，狀態填 NEED_PERIOD，絕對不可以自己猜一個預設範圍）\n"
    "④ 使用者是否想比較兩個時間區間（COMPARE：YES 或 NO；只有明確講出「比較」「跟...比」之類的"
    "意思，且能明確判斷出第二個時間區間時才填 YES，否則一律 NO；COMPARE 不影響 STATUS 判斷）\n\n"
    "請嚴格照下面格式輸出，每個欄位各自一行，不要輸出其他任何文字：\n"
    "STATUS: CLEAR／NEED_EXAM_TYPE／NEED_SCOPE／NEED_PERIOD／UNCLEAR"
    "（完全看不懂使用者在問什麼、或問的是無關的事情才填 UNCLEAR）\n"
    "EXAM_TYPE: 判斷出的證照類型（STATUS 為 CLEAR 時必填，其他情況可省略）\n"
    "SCOPE: DAILY 或 FORMAL（STATUS 為 CLEAR 時必填，其他情況可省略）\n"
    "PERIOD_START: 主要查詢區間起始日期，格式 YYYY-MM-DD（STATUS 為 CLEAR 時必填，其他情況可省略）\n"
    "PERIOD_END: 主要查詢區間結束日期，格式 YYYY-MM-DD（STATUS 為 CLEAR 時必填，其他情況可省略）\n"
    "COMPARE: YES 或 NO（STATUS 為 CLEAR 時必填，其他情況可省略）\n"
    "COMPARE_START: 若 COMPARE 為 YES，對照區間起始日期，格式 YYYY-MM-DD（其他情況可省略）\n"
    "COMPARE_END: 若 COMPARE 為 YES，對照區間結束日期，格式 YYYY-MM-DD（其他情況可省略）"
)


def start_quiz_stats_query(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int
) -> str:
    """「查詢我的成效」／`/my_quiz_stats`：開始成效彈性文字問答流程（FR-29）。"""
    known_types = certificate_stats.known_exam_types(db, user_id)
    if not known_types:
        return _QUIZ_STATS_NO_DATA_REPLY

    state_store.set(telegram_user_id, {"flow": "pending_quiz_stats_query", "target_user_id": user_id, "history": []})
    return _QUIZ_STATS_INITIAL_ASK


def handle_quiz_stats_query_step(
    db: CloudSQLClient, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    """處理 `pending_quiz_stats_query` 狀態下使用者的自由描述；每輪把使用者已經講過的內容全部
    疊加起來重新丟給 LLM 解析（而非死板的單欄位反問），讓使用者可以一次講清楚也可以分次補充
    exam_type／正式-小考／時間區間（見模組上方說明）。
    """
    state = state_store.get(telegram_user_id)
    target_user_id = state["target_user_id"]
    history = state["history"] + [text]

    known_types = certificate_stats.known_exam_types(db, target_user_id)
    if not known_types:
        state_store.clear(telegram_user_id)
        return _QUIZ_STATS_NO_DATA_REPLY

    known_exam_types_text = "、".join(known_types)
    parsed = _parse_key_value_block(
        llm_client.generate_text(
            _QUIZ_STATS_PARSE_PROMPT.format(
                text="\n".join(history), known_exam_types=known_exam_types_text, current_date_text=_current_date_text(),
            )
        )
    )
    status = parsed.get("STATUS", "UNCLEAR")

    state["history"] = history
    state_store.set(telegram_user_id, state)

    if status == "NEED_EXAM_TYPE":
        return f"你是想問哪個證照的成效呢？目前有資料的有：{known_exam_types_text}"
    if status == "NEED_SCOPE":
        return _QUIZ_STATS_NEED_SCOPE_REPLY
    if status == "NEED_PERIOD":
        return _QUIZ_STATS_NEED_PERIOD_REPLY

    exam_type = parsed.get("EXAM_TYPE", "").strip()
    scope = parsed.get("SCOPE", "").strip().upper()
    period_start = _parse_date_only(parsed.get("PERIOD_START", "").strip())
    period_end = _parse_date_only(parsed.get("PERIOD_END", "").strip())

    if (
        status != "CLEAR"
        or exam_type not in known_types
        or scope not in ("DAILY", "FORMAL")
        or period_start is None
        or period_end is None
        or period_start > period_end
    ):
        return _QUIZ_STATS_UNCLEAR_REPLY

    if scope == "FORMAL":
        rows = certificate_stats.compute_formal_period_scores(db, target_user_id, exam_type, period_start, period_end)
        reply = certificate_stats.format_formal_period_summary(exam_type, period_start, period_end, rows)
    else:
        stats = certificate_stats.compute_daily_period_stats(db, target_user_id, exam_type, period_start, period_end)
        compare = parsed.get("COMPARE", "NO").strip().upper() == "YES"
        compare_start = _parse_date_only(parsed.get("COMPARE_START", "").strip())
        compare_end = _parse_date_only(parsed.get("COMPARE_END", "").strip())
        if compare and compare_start is not None and compare_end is not None and compare_start <= compare_end:
            stats_b = certificate_stats.compute_daily_period_stats(db, target_user_id, exam_type, compare_start, compare_end)
            reply = certificate_stats.format_daily_period_comparison(
                exam_type, (period_start, period_end), stats, (compare_start, compare_end), stats_b
            )
        else:
            reply = certificate_stats.format_daily_period_summary(exam_type, period_start, period_end, stats)

    state_store.clear(telegram_user_id)
    return reply


# --- Step 3.4（見 robinson SPEC.md FR-57a、ADR-21）：YouTube 技術情報主題管理 ---
#
# 三個 Owner 專屬指令：「我的YouTube主題」單次查詢（不經狀態機，設計比照
# handle_my_certificate_goals）；「新增YouTube主題」是單輪值輸入（設計比照 start_set_height／
# handle_height_value_step）；「移除YouTube主題」是「列清單→輸入編號→直接刪除」單輪，設計比照
# start_todo_list／handle_todo_list_action_step，但刪除主題屬於低風險、可隨時重新新增的操作，
# 不需要待辦事項刪除那種「先選完成/取消再進二次確認」的額外關卡，選到編號後直接刪除即可。


def handle_my_youtube_topics(db: CloudSQLClient, user_id: int) -> str:
    """「我的YouTube主題」／`/my_youtube_topics`：列出目前設定的所有 YouTube 技術情報主題（FR-57a）。"""
    return youtube.format_topics_list(youtube.list_topics(db, user_id))


def start_add_youtube_topic(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「新增YouTube主題」／`/add_youtube_topic`：開始新增一組主題（FR-57a）。"""
    state_store.set(telegram_user_id, {"flow": "pending_youtube_topic_add", "target_user_id": user_id})
    return "好的，請告訴我想訂閱的技術情報主題/關鍵字（例如：後端架構、AI Agent、DevOps）："


def handle_youtube_topic_add_step(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    """處理 `pending_youtube_topic_add` 狀態下使用者提供的主題文字；空白原地反問，不清除狀態。"""
    state = state_store.get(telegram_user_id)
    topic = text.strip()
    if not topic:
        return "不好意思，我沒看懂，麻煩告訴我一個主題/關鍵字喔！"

    target_user_id = state["target_user_id"]
    state_store.clear(telegram_user_id)
    result = youtube.add_topic(db, target_user_id, topic)
    if result["already_exists"]:
        return f"「{topic}」已經在你的主題清單裡囉，不用重複新增！"
    return f"好的，已經幫你新增主題「{topic}」，下週四開始會納入推播考量！"


def start_remove_youtube_topic(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int
) -> str:
    """「移除YouTube主題」／`/remove_youtube_topic`：列出目前主題並進入可輸入編號刪除的模式（FR-57a）。"""
    topics = youtube.list_topics(db, user_id)
    listing = youtube.format_topics_list(topics)
    if not topics:
        return listing

    state_store.set(
        telegram_user_id,
        {"flow": "pending_youtube_topic_remove", "target_user_id": user_id, "topic_ids": [t["id"] for t in topics]},
    )
    return f"{listing}\n\n請輸入要移除的主題編號，或輸入「結束」離開喔！"


def handle_youtube_topic_remove_step(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    """處理 `pending_youtube_topic_remove` 狀態下使用者輸入的編號，選定後直接刪除該主題。"""
    state = state_store.get(telegram_user_id)
    if text in _EXIT_PHRASES:
        state_store.clear(telegram_user_id)
        return "好的，已結束 YouTube 主題查詢模式！"

    topic_ids = state["topic_ids"]
    if not text.isdigit() or not (1 <= int(text) <= len(topic_ids)):
        return f"請輸入 1～{len(topic_ids)} 之間的編號，或輸入「結束」離開喔！"

    topic_id = topic_ids[int(text) - 1]
    target_user_id = state["target_user_id"]
    state_store.clear(telegram_user_id)
    youtube.remove_topic(db, target_user_id, topic_id)
    return "好的，已經幫你移除這組主題囉！"


# --- FR-51、FR-52：好友模式（ADR-22）---


def start_friend_chat(db: CloudSQLClient, llm_client, user_id: int) -> str:
    """「陪我聊聊」／`/friend_chat`：被動觸發的好友模式陪伴聊天（FR-51、FR-52，ADR-22）。

    全體使用者皆可用（`friend_mode` 開關 `owner_only=False`），單輪生成完整回覆，不走多輪對話
    狀態機（見 ADR-22 後果）；動態讀取這位使用者已開啟且近期有資料的所有功能模組近況（見
    `friend_chat.gather_recent_context()`），交給 LLM 生成陪伴式回覆，內容自然涵蓋 FR-51 的
    心情趨勢文字/emoji 摘要。
    """
    user = db.select("users", where="id = %s", params=(user_id,), fetch_one=True)
    role = user["role"] if user else "這位使用者"

    today = _now().date()
    context = friend_chat.gather_recent_context(db, user_id, today)
    prompt = friend_chat.build_companion_prompt(role, context)
    return llm_client.generate_text(prompt).strip()


# --- Step 4.1（見 robinson SPEC.md FR-33、FR-36，ADR-24）：求職模組設定流程（僅 Robin 可用）---
#
# 收集流程共 8 輪，設計比照 FR-56f 情境範例：搜尋條件（FR-33，LLM 一次解析關鍵字/地區/薪資，
# 關鍵字是唯一必要欄位，其餘沒提到一律視為「不限」）→ 說明每週排程限制＋準備確認
# （CONFIRM 才繼續，CANCEL 直接結束不留下任何資料）→ 履歷全文（FR-36，含 PII 遮蔽＋確認/修正
# 迴圈）→ 未來期望工作敘述（同上）→ 結構化年資 → 結構化期望薪資下限 → 上限（ADR-26 決策 1：
# 這兩個結構化欄位刻意從自由文字拆出來明確詢問，不靠 LLM 從期望工作敘述猜測）。收集途中隨時
# 可以修改前面步驟（履歷/期望工作敘述的確認迴圈），但不支援「回頭改搜尋條件」——不清楚就直接
# 反問到清楚為止，不會走到後面才需要回頭改。最後一步收齊才一次寫入資料庫（FR-33 的
# `job_search_criteria` INSERT 一筆、FR-36 的 `users` 五個欄位一起 UPDATE），中途任何一步
# 放棄都不會留下部分資料。FR-34（爬蟲）、FR-35（公司背景 Email 協作）留待後續 commit 擴充。
#
# 2026-08-09：依 Robin 指示移除產業篩選（實測 104 API 後確認這個維度不值得繼續猜參數名稱），
# 這一輪不再詢問「產業類型」。

_JOB_SEARCH_CRITERIA_PROMPT = "好的，你有什麼特別的需求嗎（找什麼類型的職缺？地區？薪資待遇區間？）："

_JOB_SEARCH_CRITERIA_PARSE_PROMPT = (
    "使用者想要設定 104 求職搜尋條件，這是使用者針對「有什麼特別的需求嗎（關鍵字/地區/薪資範圍）」"
    "這句反問的回覆：「{text}」。\n"
    "請嚴格照下面格式輸出，每個欄位各自一行，不要輸出其他任何文字：\n"
    "STATUS: CLEAR 或 UNCLEAR。只要完全沒有提到任何職缺關鍵字（例如職稱、技能、產業方向）就填"
    "UNCLEAR；只要有提到關鍵字，其餘欄位（地區/薪資）沒提到一律視為「不限」，不影響"
    "STATUS 判斷，一律填 CLEAR\n"
    "KEYWORD: 職缺關鍵字（STATUS 為 UNCLEAR 時可省略）\n"
    "REGION: 地區文字，沒有提到或使用者說不限就填 NONE\n"
    "SALARY_MIN: 薪資下限數字（純數字，不要千分位逗號或單位），沒有提到就填 NONE\n"
    "SALARY_MAX: 薪資上限數字（純數字），沒有提到就填 NONE"
)

_JOB_SEARCH_WEEKLY_NOTICE = (
    "好的，但我要提醒你一下，這個功能一週只會做一次喔，要等到排程啟動後，我才能給你清單與連結，"
    "然後我需要你給我「詳細的履歷敘述（3500 字以內），記得不用給您的個資資訊如電子郵件或"
    "手機號碼等」和「未來期望工作敘述（期望工作內容、企業文化、薪資、福利等）」，你準備好了嗎？"
)

_JOB_SEARCH_READY_CONFIRM_PROMPT = (
    "Robinson 剛跟使用者說明求職功能一週只執行一次，並詢問「你準備好了嗎？」準備開始提供履歷與"
    "期望工作敘述，這是使用者這一則的回覆：「{text}」。\n"
    "請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 準備好了，要繼續 → CONFIRM\n"
    "(2) 還沒準備好/不要了 → CANCEL"
)

_JOB_SEARCH_REVISE_PROMPT = (
    "Robinson 剛把使用者提供的內容記錄下來，並詢問「有需要修正嗎？」，這是使用者這一則的回覆："
    "「{text}」。\n"
    "請判斷使用者的意思，整則回覆只能輸出以下其中一個固定字，不要輸出其他任何文字：\n"
    "(1) 不需要修正，可以繼續下一步 → CONFIRM\n"
    "(2) 需要修正/重新提供 → REVISE"
)


def _parse_optional_text(value: str) -> str | None:
    """把 LLM 輸出的欄位值換算成「使用者真的有講」的文字；空字串或 `NONE` 一律視為未提供。"""
    value = (value or "").strip()
    if not value or value.upper() == "NONE":
        return None
    return value


def _parse_optional_int(value: str) -> int | None:
    """把 LLM 輸出的欄位值換算成可為 `None` 的整數；空字串、`NONE`、或無法解析都回傳 `None`。"""
    value = (value or "").strip()
    if not value or value.upper() == "NONE":
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _parse_non_negative_float(text: str) -> float | None:
    """把使用者輸入的文字換算成 >= 0 的 float（年資允許 0，代表社會新鮮人）；無法解析回傳 None。"""
    try:
        value = float(text.strip())
    except ValueError:
        return None
    return value if value >= 0 else None


def start_job_search_setup(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「/set_job_search」／「我要找工作」：開始求職模組設定流程（FR-33、FR-36，僅 Robin 可用）。"""
    state_store.set(telegram_user_id, {"flow": "pending_job_search_criteria", "target_user_id": user_id})
    return _JOB_SEARCH_CRITERIA_PROMPT


def handle_job_search_criteria_step(
    llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    """處理 `pending_job_search_criteria` 狀態下使用者提供的搜尋條件（FR-33）。

    只有完全沒提到任何關鍵字才視為 UNCLEAR、原地反問；地區/薪資沒提到一律視為「不限」，
    不會卡住整輪。解析成功後先存在 state 裡（尚未寫入資料庫），等
    `pending_job_search_ready_confirm` 這一輪使用者確認要繼續才真正呼叫
    `job_search.save_search_criteria()`（見 `handle_job_search_salary_max_step`）。
    """
    state = state_store.get(telegram_user_id)
    parsed = _parse_key_value_block(llm_client.generate_text(_JOB_SEARCH_CRITERIA_PARSE_PROMPT.format(text=text)))
    keyword = (parsed.get("KEYWORD") or "").strip()
    if parsed.get("STATUS") != "CLEAR" or not keyword:
        return "不好意思，我還是不太確定你想找什麼類型的職缺，可以再講清楚一點嗎？（例如：AI、資料相關）"

    state_store.set(
        telegram_user_id,
        {
            "flow": "pending_job_search_ready_confirm",
            "target_user_id": state["target_user_id"],
            "keyword": keyword,
            "region": _parse_optional_text(parsed.get("REGION", "")),
            "salary_min": _parse_optional_int(parsed.get("SALARY_MIN", "")),
            "salary_max": _parse_optional_int(parsed.get("SALARY_MAX", "")),
        },
    )
    return _JOB_SEARCH_WEEKLY_NOTICE


def handle_job_search_ready_confirm_step(
    llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    """處理 `pending_job_search_ready_confirm` 狀態下使用者對「你準備好了嗎？」的回覆。"""
    state = state_store.get(telegram_user_id)
    decision = llm_client.generate_text(_JOB_SEARCH_READY_CONFIRM_PROMPT.format(text=text)).strip()
    if decision != "CONFIRM":
        state_store.clear(telegram_user_id)
        return "好的，那我們先不設定，想開始時再跟我說一聲！"

    state_store.set(telegram_user_id, {**state, "flow": "pending_job_search_resume"})
    return "先給我詳細的履歷敘述（3500 字以內）！"


def handle_job_search_resume_step(
    state_store: ConversationStateStore, telegram_user_id: int, text: str, privacy_llm_client=None
) -> str:
    """處理 `pending_job_search_resume` 狀態下使用者提供的履歷全文（FR-36）。

    `privacy_llm_client`：履歷可能不小心含個資，寫入 state（最終落地 `users.job_resume`）前
    一律先過 `privacy.mask_text()`，設計比照 `handle_mood_content_step()`。
    """
    if not job_search.is_text_length_valid(text):
        return "不好意思，履歷內容超過 3500 字了，麻煩精簡一下再重新提供喔！"

    state = state_store.get(telegram_user_id)
    masked_resume, pii_detected = privacy.mask_text(text, privacy_llm_client)
    state_store.set(telegram_user_id, {**state, "flow": "pending_job_search_resume_confirm", "resume": masked_resume})
    reply = "有需要修正嗎？沒有的話再給我未來期望工作敘述："
    if pii_detected:
        reply += _PII_DETECTED_REMINDER
    return reply


def handle_job_search_resume_confirm_step(
    llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    """處理 `pending_job_search_resume_confirm` 狀態下使用者對「有需要修正嗎？」的回覆。"""
    state = state_store.get(telegram_user_id)
    decision = llm_client.generate_text(_JOB_SEARCH_REVISE_PROMPT.format(text=text)).strip()
    if decision == "REVISE":
        state_store.set(telegram_user_id, {**state, "flow": "pending_job_search_resume"})
        return "好的，麻煩重新提供一次履歷內容："

    state_store.set(telegram_user_id, {**state, "flow": "pending_job_search_expectation"})
    return "好的，再給我未來期望工作敘述（期望工作內容、企業文化、薪資、福利等）："


def handle_job_search_expectation_step(
    state_store: ConversationStateStore, telegram_user_id: int, text: str, privacy_llm_client=None
) -> str:
    """處理 `pending_job_search_expectation` 狀態下使用者提供的期望工作敘述（FR-36）。"""
    if not job_search.is_text_length_valid(text):
        return "不好意思，內容超過 3500 字了，麻煩精簡一下再重新提供喔！"

    state = state_store.get(telegram_user_id)
    masked_expectation, pii_detected = privacy.mask_text(text, privacy_llm_client)
    state_store.set(
        telegram_user_id,
        {**state, "flow": "pending_job_search_expectation_confirm", "expectation": masked_expectation},
    )
    reply = "有需要修正嗎？沒有的話我接著問你的年資："
    if pii_detected:
        reply += _PII_DETECTED_REMINDER
    return reply


def handle_job_search_expectation_confirm_step(
    llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    """處理 `pending_job_search_expectation_confirm` 狀態下使用者對「有需要修正嗎？」的回覆。"""
    state = state_store.get(telegram_user_id)
    decision = llm_client.generate_text(_JOB_SEARCH_REVISE_PROMPT.format(text=text)).strip()
    if decision == "REVISE":
        state_store.set(telegram_user_id, {**state, "flow": "pending_job_search_expectation"})
        return "好的，麻煩重新提供一次未來期望工作敘述："

    state_store.set(telegram_user_id, {**state, "flow": "pending_job_search_years_experience"})
    return "好的，你的年資大概是幾年呢？（直接給我數字就好，例如：3.5，社會新鮮人可以填 0）"


def handle_job_search_years_experience_step(
    state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    """處理 `pending_job_search_years_experience` 狀態下使用者提供的年資數字
    （FR-36，ADR-26 決策 1：從自由文字拆出來的結構化欄位，明確詢問不靠 LLM 猜測）。"""
    years = _parse_non_negative_float(text)
    if years is None:
        return "不好意思，我沒看懂，麻煩直接輸入數字喔（例如：3.5）"
    if not job_search.is_years_of_experience_reasonable(years):
        return "這個年資數字看起來不太合理，麻煩確認一下再重新輸入喔（0～60 之間）！"

    state = state_store.get(telegram_user_id)
    state_store.set(telegram_user_id, {**state, "flow": "pending_job_search_salary_min", "years_of_experience": years})
    return "好的，那你期望的薪資下限是多少呢？（直接給我數字就好）"


def handle_job_search_salary_min_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_job_search_salary_min` 狀態下使用者提供的期望薪資下限（FR-36，ADR-26 決策 1）。"""
    amount = _parse_amount(text)
    if amount is None:
        return "不好意思，我沒看懂，麻煩輸入一個數字喔（例如：50000）"

    state = state_store.get(telegram_user_id)
    state_store.set(
        telegram_user_id, {**state, "flow": "pending_job_search_salary_max", "expected_salary_min": int(amount)}
    )
    return "那期望薪資上限呢？（直接給我數字就好）"


def handle_job_search_salary_max_step(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, text: str
) -> str:
    """處理 `pending_job_search_salary_max` 狀態下使用者提供的期望薪資上限，收齊後一次寫入
    `job_search_criteria`（FR-33）與 `users` 的履歷/期望工作/年資/期望薪資欄位（FR-36）。"""
    amount = _parse_amount(text)
    if amount is None:
        return "不好意思，我沒看懂，麻煩輸入一個數字喔（例如：80000）"

    state = state_store.get(telegram_user_id)
    expected_salary_min = state["expected_salary_min"]
    expected_salary_max = int(amount)
    if expected_salary_max < expected_salary_min:
        return f"上限（{expected_salary_max}）比下限（{expected_salary_min}）還低耶，麻煩重新輸入上限："

    target_user_id = state["target_user_id"]
    state_store.clear(telegram_user_id)

    job_search.save_search_criteria(
        db, target_user_id, state["keyword"], state["region"], state["salary_min"], state["salary_max"],
    )
    job_search.save_profile(
        db, target_user_id, state["resume"], state["expectation"], state["years_of_experience"],
        expected_salary_min, expected_salary_max,
    )
    return "好的，已經幫你記錄好求職資料了！等下週排程跑完，我就會把清單寄給你囉～"


def handle_company_csv_uploaded(db: CloudSQLClient, gdrive_client, filename: str) -> str:
    """處理「已上傳{filename}」觸發詞中，檔名符合公司背景 CSV 命名規則的情況（FR-35e）：至既有
    共用 Google Drive 資料夾（沿用 `GDRIVE_FOLDER_ID`）以檔名找到該檔案、下載、解析 CSV，把
    「背景」欄位逐筆 `UPDATE` 回填 `job_companies`（以 104 公司 ID 比對）。

    找不到對應公司的 104 公司 ID 一律列出來提醒人工處理，不可靜默略過（比照 FR-38e）。
    """
    candidates = gdrive_client.list_files(name_contains=filename)
    matched = next((f for f in candidates if f["name"] == filename), None)
    if matched is None:
        return f"我在 Drive 資料夾裡找不到「{filename}」耶，麻煩確認一下檔名或是不是真的上傳成功了！"

    csv_text = gdrive_client.download_file(matched["id"]).decode("utf-8-sig")
    entries = job_search.parse_companies_csv(csv_text)
    result = job_search.apply_company_backgrounds(db, entries)

    reply = f"已經幫你回填 {result['updated_count']} 家公司的背景資料囉！"
    if result["not_found_ids"]:
        ids_text = "、".join(result["not_found_ids"])
        reply += f"\n找不到對應公司的 104 公司 ID：{ids_text}，麻煩人工確認一下！"
    return reply


def handle_job_recommendation_excel_uploaded(db: CloudSQLClient, gdrive_client, filename: str) -> str:
    """處理「已上傳{filename}」觸發詞中，檔名符合職缺推薦 Excel 命名規則的情況（FR-38e）：至既有
    共用 Google Drive 資料夾（沿用 `GDRIVE_FOLDER_ID`）以檔名找到該檔案、下載、解析 Excel，把
    「是否喜歡」欄位（填 1 代表不喜歡）逐筆 `UPDATE` 回填 `job_postings.is_unliked`（以職缺 URL
    比對，設計完全比照 `handle_company_csv_uploaded()`）。

    找不到對應職缺的連結一律列出來提醒人工處理，不可靜默略過（比照 FR-35e）。
    """
    candidates = gdrive_client.list_files(name_contains=filename)
    matched = next((f for f in candidates if f["name"] == filename), None)
    if matched is None:
        return f"我在 Drive 資料夾裡找不到「{filename}」耶，麻煩確認一下檔名或是不是真的上傳成功了！"

    xlsx_bytes = gdrive_client.download_file(matched["id"])
    entries = job_search.parse_recommendation_excel(xlsx_bytes)
    result = job_search.apply_job_preferences(db, entries)

    reply = f"已經幫你回填 {result['updated_count']} 筆職缺的喜好標記囉！"
    if result["not_found_urls"]:
        urls_text = "、".join(result["not_found_urls"])
        reply += f"\n找不到對應職缺的連結：{urls_text}，麻煩人工確認一下！"
    return reply


# --- FR-40：外部管道職缺新增（Step 4.3，見 ADR-27）---

_EXTERNAL_JOB_CHANNEL_PROMPT = "好的，這個職缺是從哪個管道找到的呢？（例如：LinkedIn、Cake）"
_EXTERNAL_JOB_TITLE_PROMPT = "職缺名稱是？"
_EXTERNAL_JOB_COMPANY_PROMPT = "公司名稱是？"
_EXTERNAL_JOB_URL_PROMPT = "職缺連結是？"
_EXTERNAL_JOB_CONTENT_PROMPT = "職缺內容是？（把完整說明貼給我，3500 字以內，供之後契合度評分使用）"
_EXTERNAL_JOB_BACKGROUND_PROMPT = "這家公司的背景資料呢？（用你知道的資訊描述，3500 字以內，供之後契合度評分使用）"


def start_add_external_job(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    """「新增外部職缺」／`/add_external_job`：開始記錄 LinkedIn／Cake 等非 104 來源職缺的流程
    （FR-40），先問管道。"""
    state_store.set(telegram_user_id, {"flow": "pending_external_job_channel", "target_user_id": user_id})
    return _EXTERNAL_JOB_CHANNEL_PROMPT


def handle_external_job_channel_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_external_job_channel` 狀態下使用者提供的管道名稱（自由文字，不限固定清單）。"""
    state = state_store.get(telegram_user_id)
    state_store.set(telegram_user_id, {**state, "flow": "pending_external_job_title", "channel": text.strip()})
    return _EXTERNAL_JOB_TITLE_PROMPT


def handle_external_job_title_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_external_job_title` 狀態下使用者提供的職缺名稱。"""
    state = state_store.get(telegram_user_id)
    state_store.set(telegram_user_id, {**state, "flow": "pending_external_job_company", "title": text.strip()})
    return _EXTERNAL_JOB_COMPANY_PROMPT


def handle_external_job_company_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_external_job_company` 狀態下使用者提供的公司名稱。"""
    state = state_store.get(telegram_user_id)
    state_store.set(telegram_user_id, {**state, "flow": "pending_external_job_url", "company_name": text.strip()})
    return _EXTERNAL_JOB_URL_PROMPT


def handle_external_job_url_step(state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    """處理 `pending_external_job_url` 狀態下使用者提供的職缺連結。"""
    state = state_store.get(telegram_user_id)
    state_store.set(telegram_user_id, {**state, "flow": "pending_external_job_content", "url": text.strip()})
    return _EXTERNAL_JOB_CONTENT_PROMPT


def handle_external_job_content_step(
    state_store: ConversationStateStore, telegram_user_id: int, text: str, privacy_llm_client=None
) -> str:
    """處理 `pending_external_job_content` 狀態下使用者提供的職缺內容（FR-40a），套用既有 3500
    字上限（比照 FR-36）＋ FR-13 個資遮蔽（貼上的職缺說明可能不小心含聯絡窗口等個資）。"""
    if not job_search.is_text_length_valid(text):
        return "不好意思，職缺內容超過 3500 字了，麻煩精簡一下再重新提供喔！"

    state = state_store.get(telegram_user_id)
    masked_content, pii_detected = privacy.mask_text(text, privacy_llm_client)
    state_store.set(telegram_user_id, {**state, "flow": "pending_external_job_background", "content": masked_content})
    reply = _EXTERNAL_JOB_BACKGROUND_PROMPT
    if pii_detected:
        reply += _PII_DETECTED_REMINDER
    return reply


def handle_external_job_background_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    text: str,
    privacy_llm_client=None,
) -> str:
    """處理 `pending_external_job_background` 狀態下使用者提供的公司背景，收齊六個欄位後一次寫入
    資料庫（`job_search.add_external_job()`），回覆分配到的職缺 ID 供之後查詢／更新應徵狀態
    （FR-39）使用。"""
    if not job_search.is_text_length_valid(text):
        return "不好意思，公司背景超過 3500 字了，麻煩精簡一下再重新提供喔！"

    state = state_store.get(telegram_user_id)
    masked_background, pii_detected = privacy.mask_text(text, privacy_llm_client)
    state_store.clear(telegram_user_id)

    job_id_104 = job_search.add_external_job(
        db, state["channel"], state["title"], state["company_name"], state["url"], state["content"], masked_background,
    )
    reply = (
        f"已經幫你記錄好這筆職缺囉！職缺 ID 是 {job_id_104}，之後要更新應徵狀態可以打「ID={job_id_104} "
        f"職缺已應徵」這類語句，下週排程也會自動幫你評分～"
    )
    if pii_detected:
        reply += _PII_DETECTED_REMINDER
    return reply


# --- FR-39（追加）：我的應徵紀錄查詢指令 ---


def handle_my_applications(db: CloudSQLClient) -> str:
    """「我的應徵紀錄」／`/my_applications`：列出各職缺目前最新的應徵狀態（依最新更新時間排序）。"""
    statuses = job_search.list_latest_application_statuses(db)
    return job_search.format_application_statuses(statuses)
