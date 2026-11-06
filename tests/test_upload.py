import json
from datetime import timedelta
from pathlib import Path

import pytest
from googleapiclient.http import HttpMockSequence
from sqlalchemy import text

from src.clients.drive_client import DriveClient
from src.clients.errors import is_quota_exceeded, is_retryable
from src.services.quota import QuotaExceeded, QuotaLedger
from src.upload.duplicate_guard import insert_if_new
from src.upload.pipeline import UploadContext, process_video
from src.upload.resumable import ResumableUploader, SessionLost
from src.upload.state import InvalidTransition, acquire_lock, release_lock, transition
from src.upload.verifier import verify_upload
from src.upload.youtube_client import YouTubeClient
from src.utils.timeutil import utcnow
from tests.fakes import (FakeDriveService, FakeMediaIo, FakeUploadServer, FakeYT, fake_media_factory,
                         folder, http_error)

KB = 1024
CHUNK = 256 * KB
SETTINGS = {"uploads": {"chunk_size_mb": 1, "max_retries": 3, "retry_wait_minutes": 30,
                        "stale_lock_minutes": 90}, "quota": {"daily_limit_units": 10000}}


def _video(engine, cid, fid="v1", thumb=None, size=600 * KB):
    vid, _ = insert_if_new(engine, {
        "channel_id": cid, "drive_file_id": fid, "drive_file_version": "m-" + fid, "drive_md5": None,
        "filename": f"{fid}.mp4", "file_size": size, "mime_type": "video/mp4", "title": f"Title {fid}",
        "description": "d", "tags": ["a"], "category_id": "22", "privacy_status": "private",
        "thumbnail_drive_id": thumb})
    transition(engine, vid, "QUEUED", scheduled_publish_at=utcnow() + timedelta(days=1))
    return vid


class LocalDrive(DriveClient):
    def __init__(self, svc, sizes):
        super().__init__(svc)
        self.sizes, self.downloads = sizes, 0

    def download_to(self, file_id, path, expected_md5=None, **_):
        self.downloads += 1
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"x" * self.sizes[file_id])
        return Path(path)


@pytest.fixture
def ctx(engine, cipher, channel, tmp_path):
    files = {"tf": folder(["root"]),
             "th1": {"name": "v1.jpg", "mimeType": "image/jpeg", "parents": [], "size": "5"}}
    files["tf"]["name"] = "thumbnails"
    drive = LocalDrive(FakeDriveService(files, {"th1": b"JPEG!"}), {"v1": 600 * KB, "v2": 300 * KB})
    quota = QuotaLedger(engine, SETTINGS)
    server = FakeUploadServer()
    c = UploadContext(engine, cipher, FakeYT(server, channel["channel_id"], quota), drive, quota,
                      SETTINGS,
                      worker="w1", tmp_dir=tmp_path / "tmp", media_factory=fake_media_factory,
                      thumb_media_cls=FakeMediaIo, sleep=lambda s: None)
    c.server = server
    c.uploader = lambda: ResumableUploader(engine, cipher, c.yt, quota, chunk_size=CHUNK,
                                           media_factory=fake_media_factory, max_retries=3,
                                           sleep=lambda s: None)
    return c


def _v(engine, vid):
    with engine.connect() as c:
        return c.execute(text("SELECT * FROM videos WHERE id=:v"), {"v": vid}).first()


def _hist(engine, vid):
    with engine.connect() as c:
        return [(r.event_type, r.event_status) for r in c.execute(
            text("SELECT * FROM upload_history WHERE video_id=:v ORDER BY id"), {"v": vid})]


# ---------- state machine + locks ----------
def test_state_machine_rejects_invalid(engine, channel):
    vid = _video(engine, channel["channel_id"])
    with pytest.raises(InvalidTransition):
        transition(engine, vid, "COMPLETED")
    transition(engine, vid, "CANCELLED")
    with pytest.raises(InvalidTransition):
        transition(engine, vid, "QUEUED")


def test_lock_exclusive_and_stale_takeover(engine, channel):
    vid = _video(engine, channel["channel_id"])
    t0 = utcnow()
    assert acquire_lock(engine, vid, "A", 90, now=t0)
    assert not acquire_lock(engine, vid, "B", 90, now=t0 + timedelta(minutes=10))
    assert acquire_lock(engine, vid, "B", 90, now=t0 + timedelta(minutes=91))   # stale
    release_lock(engine, vid, "A")                                              # A ka lock nahi raha
    assert _v(engine, vid).locked_by == "B"
    release_lock(engine, vid, "B")
    assert _v(engine, vid).locked_by is None


# ---------- end-to-end pipeline ----------
def test_full_upload_thumbnail_verify_completed(engine, ctx, channel):
    vid = _video(engine, channel["channel_id"], thumb="th1")
    assert process_video(ctx, vid) == "COMPLETED"
    v = _v(engine, vid)
    assert v.youtube_video_id == "yt_vid_001" and v.verified_channel_id == channel["channel_id"]
    assert v.thumbnail_status == "set" and v.locked_by is None
    assert ctx.server.initiations == 1
    body = ctx.server.sessions["https://upload.fake/s1"]["body"]
    assert body["status"]["privacyStatus"] == "private" and "publishAt" in body["status"]
    states = [s for e, s in _hist(engine, vid)]
    for st in ["DOWNLOADING", "READY", "UPLOADING", "PROCESSING", "VERIFYING", "COMPLETED"]:
        assert st in states
    with engine.connect() as c:
        s = c.execute(text("SELECT * FROM upload_sessions WHERE video_id=:v"), {"v": vid}).first()
        assert s.session_status == "completed" and s.bytes_uploaded == 600 * KB
        assert "upload.fake" not in s.encrypted_session_uri          # URI encrypted
        assert ctx.cipher.decrypt(s.encrypted_session_uri) == "https://upload.fake/s1"
    assert ctx.quota.used() == 1600 + 50 + 1
    assert not list(Path(ctx.tmp_dir).glob("*"))                       # temp file saaf


def test_5xx_and_timeout_retried_with_status_query(engine, ctx, channel):
    ctx.server.fail_plan = [None, http_error(503), "lost_response", None]
    vid = _video(engine, channel["channel_id"])
    assert process_video(ctx, vid) == "COMPLETED"
    assert ctx.server.initiations == 1                                  # kabhi naya insert nahi


def test_crash_then_resume_existing_session_no_new_insert(engine, ctx, channel):
    vid = _video(engine, channel["channel_id"])
    ctx.server.fail_plan = [None, RuntimeError("runner mar gaya")]      # non-retryable crash
    assert process_video(ctx, vid) == "RETRY_WAIT"
    with engine.connect() as c:
        s = c.execute(text("SELECT * FROM upload_sessions WHERE video_id=:v"), {"v": vid}).first()
    assert s.session_status == "active" and s.bytes_uploaded == CHUNK
    transition(engine, vid, "QUEUED")                                   # retry ka time
    assert process_video(ctx, vid) == "COMPLETED"
    assert ctx.server.initiations == 1                                  # wahi session resume hua
    assert ctx.quota.cost("videos.insert") == 1600 and ctx.quota.used() == 1600 + 1


def test_upload_actually_finished_before_crash_is_adopted(engine, ctx, channel):
    vid = _video(engine, channel["channel_id"], fid="v2")               # 300KB = 2 chunks
    ctx.server.fail_plan = [None, "lost_response"]
    up = ResumableUploader(engine, ctx.cipher, ctx.yt, None, chunk_size=CHUNK,
                           media_factory=fake_media_factory, max_retries=0, sleep=lambda s: None)
    ctx.uploader = lambda: up
    assert process_video(ctx, vid) == "RETRY_WAIT"      # server ke paas poora, hamein jawab nahi mila
    transition(engine, vid, "QUEUED")
    assert process_video(ctx, vid) == "COMPLETED"
    assert ctx.server.initiations == 1 and _v(engine, vid).youtube_video_id == "yt_vid_001"


def test_session_expired_reconciles_via_channel_uploads(engine, ctx, channel):
    vid = _video(engine, channel["channel_id"])
    ctx.server.fail_plan = [None, RuntimeError("crash")]
    process_video(ctx, vid)
    ctx.server.sessions["https://upload.fake/s1"]["expired"] = True
    ctx.server.videos["already_there"] = {}
    ctx.yt.recent = [{"title": "Title v1", "id": "already_there"}]
    transition(engine, vid, "QUEUED")
    assert process_video(ctx, vid) == "COMPLETED"
    assert _v(engine, vid).youtube_video_id == "already_there" and ctx.server.initiations == 1
    assert ("reconcile", "found") in _hist(engine, vid)


def test_session_expired_and_not_on_channel_restarts_fresh(engine, ctx, channel):
    vid = _video(engine, channel["channel_id"])
    ctx.server.fail_plan = [None, RuntimeError("crash")]
    process_video(ctx, vid)
    ctx.server.sessions["https://upload.fake/s1"]["expired"] = True
    transition(engine, vid, "QUEUED")
    assert process_video(ctx, vid) == "COMPLETED"
    assert ctx.server.initiations == 2 and ("reconcile", "not_found") in _hist(engine, vid)
    with engine.connect() as c:
        st = [r[0] for r in c.execute(text("SELECT session_status FROM upload_sessions WHERE video_id=:v ORDER BY id"), {"v": vid})]
    assert st == ["expired", "completed"]


def test_quota_exceeded_pauses_and_keeps_queued(engine, ctx, channel):
    vid = _video(engine, channel["channel_id"])
    ctx.server.fail_plan = [http_error(403, "quotaExceeded")]
    with pytest.raises(QuotaExceeded):
        process_video(ctx, vid)
    assert _v(engine, vid).upload_status == "QUEUED" and ctx.quota.is_paused()
    vid2 = _video(engine, channel["channel_id"], fid="v2")
    with pytest.raises(QuotaExceeded):
        process_video(ctx, vid2)                                        # upload shuru hi nahi
    assert _v(engine, vid2).upload_status == "QUEUED"


def test_low_quota_blocks_before_upload(engine, ctx, channel):
    ctx.quota.record("videos.insert", 6)                                # 9600 used
    vid = _video(engine, channel["channel_id"])
    with pytest.raises(QuotaExceeded):
        process_video(ctx, vid)
    assert ctx.server.initiations == 0 and _v(engine, vid).upload_status == "QUEUED"


def test_permanent_failure_after_max_retries(engine, ctx, channel):
    vid = _video(engine, channel["channel_id"])
    for _ in range(3):
        ctx.server.fail_plan = [ValueError("bad")]
        with engine.begin() as c:
            c.execute(text("UPDATE upload_sessions SET session_status='expired'"))
        st = process_video(ctx, vid)
        if st == "RETRY_WAIT":
            transition(engine, vid, "QUEUED")
    assert st == "FAILED" and _v(engine, vid).attempts == 3 and "bad" in _v(engine, vid).last_error


def test_verify_pending_then_completed(engine, ctx, channel):
    ctx.yt.upload_status = "uploaded"
    vid = _video(engine, channel["channel_id"])
    assert process_video(ctx, vid) == "VERIFYING"
    ctx.yt.upload_status = "processed"
    assert process_video(ctx, vid) == "COMPLETED"
    assert ctx.server.initiations == 1


def test_thumbnail_failure_does_not_fail_video(engine, ctx, channel):
    ctx.yt.thumb_error = http_error(403, "forbidden")
    vid = _video(engine, channel["channel_id"], thumb="th1")
    assert process_video(ctx, vid) == "COMPLETED"
    assert _v(engine, vid).thumbnail_status == "failed"


def test_context_uploader_uses_settings(ctx):
    up = UploadContext.uploader(ctx)
    assert up.chunk == 1024 * 1024 and up.max_retries == 3


def test_locked_job_skipped(engine, ctx, channel):
    vid = _video(engine, channel["channel_id"])
    acquire_lock(engine, vid, "other-runner")
    assert process_video(ctx, vid) == "LOCKED" and ctx.server.initiations == 0


# ---------- verifier ----------
class _YT:
    def __init__(self, item):
        self.item = item

    def get_video(self, _):
        return self.item


def test_verifier_cases():
    C = "UC" + "c" * 22
    ok = {"snippet": {"channelId": C}, "status": {"uploadStatus": "processed"}}
    assert verify_upload(_YT(ok), "x", C).ok
    wrong = {"snippet": {"channelId": "UCother"}, "status": {"uploadStatus": "processed"}}
    r = verify_upload(_YT(wrong), "x", C); assert not r.ok and r.final
    rej = {"snippet": {"channelId": C}, "status": {"uploadStatus": "rejected", "rejectionReason": "duplicate"}}
    r = verify_upload(_YT(rej), "x", C); assert not r.ok and r.final and "duplicate" in r.reason
    r = verify_upload(_YT(None), "x", C); assert not r.ok and not r.final


def test_error_classification():
    assert is_retryable(http_error(503)) and is_retryable(TimeoutError())
    assert not is_retryable(http_error(400, "invalidMetadata"))
    assert is_quota_exceeded(http_error(403, "quotaExceeded")) and not is_retryable(http_error(403, "quotaExceeded"))


# ---------- real googleapiclient resumable protocol ----------
class RecordingSeq(HttpMockSequence):
    def __init__(self, iterable):
        super().__init__(iterable)
        self.requests = []

    def request(self, uri, method="GET", body=None, headers=None, *a, **k):
        self.requests.append((method, uri, dict(headers or {})))
        return super().request(uri, method, body, headers, *a, **k)


def _real_yt(seq):
    from googleapiclient.discovery import build
    return YouTubeClient(build("youtube", "v3", http=seq, static_discovery=True))


def test_real_googleapiclient_resume_after_restart(engine, cipher, channel, tmp_path):
    from googleapiclient.http import MediaFileUpload
    vid = _video(engine, channel["channel_id"])
    f = tmp_path / "v.mp4"; f.write_bytes(b"z" * (600 * KB))
    media = lambda p, m, c: MediaFileUpload(p, mimetype="video/mp4", chunksize=c, resumable=True)  # noqa: E731
    sess_uri = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=XYZ"
    seq1 = RecordingSeq([({"status": "200", "location": sess_uri}, ""),
                         ({"status": "308", "range": "bytes=0-262143"}, ""),
                         ({"status": "503"}, "")])
    up1 = ResumableUploader(engine, cipher, _real_yt(seq1), None, chunk_size=CHUNK, media_factory=media,
                            max_retries=0, sleep=lambda s: None)
    with pytest.raises(Exception):
        up1.upload(vid, f, {"snippet": {"title": "t"}, "status": {"privacyStatus": "private"}})
    assert seq1.requests[0][0] == "POST" and "uploadType=resumable" in seq1.requests[0][1]
    # "naya process": pehle status query (bytes */size), phir baaki chunks; koi POST nahi
    seq2 = RecordingSeq([({"status": "308", "range": "bytes=0-262143"}, ""),
                         ({"status": "308", "range": "bytes=0-524287"}, ""),
                         ({"status": "200"}, json.dumps({"id": "REALID", "snippet": {"channelId": "x"}}))])
    up2 = ResumableUploader(engine, cipher, _real_yt(seq2), None, chunk_size=CHUNK, media_factory=media,
                            max_retries=0, sleep=lambda s: None)
    resp = up2.upload(vid, f, {"snippet": {"title": "t"}, "status": {"privacyStatus": "private"}})
    assert resp["id"] == "REALID"
    assert [m for m, _, _ in seq2.requests] == ["PUT", "PUT", "PUT"]
    assert all(u == sess_uri for _, u, _ in seq2.requests)
    assert seq2.requests[0][2]["Content-Range"] == f"bytes */{600 * KB}"
    assert seq2.requests[1][2]["Content-Range"].startswith("bytes 262144-524287/")


def test_real_googleapiclient_session_gone_raises_session_lost(engine, cipher, channel, tmp_path):
    from googleapiclient.http import MediaFileUpload
    vid = _video(engine, channel["channel_id"])
    f = tmp_path / "v.mp4"; f.write_bytes(b"z" * (300 * KB))
    with engine.begin() as c:
        c.execute(text("""INSERT INTO upload_sessions(video_id, encrypted_session_uri, bytes_uploaded, total_bytes)
                          VALUES (:v, :u, 262144, :t)"""),
                  {"v": vid, "u": cipher.encrypt("https://up/old"), "t": 300 * KB})
    seq = RecordingSeq([({"status": "404"}, '{"error":{"code":404,"errors":[{"reason":"notFound"}]}}')])
    up = ResumableUploader(engine, cipher, _real_yt(seq), None, chunk_size=CHUNK,
                           media_factory=lambda p, m, c: MediaFileUpload(p, mimetype="video/mp4", chunksize=c, resumable=True),
                           max_retries=0, sleep=lambda s: None)
    with pytest.raises(SessionLost):
        up.upload(vid, f, {"snippet": {"title": "t"}, "status": {}})
    assert seq.requests[0][0] == "PUT"
