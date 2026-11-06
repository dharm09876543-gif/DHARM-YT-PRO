"""Har DISCOVERED video ko channel ka agla khaali slot do -> publish_at (private + publishAt).

Slots: config/schedules.yaml scheduler.slots; overrides channel key (channels.yaml) ya channel_id se.
Slot channel ke timezone mein samjhe jaate hain (override.timezone > channel.timezone > scheduler.timezone).
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.upload.state import transition
from src.utils.timeutil import parse_dt, utcnow


def channel_override(channel_id: str, sched_cfg: dict, channels_cfg: dict | None = None) -> dict:
    overrides = (sched_cfg.get("scheduler", {}) or {}).get("overrides") or {}
    if channel_id in overrides:
        return overrides[channel_id] or {}
    for ch in (channels_cfg or {}).get("channels") or []:
        if ch.get("channel_id") == channel_id and ch.get("key") in overrides:
            return overrides[ch["key"]] or {}
    return {}


def channel_slots(channel: dict, sched_cfg: dict, channels_cfg: dict | None = None) -> tuple[list[str], str]:
    sch = sched_cfg.get("scheduler", {}) or {}
    ov = channel_override(channel["channel_id"], sched_cfg, channels_cfg)
    slots = sorted(ov.get("slots") or sch.get("slots") or [])
    tz = ov.get("timezone") or channel.get("timezone") or sch.get("timezone") or "Asia/Kolkata"
    return slots, tz


def taken_slots(engine: Engine, channel_id: str) -> set[datetime]:
    with engine.connect() as c:
        rows = c.execute(text("""SELECT scheduled_at FROM schedules WHERE channel_id=:c
                                 AND status IN ('pending','uploaded')"""), {"c": channel_id})
        return {parse_dt(r[0]) for r in rows}


def next_free_slot(slots: list[str], tz: str, taken: set[datetime], now: datetime | None = None,
                   lead_minutes: int = 60, days_ahead: int = 30) -> datetime | None:
    if not slots:
        return None
    zone = ZoneInfo(tz)
    now = now or utcnow()
    earliest = now + timedelta(minutes=lead_minutes)
    start_day = now.astimezone(zone).date()
    for d in range(days_ahead + 1):
        day = start_day + timedelta(days=d)
        for s in slots:
            hh, mm = map(int, s.split(":"))
            local = datetime.combine(day, time(hh, mm), tzinfo=zone)
            utc = local.astimezone(ZoneInfo("UTC"))
            if utc >= earliest and utc not in taken:
                return utc
    return None


def plan_channel(engine: Engine, channel: dict, sched_cfg: dict, channels_cfg: dict | None = None,
                 now: datetime | None = None) -> int:
    """DISCOVERED -> QUEUED (slot ke saath). Kitne plan hue, lautata hai."""
    sch = sched_cfg.get("scheduler", {}) or {}
    with engine.connect() as c:
        ids = [r[0] for r in c.execute(text("""SELECT id FROM videos WHERE channel_id=:c
                                               AND upload_status='DISCOVERED' ORDER BY id"""),
                                       {"c": channel["channel_id"]})]
    if not sch.get("enabled", True):
        for vid in ids:
            transition(engine, vid, "QUEUED", "scheduler band - turant upload", event="planned")
        return len(ids)
    slots, tz = channel_slots(channel, sched_cfg, channels_cfg)
    taken = taken_slots(engine, channel["channel_id"])
    n = 0
    for vid in ids:
        slot = next_free_slot(slots, tz, taken, now, int(sch.get("lead_minutes", 60)),
                              int(sch.get("days_ahead", 30)))
        if slot is None:
            break      # aage ke din bhare hain; video DISCOVERED rahega
        _assign(engine, vid, channel["channel_id"], slot, tz, new=True)
        taken.add(slot)
        n += 1
    return n


def _assign(engine: Engine, video_id: int, channel_id: str, slot: datetime, tz: str, new: bool) -> None:
    with engine.begin() as c:
        c.execute(text("DELETE FROM schedules WHERE video_id=:v"), {"v": video_id})
        c.execute(text("""INSERT INTO schedules(channel_id, video_id, scheduled_at, timezone, status)
                          VALUES (:c,:v,:s,:tz,'pending')"""),
                  {"c": channel_id, "v": video_id, "s": slot, "tz": tz})
    local = slot.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M")
    if new:
        transition(engine, video_id, "QUEUED", f"slot {local} {tz}", event="planned",
                   scheduled_publish_at=slot, privacy_status="private")
    else:
        from src.upload.state import log_event, update_fields
        update_fields(engine, video_id, scheduled_publish_at=slot, privacy_status="private")
        log_event(engine, video_id, "replanned", "ok", f"naya slot {local} {tz}")


def replan_if_stale(engine: Engine, video: dict, channel: dict, sched_cfg: dict,
                    channels_cfg: dict | None = None, now: datetime | None = None,
                    margin_minutes: int = 15) -> bool:
    """Upload se pehle: publish_at nikal gaya/bahut paas ho (quota delay) to agla slot."""
    pub = parse_dt(video.get("scheduled_publish_at"))
    now = now or utcnow()
    if pub is None or pub > now + timedelta(minutes=margin_minutes):
        return False
    sch = sched_cfg.get("scheduler", {}) or {}
    slots, tz = channel_slots(channel, sched_cfg, channels_cfg)
    taken = taken_slots(engine, channel["channel_id"]) - {pub}
    slot = next_free_slot(slots, tz, taken, now, int(sch.get("lead_minutes", 60)),
                          int(sch.get("days_ahead", 30)))
    if slot is None:
        return False
    _assign(engine, video["id"], channel["channel_id"], slot, tz, new=False)
    return True
