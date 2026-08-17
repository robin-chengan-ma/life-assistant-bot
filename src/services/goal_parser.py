"""批次3（FR-45a／FR-48 方案A：目標「結構化為主、LLM 輔助解析」）共用的目標值解析工具。

給定使用者輸入的自由文字目標敘述，嘗試用 LLM 抽出結構化的「目標數值＋單位＋方向」；抽得出來的
目標之後可以支援自動達成判斷（見 `src/bot/goals.py`、`src/bot/finance.py`、
`src/bot/collections.py`、`src/bot/body.py` 各自的達成判斷邏輯），抽不出來的目標退化成純文字
目標，只能使用者自己刪除結束。

`target_direction`（2026-08-17 補做，Robin 要求飲食目標也要能自動判斷）：
- `min`：目標是「至少要達到」這個數值，例如「每週吃蔬菜5次」「這個月存5000元」——數值越大越好。
- `max`：目標是「不能超過」這個數值，例如「這週熱量控制在14000大卡以內」——數值越小越好。
記帳／收藏清單語意固定是「至少要達到」，直接寫死回傳 `min`，不需要 LLM 額外判斷；飲食目標的
方向不固定，交給 LLM 從語意判斷。

LLM 呼叫失敗（逾時、額度用盡、回覆格式不符預期）一律降級為 `target_value=None`，比照
`body.estimate_exercise_calories()`／`body.find_or_create_exercise_category()` 的容錯風格，
不能因為解析失敗就擋下使用者的目標建立流程。
"""
import logging
import re

_logger = logging.getLogger(__name__)

_EMPTY_RESULT = {"target_value": None, "target_unit": None, "target_direction": None}

# finance／collections 語意固定為「至少要達到」，只需要抽數字/單位，方向寫死 min。
_PROMPTS: dict[str, str] = {
    "finance": (
        "使用者輸入了一句記帳目標敘述：「{text}」。請判斷這句話有沒有明確的金額數字目標（新台幣，"
        "例如「這個月想存5000」「淨結餘多存3000元」）。如果有，請用「數字|TWD」格式回覆（例如"
        "「5000|TWD」），數字不要千分位逗號或貨幣符號；如果沒有明確金額數字，只回覆 NONE，"
        "不要附加其他文字或說明。"
    ),
    "collections": (
        "使用者輸入了一句收藏清單目標敘述：「{text}」。請判斷這句話有沒有明確的「數量」目標"
        "（例如「這個月完成5個收藏」「造訪3個景點」）。如果有，請用「數字|count」格式回覆（例如"
        "「5|count」）；如果沒有明確數量，只回覆 NONE，不要附加其他文字或說明。"
    ),
}
_FIXED_DIRECTION: dict[str, str] = {"finance": "min", "collections": "min"}

# diet 語意不固定（有可能是上限也可能是下限），額外請 LLM 判斷方向。
_DIET_PROMPT = (
    "使用者輸入了一句飲食目標敘述：「{text}」。請判斷這句話有沒有明確的數值目標（例如熱量"
    "大卡、次數等，例如「這週熱量控制在14000大卡以內」「每週吃蔬菜5次」）。如果有，請用"
    "「數字|單位|方向」格式回覆，單位盡量簡短（例如「大卡」「次」），方向只能是 MIN（目標是"
    "至少要達到這個數值，數值越大越好，例如吃蔬菜次數）或 MAX（目標是不能超過這個數值，數值"
    "越小越好，例如熱量上限），例如「14000|大卡|MAX」或「5|次|MIN」；如果沒有明確數值，只回覆"
    "NONE，不要附加其他文字或說明。"
)


def parse_goal_input(llm_client, raw_text: str, module_key: str) -> dict:
    """回傳 `{"target_value": float|None, "target_unit": str|None, "target_direction":
    "min"|"max"|None}`。`module_key` 需為 finance／collections／diet 三種之一；未定義或
    `llm_client` 為 `None` 時直接降級為純文字目標。"""
    if llm_client is None:
        return dict(_EMPTY_RESULT)

    if module_key == "diet":
        return _parse_diet(llm_client, raw_text)

    prompt_template = _PROMPTS.get(module_key)
    if prompt_template is None:
        return dict(_EMPTY_RESULT)

    try:
        response = (llm_client.generate_text(prompt_template.format(text=raw_text)) or "").strip()
    except Exception:
        _logger.exception("目標解析（module_key=%s）呼叫 LLM 失敗，降級為純文字目標", module_key)
        return dict(_EMPTY_RESULT)

    if response.upper().startswith("NONE"):
        return dict(_EMPTY_RESULT)

    parts = response.split("|", 1)
    if len(parts) != 2:
        return dict(_EMPTY_RESULT)

    value_text, unit_text = parts[0].strip(), parts[1].strip()
    match = re.search(r"-?\d+(\.\d+)?", value_text)
    if not match:
        return dict(_EMPTY_RESULT)

    return {
        "target_value": float(match.group()),
        "target_unit": unit_text or None,
        "target_direction": _FIXED_DIRECTION[module_key],
    }


def _parse_diet(llm_client, raw_text: str) -> dict:
    try:
        response = (llm_client.generate_text(_DIET_PROMPT.format(text=raw_text)) or "").strip()
    except Exception:
        _logger.exception("目標解析（module_key=diet）呼叫 LLM 失敗，降級為純文字目標")
        return dict(_EMPTY_RESULT)

    if response.upper().startswith("NONE"):
        return dict(_EMPTY_RESULT)

    parts = response.split("|", 2)
    if len(parts) != 3:
        return dict(_EMPTY_RESULT)

    value_text, unit_text, direction_text = (part.strip() for part in parts)
    match = re.search(r"-?\d+(\.\d+)?", value_text)
    direction = direction_text.lower()
    if not match or direction not in ("min", "max"):
        return dict(_EMPTY_RESULT)

    return {"target_value": float(match.group()), "target_unit": unit_text or None, "target_direction": direction}
