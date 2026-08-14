# email

Email 通用 Client：透過 Gmail SMTP（SSL，port 465）寄送純文字信件、透過 Gmail IMAP（SSL，port 993）讀取收件匣信件，只用 Python 標準函式庫 `smtplib`／`imaplib`／`email`，不安裝任何第三方套件。

## 環境變數

見 `.env.example`：

| 變數 | 說明 |
| --- | --- |
| `GMAIL_USER` | 寄件／讀信共用的 Gmail 帳號 |
| `GMAIL_PASSWORD` | Google 帳號的**應用程式密碼**（App Password），不是一般登入密碼；同一組密碼同時支援 SMTP 寄信與 IMAP 讀信 |

## 安裝

```bash
pip install -r submodules/email/requirements.txt
```

（這個檔案目前是空的，僅作為與其他子模組一致的骨架慣例，不需要真的安裝任何套件。）

## 使用範例

```python
from submodules.email.client import EmailClient

client = EmailClient(username="you@gmail.com", password="xxxx xxxx xxxx xxxx")

# 寄信
client.send_text(to="you@gmail.com", subject="主旨", body="信件內容")

# 讀信（FR-23：讀取寄件者網域為 tldrnewsletter.com、寄送日期為指定日期的信件純文字內容；
# 呼叫端決定要讀哪一天，這個 Client 本身不假設「昨天」或「今天」）
from datetime import date

texts = client.fetch_emails_from_domain_on_date("tldrnewsletter.com", date(2026, 8, 7))
```

## 設計限制（務必遵守）

1. 寄信只支援純文字信件（`send_text`），不做附件、HTML 信件等其他能力；讀信只支援「依寄件者網域＋指定日期」篩選收件匣信件（`fetch_emails_from_domain_on_date`），不做其他資料夾、其他篩選條件、標記已讀/刪除等操作——目前呼叫端只需要這兩個能力，需要更多功能時再依實際需求擴充。
2. `GMAIL_PASSWORD` 一律要求是應用程式密碼：Google 自 2022 年起，已開啟兩步驟驗證的帳號必須用應用程式密碼才能通過 SMTP／IMAP 驗證，一般登入密碼會被拒絕，這是 Google 官方機制，不是本模組的限制。
3. 寄信這個 Client 設計上是「備援管道」，不是主要通知手段——目前呼叫端是 `src/bot/webhook.py` 的 `_notify_robin_of_error()`，只在 Telegram 私訊 Robin 失敗時才會觸發，平常不會用到，見 SPEC.md FR-19b（服務健康與治理）。
4. 讀信用寄件者網域比對（`_is_from_domain()`）而非主旨關鍵字，並用信件 `Date` header 換算台灣時間精確比對指定日期（`_sent_on_date()`），避免 IMAP `SINCE`/`BEFORE` 以日曆日為單位、不保證時區精確所造成的誤差；目前唯一呼叫端是 Step 3.1 每日技術摘要（FR-23），固定台灣時間 23:00 讀取「當天」的 TLDR 電子報。

## 對應 Spec

[docs/specs/SPEC.md](../../docs/specs/SPEC.md) FR-19b、FR-23、[docs/ADR/discuss/submodules-core.md](../../docs/ADR/discuss/submodules-core.md)
