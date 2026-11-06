"""YouTube Data API quota ledger.

- Records units per operation (quota_usage table, ON CONFLICT upsert).
- Checks daily_limit before an upload.
- Google quota resets at Pacific midnight, so quota_date = America/Los_Angeles date.
- On quotaExceeded, pause for the rest of the day (jobs stay QUEUED).
"""
from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.utils.timeutil import utcnow

PACIFIC = ZoneInfo("America/Los_Angeles")
DEFAULT_COSTS = {"videos.insert": 1600, "thumbnails.set": 50, "videos.list": 1,
                 "channels.list": 1, "playlistItems.list": 1, "videos.update": 50}
EXHAUSTED = "__quota_exceeded__"


class QuotaExceeded(RuntimeError):
    """Today's quota is used up - jobs stay queued and run after Pacific midnight."""


def pacific_date(now: datetime | None = None) -> date:
    return (now or utcnow()).astimezone(PACIFIC).date()


class QuotaLedger:
    def __init__(self, engine: Engine, settings: dict | None = None,
                 project_id: str | None = None, clock=utcnow):
        q = (settings or {}).get("quota", {})
        self.db = engine
        self.limit = int(q.get("daily_limit_units", 10000))
        self.warning = int(q.get("warning_threshold_units", int(self.limit * 0.8)))
        self.costs = dict(DEFAULT_COSTS)
        if "upload_cost_units" in q:
            self.costs["videos.insert"] = int(q["upload_cost_units"])
        self.costs.update({k: int(v) for k, v in (q.get("costs") or {}).items()})
        self.project = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "default")
        self.clock = clock

    def today(self) -> date:
        return pacific_date(self.clock())

    def cost(self, op: str) -> int:
        return self.costs.get(op, 1)

    def record(self, op: str, count: int = 1) -> None:
        units = self.cost(op) * count if op != EXHAUSTED else 0
        with self.db.begin() as c:
            c.execute(text("""
                INSERT INTO quota_usage(quota_date, api_project_id, operation, request_count, quota_units)
                VALUES (:d, :p, :op, :n, :u)
                ON CONFLICT(quota_date, api_project_id, operation) DO UPDATE SET
                  request_count = quota_usage.request_count + excluded.request_count,
                  quota_units = COALESCE(quota_usage.quota_units, 0) + excluded.quota_units"""),
                {"d": self.today(), "p": self.project, "op": op, "n": count, "u": units})

    def used(self) -> int:
        with self.db.connect() as c:
            return int(c.execute(text("""SELECT COALESCE(SUM(quota_units),0) FROM quota_usage
                                         WHERE quota_date=:d AND api_project_id=:p"""),
                                 {"d": self.today(), "p": self.project}).scalar() or 0)

    def remaining(self) -> int:
        return max(0, self.limit - self.used())

    def is_paused(self) -> bool:
        with self.db.connect() as c:
            return c.execute(text("""SELECT 1 FROM quota_usage WHERE quota_date=:d AND api_project_id=:p
                                     AND operation=:op"""),
                             {"d": self.today(), "p": self.project, "op": EXHAUSTED}).first() is not None

    def mark_exceeded(self) -> None:
        """Google returned quotaExceeded: pause uploads for today (Pacific)."""
        if not self.is_paused():
            self.record(EXHAUSTED)

    def upload_cost(self, with_thumbnail: bool = True) -> int:
        return (self.cost("videos.insert") + self.cost("videos.list")
                + (self.cost("thumbnails.set") if with_thumbnail else 0))

    def check_upload(self, with_thumbnail: bool = True) -> None:
        if self.is_paused():
            raise QuotaExceeded("Today's YouTube quota is used up (Google) - resumes after Pacific midnight")
        need = self.upload_cost(with_thumbnail)
        if self.remaining() < need:
            raise QuotaExceeded(f"Quota low: {self.remaining()} units left, upload needs {need}")

    def near_warning(self) -> bool:
        return self.used() >= self.warning
