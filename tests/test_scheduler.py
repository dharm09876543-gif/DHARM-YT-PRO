from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import text

from src.auth.token_manager import AuthRevoked
from src.scheduler.executor import due_jobs, run_all, summary
from src.scheduler.planner import channel_slots, next_free_slot, plan_channel, replan_if_stale
from src.services.quota import QuotaLedger
from src.upload.duplicate_guard import insert_if_new
from src.upload.pipeline import UploadContext
from src.upload.resumable import ResumableUploader
from src.utils.timeutil import utcnow
from tests.fakes import FakeDriveService, FakeUploadServer, FakeYT, fake_media_factory, folder
from tests.test_upload import CHUNK, LocalDrive

IST = ZoneInfo("Asia/Kolkata")
SCHED = {"scheduler": {"enabled": True, "timezone": "Asia/Kolkata", "slots": ["09:00", "17:00"],
                       "lead_minutes": 60, "overrides": {"CH_KEY": {"slots": ["10:00"], "timezone": "America/New_York"}}}}


def _disc(engine, cid, fid):
    return insert_if_new(engine, {"channel_id": cid, "drive_file_id": fid, "drive_file_version": "1",
                                  "drive_md5": None, "filename": fid + ".mp4", "file_size": 1,
                                  "mime_type": "video/mp4", "title": fid, "description": "", "tags": [],
                                  "category_id": "22", "privacy_status": "public",
                                  "thumbnail_drive_id": None})[0]


def test_next_free_slot_respects_lead_tz_and_taken():
    now = datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc)            # 08:30 IST
    s1 = next_free_slot(["09:00", "17:00"], "Asia/Kolkata", set(), now, lead_minutes=60)
    assert s1.astimezone(IST).strftime("%d %H:%M") == "06 17:00"      # 09:00 lead ke andar
    s2 = next_free_slot(["09:00", "17:00"], "Asia/Kolkata", {s1}, now, 60)
    assert s2.astimezone(IST).strftime("%d %H:%M") == "07 09:00"
    assert next_free_slot([], "Asia/Kolkata", set(), now) is None


def test_channel_override_by_key_and_timezone():
    chcfg = {"channels": [{"key": "CH_KEY", "channel_id": "UC1"}]}
    slots, tz = channel_slots({"channel_id": "UC1", "timezone": "Asia/Kolkata"}, SCHED, chcfg)
    assert slots == ["10:00"] and tz == "America/New_York"
    slots, tz = channel_slots({"channel_id": "UC2", "timezone": "Asia/Dubai"}, SCHED, chcfg)
    assert slots == ["09:00", "17:00"] and tz == "Asia/Dubai"


def test_plan_assigns_unique_slots_private(engine, channel):
    cid = channel["channel_id"]
    ids = [_disc(engine, cid, f"f{i}") for i in range(3)]
    now = datetime(2026, 11, 6, 3, 0, tzinfo=timezone.utc)
    import src.scheduler.planner as pl
    orig = pl.utcnow
    pl.utcnow = lambda: now
    try:
        assert plan_channel(engine, channel, SCHED) == 3
    finally:
        pl.utcnow = orig
    with engine.connect() as c:
        rows = c.execute(text("SELECT upload_status, privacy_status, scheduled_publish_at FROM videos ORDER BY id")).all()
        sch = c.execute(text("SELECT COUNT(DISTINCT scheduled_at), COUNT(*) FROM schedules")).first()
    assert all(r[0] == "QUEUED" and r[1] == "private" and r[2] for r in rows)
    assert tuple(sch) == (3, 3)
    assert plan_channel(engine, channel, SCHED) == 0                   # dobara: kuch nahi


def test_scheduler_disabled_queues_immediately(engine, channel):
    vid = _disc(engine, channel["channel_id"], "x")
    assert plan_channel(engine, channel, {"scheduler": {"enabled": False}}) == 1
    with engine.connect() as c:
        r = c.execute(text("SELECT upload_status, scheduled_publish_at, privacy_status FROM videos WHERE id=:v"), {"v": vid}).first()
    assert tuple(r) == ("QUEUED", None, "public")


def test_replan_when_publish_time_passed(engine, channel):
    vid = _disc(engine, channel["channel_id"], "late")
    plan_channel(engine, channel, SCHED)
    with engine.begin() as c:
        c.execute(text("UPDATE videos SET scheduled_publish_at=:t"), {"t": utcnow() - timedelta(hours=1)})
    v = {"id": vid, "scheduled_publish_at": utcnow() - timedelta(hours=1)}
    assert replan_if_stale(engine, v, channel, SCHED)
    with engine.connect() as c:
        from src.utils.timeutil import parse_dt
        assert parse_dt(c.execute(text("SELECT scheduled_publish_at FROM videos")).scalar()) > utcnow()


def _ctx_factory(engine, cipher, servers, tmp, fail_for=None):
    quota = QuotaLedger(engine, {"quota": {"daily_limit_units": 10000}})

    def factory(ch):
        if fail_for and ch["channel_id"] in fail_for:
            raise fail_for[ch["channel_id"]]
        files = {"vid_" + ch["channel_id"]: {"name": "a.mp4", "mimeType": "video/mp4", "parents": [ch["drive_folder_id"]],
                                            "size": str(300 * 1024), "createdTime": "2026", "version": "1", "md5Checksum": "m" + ch["channel_id"]}}
        drv = LocalDrive(FakeDriveService(files), {"vid_" + ch["channel_id"]: 300 * 1024})
        srv = servers.setdefault(ch["channel_id"], FakeUploadServer())
        srv.next_video_id = "yt_" + ch["channel_id"][-4:]
        yt = FakeYT(srv, ch["channel_id"], quota)
        ctx = UploadContext(engine, cipher, yt, drv, quota, {"uploads": {"max_retries": 3}}, worker="w",
                            tmp_dir=tmp, sleep=lambda s: None)
        ctx.uploader = lambda: ResumableUploader(engine, cipher, yt, quota, chunk_size=CHUNK,
                                                 media_factory=fake_media_factory, sleep=lambda s: None)
        return ctx
    return factory, quota


def test_run_all_isolates_channel_failures(engine, cipher, chsvc, tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    ids = ["UC" + c * 22 for c in "xyz"]
    for i, cid in enumerate(ids):
        chsvc.add(cid, f"Ch{i}", f"root{i}"); chsvc.save_tokens(cid, "1//r")
    servers = {}
    factory, quota = _ctx_factory(engine, cipher, servers, tmp_path,
                                  fail_for={ids[1]: AuthRevoked("reconnect karein")})
    sched = {"scheduler": {"enabled": True, "slots": ["09:00", "21:00"], "lead_minutes": 60}}
    res = run_all(engine, chsvc.list(), factory, {"uploads": {"max_concurrent_uploads": 1}}, sched,
                  steps=("discover", "plan", "upload"))
    by = {r.channel_id: r for r in res}
    assert by[ids[0]].completed == 1 and by[ids[2]].completed == 1
    assert by[ids[1]].stopped == "auth" and not by[ids[1]].ok
    assert "ruka: auth" in summary(res)


def test_run_all_concurrent_threads(engine, cipher, chsvc, tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    ids = ["UC" + c * 22 for c in "pq"]
    for cid in ids:
        chsvc.add(cid, cid[-3:], "r" + cid); chsvc.save_tokens(cid, "1//r")
    factory, _ = _ctx_factory(engine, cipher, {}, tmp_path)
    res = run_all(engine, chsvc.list(), factory, {"uploads": {"max_concurrent_uploads": 2}},
                  {"scheduler": {"enabled": False}}, steps=("discover", "plan", "upload"))
    assert sorted(r.completed for r in res) == [1, 1]


def test_quota_pause_keeps_jobs_queued_across_channels(engine, cipher, chsvc, tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    ids = ["UC" + c * 22 for c in "mn"]
    for cid in ids:
        chsvc.add(cid, cid[-3:], "r" + cid); chsvc.save_tokens(cid, "1//r")
    factory, quota = _ctx_factory(engine, cipher, {}, tmp_path)
    quota.mark_exceeded()
    res = run_all(engine, chsvc.list(), factory, {"uploads": {}}, {"scheduler": {"enabled": False}},
                  steps=("discover", "plan", "upload"))
    assert all(r.stopped == "quota" and r.discovered == 1 for r in res)
    with engine.connect() as c:
        assert {r[0] for r in c.execute(text("SELECT upload_status FROM videos"))} == {"QUEUED"}


def test_due_jobs_respects_retry_time(engine, channel):
    from src.upload.state import transition
    cid = channel["channel_id"]
    a, b = _disc(engine, cid, "a"), _disc(engine, cid, "b")
    transition(engine, a, "QUEUED"); transition(engine, b, "QUEUED")
    transition(engine, b, "RETRY_WAIT", next_retry_at=utcnow() + timedelta(hours=1))
    assert due_jobs(engine, cid) == [a]
    assert set(due_jobs(engine, cid, now=utcnow() + timedelta(hours=2))) == {a, b}
