# retry

共用重試工具，提供 `call_with_retry()`：對外部 API 呼叫套用「最多重試 3 次 + Exponential Backoff（第 1 次失敗等 1 秒、第 2 次失敗等 2 秒、第 3 次失敗等 4 秒）」的一致邏輯（見 [docs/specs/SPEC.md](../../docs/specs/SPEC.md) FR-19i）。

這是 `submodules/` 底下唯一不是「包裝外部服務」的子模組——它不直接呼叫任何第三方 API，純粹是重試迴圈與 Exponential Backoff 的流程控制工具，供其他子模組（`llm`／`telegram`／`voice`／`gdrive`／`calendar`／`email`）內部呼叫（見 [docs/ADR/discuss/submodules-core.md](../../docs/ADR/discuss/submodules-core.md) ADR-13）。

## 環境變數

無。這個模組不涉及任何金鑰或連線資訊，`.env.example` 僅為維持與其他子模組一致的四檔案結構慣例而保留，內容為空。

## 安裝

```bash
pip install -r submodules/retry/requirements.txt
```

（這個檔案目前是空的，只用 Python 標準函式庫 `time`，不需要安裝任何第三方套件。）

## 使用範例

```python
from submodules.retry.client import call_with_retry

def _is_retryable(exc: Exception) -> bool:
    """由呼叫端自行定義：哪些例外算「暫時性錯誤」值得重試（例如連線逾時、5xx、429），
    哪些是「永久性錯誤」重試也沒用（例如認證失敗、資源不存在），因供應商而異。"""
    return isinstance(exc, (ConnectionError, TimeoutError))

result = call_with_retry(
    lambda: some_external_api_call(),
    is_retryable=_is_retryable,
)
```

## 設計限制（務必遵守）

1. 只負責「重試迴圈本身」，不內建任何 SDK 專屬的例外判斷邏輯——`is_retryable` 一律由呼叫端傳入，各子模組依自己串接的 SDK/REST API 決定什麼算暫時性錯誤（見各子模組 `client.py` 內的實際用法）。
2. 重試次數用盡、或遇到 `is_retryable` 判定為 `False` 的例外時，一律把「最後一次的原始例外」原封不動往外拋出，不包裝成新的例外型別——呼叫端既有的 `except` 邏輯不需要跟著改。
3. 預設 3 次、1s/2s/4s 皆可透過 `max_attempts`／`backoff_seconds` 參數覆寫，但一般呼叫端不需要覆寫，維持全專案一致的重試行為。

## 對應 Spec

[docs/specs/SPEC.md](../../docs/specs/SPEC.md) FR-19i、[docs/ADR/discuss/submodules-core.md](../../docs/ADR/discuss/submodules-core.md) ADR-13
