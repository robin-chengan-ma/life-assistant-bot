"""Telegram「🔍 資料查詢」選單流程（批次4，見 docs/ADR/discuss/robinson.md「資料查詢開工前
SDD 計畫確認」，docs/specs/SPEC.md FR-9c／FR-9d）。

直接複用 Mobile App 既有的 `AppAnalyticsService`（`src/services/app_analytics.py`）各模組唯讀
查詢方法，不重寫查詢邏輯，符合 FR-6h「兩端共用相同欄位、必填、數值範圍、驗證與讀取結果」。
可查範圍只涵蓋 `menu.QUERY_MODULES` 這 7 個本來就有日期區間概念的模組；重要日子／收藏與旅遊／
成果展示／目標追蹤維持只能從各自主選單查看，不併入資料查詢（2026-08-18 與 Robin 確認）。

流程：選單「🔍 資料查詢」→ 選最終日期（快速按鈕「今天」「昨天」，或直接打字，打字走 LLM 判斷
CLEAR／UNCLEAR，比照 `commands.py` 既有補記日期解析的慣例；跟補記不同的是這裡允許未來日期，
FR-9c 明確容許「最終日期可位於未來」）→ 系統自動往前推 6 天組出最多 7 個曆日的區間 → 模組複選
（`query:module:<key>` 逐一切換勾選狀態）→「🔍 開始查詢」（`query:run`）。

查詢結果逐日列出區間內全部日期，當天沒有紀錄一律顯示「查無紀錄」，不省略；每筆紀錄的欄位不寫死
固定樣板，改成該筆紀錄實際有什麼欄位就顯示什麼（`_format_record()`），只排除 `id`／`user_id`
等內部欄位（2026-08-18 與 Robin 確認的兩點：逐日含空日、格式彈性不寫死）。多模組查詢結果依模組
分則 Telegram 訊息送出（避開單則 4096 字元上限），需要 `telegram_client`；沒有提供時優雅降級成
合併成一則訊息回傳（測試或極端情況下的保守做法，不中斷流程）。

FR-9d「Telegram 查詢結果沿用帳號層的 Mobile App 隱私數字遮罩偏好」：Mobile 前端的
`privacy_mask_enabled` 只是旗標，實際遮罩顯示邏輯在 Mobile App 前端元件裡；Telegram 沒有對應
UI，這裡是新寫的純文字遮罩實作決策——`privacy_mask_enabled=True` 時，把每個欄位值裡的數字字元
逐位替換成 `*`（例如「65.5」→「**.*」），文字型欄位（備註、心情內容等）不遮罩。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.bot import menu
from src.bot.state import ConversationStateStore
from src.services.app_analytics import (
    AppAnalyticsService,
    FeatureDisabledError,
    ForbiddenModuleError,
)
from src.services.app_auth import AuthenticatedUser

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")

_QUERY_DATE_PARSE_PROMPT = (
    "使用者正在使用「資料查詢」功能，Robinson 剛請使用者選擇查詢區間的「最終日期」，"
    "這是使用者這一則的回覆：「{date_reply}」。\n"
    "【現在的日期（台灣時區，計算相對日期時一律以此為準）】\n{current_date_text}\n\n"
    "請判斷使用者是否已經講清楚明確的日期，並嚴格照下面格式輸出，每個欄位各自一行，"
    "不要輸出其他任何文字：\n"
    "STATUS: CLEAR 或 UNCLEAR。使用者必須明確講出是哪一天（例如「今天」「昨天」「8/15」"
    "「2026-08-20」「下星期三」都算明確；只要含糊、沒有講清楚是哪一天，一律填 UNCLEAR，"
    "絕對不可以自己亂猜。這個日期可以是未來日期，不要因為是未來日期就填 UNCLEAR。\n"
    "DATE: 換算後的日期，格式一律為 YYYY-MM-DD（STATUS 為 UNCLEAR 時可省略）"
)
_QUERY_DATE_UNCLEAR_REPLY = "不好意思，我還是不太確定是哪一天，可以再講清楚一點嗎？（例如：今天、8/15、2026-08-20）"
_NO_LLM_REPLY = "日期解析功能暫時無法使用，請改用「📅 今天」「📅 昨天」快速按鈕，或稍後再試。"
_NO_MODULE_SELECTED_REPLY = "請至少勾選一個模組再開始查詢喔！"

# 每個模組要逐日列出哪幾個小節：(小節標題, AppAnalyticsService 回傳 dict 裡的 list key, 該筆紀錄的日期欄位)。
# 只列「紀錄本身有日期」的清單，不含彙總指標（例如記帳收支總額、體態目標、求職漏斗統計）——
# 那些屬於分析彙總、不是「某天發生了什麼」，維持只能從各自模組或「🎯 目標追蹤」查看。
_MODULE_SECTIONS: dict[str, list[tuple[str, str, str]]] = {
    "todos": [("待辦事項", "items", "due_at")],
    "body": [
        ("體重", "weight_records", "entry_date"),
        ("飲食", "diet_records", "entry_date"),
        ("運動", "exercise_records", "entry_date"),
    ],
    "finance": [("記帳", "records", "date")],
    "mood": [("心情", "items", "date")],
    "skills": [("技術文摘", "digests", "digest_date"), ("YouTube 推播", "videos", "pushed_on")],
    "jobs": [("推薦職缺", "recommendations", "first_seen_at"), ("投遞時程", "timeline", "created_at")],
    "exams": [("正式成績", "official_scores", "exam_date"), ("練習記錄", "practice", "date")],
}

# 已知欄位的中文標籤；沒列出的欄位直接顯示原始 key，不因為欄位還沒被登記進這份對照表就漏顯示
# （呼應「格式不寫死」的決策：這份表只是「翻譯成中文」的加分項，不是白名單）。
_FIELD_LABELS = {
    "weight_kg": "體重(公斤)", "waist_cm": "腰圍(公分)", "height_cm": "身高(公分)", "bmi": "BMI",
    "water_ml": "飲水量(ml)", "total_fat_g": "脂肪(g)", "total_protein_g": "蛋白質(g)",
    "total_carbs_g": "碳水(g)", "total_calories": "熱量(大卡)", "minutes": "運動時長(分鐘)",
    "type": "收支類型", "category": "分類", "amount": "金額", "note": "備註",
    "mood_category": "心情分類", "content": "內容", "achievement_note": "成就筆記",
    "title": "職缺名稱", "match_score": "媒合分數", "recommend_reason": "推薦原因", "status": "狀態",
    "exam_type": "證照類型", "score": "分數", "question_type": "題型",
    "total": "作答題數", "correct": "答對題數", "summary_text": "摘要", "source": "來源",
    "topic": "主題", "due_at": "截止時間", "start_at": "開始時間",
}
_EXCLUDED_FIELDS = {"id", "user_id", "can_edit", "created_at", "job_id_104", "waist"}


def _now() -> datetime:
    return datetime.now(_TAIWAN_TZ)


def _current_date_text() -> str:
    now = _now()
    return f"{now.year}年{now.month}月{now.day}日"


def _parse_key_value_block(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in (raw or "").splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        result[key.strip().upper()] = value.strip()
    return result


def _parse_date_only(raw: str) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()  # noqa: DTZ007
    except ValueError:
        return None


def _authenticated_user(user: dict) -> AuthenticatedUser:
    is_owner = bool(user.get("is_owner"))
    return AuthenticatedUser(
        database_id=user["id"],
        app_user_id=f"user{user['id']:02d}",
        role=user.get("role") or ("owner" if is_owner else "member"),
        is_owner=is_owner,
    )


def _date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _mask_number(value: Any) -> str:
    return "".join("*" if ch.isdigit() else ch for ch in str(value))


def _format_value(value: Any, *, mask_numbers: bool) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        return _mask_number(value) if mask_numbers else str(value)
    return str(value)


def _format_record(record: dict[str, Any], *, date_field: str, mask_numbers: bool) -> str:
    parts = []
    for key, value in record.items():
        if key == date_field or key in _EXCLUDED_FIELDS:
            continue
        if value is None or value == "":
            continue
        label = _FIELD_LABELS.get(key, key)
        parts.append(f"{label}：{_format_value(value, mask_numbers=mask_numbers)}")
    return "・" + ("／".join(parts) if parts else "（無其他欄位）")


def _format_module(module_label: str, payload: dict[str, Any], sections: list[tuple[str, str, str]],
                    days: list[date], *, mask_numbers: bool) -> str:
    lines = [f"🔍 {module_label}（{days[0].isoformat()} ~ {days[-1].isoformat()}）"]
    for section_label, list_key, date_field in sections:
        lines.append("")
        lines.append(f"【{section_label}】")
        records = payload.get(list_key) or []
        by_day: dict[str, list[dict]] = {}
        for record in records:
            raw_date = record.get(date_field)
            if not raw_date:
                continue
            by_day.setdefault(str(raw_date)[:10], []).append(record)
        for day in days:
            lines.append(f"{day.month}/{day.day}：")
            day_records = by_day.get(day.isoformat())
            if not day_records:
                lines.append("　　查無紀錄")
                continue
            for record in day_records:
                lines.append("　　" + _format_record(record, date_field=date_field, mask_numbers=mask_numbers))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 選單／日期
# ---------------------------------------------------------------------------

def start_query_menu(state_store: ConversationStateStore, telegram_user_id: int) -> tuple[str, dict]:
    """主選單按下「🔍 資料查詢」後的子選單首頁；同時把狀態設成 `pending_query_date`，
    下一則自由文字會被當成日期描述解析。"""
    state_store.set(telegram_user_id, {"flow": "pending_query_date"})
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📅 今天", "callback_data": "query:date:today"},
                {"text": "📅 昨天", "callback_data": "query:date:yesterday"},
            ],
            [{"text": "🔙 返回主選單", "callback_data": "menu:main"}],
        ]
    }
    text = (
        "🔍 資料查詢\n\n"
        "請選擇查詢區間的「最終日期」，我會自動往前推 6 天，一次最多查 7 個曆日（最終日期可以是"
        "未來日期）。\n可以直接按下面的快速按鈕，或是直接打字告訴我日期（例如：8/15、"
        "2026-08-20、下星期三）。"
    )
    return text, keyboard


def _module_selection_text(state: dict) -> str:
    end_date = date.fromisoformat(state["end_date"])
    start_date = end_date - timedelta(days=6)
    return (
        f"查詢區間：{start_date.isoformat()} ~ {end_date.isoformat()}（共 7 天）\n\n"
        "請勾選要查詢的模組（可複選），選好後按「🔍 開始查詢」："
    )


def _build_module_keyboard(state: dict, *, is_owner: bool) -> dict:
    selected = set(state.get("selected") or [])
    buttons = []
    for item in menu.visible_query_modules(is_owner):
        mark = "✅" if item["key"] in selected else "⬜"
        buttons.append([{"text": f"{mark} {item['label']}", "callback_data": f"query:module:{item['key']}"}])
    buttons.append([{"text": "🔍 開始查詢", "callback_data": "query:run"}])
    buttons.append([{"text": "📅 重新選擇日期", "callback_data": "menu:query"}])
    buttons.append([{"text": "🔙 返回主選單", "callback_data": "menu:main"}])
    return {"inline_keyboard": buttons}


def _enter_module_selection(
    state_store: ConversationStateStore, telegram_user_id: int, end_date: date, *, is_owner: bool
) -> tuple[str, dict]:
    state = {"flow": "pending_query_modules", "end_date": end_date.isoformat(), "selected": []}
    state_store.set(telegram_user_id, state)
    return _module_selection_text(state), _build_module_keyboard(state, is_owner=is_owner)


def handle_date_quick(
    state_store: ConversationStateStore, telegram_user_id: int, *, is_owner: bool, choice: str
) -> tuple[str, dict]:
    """`query:date:today` / `query:date:yesterday` 快速按鈕。"""
    today = _now().date()
    end_date = today if choice == "today" else today - timedelta(days=1)
    return _enter_module_selection(state_store, telegram_user_id, end_date, is_owner=is_owner)


def handle_date_text(
    state_store: ConversationStateStore, telegram_user_id: int, text: str, *, is_owner: bool, llm_client=None
) -> tuple[str, dict | None]:
    """`pending_query_date` 狀態下使用者打字描述的日期。"""
    if llm_client is None:
        return _NO_LLM_REPLY, None

    parsed = _parse_key_value_block(
        llm_client.generate_text(
            _QUERY_DATE_PARSE_PROMPT.format(date_reply=text, current_date_text=_current_date_text())
        )
    )
    if parsed.get("STATUS") != "CLEAR":
        return _QUERY_DATE_UNCLEAR_REPLY, None

    end_date = _parse_date_only(parsed.get("DATE", ""))
    if end_date is None:
        return _QUERY_DATE_UNCLEAR_REPLY, None

    return _enter_module_selection(state_store, telegram_user_id, end_date, is_owner=is_owner)


def handle_module_toggle(
    state_store: ConversationStateStore, telegram_user_id: int, *, is_owner: bool, module_key: str
) -> tuple[str, dict]:
    """`query:module:<key>`：切換該模組的勾選狀態。"""
    state = state_store.get(telegram_user_id)
    if state is None or state.get("flow") != "pending_query_modules":
        return start_query_menu(state_store, telegram_user_id)
    if not menu.is_valid_query_module_key(module_key, is_owner=is_owner):
        return _module_selection_text(state), _build_module_keyboard(state, is_owner=is_owner)

    selected = list(state.get("selected") or [])
    if module_key in selected:
        selected.remove(module_key)
    else:
        selected.append(module_key)
    state["selected"] = selected
    state_store.set(telegram_user_id, state)
    return _module_selection_text(state), _build_module_keyboard(state, is_owner=is_owner)


def handle_run(
    db, state_store: ConversationStateStore, telegram_user_id: int, user: dict, *, telegram_client=None
) -> tuple[str, dict | None]:
    """`query:run`：依已勾選模組逐一查詢，依模組分則訊息送出（FR-9c／FR-9d）。"""
    is_owner = bool(user.get("is_owner"))
    state = state_store.get(telegram_user_id)
    if state is None or state.get("flow") != "pending_query_modules":
        return start_query_menu(state_store, telegram_user_id)

    selected = list(state.get("selected") or [])
    if not selected:
        return _NO_MODULE_SELECTED_REPLY, _build_module_keyboard(state, is_owner=is_owner)

    end_date = date.fromisoformat(state["end_date"])
    start_date = end_date - timedelta(days=6)
    days = _date_range(start_date, end_date)
    mask_numbers = bool(user.get("privacy_mask_enabled"))

    service = AppAnalyticsService(db)
    auth_user = _authenticated_user(user)
    messages: list[str] = []
    for module_key in selected:
        module = next(item for item in menu.QUERY_MODULES if item["key"] == module_key)
        method = getattr(service, module["analytics_method"])
        try:
            if module_key == "todos":
                payload = method(auth_user, start_date, end_date, calendar_start=start_date, calendar_end=end_date)
            else:
                payload = method(auth_user, start_date, end_date)
        except (ForbiddenModuleError, FeatureDisabledError) as exc:
            messages.append(f"🔍 {module['label']}\n{exc}")
            continue
        messages.append(
            _format_module(module["label"], payload, _MODULE_SECTIONS[module_key], days, mask_numbers=mask_numbers)
        )

    state_store.clear(telegram_user_id)
    keyboard = {
        "inline_keyboard": [
            [{"text": "🔄 重新查詢", "callback_data": "menu:query"}],
            [{"text": "🔙 返回主選單", "callback_data": "menu:main"}],
        ]
    }
    if not messages:
        return "查詢完成，但沒有取得任何資料。", keyboard

    if telegram_client is not None and len(messages) > 1:
        for text in messages[:-1]:
            telegram_client.send_text(telegram_user_id, text)
        return messages[-1], keyboard

    # `telegram_client` 沒有提供（例如測試環境）時優雅降級，合併成一則訊息回傳，不中斷流程。
    return "\n\n".join(messages), keyboard
