"""submodules/llm/client.py 的單元測試（AGENTS.md：wrapper 骨架的測試待 Phase 1 實際串接時補上，
現在 Step 1.3 開始真的呼叫這個 Client，所以在這裡一併補齊）。

不呼叫真正的 Gemini API，一律 mock `google.genai.Client`。
"""
from types import SimpleNamespace

import pytest

from submodules.llm import client as client_module
from submodules.llm.client import LLMClient, LLMQuotaGuardError


class _FakeModels:
    """模擬 genai.Client().models，記錄呼叫參數並回傳預先設定好的 response。"""

    def __init__(self, response):
        self._response = response
        self.last_call = None
        self.call_count = 0

    def generate_content(self, **kwargs):
        self.call_count += 1
        self.last_call = kwargs
        return self._response


class _FakeGenaiClient:
    def __init__(self, response):
        self.models = _FakeModels(response)


def _make_client(monkeypatch, response, api_key="fake-key", max_calls_per_minute=8):
    fake_genai_client = _FakeGenaiClient(response)
    monkeypatch.setattr(client_module.genai, "Client", lambda api_key: fake_genai_client)
    llm_client = LLMClient(api_key=api_key, max_calls_per_minute=max_calls_per_minute)
    return llm_client, fake_genai_client


def test_init_raises_on_empty_api_key():
    with pytest.raises(ValueError):
        LLMClient(api_key="")


def test_generate_text_returns_response_text_and_calls_correct_model(monkeypatch):
    response = SimpleNamespace(text="哈囉！")
    llm_client, fake_genai_client = _make_client(monkeypatch, response)

    result = llm_client.generate_text("你好")

    assert result == "哈囉！"
    assert fake_genai_client.models.last_call["model"] == "gemini-3.5-flash-lite"
    assert fake_genai_client.models.last_call["contents"] == "你好"


def test_generate_with_image_passes_image_part_and_prompt(monkeypatch):
    response = SimpleNamespace(text="這是一張貓的照片")
    llm_client, fake_genai_client = _make_client(monkeypatch, response)

    result = llm_client.generate_with_image("這是什麼？", image_bytes=b"fake-bytes", mime_type="image/png")

    assert result == "這是一張貓的照片"
    contents = fake_genai_client.models.last_call["contents"]
    assert contents[1] == "這是什麼？"


def test_generate_with_search_returns_text_and_true_when_search_used(monkeypatch):
    metadata = SimpleNamespace(web_search_queries=["今天天氣"])
    candidate = SimpleNamespace(grounding_metadata=metadata)
    response = SimpleNamespace(text="今天晴天", candidates=[candidate])
    llm_client, fake_genai_client = _make_client(monkeypatch, response)

    text, used_search = llm_client.generate_with_search("今天天氣如何？")

    assert text == "今天晴天"
    assert used_search is True
    # 確認有把 Google Search 工具帶進 config
    assert "config" in fake_genai_client.models.last_call
    # ADR-7：grounding 免費額度依模型世代分桶，Gemini 3 世代（_DEFAULT_MODEL）額度是 0，
    # generate_with_search 必須固定改用有免費額度的 Gemini 2.5 世代模型，不能用 self._model
    assert fake_genai_client.models.last_call["model"] == "gemini-2.5-flash-lite"


def test_generate_with_search_returns_false_when_no_search_queries(monkeypatch):
    metadata = SimpleNamespace(web_search_queries=[])
    candidate = SimpleNamespace(grounding_metadata=metadata)
    response = SimpleNamespace(text="知識庫就有答案", candidates=[candidate])
    llm_client, _ = _make_client(monkeypatch, response)

    text, used_search = llm_client.generate_with_search("記帳功能怎麼用？")

    assert used_search is False


def test_generate_with_search_returns_false_when_no_grounding_metadata(monkeypatch):
    candidate = SimpleNamespace(grounding_metadata=None)
    response = SimpleNamespace(text="正常回答", candidates=[candidate])
    llm_client, _ = _make_client(monkeypatch, response)

    _, used_search = llm_client.generate_with_search("隨便問點什麼")

    assert used_search is False


def test_generate_with_search_returns_false_when_no_candidates(monkeypatch):
    response = SimpleNamespace(text="正常回答", candidates=[])
    llm_client, _ = _make_client(monkeypatch, response)

    _, used_search = llm_client.generate_with_search("隨便問點什麼")

    assert used_search is False


# --- 本地端節流保護（避免明知道會被 Gemini 429 拒絕還是送出請求）---


def test_generate_text_raises_quota_guard_error_when_exceeding_local_limit(monkeypatch):
    response = SimpleNamespace(text="哈囉！")
    llm_client, fake_genai_client = _make_client(monkeypatch, response, api_key="key-a", max_calls_per_minute=2)

    llm_client.generate_text("第一句")
    llm_client.generate_text("第二句")
    with pytest.raises(LLMQuotaGuardError):
        llm_client.generate_text("第三句")

    # 第三次被本地端擋下來，不該真的呼叫底層 SDK，才是真正省到額度
    assert fake_genai_client.models.call_count == 2


def test_rate_limit_is_shared_across_instances_with_same_api_key(monkeypatch):
    response = SimpleNamespace(text="哈囉！")
    fake_genai_client = _FakeGenaiClient(response)
    monkeypatch.setattr(client_module.genai, "Client", lambda api_key: fake_genai_client)

    client_1 = LLMClient(api_key="key-b", max_calls_per_minute=1)
    client_2 = LLMClient(api_key="key-b", max_calls_per_minute=1)

    client_1.generate_text("第一句")  # 用掉這把 key 本分鐘唯一的額度
    with pytest.raises(LLMQuotaGuardError):
        client_2.generate_text("第二句")  # 即使是不同 instance，同一把 key 仍然共用節流計數


def test_rate_limit_is_independent_per_api_key(monkeypatch):
    response = SimpleNamespace(text="哈囉！")
    fake_genai_client = _FakeGenaiClient(response)
    monkeypatch.setattr(client_module.genai, "Client", lambda api_key: fake_genai_client)

    client_key_c = LLMClient(api_key="key-c", max_calls_per_minute=1)
    client_key_d = LLMClient(api_key="key-d", max_calls_per_minute=1)

    client_key_c.generate_text("用掉 key-c 的額度")
    # key-d 是不同的 Gemini 專案/額度池，不該被 key-c 的用量影響
    client_key_d.generate_text("key-d 應該還能正常呼叫")


def test_rate_limit_window_resets_after_time_passes(monkeypatch):
    response = SimpleNamespace(text="哈囉！")
    llm_client, _ = _make_client(monkeypatch, response, api_key="key-e", max_calls_per_minute=1)

    fake_now = [1000.0]
    monkeypatch.setattr(client_module.time, "monotonic", lambda: fake_now[0])

    llm_client.generate_text("第一句")
    with pytest.raises(LLMQuotaGuardError):
        llm_client.generate_text("太快了")

    fake_now[0] += 61  # 超過 60 秒視窗，舊紀錄應該過期
    llm_client.generate_text("視窗重置後應該可以再打")  # 不該再拋例外
