"""體態管理純邏輯（對應 docs/specs/SPEC.md FR-45／FR-45a／FR-46，Phase 6 第二批 2h）。

負責：身高／腰圍設定、體重/運動/飲食三個子功能的紀錄 CRUD（含補記/更新/刪除，從一開始就內建，
理由同記帳模組）、BMI 計算與分級、運動消耗卡路里與飲食三大營養素的 LLM 估算。不處理任何 Telegram
對話流程，那是 src/bot/commands.py 的責任，保持這個模組是純粹的資料操作與計算，方便獨立測試。

2026-11-26（ADR 再修正）：原本的「體態目標」（`body_goals`）設定/查詢/編輯/刪除與 FR-45 三種
預警情境（目標達成通知等）查明後從頭到尾沒有任何設定入口（純死碼，Telegram 機器人已大幅精簡、
Mobile App 從未實作對應畫面），經 Robin 確認後整段移除，連同 `body_goals` 資料表，詳見
docs/ADR/discuss/robinson.md。

2026-08-08 追加（FR-46 擴充）：新增腰圍（`waist_cm`）設定，設計比照身高——存在 `users` 表、
「設定一次、變動才修正」，不像體重需要每天記錄的歷史表。腰圍刻意定位為「參考指標、非必要」：
`calculate_bmi()` 不使用腰圍，缺少腰圍不影響 BMI 計算或任何既有功能。

2026-08-17 修正（Phase 6 第二批 2h，見 docs/ADR/discuss/robinson.md）：合理範圍改採 FR-46
最終定案數字——身高 140～200 公分（原本 220 上限過寬）、腰圍 50～150 公分（原本 40～200 過寬）、
體重新增上限 150 公斤（原本只有下限 40）；新增 `get_body_summary()` 供「我的體態紀錄」一次組出
身高／最新體重／腰圍／BMI 四項摘要；新增 `update_goal()` 供目標「✏️ 編輯」重新走一次目標值/
期限輸入後寫回，取代原本「要調整只能取消重設」的限制。

2026-08-04 經 AskUserQuestion 確認的設計決策：
① 運動消耗卡路里改用 LLM 估算（而非 MET 公式），符合 FR-56g 情境3「用自然口吻回覆＋估算免責
   聲明」的示範；`estimate_exercise_calories()` 呼叫端傳入的 `llm_client` 沿用一般聊天用的
   `GEMINI_API_BOT_KEY`，不新增專用 Key。
② 飲食三大營養素拆算同樣沿用 `GEMINI_API_BOT_KEY`（`estimate_diet_macros()`），理由同上：
   沒有食物資料庫，本來就只能靠 LLM 語意判斷，跟一般聊天共用額度可接受。
③ FR-45 預警情境：目標達成通知（體重目標在每次記體重時即時檢查；運動目標因為是「累積分鐘數」
   需要跨多筆紀錄加總，改成借用 `/healthz` 頻率的排程檢查）、BMI 異常提醒（記錄體重當下就地
   算出 BMI 附上健康提醒文字，不用排程）。原固定「期限前 7 天」提醒已由統一重要日排程取代。
④ 體態目標（`body_goals`）三種子功能共用一張表，用 `goal_type` 區分；體重目標額外存
   `baseline_value`（設定當下的體重）用來判斷「要瘦」還是「要增」的方向；飲食目標因為太主觀
   （例如「飲食完美控制」），這版不做自動達成判斷，只能由使用者手動標記完成/取消，這是已知的
   刻意簡化，記錄在此。
⑤ 運動目標的 `target_value` 語意是「累積運動分鐘數」（Robin 指出不是只有跑步，用公里數當單位
   對其他運動類型不通用，分鐘數才是各種運動都適用的共同單位）。

2026-08-17 運動紀錄改版（FR-47a，批次2，見 docs/ADR/discuss/robinson.md）：取代原本「時間／
熱量」雙頁籤設計，改成單一表單（持續時間必填／心率選填／補充內容選填）＋「是否交由 AI 計算
消耗熱量」開關；刪除「重訓強度與組數」特殊分支，改由「補充內容」自由文字承接，AI 估算時一併
參考。新增全域共用的 `exercise_categories` 類別表，取代原本寫死的固定類別字串；新增類別時採
兩段式同義詞合併——先做正規化字串比對，沒命中才呼叫 LLM 語意判斷是否為既有類別的同義詞，仍然
沒命中才新增一筆，LLM 失敗一律降級為新增（不擋下使用者的紀錄流程）。舊運動紀錄資料已於同批
migration 直接清空，不做欄位相容回填。
"""
import re
import unicodedata
from datetime import date
from zoneinfo import ZoneInfo

from submodules.cloudsql.client import CloudSQLClient

_TAIWAN_TZ = ZoneInfo("Asia/Taipei")

# FR-46 合理範圍檢查（2026-08-17 定案數字，見模組 docstring）。
_MIN_HEIGHT_CM = 140.0
_MAX_HEIGHT_CM = 200.0
_MIN_WEIGHT_KG = 40.0
_MAX_WEIGHT_KG = 150.0
# 2026-08-08 追加（FR-46 擴充）：腰圍合理範圍；2026-08-17 收斂為 50～150 公分（見模組 docstring）。
_MIN_WAIST_CM = 50.0
_MAX_WAIST_CM = 150.0

# BMI 分級標準（衛福部國健署標準），供 format_bmi_note() 組健康提醒文字。
_BMI_CATEGORIES: list[tuple[float, str]] = [
    (18.5, "過輕"),
    (24.0, "正常"),
    (27.0, "過重"),
    (30.0, "輕度肥胖"),
    (35.0, "中度肥胖"),
]
_BMI_SEVERE_LABEL = "重度肥胖"



# ---------------------------------------------------------------------------
# 身高（初始設定，變動才修正）
# ---------------------------------------------------------------------------


def is_height_reasonable(height_cm: float) -> bool:
    """FR-46 合理範圍檢查：成人身高約 140～200 公分。"""
    return _MIN_HEIGHT_CM <= height_cm <= _MAX_HEIGHT_CM


def height_range_text() -> str:
    """組出身高合理範圍的提示文字（含單位），供超出範圍時原地反問使用。"""
    return f"{_MIN_HEIGHT_CM:.0f}～{_MAX_HEIGHT_CM:.0f} 公分"


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
    """FR-46 合理範圍檢查：成人腰圍約 50～150 公分（比身高體重寬鬆，畢竟只是參考用途）。"""
    return _MIN_WAIST_CM <= waist_cm <= _MAX_WAIST_CM


def waist_range_text() -> str:
    """組出腰圍合理範圍的提示文字（含單位），供超出範圍時原地反問使用。"""
    return f"{_MIN_WAIST_CM:.0f}～{_MAX_WAIST_CM:.0f} 公分"


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
    """FR-46 合理範圍檢查：成人體重約 40～150 公斤（2026-08-17 新增上限）。"""
    return _MIN_WEIGHT_KG <= weight_kg <= _MAX_WEIGHT_KG


def weight_range_text() -> str:
    """組出體重合理範圍的提示文字（含單位），供超出範圍時原地反問使用。"""
    return f"{_MIN_WEIGHT_KG:.0f}～{_MAX_WEIGHT_KG:.0f} 公斤"


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


def get_body_summary(db: CloudSQLClient, user_id: int) -> dict:
    """FR-46（2026-08-17 新增）：「我的體態紀錄」一次組出身高／最新體重／腰圍／BMI 四項。
    體重抓最新一筆（不限今天）；BMI 缺身高或體重任一項就無法計算。回傳
    `{"height_cm", "weight_kg", "waist_cm", "bmi", "bmi_category"}`，缺紀錄的欄位為 None。"""
    height_cm = get_height(db, user_id)
    weight_kg = latest_weight(db, user_id)
    waist_cm = get_waist(db, user_id)
    bmi = None
    bmi_category = None
    if height_cm is not None and weight_kg is not None:
        bmi = calculate_bmi(weight_kg, height_cm)
        bmi_category = classify_bmi(bmi)
    return {
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "waist_cm": waist_cm,
        "bmi": bmi,
        "bmi_category": bmi_category,
    }


def format_body_summary(summary: dict) -> str:
    """把 `get_body_summary()` 的回傳值格式化成使用者看的文字，缺紀錄顯示「尚無紀錄」，
    BMI 無法計算時顯示「無法計算」。"""
    height_text = f"{summary['height_cm']:.1f} 公分" if summary["height_cm"] is not None else "尚無紀錄"
    weight_text = f"{summary['weight_kg']:.1f} 公斤" if summary["weight_kg"] is not None else "尚無紀錄"
    waist_text = f"{summary['waist_cm']:.1f} 公分" if summary["waist_cm"] is not None else "尚無紀錄"
    bmi_text = f"{summary['bmi']:.1f}（{summary['bmi_category']}）" if summary["bmi"] is not None else "無法計算"
    return (
        "這是你目前的體態紀錄：\n\n"
        f"身高：{height_text}\n"
        f"體重：{weight_text}\n"
        f"腰圍：{waist_text}\n"
        f"BMI：{bmi_text}"
    )


# ---------------------------------------------------------------------------
# 運動類別（FR-47a，2026-08-17 批次2，全域共用，見模組 docstring）
# ---------------------------------------------------------------------------


def _normalize_category_name(name: str) -> str:
    """正規化類別名稱供去重比對：trim、全形轉半形（NFKC）、大小寫統一。"""
    return unicodedata.normalize("NFKC", name.strip()).casefold()


def list_exercise_categories(db: CloudSQLClient) -> list[dict]:
    """查詢全部運動類別（全域共用，不分使用者），依名稱排序，供 Telegram 按鈕與 Mobile 下拉選單
    共用同一份清單。"""
    rows = db.select("exercise_categories")
    rows.sort(key=lambda row: row["name"])
    return rows


def find_or_create_exercise_category(db: CloudSQLClient, llm_client, raw_name: str) -> dict:
    """FR-47a 同義詞合併（2026-08-17 定案，兩段式）：使用者新增全域類別時，先做正規化字串比對，
    命中就直接沿用既有類別；沒命中才呼叫 LLM 判斷是否為既有類別的同義詞（例如「重量訓練」跟
    「重訓」），仍然沒命中才新增一筆。LLM 呼叫失敗（或沒有 `llm_client`）一律降級為直接新增，
    不能因為判斷失敗就擋下使用者的紀錄流程。回傳既有或新建立的類別列
    （`{"id", "name", "normalized_name"}`）。"""
    name = raw_name.strip()
    normalized = _normalize_category_name(name)
    existing = db.select(
        "exercise_categories", where="normalized_name = %s", params=(normalized,), fetch_one=True
    )
    if existing is not None:
        return existing

    categories = list_exercise_categories(db)
    if categories and llm_client is not None:
        options = "、".join(f"「{item['name']}」" for item in categories)
        prompt = (
            f"以下是既有的運動類別清單：{options}。使用者新輸入了一個運動類別「{name}」，請判斷這個"
            "類別是否為清單中某一個既有類別的同義詞（例如「重量訓練」跟「重訓」是同一件事）。如果"
            "是，只回覆該既有類別的名稱（跟清單中完全一樣的文字）；如果不是清單中任何一個類別的"
            "同義詞，只回覆 NONE，不要附加其他文字。"
        )
        try:
            response = (llm_client.generate_text(prompt) or "").strip()
        except Exception:  # noqa: BLE001 - LLM 失敗時降級為直接新增類別
            response = "NONE"
        matched = next((item for item in categories if item["name"] == response), None)
        if matched is not None:
            return matched

    new_id = db.insert("exercise_categories", {"name": name, "normalized_name": normalized})
    return {"id": new_id, "name": name, "normalized_name": normalized}


# ---------------------------------------------------------------------------
# 運動紀錄
# ---------------------------------------------------------------------------


def estimate_exercise_calories(
    llm_client,
    activity: str,
    duration_minutes: int,
    heart_rate: int | None,
    note: str | None = None,
) -> float | None:
    """呼叫 LLM 估算這次運動大約消耗的卡路里（決策①）。2026-08-17（FR-47a，批次2）：`note`
    取代原本只有重訓才傳的 `training_details`，任何類別的補充內容都會一併參考。回傳解析出的
    第一個數字；LLM 回覆無法解析出數字時回傳 None，呼叫端仍應正常存檔（`estimated_calories`
    存 NULL），不能因為估算失敗就擋下整筆紀錄。"""
    heart_rate_part = f"，心率約 {heart_rate} 下/分鐘" if heart_rate else "（沒有心率資料）"
    note_part = f"，補充內容為「{note}」" if note else ""
    prompt = (
        f"請估算一般成人做「{activity}」運動 {duration_minutes} 分鐘{heart_rate_part}{note_part}大約消耗多少大卡"
        "熱量，只要回覆一個數字（大卡），不要附加其他文字或單位。"
    )
    try:
        response = llm_client.generate_text(prompt)
    except Exception:  # noqa: BLE001 - 外部 LLM 失敗時降級為無估算值
        return None
    match = re.search(r"\d+(\.\d+)?", response or "")
    return float(match.group()) if match else None


def create_exercise_log(
    db: CloudSQLClient,
    user_id: int,
    category_id: int,
    activity: str,
    duration_minutes: int,
    heart_rate: int | None,
    note: str | None,
    calorie_source: str,
    estimated_calories: float | None,
    entry_date: date,
) -> int:
    """新增一筆運動紀錄（FR-47／FR-47a，2026-08-17 批次2改版）。`activity` 是類別名稱的
    denormalized 快照（寫入當下複製自 `exercise_categories.name`，方便清單顯示與既有分析
    查詢不用額外 JOIN）；`category_id` 才是類別管理與同義詞合併的權威來源。回傳新建列的 id。"""
    return db.insert(
        "exercise_logs",
        {
            "user_id": user_id,
            "category_id": category_id,
            "activity": activity,
            "duration_minutes": duration_minutes,
            "heart_rate": heart_rate,
            "note": note,
            "estimated_calories": estimated_calories,
            "calorie_source": calorie_source,
            "entry_date": entry_date,
        },
    )


def update_exercise_log(
    db: CloudSQLClient,
    log_id: int,
    category_id: int,
    activity: str,
    duration_minutes: int,
    heart_rate: int | None,
    note: str | None,
    calorie_source: str,
    estimated_calories: float | None,
) -> None:
    """更新一筆運動紀錄；`entry_date` 沿用原本記錄的那一天。"""
    db.update(
        "exercise_logs",
        {
            "category_id": category_id,
            "activity": activity,
            "duration_minutes": duration_minutes,
            "heart_rate": heart_rate,
            "note": note,
            "estimated_calories": estimated_calories,
            "calorie_source": calorie_source,
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
    """把運動紀錄清單格式化成使用者看的編號清單文字（2026-08-17 改版：不再區分時間／熱量兩種
    格式，統一顯示時長，熱量來源為人工輸入時附註說明）。"""
    if not logs:
        return "目前還沒有運動紀錄喔！"
    lines = ["這是你最近的運動紀錄：", ""]
    for index, item in enumerate(logs, start=1):
        calories = item.get("estimated_calories")
        source_part = "（人工輸入）" if item.get("calorie_source") == "manual" else ""
        calories_part = f"　約 {float(calories):.0f} 大卡{source_part}" if calories is not None else ""
        heart_rate_part = f"　心率 {item['heart_rate']}" if item.get("heart_rate") else ""
        lines.append(
            f"{index}. {item['entry_date']:%Y/%m/%d} {item['activity']} {item['duration_minutes']} 分鐘{heart_rate_part}{calories_part}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 飲食（含飲水）紀錄
# ---------------------------------------------------------------------------


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
    except Exception:  # noqa: BLE001 - 外部 LLM 失敗時保留飲食紀錄
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
    nutrition_source: str = "ai",
) -> int:
    """新增一筆飲食/飲水紀錄（FR-48），回傳新建列的 id。`macros` 只有 `entry_type == "food"` 時
    才需要傳（`estimate_diet_macros()` 的回傳值，或使用者自己填寫的四個數字），飲水紀錄一律傳
    None。`nutrition_source`（2026-08-16，Phase 6 第二批 2g）：`entry_type == "food"` 時依
    使用者選擇的 `"ai"`／`"manual"` 傳入；飲水紀錄一律寫死 `"manual"`（沿用 migration 0078
    對飲水的既有慣例）。"""
    macros = macros or {}
    return db.insert(
        "diet_logs",
        {
            "user_id": user_id,
            "entry_type": entry_type,
            "description": description,
            "water_ml": water_ml,
            "nutrition_source": nutrition_source if entry_type == "food" else "manual",
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


def format_diet_macro_note(macros: dict, nutrition_source: str = "ai") -> str:
    """組出記錄飲食後附加的營養拆算文案（FR-17c／FR-48）。`nutrition_source`（2026-08-16，
    Phase 6 第二批 2g）：`"ai"` 附上估算免責聲明；`"manual"` 是使用者自己填的數字，不是估算，
    改用平鋪直敘的文案，不加「可能會有誤差」這句。"""
    calories, protein, carbs, fat = (
        macros.get("estimated_calories"), macros.get("protein_g"), macros.get("carbs_g"), macros.get("fat_g")
    )
    if calories is None and protein is None and carbs is None and fat is None:
        return "這份餐點的營養成分這次沒能順利估算出來，不過已經幫你記錄好內容了！"
    parts = []
    if calories is not None:
        parts.append(f"熱量{'約 ' if nutrition_source == 'ai' else ''}{calories:.0f} 大卡")
    if protein is not None:
        parts.append(f"蛋白質{'約 ' if nutrition_source == 'ai' else ''}{protein:.0f} 克")
    if carbs is not None:
        parts.append(f"碳水化合物{'約 ' if nutrition_source == 'ai' else ''}{carbs:.0f} 克")
    if fat is not None:
        parts.append(f"脂肪{'約 ' if nutrition_source == 'ai' else ''}{fat:.0f} 克")
    if nutrition_source == "ai":
        return "、".join(parts) + "，這是估算值，可能會有誤差，僅供參考喔！"
    return "、".join(parts) + "（這是你自己填寫的數字）"
