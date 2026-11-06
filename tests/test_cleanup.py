from sqlalchemy import text

from src.cleanup.drive_trash import blocking_reasons, cleanup_channel, trash_video_file
from src.clients.drive_client import DriveClient
from src.upload.duplicate_guard import insert_if_new
from src.upload.state import update_fields
from tests.fakes import FakeDriveService

S = {"drive": {"cleanup_mode": "trash", "cleanup_after_verification": True, "cleanup_require_thumbnail": True}}


def _done(engine, cid, fid="d1", md5="m1", thumb=None, **over):
    vid, _ = insert_if_new(engine, {"channel_id": cid, "drive_file_id": fid, "drive_file_version": md5,
                                    "drive_md5": md5, "filename": "a.mp4", "file_size": 1, "mime_type": "video/mp4",
                                    "title": "t", "description": "", "tags": [], "category_id": "22",
                                    "privacy_status": "private", "thumbnail_drive_id": thumb})
    f = {"upload_status": "COMPLETED", "youtube_video_id": "yt_" + fid, "verified_channel_id": cid, **over}
    update_fields(engine, vid, **f)
    return vid


def _drive(**files):
    return FakeDriveService({k: {"name": k, "mimeType": "video/mp4", "parents": ["root"], "md5Checksum": v}
                             for k, v in files.items()})


def test_trash_only_when_all_conditions_met(engine, channel):
    cid = channel["channel_id"]
    svc = _drive(d1="m1")
    vid = _done(engine, cid)
    ok, why = trash_video_file(engine, DriveClient(svc), vid, S)
    assert ok and why == []
    assert ("update", "d1", {"trashed": True}) in svc.calls             # trash, not delete
    with engine.connect() as c:
        assert c.execute(text("SELECT drive_trashed_at FROM videos")).scalar()
        h = c.execute(text("SELECT event_type, event_status FROM upload_history WHERE event_type='drive_trash'")).first()
    assert tuple(h) == ("drive_trash", "ok")
    ok2, why2 = trash_video_file(engine, DriveClient(svc), vid, S)      # not again
    assert not ok2 and "already trashed" in why2


def test_blocking_reasons():
    cid = "UC" + "c" * 22
    base = {"upload_status": "COMPLETED", "youtube_video_id": "y", "verified_channel_id": cid, "channel_id": cid}
    assert blocking_reasons(base, S) == []
    assert blocking_reasons({**base, "upload_status": "VERIFYING"}, S)
    assert blocking_reasons({**base, "youtube_video_id": None}, S)
    assert blocking_reasons({**base, "verified_channel_id": "UCother"}, S)
    assert blocking_reasons({**base, "thumbnail_drive_id": "t", "thumbnail_status": "failed"}, S)
    assert blocking_reasons({**base, "thumbnail_drive_id": "t", "thumbnail_status": "set"}, S) == []
    assert blocking_reasons(base, {"drive": {"cleanup_mode": "delete"}})


def test_not_completed_or_changed_file_never_trashed(engine, channel):
    cid = channel["channel_id"]
    svc = _drive(d1="m1", d2="CHANGED", d3="m3")
    _done(engine, cid, "d1", "m1", upload_status="VERIFYING")
    _done(engine, cid, "d2", "m2")
    _done(engine, cid, "d3", "m3", thumb="th", thumbnail_status="failed")
    out = cleanup_channel(engine, DriveClient(svc), cid, S)
    assert out["trashed"] == 0
    assert not [c for c in svc.calls if c[0] == "update"]
    assert any("md5" in " ".join(w) for w in out["blocked"].values())


def test_live_reverify_blocks_on_failure(engine, channel):
    cid = channel["channel_id"]
    svc = _drive(d1="m1")
    vid = _done(engine, cid)

    class YT:
        def get_video(self, _):
            return None
    ok, why = trash_video_file(engine, DriveClient(svc), vid, S, yt=YT())
    assert not ok and "live verify" in why[0] and not svc.calls


def test_no_permanent_delete_anywhere():
    import pathlib
    for p in pathlib.Path("src").rglob("*.py"):
        src = p.read_text()
        assert ".delete(fileId" not in src and "files().delete" not in src, p
