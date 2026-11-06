"""YouTube Analytics API v2 -> analytics_snapshots (per day).

Metrics: views, estimatedMinutesWatched, subscribersGained, subscribersLost.
estimated_revenue needs the monetary scope - NULL for now. Any missing metric is stored as NULL.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine

METRICS = ["views", "estimatedMinutesWatched", "subscribersGained", "subscribersLost"]
COLUMN = {"views": "views", "estimatedMinutesWatched": "watch_time_minutes",
          "subscribersGained": "subscribers_gained", "subscribersLost": "subscribers_lost"}


def fetch_daily(analytics, start: date, end: date) -> list[dict]:
    resp = analytics.reports().query(ids="channel==MINE", startDate=start.isoformat(),
                                     endDate=end.isoformat(), metrics=",".join(METRICS),
                                     dimensions="day", sort="day").execute()
    heads = [h.get("name") for h in resp.get("columnHeaders", [])]
    out = []
    for row in resp.get("rows") or []:
        rec = dict(zip(heads, row))
        item = {"report_date": rec.get("day")}
        for m, col in COLUMN.items():
            item[col] = rec.get(m)       # None if the metric was not returned
        out.append(item)
    return out


def sync_channel(engine: Engine, analytics, channel_id: str, start: date, end: date) -> int:
    rows = fetch_daily(analytics, start, end)
    with engine.begin() as c:
        for r in rows:
            if not r["report_date"]:
                continue
            c.execute(text("""
                INSERT INTO analytics_snapshots(channel_id, report_date, views, watch_time_minutes,
                    subscribers_gained, subscribers_lost, estimated_revenue)
                VALUES (:c, :d, :v, :w, :g, :l, NULL)
                ON CONFLICT(channel_id, report_date) DO UPDATE SET views=excluded.views,
                    watch_time_minutes=excluded.watch_time_minutes,
                    subscribers_gained=excluded.subscribers_gained,
                    subscribers_lost=excluded.subscribers_lost"""),
                {"c": channel_id, "d": date.fromisoformat(r["report_date"]), "v": r["views"],
                 "w": r["watch_time_minutes"], "g": r["subscribers_gained"], "l": r["subscribers_lost"]})
    return len(rows)
