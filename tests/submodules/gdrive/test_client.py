"""submodules/gdrive/client.py 的單元測試。

不呼叫真正的 Google Drive API，一律 mock `google.oauth2.credentials.Credentials` 與
`googleapiclient.discovery.build`；`MediaIoBaseUpload` 只是包住 bytes 的輕量物件，
不會觸發網路請求，直接用真的沒關係。

2026-08-02：改用 OAuth 2.0（真人帳號身分）認證，取代原本的 Service Account 認證
（見 docs/specs/submodules-core/SPEC.md ADR-10），mock 對象與建構子參數同步更新。
"""
import pytest
from googleapiclient.http import MediaIoBaseUpload

from submodules.gdrive import client as client_module
from submodules.gdrive.client import GDriveClient


class _FakeFilesCreateRequest:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class _FakeFiles:
    def __init__(self, response):
        self._response = response
        self.last_create_call = None

    def create(self, body, media_body, fields):
        self.last_create_call = {"body": body, "media_body": media_body, "fields": fields}
        return _FakeFilesCreateRequest(self._response)


class _FakeDriveService:
    def __init__(self, response):
        self._files = _FakeFiles(response)

    def files(self):
        return self._files


def _make_client(
    monkeypatch,
    response=None,
    refresh_token="fake-refresh-token",
    client_id="fake-client-id",
    client_secret="fake-client-secret",
    folder_id="fake-folder",
):
    response = response or {"id": "abc123", "webViewLink": "https://drive.google.com/file/d/abc123/view"}
    fake_service = _FakeDriveService(response)

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
    assert captured["scopes"] == ["https://www.googleapis.com/auth/drive.file"]


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
