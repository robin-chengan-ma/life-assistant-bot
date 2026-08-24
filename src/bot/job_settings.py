"""Telegram 求職設定選單流程（FR-41／FR-41a）。"""
from src.bot import job_search
from src.bot.state import ConversationStateStore

_PROFILE_FIELDS = {
    "resume": ("job_resume", "我的履歷"),
    "expectation": ("job_expectation", "期望工作內容"),
}
_STATUS_OPTIONS = [
    ("applied", "已應徵"),
    ("interview", "已獲得面試"),
    ("offer", "已拿到 Offer"),
    ("rejected", "未錄取／已婉拒"),
]


def _keyboard(rows: list[tuple[str, str]]) -> dict:
    return {"inline_keyboard": [[{"text": label, "callback_data": callback}] for label, callback in rows]}


def start_menu() -> tuple[str, dict]:
    return "💼 求職設定，請選擇項目：", _keyboard([
        ("我的履歷", "job_search:profile:resume"),
        ("期望工作內容", "job_search:profile:expectation"),
        ("必要條件設定", "job_search:requirements"),
        ("職缺關鍵字設定", "job_search:criteria"),
        ("職缺清單", "job_search:jobs"),
        ("已應徵職缺設定", "job_search:status:applied"),
        ("獲得面試職缺設定", "job_search:status:interview"),
        ("拿到 Offer 職缺設定", "job_search:status:offer"),
        ("職缺已關閉設定", "job_search:closed"),
        ("其他平台職缺", "job_search:external:add"),
        ("🔙 返回主選單", "menu:main"),
    ])


def start_profile_menu(db, user_id: int, key: str) -> tuple[str, dict]:
    field, label = _PROFILE_FIELDS[key]
    value = job_search.get_profile(db, user_id).get(field) or "尚未設定"
    return f"{label}：\n{value}", _keyboard([
        ("✏️ 編輯", f"job_search:profile:edit:{key}"),
        ("🗑 清空", f"job_search:profile:clear:{key}"),
        ("🔙 返回求職設定", "job_search:menu"),
    ])


def start_profile_edit(state_store: ConversationStateStore, telegram_user_id: int, user_id: int, key: str) -> str:
    field, label = _PROFILE_FIELDS[key]
    state_store.set(telegram_user_id, {"flow": "pending_job_settings_profile", "user_id": user_id, "field": field, "label": label})
    return f"請輸入新的{label}（3500 字以內）："


def handle_profile_edit(db, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    state = state_store.get(telegram_user_id)
    if not job_search.is_text_length_valid(text):
        return "內容超過 3500 字，請精簡後重新輸入。"
    job_search.update_profile_field(db, state["user_id"], state["field"], text.strip())
    state_store.clear(telegram_user_id)
    return f"已更新{state['label']}。"


def start_profile_clear_confirm(db, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, field: str) -> tuple[str, dict]:
    key = next(key for key, value in _PROFILE_FIELDS.items() if value[0] == field)
    state_store.set(telegram_user_id, {"flow": "pending_job_settings_profile_clear", "user_id": user_id, "field": field})
    return "確定要清空這項內容嗎？此操作無法復原。", _keyboard([
        ("✅ 確認清空", f"job_search:profile:confirm_clear:{key}"),
        ("❌ 取消", f"job_search:profile:{key}"),
    ])


def handle_profile_clear_confirm(db, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, field: str) -> str:
    state = state_store.get(telegram_user_id)
    if state is None or state.get("flow") != "pending_job_settings_profile_clear" or state.get("field") != field:
        return "這個清空操作已失效，請重新操作。"
    job_search.update_profile_field(db, user_id, field, None)
    state_store.clear(telegram_user_id)
    return "已清空設定。"


def start_requirements(db, state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> tuple[str, dict]:
    profile = job_search.get_profile(db, user_id)
    text = "必要條件設定：\n年資：{} 年\n期望薪資：{}～{}".format(
        profile.get("years_of_experience", "尚未設定"),
        profile.get("expected_salary_min", "尚未設定"),
        profile.get("expected_salary_max", "尚未設定"),
    )
    return text, _keyboard([("✏️ 編輯", "job_search:requirements:edit"), ("🔙 返回求職設定", "job_search:menu")])


def start_requirements_edit(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    state_store.set(telegram_user_id, {"flow": "pending_job_settings_requirements", "user_id": user_id, "step": "years"})
    return "請輸入年資（0～60，單位：年）："


def handle_requirements_edit(db, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    state = state_store.get(telegram_user_id)
    step = state["step"]
    try:
        value = float(text.strip()) if step == "years" else int(text.strip())
    except ValueError:
        return "格式不正確，請輸入數字。"
    if step == "years":
        if not job_search.is_years_of_experience_reasonable(value):
            return "年資請輸入 0～60 年。"
        state_store.set(telegram_user_id, {**state, "step": "salary_min", "years": value})
        return "請輸入期望薪資下限："
    if step == "salary_min":
        if value < 0:
            return "薪資不可為負數。"
        state_store.set(telegram_user_id, {**state, "step": "salary_max", "salary_min": value})
        return "請輸入期望薪資上限："
    if value < state["salary_min"]:
        return "薪資上限不可低於下限，請重新輸入。"
    for field, field_value in (
        ("years_of_experience", state["years"]),
        ("expected_salary_min", state["salary_min"]),
        ("expected_salary_max", value),
    ):
        job_search.update_profile_field(db, state["user_id"], field, field_value)
    state_store.clear(telegram_user_id)
    return "已更新必要條件設定。"


_CRITERIA_EXAMPLE_TEXT = (
    "請用自然語言描述搜尋條件，例如「台北的 AI 工程師，薪資 5 到 8 萬」，"
    "或「台北或新竹的 AI 工程師，薪資 5 到 8 萬」（可以同時指定多個地區）。"
)


def start_criteria_menu(db, user_id: int) -> tuple[str, dict]:
    """2026-08-18（求職設定選單化第二批，見 docs/ADR/discuss/job-search.md ADR-28 決策更新）：
    清單同時顯示地區／薪資範圍（`format_search_criteria()`），不再只印關鍵字；每筆各自補上
    「✏️ 編輯」按鈕，改地區/薪資不用再先刪除重建。"""
    criteria = job_search.list_search_criteria(db, user_id)
    lines = ["職缺關鍵字設定："] + [job_search.format_search_criteria(item) for item in criteria]
    rows = [("➕ 新增關鍵字", "job_search:criteria:add")]
    for item in criteria:
        rows.append((f"✏️ 編輯：{item['keyword']}", f"job_search:criteria:edit:{item['id']}"))
        rows.append((f"🗑 刪除：{item['keyword']}", f"job_search:criteria:delete:{item['id']}"))
    rows.append(("🔙 返回求職設定", "job_search:menu"))
    text = "\n".join(lines) if criteria else "目前沒有職缺關鍵字，可新增一筆。"
    return text, _keyboard(rows)


def start_criteria_add(state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> str:
    state_store.set(telegram_user_id, {"flow": "pending_job_settings_criteria", "user_id": user_id})
    return _CRITERIA_EXAMPLE_TEXT


def handle_criteria_add(db, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    from src.bot import commands
    parsed = commands._parse_key_value_block(llm_client.generate_text(commands._JOB_SEARCH_CRITERIA_PARSE_PROMPT.format(text=text)))
    keyword = (parsed.get("KEYWORD") or "").strip()
    if parsed.get("STATUS") != "CLEAR" or not keyword:
        return "不太確定職缺關鍵字，請再描述得明確一些。"
    state = state_store.get(telegram_user_id)
    job_search.save_search_criteria(db, state["user_id"], keyword, commands._parse_optional_text(parsed.get("REGION", "")), commands._parse_optional_int(parsed.get("SALARY_MIN", "")), commands._parse_optional_int(parsed.get("SALARY_MAX", "")))
    state_store.clear(telegram_user_id)
    return "已新增職缺關鍵字設定。"


def start_criteria_edit(db, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, criteria_id: int) -> tuple[str, dict | None]:
    """2026-08-18（求職設定選單化第二批，ADR-28 決策④）：編輯走跟新增相同的自然語言整段描述，
    解析完成後整筆覆蓋（不做逐欄位局部編輯），語意上跟「移除＝清空該欄位」一致，只是保留原本
    的 `id` 不變。回傳固定是 `(文字, keyboard 或 None)`——找不到這筆設定時附返回鍵盤，正常進入
    編輯狀態時 `keyboard` 為 `None`（比照 `start_criteria_add()` 的純文字提示，等使用者下一則
    訊息才由 `handle_criteria_edit()` 接手）。"""
    criteria = next((item for item in job_search.list_search_criteria(db, user_id) if item["id"] == criteria_id), None)
    if criteria is None:
        return "找不到這筆職缺關鍵字設定，可能已經被刪除了。", _keyboard([("🔙 返回求職設定", "job_search:menu")])
    state_store.set(telegram_user_id, {"flow": "pending_job_settings_criteria_edit", "user_id": user_id, "criteria_id": criteria_id})
    text = f"目前設定：{job_search.format_search_criteria(criteria)}\n\n{_CRITERIA_EXAMPLE_TEXT}（會整筆覆蓋原本設定）"
    return text, None


def handle_criteria_edit(db, llm_client, state_store: ConversationStateStore, telegram_user_id: int, text: str) -> str:
    from src.bot import commands
    parsed = commands._parse_key_value_block(llm_client.generate_text(commands._JOB_SEARCH_CRITERIA_PARSE_PROMPT.format(text=text)))
    keyword = (parsed.get("KEYWORD") or "").strip()
    if parsed.get("STATUS") != "CLEAR" or not keyword:
        return "不太確定職缺關鍵字，請再描述得明確一些。"
    state = state_store.get(telegram_user_id)
    updated = job_search.update_search_criteria(
        db,
        state["user_id"],
        state["criteria_id"],
        keyword,
        commands._parse_optional_text(parsed.get("REGION", "")),
        commands._parse_optional_int(parsed.get("SALARY_MIN", "")),
        commands._parse_optional_int(parsed.get("SALARY_MAX", "")),
    )
    state_store.clear(telegram_user_id)
    return "已更新職缺關鍵字設定。" if updated else "找不到這筆職缺關鍵字設定，可能已經被刪除了。"


def start_criteria_delete_confirm(state_store: ConversationStateStore, telegram_user_id: int, user_id: int, criteria_id: int) -> tuple[str, dict]:
    state_store.set(telegram_user_id, {"flow": "pending_job_settings_criteria_delete", "user_id": user_id, "criteria_id": criteria_id})
    return "確定要刪除這筆職缺關鍵字嗎？", _keyboard([
        ("✅ 確認刪除", f"job_search:criteria:confirm_delete:{criteria_id}"),
        ("❌ 取消", "job_search:criteria"),
    ])


def handle_criteria_delete_confirm(db, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, criteria_id: int) -> str:
    state = state_store.get(telegram_user_id)
    if state is None or state.get("flow") != "pending_job_settings_criteria_delete" or state.get("criteria_id") != criteria_id:
        return "這個刪除操作已失效，請重新操作。"
    state_store.clear(telegram_user_id)
    return "已刪除職缺關鍵字設定。" if job_search.delete_search_criteria(db, user_id, criteria_id) else "找不到這筆職缺關鍵字設定。"


_JOBS_LIST_PAGE_SIZE = 10


def start_jobs_list(db, page: int = 1) -> tuple[str, dict]:
    """2026-08-24（見 docs/ADR/debug/job-search.md「職缺清單訊息過長打不開」條目）：職缺會隨每週
    爬蟲持續累積，過去把全部職缺一次串成一則訊息，職缺數一多就會超過 Telegram 單則訊息 4096
    字元上限，導致 `send_text()` 送出失敗；`webhook.py` 又刻意把送出失敗的例外整個吞掉只記
    log（避免單一功能壞掉波及其他功能），使用者端因此完全沒有任何反應。改成每頁固定
    `_JOBS_LIST_PAGE_SIZE` 筆＋上一頁／下一頁按鈕，徹底避免單則訊息無上限增長。
    """
    jobs = job_search.list_jobs_by_score(db)
    if not jobs:
        return "目前沒有職缺資料。", _keyboard([("🔙 返回求職設定", "job_search:menu")])

    total_pages = (len(jobs) + _JOBS_LIST_PAGE_SIZE - 1) // _JOBS_LIST_PAGE_SIZE
    page = max(1, min(page, total_pages))
    start = (page - 1) * _JOBS_LIST_PAGE_SIZE
    page_items = jobs[start : start + _JOBS_LIST_PAGE_SIZE]

    lines = [f"📋 職缺清單（依契合度排序，第 {page}／{total_pages} 頁）："]
    for item in page_items:
        score = item.get("score")
        lines.append(f"・{item['title']}（ID={item['job_id_104']}，分數：{score if score is not None else '尚未評分'}）")

    nav_row = []
    if page > 1:
        nav_row.append({"text": "⬅️ 上一頁", "callback_data": f"job_search:jobs:page:{page - 1}"})
    if page < total_pages:
        nav_row.append({"text": "➡️ 下一頁", "callback_data": f"job_search:jobs:page:{page + 1}"})
    keyboard = {"inline_keyboard": ([nav_row] if nav_row else []) + [[{"text": "🔙 返回求職設定", "callback_data": "job_search:menu"}]]}
    return "\n".join(lines), keyboard


def start_status_list(db, status: str) -> tuple[str, dict]:
    jobs = job_search.list_jobs_by_latest_application_status(db, status)
    label = dict(_STATUS_OPTIONS)[status]
    rows = [(item["title"], f"job_search:status:select:{item['job_id_104']}") for item in jobs]
    rows.append(("🔙 返回求職設定", "job_search:menu"))
    return (f"{label}職缺：" if jobs else f"目前沒有{label}職缺。"), _keyboard(rows)


def start_status_update(job_id_104: str) -> tuple[str, dict]:
    return "請選擇新的應徵狀態：", _keyboard([
        (label, f"job_search:status:set:{job_id_104}:{status}") for status, label in _STATUS_OPTIONS
    ] + [("🔙 返回求職設定", "job_search:menu")])


def start_closed_list(db) -> tuple[str, dict]:
    jobs = job_search.list_jobs_by_score(db)
    rows = []
    for item in jobs:
        action = "open" if item.get("is_closed") else "close"
        label = "重新開啟" if item.get("is_closed") else "標記關閉"
        rows.append((f"{label}：{item['title']}", f"job_search:closed:{action}:{item['job_id_104']}"))
    rows.append(("🔙 返回求職設定", "job_search:menu"))
    return "職缺已關閉設定（顯示全部職缺）：", _keyboard(rows)
