"""DB-only audit report: status counts, stale locks, failures, verify pending, cleanup pending,
duplicate YouTube ids, sessions without URI, aaj ka quota."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text

from src.cleanup.drive_trash import blocking_reasons
from src.services.quota import QuotaLedger
from src.utils.timeutil import parse_dt, utcnow


def audit(engine, settings: dict | None = None) -> dict:
    settings = settings or {}
    stale_min = int(settings.get("uploads", {}).get("stale_lock_minutes", 90))
    now = utcnow()
    with engine.connect() as c:
        counts = {r[0]: r[1] for r in c.execute(text(
            "SELECT upload_status, COUNT(*) FROM videos GROUP BY upload_status"))}
        vids = [dict(r._mapping) for r in c.execute(text("SELECT * FROM videos"))]
        dup = [r[0] for r in c.execute(text("""SELECT youtube_video_id FROM videos WHERE youtube_video_id IS NOT NULL
                                               GROUP BY youtube_video_id HAVING COUNT(*) > 1"""))]
        multi = [r[0] for r in c.execute(text("""SELECT video_id FROM upload_sessions WHERE session_status='active'
                                                 GROUP BY video_id HAVING COUNT(*) > 1"""))]
    stale = [v for v in vids if v["locked_by"] and parse_dt(v["locked_at"])
             and parse_dt(v["locked_at"]) < now - timedelta(minutes=stale_min)]
    failed = [v for v in vids if v["upload_status"] == "FAILED"]
    verifying = [v for v in vids if v["upload_status"] in ("PROCESSING", "VERIFYING")]
    no_id_done = [v for v in vids if v["upload_status"] == "COMPLETED" and not v["youtube_video_id"]]
    cleanup_wait = [(v, blocking_reasons(v, settings)) for v in vids
                    if v["upload_status"] == "COMPLETED" and not v["drive_trashed_at"]]
    q = QuotaLedger(engine, settings)
    lines = ["== Upload audit ==", "Status: " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "koi video nahi"),
             f"Quota aaj (Pacific {q.today()}): {q.used()}/{q.limit}" + (" PAUSED" if q.is_paused() else "")]
    for v in stale:
        lines.append(f"!! Atka lock: video {v['id']} ({v['filename']}) by {v['locked_by']}")
    for v in failed:
        lines.append(f"!! FAILED: video {v['id']} {v['filename']}: {v['last_error']}")
    for v in verifying:
        lines.append(f".. Verify baaki: video {v['id']} yt={v['youtube_video_id']} ({v['processing_status']})")
    for v, why in cleanup_wait:
        lines.append(f".. Drive trash baaki: video {v['id']}" + (f" -> {', '.join(why)}" if why else " (agle run mein)"))
    for y in dup:
        lines.append(f"!! Duplicate YouTube id: {y}")
    for vid in multi:
        lines.append(f"!! Ek se zyada active session: video {vid}")
    for v in no_id_done:
        lines.append(f"!! COMPLETED par youtube id nahi: video {v['id']}")
    problems = len(stale) + len(failed) + len(dup) + len(multi) + len(no_id_done)
    lines.append("Sab theek." if not problems else f"{problems} problem(s) - upar dekhein.")
    return {"counts": counts, "problems": problems, "stale": [v["id"] for v in stale],
            "failed": [v["id"] for v in failed], "text": "\n".join(lines)}
