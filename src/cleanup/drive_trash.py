"""Verified upload ke baad Drive video ko TRASH mein (files.update trashed=true).

Kabhi permanent delete nahi (files.delete is module mein kahin nahi). Trash 30 din tak recover ho sakta hai.
Shartein (sab zaroori):
  - video COMPLETED, youtube_video_id maujood
  - verified_channel_id == video ka channel_id
  - thumbnail tha to thumbnail_status == 'set' (settings.drive.cleanup_require_thumbnail)
  - Drive file ab bhi wahi content (md5 match) aur pehle se trash nahi
  - optional: YouTube se live dobara verify (yt diya ho to)
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.upload.state import log_event, update_fields
from src.upload.verifier import verify_upload
from src.utils.timeutil import utcnow


def blocking_reasons(v: dict, settings: dict | None = None) -> list[str]:
    d = (settings or {}).get("drive", {})
    r = []
    if d.get("cleanup_mode", "trash") != "trash":
        r.append("cleanup_mode 'trash' nahi hai")
    if d.get("cleanup_after_verification", True) is False:
        r.append("cleanup_after_verification band hai")
    if v.get("upload_status") != "COMPLETED":
        r.append(f"status {v.get('upload_status')} (COMPLETED chahiye)")
    if not v.get("youtube_video_id"):
        r.append("youtube_video_id nahi")
    if not v.get("verified_channel_id") or v.get("verified_channel_id") != v.get("channel_id"):
        r.append("channel verify nahi hua")
    if v.get("thumbnail_drive_id") and d.get("cleanup_require_thumbnail", True) \
            and v.get("thumbnail_status") != "set":
        r.append("thumbnail set/verify nahi hua")
    if v.get("drive_trashed_at"):
        r.append("pehle se trash")
    return r


def trash_video_file(engine: Engine, drive, video_id: int, settings: dict | None = None,
                     yt=None) -> tuple[bool, list[str]]:
    with engine.connect() as c:
        row = c.execute(text("SELECT * FROM videos WHERE id=:v"), {"v": video_id}).first()
    if not row:
        return False, ["video nahi mila"]
    v = dict(row._mapping)
    reasons = blocking_reasons(v, settings)
    if reasons:
        return False, reasons
    try:
        if yt is not None:
            vr = verify_upload(yt, v["youtube_video_id"], v["channel_id"])
            if not vr.ok:
                return False, [f"live verify fail: {vr.reason}"]
        meta = drive.get(v["drive_file_id"])
        if meta.get("trashed"):
            update_fields(engine, video_id, drive_trashed_at=utcnow())
            return False, ["Drive par pehle se trash"]
        if v.get("drive_md5") and meta.get("md5Checksum") and meta["md5Checksum"] != v["drive_md5"]:
            return False, ["Drive file badal gayi (md5 alag) - trash nahi kiya"]
        res = drive.trash(v["drive_file_id"])
        if not res.get("trashed"):
            return False, ["Drive ne trash confirm nahi kiya"]
    except Exception as e:  # noqa: BLE001
        log_event(engine, video_id, "drive_trash", "failed", str(e)[:500], v["youtube_video_id"])
        return False, [f"Drive error: {e}"]
    update_fields(engine, video_id, drive_trashed_at=utcnow())
    log_event(engine, video_id, "drive_trash", "ok", "Drive file trash mein (30 din recoverable)",
              v["youtube_video_id"])
    return True, []


def cleanup_channel(engine: Engine, drive, channel_id: str, settings: dict | None = None,
                    yt=None) -> dict:
    with engine.connect() as c:
        ids = [r[0] for r in c.execute(text("""SELECT id FROM videos WHERE channel_id=:c
                                               AND upload_status='COMPLETED' AND drive_trashed_at IS NULL"""),
                                       {"c": channel_id})]
    out = {"trashed": 0, "blocked": {}}
    for vid in ids:
        ok, why = trash_video_file(engine, drive, vid, settings, yt)
        if ok:
            out["trashed"] += 1
        else:
            out["blocked"][vid] = why
    return out
