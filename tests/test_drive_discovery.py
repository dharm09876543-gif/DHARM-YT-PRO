import json

from sqlalchemy import text

from src.clients.drive_client import DriveClient
from src.upload.discovery import discover_channel, parse_sidecar
from src.upload.duplicate_guard import insert_if_new
from src.upload.metadata import VideoMetadata
from tests.fakes import FakeDriveService, folder


def _tree():
    files = {
        "vfold": folder(["root"]), "tfold": folder(["root"]),
        "v1": {"name": "Pehla Video.mp4", "mimeType": "video/mp4", "parents": ["root"], "size": "100",
               "createdTime": "2026-11-01T00:00:00Z", "version": "3", "md5Checksum": "m1"},
        "v2": {"name": "doosra_video.mov", "mimeType": "video/quicktime", "parents": ["vfold"], "size": "200",
               "createdTime": "2026-11-02T00:00:00Z", "version": "1", "md5Checksum": "m2"},
        "doc": {"name": "notes.pdf", "mimeType": "application/pdf", "parents": ["root"]},
        "t1": {"name": "Pehla Video.jpg", "mimeType": "image/jpeg", "parents": ["tfold"], "size": "10"},
        "s2": {"name": "doosra_video.json", "mimeType": "application/json", "parents": ["vfold"]},
    }
    files["vfold"]["name"] = "videos"; files["tfold"]["name"] = "thumbnails"
    content = {"s2": json.dumps({"title": "Sidecar Title", "description": "desc", "tags": "a, b"}).encode()}
    return FakeDriveService(files, content)


def test_list_videos_root_and_subfolder():
    d = DriveClient(_tree())
    vids = d.list_videos("root")
    assert [v["id"] for v in vids] == ["v1", "v2"]          # pdf nahi, createdTime order
    assert {"size", "mimeType", "createdTime", "md5Checksum", "version"} <= set(vids[0])
    assert d.find_thumbnail("root", "Pehla Video.mp4")["id"] == "t1"
    assert d.find_thumbnail("root", "doosra_video.mov") is None


def test_parse_sidecar_txt_and_json():
    t = parse_sidecar("x.txt", "Mera Title\nLine 1\ntags: yt, hindi\nLine 2".encode())
    assert t == {"title": "Mera Title", "description": "Line 1\nLine 2", "tags": ["yt", "hindi"]}
    j = parse_sidecar("x.json", b'{"title":"T","tags":["a"],"category_id":"27"}')
    assert j["category_id"] == "27" and j["tags"] == ["a"]


def test_discover_inserts_with_metadata_priority(engine, channel, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    drv = DriveClient(_tree())
    r = discover_channel(engine, channel, drv, {"tags": ["Default"], "description_footer": "Subscribe!"})
    assert (r.found, r.inserted, r.skipped, r.errors) == (2, 2, 0, [])
    with engine.connect() as c:
        rows = {x.drive_file_id: x for x in c.execute(text("SELECT * FROM videos"))}
    assert rows["v1"].title == "Pehla Video" and rows["v1"].thumbnail_drive_id == "t1"
    assert rows["v1"].drive_file_version == "m1" and rows["v1"].upload_status == "DISCOVERED"
    assert rows["v1"].description == "Subscribe!"
    assert rows["v2"].title == "Sidecar Title" and json.loads(rows["v2"].tags) == ["a", "b"]
    # dobara chalao: kuch naya nahi
    r2 = discover_channel(engine, channel, drv)
    assert (r2.inserted, r2.skipped) == (0, 2)


def test_gemini_used_when_no_sidecar(engine, channel):
    class G:
        def generate(self, filename, **kw):
            return VideoMetadata(title="AI Title", description="AI desc", tags=["ai"], category_id="27")
    discover_channel(engine, channel, DriveClient(_tree()), gemini=G())
    with engine.connect() as c:
        t = c.execute(text("SELECT title, category_id FROM videos WHERE drive_file_id='v1'")).first()
    assert tuple(t) == ("AI Title", "27")


def test_gemini_failure_falls_back_to_filename(engine, channel):
    class G:
        def generate(self, *a, **k):
            raise RuntimeError("quota")
    r = discover_channel(engine, channel, DriveClient(_tree()), gemini=G())
    assert r.inserted == 2
    with engine.connect() as c:
        assert c.execute(text("SELECT title FROM videos WHERE drive_file_id='v1'")).scalar() == "Pehla Video"


def _row(cid, fid="f1", ver="1", md5="mm"):
    return {"channel_id": cid, "drive_file_id": fid, "drive_file_version": ver, "drive_md5": md5,
            "filename": "a.mp4", "file_size": 1, "mime_type": "video/mp4", "title": "a", "description": "",
            "tags": [], "category_id": "22", "privacy_status": "private", "thumbnail_drive_id": None}


def test_duplicate_guard_same_file_and_same_content(engine, channel):
    cid = channel["channel_id"]
    vid, why = insert_if_new(engine, _row(cid))
    assert vid and why == "inserted"
    assert insert_if_new(engine, _row(cid)) == (None, "same_file")
    assert insert_if_new(engine, _row(cid, fid="copy_of_f1")) == (None, "same_content")
    vid2, why2 = insert_if_new(engine, _row(cid, ver="2", md5="new"))       # nayi version = naya video
    assert vid2 and why2 == "inserted"


def test_duplicate_guard_db_constraint_race(engine, channel, monkeypatch):
    import src.upload.duplicate_guard as dg
    cid = channel["channel_id"]
    insert_if_new(engine, _row(cid))
    monkeypatch.setattr(dg, "find_existing", lambda *a, **k: (None, None))   # pre-check ko bypass
    assert insert_if_new(engine, _row(cid)) == (None, "race")
