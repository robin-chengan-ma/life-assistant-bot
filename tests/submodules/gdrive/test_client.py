"""submodules/gdrive/client.py 的單元測試。

不呼叫真正的 Google Drive API，一律 mock `google.oauth2.credentials.Credentials` 與
`googleapiclient.discovery.build`；`MediaIoBaseUpload` 只是包住 bytes 的輕量物件，
不會觸發網路請求，直接用真的沒關係。

2026-08-02：改用 OAuth 2.0（真人帳號身分）認證，取代原本的 Service Account 認證
（見 docs/specs/submodules-core/SPEC.md ADR-10），mock 對象與建構子參數同步更新。
"""
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload

from submodules.gdrive import client as client_module
from submodules.gdrive.client import GDriveClient
from submodules.retry import client as retry_client_module


class _FakeFilesCreateRequest:
    """execute_side_effects：若提供，依序拋出這些例外（或回傳值），用來測試重試邏輯；
    全部用完後才回傳 response。"""

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


class _FakeFiles:
    def __init__(self, response, execute_side_effects=None):
        self._response = response
        self._execute_side_effects = execute_side_effects
        self.last_create_call = None
        self.last_request = None
        self.last_list_call = None
        self.last_get_media_call = None

    def create(self, body, media_body, fields):
        self.last_create_call = {"body": body, "media_body": media_body, "fields": fields}
        self.last_request = _FakeFilesCreateRequest(self._response, self._execute_side_effects)
        return self.last_request

    def list(self, q, fields):
        self.last_list_call = {"q": q, "fields": fields}
        self.last_request = _FakeFilesCreateRequest(self._response, self._execute_side_effects)
        return self.last_request

    def get_media(self, fileId):
        self.last_get_media_call = {"fileId": fileId}
        self.last_request = _FakeFilesCreateRequest(self._response, self._execute_side_effects)
        return self.last_request


class _FakeDriveService:
    def __init__(self, response, execute_side_effects=None):
        self._files = _FakeFiles(response, execute_side_effects)

    def files(self):
        return self._files


def _make_client(
    monkeypatch,
    response=None,
    refresh_token="fake-refresh-token",
    client_id="fake-client-id",
    client_secret="fake-client-secret",
    folder_id="fake-folder",
    execute_side_effects=None,
):
    response = response or {"id": "abc123", "webViewLink": "https://drive.google.com/file/d/abc123/view"}
    fake_service = _FakeDriveService(response, execute_side_effects)

    captured_credentials_kwargs = {}

    def _fake_credentials(**kwargs):
        captured_credentials_kwargs.update(kwargs)
        return "fake-creds"

    monkeypatch.setattr(client_module, "Credentials", _fake_credentials)
    monkeypatch.setattr(client_module, "build", lambda *args, **kwargs: fake_service)

    gdrive_client = GDriveClient(
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        folder_id=folder_id,
    )
    return gdrive_client, fake_service, captured_credentials_kwargs


def test_init_raises_on_empty_refresh_token():
    with pytest.raises(ValueError):
        GDriveClient(refresh_token="", client_id="cid", client_secret="secret", folder_id="fake-folder")


def test_init_raises_on_empty_client_id():
    with pytest.raises(ValueError):
        GDriveClient(refresh_token="token", client_id="", client_secret="secret", folder_id="fake-folder")


def test_init_raises_on_empty_client_secret():
    with pytest.raises(ValueError):
        GDriveClient(refresh_token="token", client_id="cid", client_secret="", folder_id="fake-folder")


def test_init_raises_on_empty_folder_id():
    with pytest.raises(ValueError):
        GDriveClient(refresh_token="token", client_id="cid", client_secret="secret", folder_id="")


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


def test_upload_file_returns_web_view_link(monkeypatch):
    gdrive_client, _, _ = _make_client(monkeypatch)

    url = gdrive_client.upload_file(filename="test.jpg", content=b"fake-bytes", mime_type="image/jpeg")

    assert url == "https://drive.google.com/file/d/abc123/view"


def test_upload_file_sends_correct_metadata_and_folder(monkeypatch):
    gdrive_client, fake_service, _ = _make_client(monkeypatch, folder_id="my-folder-id")

    gdrive_client.upload_file(filename="test.jpg", content=b"fake-bytes", mime_type="image/jpeg")

    call = fake_service.files().last_create_call
    assert call["body"] == {"name": "test.jpg", "parents": ["my-folder-id"]}
    assert call["fields"] == "id, webViewLink"
    assert isinstance(call["media_body"], MediaIoBaseUpload)


# --- 外部 API 重試機制（FR-19i，見 docs/specs/submodules-core/SPEC.md ADR-13）---


def _http_error(status_code):
    fake_resp = MagicMock()
    fake_resp.status = status_code
    return HttpError(fake_resp, b"error body")


def test_upload_file_retries_on_5xx_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    gdrive_client, fake_service, _ = _make_client(
        monkeypatch, execute_side_effects=[_http_error(503)]
    )

    url = gdrive_client.upload_file(filename="test.jpg", content=b"fake-bytes", mime_type="image/jpeg")

    assert url == "https://drive.google.com/file/d/abc123/view"
    assert fake_service.files().last_request.execute_call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_upload_file_does_not_retry_on_403(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    gdrive_client, fake_service, _ = _make_client(
        monkeypatch, execute_side_effects=[_http_error(403)]
    )

    with pytest.raises(HttpError):
        gdrive_client.upload_file(filename="test.jpg", content=b"fake-bytes", mime_type="image/jpeg")

    assert fake_service.files().last_request.execute_call_count == 1
    mock_sleep.assert_not_called()


def test_is_retryable_google_api_error_treats_http_error_without_status_as_non_retryable():
    fake_resp = MagicMock()
    fake_resp.status = None
    error = HttpError(fake_resp, b"error body")
    assert client_module._is_retryable_google_api_error(error) is False


def test_is_retryable_google_api_error_retries_connection_error():
    assert client_module._is_retryable_google_api_error(ConnectionError("斷線")) is True


def test_upload_file_raises_after_exhausting_retries(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    gdrive_client, fake_service, _ = _make_client(
        monkeypatch, execute_side_effects=[_http_error(500), _http_error(500), _http_error(500)]
    )

    with pytest.raises(HttpError):
        gdrive_client.upload_file(filename="test.jpg", content=b"fake-bytes", mime_type="image/jpeg")

    assert fake_service.files().last_request.execute_call_count == 3
    assert mock_sleep.call_args_list == [((1,),), ((2,),)]


# --- list_files / download_file（2026-08-07，見 docs/specs/robinson/SPEC.md Step 3.2）---


def test_init_builds_credentials_with_file_and_readonly_scopes(monkeypatch):
    _, _, captured = _make_client(monkeypatch)

    assert captured["scopes"] == [
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive.readonly",
    ]


def test_list_files_returns_files_list(monkeypatch):
    response = {"files": [{"id": "f1", "name": "toeic_0001_write_1.png", "mimeType": "image/png"}]}
    gdrive_client, _, _ = _make_client(monkeypatch, response=response)

    files = gdrive_client.list_files(name_contains="toeic")

    assert files == [{"id": "f1", "name": "toeic_0001_write_1.png", "mimeType": "image/png"}]


def test_list_files_sends_correct_query_and_fields(monkeypatch):
    gdrive_client, fake_service, _ = _make_client(monkeypatch, response={"files": []}, folder_id="my-folder-id")

    gdrive_client.list_files(name_contains="toeic")

    call = fake_service.files().last_list_call
    assert call["q"] == "'my-folder-id' in parents and trashed = false and name contains 'toeic'"
    assert call["fields"] == "files(id, name, mimeType, webViewLink)"


def test_list_files_without_name_filter_omits_name_clause(monkeypatch):
    gdrive_client, fake_service, _ = _make_client(monkeypatch, response={"files": []}, folder_id="my-folder-id")

    gdrive_client.list_files()

    call = fake_service.files().last_list_call
    assert call["q"] == "'my-folder-id' in parents and trashed = false"


def test_list_files_returns_empty_list_when_no_files_key(monkeypatch):
    gdrive_client, _, _ = _make_client(monkeypatch, response={})

    assert gdrive_client.list_files() == []


def test_download_file_returns_raw_bytes(monkeypatch):
    gdrive_client, _, _ = _make_client(monkeypatch, response=b"fake-file-bytes")

    content = gdrive_client.download_file("f1")

    assert content == b"fake-file-bytes"


def test_download_file_sends_correct_file_id(monkeypatch):
    gdrive_client, fake_service, _ = _make_client(monkeypatch, response=b"bytes")

    gdrive_client.download_file("target-file-id")

    assert fake_service.files().last_get_media_call == {"fileId": "target-file-id"}


def test_list_files_retries_on_5xx_then_succeeds(monkeypatch):
    mock_sleep = MagicMock()
    monkeypatch.setattr(retry_client_module.time, "sleep", mock_sleep)
    gdrive_client, fake_service, _ = _make_client(
        monkeypatch, response={"files": []}, execute_side_effects=[_http_error(503)]
    )

    gdrive_client.list_files()

    assert fake_service.files().last_request.execute_call_count == 2
    mock_sleep.assert_called_once_with(1)
