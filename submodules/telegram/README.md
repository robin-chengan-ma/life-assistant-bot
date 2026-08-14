# telegram

Telegram Bot 通用 Client，以 `requests` 直接呼叫 Telegram Bot HTTP API，不綁定 async 框架，可被任何 Python 專案直接 import 使用。

## 環境變數

見 `.env.example`：

| 變數 | 說明 |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | Bot Token。本模組不主動讀取這個變數，只是給獨立測試/reuse 時參考；正式串接時由呼叫端決定要傳哪一組 Token（Robinson 專案目前僅一組共用的 `TELEGRAM_BOT_TOKEN`） |

> 註：Robinson 專案另有 `ROBIN_TELEGRAM_TOKEN` 變數，但那是 Robin 的 Telegram 使用者 ID（用於後端層判斷發訊息的人是不是管理者），並非 Bot Token，不屬於本模組的關注範圍，故不列於上表。

## 安裝

```bash
pip install -r submodules/telegram/requirements.txt
```

## 使用範例

```python
from submodules.telegram.client import TelegramClient

client = TelegramClient(bot_token="<TELEGRAM_BOT_TOKEN>")

client.send_chat_action(chat_id=12345, action="typing")
client.send_text(chat_id=12345, text="今天的待辦事項有 3 筆喔！")
client.send_photo(chat_id=12345, photo="https://example.com/chart.png", caption="這是你的心情趨勢圖")
```

## 分工說明

- 本模組只負責「送出訊息」這類可重用的基礎操作。
- Webhook 接收、指令路由、對話狀態機等較複雜的邏輯：留給 Phase 1 backend 層決定要用什麼框架（可能沿用主專案 `requirements.txt` 中的 `python-telegram-bot` 處理 webhook dispatch），與本模組互不衝突。

## 對應 Spec

[docs/specs/SPEC.md](../../docs/specs/SPEC.md)「Submodules 共用子模組基礎骨架」、[docs/ADR/discuss/submodules-core.md](../../docs/ADR/discuss/submodules-core.md)
