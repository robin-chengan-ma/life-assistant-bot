# llm

LLM 通用 Client，目前串接 Gemini API（官方 `google-genai` SDK），一般呼叫模型固定 `gemini-3.5-flash-lite`（**2026-07-31 更新**：原本用 `gemini-flash-latest` 別名，實測發現它解析到的最新模型免費層額度極低（RPM 5／RPD 20），改用明確指定版本的 `gemini-3.5-flash-lite`，免費層實測 RPM 15／RPD 500，詳見 [submodules-core SPEC.md](../../docs/specs/submodules-core/SPEC.md) ADR-6）。**`generate_with_search()` 是例外**：固定改用 `gemini-2.5-flash`，因為 Google Search grounding 的免費額度依模型世代分桶，`gemini-3.5-flash-lite` 所屬的 Gemini 3 世代免費 grounding 額度是 0，Gemini 2.5 世代才有 1,500 次/天免費額度，詳見 ADR-7。

## 環境變數

見 `.env.example`：

| 變數 | 說明 |
| --- | --- |
| `LLM_API_KEY` | Gemini API Key。本模組不主動讀取這個變數，只是給獨立測試/reuse 時參考；正式串接時由呼叫端決定要傳哪一組 Key（Robinson 專案依用途拆成四把：一般問答 `GEMINI_API_BOT_KEY`、影像辨識 `GEMINI_API_IMAGE_KEY1`/`GEMINI_API_IMAGE_KEY2`（每次隨機擇一）、長文生成 `GEMINI_API_TEXT_KEY`，見主專案 `.env.example` 與 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) ADR-12） |

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
- 對外暴露 `generate_text` / `generate_with_image` / `generate_with_search` 三個方法，未來更換或新增 LLM 供應商時，呼叫端介面不受影響。
- `generate_with_search(prompt)` 回傳 `(文字, 是否使用了 Google Search)` tuple；是否查網路由模型依 prompt 內容自行判斷（見 [chat-core SPEC.md](../../docs/specs/chat-core/SPEC.md) ADR-1），這裡只負責讀取 `grounding_metadata` 回報有沒有真的觸發搜尋，供呼叫端決定要不要詢問使用者是否存檔。這個方法固定用 `gemini-2.5-flash`，不受建構子傳入的 `model` 參數影響（見 ADR-7）。

## 對應 Spec

[docs/specs/submodules-core/SPEC.md](../../docs/specs/submodules-core/SPEC.md)
