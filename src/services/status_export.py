"""Public, read-only status snapshot for the dashboard (docs/).

The repo is PUBLIC, so this file is public too. It holds only counts, channel
names, statuses and times. Never: tokens, emails, Drive folder/file IDs,
filenames, video titles, YouTube video IDs or raw error text.
"""
import re
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.services.quota import QuotaLedger

WAITING = ("DISCOVERED", "QUEUED", "READY", "RETRY_WAIT")
RUNNING = ("DOWNLOADING", "UPLOADING", "PROCESSING", "VERIFYING")
_ERR_CODES = ("quotaExceeded", "uploadLimitExceeded", "invalid_grant", "accessNotConfigured",
              "forbidden", "notFound", "timeout", "rateLimitExceeded", "VPN")


def _iso(v):
    if v is None:
        return None
    if isinstance(v, str):
        v = datetime.fromisoformat(v)
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    return v.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_error(msg) -> str | None:
    """Only a known error code survives; everything else becomes a generic label."""
    if not msg:
        return None
    for code in _ERR_CODES:
        if code.lower() in str(msg).lower():
            return code
    return "error (see Actions log)"


def build_status(engine: Engine, settings: dict | None = None, last_run: dict | None = None) -> dict:
    with engine.connect() as c:
        chans = [dict(r._mapping) for r in c.execute(text("""
            SELECT c.channel_id, c.channel_name, c.enabled, c.timezone,
                   COALESCE(o.status,'not_connected') AS auth_status
            FROM channels c LEFT JOIN oauth_credentials o ON o.channel_id=c.channel_id
            ORDER BY c.channel_name"""))]
        vids = [dict(r._mapping) for r in c.execute(text("""
            SELECT id, channel_id, upload_status, file_size, attempts, privacy_status,
                   scheduled_publish_at, updated_at FROM videos ORDER BY updated_at DESC"""))]
        errs = [dict(r._mapping) for r in c.execute(text("""
            SELECT h.created_at, h.event_type, h.message FROM upload_history h
            WHERE h.event_status IN ('FAILED','ERROR','error','failed')
            ORDER BY h.created_at DESC LIMIT 5"""))]
    names = {ch["channel_id"]: ch["channel_name"] for ch in chans}
    idx = {cid: f"ch-{i + 1}" for i, cid in enumerate(names)}
    per = {cid: {"uploaded": 0, "queued": 0, "failed": 0, "last": None} for cid in names}
    for v in vids:
        p = per.get(v["channel_id"])
        if not p:
            continue
        s = v["upload_status"]
        p["uploaded"] += s == "COMPLETED"
        p["queued"] += s in WAITING
        p["failed"] += s == "FAILED"
        if s == "COMPLETED" and p["last"] is None:
            p["last"] = v["updated_at"]

    channels = [{
        "id": idx[ch["channel_id"]], "youtube_channel_id": ch["channel_id"], "name": ch["channel_name"],
        "thumbnail_url": None, "auth_status": ch["auth_status"], "enabled": bool(ch["enabled"]),
        "drive_folder_name": "Drive folder (hidden)", "drive_folder_id": None,
        "uploaded": per[ch["channel_id"]]["uploaded"], "queued": per[ch["channel_id"]]["queued"],
        "failed": per[ch["channel_id"]]["failed"], "subscribers": None, "views_28d": None,
        "watch_hours_28d": None, "ctr": None, "last_upload_at": _iso(per[ch["channel_id"]]["last"]),
        "timezone": ch["timezone"]} for ch in chans]

    progress = {"COMPLETED": 100, "VERIFYING": 100, "PROCESSING": 100}
    queue = [{
        "id": f"job-{v['id']}", "file_name": f"Video #{v['id']}", "channel_id": idx.get(v["channel_id"]),
        "channel_name": names.get(v["channel_id"], "?"), "status": v["upload_status"],
        "progress": progress.get(v["upload_status"], 0), "size_bytes": v["file_size"],
        "attempts": v["attempts"], "error": None, "updated_at": _iso(v["updated_at"]),
        "youtube_video_id": None} for v in vids[:50]]

    ledger = QuotaLedger(engine, settings)
    used, limit = ledger.used(), ledger.limit
    errors = [{"at": _iso(e["created_at"]), "source": e["event_type"], "message": safe_error(e["message"])}
              for e in errs]
    n = lambda st: sum(1 for v in vids if v["upload_status"] in st)  # noqa: E731
    active = sum(1 for ch in channels if ch["enabled"] and ch["auth_status"] == "active")
    now = _iso(datetime.now(timezone.utc))
    return {
        "generated_at": now, "live_snapshot": True,
        "overview": {
            "snapshot": True, "channels": {"total": len(channels), "active": active,
                                           "disabled": sum(1 for ch in channels if not ch["enabled"])},
            "uploaded_total": n(("COMPLETED",)), "queue": n(WAITING), "processing": n(RUNNING),
            "failed": n(("FAILED",)),
            "scheduled": sum(1 for v in vids if v["scheduled_publish_at"] and v["upload_status"] != "COMPLETED"),
            "views_28d": None, "subscribers_total": None, "quota": {"used": used, "limit": limit},
            "last_run": last_run or {"at": now, "status": "success", "workflow": "upload.yml"},
            "latest_errors": errors},
        "channels": channels, "queue": queue,
        "quota": {"snapshot": True, "projects": [{"name": "Google Cloud project", "used": used, "limit": limit,
                                                   "uploads_today": None}],
                  "cost": {"upload": ledger.cost("videos.insert"), "thumbnail": ledger.cost("thumbnails.set"),
                           "metadata_update": ledger.cost("videos.update"), "list": 1},
                  "resets_at": None, "history": []},
    }


_FORBIDDEN = re.compile(r"(ya29\.|1//0|@gmail\.com|refresh_token|access_token|postgres(ql)?://|AIza)", re.I)


def assert_public_safe(blob: str) -> None:
    if _FORBIDDEN.search(blob):
        raise ValueError("status export contains something that must never be public")
