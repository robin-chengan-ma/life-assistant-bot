"""Email 通用 Client：目前透過 Gmail SMTP（SSL）寄送純文字信件。

命名為 email 而不是 gmail，是為了讓對外呼叫介面（`send_text`）維持穩定；未來若要換成
其他寄信服務，呼叫端的程式碼不需要跟著改。刻意只用 Python 標準函式庫 `smtplib`／
`email.mime`，不額外安裝第三方套件（比照 `submodules/telegram`／`submodules/voice`
「輕量優先、能用標準函式庫就不多裝依賴」的做法）。

用途（見 robinson SPEC.md FR-19b）：Telegram 是 Robinson 唯一的對外管道，一旦 Telegram
API 本身故障或 Bot Token 失效，連私訊 Robin 的錯誤通知都送不出去；這個 Client 提供一條
完全獨立於 Telegram 的備援管道，只在 Telegram 送達失敗時才觸發。

`password` 必須是 Google 帳號的「應用程式密碼」（App Password），不是一般登入密碼——Google
自 2022 年起要求已開啟兩步驟驗證的帳號改用應用程式密碼才能通過 SMTP／IMAP 驗證，這是
Google 的既定機制，不是本模組可以繞過的限制。

金鑰不寫死在程式碼中，一律由呼叫端在建立 Client 時傳入 username/password。
"""
import smtplib
from email.mime.text import MIMEText

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 465


class EmailClient:
    """封裝 Gmail SMTP（SSL）寄信的最小 Client，僅支援純文字信件（`send_text`）。"""

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

        with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT) as server:
            server.login(self._username, self._password)
            server.sendmail(self._username, [to], message.as_string())
