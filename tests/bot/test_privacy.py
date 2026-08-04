"""src/bot/privacy.py 的單元測試（docs/specs/privacy-masking/SPEC.md FR-1～FR-3）。"""
from unittest.mock import MagicMock

import pytest

from src.bot import privacy

MASKED = privacy._MASK_TEXT


# --- mask_regex：FR-13a 8 類格式正例 ---

@pytest.mark.parametrize(
    "text",
    [
        "我的身分證字號是 A123456789",
        "我的身分證字號是 a123456789",
        "手機是 0912345678",
        "手機是 0912-345-678",
        "手機是 0912 345 678",
        "市話 04-22334455",
        "市話 (04)2233-4455",
        "信用卡卡號 1234-5678-9012-3456",
        "銀行帳戶 822-123456789012",
        "中國信託帳戶 123456789012",
        "健保卡號 123456789012",
        "地址是台北市中正區忠孝東路一段1號",
        "車牌 ABC-1234",
        "車牌 1234-AB",
    ],
)
def test_mask_regex_detects_and_masks_pii_positive_examples(text):
    masked, detected = privacy.mask_regex(text)
    assert detected is True
    assert MASKED in masked


# --- mask_regex：FR-13c 排除項目（生日／LINE ID）不應被誤判 ---

@pytest.mark.parametrize(
    "text",
    [
        "我的生日是 1998-05-20",
        "我是民國 82 年出生的",
        "我的生日是 5/20",
        "我的 LINE ID 是 @robinma",
        "LINE ID: robin_ma_1225",
        "今天天氣真好",
    ],
)
def test_mask_regex_does_not_mask_excluded_or_unrelated_text(text):
    masked, detected = privacy.mask_regex(text)
    assert detected is False
    assert masked == text


def test_mask_regex_masks_multiple_occurrences_in_same_text():
    text = "身分證 A123456789，手機 0912345678"
    masked, detected = privacy.mask_regex(text)
    assert detected is True
    assert masked.count(MASKED) == 2
    assert "A123456789" not in masked
    assert "0912345678" not in masked


def test_mask_regex_empty_string_not_detected():
    masked, detected = privacy.mask_regex("")
    assert masked == ""
    assert detected is False


# --- mask_with_llm ---

def test_mask_with_llm_detects_when_llm_changes_text():
    llm_client = MagicMock()
    llm_client.generate_text.return_value = f"我的手機是{MASKED}"

    masked, detected = privacy.mask_with_llm("我的手機是 零九一二 三四五 六七八", llm_client)

    assert masked == f"我的手機是{MASKED}"
    assert detected is True
    llm_client.generate_text.assert_called_once()


def test_mask_with_llm_not_detected_when_llm_returns_text_unchanged():
    llm_client = MagicMock()
    llm_client.generate_text.return_value = "今天天氣真好"

    masked, detected = privacy.mask_with_llm("今天天氣真好", llm_client)

    assert masked == "今天天氣真好"
    assert detected is False


def test_mask_with_llm_strips_surrounding_whitespace_before_comparing():
    llm_client = MagicMock()
    llm_client.generate_text.return_value = "今天天氣真好\n"

    masked, detected = privacy.mask_with_llm("今天天氣真好", llm_client)

    assert masked == "今天天氣真好"
    assert detected is False


# --- mask_text：統一入口 ---

def test_mask_text_without_llm_client_only_runs_regex_layer():
    masked, detected = privacy.mask_text("手機是 0912345678", llm_client=None)
    assert detected is True
    assert masked == "手機是 " + MASKED


def test_mask_text_without_llm_client_and_no_pii_returns_original():
    masked, detected = privacy.mask_text("今天天氣真好", llm_client=None)
    assert masked == "今天天氣真好"
    assert detected is False


def test_mask_text_passes_regex_masked_text_to_llm_layer_not_raw_text():
    llm_client = MagicMock()
    llm_client.generate_text.return_value = f"手機是 {MASKED}"

    masked, detected = privacy.mask_text("手機是 0912345678", llm_client=llm_client)

    assert detected is True
    assert masked == f"手機是 {MASKED}"
    called_prompt = llm_client.generate_text.call_args.args[0]
    assert "0912345678" not in called_prompt
    assert MASKED in called_prompt


def test_mask_text_llm_layer_catches_what_regex_misses():
    llm_client = MagicMock()
    llm_client.generate_text.return_value = f"我的手機是{MASKED}"

    masked, detected = privacy.mask_text("我的手機是零九一二三四五六七八", llm_client=llm_client)

    assert detected is True
    assert masked == f"我的手機是{MASKED}"


def test_mask_text_both_layers_find_nothing():
    llm_client = MagicMock()
    llm_client.generate_text.return_value = "今天天氣真好"

    masked, detected = privacy.mask_text("今天天氣真好", llm_client=llm_client)

    assert masked == "今天天氣真好"
    assert detected is False


# --- mask_text：ADR-3 語意層暫時性外部錯誤優雅降級 ---


def test_mask_text_falls_back_to_regex_only_when_llm_call_raises():
    """Robin 實測撞到的真實情境：Gemini 503 過載，語意層呼叫拋例外，不應讓整則訊息處理失敗，
    優雅降級成只回傳 Regex 層結果。"""
    llm_client = MagicMock()
    llm_client.generate_text.side_effect = RuntimeError("503 UNAVAILABLE")

    masked, detected = privacy.mask_text("手機是 0912345678", llm_client=llm_client)

    assert masked == "手機是 " + MASKED
    assert detected is True  # Regex 層有偵測到


def test_mask_text_falls_back_to_regex_only_when_llm_call_raises_and_regex_found_nothing():
    llm_client = MagicMock()
    llm_client.generate_text.side_effect = RuntimeError("503 UNAVAILABLE")

    masked, detected = privacy.mask_text("今天天氣真好", llm_client=llm_client)

    assert masked == "今天天氣真好"
    assert detected is False
