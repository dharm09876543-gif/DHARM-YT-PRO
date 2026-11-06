"""Time helpers: hamesha timezone-aware UTC; SQLite strings ko wapas datetime banana."""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_dt(v) -> datetime | None:
    """DB se aaya value (datetime ya SQLite string) -> aware UTC datetime."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        dt = v
    else:
        s = str(v).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
