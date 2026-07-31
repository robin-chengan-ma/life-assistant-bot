# gdrive

Google Drive 通用 Client，使用 Service Account 認證，把檔案上傳到指定資料夾，回傳可分享檢視的網址。

## 環境變數

見 `.env.example`：

| 變數 | 說明 |
| --- | --- |
| `GDRIVE_KEY_FILE_PATH` | Google Service Account 金鑰 JSON 檔的路徑 |
| `GDRIVE_FOLDER_ID` | 要上傳到哪個 Google Drive 資料夾（資料夾 ID，可從資料夾網址取得） |

## 安裝

```bash
pip install -r submodules/gdrive/requirements.txt
```

## 使用範例

```python
from submodules.gdrive.client import GDriveClient

client = GDriveClient(key_file_path="google_service_account.json", folder_id="1rONV9Hz...")

url = client.upload_file(
    filename="爸爸_20260731153000_飲食紀錄.jpg",
    content=image_bytes,
    mime_type="image/jpeg",
)
```

## 設計限制（務必遵守）

1. 只支援上傳（`upload_file`），不做下載/刪除/列表等其他 Drive 操作——目前呼叫端只需要「上傳後拿到分享連結」這個能力，需要更多功能時再依實際需求擴充，不要預先做用不到的介面。
2. 檔名規則、要不要寫入資料庫、壓縮處理等商業邏輯一律由呼叫端（`src/bot/`）決定，本模組只負責「把 bytes 丟到 Drive」。
3. Service Account 的權限範圍固定為 `drive.file`（只能操作自己建立的檔案），不要求更寬的權限範圍。

## 對應 Spec

[docs/specs/submodules-core/SPEC.md](../../docs/specs/submodules-core/SPEC.md)
