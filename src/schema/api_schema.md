# Robinson API Schema

> 本文件記錄 Robinson 對外／內部使用的所有 API 路由，包含 Telegram webhook 入口與內建指令路由。依 [robinson SPEC.md](../../docs/specs/robinson/SPEC.md) 的 ADR-10，與 `db_schema.md` 同樣視為活文件，隨開發進度更新；狀態欄位標記 `計畫中` / `已實作`，實作完成後記得回來更新狀態。

## 使用方式

新增一個路由時，複製下方樣板填入實際內容。

```markdown
### `<METHOD> <path>`

**狀態**：計畫中 / 已實作
**觸發方式**：<Telegram 文字/指令 或 HTTP 呼叫方式>
**權限**：<任何人 / 已驗證使用者 / 僅 Owner>
**對應 FR**：<FR-xx>

**Request**：
​```json
{}
​```

**Response**：
​```json
{}
​```

**備註**：
```

---

## 路由清單

### `GET /healthz`

**狀態**：已實作，已部署上線（`https://life-assistant-bot-yhkm.onrender.com/healthz`）
**觸發方式**：cron-job.org 每 10 分鐘呼叫一次
**權限**：無需驗證（公開，僅回應健康狀態，不回傳任何使用者資料）
**對應 FR**：FR-3

**Response**：
```json
{"status": "ok"}
```

**備註**：純 keep-alive 用途，避免 Render 免費方案 15 分鐘無請求即休眠。

---

### `POST /telegram/webhook`

**狀態**：計畫中
**觸發方式**：Telegram Bot API 主動推送使用者訊息
**權限**：依訊息內容與使用者身分於內部再判斷（通關密碼驗證、功能開關等）
**對應 FR**：FR-1、FR-2、FR-5～FR-8

**備註**：所有使用者文字/語音訊息的統一入口，內部再依內容路由到 `/rule`、`/function`、`/complaint` 或各功能模組的處理邏輯。

---

### `/rule`（內部路由，非對外 HTTP 端點）

**狀態**：計畫中
**觸發方式**：使用者於對話框輸入「我要看使用規則」或 `/rule`
**權限**：任何已驗證使用者（Robin 或家人）
**對應 FR**：FR-6d、FR-55

**Response**：固定文字，見 `docs/specs/robinson/SPEC.md` 附錄 A，不經過 LLM 生成。

---

### `/function`（內部路由，非對外 HTTP 端點）

**狀態**：計畫中
**觸發方式**：使用者於對話框輸入「我要看所有功能」或 `/function`
**權限**：任何已驗證使用者（Robin 或家人）
**對應 FR**：FR-56

**備註**：回傳所有功能清單並註記 Owner 專屬 vs 一般使用者可用；實際文字模板待有產品原型後補上（見 SPEC.md 附錄 B）。

---

### `/complaint`（內部路由，非對外 HTTP 端點）

**狀態**：計畫中
**觸發方式**：使用者於對話框輸入「我要客訴你」或 `/complaint`
**權限**：任何已驗證使用者（Robin 或家人）
**對應 FR**：FR-60～FR-63

**Response**：固定文字「請問你覺得哪個地方需要改進呢？」，接著進入等待客訴內容狀態；下一則訊息視為客訴內容並寫入資料庫。

**備註**：客訴內容會私訊給 Robin 並觸發 Gemini 分析（見 FR-62），此為刻意的隱私例外（見 FR-10/FR-11 的一般資料隔離原則）。

---

### `/set_invite_codes`（內部路由，非對外 HTTP 端點）

**狀態**：計畫中
**觸發方式**：Robin 輸入 `/set_invite_codes` 或「設定通關密碼」
**權限**：僅 Owner（Robin）
**對應 FR**：FR-6a～FR-6c

**備註**：進入引導式設定對話流（狀態機），詳見 ADR-8。
