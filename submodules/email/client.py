"""Email 通用 Client：透過 Gmail SMTP（SSL）寄信、透過 Gmail IMAP（SSL）讀信。

命名為 email 而不是 gmail，是為了讓對外呼叫介面（`send_text`／`fetch_emails_from_domain_on_date`）
維持穩定；未來若要換成其他信箱服務，呼叫端的程式碼不需要跟著改。刻意只用 Python 標準函式庫
`smtplib`／`imaplib`／`email`，不額外安裝第三方套件（比照 `submodules/telegram`／`submodules/voice`
「輕量優先、能用標準函式庫就不多裝依賴」的做法）。

寄信用途（見 robinson SPEC.md FR-19b）：Telegram 是 Robinson 唯一的對外管道，一旦 Telegram
API 本身故障或 Bot Token 失效，連私訊 Robin 的錯誤通知都送不出去；這個 Client 提供一條
完全獨立於 Telegram 的備援管道，只在 Telegram 送達失敗時才觸發。

讀信用途（見 robinson SPEC.md FR-23，Step 3.1）：每日技術摘要要讀取 Robin 訂閱的 TLDR 電子報
（寄件者 `dan@tldrnewsletter.com`）。2026-08-07 與 Robin 確認：不用主旨關鍵字比對（電子報版本多、
主旨格式不保證固定），改用「寄件者網域比對」（TLDR 電子報固定由 `tldrnewsletter.com` 網域寄出），
較不易漏抓或誤抓。呼叫端指定要讀哪一天（`target_date`），不在這裡假設「昨天」或「今天」——
Robin 要求固定台灣時間 23:00 收集「當天」的信件、隔天 08:00 才推播，日期語意由呼叫端
（`src/bot/skill_growth.py`）決定，這個 Client 只負責「給定日期，讀出那天的信」。

`password` 必須是 Google 帳號的「應用程式密碼」（App Password），不是一般登入密碼——Google
自 2022 年起要求已開啟兩步驟驗證的帳號改用應用程式密碼才能通過 SMTP／IMAP 驗證，這是
Google 的既定機制，不是本模組可以繞過的限制。`GMAIL_USER`／`GMAIL_PASSWORD` 用於 IMAP 讀信。

2026-08-24（見 docs/ADR/discuss/job-search.md「寄信改走 SendGrid API，取代直連 SMTP」條目）：
Render 免費方案自 2025 年 9 月起封鎖對外連到 SMTP 埠 25／465／587 的流量，原本寄信用的
`smtplib.SMTP_SSL` 完全連不出去。寄信改成呼叫 SendGrid 的 HTTPS API（走 443 埠，不受影響）；
讀信仍是 IMAP（`imaplib`，走 993 埠，不受此限制影響），維持原樣不動。呼叫端建立 Client 時
額外傳入 `send_api_key`（對應環境變數 `SENDGRID_API_KEY`）才能呼叫 `send_text()`／
`send_text_with_attachment()`；只讀信不寄信的呼叫端（例如 Step 3.1 每日技術摘要）可以不傳，
省去申請用不到的金鑰。寄件地址沿用 `username`（即 `GMAIL_USER`），這是 Robin 在 SendGrid
完成 Single Sender Verification 驗證過的同一個信箱，不需要另外持有網域。

金鑰不寫死在程式碼中，一律由呼叫端在建立 Client 時傳入 username/password/send_api_key。
"""
import base64
import imaplib
from datetime import date, timedelta, timezone
from email import message_from_bytes
from email.utils import parseaddr, parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests

from submodules.retry.client import call_with_retry

_IMAP_HOST = "imap.gmail.com"
_TAIWAN_TZ = ZoneInfo("Asia/Taipei")
_SENDGRID_SEND_URL = "https://api.sendgrid.com/v3/mail/send"
_SENDGRID_TIMEOUT_SECONDS = 15
_RETRYABLE_RATE_LIMIT_STATUS = 429
_RETRYABLE_HTTP_STATUS_MIN = 500

# 2026-08-05：外部 API 重試機制（見 docs/specs/robinson/SPEC.md FR-19i、
# docs/specs/submodules-core/SPEC.md ADR-13）。只重試「暫時性錯誤」。


def _is_retryable_sendgrid_error(exc: Exception) -> bool:
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code is None:
            return False
        # 401/403（金鑰錯誤或未驗證寄件人）、400（請求格式錯誤）都是永久性錯誤，重試也沒用。
        return status_code == _RETRYABLE_RATE_LIMIT_STATUS or status_code >= _RETRYABLE_HTTP_STATUS_MIN
    return False


# 2026-08-07：IMAP 讀信同樣套用重試機制（FR-19i）。`imaplib.IMAP4.error`（帳密錯誤、指令格式
# 錯誤）是永久性錯誤，不重試；連線中斷（`OSError`）或伺服器主動中止連線（`imaplib.IMAP4.abort`）
# 屬於暫時性狀況，才重試。


def _is_retryable_imap_error(exc: Exception) -> bool:
    if isinstance(exc, imaplib.IMAP4.error):
        return False
    return isinstance(exc, (OSError, imaplib.IMAP4.abort))


def _is_from_domain(from_header: str, domain: str) -> bool:
    """判斷信件 From header 的寄件位址是否屬於指定網域（大小寫不敏感）。"""
    _, addr = parseaddr(from_header or "")
    return addr.lower().endswith(f"@{domain.lower()}")


def _sent_on_date(date_header: str, target_date: date) -> bool:
    """把信件 Date header 換算成台灣時間後，判斷是否落在 `target_date` 這一天。"""
    try:
        parsed_dt = parsedate_to_datetime(date_header or "")
    except (TypeError, ValueError):
        return False
    if parsed_dt.tzinfo is None:
        parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
    return parsed_dt.astimezone(_TAIWAN_TZ).date() == target_date


def _extract_plain_text(parsed_message) -> str:
    """從解析後的 email.message.Message 取出純文字內容；優先找 `text/plain` 分段，找不到回傳空字串。"""
    if parsed_message.is_multipart():
        for part in parsed_message.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            if part.get_content_type() == "text/plain" and "attachment" not in content_disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return ""

    payload = parsed_message.get_payload(decode=True)
    if not payload:
        return ""
    charset = parsed_message.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


class EmailClient:
    """封裝「SendGrid API 寄信」＋「Gmail IMAP（SSL）讀信」的最小 Client。

    寄信支援純文字信件（`send_text`）與純文字＋單一附件信件（`send_text_with_attachment`，
    2026-08-09 新增，見 robinson SPEC.md FR-35b、ADR-24 後果：Step 4.1 公司背景協作機制需要
    寄送 CSV 附件，Step 4.2 職缺推薦交付機制需要寄送 Excel 附件，兩者共用同一個方法）；
    2026-08-24 起兩者改走 SendGrid HTTPS API（見模組 docstring），需要 `send_api_key`。
    讀信只支援「依寄件者網域＋指定日期」篩選收件匣信件（`fetch_emails_from_domain_on_date`），
    目前唯一呼叫端是 Step 3.1 每日技術摘要（FR-23）讀取 TLDR 電子報，只用到 `username`／
    `password`，不需要 `send_api_key`。
    """

    def __init__(self, username: str, password: str, send_api_key: str | None = None):
        if not username:
            raise ValueError("username 不可為空")
        if not password:
            raise ValueError("password 不可為空")
        self._username = username
        self._password = password
        self._send_api_key = send_api_key

    def _require_send_api_key(self) -> str:
        if not self._send_api_key:
            raise ValueError("寄信需要 send_api_key（對應環境變數 SENDGRID_API_KEY），建立 Client 時未傳入")
        return self._send_api_key

    def _send_via_sendgrid(self, payload: dict) -> None:
        api_key = self._require_send_api_key()
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        def _do_send():
            response = requests.post(_SENDGRID_SEND_URL, json=payload, headers=headers, timeout=_SENDGRID_TIMEOUT_SECONDS)
            response.raise_for_status()

        call_with_retry(_do_send, is_retryable=_is_retryable_sendgrid_error)

    def send_text(self, to: str, subject: str, body: str) -> None:
        """寄送一封純文字信件給 `to`。"""
        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": self._username},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }
        self._send_via_sendgrid(payload)

    def send_text_with_attachment(
        self, to: str, subject: str, body: str, attachment_filename: str, attachment_bytes: bytes
    ) -> None:
        """寄送一封純文字信件給 `to`，並附帶單一檔案附件。

        附件一律用通用二進位型別 `application/octet-stream` 編碼（不特別分辨 CSV/Excel 等實際
        格式）——收件端（Gmail 網頁/App）會依副檔名自行判斷開啟方式。SendGrid API 的附件欄位
        本身就是 UTF-8 JSON 字串，`attachment_filename` 含中文（例如 `2026-08-09-104職缺公司.csv`）
        不需要像過去 SMTP／MIME 那樣額外做 RFC 2231 編碼，直接放進 `filename` 欄位即可。
        """
        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": self._username},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
            "attachments": [
                {
                    "content": base64.b64encode(attachment_bytes).decode("ascii"),
                    "filename": attachment_filename,
                    "type": "application/octet-stream",
                    "disposition": "attachment",
                }
            ],
        }
        self._send_via_sendgrid(payload)

    def fetch_emails_from_domain_on_date(self, sender_domain: str, target_date: date) -> list[str]:
        """讀取寄件者網域符合 `sender_domain`、寄送日期（台灣時間）為 `target_date` 的信件純文字內容清單。

        對應 FR-23：Robin 訂閱的 TLDR 電子報固定由 `tldrnewsletter.com` 網域寄出，用寄件者網域
        比對（而非主旨關鍵字）辨識，避免電子報改版主旨格式時漏抓。IMAP 的 `SEARCH SINCE/BEFORE`
        是以「日曆日」為單位、且不保證時區精確，所以先用寬鬆的 `SINCE/BEFORE` 區間＋`FROM` 縮小
        範圍抓信，抓回來後再用信件 `Date` header 換算台灣時間精確比對是否真的落在 `target_date`，
        並用 `_is_from_domain()` 二次確認寄件網域，避免時區誤差或子字串誤配多抓到不該抓的信。

        `target_date` 由呼叫端決定要讀哪一天（例如固定台灣時間 23:00 收集「當天」信件時傳入
        當天日期），這個 Client 本身不假設任何相對日期語意。
        """
        imap_since = target_date.strftime("%d-%b-%Y")
        imap_before = (target_date + timedelta(days=1)).strftime("%d-%b-%Y")

        def _do_fetch() -> list[str]:
            texts: list[str] = []
            with imaplib.IMAP4_SSL(_IMAP_HOST) as conn:
                conn.login(self._username, self._password)
                conn.select("INBOX", readonly=True)
                status, data = conn.search(
                    None, f'(SINCE "{imap_since}" BEFORE "{imap_before}" FROM "{sender_domain}")'
                )
                if status != "OK" or not data or not data[0]:
                    return texts

                for message_id in data[0].split():
                    fetch_status, msg_data = conn.fetch(message_id, "(RFC822)")
                    if fetch_status != "OK" or not msg_data or not msg_data[0]:
                        continue
                    parsed_message = message_from_bytes(msg_data[0][1])
                    if not _is_from_domain(parsed_message.get("From", ""), sender_domain):
                        continue
                    if not _sent_on_date(parsed_message.get("Date", ""), target_date):
                        continue
                    texts.append(_extract_plain_text(parsed_message))
            return texts

        return call_with_retry(_do_fetch, is_retryable=_is_retryable_imap_error)
