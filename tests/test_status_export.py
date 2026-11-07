import json

from sqlalchemy import text

from src.database.connection import get_engine, run_migrations
from src.services.status_export import assert_public_safe, build_status, safe_error


def _db(tmp_path):
    eng = get_engine(f"sqlite:///{tmp_path}/s.db")
    run_migrations(eng)
    with eng.begin() as c:
        c.execute(text("INSERT INTO channels(channel_id, channel_name, drive_folder_id) VALUES ('UCx','My Ch','FOLDERSECRET123')"))
        c.execute(text("INSERT INTO oauth_credentials(channel_id, encrypted_refresh_token, status) VALUES ('UCx','enc','active')"))
        for i, st in enumerate(["COMPLETED", "VERIFYING", "QUEUED", "FAILED"]):
            c.execute(text("""INSERT INTO videos(channel_id, drive_file_id, filename, title, upload_status, youtube_video_id)
                              VALUES ('UCx', :d, :f, 'Secret title', :s, :y)"""),
                      {"d": f"DRIVEFILE{i}", "f": f"private_name_{i}.mp4", "s": st, "y": f"YTID{i}" if i < 2 else None})
    return eng


def test_snapshot_counts_and_no_private_fields(tmp_path):
    snap = build_status(_db(tmp_path), {})
    o = snap["overview"]
    assert o["uploaded_total"] == 1 and o["processing"] == 1 and o["queue"] == 1 and o["failed"] == 1
    assert o["channels"] == {"total": 1, "active": 1, "disabled": 0}
    assert snap["channels"][0]["name"] == "My Ch" and snap["channels"][0]["uploaded"] == 1
    blob = json.dumps(snap, default=str)
    for leak in ("FOLDERSECRET123", "DRIVEFILE", "private_name", "Secret title", "YTID", "enc"):
        assert leak not in blob.replace("encrypt", ""), leak
    assert_public_safe(blob)


def test_safe_error_and_guard():
    assert safe_error("HttpError 403 quotaExceeded for x@gmail.com") == "quotaExceeded"
    assert safe_error("weird thing with path /home/x") == "error (see Actions log)"
    import pytest
    with pytest.raises(ValueError):
        assert_public_safe('{"x": "someone@gmail.com"}')
