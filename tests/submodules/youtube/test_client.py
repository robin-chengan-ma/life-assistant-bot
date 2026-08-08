"""submodules/youtube/client.py 的單元測試。

不呼叫真正的 YouTube Data API，一律 mock `googleapiclient.discovery.build`；沿用
`submodules/gdrive` 既有的假 Request/Service 測試慣例（`execute_side_effects` 驗證重試邏輯）。
"""
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from submodules.youtube import client as client_module
from submodules.youtube.client import YouTubeClient


class _FakeRequest:
    def __init__(self, response, execute_side_effects=None):
        self._response = response
        self._execute_side_effects = list(execute_side_effects or [])
        self.execute_call_count = 0

    def execute(self):
        self.execute_call_count += 1
        if self._execute_side_effects:
            effect = self._execute_side_effects.pop(0)
            if isinstance(effect, Exception):
                raise effect
            return effect
        return self._response


class _FakeSearchResource:
    def __init__(self, response, execute_side_effects=None):
        self._response = response
        self._execute_side_effects = execute_side_effects
        self.last_call = None
        self.last_request = None

    def list(self, part, q, type, order, maxResults):
        self.last_call = {"part": part, "q": q, "type": type, "order": order, "maxResults": maxResults}
        self.last_request = _FakeRequest(self._response, self._execute_side_effects)
        return self.last_request


class _FakeVideosResource:
    def __init__(self, response, execute_side_effects=None):
        self._response = response
        self._execute_side_effects = execute_side_effects
        self.last_call = None
        self.last_request = None

    def list(self, part, id):
        self.last_call = {"part": part, "id": id}
        self.last_request = _FakeRequest(self._response, self._execute_side_effects)
        return self.last_request


class _FakeYouTubeService:
    def __init__(self, response, execute_side_effects=None):
        self._search_resource = _FakeSearchResource(response, execute_side_effects)
        self._videos_resource = _FakeVideosResource(response, execute_side_effects)

    def search(self):
        return self._search_resource

    def videos(self):
        return self._videos_resource


def _make_client(monkeypatch, response=None, api_key="fake-api-key", execute_side_effects=None):
    response = response or {"items": []}
    fake_service = _FakeYouTubeService(response, execute_side_effects)
    captured_build_kwargs = {}

    def _fake_build(*args, **kwargs):
        captured_build_kwargs["args"] = args
        captured_build_kwargs["kwargs"] = kwargs
        return fake_service

    monkeypatch.setattr(client_module, "build", _fake_build)

    youtube_client = YouTubeClient(api_key=api_key)
    return youtube_client, fake_service, captured_build_kwargs


def _http_error(status_code):
    resp = MagicMock()
    resp.status = status_code
    return HttpError(resp=resp, content=b"error")


# --- 建構子 ---


def test_constructor_rejects_empty_api_key():
    with pytest.raises(ValueError):
        YouTubeClient(api_key="")


def test_constructor_builds_service_with_api_key(monkeypatch):
    _client, _service, captured = _make_client(monkeypatch, api_key="secret-key")

    assert captured["args"] == ("youtube", "v3")
    assert captured["kwargs"]["developerKey"] == "secret-key"


# --- search_videos ---


def test_search_videos_parses_items(monkeypatch):
    response = {
        "items": [
            {
                "id": {"videoId": "abc123"},
                "snippet": {
                    "title": "AI Agent 架構設計",
                    "description": "介紹如何設計...",
                    "channelTitle": "Tech Channel",
                    "publishedAt": "2026-08-01T00:00:00Z",
                },
            }
        ]
    }
    youtube_client, service, _ = _make_client(monkeypatch, response=response)

    results = youtube_client.search_videos("AI Agent", max_results=10)

    assert results == [{
        "video_id": "abc123",
        "title": "AI Agent 架構設計",
        "description": "介紹如何設計...",
        "channel_title": "Tech Channel",
        "published_at": "2026-08-01T00:00:00Z",
        "url": "https://www.youtube.com/watch?v=abc123",
    }]
    assert service._search_resource.last_call == {
        "part": "snippet", "q": "AI Agent", "type": "video", "order": "relevance", "maxResults": 10,
    }


def test_search_videos_skips_items_without_video_id(monkeypatch):
    response = {"items": [{"id": {}, "snippet": {"title": "沒有 videoId"}}]}
    youtube_client, _service, _ = _make_client(monkeypatch, response=response)

    assert youtube_client.search_videos("query") == []


def test_search_videos_empty_response(monkeypatch):
    youtube_client, _service, _ = _make_client(monkeypatch, response={"items": []})
    assert youtube_client.search_videos("query") == []


def test_search_videos_retries_on_retryable_error_then_succeeds(monkeypatch):
    response = {"items": []}
    youtube_client, service, _ = _make_client(
        monkeypatch, response=response, execute_side_effects=[_http_error(503)],
    )

    results = youtube_client.search_videos("query")

    assert results == []
    assert service._search_resource.last_request.execute_call_count == 2


def test_search_videos_does_not_retry_non_retryable_error(monkeypatch):
    youtube_client, _service, _ = _make_client(
        monkeypatch, execute_side_effects=[_http_error(403)],
    )

    with pytest.raises(HttpError):
        youtube_client.search_videos("query")


# --- get_video_details ---


def test_get_video_details_empty_list_skips_api_call(monkeypatch):
    youtube_client, service, _ = _make_client(monkeypatch)

    results = youtube_client.get_video_details([])

    assert results == []
    assert service._videos_resource.last_call is None


def test_get_video_details_parses_items_with_statistics(monkeypatch):
    response = {
        "items": [
            {
                "id": "abc123",
                "snippet": {
                    "title": "AI Agent 架構設計",
                    "description": "介紹如何設計...",
                    "channelTitle": "Tech Channel",
                    "publishedAt": "2026-08-01T00:00:00Z",
                },
                "statistics": {"viewCount": "12345", "likeCount": "678", "commentCount": "90"},
            }
        ]
    }
    youtube_client, service, _ = _make_client(monkeypatch, response=response)

    results = youtube_client.get_video_details(["abc123"])

    assert results == [{
        "video_id": "abc123",
        "title": "AI Agent 架構設計",
        "description": "介紹如何設計...",
        "channel_title": "Tech Channel",
        "published_at": "2026-08-01T00:00:00Z",
        "view_count": 12345,
        "like_count": 678,
        "comment_count": 90,
        "url": "https://www.youtube.com/watch?v=abc123",
    }]
    assert service._videos_resource.last_call == {"part": "snippet,statistics", "id": "abc123"}


def test_get_video_details_multiple_ids_joined_with_comma(monkeypatch):
    youtube_client, service, _ = _make_client(monkeypatch, response={"items": []})

    youtube_client.get_video_details(["abc", "def", "ghi"])

    assert service._videos_resource.last_call["id"] == "abc,def,ghi"


def test_get_video_details_missing_statistics_defaults_to_zero(monkeypatch):
    response = {
        "items": [
            {
                "id": "abc123",
                "snippet": {"title": "沒開放讚數的影片"},
                "statistics": {"viewCount": "100"},
            }
        ]
    }
    youtube_client, _service, _ = _make_client(monkeypatch, response=response)

    results = youtube_client.get_video_details(["abc123"])

    assert results[0]["view_count"] == 100
    assert results[0]["like_count"] == 0
    assert results[0]["comment_count"] == 0


def test_get_video_details_retries_on_retryable_error_then_succeeds(monkeypatch):
    response = {"items": []}
    youtube_client, service, _ = _make_client(
        monkeypatch, response=response, execute_side_effects=[_http_error(429)],
    )

    results = youtube_client.get_video_details(["abc123"])

    assert results == []
    assert service._videos_resource.last_request.execute_call_count == 2


# --- _is_retryable_google_api_error（透過 HttpError 沒有 status 的邊界情況間接驗證） ---


def test_search_videos_http_error_without_status_not_retried(monkeypatch):
    resp = MagicMock()
    resp.status = None
    error = HttpError(resp=resp, content=b"error")
    youtube_client, _service, _ = _make_client(monkeypatch, execute_side_effects=[error])

    with pytest.raises(HttpError):
        youtube_client.search_videos("query")


def test_search_videos_connection_error_is_retried(monkeypatch):
    response = {"items": []}
    youtube_client, service, _ = _make_client(
        monkeypatch, response=response, execute_side_effects=[ConnectionError("network down")],
    )

    results = youtube_client.search_videos("query")

    assert results == []
    assert service._search_resource.last_request.execute_call_count == 2
