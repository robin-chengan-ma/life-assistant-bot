"""共用重試工具：外部 API 呼叫套用「最多重試 3 次 + Exponential Backoff（1s/2s/4s）」的一致邏輯
（見 docs/specs/robinson/SPEC.md FR-19i、docs/specs/submodules-core/SPEC.md ADR-13）。

刻意不依賴任何特定 SDK 的例外型別——「什麼樣的例外才算暫時性、值得重試」因供應商而異
（HTTP 狀態碼、SDK 專屬例外類別都不一樣：requests 的 HTTPError、google-genai 的
ServerError/ClientError、googleapiclient 的 HttpError、smtplib 的各種 SMTPException…），
因此本模組只負責「重試迴圈本身＋Exponential Backoff 時間控制」，由呼叫端（各個
submodules/<name>/client.py）自行傳入 `is_retryable` 判斷式，決定哪些例外值得重試。

這是 submodules/ 底下唯一一個不是「包裝外部服務」的子模組，不涉及任何金鑰或連線資訊，
純粹是流程控制小工具，因此沒有 .env.example 需要的環境變數（仍保留該檔案並註明原因，
維持與其他子模組一致的四檔案結構，見 docs/specs/submodules-core/SPEC.md ADR-4／ADR-13）。
"""
import time
from collections.abc import Callable
from typing import TypeVar

_T = TypeVar("_T")

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = (1, 2, 4)


def call_with_retry(
    func: Callable[[], _T],
    is_retryable: Callable[[Exception], bool],
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    backoff_seconds: tuple = DEFAULT_BACKOFF_SECONDS,
) -> _T:
    """執行 `func()`，若拋出的例外經 `is_retryable` 判定為暫時性錯誤則重試。

    採 Exponential Backoff：第 1 次失敗等 `backoff_seconds[0]` 秒、第 2 次失敗等
    `backoff_seconds[1]` 秒，以此類推；重試次數用盡（或遇到 `is_retryable` 判定為
    False 的永久性錯誤，例如認證失敗、資源不存在）時，把最後一次的原始例外原封不動
    往外拋出，不包裝成新的例外型別，讓呼叫端既有的 `except` 邏輯不需要跟著改。
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as exc:
            if not is_retryable(exc):
                raise
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(backoff_seconds[attempt])
    assert last_exc is not None
    raise last_exc
