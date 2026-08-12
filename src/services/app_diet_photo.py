"""Mobile App 飲食照片暫存辨識與營養估算服務。"""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any

from src.bot import body, image, privacy

_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_DESCRIPTION_LENGTH = 3000


class DietPhotoError(Exception):
    """飲食照片流程的可預期錯誤。"""


def _decode_image(image_base64: Any, mime_type: Any) -> bytes:
    if mime_type not in _ALLOWED_MIME_TYPES:
        raise DietPhotoError("僅支援 JPG、PNG 或 WebP 圖片")
    if not isinstance(image_base64, str) or not image_base64:
        raise DietPhotoError("請先拍照或選擇照片")
    try:
        raw = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DietPhotoError("圖片資料格式不正確") from exc
    if not raw or len(raw) > _MAX_IMAGE_BYTES:
        raise DietPhotoError("圖片大小不可超過 8 MB")
    try:
        return image.compress_image(raw)
    except Exception as exc:
        raise DietPhotoError("無法讀取這張圖片，請改用 JPG 或 PNG") from exc


def _json_object(response: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip(), flags=re.IGNORECASE)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise DietPhotoError("圖片辨識結果格式異常，請重試") from exc
    if not isinstance(parsed, dict):
        raise DietPhotoError("圖片辨識結果格式異常，請重試")
    return parsed


def recognize_diet_photo(llm_client, image_base64: Any, mime_type: Any) -> dict[str, Any]:
    """在記憶體內壓縮圖片並辨識食物；不儲存圖片或上傳 Drive。"""
    compressed = _decode_image(image_base64, mime_type)
    prompt = (
        "你是飲食辨識助手。只分析照片中實際看到的食物與飲料，不要先計算熱量或營養素。"
        "請輸出單一 JSON 物件，不得加 Markdown："
        '{"description":"可由使用者編輯的完整飲食描述，包含品項、份量、烹調方式、可見配料與飲料",'
        '"uncertain_items":["無法確定或可能遺漏、需要使用者確認的項目"]}。'
        "看不清楚就寫入 uncertain_items，不可臆測。若完全確定，uncertain_items 回傳空陣列。"
    )
    try:
        result = _json_object(llm_client.generate_with_image(prompt, compressed, mime_type="image/jpeg") or "")
    except DietPhotoError:
        raise
    except Exception as exc:
        raise DietPhotoError("圖片辨識暫時無法使用，請稍後再試") from exc

    description = result.get("description")
    uncertain = result.get("uncertain_items", [])
    if not isinstance(description, str) or not description.strip():
        raise DietPhotoError("無法辨識圖片中的飲食內容，請改用文字輸入")
    if not isinstance(uncertain, list):
        uncertain = []
    return {
        "description": description.strip()[:_MAX_DESCRIPTION_LENGTH],
        "uncertain_items": [str(item).strip() for item in uncertain if str(item).strip()][:10],
    }


def calculate_diet_nutrition(
    llm_client,
    confirmed_description: Any,
    *,
    existing_description: Any = None,
    mode: Any = "replace",
) -> dict[str, Any]:
    """根據使用者確認後的內容重新估算，新增模式必須以完整合併文字重算。"""
    if not isinstance(confirmed_description, str) or not confirmed_description.strip():
        raise DietPhotoError("請先確認飲食內容")
    if mode not in {"add", "replace"}:
        raise DietPhotoError("請選擇新增至今日紀錄或取代原紀錄")
    new_text = confirmed_description.strip()
    old_text = existing_description.strip() if isinstance(existing_description, str) else ""
    description = f"{old_text}\n{new_text}" if mode == "add" and old_text else new_text
    description, _detected = privacy.mask_text(description[:_MAX_DESCRIPTION_LENGTH])
    try:
        nutrition = body.estimate_diet_macros(llm_client, description)
    except Exception as exc:  # pragma: no cover - estimate 本身會降級，保留邊界防護
        raise DietPhotoError("營養估算暫時無法使用，請稍後再試") from exc
    if not any(value is not None for value in nutrition.values()):
        raise DietPhotoError("無法完成營養估算，請補充食物份量後再試")
    return {"description": description, "nutrition": nutrition}
