# email

Email 通用 Client，目前透過 Gmail SMTP（SSL，port 465）寄送純文字信件，只用 Python 標準函式庫 `smtplib`／`email.mime`，不安裝任何第三方套件。

## 環境變數

見 `.env.example`：

| 變數 | 說明 |
| --- | --- |
| `GMAIL_USER` | 寄件用的 Gmail 帳號 |
| `GMAIL_PASSWORD` | Google 帳號的**應用程式密碼**（App Password），不是一般登入密碼 |

## 安裝

```bash
pip install -r submodules/email/requirements.txt
```

（這個檔案目前是空的，僅作為與其他子模組一致的骨架慣例，不需要真的安裝任何套件。）

## 使用範例

```python
from submodules.email.client import EmailClient

client = EmailClient(username="you@gmail.com", password="xxxx xxxx xxxx xxxx")

client.send_text(to="you@gmail.com", subject="主旨", body="信件內容")
```

## 設計限制（務必遵守）

1. 只支援寄送純文字信件（`send_text`），不做附件、HTML 信件、收信（IMAP）等其他能力——目前呼叫端只需要「寄一封純文字通知信」這個能力，需要更多功能時再依實際需求擴充。
2. `GMAIL_PASSWORD` 一律要求是應用程式密碼：Google 自 2022 年起，已開啟兩步驟驗證的帳號必須用應用程式密碼才能通過 SMTP／IMAP 驗證，一般登入密碼會被拒絕，這是 Google 官方機制，不是本模組的限制。
3. 這個 Client 設計上是「備援管道」，不是主要通知手段——目前唯一的呼叫端是 `src/bot/webhook.py` 的 `_notify_robin_of_error()`，只在 Telegram 私訊 Robin 失敗時才會觸發，平常不會用到，見 robinson SPEC.md FR-19b。

## 對應 Spec

[docs/specs/submodules-core/SPEC.md](../../docs/specs/submodules-core/SPEC.md)、[docs/specs/robinson/SPEC.md](../../docs/specs/robinson/SPEC.md) FR-19b
