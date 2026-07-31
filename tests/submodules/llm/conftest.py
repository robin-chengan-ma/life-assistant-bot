import pytest

from submodules.llm.client import LLMClient


@pytest.fixture(autouse=True)
def _reset_llm_rate_limit_history():
    """`LLMClient._call_history_by_key` 是 class 層級的共用狀態（見節流保護設計），
    測試之間如果不清空，不同測試用同一個 api_key（例如預設值 "fake-key"）會互相汙染彼此的
    節流計數，導致測試結果依執行順序而不穩定。每個測試前後都清空一次確保互相獨立。
    """
    LLMClient._call_history_by_key.clear()
    yield
    LLMClient._call_history_by_key.clear()
