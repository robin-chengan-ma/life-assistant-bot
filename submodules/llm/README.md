# llm

LLM 通用 Client，目前串接 Gemini API（官方 `google-genai` SDK），一般呼叫模型固定 `gemini-3.5-flash-lite`（**2026-07-31 更新**：原本用 `gemini-flash-latest` 別名，實測發現它解析到的最新模型免費層額度極低（RPM 5／RPD 20），改用明確指定版本的 `gemini-3.5-flash-lite`，免費層實測 RPM 15／RPD 500，詳見 [docs/ADR/discuss/submodules-core.md](../../docs/ADR/discuss/submodules-core.md) ADR-6）。

**2026-07-31 移除 `generate_with_search()`（原 ADR-7）**：曾固定改用 `gemini-2.5-flash` 做 Google Search grounding，但 Robin 排查一把新產生的 Gemini API Key 時，發現該模型直接回傳 404「This model ... is no longer available to new users」——Gemini 2.5 世代已對新專案關閉存取，不是額度或選型問題。改為完全移除 grounding 功能，`generate_with_search()` 方法已刪除；查無答案時由呼叫端（`src/bot/chat.py`）改為誠實回覆不知道，並請使用者自行查詢後提供答案存檔，詳見 [docs/ADR/discuss/submodules-core.md](../../docs/ADR/discuss/submodules-core.md) ADR-8。

## 環境變數

見 `.env.example`：

| 變數 | 說明 |
| --- | --- |
| `LLM_API_KEY` | Gemini API Key。本模組不主動讀取這個變數，只是給獨立測試/reuse 時參考；正式串接時由呼叫端決定要傳哪一組 Key（Robinson 專案依用途拆成四把：一般問答 `GEMINI_API_BOT_KEY`、影像辨識 `GEMINI_API_IMAGE_KEY1`/`GEMINI_API_IMAGE_KEY2`（每次隨機擇一）、長文生成 `GEMINI_API_TEXT_KEY`，見主專案 `.env.example` 與 [docs/ADR/discuss/submodules-core.md](../../docs/ADR/discuss/submodules-core.md) ADR-12） |

## 安裝

```bash
pip install -r submodules/llm/requirements.txt
```

## 使用範例

```python
from submodules.llm.client import LLMClient

chat_client = LLMClient(api_key="<GEMINI_API_BOT_KEY>")
reply = chat_client.generate_text("幫我用一句話總結今天的待辦事項")

import random
image_key = random.choice(["<GEMINI_API_IMAGE_KEY1>", "<GEMINI_API_IMAGE_KEY2>"])
image_client = LLMClient(api_key=image_key)
with open("cert_question.jpg", "rb") as f:
    answer = image_client.generate_with_image(
        prompt="請解析這張證照題目截圖的題目與選項",
        image_bytes=f.read(),
    )
```

## 設計說明

- 使用 `google-genai`（`from google import genai`），而非已棄用的 `google-generativeai`。
- 對外暴露 `generate_text` / `generate_with_image` 兩個方法，未來更換或新增 LLM 供應商時，呼叫端介面不受影響。

## 對應 Spec

[docs/specs/SPEC.md](../../docs/specs/SPEC.md)「Submodules 共用子模組基礎骨架」、[docs/ADR/discuss/submodules-core.md](../../docs/ADR/discuss/submodules-core.md)
