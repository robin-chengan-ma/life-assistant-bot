"""Mobile App Phase 5：旅遊行程、探索地圖與成果展示服務。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from zoneinfo import ZoneInfo

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_TRIP_STATUSES = {"planning", "confirmed", "completed", "cancelled"}
_BUDGET_FIELDS = (
    "estimated_transport",
    "estimated_accommodation",
    "estimated_food",
    "estimated_tickets",
    "estimated_shopping",
    "estimated_other",
)
_ACHIEVEMENT_CATEGORIES = {"body", "exam", "exercise", "exploration", "trip", "todo", "other"}


class LifeDatabase(Protocol):
    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False): ...
    def insert(self, table, data, returning="id"): ...
    def update(self, table, data, where, params): ...
    def delete(self, table, where, params): ...
    def execute_query(self, query, params=None): ...


class LifeGeocoder(Protocol):
    def search(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class LifeExplorationError(Exception):
    """可安全回傳給 App 的生活探索錯誤。"""


class LifeValidationError(LifeExplorationError):
    """輸入不符合定案規則。"""


class LifeNotFoundError(LifeExplorationError):
    """資料不存在或不屬於目前使用者。"""


def _text(value: Any, label: str, *, required: bool = False, maximum: int = 2000) -> str | None:
    if value is None or value == "":
        if required:
            raise LifeValidationError(f"請輸入{label}")
        return None
    if not isinstance(value, str):
        raise LifeValidationError(f"{label}格式不正確")
    normalized = value.strip()
    if not normalized:
        if required:
            raise LifeValidationError(f"請輸入{label}")
        return None
    if len(normalized) > maximum:
        raise LifeValidationError(f"{label}不可超過 {maximum} 個字元")
    return normalized


def _iso_date(value: Any, label: str, *, required: bool = False) -> date | None:
    if value in (None, ""):
        if required:
            raise LifeValidationError(f"請選擇{label}")
        return None
    if not isinstance(value, str):
        raise LifeValidationError(f"{label}格式不正確")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LifeValidationError(f"{label}格式不正確") from exc


def _money(value: Any, label: str) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise LifeValidationError(f"{label}格式不正確")
    try:
        parsed = Decimal(str(value)).quantize(Decimal("1"))
    except (InvalidOperation, ValueError) as exc:
        raise LifeValidationError(f"{label}格式不正確") from exc
    if not parsed.is_finite() or parsed < 0 or parsed > Decimal("9999999999"):
        raise LifeValidationError(f"{label}超出允許範圍")
    return parsed


def _id_list(value: Any, label: str) -> list[int]:
    if value in (None, ""):
        return []
    if not isinstance(value, list) or len(value) > 100:
        raise LifeValidationError(f"{label}格式不正確")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int) or item <= 0:
            raise LifeValidationError(f"{label}格式不正確")
        if item not in result:
            result.append(item)
    return result


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


class AppLifeExplorationService:
    def __init__(self, db: LifeDatabase, geocoder: LifeGeocoder | None = None):
        self._db = db
        self._geocoder = geocoder

    def list_trips(self, user_id: int) -> dict[str, Any]:
        rows = self._db.execute_query(
            """/* app_life:list_trips */
            SELECT t.*,
              COALESCE((SELECT SUM(x.amount) FROM transactions x
                        WHERE x.trip_id = t.id AND x.user_id = t.user_id AND x.type = 'expense'), 0)
                AS actual_expense,
              COALESCE((SELECT SUM(x.amount) FROM transactions x WHERE x.trip_id = t.id AND x.user_id = t.user_id AND x.type = 'expense' AND x.category = '交通'), 0) AS actual_transport,
              COALESCE((SELECT SUM(x.amount) FROM transactions x WHERE x.trip_id = t.id AND x.user_id = t.user_id AND x.type = 'expense' AND x.category IN ('居住', '住宿')), 0) AS actual_accommodation,
              COALESCE((SELECT SUM(x.amount) FROM transactions x WHERE x.trip_id = t.id AND x.user_id = t.user_id AND x.type = 'expense' AND x.category = '餐飲'), 0) AS actual_food,
              COALESCE((SELECT SUM(x.amount) FROM transactions x WHERE x.trip_id = t.id AND x.user_id = t.user_id AND x.type = 'expense' AND x.category = '娛樂'), 0) AS actual_tickets,
              COALESCE((SELECT SUM(x.amount) FROM transactions x WHERE x.trip_id = t.id AND x.user_id = t.user_id AND x.type = 'expense' AND x.category = '購物'), 0) AS actual_shopping,
              COALESCE((SELECT SUM(x.amount) FROM transactions x WHERE x.trip_id = t.id AND x.user_id = t.user_id AND x.type = 'expense' AND x.category IN ('醫療', '其他')), 0) AS actual_other
            FROM trips t
            WHERE t.user_id = %s AND t.deleted_at IS NULL
            ORDER BY t.start_date NULLS FIRST, t.updated_at DESC, t.id DESC""",
            (user_id,),
        )
        for row in rows:
            row["items"] = self._db.execute_query(
                """/* app_life:trip_items */
                SELECT tci.collection_item_id, tci.sort_order, tci.visit_status,
                       tci.title_snapshot, ci.item_type, ci.country_name, ci.city_name, ci.address
                FROM trip_collection_items tci
                LEFT JOIN collection_items ci ON ci.id = tci.collection_item_id
                WHERE tci.trip_id = %s ORDER BY tci.sort_order, tci.id""",
                (row["id"],),
            )
            row["estimated_total"] = row.get("budget_amount") or sum(
                Decimal(str(row.get(field) or 0)) for field in _BUDGET_FIELDS
            )
            row["expense_difference"] = Decimal(str(row.get("actual_expense") or 0)) - Decimal(
                str(row["estimated_total"] or 0)
            )
        return {"trips": _serialize(rows)}

    def create_trip(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        data, collection_ids = self._validated_trip(payload, user_id)
        trip_id = self._db.insert("trips", {"user_id": user_id, **data})
        self._replace_trip_items(trip_id, user_id, collection_ids)
        return {"id": trip_id, "message": "旅遊行程已建立"}

    def update_trip(self, trip_id: int, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        self._owned("trips", trip_id, user_id)
        data, collection_ids = self._validated_trip(payload, user_id)
        self._db.update(
            "trips",
            {**data, "updated_at": datetime.now(_TAIWAN_TZ)},
            where="id = %s AND user_id = %s",
            params=(trip_id, user_id),
        )
        self._replace_trip_items(trip_id, user_id, collection_ids)
        return {"id": trip_id, "message": "旅遊行程已更新"}

    def delete_trip(self, trip_id: int, user_id: int) -> dict[str, Any]:
        self._owned("trips", trip_id, user_id)
        self._db.update(
            "trips", {"deleted_at": datetime.now(_TAIWAN_TZ)},
            where="id = %s AND user_id = %s", params=(trip_id, user_id),
        )
        return {"id": trip_id, "message": "旅遊行程已刪除", "undo_seconds": 5}

    def restore_trip(self, trip_id: int, user_id: int) -> dict[str, Any]:
        row = self._db.select("trips", where="id = %s AND user_id = %s", params=(trip_id, user_id), fetch_one=True)
        if row is None:
            raise LifeNotFoundError("找不到指定的旅遊行程")
        self._db.update("trips", {"deleted_at": None}, where="id = %s AND user_id = %s", params=(trip_id, user_id))
        return {"id": trip_id, "message": "旅遊行程已復原"}

    def complete_trip(self, trip_id: int, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        trip = self._owned("trips", trip_id, user_id)
        if not trip.get("start_date") or not trip.get("end_date"):
            raise LifeValidationError("完成行程前請先設定開始與結束日期")
        visited_ids = set(_id_list(payload.get("visited_collection_ids"), "造訪項目"))
        links = self._db.select("trip_collection_items", where="trip_id = %s", params=(trip_id,))
        allowed = {row.get("collection_item_id") for row in links}
        if not visited_ids.issubset(allowed):
            raise LifeValidationError("造訪項目不屬於此行程")
        for link in links:
            collection_id = link.get("collection_item_id")
            if collection_id in visited_ids:
                event_id = self._create_visit(user_id, collection_id, trip_id, trip["end_date"], None)
                self._db.update(
                    "trip_collection_items", {"visit_status": "visited", "visited_event_id": event_id},
                    where="id = %s", params=(link["id"],),
                )
            else:
                self._db.update(
                    "trip_collection_items", {"visit_status": "skipped"},
                    where="id = %s", params=(link["id"],),
                )
        self._db.update(
            "trips", {"status": "completed", "updated_at": datetime.now(_TAIWAN_TZ)},
            where="id = %s AND user_id = %s", params=(trip_id, user_id),
        )
        self._ensure_candidate(
            user_id, f"trip:{trip_id}", "trip", f"完成旅遊行程：{trip['title']}",
            "已完成一趟旅遊行程", trip["end_date"], "trip", trip_id,
        )
        return {"id": trip_id, "message": "行程已完成並建立探索紀錄", "visited_count": len(visited_ids)}

    def visit_collection(self, collection_id: int, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        visited_on = _iso_date(payload.get("visited_on"), "造訪日期", required=True)
        event_id = self._create_visit(user_id, collection_id, None, visited_on, payload.get("notes"))
        return {"id": event_id, "message": "已加入探索地圖"}

    def list_exploration(
        self, user_id: int, *, country_name: str | None = None, city_name: str | None = None
    ) -> dict[str, Any]:
        clauses = ["user_id = %s", "deleted_at IS NULL"]
        params: list[Any] = [user_id]
        if country_name:
            clauses.append("country_name = %s")
            params.append(country_name)
        if city_name:
            clauses.append("city_name = %s")
            params.append(city_name)
        rows = self._db.execute_query(
            f"""/* app_life:list_exploration */ SELECT * FROM exploration_events
            WHERE {' AND '.join(clauses)} ORDER BY start_date DESC, id DESC""",
            tuple(params),
        )
        markers: dict[str, dict[str, Any]] = {}
        unlocated: list[dict[str, Any]] = []
        for row in rows:
            if row.get("latitude") is None or row.get("longitude") is None:
                unlocated.append(row)
                continue
            key = f"{row['latitude']}:{row['longitude']}"
            marker = markers.setdefault(
                key,
                {"latitude": row["latitude"], "longitude": row["longitude"], "title": row["title"], "visits": []},
            )
            marker["visits"].append(row)
        return {
            "markers": _serialize(list(markers.values())),
            "unlocated": _serialize(unlocated),
            "filters": {
                "countries": sorted({row["country_name"] for row in rows if row.get("country_name")}),
                "cities": sorted({row["city_name"] for row in rows if row.get("city_name")}),
            },
        }

    def update_exploration(self, event_id: int, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        current = self._owned("exploration_events", event_id, user_id)
        address = _text(payload.get("address"), "地址", maximum=500)
        data: dict[str, Any] = {
            "start_date": _iso_date(payload.get("visited_on"), "造訪日期", required=True),
            "end_date": _iso_date(payload.get("visited_on"), "造訪日期", required=True),
            "notes": _text(payload.get("notes"), "備註"),
            "address": address,
            "updated_at": datetime.now(_TAIWAN_TZ),
        }
        if address != current.get("address"):
            data.update({"latitude": None, "longitude": None})
        self._db.update("exploration_events", data, where="id = %s AND user_id = %s", params=(event_id, user_id))
        return {"id": event_id, "message": "探索紀錄已更新"}

    def relocate_exploration(self, event_id: int, user_id: int) -> dict[str, Any]:
        row = self._owned("exploration_events", event_id, user_id)
        if self._geocoder is None:
            raise LifeValidationError("地址定位服務尚未設定")
        result = self._geocoder.search(
            {
                "address": row.get("address"),
                "city_name": row.get("city_name"),
                "country_name": row.get("country_name"),
            }
        )
        self._db.update(
            "exploration_events",
            {
                "latitude": result["latitude"],
                "longitude": result["longitude"],
                "updated_at": datetime.now(_TAIWAN_TZ),
            },
            where="id = %s AND user_id = %s",
            params=(event_id, user_id),
        )
        return {"id": event_id, "message": "探索地址已重新定位", **result}

    def delete_exploration(self, event_id: int, user_id: int) -> dict[str, Any]:
        self._soft_delete("exploration_events", event_id, user_id)
        return {"id": event_id, "message": "探索紀錄已刪除", "undo_seconds": 5}

    def restore_exploration(self, event_id: int, user_id: int) -> dict[str, Any]:
        self._restore("exploration_events", event_id, user_id)
        return {"id": event_id, "message": "探索紀錄已復原"}

    def list_achievements(self, user_id: int) -> dict[str, Any]:
        self._refresh_candidates(user_id)
        cards = self._db.select(
            "user_achievements", where="user_id = %s AND deleted_at IS NULL", params=(user_id,)
        )
        candidates = self._db.select(
            "achievement_candidates", where="user_id = %s AND status = 'pending'", params=(user_id,)
        )
        cards = sorted(cards, key=lambda row: (row.get("unlocked_on"), row.get("id")), reverse=True)
        return {"achievements": _serialize(cards), "candidates": _serialize(candidates)}

    def create_achievement(self, user_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        category = payload.get("category")
        if category not in _ACHIEVEMENT_CATEGORIES:
            raise LifeValidationError("請選擇成果類別")
        result_id = self._db.insert(
            "user_achievements",
            {
                "user_id": user_id,
                "achievement_id": None,
                "creation_source": "manual",
                "category": category,
                "title": _text(payload.get("title"), "成果名稱", required=True, maximum=120),
                "description": _text(payload.get("description"), "成果說明"),
                "unlocked_on": _iso_date(payload.get("completed_on"), "完成日期", required=True),
                "cover_image_url": _text(payload.get("cover_image_url"), "成果照片", maximum=2000),
                "source_type": "manual",
            },
        )
        return {"id": result_id, "message": "成果已建立"}

    def respond_candidate(self, candidate_id: int, user_id: int, accept: bool) -> dict[str, Any]:
        candidate = self._owned("achievement_candidates", candidate_id, user_id)
        if candidate.get("status") != "pending":
            raise LifeValidationError("此成果候選已處理")
        if accept:
            result_id = self._db.insert(
                "user_achievements",
                {
                    "user_id": user_id,
                    "achievement_id": None,
                    "creation_source": "suggested",
                    "category": candidate["category"],
                    "title": candidate["title"],
                    "description": candidate.get("description"),
                    "unlocked_on": candidate["completed_on"],
                    "source_type": candidate["source_type"],
                    "source_id": candidate.get("source_id"),
                },
            )
            self._db.update(
                "achievement_candidates", {"status": "accepted", "updated_at": datetime.now(_TAIWAN_TZ)},
                where="id = %s AND user_id = %s", params=(candidate_id, user_id),
            )
            return {"id": result_id, "message": "成果已建立"}
        self._db.update(
            "achievement_candidates", {"status": "rejected", "updated_at": datetime.now(_TAIWAN_TZ)},
            where="id = %s AND user_id = %s", params=(candidate_id, user_id),
        )
        return {"message": "已略過成果候選"}

    def delete_achievement(self, achievement_id: int, user_id: int) -> dict[str, Any]:
        self._soft_delete("user_achievements", achievement_id, user_id)
        return {"id": achievement_id, "message": "成果已刪除", "undo_seconds": 5}

    def restore_achievement(self, achievement_id: int, user_id: int) -> dict[str, Any]:
        self._restore("user_achievements", achievement_id, user_id)
        return {"id": achievement_id, "message": "成果已復原"}

    def _validated_trip(self, payload: dict[str, Any], user_id: int) -> tuple[dict[str, Any], list[int]]:
        status = payload.get("status", "planning")
        if status not in _TRIP_STATUSES:
            raise LifeValidationError("請選擇正確的行程狀態")
        start_date = _iso_date(payload.get("start_date"), "開始日期")
        end_date = _iso_date(payload.get("end_date"), "結束日期")
        if (start_date is None) != (end_date is None):
            raise LifeValidationError("開始與結束日期必須同時填寫")
        if start_date and end_date and end_date < start_date:
            raise LifeValidationError("結束日期不可早於開始日期")
        if status in {"confirmed", "completed"} and start_date is None:
            raise LifeValidationError("確認或完成行程前請設定日期")
        collection_ids = _id_list(payload.get("collection_item_ids"), "收藏項目")
        for collection_id in collection_ids:
            self._owned("collection_items", collection_id, user_id)
        budgets = {field: _money(payload.get(field), "預估支出") for field in _BUDGET_FIELDS}
        category_total = sum((value or Decimal(0)) for value in budgets.values())
        total = _money(payload.get("budget_amount"), "預估總支出")
        return {
            "title": _text(payload.get("title"), "行程名稱", required=True, maximum=120),
            "start_date": start_date,
            "end_date": end_date,
            "country_name": _text(payload.get("country_name"), "國家", required=True, maximum=100),
            "city_name": _text(payload.get("city_name"), "區域／城市", required=True, maximum=100),
            "budget_amount": total if total is not None else category_total,
            "currency_code": "TWD",
            "status": status,
            "notes": _text(payload.get("notes"), "備註"),
            **budgets,
        }, collection_ids

    def _replace_trip_items(self, trip_id: int, user_id: int, collection_ids: list[int]) -> None:
        previous = self._db.select("trip_collection_items", where="trip_id = %s", params=(trip_id,))
        previous_ids = {row.get("collection_item_id") for row in previous if row.get("collection_item_id")}
        self._db.delete("trip_collection_items", where="trip_id = %s", params=(trip_id,))
        for index, collection_id in enumerate(collection_ids):
            item = self._owned("collection_items", collection_id, user_id)
            self._db.insert(
                "trip_collection_items",
                {
                    "trip_id": trip_id,
                    "collection_item_id": collection_id,
                    "sort_order": index,
                    "title_snapshot": item["title"],
                },
            )
            if item.get("status") == "saved":
                self._db.update(
                    "collection_items", {"status": "added_to_trip", "updated_at": datetime.now(_TAIWAN_TZ)},
                    where="id = %s AND user_id = %s", params=(collection_id, user_id),
                )
        for removed_id in previous_ids - set(collection_ids):
            self._refresh_collection_status(removed_id, user_id)

    def _create_visit(
        self, user_id: int, collection_id: int, trip_id: int | None, visited_on: date, notes: Any
    ) -> int:
        item = self._owned("collection_items", collection_id, user_id)
        event_id = self._db.insert(
            "exploration_events",
            {
                "user_id": user_id,
                "trip_id": trip_id,
                "collection_item_id": collection_id,
                "event_type": item["item_type"],
                "title": item["title"],
                "start_date": visited_on,
                "end_date": visited_on,
                "country_code": item.get("country_code"),
                "country_name": item.get("country_name"),
                "city_name": item.get("city_name"),
                "address": item.get("address"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "source_url": item.get("source_url"),
                "notes": _text(notes, "造訪備註") if notes is not None else item.get("notes"),
            },
        )
        self._db.update(
            "collection_items", {"status": "visited", "visited_at": datetime.now(_TAIWAN_TZ)},
            where="id = %s AND user_id = %s", params=(collection_id, user_id),
        )
        return event_id

    def _refresh_collection_status(self, collection_id: int, user_id: int) -> None:
        rows = self._db.execute_query(
            """/* app_life:collection_status */
            SELECT
              EXISTS(SELECT 1 FROM exploration_events e WHERE e.collection_item_id = %s
                     AND e.user_id = %s AND e.deleted_at IS NULL) AS visited,
              EXISTS(SELECT 1 FROM trip_collection_items tci JOIN trips t ON t.id = tci.trip_id
                     WHERE tci.collection_item_id = %s AND t.user_id = %s
                       AND t.deleted_at IS NULL AND t.status <> 'cancelled') AS planned""",
            (collection_id, user_id, collection_id, user_id),
        )
        state = rows[0] if rows else {}
        status = "visited" if state.get("visited") else "added_to_trip" if state.get("planned") else "saved"
        self._db.update("collection_items", {"status": status}, where="id = %s AND user_id = %s", params=(collection_id, user_id))

    def _refresh_candidates(self, user_id: int) -> None:
        completed_trips = self._db.execute_query(
            "SELECT id, title, end_date FROM trips WHERE user_id = %s AND status = 'completed' AND deleted_at IS NULL",
            (user_id,),
        )
        for row in completed_trips:
            self._ensure_candidate(
                user_id, f"trip:{row['id']}", "trip", f"完成旅遊行程：{row['title']}",
                "已完成一趟旅遊行程", row.get("end_date") or date.today(), "trip", row["id"],
            )
        goals = self._db.execute_query(
            "SELECT id, target_description, updated_at::date AS completed_on FROM body_goals WHERE user_id = %s AND status = 'achieved'",
            (user_id,),
        )
        for row in goals:
            self._ensure_candidate(
                user_id, f"body_goal:{row['id']}", "body", f"完成體態目標：{row['target_description']}",
                row["target_description"], row["completed_on"], "body_goal", row["id"],
            )
        exam_rows = self._db.execute_query(
            """/* app_life:exam_goal_candidates */
            SELECT g.id AS goal_id, g.exam_type, g.target_score,
                   s.id AS score_id, s.score, s.exam_date
            FROM certificate_goals g
            JOIN exam_official_scores s
              ON s.user_id = g.user_id AND s.exam_type = g.exam_type
            WHERE g.user_id = %s AND g.target_score IS NOT NULL
            ORDER BY s.exam_date DESC, s.id DESC""",
            (user_id,),
        )
        for row in exam_rows:
            if self._score_reaches_target(row.get("score"), row.get("target_score")):
                self._ensure_candidate(
                    user_id,
                    f"certificate_goal:{row['goal_id']}:{row['score_id']}",
                    "exam",
                    f"達成 {row['exam_type']} 目標",
                    f"正式成績 {row['score']}，目標 {row['target_score']}",
                    row["exam_date"],
                    "certificate_goal",
                    row["goal_id"],
                )
        counts = self._db.execute_query(
            """SELECT
              (SELECT COUNT(*) FROM todos WHERE user_id = %s AND status = 'completed') AS todo_count,
              (SELECT COUNT(*) FROM exercise_logs WHERE user_id = %s) AS exercise_count,
              (SELECT COUNT(*) FROM exploration_events WHERE user_id = %s AND deleted_at IS NULL) AS exploration_count,
              (SELECT COUNT(DISTINCT country_name) FROM exploration_events
               WHERE user_id = %s AND deleted_at IS NULL AND country_name IS NOT NULL) AS country_count""",
            (user_id, user_id, user_id, user_id),
        )
        summary = counts[0] if counts else {}
        for category, source_type, count, thresholds, label in (
            ("todo", "todo", int(summary.get("todo_count") or 0), (10, 50, 100), "完成待辦"),
            ("exercise", "exercise", int(summary.get("exercise_count") or 0), (10, 30, 100), "累積運動紀錄"),
            ("exploration", "exploration", int(summary.get("exploration_count") or 0), (1, 10, 50), "探索地點"),
            ("exploration", "exploration", int(summary.get("country_count") or 0), (1, 5, 10), "探索國家"),
        ):
            for threshold in thresholds:
                if count >= threshold:
                    self._ensure_candidate(
                        user_id, f"{label}:{threshold}", category, f"{label} {threshold} 次",
                        f"已達成 {label} {threshold} 次", date.today(), source_type, None,
                    )

    def _ensure_candidate(
        self, user_id: int, key: str, category: str, title: str, description: str,
        completed_on: date, source_type: str, source_id: int | None,
    ) -> None:
        existing = self._db.select(
            "achievement_candidates", where="user_id = %s AND candidate_key = %s",
            params=(user_id, key), fetch_one=True,
        )
        if existing is None:
            self._db.insert(
                "achievement_candidates",
                {
                    "user_id": user_id, "candidate_key": key, "category": category, "title": title,
                    "description": description, "completed_on": completed_on, "source_type": source_type,
                    "source_id": source_id, "status": "pending",
                },
            )

    @staticmethod
    def _score_reaches_target(score: Any, target: Any) -> bool:
        actual = str(score or "").strip()
        expected = str(target or "").strip()
        if not actual or not expected:
            return False
        try:
            return Decimal(actual.replace(",", "")) >= Decimal(expected.replace(",", ""))
        except InvalidOperation:
            passing_words = {"通過", "合格", "pass", "passed"}
            return actual.casefold() == expected.casefold() or (
                expected.casefold() in passing_words and actual.casefold() in passing_words
            )

    def _owned(self, table: str, item_id: int, user_id: int) -> dict[str, Any]:
        row = self._db.select(table, where="id = %s AND user_id = %s", params=(item_id, user_id), fetch_one=True)
        if row is None:
            raise LifeNotFoundError("找不到指定資料")
        return row

    def _soft_delete(self, table: str, item_id: int, user_id: int) -> None:
        self._owned(table, item_id, user_id)
        self._db.update(
            table, {"deleted_at": datetime.now(_TAIWAN_TZ)},
            where="id = %s AND user_id = %s", params=(item_id, user_id),
        )

    def _restore(self, table: str, item_id: int, user_id: int) -> None:
        self._owned(table, item_id, user_id)
        self._db.update(table, {"deleted_at": None}, where="id = %s AND user_id = %s", params=(item_id, user_id))
