# calendar

Google Calendar 通用 Client，使用 OAuth 2.0（以 Robin 本人 Google 帳號身分）認證，對指定的「Robinson 家庭行事曆」做事件的建立/更新/刪除。

見 [docs/specs/SPEC.md](../../docs/specs/SPEC.md) FR-66、[docs/ADR/discuss/google-calendar.md](../../docs/ADR/discuss/google-calendar.md) ADR-17：待辦事項、重要通知（節日/生日）、體態目標期限單向同步寫入這個共用行事曆，家人用「查看所有活動詳細資料」（唯讀）權限訂閱，在自己手機的原生行事曆 App 瀏覽。

## 環境變數

見 `.env.example`：

| 變數 | 說明 |
| --- | --- |
| `GOOGLE_CALENDAR_OAUTH_CLIENT_ID` | Google Cloud Console 建立的 OAuth 用戶端 ID（應用程式類型選「桌面應用程式」，**跟 `gdrive` 使用不同的一組，不共用**，見 ADR-12） |
| `GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET` | 對應的 Client Secret |
| `GOOGLE_CALENDAR_OAUTH_REFRESH_TOKEN` | 用 `get_refresh_token.py` 一次性互動授權取得的 refresh token |
| `GOOGLE_CALENDAR_ID` | 要寫入哪個 Google Calendar（次要日曆的 Calendar ID，格式通常是 `xxxxx@group.calendar.google.com`，可從行事曆設定頁面取得） |

## 取得 OAuth 憑證（一次性）

見 `get_refresh_token.py` 檔案開頭的完整步驟說明；簡述如下：

1. Google Cloud Console 額外開通 Google Calendar API（跟 Drive API 是不同的 API，要分別啟用）。
2. 建立一組**全新**的「桌面應用程式」類型 OAuth 用戶端 ID（不要沿用 `gdrive` 那組），取得 Client ID／Secret。
3. OAuth 同意畫面「範圍」新增 `.../auth/calendar.events`；發布狀態設為「正式版」，避免「測試中」狀態核發的 refresh token 只有 7 天效期。
4. 本機 `pip install google-auth-oauthlib`，執行 `python3 submodules/calendar/get_refresh_token.py`，跑完瀏覽器互動授權後終端機會印出 refresh token。

## 安裝

```bash
pip install -r submodules/calendar/requirements.txt
```

## 使用範例

```python
from submodules.calendar.client import CalendarClient

client = CalendarClient(
    refresh_token="...",
    client_id="...",
    client_secret="...",
    calendar_id="xxxxx@group.calendar.google.com",
)

# 有時間點的事件（例如待辦事項）
event_id = client.create_event(
    summary="繳電費",
    start="2026-08-10T08:00:00+08:00",
    end="2026-08-10T09:00:00+08:00",
    description="來自 Robinson 待辦事項",
)

# 全天事件（例如節日/生日）
event_id = client.create_event(
    summary="爸爸生日",
    start="2026-09-12",
    end="2026-09-13",
    all_day=True,
)

client.update_event(
    event_id=event_id,
    summary="繳電費（已改期）",
    start="2026-08-11T08:00:00+08:00",
    end="2026-08-11T09:00:00+08:00",
)

client.delete_event(event_id=event_id)
```

## 設計限制（務必遵守）

1. 只支援建立/更新/刪除單一事件（`create_event`／`update_event`／`delete_event`），不做行事曆本身的設定變更、不做讀取/查詢——目前呼叫端只需要「單向寫入」這個能力（見 ADR-17 決策 3，讀取查空檔明確排除在範圍外），需要更多功能時再依實際需求擴充，不要預先做用不到的介面。
2. OAuth 權限範圍固定為 `calendar.events`（僅限事件讀寫），不要求完整的 `calendar` scope，符合最小權限原則（見 ADR-12）。
3. 這組憑證跟 `submodules/gdrive` 的憑證各自獨立管理，不共用，即使兩者可能來自同一個 Google Cloud 專案。
4. 事件內容格式（全天 `date` 或有時間點 `dateTime`）、要不要同步、同步哪些欄位等商業邏輯一律由呼叫端（`src/bot/`）決定，本模組只負責「把事件內容丟到 Calendar」。
5. 底層 API 例外一律往外拋，不吞例外，由呼叫端決定要不要處理（例如優雅降級、記 log）。

## 對應 Spec

[docs/specs/SPEC.md](../../docs/specs/SPEC.md)「Submodules 共用子模組基礎骨架」、[docs/ADR/discuss/submodules-core.md](../../docs/ADR/discuss/submodules-core.md)
