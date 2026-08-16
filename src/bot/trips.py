"""Telegram「旅遊行程」選單流程（Phase 6 第二批 2d，見 docs/ADR/discuss/robinson.md
2026-08-15「Phase 6 第二批 2b 起子批次分組順序」與「2d 收藏與旅遊實作計畫」）。

直接複用既有 `AppLifeExplorationService`（Mobile App 已在用的同一套驗證與 CRUD 邏輯），
不重寫欄位規則，符合 FR-6h。行程只允許一個國家及一個區域／城市，收藏項目只列出相同
目的地的收藏（FR-74）；預估支出支援六個分類逐一輸入，也允許全部略過只看加總（FR-74a）。
"""

from __future__ import annotations

from typing import Any

from src.bot import menu
from src.bot.state import ConversationStateStore
from src.services.app_life_exploration import (
    AppLifeExplorationService,
    LifeNotFoundError,
    LifeValidationError,
)
from src.services.geocoding import NominatimGeocoder
from submodules.cloudsql.client import CloudSQLClient

_EXIT_PHRASES = {"沒有了", "結束"}
_SKIP_PHRASES = {"略過", "skip"}

_STATUS_LABELS = {"planning": "規劃中", "confirmed": "已確認", "completed": "已完成", "cancelled": "已取消"}

_BUDGET_STEPS = (
    ("estimated_transport", "交通"),
    ("estimated_accommodation", "住宿"),
    ("estimated_food", "飲食"),
    ("estimated_tickets", "門票"),
    ("estimated_shopping", "購物"),
    ("estimated_other", "其他"),
)


def _service(db: CloudSQLClient) -> AppLifeExplorationService:
    return AppLifeExplorationService(db, NominatimGeocoder(db))


def _candidates(db: CloudSQLClient, user_id: int, country_name: str, city_name: str) -> list[dict[str, Any]]:
    rows = db.select(
        "collection_items",
        where="user_id = %s AND deleted_at IS NULL AND country_name = %s AND city_name = %s",
        params=(user_id, country_name, city_name),
    )
    return sorted(rows, key=lambda row: row["id"])


# ---------------------------------------------------------------------------
# 清單／狀態操作
# ---------------------------------------------------------------------------

def _format_trip(trip: dict[str, Any], index: int) -> str:
    status_label = _STATUS_LABELS.get(trip["status"], trip["status"])
    date_line = "日期未定" if not trip.get("start_date") else f"{trip['start_date']} ～ {trip['end_date']}"
    estimated = trip.get("estimated_total") or 0
    actual = trip.get("actual_expense") or 0
    return (
        f"{index}. {trip['title']}（{status_label}）\n"
        f"　　{trip['country_name']}／{trip['city_name']}｜{date_line}\n"
        f"　　預估 {estimated:g} 元／實際 {actual:g} 元"
    )


def handle_list(db: CloudSQLClient, user_id: int) -> tuple[str, dict]:
    service = _service(db)
    result = service.list_trips(user_id)
    trips = result["trips"]
    if not trips:
        keyboard = {
            "inline_keyboard": [
                [{"text": "🧭 從收藏清單建立行程", "callback_data": "collections:list"}],
                [{"text": "🔙 返回", "callback_data": "menu:collections"}],
            ]
        }
        return "目前還沒有任何旅遊行程，先到收藏清單挑選想去的地點吧！", keyboard

    lines = ["目前的旅遊行程：", ""]
    buttons = []
    for index, trip in enumerate(trips, start=1):
        lines.append(_format_trip(trip, index))
        row = [
            {"text": f"✏️ 編輯 {index}", "callback_data": f"trips:edit:{trip['id']}"},
            {"text": f"🗑 刪除 {index}", "callback_data": f"trips:delete:{trip['id']}"},
        ]
        buttons.append(row)
        action_row = []
        if trip["status"] == "planning":
            action_row.append({"text": f"✅ 確認 {index}", "callback_data": f"trips:confirm:{trip['id']}"})
        if trip["status"] in ("planning", "confirmed"):
            action_row.append({"text": f"🏁 完成 {index}", "callback_data": f"trips:complete:{trip['id']}"})
            action_row.append({"text": f"❌ 取消 {index}", "callback_data": f"trips:cancel:{trip['id']}"})
        if action_row:
            buttons.append(action_row)
    buttons.append([{"text": "🔙 返回", "callback_data": "menu:collections"}])
    return "\n".join(lines), {"inline_keyboard": buttons}


def _full_payload(trip: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "title": trip["title"],
        "start_date": trip.get("start_date"),
        "end_date": trip.get("end_date"),
        "country_name": trip["country_name"],
        "city_name": trip["city_name"],
        "collection_item_ids": [item["collection_item_id"] for item in trip.get("items", [])],
        "notes": trip.get("notes"),
        "sync_to_important_day": trip.get("sync_to_important_day", True),
        "status": trip["status"],
    }
    for field, _ in _BUDGET_STEPS:
        payload[field] = trip.get(field)
    return payload


def handle_set_status(db: CloudSQLClient, user_id: int, trip_id: int, new_status: str) -> tuple[str, dict]:
    """行程清單頁的快速狀態操作（確認／取消／略過完成前的兩種前置狀態），
    不重新走一次多步驟輸入，直接用既有欄位組完整 payload 呼叫 `update_trip()`。"""
    service = _service(db)
    result = service.list_trips(user_id)
    trip = next((t for t in result["trips"] if t["id"] == trip_id), None)
    if trip is None:
        return "找不到這個旅遊行程，可能已經被刪除了。", menu.back_to_main_menu_keyboard()
    payload = _full_payload(trip)
    payload["status"] = new_status
    try:
        service.update_trip(trip_id, user_id, payload)
    except LifeValidationError as exc:
        return str(exc), menu.back_to_main_menu_keyboard()
    label = _STATUS_LABELS.get(new_status, new_status)
    return f"行程已更新為「{label}」。", menu.back_to_main_menu_keyboard()


def start_delete_confirm(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, trip_id: int) -> tuple[str, dict]:
    row = db.select("trips", where="id = %s AND user_id = %s AND deleted_at IS NULL", params=(trip_id, user_id), fetch_one=True)
    if row is None:
        return "找不到這個旅遊行程，可能已經被刪除了。", menu.back_to_main_menu_keyboard()
    state_store.set(telegram_user_id, {"flow": "trip_delete_confirm", "target_id": trip_id})
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ 確認刪除", "callback_data": f"trips:confirm_delete:{trip_id}"}],
            [{"text": "❌ 取消", "callback_data": "trips:list"}],
        ]
    }
    return f"確定要刪除「{row['title']}」嗎？此動作無法復原（不會刪除收藏或記帳紀錄）。", keyboard


def handle_delete_confirm_text(state_store: ConversationStateStore, telegram_user_id: int) -> tuple[str, dict]:
    state_store.clear(telegram_user_id)
    return "刪除確認請用上面的按鈕操作喔，這次先幫你取消了。", menu.back_to_main_menu_keyboard()


def handle_delete(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, trip_id: int) -> tuple[str, dict]:
    state_store.clear(telegram_user_id)
    service = _service(db)
    try:
        service.delete_trip(trip_id, user_id)
    except LifeNotFoundError as exc:
        return str(exc), menu.back_to_main_menu_keyboard()
    return "已刪除該筆旅遊行程。", menu.back_to_main_menu_keyboard()


# ---------------------------------------------------------------------------
# 新增／編輯（共用同一組多步驟流程）
# ---------------------------------------------------------------------------

def start_add(state_store: ConversationStateStore, telegram_user_id: int) -> str:
    state_store.set(
        telegram_user_id,
        {"flow": "trip", "step": "awaiting_title", "mode": "add", "target_id": None, "data": {}},
    )
    return "請輸入行程名稱："


def start_edit(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, trip_id: int) -> str:
    row = db.select("trips", where="id = %s AND user_id = %s AND deleted_at IS NULL", params=(trip_id, user_id), fetch_one=True)
    if row is None:
        return "找不到這個旅遊行程，可能已經被刪除了。"
    state_store.set(
        telegram_user_id,
        {"flow": "trip", "step": "awaiting_title", "mode": "edit", "target_id": trip_id, "data": {}},
    )
    return f"目前名稱是「{row['title']}」，重新輸入完整內容即可（不需要改的欄位重打一次原值）。\n\n請輸入行程名稱："


def _summary_text(data: dict[str, Any]) -> str:
    date_line = "尚未指定（規劃中）" if not data.get("start_date") else f"{data['start_date']} ～ {data['end_date']}"
    items_line = "（無）" if not data.get("_selected_titles") else "、".join(data["_selected_titles"])
    sync_line = "是" if data.get("sync_to_important_day") else "否"
    budget_lines = "\n".join(
        f"　{label}：{(data.get(field) or 0):g} 元" for field, label in _BUDGET_STEPS
    )
    total = sum((data.get(field) or 0) for field, _ in _BUDGET_STEPS)
    notes = data.get("notes") or "（無）"
    return (
        "請確認以下內容：\n\n"
        f"名稱：{data['title']}\n"
        f"國家／城市：{data['country_name']}／{data['city_name']}\n"
        f"收藏項目：{items_line}\n"
        f"日期：{date_line}\n"
        f"同步重要日子：{sync_line}\n"
        f"預估支出：\n{budget_lines}\n"
        f"　合計：{total:g} 元\n"
        f"備註：{notes}"
    )


def _render_item_select(data: dict[str, Any]) -> tuple[str, dict]:
    candidates = data["_candidates"]
    selected = set(data.get("_selected_ids", []))
    lines = [f"請勾選要加入行程的收藏項目（{data['country_name']}／{data['city_name']}）：", ""]
    buttons = []
    for item in candidates:
        mark = "☑" if item["id"] in selected else "☐"
        lines.append(f"{mark} {item['title']}")
        buttons.append([{"text": f"{mark} {item['title']}", "callback_data": f"trips:toggle_item:{item['id']}"}])
    buttons.append([{"text": "✅ 完成選擇", "callback_data": "trips:items_done"}])
    return "\n".join(lines), {"inline_keyboard": buttons}


def handle_step(
    db: CloudSQLClient,
    state_store: ConversationStateStore,
    telegram_user_id: int,
    user_id: int,
    text: str,
) -> tuple[str, dict | None]:
    state = state_store.get(telegram_user_id)
    step = state.get("step")
    data: dict[str, Any] = state.get("data", {})

    if text in _EXIT_PHRASES:
        state_store.clear(telegram_user_id)
        return "好的，已結束旅遊行程設定！", menu.back_to_main_menu_keyboard()

    if step == "awaiting_title":
        title = text.strip()
        if not title:
            return "名稱不可以是空白，請重新輸入：", None
        data["title"] = title
        state["step"] = "awaiting_country"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return "請輸入國家（單一行程只允許一個國家）：", None

    if step == "awaiting_country":
        country = text.strip()
        if not country:
            return "國家不可以是空白，請重新輸入：", None
        data["country_name"] = country
        state["step"] = "awaiting_city"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return "請輸入區域／城市（單一行程只允許一個區域／城市）：", None

    if step == "awaiting_city":
        city = text.strip()
        if not city:
            return "區域／城市不可以是空白，請重新輸入：", None
        candidates = _candidates(db, user_id, data["country_name"], city)
        if not candidates:
            state_store.clear(telegram_user_id)
            keyboard = {
                "inline_keyboard": [
                    [{"text": "➕ 新增收藏", "callback_data": "collections:add"}],
                    [{"text": "🔙 返回", "callback_data": "menu:collections"}],
                ]
            }
            return (
                f"「{data['country_name']}／{city}」目前沒有任何收藏項目，"
                "請先到收藏清單新增這個目的地的收藏，再回來建立行程。"
            ), keyboard
        data["city_name"] = city
        data["_candidates"] = [{"id": row["id"], "title": row["title"]} for row in candidates]
        data["_selected_ids"] = []
        state["step"] = "awaiting_items"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return _render_item_select(data)

    if step == "awaiting_items":
        return "請用上面的按鈕勾選收藏項目，勾選完成後按「✅ 完成選擇」：", None

    if step == "awaiting_start_date":
        if text.strip() in _SKIP_PHRASES:
            data["start_date"] = None
            data["end_date"] = None
            return _advance_to_sync(state, state_store, telegram_user_id, data)
        try:
            from datetime import date as _date
            start = _date.fromisoformat(text.strip())
        except ValueError:
            return "日期格式不正確，請用「YYYY-MM-DD」，或輸入「略過」：", None
        data["_start_date"] = start.isoformat()
        state["step"] = "awaiting_end_date"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return "請輸入結束日期（只有一天的話重打一次開始日期即可）：", None

    if step == "awaiting_end_date":
        try:
            from datetime import date as _date
            end = _date.fromisoformat(text.strip())
            start = _date.fromisoformat(data["_start_date"])
        except ValueError:
            return "日期格式不正確，請用「YYYY-MM-DD」：", None
        if end < start:
            return "結束日期不可早於開始日期，請重新輸入：", None
        data["start_date"] = data["_start_date"]
        data["end_date"] = end.isoformat()
        return _advance_to_sync(state, state_store, telegram_user_id, data)

    if step == "awaiting_sync":
        if text.strip() in ("是", "yes"):
            data["sync_to_important_day"] = True
        elif text.strip() in ("否", "no"):
            data["sync_to_important_day"] = False
        else:
            return "請回答「是」或「否」：", None
        state["step"] = "awaiting_budget"
        state["_budget_index"] = 0
        state["data"] = data
        state_store.set(telegram_user_id, state)
        field, label = _BUDGET_STEPS[0]
        return f"請輸入預估支出－{label}（新台幣，選填，沒有的話請輸入「略過」）：", None

    if step == "awaiting_budget":
        index = state.get("_budget_index", 0)
        field, label = _BUDGET_STEPS[index]
        if text.strip() in _SKIP_PHRASES:
            data[field] = None
        else:
            try:
                data[field] = float(text.strip())
            except ValueError:
                return f"請輸入數字，或輸入「略過」（目前是{label}）：", None
        index += 1
        if index < len(_BUDGET_STEPS):
            state["_budget_index"] = index
            state["data"] = data
            state_store.set(telegram_user_id, state)
            next_field, next_label = _BUDGET_STEPS[index]
            return f"請輸入預估支出－{next_label}（新台幣，選填，沒有的話請輸入「略過」）：", None
        state["step"] = "awaiting_notes"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return "有想補充的備註嗎？沒有的話請輸入「略過」：", None

    if step == "awaiting_notes":
        data["notes"] = None if text.strip() in _SKIP_PHRASES else text.strip()
        state["step"] = "awaiting_confirm"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        keyboard = {
            "inline_keyboard": [
                [{"text": "✅ 確認送出", "callback_data": "trips:confirm_save"}],
                [{"text": "❌ 取消", "callback_data": "menu:main"}],
            ]
        }
        return _summary_text(data), keyboard

    raise ValueError(f"未知的對話狀態：{state}")


def _advance_to_sync(state: dict, state_store: ConversationStateStore, telegram_user_id: int, data: dict) -> tuple[str, None]:
    state["step"] = "awaiting_sync"
    state["data"] = data
    state_store.set(telegram_user_id, state)
    return "要同步建立「重要日子」提醒嗎？請回答「是」或「否」：", None


def handle_toggle_item(state_store: ConversationStateStore, telegram_user_id: int, collection_id: int) -> tuple[str, dict]:
    state = state_store.get(telegram_user_id)
    if not state or state.get("flow") != "trip" or state.get("step") != "awaiting_items":
        return "目前沒有進行中的旅遊行程設定。", menu.back_to_main_menu_keyboard()
    data = state["data"]
    selected = set(data.get("_selected_ids", []))
    if collection_id in selected:
        selected.discard(collection_id)
    else:
        selected.add(collection_id)
    data["_selected_ids"] = sorted(selected)
    state["data"] = data
    state_store.set(telegram_user_id, state)
    return _render_item_select(data)


def handle_items_done(state_store: ConversationStateStore, telegram_user_id: int) -> tuple[str, None]:
    state = state_store.get(telegram_user_id)
    if not state or state.get("flow") != "trip" or state.get("step") != "awaiting_items":
        return "目前沒有進行中的旅遊行程設定。", None
    data = state["data"]
    selected_ids = data.get("_selected_ids", [])
    id_to_title = {item["id"]: item["title"] for item in data["_candidates"]}
    data["collection_item_ids"] = selected_ids
    data["_selected_titles"] = [id_to_title[i] for i in selected_ids]
    state["step"] = "awaiting_start_date"
    state["data"] = data
    state_store.set(telegram_user_id, state)
    return "請輸入開始日期（YYYY-MM-DD），尚未確定可以輸入「略過」：", None


def handle_confirm_save(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> tuple[str, dict]:
    state = state_store.get(telegram_user_id)
    if not state or state.get("flow") != "trip" or state.get("step") != "awaiting_confirm":
        return "目前沒有進行中的旅遊行程設定。", menu.back_to_main_menu_keyboard()

    data = dict(state["data"])
    mode = state.get("mode", "add")
    target_id = state.get("target_id")
    payload = {k: v for k, v in data.items() if not k.startswith("_")}

    service = _service(db)
    state_store.clear(telegram_user_id)
    try:
        if mode == "edit" and target_id is not None:
            service.update_trip(target_id, user_id, payload)
            return "已更新該筆旅遊行程！", menu.back_to_main_menu_keyboard()
        service.create_trip(user_id, payload)
        return "已新增旅遊行程！", menu.back_to_main_menu_keyboard()
    except LifeValidationError as exc:
        return f"儲存失敗：{exc}\n請重新從「收藏與旅遊」選單開始設定。", menu.back_to_main_menu_keyboard()
    except LifeNotFoundError as exc:
        return str(exc), menu.back_to_main_menu_keyboard()


# ---------------------------------------------------------------------------
# 完成行程（勾選實際造訪項目）
# ---------------------------------------------------------------------------

def _render_complete_select(data: dict[str, Any]) -> tuple[str, dict]:
    candidates = data["_candidates"]
    selected = set(data.get("_selected_ids", []))
    lines = ["這趟行程實際造訪了哪些項目？（未勾選的收藏會保留，不會標記為已造訪）", ""]
    buttons = []
    for item in candidates:
        mark = "☑" if item["collection_item_id"] in selected else "☐"
        lines.append(f"{mark} {item['title_snapshot']}")
        buttons.append([{"text": f"{mark} {item['title_snapshot']}", "callback_data": f"trips:complete_toggle:{item['collection_item_id']}"}])
    buttons.append([{"text": "✅ 完成行程", "callback_data": f"trips:complete_confirm:{data['trip_id']}"}])
    buttons.append([{"text": "❌ 取消", "callback_data": "trips:list"}])
    return "\n".join(lines), {"inline_keyboard": buttons}


def start_complete_select(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, trip_id: int) -> tuple[str, dict]:
    trip_row = db.select("trips", where="id = %s AND user_id = %s AND deleted_at IS NULL", params=(trip_id, user_id), fetch_one=True)
    if trip_row is None:
        return "找不到這個旅遊行程，可能已經被刪除了。", menu.back_to_main_menu_keyboard()
    if not trip_row.get("start_date") or not trip_row.get("end_date"):
        return "完成行程前請先編輯行程設定開始與結束日期。", menu.back_to_main_menu_keyboard()
    links = db.select("trip_collection_items", where="trip_id = %s", params=(trip_id,))
    items = [{"id": row["id"], "collection_item_id": row["collection_item_id"], "title_snapshot": row.get("title_snapshot") or "（收藏項目）"} for row in links]
    if not items:
        return "這個行程沒有任何收藏項目，無法標記造訪，請先編輯行程加入收藏項目。", menu.back_to_main_menu_keyboard()
    data = {"trip_id": trip_id, "_candidates": items, "_selected_ids": []}
    state_store.set(telegram_user_id, {"flow": "trip_complete_select", "data": data})
    return _render_complete_select(data)


def handle_complete_toggle(state_store: ConversationStateStore, telegram_user_id: int, collection_id: int) -> tuple[str, dict]:
    state = state_store.get(telegram_user_id)
    if not state or state.get("flow") != "trip_complete_select":
        return "目前沒有進行中的完成行程流程。", menu.back_to_main_menu_keyboard()
    data = state["data"]
    selected = set(data.get("_selected_ids", []))
    if collection_id in selected:
        selected.discard(collection_id)
    else:
        selected.add(collection_id)
    data["_selected_ids"] = sorted(selected)
    state["data"] = data
    state_store.set(telegram_user_id, state)
    return _render_complete_select(data)


def handle_complete_confirm(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, trip_id: int) -> tuple[str, dict]:
    state = state_store.get(telegram_user_id)
    if not state or state.get("flow") != "trip_complete_select" or state["data"].get("trip_id") != trip_id:
        return "目前沒有進行中的完成行程流程。", menu.back_to_main_menu_keyboard()
    selected_ids = state["data"].get("_selected_ids", [])
    state_store.clear(telegram_user_id)
    service = _service(db)
    try:
        result = service.complete_trip(trip_id, user_id, {"visited_collection_ids": selected_ids})
    except (LifeValidationError, LifeNotFoundError) as exc:
        return str(exc), menu.back_to_main_menu_keyboard()
    return f"行程已完成並建立探索紀錄，共 {result['visited_count']} 項已造訪！", menu.back_to_main_menu_keyboard()


def handle_complete_select_text(state_store: ConversationStateStore, telegram_user_id: int) -> tuple[str, dict]:
    state_store.clear(telegram_user_id)
    return "完成行程請用上面的按鈕操作喔，這次先幫你取消了。", menu.back_to_main_menu_keyboard()
