"""submodules/llm/client.py 的單元測試（AGENTS.md：wrapper 骨架的測試待 Phase 1 實際串接時補上，
現在 Step 1.3 開始真的呼叫這個 Client，所以在這裡一併補齊）。

不呼叫真正的 Gemini API，一律 mock `google.genai.Client`。

2026-07-31：移除 `generate_with_search()` 相關測試（見 docs/specs/submodules-core/SPEC.md ADR-8）。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.genai import errors as genai_errors

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


# --- 外部 API 重試機制（FR-19i，見 docs/specs/submodules-core/SPEC.md ADR-13）---


class _FlakyModels:
    """先拋出預先設定的例外若干次，之後才回傳正常 response，用來測試重試邏輯。"""

    def __init__(self, exceptions, response):
        self._exceptions = list(exceptions)
        self._response = response
        self.call_count = 0

    def generate_content(self, **kwargs):
        self.call_count += 1
        if self._exceptions:
            raise self._exceptions.pop(0)
        return self._response


def _make_flaky_client(monkeypatch, exceptions, response, api_key="retry-key"):
    flaky_models = _FlakyModels(exceptions, response)
    fake_genai_client = SimpleNamespace(models=flaky_models)
    monkeypatch.setattr(client_module.genai, "Client", lambda api_key: fake_genai_client)
    llm_client = LLMClient(api_key=api_key)
    return llm_client, flaky_models


def test_generate_text_retries_on_server_error_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(client_module.time, "sleep", mock_sleep)
    response = SimpleNamespace(text="哈囉！")
    server_error = genai_errors.ServerError(503, {"message": "overloaded"}, None)
    llm_client, flaky_models = _make_flaky_client(monkeypatch, [server_error], response)

    result = llm_client.generate_text("你好")

    assert result == "哈囉！"
    assert flaky_models.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_generate_text_retries_on_rate_limit_client_error(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(client_module.time, "sleep", mock_sleep)
    response = SimpleNamespace(text="哈囉！")
    rate_limit_error = genai_errors.ClientError(429, {"message": "rate limited"}, None)
    llm_client, flaky_models = _make_flaky_client(monkeypatch, [rate_limit_error], response)

    result = llm_client.generate_text("你好")

    assert result == "哈囉！"
    assert flaky_models.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_generate_text_does_not_retry_permanent_client_error(monkeypatch):
    """比照 ADR-8 實際排查過的情境：模型不存在（404）重試也沒用，應直接拋出、不浪費重試次數。"""
    mock_sleep = MagicMock()
    monkeypatch.setattr(client_module.time, "sleep", mock_sleep)
    response = SimpleNamespace(text="不會被回傳")
    not_found_error = genai_errors.ClientError(404, {"message": "model not found"}, None)
    llm_client, flaky_models = _make_flaky_client(monkeypatch, [not_found_error], response)

    with pytest.raises(genai_errors.ClientError):
        llm_client.generate_text("你好")

    assert flaky_models.call_count == 1
    mock_sleep.assert_not_called()


def test_generate_with_image_retries_on_server_error_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(client_module.time, "sleep", mock_sleep)
    response = SimpleNamespace(text="這是一張貓的照片")
    server_error = genai_errors.ServerError(500, {"message": "internal error"}, None)
    llm_client, flaky_models = _make_flaky_client(monkeypatch, [server_error], response)

    result = llm_client.generate_with_image("這是什麼？", image_bytes=b"fake-bytes")

    assert result == "這是一張貓的照片"
    assert flaky_models.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_generate_text_retries_on_connection_error_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(client_module.time, "sleep", mock_sleep)
    response = SimpleNamespace(text="哈囉！")
    llm_client, flaky_models = _make_flaky_client(monkeypatch, [ConnectionError("斷線")], response)

    result = llm_client.generate_text("你好")

    assert result == "哈囉！"
    assert flaky_models.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_generate_text_raises_after_exhausting_retries(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(client_module.time, "sleep", mock_sleep)
    response = SimpleNamespace(text="不會被回傳")
    server_errors = [genai_errors.ServerError(503, {"message": "overloaded"}, None) for _ in range(3)]
    llm_client, flaky_models = _make_flaky_client(monkeypatch, server_errors, response)

    with pytest.raises(genai_errors.ServerError):
        llm_client.generate_text("你好")

    assert flaky_models.call_count == 3
    assert mock_sleep.call_args_list == [((1,),), ((2,),)]


def test_quota_guard_error_is_not_retried(monkeypatch):
    """本地端節流保護（LLMQuotaGuardError）發生在真正呼叫 API 之前，不屬於「暫時性外部錯誤」，
    重試也沒有意義（門檻是時間窗口，不是立即重試就能解決），應直接拋出、不觸發任何 sleep。"""
    mock_sleep = MagicMock()
    monkeypatch.setattr(client_module.time, "sleep", mock_sleep)
    response = SimpleNamespace(text="哈囉！")
    llm_client, _fake_genai_client = _make_client(
        monkeypatch, response, api_key="quota-key", max_calls_per_minute=1
    )

    llm_client.generate_text("第一句")
    with pytest.raises(LLMQuotaGuardError):
        llm_client.generate_text("第二句")

    mock_sleep.assert_not_called()
