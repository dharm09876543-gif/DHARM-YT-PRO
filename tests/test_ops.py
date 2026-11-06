from datetime import date, timedelta
from pathlib import Path

import httpx
import yaml
from sqlalchemy import text

from src.analytics.sync import sync_channel
from src.services.alerts import send_alert
from src.services.audit import audit
from src.upload.duplicate_guard import insert_if_new
from src.upload.state import acquire_lock, update_fields
from src.utils.timeutil import utcnow
from tests.fakes import _Exec

ROOT = Path(__file__).resolve().parent.parent


class FakeAnalytics:
    def __init__(self, resp):
        self.resp, self.kw = resp, None

    def reports(self):
        return self

    def query(self, **kw):
        self.kw = kw
        return _Exec(lambda: self.resp)


def test_analytics_sync_upsert_and_nulls(engine, channel):
    cid = channel["channel_id"]
    resp = {"columnHeaders": [{"name": "day"}, {"name": "views"}, {"name": "estimatedMinutesWatched"},
                              {"name": "subscribersGained"}],      # subscribersLost missing -> NULL
            "rows": [["2026-11-01", 100, 55.5, 3], ["2026-11-02", 120, 60, 1]]}
    fa = FakeAnalytics(resp)
    assert sync_channel(engine, fa, cid, date(2026, 11, 1), date(2026, 11, 2)) == 2
    assert fa.kw["ids"] == "channel==MINE" and "subscribersLost" in fa.kw["metrics"] and fa.kw["dimensions"] == "day"
    resp["rows"] = [["2026-11-02", 150, 70, 2]]
    sync_channel(engine, fa, cid, date(2026, 11, 2), date(2026, 11, 2))
    with engine.connect() as c:
        rows = c.execute(text("SELECT report_date, views, subscribers_lost, estimated_revenue FROM analytics_snapshots ORDER BY report_date")).all()
    assert len(rows) == 2 and rows[1][1] == 150 and rows[0][2] is None and rows[0][3] is None


def test_analytics_empty_rows(engine, channel):
    assert sync_channel(engine, FakeAnalytics({"columnHeaders": [], "rows": None}), channel["channel_id"],
                        date(2026, 1, 1), date(2026, 1, 2)) == 0


def test_alert_noop_without_env_and_sends_with_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert send_alert("x") is False
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc"); monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    seen = []
    cl = httpx.Client(transport=httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, json={"ok": True})))
    assert send_alert("Upload done", client=cl)
    assert seen[0].url.path == "/bot123:abc/sendMessage" and b"Upload done" in seen[0].content
    bad = httpx.Client(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("x"))))
    assert send_alert("y", client=bad) is False                         # never raises


def test_audit_reports_problems(engine, channel):
    cid = channel["channel_id"]
    def ins(fid):
        return insert_if_new(engine, {"channel_id": cid, "drive_file_id": fid, "drive_file_version": "1", "drive_md5": None,
                                      "filename": fid, "file_size": 1, "mime_type": "video/mp4", "title": fid,
                                      "description": "", "tags": [], "category_id": "22", "privacy_status": "private",
                                      "thumbnail_drive_id": None})[0]
    a, b, c_ = ins("a"), ins("b"), ins("c")
    update_fields(engine, a, upload_status="FAILED", last_error="boom")
    acquire_lock(engine, b, "dead-runner", now=utcnow() - timedelta(hours=5))
    update_fields(engine, c_, upload_status="COMPLETED", youtube_video_id="y1", verified_channel_id=cid)
    rep = audit(engine, {"uploads": {"stale_lock_minutes": 90}})
    assert rep["failed"] == [a] and rep["stale"] == [b] and rep["problems"] == 2
    assert "Drive trash pending" in rep["text"] and "boom" in rep["text"]


def test_workflows_valid_and_guard_database_url():
    wf = ROOT / ".github" / "workflows"
    for name in ["upload.yml", "analytics.yml", "health_check.yml", "drive_cleanup.yml"]:
        data = yaml.safe_load((wf / name).read_text())
        raw = (wf / name).read_text()
        assert "workflow_dispatch" in raw and "DATABASE_URL" in raw
        assert "secrets.DATABASE_URL" in raw and "DATABASE_URL secret is not set" in raw
        assert "concurrency" in data
        assert "ya29." not in raw and "1//" not in raw
    up = yaml.safe_load((wf / "upload.yml").read_text())
    trig = up.get("on") or up.get(True)
    assert trig["schedule"][0]["cron"] == "0 */3 * * *"
    for s in ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "TOKEN_ENCRYPTION_KEY", "GEMINI_API_KEY",
              "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]:
        assert f"secrets.{s}" in (wf / "upload.yml").read_text()


def test_main_wires_new_commands():
    src = (ROOT / "main.py").read_text()
    for cmd in ["connect", "run", "cleanup", "audit", "analytics"]:
        assert f'"{cmd}"' in src
    for script in ["connect_channel.py", "run_uploads.py", "verify_drive_cleanup.py", "audit_uploads.py", "sync_analytics.py"]:
        assert (ROOT / "scripts" / script).exists()


def test_runtime_ctx_factory_wiring(engine, cipher, channel, monkeypatch):
    from src.auth.token_manager import TokenManager
    from src.runtime import channel_defaults, make_ctx_factory
    monkeypatch.setattr(TokenManager, "services",
                        lambda self, cid, build=None: {"youtube": "YT", "drive": "DR", "analytics": "AN"})
    ctx = make_ctx_factory(engine, cipher, {"quota": {"daily_limit_units": 77}})(channel)
    assert ctx.yt.svc == "YT" and ctx.drive.svc == "DR" and ctx.analytics == "AN" and ctx.quota.limit == 77
    d = channel_defaults({"channels": [{"channel_id": channel["channel_id"], "defaults": {"tags": ["x"]}}]})
    assert d(channel) == {"tags": ["x"]}
