"""submodules/llm/client.py 的單元測試（AGENTS.md：wrapper 骨架的測試待 Phase 1 實際串接時補上，
現在 Step 1.3 開始真的呼叫這個 Client，所以在這裡一併補齊）。

不呼叫真正的 Gemini API，一律 mock `google.genai.Client`。
"""
from types import SimpleNamespace

import pytest

from submodules.llm import client as client_module
from submodules.llm.client import LLMClient


class _FakeModels:
    """模擬 genai.Client().models，記錄呼叫參數並回傳預先設定好的 response。"""

    def __init__(self, response):
        self._response = response
        self.last_call = None

    def generate_content(self, **kwargs):
        self.last_call = kwargs
        return self._response


class _FakeGenaiClient:
    def __init__(self, response):
        self.models = _FakeModels(response)


def _make_client(monkeypatch, response, api_key="fake-key"):
    fake_genai_client = _FakeGenaiClient(response)
    monkeypatch.setattr(client_module.genai, "Client", lambda api_key: fake_genai_client)
    llm_client = LLMClient(api_key=api_key)
    return llm_client, fake_genai_client


def test_init_raises_on_empty_api_key():
    with pytest.raises(ValueError):
        LLMClient(api_key="")


def test_generate_text_returns_response_text_and_calls_correct_model(monkeypatch):
    response = SimpleNamespace(text="哈囉！")
    llm_client, fake_genai_client = _make_client(monkeypatch, response)

    result = llm_client.generate_text("你好")

    assert result == "哈囉！"
    assert fake_genai_client.models.last_call["model"] == "gemini-flash-latest"
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
