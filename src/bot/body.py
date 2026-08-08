"""體態管理純邏輯（對應 docs/specs/robinson/SPEC.md FR-45～FR-48，Step 2.2）。

負責：身高／腰圍設定、體重/運動/飲食三個子功能的紀錄 CRUD（含補記/更新/刪除，從一開始就內建，
理由同記帳模組）、BMI 計算與分級、運動消耗卡路里與飲食三大營養素的 LLM 估算、體態目標（三個子
功能共用一張表）的設定/查詢/取消、FR-45 三種預警情境的判斷與推播。不處理任何 Telegram 對話流程，
那是 src/bot/commands.py 的責任，保持這個模組是純粹的資料操作與計算，方便獨立測試。

2026-08-08 追加（FR-46 擴充）：新增腰圍（`waist_cm`）設定，設計比照身高——存在 `users` 表、
「設定一次、變動才修正」，不像體重需要每天記錄的歷史表。腰圍刻意定位為「參考指標、非必要」：
`calculate_bmi()` 不使用腰圍，缺少腰圍不影響 BMI 計算或任何既有功能。

2026-08-04 經 AskUserQuestion 確認的設計決策：
① 運動消耗卡路里改用 LLM 估算（而非 MET 公式），符合 FR-56g 情境3「用自然口吻回覆＋估算免責
   聲明」的示範；`estimate_exercise_calories()` 呼叫端傳入的 `llm_client` 沿用一般聊天用的
   `GEMINI_API_BOT_KEY`，不新增專用 Key。
② 飲食三大營養素拆算同樣沿用 `GEMINI_API_BOT_KEY`（`estimate_diet_macros()`），理由同上：
   沒有食物資料庫，本來就只能靠 LLM 語意判斷，跟一般聊天共用額度可接受。
③ FR-45 預警情境：目標達成通知（體重目標在每次記體重時即時檢查；運動目標因為是「累積分鐘數」
   需要跨多筆紀錄加總，改成借用 `/healthz` 頻率的排程檢查）、目標期限將近提醒（期限前 7 天
   排程提醒一次，`body_goals.deadline_reminder_sent` 去重）、BMI 異常提醒（記錄體重當下就地
   算出 BMI 附上健康提醒文字，不用排程）。
④ 體態目標（`body_goals`）三種子功能共用一張表，用 `goal_type` 區分；體重目標額外存
   `baseline_value`（設定當下的體重）用來判斷「要瘦」還是「要增」的方向；飲食目標因為太主觀
   （例如「飲食完美控制」），這版不做自動達成判斷，只能由使用者手動標記完成/取消，這是已知的
   刻意簡化，記錄在此。
⑤ 運動目標的 `target_value` 語意是「累積運動分鐘數」（Robin 指出不是只有跑步，用公里數當單位
   對其他運動類型不通用，分鐘數才是各種運動都適用的共同單位）。
"""
import logging
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_logger = logging.getLogger(__name__)

# FR-46 合理範圍檢查：成人身高約 140～220 公分、體重約 40 公斤以上。
_MIN_HEIGHT_CM = 140.0
_MAX_HEIGHT_CM = 220.0
_MIN_WEIGHT_KG = 40.0
# 2026-08-08 追加（FR-46 擴充）：腰圍合理範圍，比身高體重寬鬆，因為只是參考指標、非必要欄位。
_MIN_WAIST_CM = 40.0
_MAX_WAIST_CM = 200.0

# BMI 分級標準（衛福部國健署標準），供 format_bmi_note() 組健康提醒文字。
_BMI_CATEGORIES: list[tuple[float, str]] = [
    (18.5, "過輕"),
    (24.0, "正常"),
    (27.0, "過重"),
    (30.0, "輕度肥胖"),
    (35.0, "中度肥胖"),
]
_BMI_SEVERE_LABEL = "重度肥胖"

# FR-48 飲食紀錄類型：食物需要營養拆算，飲水只記錄毫升數。
DIET_ENTRY_TYPES: list[tuple[str, str]] = [("food", "飲食"), ("water", "飲水")]
_DIET_TYPE_LABEL_BY_CODE = dict(DIET_ENTRY_TYPES)
_DIET_TYPE_CODE_BY_LABEL = {label: code for code, label in DIET_ENTRY_TYPES}

# FR-46～FR-48 體態目標三種類型（決策④）。
GOAL_TYPES: list[tuple[str, str]] = [("weight", "體重"), ("exercise", "運動"), ("diet", "飲食")]
_GOAL_TYPE_LABEL_BY_CODE = dict(GOAL_TYPES)
_GOAL_TYPE_CODE_BY_LABEL = {label: code for code, label in GOAL_TYPES}

# FR-45 目標期限提醒：期限前幾天提醒一次（決策③）。
_DEADLINE_REMINDER_DAYS_BEFORE = 7


# ---------------------------------------------------------------------------
# 身高（初始設定，變動才修正）
# ---------------------------------------------------------------------------


def is_height_reasonable(height_cm: float) -> bool:
    """FR-46 合理範圍檢查：成人身高約 140～220 公分。"""
    return _MIN_HEIGHT_CM <= height_cm <= _MAX_HEIGHT_CM


def set_height(db: CloudSQLClient, user_id: int, height_cm: float) -> None:
    """設定/修正使用者身高（FR-46）；呼叫端必須先呼叫 `is_height_reasonable()` 確認合理範圍，
    這裡不重複檢查（DB 層的 CHECK 約束是最後一道防線）。"""
    db.update("users", {"height_cm": height_cm}, where="id = %s", params=(user_id,))


def get_height(db: CloudSQLClient, user_id: int) -> float | None:
    """查詢使用者目前設定的身高；尚未設定時回傳 None。"""
    row = db.select("users", where="id = %s", params=(user_id,), fetch_one=True)
    if row is None:
        return None
    height = row.get("height_cm")
    return float(height) if height is not None else None


# ---------------------------------------------------------------------------
# 腰圍（2026-08-08 追加，FR-46 擴充：初始設定，變動才修正，設計比照身高）
#
# 腰圍只是參考指標、不是必要欄位——BMI 計算只需要身高體重，不使用腰圍。設計刻意跟身高完全
# 對稱（同樣存在 `users` 表、同樣「設定一次、變動才修正」，不像體重需要每天記錄的歷史表）。
# ---------------------------------------------------------------------------


def is_waist_reasonable(waist_cm: float) -> bool:
    """FR-46 合理範圍檢查：成人腰圍約 40～200 公分（比身高體重寬鬆，畢竟只是參考用途）。"""
    return _MIN_WAIST_CM <= waist_cm <= _MAX_WAIST_CM


def set_waist(db: CloudSQLClient, user_id: int, waist_cm: float) -> None:
    """設定/修正使用者腰圍；呼叫端必須先呼叫 `is_waist_reasonable()` 確認合理範圍，這裡不重複
    檢查（DB 層的 CHECK 約束是最後一道防線）。"""
    db.update("users", {"waist_cm": waist_cm}, where="id = %s", params=(user_id,))


def get_waist(db: CloudSQLClient, user_id: int) -> float | None:
    """查詢使用者目前設定的腰圍；尚未設定時回傳 None。"""
    row = db.select("users", where="id = %s", params=(user_id,), fetch_one=True)
    if row is None:
        return None
    waist = row.get("waist_cm")
    return float(waist) if waist is not None else None


# ---------------------------------------------------------------------------
# 體重紀錄與 BMI
# ---------------------------------------------------------------------------


def is_weight_reasonable(weight_kg: float) -> bool:
    """FR-46 合理範圍檢查：成人體重約 40 公斤以上。"""
    return weight_kg >= _MIN_WEIGHT_KG


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    """計算 BMI（體重 kg ÷ 身高 m 的平方）。"""
    height_m = height_cm / 100
    return weight_kg / (height_m**2)


def classify_bmi(bmi: float) -> str:
    """依衛福部國健署標準分級。"""
    for threshold, label in _BMI_CATEGORIES:
        if bmi < threshold:
            return label
    return _BMI_SEVERE_LABEL


def format_bmi_note(weight_kg: float, height_cm: float) -> str:
    """組出記錄體重後附加的 BMI 說明文字（FR-46：自動計算 BMI 並附標準說明）。"""
    bmi = calculate_bmi(weight_kg, height_cm)
    category = classify_bmi(bmi)
    return f"你的 BMI 是 {bmi:.1f}（{category}），提供你參考，實際健康狀況仍建議諮詢專業意見喔！"


def create_weight_log(db: CloudSQLClient, user_id: int, weight_kg: float, entry_date: date, note: str | None = None) -> int:
    """新增一筆體重紀錄（FR-46），回傳新建列的 id。`entry_date` 設計比照 `mood_journals.entry_date`，
    一律由呼叫端算好台灣時區日期後傳入。"""
    return db.insert(
        "body_weight_logs", {"user_id": user_id, "weight_kg": weight_kg, "entry_date": entry_date, "note": note}
    )


def update_weight_log(db: CloudSQLClient, log_id: int, weight_kg: float) -> None:
    """更新一筆體重紀錄的數值；`entry_date` 沿用原本記錄的那一天（比照 finance/mood 的更新做法）。"""
    db.update("body_weight_logs", {"weight_kg": weight_kg}, where="id = %s", params=(log_id,))


def delete_weight_log(db: CloudSQLClient, log_id: int) -> None:
    """刪除一筆體重紀錄。"""
    db.delete("body_weight_logs", where="id = %s", params=(log_id,))


def list_weight_logs(db: CloudSQLClient, user_id: int, limit: int = 10) -> list[dict]:
    """查詢某使用者最近的體重紀錄，依日期由新到舊排序。"""
    rows = db.select("body_weight_logs", where="user_id = %s", params=(user_id,))
    rows.sort(key=lambda row: (row["entry_date"], row["id"]), reverse=True)
    return rows[:limit]


def format_weight_log_list(logs: list[dict]) -> str:
    """把體重紀錄清單格式化成使用者看的編號清單文字。"""
    if not logs:
        return "目前還沒有體重紀錄喔！"
    lines = ["這是你最近的體重紀錄：", ""]
    for index, item in enumerate(logs, start=1):
        lines.append(f"{index}. {item['entry_date']:%Y/%m/%d} {float(item['weight_kg']):.1f} 公斤")
    return "\n".join(lines)


def latest_weight(db: CloudSQLClient, user_id: int) -> float | None:
    """查詢使用者最新一筆體重紀錄的數值，供目標達成判斷、飲食/運動估算等情境參考使用。"""
    logs = list_weight_logs(db, user_id, limit=1)
    return float(logs[0]["weight_kg"]) if logs else None


# ---------------------------------------------------------------------------
# 運動紀錄
# ---------------------------------------------------------------------------


def estimate_exercise_calories(llm_client, activity: str, duration_minutes: int, heart_rate: int | None) -> float | None:
    """呼叫 LLM 估算這次運動大約消耗的卡路里（決策①）。回傳解析出的第一個數字；LLM 回覆無法解析
    出數字時回傳 None，呼叫端仍應正常存檔（`estimated_calories` 存 NULL），不能因為估算失敗就擋下
    整筆紀錄。"""
    heart_rate_part = f"，心率約 {heart_rate} 下/分鐘" if heart_rate else "（沒有心率資料）"
    prompt = (
        f"請估算一般成人做「{activity}」運動 {duration_minutes} 分鐘{heart_rate_part}大約消耗多少大卡"
        "熱量，只要回覆一個數字（大卡），不要附加其他文字或單位。"
    )
    try:
        response = llm_client.generate_text(prompt)
    except Exception:
        return None
    match = re.search(r"\d+(\.\d+)?", response or "")
    return float(match.group()) if match else None


def create_exercise_log(
    db: CloudSQLClient,
    user_id: int,
    activity: str,
    duration_minutes: int,
    heart_rate: int | None,
    estimated_calories: float | None,
    entry_date: date,
) -> int:
    """新增一筆運動紀錄（FR-47），回傳新建列的 id。"""
    return db.insert(
        "exercise_logs",
        {
            "user_id": user_id,
            "activity": activity,
            "duration_minutes": duration_minutes,
            "heart_rate": heart_rate,
            "estimated_calories": estimated_calories,
            "entry_date": entry_date,
        },
    )


def update_exercise_log(
    db: CloudSQLClient, log_id: int, activity: str, duration_minutes: int, heart_rate: int | None, estimated_calories: float | None
) -> None:
    """更新一筆運動紀錄；`entry_date` 沿用原本記錄的那一天。"""
    db.update(
        "exercise_logs",
        {
            "activity": activity,
            "duration_minutes": duration_minutes,
            "heart_rate": heart_rate,
            "estimated_calories": estimated_calories,
        },
        where="id = %s",
        params=(log_id,),
    )


def delete_exercise_log(db: CloudSQLClient, log_id: int) -> None:
    """刪除一筆運動紀錄。"""
    db.delete("exercise_logs", where="id = %s", params=(log_id,))


def list_exercise_logs(db: CloudSQLClient, user_id: int, limit: int = 10) -> list[dict]:
    """查詢某使用者最近的運動紀錄，依日期由新到舊排序。"""
    rows = db.select("exercise_logs", where="user_id = %s", params=(user_id,))
    rows.sort(key=lambda row: (row["entry_date"], row["id"]), reverse=True)
    return rows[:limit]


def format_exercise_log_list(logs: list[dict]) -> str:
    """把運動紀錄清單格式化成使用者看的編號清單文字。"""
    if not logs:
        return "目前還沒有運動紀錄喔！"
    lines = ["這是你最近的運動紀錄：", ""]
    for index, item in enumerate(logs, start=1):
        calories = item.get("estimated_calories")
        calories_part = f"　約 {float(calories):.0f} 大卡" if calories is not None else ""
        lines.append(
            f"{index}. {item['entry_date']:%Y/%m/%d} {item['activity']} {item['duration_minutes']} 分鐘{calories_part}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 飲食（含飲水）紀錄
# ---------------------------------------------------------------------------


def format_diet_entry_type_prompt() -> str:
    """組出讓使用者選擇要記錄飲食還是飲水的編號清單文字。"""
    lines = ["要記錄飲食還是飲水呢？", ""]
    for index, (_, label) in enumerate(DIET_ENTRY_TYPES, start=1):
        lines.append(f"{index}. {label}")
    return "\n".join(lines)


def resolve_diet_entry_type(text: str) -> str | None:
    """把使用者輸入解析成飲食紀錄類型代碼；接受編號或直接輸入「飲食」「飲水」。"""
    text = text.strip()
    if text.isdigit():
        index = int(text)
        if 1 <= index <= len(DIET_ENTRY_TYPES):
            return DIET_ENTRY_TYPES[index - 1][0]
        return None
    return _DIET_TYPE_CODE_BY_LABEL.get(text)


def estimate_diet_macros(llm_client, description: str) -> dict:
    """呼叫 LLM 拆算這份食物大約的三大營養素與熱量（決策②）。回傳
    `{"estimated_calories", "protein_g", "carbs_g", "fat_g"}`，任何一項解析不到就是 None
    （呼叫端仍應正常存檔，估算失敗不擋下整筆紀錄）。"""
    prompt = (
        f"請估算「{description}」這份餐點大約的營養成分，用以下固定格式回覆，每行一個數字，"
        "不要附加其他文字：\n"
        "CALORIES: <大卡數字>\nPROTEIN: <蛋白質公克數字>\nCARBS: <碳水化合物公克數字>\nFAT: <脂肪公克數字>"
    )
    try:
        response = llm_client.generate_text(prompt) or ""
    except Exception:
        response = ""

    def _extract(field: str) -> float | None:
        match = re.search(rf"{field}\s*:\s*(\d+(\.\d+)?)", response, re.IGNORECASE)
        return float(match.group(1)) if match else None

    return {
        "estimated_calories": _extract("CALORIES"),
        "protein_g": _extract("PROTEIN"),
        "carbs_g": _extract("CARBS"),
        "fat_g": _extract("FAT"),
    }


def create_diet_log(
    db: CloudSQLClient,
    user_id: int,
    entry_type: str,
    description: str,
    entry_date: date,
    water_ml: int | None = None,
    macros: dict | None = None,
) -> int:
    """新增一筆飲食/飲水紀錄（FR-48），回傳新建列的 id。`macros` 只有 `entry_type == "food"` 時
    才需要傳（`estimate_diet_macros()` 的回傳值），飲水紀錄一律傳 None。"""
    macros = macros or {}
    return db.insert(
        "diet_logs",
        {
            "user_id": user_id,
            "entry_type": entry_type,
            "description": description,
            "water_ml": water_ml,
            "estimated_calories": macros.get("estimated_calories"),
            "protein_g": macros.get("protein_g"),
            "carbs_g": macros.get("carbs_g"),
            "fat_g": macros.get("fat_g"),
            "entry_date": entry_date,
        },
    )


def delete_diet_log(db: CloudSQLClient, log_id: int) -> None:
    """刪除一筆飲食/飲水紀錄。"""
    db.delete("diet_logs", where="id = %s", params=(log_id,))


def list_diet_logs(db: CloudSQLClient, user_id: int, limit: int = 10) -> list[dict]:
    """查詢某使用者最近的飲食/飲水紀錄，依日期由新到舊排序。"""
    rows = db.select("diet_logs", where="user_id = %s", params=(user_id,))
    rows.sort(key=lambda row: (row["entry_date"], row["id"]), reverse=True)
    return rows[:limit]


def format_diet_log_list(logs: list[dict]) -> str:
    """把飲食/飲水紀錄清單格式化成使用者看的編號清單文字。"""
    if not logs:
        return "目前還沒有飲食紀錄喔！"
    lines = ["這是你最近的飲食紀錄：", ""]
    for index, item in enumerate(logs, start=1):
        if item["entry_type"] == "water":
            lines.append(f"{index}. {item['entry_date']:%Y/%m/%d} 飲水 {item['water_ml']} 毫升")
        else:
            calories = item.get("estimated_calories")
            calories_part = f"　約 {float(calories):.0f} 大卡" if calories is not None else ""
            lines.append(f"{index}. {item['entry_date']:%Y/%m/%d} {item['description']}{calories_part}")
    return "\n".join(lines)


def format_diet_macro_note(macros: dict) -> str:
    """組出記錄飲食後附加的營養拆算＋估算免責聲明（FR-17c／FR-48）。"""
    calories, protein, carbs, fat = (
        macros.get("estimated_calories"), macros.get("protein_g"), macros.get("carbs_g"), macros.get("fat_g")
    )
    if calories is None and protein is None and carbs is None and fat is None:
        return "這份餐點的營養成分這次沒能順利估算出來，不過已經幫你記錄好內容了！"
    parts = []
    if calories is not None:
        parts.append(f"熱量約 {calories:.0f} 大卡")
    if protein is not None:
        parts.append(f"蛋白質約 {protein:.0f} 克")
    if carbs is not None:
        parts.append(f"碳水化合物約 {carbs:.0f} 克")
    if fat is not None:
        parts.append(f"脂肪約 {fat:.0f} 克")
    return "、".join(parts) + "，這是估算值，可能會有誤差，僅供參考喔！"


# ---------------------------------------------------------------------------
# 體態目標（三個子功能共用，決策④）
# ---------------------------------------------------------------------------


def format_goal_type_prompt() -> str:
    """組出讓使用者選擇要設定哪一種體態目標的編號清單文字。"""
    lines = ["請問你是要設定哪一種體態目標呢？", ""]
    for index, (_, label) in enumerate(GOAL_TYPES, start=1):
        lines.append(f"{index}. {label}")
    return "\n".join(lines)


def resolve_goal_type(text: str) -> str | None:
    """把使用者輸入解析成目標類型代碼；接受編號或直接輸入「體重」「運動」「飲食」。"""
    text = text.strip()
    if text.isdigit():
        index = int(text)
        if 1 <= index <= len(GOAL_TYPES):
            return GOAL_TYPES[index - 1][0]
        return None
    return _GOAL_TYPE_CODE_BY_LABEL.get(text)


def goal_type_label(code: str) -> str:
    """依代碼查回顯示用的中文標籤。"""
    return _GOAL_TYPE_LABEL_BY_CODE[code]


def create_goal(
    db: CloudSQLClient,
    user_id: int,
    goal_type: str,
    target_description: str,
    target_value: float | None = None,
    baseline_value: float | None = None,
    target_date: date | None = None,
    sync_to_calendar: bool = False,
) -> int:
    """新增一筆體態目標（FR-46～FR-48），回傳新建列的 id。`baseline_value` 只有 `goal_type ==
    "weight"` 時才需要傳（設定當下的體重，用來判斷要瘦還是要增，決策④）。

    `sync_to_calendar`（2026-08-05，見 robinson SPEC.md FR-66c、ADR-17）：使用者在設定流程中
    明確選擇要不要同步到 Google 家庭共用行事曆，MVP 不支援事後修改；實際建立 Calendar 事件、
    寫回 `google_calendar_event_id` 是呼叫端（`src/bot/commands.py`）的責任，本函式只負責記下
    這個布林選擇。沒有 `target_date` 的目標即使選了同步也沒有意義（沒有日期可以建事件），由
    呼叫端在反問流程裡自行決定要不要問這一題。
    """
    return db.insert(
        "body_goals",
        {
            "user_id": user_id,
            "goal_type": goal_type,
            "target_description": target_description,
            "target_value": target_value,
            "baseline_value": baseline_value,
            "target_date": target_date,
            "status": "active",
            "achieved_notified": False,
            "deadline_reminder_sent": False,
            "sync_to_calendar": sync_to_calendar,
        },
    )


def set_calendar_event_id(db: CloudSQLClient, goal_id: int, event_id: str) -> None:
    """記錄這筆體態目標對應的 Google Calendar 事件 ID（FR-66c），供之後達成/取消時刪除對應事件。"""
    db.update("body_goals", {"google_calendar_event_id": event_id}, where="id = %s", params=(goal_id,))


def list_active_goals(db: CloudSQLClient, user_id: int) -> list[dict]:
    """查詢某使用者所有進行中的體態目標。"""
    rows = db.select("body_goals", where="user_id = %s AND status = %s", params=(user_id, "active"))
    rows.sort(key=lambda row: row["id"], reverse=True)
    return rows


def format_goal_list(goals: list[dict]) -> str:
    """把體態目標清單格式化成使用者看的編號清單文字。"""
    if not goals:
        return "目前還沒有設定中的體態目標喔！"
    lines = ["這是你目前設定中的體態目標：", ""]
    for index, item in enumerate(goals, start=1):
        deadline_part = f"（期限：{item['target_date']:%Y/%m/%d}）" if item.get("target_date") else ""
        lines.append(f"{index}. [{goal_type_label(item['goal_type'])}] {item['target_description']}{deadline_part}")
    return "\n".join(lines)


def cancel_goal(db: CloudSQLClient, goal_id: int, calendar_client=None, google_calendar_event_id=None) -> None:
    """取消一筆體態目標（使用者明確確認後才會呼叫）。`google_calendar_event_id`（2026-08-05，
    見 FR-66c、ADR-17）由呼叫端傳入（`commands.py` 在列出清單時已經查過），這裡不重複查詢。"""
    db.update("body_goals", {"status": "cancelled"}, where="id = %s", params=(goal_id,))
    _delete_calendar_event_if_synced(calendar_client, google_calendar_event_id, goal_id)


def _delete_calendar_event_if_synced(calendar_client, google_calendar_event_id, goal_id: int) -> None:
    """FR-66c：目標達成或取消時，如果當初有同步到 Calendar，一併刪除對應事件。刪除失敗
    （`calendar_client` 為 `None` 或 API 例外）優雅降級，不影響目標狀態本身的更新。"""
    if not google_calendar_event_id or calendar_client is None:
        return
    try:
        calendar_client.delete_event(event_id=google_calendar_event_id)
    except Exception:
        _logger.exception(
            "刪除體態目標（id=%s）對應的 Google Calendar 事件失敗，目標狀態已成功更新不受影響", goal_id
        )


def _mark_goal_achieved(db: CloudSQLClient, goal_id: int, calendar_client=None, google_calendar_event_id=None) -> None:
    db.update("body_goals", {"status": "achieved", "achieved_notified": True}, where="id = %s", params=(goal_id,))
    _delete_calendar_event_if_synced(calendar_client, google_calendar_event_id, goal_id)


def check_weight_goal_achieved(
    db: CloudSQLClient, user_id: int, latest_weight_kg: float, calendar_client=None
) -> str | None:
    """FR-45 目標達成通知：體重目標在每次記體重時即時檢查（決策③）。方向由 `baseline_value`
    跟 `target_value` 的大小關係判斷：`target_value < baseline_value` 代表要瘦，達成條件是
    `latest_weight_kg <= target_value`；反之代表要增重，達成條件是 `latest_weight_kg >=
    target_value`。達成時立刻標記為 `achieved` 並回傳一句恭喜文字供呼叫端附加在回覆後面；
    沒有達成中的體重目標，或條件未達成，回傳 None。

    `calendar_client`（2026-08-05，見 FR-66c、ADR-17）：達成時如果這個目標當初有同步到
    Calendar，一併刪除對應事件（見 `_delete_calendar_event_if_synced()`）。
    """
    goals = db.select(
        "body_goals", where="user_id = %s AND goal_type = %s AND status = %s", params=(user_id, "weight", "active")
    )
    for goal in goals:
        target_value = goal.get("target_value")
        baseline_value = goal.get("baseline_value")
        if target_value is None or baseline_value is None:
            continue
        target_value, baseline_value = float(target_value), float(baseline_value)
        losing_weight = target_value < baseline_value
        achieved = latest_weight_kg <= target_value if losing_weight else latest_weight_kg >= target_value
        if achieved:
            _mark_goal_achieved(
                db, goal["id"], calendar_client=calendar_client,
                google_calendar_event_id=goal.get("google_calendar_event_id"),
            )
            return f"🎉 恭喜你達成體重目標「{goal['target_description']}」了！"
    return None


def check_and_push_exercise_goal_achievements(
    db: CloudSQLClient, telegram_client, now: datetime | None = None, calendar_client=None
) -> None:
    """FR-45 目標達成通知：運動目標是「累積分鐘數」（決策⑤），需要跨多筆紀錄加總，改成借用
    `/healthz` 頻率的排程檢查（不像體重目標能在單次記錄當下就地判斷）：加總該目標建立之後的所有
    `exercise_logs.duration_minutes`，達到或超過 `target_value` 就推播恭喜並標記 `achieved`。

    `calendar_client`（2026-08-05，見 FR-66c、ADR-17）：同步刪除已達成目標對應的 Calendar 事件。
    """
    now = now or datetime.now(timezone.utc)
    goals = db.select("body_goals", where="goal_type = %s AND status = %s", params=("exercise", "active"))
    for goal in goals:
        target_value = goal.get("target_value")
        if target_value is None:
            continue
        user = db.select("users", where="id = %s", params=(goal["user_id"],), fetch_one=True)
        if user is None or user.get("telegram_user_id") is None:
            continue

        created_at_local = goal["created_at"].astimezone(_TAIWAN_TZ).date()
        logs = db.select(
            "exercise_logs",
            where="user_id = %s AND entry_date >= %s",
            params=(goal["user_id"], created_at_local),
        )
        total_minutes = sum(row["duration_minutes"] for row in logs)
        if total_minutes >= float(target_value):
            _mark_goal_achieved(
                db, goal["id"], calendar_client=calendar_client,
                google_calendar_event_id=goal.get("google_calendar_event_id"),
            )
            telegram_client.send_text(
                chat_id=user["telegram_user_id"],
                text=f"🎉 恭喜你達成運動目標「{goal['target_description']}」了，累積運動了 {total_minutes} 分鐘！",
            )


def check_and_push_goal_deadline_reminders(db: CloudSQLClient, telegram_client, now: datetime | None = None) -> None:
    """FR-45 目標期限將近提醒（決策③）：適用所有有設定 `target_date` 的進行中目標，期限前
    `_DEADLINE_REMINDER_DAYS_BEFORE`（7）天固定提醒一次，`deadline_reminder_sent` 去重。

    比照 `finance.check_and_push_budget_alerts()` 的做法，借用 `/healthz` 既有的 10 分鐘 cron 頻率。
    """
    now = now or datetime.now(timezone.utc)
    today_local = now.astimezone(_TAIWAN_TZ).date()

    goals = db.select("body_goals", where="status = %s AND target_date IS NOT NULL", params=("active",))
    for goal in goals:
        if goal.get("deadline_reminder_sent"):
            continue
        target_date = goal["target_date"]
        if (target_date - today_local).days != _DEADLINE_REMINDER_DAYS_BEFORE:
            continue
        user = db.select("users", where="id = %s", params=(goal["user_id"],), fetch_one=True)
        if user is None or user.get("telegram_user_id") is None:
            continue

        telegram_client.send_text(
            chat_id=user["telegram_user_id"],
            text=(
                f"⏰ 提醒你，體態目標「{goal['target_description']}」還有 {_DEADLINE_REMINDER_DAYS_BEFORE} "
                f"天就到期限（{target_date:%Y/%m/%d}）囉，加油！"
            ),
        )
        db.update("body_goals", {"deadline_reminder_sent": True}, where="id = %s", params=(goal["id"],))
