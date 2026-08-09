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
Google 的既定機制，不是本模組可以繞過的限制。同一組 `GMAIL_USER`／`GMAIL_PASSWORD` 同時
支援 SMTP 寄信與 IMAP 讀信，不需要另外申請憑證。

金鑰不寫死在程式碼中，一律由呼叫端在建立 Client 時傳入 username/password。
"""
import imaplib
import smtplib
from datetime import date, timedelta, timezone
from email import encoders, message_from_bytes
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr, parsedate_to_datetime
from zoneinfo import ZoneInfo

from submodules.retry.client import call_with_retry

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 465
_IMAP_HOST = "imap.gmail.com"
_TAIWAN_TZ = ZoneInfo("Asia/Taipei")

# 2026-08-05：外部 API 重試機制（見 docs/specs/robinson/SPEC.md FR-19i、
# docs/specs/submodules-core/SPEC.md ADR-13）。只重試「暫時性錯誤」：連線中斷、連線失敗等
# 屬於 OSError／SMTPException 的暫時性狀況；`SMTPAuthenticationError`（帳密錯誤）是永久性
# 錯誤，重試也沒用，直接往外拋，不浪費重試次數。


def _is_retryable_smtp_error(exc: Exception) -> bool:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return False
    return isinstance(exc, OSError)


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
    """封裝 Gmail SMTP（SSL）寄信、Gmail IMAP（SSL）讀信的最小 Client。

    寄信支援純文字信件（`send_text`）與純文字＋單一附件信件（`send_text_with_attachment`，
    2026-08-09 新增，見 robinson SPEC.md FR-35b、ADR-24 後果：Step 4.1 公司背景協作機制需要
    寄送 CSV 附件，Step 4.2 職缺推薦交付機制需要寄送 Excel 附件，兩者共用同一個方法）；讀信只
    支援「依寄件者網域＋指定日期」篩選收件匣信件（`fetch_emails_from_domain_on_date`），目前
    唯一呼叫端是 Step 3.1 每日技術摘要（FR-23）讀取 TLDR 電子報，需要更多能力時再依實際需求擴充。
    """

    def __init__(self, username: str, password: str):
        if not username:
            raise ValueError("username 不可為空")
        if not password:
            raise ValueError("password 不可為空")
        self._username = username
        self._password = password

    def send_text(self, to: str, subject: str, body: str) -> None:
        """寄送一封純文字信件給 `to`。"""
        message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = subject
        message["From"] = self._username
        message["To"] = to

        def _do_send():
            with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT) as server:
                server.login(self._username, self._password)
                server.sendmail(self._username, [to], message.as_string())

        call_with_retry(_do_send, is_retryable=_is_retryable_smtp_error)

    def send_text_with_attachment(
        self, to: str, subject: str, body: str, attachment_filename: str, attachment_bytes: bytes
    ) -> None:
        """寄送一封純文字信件給 `to`，並附帶單一檔案附件。

        附件一律用通用二進位型別 `application/octet-stream` 編碼（不特別分辨 CSV/Excel 等實際
        格式）——收件端（Gmail 網頁/App）會依副檔名自行判斷開啟方式，寄件端不需要精確指定
        MIME type，維持跟 `send_text()` 一樣「只用標準函式庫 `email.mime`，不額外安裝第三方
        套件」的做法（見模組 docstring）。`attachment_filename` 可能含中文（例如
        `2026-08-09-104職缺公司.csv`），用 `email.message.Message.add_header()` 官方支援的
        `(charset, language, value)` 三元組寫法觸發 RFC 2231 編碼，避免中文檔名在部分信箱
        客戶端顯示成亂碼或副檔名遺失。
        """
        message = MIMEMultipart()
        message["Subject"] = subject
        message["From"] = self._username
        message["To"] = to
        message.attach(MIMEText(body, "plain", "utf-8"))

        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", attachment_filename))
        message.attach(part)

        def _do_send():
            with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT) as server:
                server.login(self._username, self._password)
                server.sendmail(self._username, [to], message.as_string())

        call_with_retry(_do_send, is_retryable=_is_retryable_smtp_error)

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
