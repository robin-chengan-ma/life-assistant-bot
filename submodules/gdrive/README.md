# gdrive

Google Drive 通用 Client，使用 OAuth 2.0（以真人 Google 帳號身分）認證，把檔案上傳到指定資料夾，回傳可分享檢視的網址。

**2026-08-02 起改用 OAuth，不再是 Service Account**：Service Account 完全沒有 Drive 儲存額度，上傳任何檔案到一般（非 Shared Drive）資料夾都會撞到 `storageQuotaExceeded`，這是 Google 的既定限制，不是資料夾空間不夠的問題；Shared Drive 又只有付費的 Google Workspace 才有。改用 OAuth 讓程式以你自己的身分上傳，檔案算進你自己的 Drive 額度，完全免費。

## 環境變數

見 `.env.example`：

| 變數 | 說明 |
| --- | --- |
| `GDRIVE_OAUTH_CLIENT_ID` | Google Cloud Console 建立的 OAuth 用戶端 ID（應用程式類型選「桌面應用程式」） |
| `GDRIVE_OAUTH_CLIENT_SECRET` | 對應的 Client Secret |
| `GDRIVE_OAUTH_REFRESH_TOKEN` | 用 `get_refresh_token.py` 一次性互動授權取得的 refresh token |
| `GDRIVE_FOLDER_ID` | 要上傳到哪個 Google Drive 資料夾（資料夾 ID，可從資料夾網址取得） |

## 取得 OAuth 憑證（一次性）

見 `get_refresh_token.py` 檔案開頭的完整步驟說明；簡述如下：

1. Google Cloud Console 建立「桌面應用程式」類型的 OAuth 用戶端 ID，取得 Client ID／Secret。
2. OAuth 同意畫面發布狀態設為「正式版」，避免「測試中」狀態核發的 refresh token 只有 7 天效期。
3. 本機 `pip install google-auth-oauthlib`，執行 `python3 submodules/gdrive/get_refresh_token.py`，跑完瀏覽器互動授權後終端機會印出 refresh token。

## 安裝

```bash
pip install -r submodules/gdrive/requirements.txt
```

## 使用範例

```python
from submodules.gdrive.client import GDriveClient

client = GDriveClient(
    refresh_token="...",
    client_id="...",
    client_secret="...",
    folder_id="1rONV9Hz...",
)

url = client.upload_file(
    filename="爸爸_20260731153000_飲食紀錄.jpg",
    content=image_bytes,
    mime_type="image/jpeg",
)
```

## 使用範例（列表／下載，2026-08-07 新增，見 TOEIC 題庫 Pipeline Step 3.2）

```python
files = client.list_files(name_contains="toeic")
for f in files:
    content = client.download_file(f["id"])
```

## 設計限制（務必遵守）

1. 只支援上傳／列表／下載（`upload_file`／`list_files`／`download_file`），不做刪除——目前呼叫端沒有刪檔需求，需要時再依實際需求擴充，不要預先做用不到的介面。
2. 檔名規則、要不要寫入資料庫、壓縮處理等商業邏輯一律由呼叫端（`src/bot/`）決定，本模組只負責跟 Drive API 溝通。
3. OAuth 權限範圍為 `drive.file`（操作本程式自己建立的檔案）＋`drive.readonly`（讀取使用者手動上傳、本程式未建立的檔案，供 TOEIC Pipeline 掃描 Robin 手動上傳的題目照片/音檔），仍刻意不要求完整 `drive` 寫入權限。

## 對應 Spec

[docs/specs/submodules-core/SPEC.md](../../docs/specs/submodules-core/SPEC.md)
