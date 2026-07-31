"""Google Drive 通用 Client：使用 Service Account 認證，把檔案上傳到指定資料夾。

命名為 gdrive 而不是 drive，避免與標準函式庫或第三方套件的命名衝突；對外只暴露
`upload_file()` 一個方法，封裝 Service Account 認證與 Drive API v3 呼叫細節，
不涉及本專案的商業邏輯（例如檔名規則、要不要寫入資料庫，都是呼叫端的責任）。

金鑰檔路徑與資料夾 ID 不寫死在程式碼中，一律由呼叫端在建立 Client 時傳入。
"""
import io

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class GDriveClient:
    """封裝 Google Drive API v3 的最小 Client（Service Account 認證，僅支援上傳）。"""

    def __init__(self, key_file_path: str, folder_id: str):
        if not key_file_path:
            raise ValueError("key_file_path 不可為空")
        if not folder_id:
            raise ValueError("folder_id 不可為空")
        credentials = service_account.Credentials.from_service_account_file(
            key_file_path, scopes=_SCOPES
        )
        self._service = build("drive", "v3", credentials=credentials)
        self._folder_id = folder_id

    def upload_file(self, filename: str, content: bytes, mime_type: str) -> str:
        """把檔案內容上傳到建構子指定的資料夾，回傳可分享檢視的網址（webViewLink）。"""
        file_metadata = {"name": filename, "parents": [self._folder_id]}
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type)
        uploaded = (
            self._service.files()
            .create(body=file_metadata, media_body=media, fields="id, webViewLink")
            .execute()
        )
        return uploaded["webViewLink"]
