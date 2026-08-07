"""Google Calendar 通用 Client：使用 OAuth 2.0（以 Robin 本人帳號身分）認證，
對指定的共用行事曆做事件的建立/更新/刪除（見 docs/specs/robinson/SPEC.md FR-66、ADR-17）。

命名為 `calendar` 是子模組資料夾名稱，跟 Python 標準函式庫的 `calendar` 模組不會衝突
（`from submodules.calendar.client import CalendarClient` 是絕對匯入路徑，不受影響）。

刻意只申請 `calendar.events` scope（僅限事件讀寫），不申請完整的 `calendar` scope
（會額外拿到修改行事曆本身設定、刪除整個行事曆等更高權限），符合最小權限原則；這組
OAuth 憑證跟 `submodules/gdrive` 的憑證各自獨立，不共用（見
docs/specs/submodules-core/SPEC.md ADR-12）。取得 refresh token 的一次性互動流程見
`get_refresh_token.py`（本機執行，不進 production 依賴）。

對外只暴露 `create_event()`／`update_event()`／`delete_event()` 三個方法，封裝 OAuth
認證與 Calendar API v3 呼叫細節；事件內容格式（全天事件用 `date`、有時間點的事件用
`dateTime`＋時區）由呼叫端透過 `all_day` 參數決定，不涉及本專案的商業邏輯（例如要不要
同步、同步哪些欄位，都是呼叫端 `src/bot/*.py` 的責任）。底層 API 例外一律往外拋，不吞
例外，由呼叫端決定要不要處理。

金鑰／憑證與行事曆 ID 不寫死在程式碼中，一律由呼叫端在建立 Client 時傳入。
"""
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
_TOKEN_URI = "https://oauth2.googleapis.com/token"
_TIME_ZONE = "Asia/Taipei"


class CalendarClient:
    """封裝 Google Calendar API v3 的最小 Client（OAuth 2.0 使用者身分認證）。"""

    def __init__(self, refresh_token: str, client_id: str, client_secret: str, calendar_id: str):
        if not refresh_token:
            raise ValueError("refresh_token 不可為空")
        if not client_id:
            raise ValueError("client_id 不可為空")
        if not client_secret:
            raise ValueError("client_secret 不可為空")
        if not calendar_id:
            raise ValueError("calendar_id 不可為空")
        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri=_TOKEN_URI,
            scopes=_SCOPES,
        )
        self._service = build("calendar", "v3", credentials=credentials)
        self._calendar_id = calendar_id

    def create_event(
        self, summary: str, start: str, end: str, description: str = "", all_day: bool = False
    ) -> str:
        """建立事件，回傳新建事件的 event_id。

        `start`／`end`：`all_day=True` 時用 `YYYY-MM-DD` 日期格式；否則用含時區資訊的
        ISO 8601 時間戳記字串（例如 `2026-08-10T08:00:00+08:00`）。
        """
        body = self._build_event_body(summary, start, end, description, all_day)
        created = self._service.events().insert(calendarId=self._calendar_id, body=body).execute()
        return created["id"]

    def update_event(
        self,
        event_id: str,
        summary: str,
        start: str,
        end: str,
        description: str = "",
        all_day: bool = False,
    ) -> None:
        """用完整覆蓋的方式更新既有事件（呼叫端已知完整最新狀態，不做部分欄位 patch）。"""
        body = self._build_event_body(summary, start, end, description, all_day)
        self._service.events().update(
            calendarId=self._calendar_id, eventId=event_id, body=body
        ).execute()

    def delete_event(self, event_id: str) -> None:
        """刪除既有事件。"""
        self._service.events().delete(calendarId=self._calendar_id, eventId=event_id).execute()

    def _build_event_body(
        self, summary: str, start: str, end: str, description: str, all_day: bool
    ) -> dict:
        time_key = "date" if all_day else "dateTime"
        body = {
            "summary": summary,
            "description": description,
            "start": {time_key: start},
            "end": {time_key: end},
        }
        if not all_day:
            body["start"]["timeZone"] = _TIME_ZONE
            body["end"]["timeZone"] = _TIME_ZONE
        return body
