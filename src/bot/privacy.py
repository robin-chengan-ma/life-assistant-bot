"""個資偵測與遮蔽邏輯（對應 docs/specs/privacy-masking/SPEC.md FR-1～FR-3）。

雙層防線：
1. `mask_regex()` —— Regex 硬規則，涵蓋 robinson SPEC.md FR-13a 列出的 8 類台灣常見個資格式
   （身分證字號、手機號碼、市話號碼、銀行帳戶、信用卡號、健保卡號、地址、車牌號碼）。免費、
   不依賴任何外部服務，永遠可以運作。
2. `mask_with_llm()` —— LLM 語意辨識，補 Regex 抓不到的變形寫法（全形數字、中文數字、額外空白
   或符號閃避偵測），排除生日與 LINE ID（FR-13c）。使用獨立申請的 `GEMINI_API_PRIVACY_KEY`
   （見 ADR-1），不佔用既有聊天/長記憶/圖片辨識的配額。

`mask_text()` 是統一入口：先跑 Regex 層，把已遮蔽的文字（不是明碼）送進 LLM 語意層（見 FR-3）；
`llm_client=None` 時只執行 Regex 層、不報錯（見 ADR-2 優雅降級）。

2026-08-04 追加（見 privacy-masking SPEC.md ADR-3）：`llm_client` 有給，但實際呼叫時遇到暫時性
外部錯誤（Gemini 503 過載、逾時等）也要優雅降級成只回傳 Regex 層結果，不能讓整個訊息處理流程
被這一層輔助防線的暫時性故障拖垮。Robin 實際使用時撞到 Gemini `503 UNAVAILABLE`（「模型目前需求
量大」，屬於外部服務短暫過載，非本專案額度或程式問題），觸發 `mask_with_llm()` 未捕捉例外，導致
整則訊息完全沒有回覆、只跳出「系統發生未預期例外」；`mask_text()` 因此新增 try/except，理由與
ADR-2「Key 缺失時只跑 Regex 層」完全一致——語意層是輔助防線，永遠不該讓必要的訊息處理失敗。
完整的外部 API 重試機制（FR-19i）仍留待 Phase 2 Step 2.5，這裡先做最小必要的防禦性降級。

已知限制（見 spec「風險與緩解」）：Regex 對純數字格式（銀行帳戶／健保卡號／信用卡號）刻意抓寬
（10～16 碼連續數字），可能誤判其他無關的長數字為個資；地址規則只涵蓋常見「城市+路街+號」寫法，
不是完整地址剖析器。這些都是刻意的「寧可誤判也不要漏抓」取捨，符合個人使用場景的保守防護原則。
"""
import logging
import re

logger = logging.getLogger("robinson.privacy")

_MASK_TEXT = "[已遮蔽個資]"

# FR-13a 8 類格式：身分證字號／手機／市話／信用卡（分組格式）／銀行帳戶（銀行代碼-帳號）／
# 銀行帳戶或健保卡或信用卡（純數字 10~16 碼，格式本身重疊、遮蔽動作相同，不需要精確分類）／
# 地址／車牌（兩種常見排列）。這幾個都用 \b 包住確保數字/英文字母前後有明確邊界，避免誤吃到
# 更長數字序列的一部分。
_PII_PATTERNS_WITH_BOUNDARY = [
    r"[A-Za-z][12]\d{8}",
    r"09\d{2}(?:[-\s]?\d{3}){2}",
    r"\(?0[2-8]\)?[-\s]?\d{3,4}[-\s]?\d{4}",
    r"(?:\d{4}[-\s]){3}\d{4}",
    r"\d{3}-\d{10,14}",
    r"\d{10,16}",
    r"[A-Za-z]{2,3}-\d{3,4}",
    r"\d{3,4}-[A-Za-z]{2,3}",
]

# 地址不套用 \b：中文字元在 Python re 裡也算 \w，兩個連續中文字之間（例如「是」和「台」之間）
# 不會形成邊界，套 \b 反而會讓「地址是台北市...」這種前面緊接中文字的情況完全比對不到。
# 這個 pattern 本身用具體的縣市名稱清單起頭，已經有足夠明確的邊界，不需要額外的 \b。
_ADDRESS_PATTERN = (
    r"(?:台北|新北|桃園|台中|臺中|台南|臺南|高雄|基隆|新竹|嘉義|苗栗|彰化|南投|雲林|屏東|"
    r"宜蘭|花蓮|台東|臺東|澎湖|金門|連江)[市縣][^\s，。,]{0,20}(?:路|街|大道|巷|弄)[^\s，。,]{0,10}\d+號"
)

_COMBINED_PATTERN = re.compile(
    "|".join([rf"\b(?:{pattern})\b" for pattern in _PII_PATTERNS_WITH_BOUNDARY] + [_ADDRESS_PATTERN]),
    re.IGNORECASE,
)

_LLM_MASK_PROMPT = (
    "你是個資遮蔽助手，只做一件事：檢查以下文字裡有沒有台灣常見的敏感個資"
    "（身分證字號、手機號碼、市話號碼、銀行帳戶、信用卡號、健保卡號、地址、車牌號碼），"
    "包含刻意變形寫法（例如用全形數字、中文數字、額外空白或符號閃避偵測）。\n"
    "生日與 LINE ID 不算個資，絕對不能遮蔽，就算格式看起來像數字或帳號也一樣。\n"
    f"固定遮蔽替換文字是「{_MASK_TEXT}」，已經被替換成這個文字的部分不要再處理。\n"
    "找到符合的內容就把該段內容整段替換成這個固定文字，其餘文字一字不動；"
    "完全沒找到任何個資的話，原封不動地回傳輸入文字。\n"
    "只回傳處理後的文字本身，不要加任何說明、標記、前後綴或引號包裝。\n\n"
    "文字內容：{text}"
)


def mask_regex(text: str) -> tuple[str, bool]:
    """Regex 硬規則層：回傳（遮蔽後文字, 是否有偵測到）。"""
    detected = False

    def _replace(match: re.Match) -> str:
        nonlocal detected
        detected = True
        return _MASK_TEXT

    masked = _COMBINED_PATTERN.sub(_replace, text)
    return masked, detected


def mask_with_llm(text: str, llm_client) -> tuple[str, bool]:
    """LLM 語意辨識層：回傳（遮蔽後文字, 是否有偵測到）。

    `text` 應該是已經跑過 `mask_regex()` 的版本，避免把還沒處理的明碼送進 Prompt。
    """
    result = llm_client.generate_text(_LLM_MASK_PROMPT.format(text=text)).strip()
    return result, result != text.strip()


def mask_text(text: str, llm_client=None) -> tuple[str, bool]:
    """統一入口：先跑 Regex 層，再（若有提供 `llm_client`）跑 LLM 語意層。

    回傳（最終遮蔽後文字, 兩層任一層是否有偵測到）。`llm_client=None` 時只執行 Regex 層，
    不拋出例外（見 ADR-2 優雅降級）；`llm_client` 有給但呼叫時遇到暫時性外部錯誤（例如 Gemini
    過載、逾時）同樣優雅降級成只回傳 Regex 層結果，不拋出例外（見 ADR-3 優雅降級）。
    """
    masked, regex_detected = mask_regex(text)
    if llm_client is None:
        return masked, regex_detected

    try:
        masked, llm_detected = mask_with_llm(masked, llm_client)
    except Exception:
        logger.exception("個資遮蔽語意層呼叫失敗，優雅降級成只使用 Regex 層結果")
        return masked, regex_detected

    return masked, regex_detected or llm_detected
