"""Telegram「收藏清單」選單流程（Phase 6 第二批 2d，見 docs/ADR/discuss/robinson.md
2026-08-15「Phase 6 第二批 2b 起子批次分組順序」與「2d 收藏與旅遊實作計畫」）。

直接複用既有 `AppCollectionService`（Mobile App 已在用的同一套驗證與 CRUD 邏輯），
不重寫欄位規則，符合 FR-6h「兩端共用相同欄位、必填、數值範圍、驗證與讀取結果」。

地址定位比照 Mobile 規則（FR-75）：使用者必須明確按下「📍 定位地址」按鈕才會呼叫
Nominatim，不在文字輸入當下自動觸發；全部層級失敗仍可保存並標記「無法定位」。

2026-08-16（Phase 6 第二批 2d 補修，見 docs/ADR/debug/robinson.md）：新增「🧭 標記已造訪」
動作，直接呼叫 `AppLifeExplorationService.visit_collection()`，補上 Telegram 原本漏掉的
「收藏可不經行程、直接標記已造訪」入口（FR-73「狀態依行程關聯與造訪紀錄自動推導」），
比照 Mobile 收藏清單卡片上的「標記已造訪」按鈕；標記後才會在探索地圖看到座標標記。
"""

from __future__ import annotations

from datetime import date as _date
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.bot import menu
from src.bot.state import ConversationStateStore
from src.services.app_collections import (
    AppCollectionService,
    CollectionNotFoundError,
    CollectionValidationError,
)
from src.services.app_life_exploration import (
    AppLifeExplorationService,
    LifeNotFoundError,
    LifeValidationError,
)
from src.services.geocoding import (
    GeocodingError,
    NominatimGeocoder,
)
from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_EXIT_PHRASES = {"沒有了", "結束"}
_SKIP_PHRASES = {"略過", "skip"}
_TODAY_PHRASES = {"今天", "today"}

_ITEM_TYPE_LABELS = {
    "restaurant": "餐廳",
    "attraction": "景點",
    "mountain": "山岳",
    "accommodation": "住宿",
    "activity": "活動",
    "other": "其他",
}
_ITEM_TYPE_ORDER = ("restaurant", "attraction", "mountain", "accommodation", "activity", "other")

_STATUS_LABELS = {"saved": "已收藏", "added_to_trip": "已排入行程", "visited": "已造訪"}


def _service(db: CloudSQLClient) -> AppCollectionService:
    return AppCollectionService(db, NominatimGeocoder(db))


def _life_service(db: CloudSQLClient) -> AppLifeExplorationService:
    return AppLifeExplorationService(db, NominatimGeocoder(db))


# ---------------------------------------------------------------------------
# 選單／清單
# ---------------------------------------------------------------------------

def start_collections_menu() -> tuple[str, dict]:
    """主選單按下「🧭 收藏與旅遊」後的子選單首頁。"""
    keyboard = {
        "inline_keyboard": [
            [{"text": "📋 收藏清單", "callback_data": "collections:list"}],
            [{"text": "➕ 新增收藏", "callback_data": "collections:add"}],
            [{"text": "🧳 旅遊行程", "callback_data": "trips:list"}],
            [{"text": "🔙 返回主選單", "callback_data": "menu:main"}],
        ]
    }
    return "收藏與旅遊，請選擇要進行的操作：", keyboard


def _format_list_item(item: dict[str, Any], index: int) -> str:
    type_label = _ITEM_TYPE_LABELS.get(item["item_type"], item["item_type"])
    status_label = _STATUS_LABELS.get(item["status"], item["status"])
    address = item.get("address") or "（未定位）"
    return (
        f"{index}. {item['title']}（{type_label}）\n"
        f"　　{item['country_name']}／{item['city_name']}｜{address}\n"
        f"　　狀態：{status_label}"
    )


def handle_list(db: CloudSQLClient, user_id: int) -> tuple[str, dict]:
    service = _service(db)
    result = service.list_for_user(user_id)
    items = result["items"]
    if not items:
        keyboard = {
            "inline_keyboard": [
                [{"text": "➕ 新增收藏", "callback_data": "collections:add"}],
                [{"text": "🔙 返回", "callback_data": "menu:collections"}],
            ]
        }
        return "目前還沒有任何收藏，可以按「➕ 新增收藏」建立第一筆！", keyboard

    lines = ["目前的收藏清單：", ""]
    buttons = []
    for index, item in enumerate(items, start=1):
        lines.append(_format_list_item(item, index))
        row = [
            {"text": f"✏️ 編輯 {index}", "callback_data": f"collections:edit:{item['id']}"},
            {"text": f"🗑 刪除 {index}", "callback_data": f"collections:delete:{item['id']}"},
        ]
        buttons.append(row)
        if item["status"] != "visited":
            buttons.append([{"text": f"🧭 標記已造訪 {index}", "callback_data": f"collections:visit:{item['id']}"}])
    buttons.append([{"text": "➕ 新增收藏", "callback_data": "collections:add"}])
    buttons.append([{"text": "🔙 返回", "callback_data": "menu:collections"}])
    return "\n".join(lines), {"inline_keyboard": buttons}


# ---------------------------------------------------------------------------
# 新增／編輯（共用同一組多步驟流程）
# ---------------------------------------------------------------------------

def start_add(state_store: ConversationStateStore, telegram_user_id: int) -> tuple[str, dict]:
    state_store.set(
        telegram_user_id,
        {"flow": "collection", "step": "awaiting_item_type", "mode": "add", "target_id": None, "data": {}},
    )
    return _item_type_prompt(), None


def _item_type_prompt() -> str:
    lines = ["請選擇收藏類型："]
    for index, key in enumerate(_ITEM_TYPE_ORDER, start=1):
        lines.append(f"{index}. {_ITEM_TYPE_LABELS[key]}")
    return "\n".join(lines)


def start_edit(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, item_id: int) -> str:
    row = db.select(
        "collection_items",
        where="id = %s AND user_id = %s AND deleted_at IS NULL",
        params=(item_id, user_id),
        fetch_one=True,
    )
    if row is None:
        return "找不到這筆收藏，可能已經被刪除了。"

    state_store.set(
        telegram_user_id,
        {
            "flow": "collection",
            "step": "awaiting_item_type",
            "mode": "edit",
            "target_id": item_id,
            "data": {},
            "existing": dict(row),
        },
    )
    return f"目前名稱是「{row['title']}」，重新輸入完整內容即可（不需要改的欄位重打一次原值）。\n\n{_item_type_prompt()}"


def start_delete_confirm(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, item_id: int) -> tuple[str, dict]:
    row = db.select(
        "collection_items",
        where="id = %s AND user_id = %s AND deleted_at IS NULL",
        params=(item_id, user_id),
        fetch_one=True,
    )
    if row is None:
        return "找不到這筆收藏，可能已經被刪除了。", menu.back_to_main_menu_keyboard()

    state_store.set(telegram_user_id, {"flow": "collection_delete_confirm", "target_id": item_id})
    keyboard = {
        "inline_keyboard": [
            [{"text": "✅ 確認刪除", "callback_data": f"collections:confirm_delete:{item_id}"}],
            [{"text": "❌ 取消", "callback_data": "collections:list"}],
        ]
    }
    return f"確定要刪除「{row['title']}」嗎？此動作無法復原（若已有探索歷史，歷史快照仍會保留）。", keyboard


def handle_delete_confirm_text(state_store: ConversationStateStore, telegram_user_id: int) -> tuple[str, dict]:
    """`collection_delete_confirm` 只接受按鈕操作；打字一律視為取消，比照 2b／2c 保守做法。"""
    state_store.clear(telegram_user_id)
    return "刪除確認請用上面的按鈕操作喔，這次先幫你取消了。", menu.back_to_main_menu_keyboard()


def handle_delete(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, item_id: int) -> tuple[str, dict]:
    state_store.clear(telegram_user_id)
    service = _service(db)
    try:
        service.delete(item_id, user_id)
    except CollectionNotFoundError as exc:
        return str(exc), menu.back_to_main_menu_keyboard()
    return "已刪除該筆收藏。", menu.back_to_main_menu_keyboard()


def _summary_text(data: dict[str, Any]) -> str:
    type_label = _ITEM_TYPE_LABELS.get(data["item_type"], data["item_type"])
    address = data.get("address") or "（未填）"
    geocode_line = ""
    if data.get("latitude") is not None:
        geocode_line = f"\n定位：{data.get('_geocode_precision_label', '已定位')}"
    elif data.get("address"):
        geocode_line = "\n定位：無法定位（略過）"
    source_url = data.get("source_url") or "（無）"
    cost = data.get("estimated_cost")
    cost_line = f"{cost:g} 元" if cost is not None else "（無）"
    notes = data.get("notes") or "（無）"
    return (
        "請確認以下內容：\n\n"
        f"類型：{type_label}\n"
        f"名稱：{data['title']}\n"
        f"國家／城市：{data['country_name']}／{data['city_name']}\n"
        f"地址：{address}{geocode_line}\n"
        f"參考網址：{source_url}\n"
        f"預估費用：{cost_line}\n"
        f"備註：{notes}"
    )


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
        return "好的，已結束收藏設定！", menu.back_to_main_menu_keyboard()

    if step == "awaiting_item_type":
        mapping = {str(i): key for i, key in enumerate(_ITEM_TYPE_ORDER, start=1)}
        choice = mapping.get(text.strip())
        if not choice:
            return f"請輸入 1～{len(_ITEM_TYPE_ORDER)} 之間的數字：", None
        data["item_type"] = choice
        state["step"] = "awaiting_title"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return "請輸入收藏名稱：", None

    if step == "awaiting_title":
        title = text.strip()
        if not title:
            return "名稱不可以是空白，請重新輸入：", None
        data["title"] = title
        state["step"] = "awaiting_country"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return "請輸入國家：", None

    if step == "awaiting_country":
        country = text.strip()
        if not country:
            return "國家不可以是空白，請重新輸入：", None
        data["country_name"] = country
        state["step"] = "awaiting_city"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return "請輸入區域／城市：", None

    if step == "awaiting_city":
        city = text.strip()
        if not city:
            return "區域／城市不可以是空白，請重新輸入：", None
        data["city_name"] = city
        state["step"] = "awaiting_address"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return "請輸入詳細地址（選填，可能無法精確辨識門牌或街道；不需要的話請輸入「略過」）：", None

    if step == "awaiting_address":
        if text.strip() in _SKIP_PHRASES:
            data["address"] = None
            state["step"] = "awaiting_source_url"
            state["data"] = data
            state_store.set(telegram_user_id, state)
            return "請輸入參考網址（選填，沒有的話請輸入「略過」）：", None
        data["address"] = text.strip()
        state["step"] = "awaiting_geocode_choice"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        keyboard = {
            "inline_keyboard": [
                [{"text": "📍 定位地址", "callback_data": "collections:geocode"}],
                [{"text": "⏭ 略過定位", "callback_data": "collections:skip_geocode"}],
            ]
        }
        return "已記下地址，要立即定位嗎？定位結果只會顯示行政區／鄉鎮市區為主的近似位置：", keyboard

    if step == "awaiting_source_url":
        if text.strip() in _SKIP_PHRASES:
            data["source_url"] = None
        else:
            data["source_url"] = text.strip()
        state["step"] = "awaiting_estimated_cost"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return "請輸入預估費用（新台幣，選填，沒有的話請輸入「略過」）：", None

    if step == "awaiting_estimated_cost":
        if text.strip() in _SKIP_PHRASES:
            data["estimated_cost"] = None
        else:
            try:
                data["estimated_cost"] = float(text.strip())
            except ValueError:
                return "請輸入數字，或輸入「略過」：", None
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
                [{"text": "✅ 確認送出", "callback_data": "collections:confirm_save"}],
                [{"text": "❌ 取消", "callback_data": "menu:main"}],
            ]
        }
        return _summary_text(data), keyboard

    raise ValueError(f"未知的對話狀態：{state}")


def handle_geocode_choice(
    db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, do_geocode: bool
) -> tuple[str, None]:
    """處理「📍 定位地址／⏭ 略過定位」按鈕；結果套用後繼續原本的文字輸入流程。"""
    state = state_store.get(telegram_user_id)
    if not state or state.get("flow") != "collection" or state.get("step") != "awaiting_geocode_choice":
        return "目前沒有進行中的收藏設定。", None
    data: dict[str, Any] = state.get("data", {})

    result_line = ""
    if do_geocode:
        service = _service(db)
        try:
            result = service.geocode(
                {
                    "address": data.get("address"),
                    "city_name": data["city_name"],
                    "country_name": data["country_name"],
                }
            )
            data["latitude"] = result["latitude"]
            data["longitude"] = result["longitude"]
            data["_geocode_precision_label"] = result["precision_label"]
            result_line = f"定位成功（{result['precision_label']}）。\n\n"
        except GeocodingError as exc:
            result_line = f"定位失敗：{exc}\n這筆收藏仍會列入「無法定位」，可以之後再重新定位。\n\n"

    state["step"] = "awaiting_source_url"
    state["data"] = data
    state_store.set(telegram_user_id, state)
    return f"{result_line}請輸入參考網址（選填，沒有的話請輸入「略過」）：", None


def handle_confirm_save(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int) -> tuple[str, dict]:
    state = state_store.get(telegram_user_id)
    if not state or state.get("flow") != "collection" or state.get("step") != "awaiting_confirm":
        return "目前沒有進行中的收藏設定。", menu.back_to_main_menu_keyboard()

    data = dict(state["data"])
    mode = state.get("mode", "add")
    target_id = state.get("target_id")
    payload = {k: v for k, v in data.items() if not k.startswith("_")}

    service = _service(db)
    state_store.clear(telegram_user_id)
    try:
        if mode == "edit" and target_id is not None:
            service.update(target_id, user_id, payload)
            return "已更新該筆收藏！", menu.back_to_main_menu_keyboard()
        service.create(user_id, payload)
        return "已新增收藏！", menu.back_to_main_menu_keyboard()
    except CollectionValidationError as exc:
        return f"儲存失敗：{exc}\n請重新從「收藏與旅遊」選單開始設定。", menu.back_to_main_menu_keyboard()
    except CollectionNotFoundError as exc:
        return str(exc), menu.back_to_main_menu_keyboard()


# ---------------------------------------------------------------------------
# 標記已造訪（不經行程，直接把收藏加入探索地圖，見 docs/ADR/debug/robinson.md）
# ---------------------------------------------------------------------------

def start_visit(db: CloudSQLClient, state_store: ConversationStateStore, telegram_user_id: int, user_id: int, item_id: int) -> tuple[str, dict | None]:
    row = db.select(
        "collection_items",
        where="id = %s AND user_id = %s AND deleted_at IS NULL",
        params=(item_id, user_id),
        fetch_one=True,
    )
    if row is None:
        return "找不到這筆收藏，可能已經被刪除了。", menu.back_to_main_menu_keyboard()
    if row.get("status") == "visited":
        return "這筆收藏已經標記過造訪了。", menu.back_to_main_menu_keyboard()

    state_store.set(
        telegram_user_id,
        {"flow": "collection_visit", "step": "awaiting_visited_date", "collection_item_id": item_id, "data": {}},
    )
    return f"要把「{row['title']}」標記為已造訪嗎？請輸入造訪日期（YYYY-MM-DD），輸入「今天」使用今天日期：", None


def handle_visit_step(
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
        return "好的，已取消標記造訪！", menu.back_to_main_menu_keyboard()

    if step == "awaiting_visited_date":
        if text.strip() in _TODAY_PHRASES:
            visited_on = datetime.now(_TAIWAN_TZ).date()
        else:
            try:
                visited_on = _date.fromisoformat(text.strip())
            except ValueError:
                return "日期格式不正確，請用「YYYY-MM-DD」，或輸入「今天」：", None
        data["visited_on"] = visited_on.isoformat()
        state["step"] = "awaiting_visit_notes"
        state["data"] = data
        state_store.set(telegram_user_id, state)
        return "有想補充的造訪備註嗎？沒有的話請輸入「略過」：", None

    if step == "awaiting_visit_notes":
        data["notes"] = None if text.strip() in _SKIP_PHRASES else text.strip()
        item_id = state["collection_item_id"]
        state_store.clear(telegram_user_id)
        service = _life_service(db)
        try:
            service.visit_collection(item_id, user_id, data)
        except LifeValidationError as exc:
            return f"標記失敗：{exc}", menu.back_to_main_menu_keyboard()
        except LifeNotFoundError as exc:
            return str(exc), menu.back_to_main_menu_keyboard()
        return "已標記造訪，探索地圖會顯示這個地點的座標標記（若收藏本身尚未定位成功，仍會列在「無法定位」清單）！", menu.back_to_main_menu_keyboard()

    raise ValueError(f"未知的對話狀態：{state}")
