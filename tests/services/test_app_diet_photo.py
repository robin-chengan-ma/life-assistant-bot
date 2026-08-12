import base64
from io import BytesIO

import pytest
from PIL import Image

from src.services.app_diet_photo import (
    DietPhotoError,
    calculate_diet_nutrition,
    recognize_diet_photo,
)


class FakeLlm:
    def __init__(self, *, image_response="", text_response=""):
        self.image_response = image_response
        self.text_response = text_response
        self.image_call = None
        self.text_call = None

    def generate_with_image(self, prompt, image_bytes, mime_type="image/jpeg"):
        self.image_call = (prompt, image_bytes, mime_type)
        return self.image_response

    def generate_text(self, prompt):
        self.text_call = prompt
        return self.text_response


def _image_base64() -> str:
    buffer = BytesIO()
    Image.new("RGB", (20, 20), "white").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_recognize_diet_photo_returns_editable_description_and_uncertainties():
    llm = FakeLlm(image_response='{"description":"一碗白飯、一份煮高麗菜", "uncertain_items":["肉類被遮住"]}')

    result = recognize_diet_photo(llm, _image_base64(), "image/png")

    assert result == {"description": "一碗白飯、一份煮高麗菜", "uncertain_items": ["肉類被遮住"]}
    assert llm.image_call[2] == "image/jpeg"


def test_recognize_diet_photo_rejects_invalid_payload():
    with pytest.raises(DietPhotoError, match="格式不正確"):
        recognize_diet_photo(FakeLlm(), "not-base64", "image/jpeg")


def test_calculate_add_mode_recalculates_full_merged_description():
    llm = FakeLlm(text_response="CALORIES: 650\nPROTEIN: 32\nCARBS: 80\nFAT: 20")

    result = calculate_diet_nutrition(
        llm,
        "一杯無糖豆漿",
        existing_description="雞胸肉便當",
        mode="add",
    )

    assert result["description"] == "雞胸肉便當\n一杯無糖豆漿"
    assert "雞胸肉便當\n一杯無糖豆漿" in llm.text_call
    assert result["nutrition"]["estimated_calories"] == 650.0


def test_calculate_requires_a_parseable_nutrition_result():
    with pytest.raises(DietPhotoError, match="無法完成"):
        calculate_diet_nutrition(FakeLlm(text_response="unknown"), "神秘料理")
