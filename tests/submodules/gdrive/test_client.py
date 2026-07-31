"""submodules/gdrive/client.py 的單元測試。

不呼叫真正的 Google Drive API，一律 mock `service_account.Credentials` 與
`googleapiclient.discovery.build`；`MediaIoBaseUpload` 只是包住 bytes 的輕量物件，
不會觸發網路請求，直接用真的沒關係。
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


def _make_client(monkeypatch, response=None, key_file_path="fake.json", folder_id="fake-folder"):
    response = response or {"id": "abc123", "webViewLink": "https://drive.google.com/file/d/abc123/view"}
    fake_service = _FakeDriveService(response)

    monkeypatch.setattr(
        client_module.service_account.Credentials,
        "from_service_account_file",
        lambda path, scopes: "fake-creds",
    )
    monkeypatch.setattr(client_module, "build", lambda *args, **kwargs: fake_service)

    gdrive_client = GDriveClient(key_file_path=key_file_path, folder_id=folder_id)
    return gdrive_client, fake_service


def test_init_raises_on_empty_key_file_path():
    with pytest.raises(ValueError):
        GDriveClient(key_file_path="", folder_id="fake-folder")


def test_init_raises_on_empty_folder_id():
    with pytest.raises(ValueError):
        GDriveClient(key_file_path="fake.json", folder_id="")


def test_upload_file_returns_web_view_link(monkeypatch):
    gdrive_client, _ = _make_client(monkeypatch)

    url = gdrive_client.upload_file(filename="test.jpg", content=b"fake-bytes", mime_type="image/jpeg")

    assert url == "https://drive.google.com/file/d/abc123/view"


def test_upload_file_sends_correct_metadata_and_folder(monkeypatch):
    gdrive_client, fake_service = _make_client(monkeypatch, folder_id="my-folder-id")

    gdrive_client.upload_file(filename="test.jpg", content=b"fake-bytes", mime_type="image/jpeg")

    call = fake_service.files().last_create_call
    assert call["body"] == {"name": "test.jpg", "parents": ["my-folder-id"]}
    assert call["fields"] == "id, webViewLink"
    assert isinstance(call["media_body"], MediaIoBaseUpload)
