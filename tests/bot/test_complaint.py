"""src/bot/complaint.py 的單元測試（對應 robinson SPEC.md FR-60～FR-63，Step 1.9）。"""
from src.bot import complaint


def test_create_complaint_inserts_row(fake_db):
    complaint_id = complaint.create_complaint(fake_db, user_id=1, content="客服態度不好")

    row = fake_db.select("complaints", where="id = %s", params=(complaint_id,), fetch_one=True)
    assert row["user_id"] == 1
    assert row["content"] == "客服態度不好"


def test_build_analysis_prompt_includes_content_and_two_required_sections():
    prompt = complaint.build_analysis_prompt("客服態度不好")

    assert "客服態度不好" in prompt
    assert "可能的問題點" in prompt
    assert "修正/優化建議" in prompt
