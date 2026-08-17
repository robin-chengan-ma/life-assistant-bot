"""批次3（FR-45a／FR-48 方案A）目標解析工具測試。"""
from src.services.goal_parser import parse_goal_input


class _FakeLLMClient:
    def __init__(self, response_text=None, raise_error=False):
        self.response_text = response_text
        self.raise_error = raise_error
        self.last_prompt = None

    def generate_text(self, prompt):
        self.last_prompt = prompt
        if self.raise_error:
            raise RuntimeError("boom")
        return self.response_text


def test_parse_goal_input_finance_extracts_value_and_fixed_min_direction():
    llm_client = _FakeLLMClient(response_text="5000|TWD")
    result = parse_goal_input(llm_client, "這個月想存5000", "finance")
    assert result == {"target_value": 5000.0, "target_unit": "TWD", "target_direction": "min"}


def test_parse_goal_input_collections_extracts_count_and_fixed_min_direction():
    llm_client = _FakeLLMClient(response_text="5|count")
    result = parse_goal_input(llm_client, "這個月完成5個收藏", "collections")
    assert result == {"target_value": 5.0, "target_unit": "count", "target_direction": "min"}


def test_parse_goal_input_diet_extracts_value_unit_and_min_direction():
    llm_client = _FakeLLMClient(response_text="5|次|MIN")
    result = parse_goal_input(llm_client, "每週吃蔬菜5次", "diet")
    assert result == {"target_value": 5.0, "target_unit": "次", "target_direction": "min"}


def test_parse_goal_input_diet_extracts_value_unit_and_max_direction():
    llm_client = _FakeLLMClient(response_text="14000|大卡|MAX")
    result = parse_goal_input(llm_client, "這週熱量控制在14000大卡以內", "diet")
    assert result == {"target_value": 14000.0, "target_unit": "大卡", "target_direction": "max"}


def test_parse_goal_input_diet_invalid_direction_degrades_to_free_text():
    llm_client = _FakeLLMClient(response_text="14000|大卡|UNKNOWN")
    result = parse_goal_input(llm_client, "隨便寫", "diet")
    assert result == {"target_value": None, "target_unit": None, "target_direction": None}


def test_parse_goal_input_none_response_degrades_to_free_text():
    llm_client = _FakeLLMClient(response_text="NONE")
    result = parse_goal_input(llm_client, "我想變得更健康", "finance")
    assert result == {"target_value": None, "target_unit": None, "target_direction": None}


def test_parse_goal_input_malformed_response_degrades_to_free_text():
    llm_client = _FakeLLMClient(response_text="這句話沒有照格式回覆")
    result = parse_goal_input(llm_client, "隨便寫點什麼", "finance")
    assert result == {"target_value": None, "target_unit": None, "target_direction": None}


def test_parse_goal_input_llm_failure_degrades_to_free_text():
    llm_client = _FakeLLMClient(raise_error=True)
    result = parse_goal_input(llm_client, "這個月想存5000", "finance")
    assert result == {"target_value": None, "target_unit": None, "target_direction": None}


def test_parse_goal_input_diet_llm_failure_degrades_to_free_text():
    llm_client = _FakeLLMClient(raise_error=True)
    result = parse_goal_input(llm_client, "這週熱量控制在14000大卡以內", "diet")
    assert result == {"target_value": None, "target_unit": None, "target_direction": None}


def test_parse_goal_input_no_llm_client_degrades_to_free_text():
    result = parse_goal_input(None, "這個月想存5000", "finance")
    assert result == {"target_value": None, "target_unit": None, "target_direction": None}


def test_parse_goal_input_unknown_module_key_degrades_to_free_text():
    llm_client = _FakeLLMClient(response_text="5000|TWD")
    result = parse_goal_input(llm_client, "隨便的目標", "certificate")
    assert result == {"target_value": None, "target_unit": None, "target_direction": None}
