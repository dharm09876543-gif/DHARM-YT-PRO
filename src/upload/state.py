"""Upload state machine + job locking.

DISCOVERED -> QUEUED -> DOWNLOADING -> READY -> UPLOADING -> PROCESSING -> VERIFYING -> COMPLETED
From any state: FAILED / RETRY_WAIT / CANCELLED. Lock: locked_by + locked_at; after the stale-lock timeout
another worker can take it over (crashed run).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.utils.timeutil import utcnow

TRANSITIONS: dict[str, set[str]] = {
    "DISCOVERED": {"QUEUED", "CANCELLED", "FAILED"},
    "QUEUED": {"DOWNLOADING", "UPLOADING", "RETRY_WAIT", "CANCELLED", "FAILED", "QUEUED"},
    "DOWNLOADING": {"READY", "RETRY_WAIT", "FAILED", "QUEUED"},
    "READY": {"UPLOADING", "DOWNLOADING", "RETRY_WAIT", "FAILED", "QUEUED"},
    "UPLOADING": {"PROCESSING", "DOWNLOADING", "RETRY_WAIT", "FAILED", "QUEUED"},   # re-download after a crash
    "PROCESSING": {"VERIFYING", "FAILED", "RETRY_WAIT"},
    "VERIFYING": {"COMPLETED", "FAILED", "VERIFYING", "RETRY_WAIT"},
    "RETRY_WAIT": {"QUEUED", "DOWNLOADING", "UPLOADING", "PROCESSING", "VERIFYING", "FAILED",
                   "CANCELLED"},
    "FAILED": {"QUEUED", "CANCELLED"},          # manual retry
    "COMPLETED": set(),
    "CANCELLED": set(),
}


class InvalidTransition(RuntimeError):
    pass


def get_status(engine: Engine, video_id: int) -> str:
    with engine.connect() as c:
        return c.execute(text("SELECT upload_status FROM videos WHERE id=:v"), {"v": video_id}).scalar()


def transition(engine: Engine, video_id: int, new: str, message: str | None = None,
               event: str = "state", **fields) -> None:
    """Only allows permitted transitions; writes to history."""
    with engine.begin() as c:
        cur = c.execute(text("SELECT upload_status FROM videos WHERE id=:v"), {"v": video_id}).scalar()
        if cur is None:
            raise InvalidTransition("video not found")
        if new != cur and new not in TRANSITIONS[cur]:
            raise InvalidTransition(f"{cur} -> {new} not allowed")
        sets = "".join(f", {k}=:{k}" for k in fields)
        c.execute(text(f"UPDATE videos SET upload_status=:s, updated_at=:now{sets} WHERE id=:v"),
                  {"s": new, "now": utcnow(), "v": video_id, **fields})
        c.execute(text("""INSERT INTO upload_history(video_id, event_type, event_status, message, youtube_video_id)
                          VALUES (:v, :e, :s, :m, :y)"""),
                  {"v": video_id, "e": event, "s": new, "m": (message or "")[:1000],
                   "y": fields.get("youtube_video_id")})


def update_fields(engine: Engine, video_id: int, **fields) -> None:
    sets = ", ".join(f"{k}=:{k}" for k in fields)
    with engine.begin() as c:
        c.execute(text(f"UPDATE videos SET {sets}, updated_at=:now WHERE id=:v"),
                  {**fields, "now": utcnow(), "v": video_id})


def log_event(engine: Engine, video_id: int, event: str, status: str, message: str = "",
              youtube_video_id: str | None = None) -> None:
    with engine.begin() as c:
        c.execute(text("""INSERT INTO upload_history(video_id, event_type, event_status, message, youtube_video_id)
                          VALUES (:v,:e,:s,:m,:y)"""),
                  {"v": video_id, "e": event, "s": status, "m": message[:1000], "y": youtube_video_id})


def acquire_lock(engine: Engine, video_id: int, worker: str, stale_minutes: int = 90,
                 now: datetime | None = None) -> bool:
    """Atomic: the lock is granted only if free, already ours, or stale."""
    now = now or utcnow()
    stale = now - timedelta(minutes=stale_minutes)
    with engine.begin() as c:
        n = c.execute(text("""UPDATE videos SET locked_by=:w, locked_at=:now
                              WHERE id=:v AND (locked_by IS NULL OR locked_by=:w OR locked_at IS NULL
                                               OR locked_at < :stale)"""),
                      {"w": worker, "now": now, "v": video_id, "stale": stale}).rowcount
    return n == 1


def heartbeat(engine: Engine, video_id: int, worker: str) -> None:
    with engine.begin() as c:
        c.execute(text("UPDATE videos SET locked_at=:now WHERE id=:v AND locked_by=:w"),
                  {"now": utcnow(), "v": video_id, "w": worker})


def release_lock(engine: Engine, video_id: int, worker: str) -> None:
    with engine.begin() as c:
        c.execute(text("UPDATE videos SET locked_by=NULL, locked_at=NULL WHERE id=:v AND locked_by=:w"),
                  {"v": video_id, "w": worker})
