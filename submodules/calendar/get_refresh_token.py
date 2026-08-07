"""一次性本機腳本：走 Google OAuth 2.0 互動授權流程，取得長期可用的 refresh token。

**只需要在本機執行一次**（不是 production 依賴，不會被 webhook.py 匯入），目的是讓 Robin
本人（真人 Google 帳號）授權這支程式讀寫「Robinson 家庭行事曆」，取得的 refresh token 之後
會設定成 Render 環境變數 `GOOGLE_CALENDAR_OAUTH_REFRESH_TOKEN`，供 `client.py` 的
`CalendarClient` 長期使用。

依 robinson SPEC.md ADR-17 與 submodules-core SPEC.md ADR-12 的最小權限設計：
- scope 只申請 `calendar.events`（僅限事件讀寫），不申請完整的 `calendar`
- 這組憑證跟 `submodules/gdrive` 的憑證是**各自獨立**的一組，即使兩者可能來自同一個
  Google Cloud 專案，也不共用 Client ID／Client Secret／refresh token

使用方式：
1. 到 Google Cloud Console →「API 和服務」→「憑證」，建立一組全新的「OAuth 用戶端 ID」
   （不要沿用 gdrive 那組），應用程式類型選「桌面應用程式」，取得 Client ID／Client Secret。
2. 「OAuth 同意畫面」的「範圍」新增 `.../auth/calendar.events`；發布狀態務必設為
   「正式版（In production）」，不要停在「測試中」——測試中狀態核發的 refresh token 只有
   7 天效期，正式版才會長期有效（不需要 Google 完整審核，只是每次互動授權時會多看到一次
   「Google 尚未驗證這個應用程式」的警告畫面，直接繼續即可，因為這是你自己的應用程式、
   只有你自己在用）。
3. 本機安裝互動授權需要的套件（production 環境不需要，只有跑這支腳本時才需要）：
   `pip install google-auth-oauthlib`
4. 執行：
   `GOOGLE_CALENDAR_OAUTH_CLIENT_ID=xxx GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET=xxx python3 submodules/calendar/get_refresh_token.py`
   會自動開啟瀏覽器，用你的 Google 帳號登入並同意授權，完成後終端機會印出 refresh token，
   把它設定成 `GOOGLE_CALENDAR_OAUTH_REFRESH_TOKEN` 環境變數（本機 `.env` 與 Render 都要設定）。
"""
import os

from google_auth_oauthlib.flow import InstalledAppFlow

_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def main() -> None:
    client_id = os.environ.get("GOOGLE_CALENDAR_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit(
            "請先設定 GOOGLE_CALENDAR_OAUTH_CLIENT_ID／GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET "
            "環境變數再執行這支腳本"
        )

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=_SCOPES)
    credentials = flow.run_local_server(port=0)

    print("\n授權成功！請把以下值設定成環境變數 GOOGLE_CALENDAR_OAUTH_REFRESH_TOKEN：\n")
    print(credentials.refresh_token)


if __name__ == "__main__":
    main()
