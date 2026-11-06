"""Saare enabled channels ke liye: discover -> plan -> upload -> verify -> cleanup.

- Har channel alag try/except mein: ek channel fail ho to baaki chalte rahenge.
- max_concurrent_uploads = ek saath kitne channels (threads).
- Quota khatam -> naye uploads ruk jaate hain, jobs QUEUED rehte hain.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.auth.token_manager import AuthRevoked
from src.cleanup.drive_trash import cleanup_channel
from src.scheduler.planner import plan_channel, replan_if_stale
from src.services.quota import QuotaExceeded
from src.upload.discovery import discover_channel
from src.upload.pipeline import ChannelLimit, load_video, process_video
from src.utils.logging import get_logger
from src.utils.timeutil import utcnow

log = get_logger("dharm_yt.executor")


@dataclass
class ChannelRun:
    channel_id: str
    name: str = ""
    discovered: int = 0
    planned: int = 0
    completed: int = 0
    pending_verify: int = 0
    failed: int = 0
    trashed: int = 0
    stopped: str | None = None       # quota / auth / channel_limit
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and self.stopped not in ("auth",)


def due_jobs(engine: Engine, channel_id: str, now=None) -> list[int]:
    """Upload/finish ke liye taiyaar: QUEUED, retry ka time aa gaya, aadhe-adhure (crash), verify baaki."""
    now = now or utcnow()
    with engine.connect() as c:
        rows = c.execute(text("""
            SELECT id FROM videos WHERE channel_id=:c AND (
                upload_status IN ('QUEUED','DOWNLOADING','READY','UPLOADING','PROCESSING','VERIFYING')
                OR (upload_status='RETRY_WAIT' AND (next_retry_at IS NULL OR next_retry_at <= :now)))
            ORDER BY CASE WHEN youtube_video_id IS NULL THEN 1 ELSE 0 END,
                     scheduled_publish_at, id"""), {"c": channel_id, "now": now})
        return [r[0] for r in rows]


def run_channel(engine: Engine, channel: dict, ctx_factory, settings: dict, sched_cfg: dict,
                channels_cfg: dict | None = None, steps=("discover", "plan", "upload", "cleanup"),
                defaults_for=None) -> ChannelRun:
    res = ChannelRun(channel["channel_id"], channel.get("channel_name", ""))
    try:
        ctx = ctx_factory(channel)
        if "discover" in steps:
            d = discover_channel(engine, channel, ctx.drive,
                                 defaults_for(channel) if defaults_for else {})
            res.discovered = d.inserted
            res.errors += d.errors
        if "plan" in steps:
            res.planned = plan_channel(engine, channel, sched_cfg, channels_cfg)
        if "upload" in steps:
            limit = int(settings.get("uploads", {}).get("max_per_channel_per_run", 2))
            new_uploads = 0
            for vid in due_jobs(engine, channel["channel_id"]):
                v = load_video(engine, vid)
                fresh = not v.get("youtube_video_id")
                if fresh:
                    if new_uploads >= limit:
                        continue
                    replan_if_stale(engine, v, channel, sched_cfg, channels_cfg)
                    new_uploads += 1
                st = process_video(ctx, vid)
                res.completed += st == "COMPLETED"
                res.pending_verify += st == "VERIFYING"
                res.failed += st == "FAILED"
        if "cleanup" in steps:
            res.trashed = cleanup_channel(engine, ctx.drive, channel["channel_id"], settings)["trashed"]
    except QuotaExceeded as e:
        res.stopped = "quota"; res.errors.append(str(e))
    except AuthRevoked as e:
        res.stopped = "auth"; res.errors.append(str(e))
    except ChannelLimit as e:
        res.stopped = "channel_limit"; res.errors.append(str(e))
    except Exception as e:  # noqa: BLE001 - error isolation
        log.exception("Channel %s fail", channel["channel_id"])
        res.errors.append(f"{type(e).__name__}: {e}")
    return res


def run_all(engine: Engine, channels: list[dict], ctx_factory, settings: dict, sched_cfg: dict,
            channels_cfg: dict | None = None, steps=("discover", "plan", "upload", "cleanup"),
            defaults_for=None) -> list[ChannelRun]:
    workers = max(1, min(5, int(settings.get("uploads", {}).get("max_concurrent_uploads", 1))))
    args = (ctx_factory, settings, sched_cfg, channels_cfg, steps, defaults_for)
    if workers == 1 or len(channels) <= 1:
        return [run_channel(engine, ch, *args) for ch in channels]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(lambda ch: run_channel(engine, ch, *args), channels))


def summary(results: list[ChannelRun]) -> str:
    lines = []
    for r in results:
        s = (f"{'OK' if r.ok else '!!'} {r.name or r.channel_id}: naye={r.discovered} plan={r.planned} "
             f"upload={r.completed} verify-baaki={r.pending_verify} fail={r.failed} trash={r.trashed}")
        if r.stopped:
            s += f" [ruka: {r.stopped}]"
        if r.errors:
            s += " | " + "; ".join(r.errors[:2])
        lines.append(s)
    return "\n".join(lines) or "Koi enabled + connected channel nahi"
