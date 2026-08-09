"""submodules/job104/client.py 的單元測試（見 robinson SPEC.md FR-34a、ADR-24 決策 4）。

不呼叫真正的 104 AJAX API，一律 mock `requests.get`（比照 `tests/submodules/newsfeed/test_client.py`
的既有慣例）。JSON 欄位假設尚未經過真實流量驗證，這裡固定用假設的回應格式測試「解析邏輯本身」
是否正確，而非驗證假設是否為真（那需要正式部署後才能確認，見 client.py 模組 docstring）。
"""
from unittest.mock import MagicMock

import requests

from submodules.job104 import client as client_module
from submodules.job104.client import (
    Job104Client,
    _is_retryable_requests_error,
    _normalize_url,
    _parse_years,
)


def _fake_response(json_data, *, raise_exc: Exception | None = None):
    response = MagicMock()
    response.json = MagicMock(return_value=json_data)
    if raise_exc is not None:
        response.raise_for_status = MagicMock(side_effect=raise_exc)
    else:
        response.raise_for_status = MagicMock()
    return response


# --- search_list ---


def test_search_list_calls_requests_get_with_expected_params(monkeypatch):
    mock_get = MagicMock(return_value=_fake_response({"data": {"list": []}}))
    monkeypatch.setattr(client_module.requests, "get", mock_get)

    client = Job104Client()
    result = client.search_list("AI 工程師", region="台北市", salary_min=50000, salary_max=80000, industry="軟體業", page=2)

    assert result == []
    call_kwargs = mock_get.call_args.kwargs
    assert call_kwargs["params"] == {
        "keyword": "AI 工程師",
        "page": 2,
        "mode": "s",
        "jobsource": "joblist_search",
        "area": "台北市",
        "scmin": 50000,
        "scmax": 80000,
        "indcat": "軟體業",
    }
    assert call_kwargs["headers"]["User-Agent"]
    assert call_kwargs["headers"]["Referer"] == "https://www.104.com.tw/jobs/search/"
    assert call_kwargs["timeout"] == 10


def test_search_list_omits_optional_none_params(monkeypatch):
    mock_get = MagicMock(return_value=_fake_response({"data": {"list": []}}))
    monkeypatch.setattr(client_module.requests, "get", mock_get)

    Job104Client().search_list("AI 工程師")

    params = mock_get.call_args.kwargs["params"]
    assert set(params.keys()) == {"keyword", "page", "mode", "jobsource"}


def test_search_list_parses_jobs(monkeypatch):
    payload = {
        "data": {
            "list": [
                {
                    "jobNo": "12345",
                    "jobName": "AI 工程師",
                    "custNo": "999",
                    "custName": "某某科技",
                    "jobAddrNoDesc": "台北市信義區",
                    "link": {"job": "/job/12345"},
                }
            ]
        }
    }
    monkeypatch.setattr(client_module.requests, "get", MagicMock(return_value=_fake_response(payload)))

    result = Job104Client().search_list("AI 工程師")

    assert result == [
        {
            "job_id": "12345",
            "title": "AI 工程師",
            "company_id": "999",
            "company_name": "某某科技",
            "region": "台北市信義區",
            "url": "https://www.104.com.tw/job/12345",
        }
    ]


def test_search_list_skips_entries_without_job_id(monkeypatch):
    payload = {"data": {"list": [{"jobName": "缺編號的職缺"}]}}
    monkeypatch.setattr(client_module.requests, "get", MagicMock(return_value=_fake_response(payload)))

    assert Job104Client().search_list("AI 工程師") == []


def test_search_list_handles_missing_list_key(monkeypatch):
    monkeypatch.setattr(client_module.requests, "get", MagicMock(return_value=_fake_response({"data": {}})))

    assert Job104Client().search_list("AI 工程師") == []


# --- fetch_job_detail ---


def test_fetch_job_detail_calls_requests_get_with_job_page_referer(monkeypatch):
    mock_get = MagicMock(return_value=_fake_response({"data": {}}))
    monkeypatch.setattr(client_module.requests, "get", mock_get)

    Job104Client().fetch_job_detail("12345")

    assert mock_get.call_args.args[0] == "https://www.104.com.tw/job/ajax/content/12345"
    assert mock_get.call_args.kwargs["headers"]["Referer"] == "https://www.104.com.tw/job/12345"


def test_fetch_job_detail_parses_all_fields(monkeypatch):
    payload = {
        "data": {
            "jobDetail": {"jobDescription": "負責 AI 模型開發"},
            "welfare": {"welfare": "彈性上下班、年終獎金"},
            "condition": {"workExp": "3年以上"},
            "applyCnt": "12人應徵",
            "appearDate": "2026-08-09",
        }
    }
    monkeypatch.setattr(client_module.requests, "get", MagicMock(return_value=_fake_response(payload)))

    result = Job104Client().fetch_job_detail("12345")

    assert result == {
        "content": "負責 AI 模型開發\n彈性上下班、年終獎金",
        "required_years_experience": 3.0,
        "applicant_count": "12人應徵",
        "source_updated_at": "2026-08-09",
    }


def test_fetch_job_detail_missing_fields_returns_none_for_unknown_dimensions(monkeypatch):
    monkeypatch.setattr(client_module.requests, "get", MagicMock(return_value=_fake_response({"data": {}})))

    result = Job104Client().fetch_job_detail("12345")

    assert result == {
        "content": "",
        "required_years_experience": None,
        "applicant_count": None,
        "source_updated_at": None,
    }


# --- _parse_years ---


def test_parse_years_extracts_leading_number():
    assert _parse_years("3年以上") == 3.0
    assert _parse_years("1.5年以上") == 1.5


def test_parse_years_no_experience_required_returns_none():
    assert _parse_years("不拘") is None


def test_parse_years_empty_or_none_returns_none():
    assert _parse_years("") is None
    assert _parse_years(None) is None


# --- _normalize_url ---


def test_normalize_url_relative_path():
    assert _normalize_url("/job/12345") == "https://www.104.com.tw/job/12345"


def test_normalize_url_relative_path_without_leading_slash():
    assert _normalize_url("job/12345") == "https://www.104.com.tw/job/12345"


def test_normalize_url_already_absolute():
    assert _normalize_url("https://www.104.com.tw/job/12345") == "https://www.104.com.tw/job/12345"


def test_normalize_url_empty_string():
    assert _normalize_url("") == ""


# --- _is_retryable_requests_error ---


def test_is_retryable_connection_error():
    assert _is_retryable_requests_error(requests.exceptions.ConnectionError())


def test_is_retryable_timeout():
    assert _is_retryable_requests_error(requests.exceptions.Timeout())


def test_is_retryable_http_5xx():
    response = MagicMock(status_code=503)
    exc = requests.exceptions.HTTPError(response=response)
    assert _is_retryable_requests_error(exc)


def test_is_retryable_http_429():
    response = MagicMock(status_code=429)
    exc = requests.exceptions.HTTPError(response=response)
    assert _is_retryable_requests_error(exc)


def test_is_retryable_http_404_not_retryable():
    response = MagicMock(status_code=404)
    exc = requests.exceptions.HTTPError(response=response)
    assert not _is_retryable_requests_error(exc)


def test_is_retryable_other_exception_not_retryable():
    assert not _is_retryable_requests_error(ValueError("不相關的例外"))
