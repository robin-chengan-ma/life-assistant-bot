"""Mobile App 今日紀錄 CRUD、重複偵測與資料權限服務。"""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from src.bot import body, finance, mood, privacy, todo

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_DUPLICATE_WINDOW = timedelta(minutes=10)
_MOOD_CODES = {code for code, _label in mood.MOOD_CATEGORIES}
_TODO_STATUSES = {"pending", "completed", "cancelled"}
_SINGLE_DAILY_KINDS = {"diet", "weight", "mood"}


class RecordsDatabase(Protocol):
    def select(self, table, columns=("*",), where=None, params=None, fetch_one=False): ...
    def insert(self, table, data, returning="id"): ...
    def update(self, table, data, where, params): ...
    def delete(self, table, where, params): ...


class AppRecordError(Exception):
    """Mobile 紀錄可預期錯誤。"""


class RecordValidationError(AppRecordError):
    """輸入欄位不符合規則。"""


class RecordNotFoundError(AppRecordError):
    """紀錄不存在或不屬於目前使用者。"""


class HistoricalRecordError(AppRecordError):
    """Mobile 不可異動非今日紀錄。"""


class DuplicateRecordError(AppRecordError):
    """10 分鐘內存在內容相同的疑似重複紀錄。"""


def _required_text(value: Any, label: str, *, max_length: int = 1000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecordValidationError(f"請輸入{label}")
    result = value.strip()
    if len(result) > max_length:
        raise RecordValidationError(f"{label}不可超過 {max_length} 個字元")
    return result


def _positive_int(value: Any, label: str, *, optional: bool = False, maximum: int | None = None) -> int | None:
    if optional and (value is None or value == ""):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RecordValidationError(f"{label}只能輸入正整數")
    result = int(value)
    if result <= 0 or result != value:
        raise RecordValidationError(f"{label}只能輸入正整數")
    if maximum is not None and result > maximum:
        raise RecordValidationError(f"{label}不可超過 {maximum}")
    return result


def _round_amount(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise RecordValidationError("金額只能輸入大於 0 的數字")
    return int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _rounded_int(value: Any, label: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise RecordValidationError(f"{label}只能輸入大於 0 的數字")
    result = int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if result < 1 or result > maximum:
        raise RecordValidationError(f"{label}僅能輸入 1 到 {maximum}")
    return result


def _diet_nutrition(value: Any, *, source: str) -> dict[str, float | int | None] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise RecordValidationError("營養估算資料格式不正確")
    result: dict[str, float | int | None] = {}
    for field in ("estimated_calories", "protein_g", "carbs_g", "fat_g"):
        number = value.get(field)
        if number is None and source == "manual":
            raise RecordValidationError("人工輸入時請完整填寫脂肪、碳水化合物、蛋白質與熱量")
        if number is None:
            result[field] = None
        elif isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
            raise RecordValidationError("營養估算資料格式不正確")
        elif field == "estimated_calories":
            try:
                result[field] = _rounded_int(number, "飲食熱量", maximum=10000)
            except RecordValidationError as exc:
                if source == "ai":
                    raise RecordValidationError("營養估算資料格式不正確") from exc
                raise
        elif number < 0 or number > 1000:
            raise RecordValidationError("三大營養素僅能輸入 0 到 1000.0 公克")
        else:
            result[field] = float(Decimal(str(number)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    return result


def _parse_due_at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise RecordValidationError("請選擇執行日期與時間")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise RecordValidationError("執行日期與時間格式不正確") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_TAIWAN_TZ)
    return parsed


class AppRecordService:
    def __init__(self, db: RecordsDatabase, *, llm_client=None, now: datetime | None = None):
        self._db = db
        self._llm = llm_client
        self._now = now or datetime.now(_TAIWAN_TZ)
        self._today = self._now.astimezone(_TAIWAN_TZ).date()

    def create(self, kind: str, user_id: int, payload: dict[str, Any], *, allow_duplicate: bool = False) -> dict:
        if kind == "weight":
            payload = self._with_preserved_body_values(user_id, payload)
        data, table, fingerprint = self._validated(kind, payload, user_id=user_id)
        if kind in _SINGLE_DAILY_KINDS and self._latest_today(table, user_id, kind=kind) is not None:
            raise RecordValidationError("今日已有紀錄，請更新原紀錄")
        if not allow_duplicate and self._is_duplicate(table, user_id, fingerprint):
            raise DuplicateRecordError("發現一筆可能重複的紀錄，確定仍要新增嗎？")
        record_id = self._insert(kind, table, user_id, data)
        if kind == "diet":
            self._sync_today_water(
                user_id,
                _positive_int(payload.get("water_ml"), "飲水量", optional=True, maximum=10000),
            )
        return {"id": record_id, "message": "紀錄已新增"}

    def update(
        self,
        kind: str,
        record_id: int,
        user_id: int,
        payload: dict[str, Any],
        *,
        allow_duplicate: bool = False,
    ) -> dict:
        row, table = self._owned(kind, record_id, user_id)
        self._ensure_editable(kind, row, user_id, table)
        if kind == "weight":
            payload = self._with_preserved_body_values(user_id, payload, current=row)
        data, _table, _fingerprint = self._validated(kind, payload, user_id=user_id)
        if not allow_duplicate and self._is_duplicate(table, user_id, _fingerprint, exclude_id=record_id):
            raise DuplicateRecordError("發現一筆可能重複的紀錄，確定仍要更新嗎？")
        data.pop("entry_date", None)
        data.pop("transaction_date", None)
        if kind in {"finance", "weight"}:
            data.pop("note", None)
        if kind == "weight" and data.get("waist_cm") is None:
            data.pop("waist_cm", None)
        if kind == "weight":
            height_cm = data.pop("height_cm", None)
            if height_cm is not None:
                self._db.update("users", {"height_cm": height_cm}, where="id = %s", params=(user_id,))
        if kind == "mood":
            data.pop("achievement_note", None)
        if kind == "todo":
            data = {"content": data["content"], "start_at": data["start_at"], "due_at": data["due_at"], "status": data["status"]}
        self._db.update(table, data, where="id = %s AND user_id = %s", params=(record_id, user_id))
        if kind == "diet":
            self._sync_today_water(
                user_id,
                _positive_int(payload.get("water_ml"), "飲水量", optional=True, maximum=10000),
            )
        return {"id": record_id, "message": "紀錄已更新"}

    def delete(self, kind: str, record_id: int, user_id: int) -> dict:
        row, table = self._owned(kind, record_id, user_id)
        self._ensure_editable(kind, row, user_id, table)
        self._db.delete(table, where="id = %s AND user_id = %s", params=(record_id, user_id))
        if kind == "diet":
            self._db.delete(
                "diet_logs",
                where="user_id = %s AND entry_date = %s AND entry_type = 'water'",
                params=(user_id, row["entry_date"]),
            )
        return {"message": "紀錄已刪除"}

    def _owned(self, kind: str, record_id: int, user_id: int) -> tuple[dict, str]:
        table = self._table(kind)
        row = self._db.select(table, where="id = %s AND user_id = %s", params=(record_id, user_id), fetch_one=True)
        if row is None:
            raise RecordNotFoundError("找不到指定紀錄")
        return row, table

    def _ensure_editable(self, kind: str, row: dict, user_id: int, table: str) -> None:
        if kind == "todo":
            return
        field = "transaction_date" if kind == "finance" else "entry_date"
        record_date = row.get(field)
        if record_date != self._today:
            raise HistoricalRecordError("若需異動其他日期的紀錄，請使用 Telegram。")
        if kind in _SINGLE_DAILY_KINDS:
            latest = self._latest_today(table, user_id, kind=kind)
            if latest is not None and latest.get("id") != row.get("id"):
                raise HistoricalRecordError("今日僅能異動最新一筆紀錄")

    def _validated(self, kind: str, payload: dict[str, Any], *, user_id: int) -> tuple[dict, str, tuple]:
        if kind == "todo":
            content = _required_text(payload.get("content"), "待辦內容")
            due_at = _parse_due_at(payload.get("due_at"))
            start_at = _parse_due_at(payload.get("start_at", payload.get("due_at")))
            if start_at > due_at:
                raise RecordValidationError("開始日期不可晚於結束日期")
            status = payload.get("status", "pending")
            if status not in _TODO_STATUSES:
                raise RecordValidationError("請選擇正確的待辦狀態")
            return {"content": content, "start_at": start_at, "due_at": due_at, "status": status}, "todos", (content, start_at, due_at)
        if kind == "finance":
            transaction_type = payload.get("type")
            if transaction_type not in {"expense", "income"}:
                raise RecordValidationError("請選擇收入或支出")
            category = payload.get("category")
            if category not in finance.categories_for_type(transaction_type):
                raise RecordValidationError("請選擇正確的記帳類別")
            amount = _round_amount(payload.get("amount"))
            trip_id = payload.get("trip_id")
            if trip_id not in (None, ""):
                if isinstance(trip_id, bool) or not isinstance(trip_id, int) or trip_id <= 0:
                    raise RecordValidationError("旅遊行程格式不正確")
                trip = self._db.select(
                    "trips",
                    where="id = %s AND user_id = %s AND deleted_at IS NULL",
                    params=(trip_id, user_id),
                    fetch_one=True,
                )
                if trip is None:
                    raise RecordValidationError("找不到指定的旅遊行程")
            else:
                trip_id = None
            return {"type": transaction_type, "category": category, "amount": amount, "note": None,
                    "trip_id": trip_id, "transaction_date": self._today}, "transactions", (
                        transaction_type, category, amount
                    )
        if kind == "diet":
            description = _required_text(payload.get("description"), "今日的飲食內容")
            description, _detected = privacy.mask_text(description)
            nutrition_source = payload.get("nutrition_source", "ai")
            if nutrition_source not in {"ai", "manual"}:
                raise RecordValidationError("營養資料來源不正確")
            macros = _diet_nutrition(payload.get("nutrition"), source=nutrition_source)
            if macros is None:
                estimated = body.estimate_diet_macros(self._llm, description) if self._llm else {}
                try:
                    macros = _diet_nutrition(estimated, source="ai") if estimated else {}
                except RecordValidationError:
                    macros = {field: None for field in ("estimated_calories", "protein_g", "carbs_g", "fat_g")}
            data = {"entry_type": "food", "description": description, "water_ml": None,
                    "nutrition_source": nutrition_source, "entry_date": self._today, **macros}
            return data, "diet_logs", (description,)
        if kind == "exercise":
            # 2026-08-17（FR-47a，批次2）：取代原本「時間／熱量」雙頁籤設計，改成單一表單＋
            # 「是否交由 AI 計算消耗熱量」開關；類別改吃全域共用的 `exercise_categories`
            # （既有類別傳 `category_id`，新增自訂類別傳 `custom_category`，同義詞合併見
            # `body.find_or_create_exercise_category()`，跟 Telegram 端共用同一支函式）。
            category_id = payload.get("category_id")
            custom_category = payload.get("custom_category")
            if custom_category not in (None, ""):
                category = body.find_or_create_exercise_category(
                    self._db, self._llm, _required_text(custom_category, "運動類別名稱", max_length=100)
                )
            elif category_id not in (None, ""):
                if isinstance(category_id, bool) or not isinstance(category_id, int) or category_id <= 0:
                    raise RecordValidationError("運動類別格式不正確")
                category = self._db.select("exercise_categories", where="id = %s", params=(category_id,), fetch_one=True)
                if category is None:
                    raise RecordValidationError("找不到指定的運動類別")
            else:
                raise RecordValidationError("請選擇運動類別")

            duration = _positive_int(payload.get("duration_minutes"), "持續時間")
            heart_rate = _positive_int(payload.get("heart_rate"), "心率", optional=True)
            note = payload.get("note")
            if note not in (None, ""):
                note, _detected = privacy.mask_text(_required_text(note, "補充內容", max_length=1000))
            else:
                note = None

            use_ai_calorie = payload.get("use_ai_calorie", True)
            if use_ai_calorie:
                calorie_source = "ai"
                calories = body.estimate_exercise_calories(
                    self._llm, category["name"], duration, heart_rate, note
                ) if self._llm else None
                if calories is not None:
                    try:
                        calories = _rounded_int(calories, "AI 估算消耗熱量", maximum=5000)
                    except RecordValidationError:
                        calories = None
            else:
                calorie_source = "manual"
                calories = _rounded_int(payload.get("calories"), "消耗熱量", maximum=5000)

            data = {"category_id": category["id"], "activity": category["name"], "duration_minutes": duration,
                    "heart_rate": heart_rate, "note": note, "estimated_calories": calories,
                    "calorie_source": calorie_source, "entry_date": self._today}
            return data, "exercise_logs", (category["id"], duration, heart_rate, note, calorie_source, calories)
        if kind == "weight":
            value = payload.get("weight_kg")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise RecordValidationError("未取得有效的體重值")
            rounded = round(float(value) + 1e-9, 1)
            if rounded < 40 or rounded > 150:
                raise RecordValidationError("體重僅能輸入 40.0 到 150.0 公斤")
            height_value = payload.get("height_cm")
            height_cm = None
            if height_value not in (None, ""):
                if isinstance(height_value, bool) or not isinstance(height_value, (int, float)) or not math.isfinite(height_value):
                    raise RecordValidationError("身高僅能輸入 140.0 到 200.0 公分")
                height_cm = round(float(height_value) + 1e-9, 1)
                if height_cm < 140 or height_cm > 200:
                    raise RecordValidationError("身高僅能輸入 140.0 到 200.0 公分")
            waist_value = payload.get("waist_cm")
            waist_cm = None
            if waist_value not in (None, ""):
                if isinstance(waist_value, bool) or not isinstance(waist_value, (int, float)) or not math.isfinite(waist_value):
                    raise RecordValidationError("腰圍僅能輸入 50.0 到 150.0 公分")
                waist_cm = round(float(waist_value) + 1e-9, 1)
                if waist_cm < 50 or waist_cm > 150:
                    raise RecordValidationError("腰圍僅能輸入 50.0 到 150.0 公分")
            return {"height_cm": height_cm, "weight_kg": rounded, "waist_cm": waist_cm, "entry_date": self._today,
                    "note": None}, "body_weight_logs", (rounded, waist_cm)
        if kind == "mood":
            category = payload.get("mood_category")
            if category not in _MOOD_CODES:
                raise RecordValidationError("請選擇心情類別")
            content = payload.get("content", "")
            if not isinstance(content, str) or len(content.strip()) > 2000:
                raise RecordValidationError("分享內容不可超過 2000 個字元")
            content, _detected = privacy.mask_text(content.strip())
            return {"mood_category": category, "content": content, "achievement_note": None,
                    "entry_date": self._today}, "mood_journals", (category, content)
        raise RecordValidationError("不支援的紀錄類型")

    def _insert(self, kind: str, table: str, user_id: int, data: dict) -> int:
        if kind == "todo":
            record_id = todo.create_todo(
                self._db, user_id, data["content"], data["due_at"], False, start_at=data["start_at"]
            )
            if data["status"] != "pending":
                self._db.update("todos", {"status": data["status"]}, where="id = %s AND user_id = %s",
                                params=(record_id, user_id))
            return record_id
        if kind == "finance":
            record_id = finance.create_transaction(
                self._db, user_id, data["type"], data["category"], data["amount"],
                None, data["transaction_date"],
            )
            if data.get("trip_id") is not None:
                self._db.update(
                    "transactions", {"trip_id": data["trip_id"]},
                    where="id = %s AND user_id = %s", params=(record_id, user_id),
                )
            return record_id
        if kind == "weight":
            height_cm = data.pop("height_cm", None)
            if height_cm is not None:
                self._db.update("users", {"height_cm": height_cm}, where="id = %s", params=(user_id,))
            return self._db.insert(table, {"user_id": user_id, **data})
        if kind == "mood":
            return mood.create_mood_journal(self._db, user_id, data["mood_category"], data["content"], data["entry_date"])
        return self._db.insert(table, {"user_id": user_id, **data})

    def _latest_today(self, table: str, user_id: int, *, kind: str | None = None) -> dict | None:
        where = "user_id = %s AND entry_date = %s"
        params: tuple[Any, ...] = (user_id, self._today)
        if kind == "diet":
            where += " AND entry_type = %s"
            params += ("food",)
        rows = self._db.select(
            table,
            where=where,
            params=params,
        )
        return max(rows, key=lambda row: int(row.get("id", 0))) if rows else None

    def _sync_today_water(self, user_id: int, water_ml: int | None) -> None:
        if water_ml is None:
            return
        existing = self._db.select(
            "diet_logs",
            where="user_id = %s AND entry_date = %s AND entry_type = %s",
            params=(user_id, self._today, "water"),
            fetch_one=True,
        )
        data = {
            "entry_type": "water",
            "description": "飲水",
            "water_ml": water_ml,
            "nutrition_source": "manual",
            "estimated_calories": None,
            "protein_g": None,
            "carbs_g": None,
            "fat_g": None,
            "entry_date": self._today,
        }
        if existing:
            self._db.update(
                "diet_logs",
                data,
                where="id = %s AND user_id = %s",
                params=(existing["id"], user_id),
            )
            return
        self._db.insert("diet_logs", {"user_id": user_id, **data})

    def _with_preserved_body_values(
        self,
        user_id: int,
        payload: dict[str, Any],
        *,
        current: dict | None = None,
    ) -> dict[str, Any]:
        resolved = dict(payload)
        rows = self._db.select("body_weight_logs", where="user_id = %s", params=(user_id,))
        latest = current or (max(rows, key=lambda row: int(row.get("id", 0))) if rows else {})
        user = self._db.select("users", columns=("height_cm",), where="id = %s", params=(user_id,), fetch_one=True) or {}
        if resolved.get("weight_kg") in (None, ""):
            resolved["weight_kg"] = latest.get("weight_kg")
        if current is None and resolved.get("waist_cm") in (None, ""):
            resolved["waist_cm"] = latest.get("waist_cm")
        if current is None and resolved.get("height_cm") in (None, ""):
            resolved["height_cm"] = user.get("height_cm")
        return resolved

    def _is_duplicate(self, table: str, user_id: int, fingerprint: tuple, *, exclude_id: int | None = None) -> bool:
        rows = self._db.select(table, where="user_id = %s AND created_at >= %s",
                               params=(user_id, self._now - _DUPLICATE_WINDOW))
        return any(row.get("id") != exclude_id and self._fingerprint(table, row) == fingerprint for row in rows)

    @staticmethod
    def _fingerprint(table: str, row: dict) -> tuple:
        if table == "todos": return (row.get("content", "").strip(), row.get("start_at"), row.get("due_at"))
        if table == "transactions": return (row.get("type"), row.get("category"), int(Decimal(str(row.get("amount"))).quantize(Decimal(1), rounding=ROUND_HALF_UP)))
        if table == "diet_logs": return (row.get("description", "").strip(),)
        if table == "exercise_logs":
            return (
                row.get("category_id"),
                row.get("duration_minutes"),
                row.get("heart_rate"),
                row.get("note"),
                row.get("calorie_source"),
                row.get("estimated_calories") if row.get("calorie_source") == "manual" else None,
            )
        if table == "body_weight_logs":
            waist = row.get("waist_cm")
            return (float(row.get("weight_kg")), float(waist) if waist is not None else None)
        return (row.get("mood_category"), row.get("content", "").strip())

    @staticmethod
    def _table(kind: str) -> str:
        tables = {"todo": "todos", "finance": "transactions", "diet": "diet_logs", "exercise": "exercise_logs",
                  "weight": "body_weight_logs", "mood": "mood_journals"}
        if kind not in tables:
            raise RecordValidationError("不支援的紀錄類型")
        return tables[kind]
