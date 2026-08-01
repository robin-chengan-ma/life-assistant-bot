# voice

語音（Speech-to-Text）通用 Client，目前串接 Groq Whisper API，用 `requests` 直接呼叫其 OpenAI 相容 REST 端點，把語音檔轉成文字。

## 環境變數

見 `.env.example`：

| 變數 | 說明 |
| --- | --- |
| `VOICE_API_KEY` | Groq API Key |

## 安裝

```bash
pip install -r submodules/voice/requirements.txt
```

## 使用範例

```python
from submodules.voice.client import VoiceClient

client = VoiceClient(api_key="gsk_...")

text = client.transcribe(audio_bytes, filename="voice.ogg", mime_type="audio/ogg")
```

## 設計限制（務必遵守）

1. 只支援轉文字（`transcribe`），不做語音生成（TTS）等其他能力——目前呼叫端只需要「語音轉文字」這個能力，需要更多功能時再依實際需求擴充。
2. 語音長度限制、修正窗口限制等商業邏輯（見 robinson SPEC.md FR-14／FR-15）一律由呼叫端（`src/bot/`）決定，本模組只負責「把 bytes 丟給 Groq 換回文字」。
3. 刻意不安裝官方 `groq` SDK：Whisper 轉錄端點是單純的 multipart POST，用 `requests` 直接呼叫即可，避免多一個重量依賴（比照 `submodules/telegram` 的作法）。

## 對應 Spec

[docs/specs/submodules-core/SPEC.md](../../docs/specs/submodules-core/SPEC.md)、[docs/specs/robinson/SPEC.md](../../docs/specs/robinson/SPEC.md) FR-14／FR-15／ADR-12
