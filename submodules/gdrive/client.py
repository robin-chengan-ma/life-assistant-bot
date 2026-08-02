"""Google Drive 通用 Client：使用 OAuth 2.0（以真人帳號身分）認證，把檔案上傳到指定資料夾。

命名為 gdrive 而不是 drive，避免與標準函式庫或第三方套件的命名衝突；對外只暴露
`upload_file()` 一個方法，封裝 OAuth 認證與 Drive API v3 呼叫細節，不涉及本專案的
商業邏輯（例如檔名規則、要不要寫入資料庫，都是呼叫端的責任）。

2026-08-02 修正（見 docs/specs/submodules-core/SPEC.md ADR-10，supersede 原本的
Service Account 認證方式）：Robin 實測上傳語音檔時撞到 Google Drive API 的
`storageQuotaExceeded`——這是 Google 的既定限制，Service Account 本身完全沒有 Drive 儲存
額度，用它上傳檔案到任何一般（非 Shared Drive）資料夾一律會失敗，跟資料夾本身還有沒有空間
無關。改用 OAuth 2.0、以 Robin 本人的 Google 帳號身分上傳，檔案算進他自己的 Drive 額度，
不再需要 Google Workspace 才有的 Shared Drive 功能。取得 refresh token 的一次性互動流程見
`get_refresh_token.py`（本機執行，不進 production 依賴）。

金鑰／憑證與資料夾 ID 不寫死在程式碼中，一律由呼叫端在建立 Client 時傳入。
"""
import io

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GDriveClient:
    """封裝 Google Drive API v3 的最小 Client（OAuth 2.0 使用者身分認證，僅支援上傳）。"""

    def __init__(self, refresh_token: str, client_id: str, client_secret: str, folder_id: str):
        if not refresh_token:
            raise ValueError("refresh_token 不可為空")
        if not client_id:
            raise ValueError("client_id 不可為空")
        if not client_secret:
            raise ValueError("client_secret 不可為空")
        if not folder_id:
            raise ValueError("folder_id 不可為空")
        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri=_TOKEN_URI,
            scopes=_SCOPES,
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
