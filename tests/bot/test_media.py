from src.bot import media


def test_save_media_upload_inserts_correct_row(fake_db):
    media.save_media_upload(fake_db, user_id=1, media_type="image", gdrive_url="https://drive/x")

    rows = fake_db.select("media_uploads", where="user_id = %s", params=(1,))
    assert len(rows) == 1
    assert rows[0]["media_type"] == "image"
    assert rows[0]["gdrive_url"] == "https://drive/x"


def test_save_media_upload_supports_audio_media_type(fake_db):
    media.save_media_upload(fake_db, user_id=7, media_type="audio", gdrive_url="https://drive/voice")

    rows = fake_db.select("media_uploads", where="user_id = %s", params=(7,))
    assert len(rows) == 1
    assert rows[0]["media_type"] == "audio"
