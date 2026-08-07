"""submodules/calendar/client.py 的單元測試。

不呼叫真正的 Google Calendar API，一律 mock `google.oauth2.credentials.Credentials` 與
`googleapiclient.discovery.build`（比照 submodules/gdrive 的測試手法，見
docs/specs/submodules-core/SPEC.md ADR-12）。
"""
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from submodules.calendar import client as client_module
from submodules.calendar.client import CalendarClient
from submodules.retry import client as retry_client_module


class _FakeEventsRequest:
    """execute_side_effects：若提供，依序拋出這些例外，用來測試重試邏輯；用完後才回傳 response。"""

    def __init__(self, response, execute_side_effects=None):
        self._response = response
        self._execute_side_effects = list(execute_side_effects or [])
        self.execute_call_count = 0

    def execute(self):
        self.execute_call_count += 1
        if self._execute_side_effects:
            raise self._execute_side_effects.pop(0)
        return self._response


class _FakeEvents:
    def __init__(self, response, execute_side_effects=None):
        self._response = response
        self._execute_side_effects = execute_side_effects
        self.last_insert_call = None
        self.last_update_call = None
        self.last_delete_call = None
        self.last_request = None

    def insert(self, calendarId, body):
        self.last_insert_call = {"calendarId": calendarId, "body": body}
        self.last_request = _FakeEventsRequest(self._response, self._execute_side_effects)
        return self.last_request

    def update(self, calendarId, eventId, body):
        self.last_update_call = {"calendarId": calendarId, "eventId": eventId, "body": body}
        self.last_request = _FakeEventsRequest(self._response, self._execute_side_effects)
        return self.last_request

    def delete(self, calendarId, eventId):
        self.last_delete_call = {"calendarId": calendarId, "eventId": eventId}
        self.last_request = _FakeEventsRequest(self._response, self._execute_side_effects)
        return self.last_request


class _FakeCalendarService:
    def __init__(self, response, execute_side_effects=None):
        self._events = _FakeEvents(response, execute_side_effects)

    def events(self):
        return self._events


def _make_client(
    monkeypatch,
    response=None,
    refresh_token="fake-refresh-token",
    client_id="fake-client-id",
    client_secret="fake-client-secret",
    calendar_id="fake-calendar-id",
    execute_side_effects=None,
):
    response = response or {"id": "event-abc123"}
    fake_service = _FakeCalendarService(response, execute_side_effects)

    captured_credentials_kwargs = {}

    def _fake_credentials(**kwargs):
        captured_credentials_kwargs.update(kwargs)
        return "fake-creds"

    monkeypatch.setattr(client_module, "Credentials", _fake_credentials)
    monkeypatch.setattr(client_module, "build", lambda *args, **kwargs: fake_service)

    calendar_client = CalendarClient(
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        calendar_id=calendar_id,
    )
    return calendar_client, fake_service, captured_credentials_kwargs


def test_init_raises_on_empty_refresh_token():
    with pytest.raises(ValueError):
        CalendarClient(refresh_token="", client_id="cid", client_secret="secret", calendar_id="cal")


def test_init_raises_on_empty_client_id():
    with pytest.raises(ValueError):
        CalendarClient(refresh_token="token", client_id="", client_secret="secret", calendar_id="cal")


def test_init_raises_on_empty_client_secret():
    with pytest.raises(ValueError):
        CalendarClient(refresh_token="token", client_id="cid", client_secret="", calendar_id="cal")


def test_init_raises_on_empty_calendar_id():
    with pytest.raises(ValueError):
        CalendarClient(refresh_token="token", client_id="cid", client_secret="secret", calendar_id="")


def test_init_builds_credentials_with_correct_oauth_params(monkeypatch):
    _, _, captured = _make_client(
        monkeypatch,
        refresh_token="my-refresh-token",
        client_id="my-client-id",
        client_secret="my-client-secret",
    )

    assert captured["token"] is None
    assert captured["refresh_token"] == "my-refresh-token"
    assert captured["client_id"] == "my-client-id"
    assert captured["client_secret"] == "my-client-secret"
    assert captured["token_uri"] == "https://oauth2.googleapis.com/token"
    assert captured["scopes"] == ["https://www.googleapis.com/auth/calendar.events"]


def test_create_event_returns_new_event_id(monkeypatch):
    calendar_client, _, _ = _make_client(monkeypatch, response={"id": "event-xyz"})

    event_id = calendar_client.create_event(
        summary="繳電費",
        start="2026-08-10T08:00:00+08:00",
        end="2026-08-10T09:00:00+08:00",
        description="來自 Robinson 待辦事項",
    )

    assert event_id == "event-xyz"


def test_create_event_sends_correct_timed_body(monkeypatch):
    calendar_client, fake_service, _ = _make_client(monkeypatch, calendar_id="my-calendar")

    calendar_client.create_event(
        summary="繳電費",
        start="2026-08-10T08:00:00+08:00",
        end="2026-08-10T09:00:00+08:00",
        description="來自 Robinson 待辦事項",
    )

    call = fake_service.events().last_insert_call
    assert call["calendarId"] == "my-calendar"
    assert call["body"] == {
        "summary": "繳電費",
        "description": "來自 Robinson 待辦事項",
        "start": {"dateTime": "2026-08-10T08:00:00+08:00", "timeZone": "Asia/Taipei"},
        "end": {"dateTime": "2026-08-10T09:00:00+08:00", "timeZone": "Asia/Taipei"},
    }


def test_create_event_sends_correct_all_day_body(monkeypatch):
    calendar_client, fake_service, _ = _make_client(monkeypatch)

    calendar_client.create_event(
        summary="爸爸生日",
        start="2026-09-12",
        end="2026-09-13",
        all_day=True,
    )

    call = fake_service.events().last_insert_call
    assert call["body"] == {
        "summary": "爸爸生日",
        "description": "",
        "start": {"date": "2026-09-12"},
        "end": {"date": "2026-09-13"},
    }


def test_update_event_sends_correct_body(monkeypatch):
    calendar_client, fake_service, _ = _make_client(monkeypatch, calendar_id="my-calendar")

    calendar_client.update_event(
        event_id="event-abc123",
        summary="繳電費（已改期）",
        start="2026-08-11T08:00:00+08:00",
        end="2026-08-11T09:00:00+08:00",
    )

    call = fake_service.events().last_update_call
    assert call["calendarId"] == "my-calendar"
    assert call["eventId"] == "event-abc123"
    assert call["body"] == {
        "summary": "繳電費（已改期）",
        "description": "",
        "start": {"dateTime": "2026-08-11T08:00:00+08:00", "timeZone": "Asia/Taipei"},
        "end": {"dateTime": "2026-08-11T09:00:00+08:00", "timeZone": "Asia/Taipei"},
    }


def test_delete_event_calls_correct_calendar_and_event(monkeypatch):
    calendar_client, fake_service, _ = _make_client(monkeypatch, calendar_id="my-calendar")

    calendar_client.delete_event(event_id="event-abc123")

    call = fake_service.events().last_delete_call
    assert call == {"calendarId": "my-calendar", "eventId": "event-abc123"}


# --- 外部 API 重試機制（FR-19i，見 docs/specs/submodules-core/SPEC.md ADR-13）---


def _http_error(status_code):
    fake_resp = MagicMock()
    fake_resp.status = status_code
    return HttpError(fake_resp, b"error body")


def test_create_event_retries_on_429_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    calendar_client, fake_service, _ = _make_client(
        monkeypatch, response={"id": "event-xyz"}, execute_side_effects=[_http_error(429)]
    )

    event_id = calendar_client.create_event(
        summary="繳電費", start="2026-08-10T08:00:00+08:00", end="2026-08-10T09:00:00+08:00"
    )

    assert event_id == "event-xyz"
    assert fake_service.events().last_request.execute_call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_update_event_does_not_retry_on_404(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    calendar_client, fake_service, _ = _make_client(
        monkeypatch, execute_side_effects=[_http_error(404)]
    )

    with pytest.raises(HttpError):
        calendar_client.update_event(
            event_id="event-abc123",
            summary="繳電費",
            start="2026-08-10T08:00:00+08:00",
            end="2026-08-10T09:00:00+08:00",
        )

    assert fake_service.events().last_request.execute_call_count == 1
    mock_sleep.assert_not_called()


def test_is_retryable_google_api_error_treats_http_error_without_status_as_non_retryable():
    fake_resp = MagicMock()
    fake_resp.status = None
    error = HttpError(fake_resp, b"error body")
    assert client_module._is_retryable_google_api_error(error) is False


def test_is_retryable_google_api_error_retries_connection_error():
    assert client_module._is_retryable_google_api_error(ConnectionError("斷線")) is True


def test_delete_event_raises_after_exhausting_retries(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    calendar_client, fake_service, _ = _make_client(
        monkeypatch, execute_side_effects=[_http_error(500), _http_error(500), _http_error(500)]
    )

    with pytest.raises(HttpError):
        calendar_client.delete_event(event_id="event-abc123")

    assert fake_service.events().last_request.execute_call_count == 3
    assert mock_sleep.call_args_list == [((1,),), ((2,),)]
