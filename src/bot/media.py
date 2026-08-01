"""`media_uploads` 表的共用寫入邏輯（對應 docs/specs/robinson/SPEC.md ADR-13）。

2026-08-01（Step 1.4）從 `image.py` 抽出：`save_media_upload()` 本來就是不分媒體類型的
通用寫入（`media_type` 只是參數），這張表的設計本來就預期圖片／語音共用（見
src/schema/db_schema.md 的 `media_uploads.media_type` 註解），獨立成這支檔案讓
`image.py`／`voice.py` 都能依賴它，避免 voice.py 反過來 import image.py 造成不必要的耦合。
"""
from submodules.cloudsql.client import CloudSQLClient


def save_media_upload(db: CloudSQLClient, user_id: int, media_type: str, gdrive_url: str) -> None:
    """寫入一筆 media_uploads 記錄（ADR-13）。"""
    db.insert("media_uploads", {"user_id": user_id, "media_type": media_type, "gdrive_url": gdrive_url})
