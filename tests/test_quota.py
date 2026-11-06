from datetime import datetime, timezone

import pytest

from src.services.quota import QuotaExceeded, QuotaLedger, pacific_date


def test_pacific_midnight_reset():
    # 07:59 UTC = 23:59 PST (previous day); 08:00 UTC = new day (November, PST = UTC-8)
    assert str(pacific_date(datetime(2026, 11, 10, 7, 59, tzinfo=timezone.utc))) == "2026-11-09"
    assert str(pacific_date(datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc))) == "2026-11-10"
    # July: PDT = UTC-7
    assert str(pacific_date(datetime(2026, 7, 10, 7, 0, tzinfo=timezone.utc))) == "2026-07-10"


def test_record_units_and_configurable_costs(engine):
    q = QuotaLedger(engine, {"quota": {"daily_limit_units": 5000, "costs": {"thumbnails.set": 60}}})
    q.record("videos.insert"); q.record("thumbnails.set"); q.record("videos.list", 3)
    assert q.used() == 1600 + 60 + 3 and q.remaining() == 5000 - 1663
    q.record("videos.list")
    from sqlalchemy import text
    with engine.connect() as c:
        r = c.execute(text("SELECT request_count, quota_units FROM quota_usage WHERE operation='videos.list'")).first()
    assert tuple(r) == (4, 4)


def test_check_before_upload_and_pause(engine):
    q = QuotaLedger(engine, {"quota": {"daily_limit_units": 3400, "upload_cost_units": 1600}})
    q.check_upload()
    q.record("videos.insert"); q.record("thumbnails.set")
    q.check_upload(with_thumbnail=True)              # 1750 left >= 1651
    q.record("videos.list", 200)                     # 1550 left
    with pytest.raises(QuotaExceeded, match="Quota low"):
        q.check_upload(with_thumbnail=True)          # needs 1651
    q2 = QuotaLedger(engine, {"quota": {"daily_limit_units": 100000}})
    q2.mark_exceeded(); q2.mark_exceeded()
    assert q2.is_paused()
    with pytest.raises(QuotaExceeded, match="Pacific"):
        q2.check_upload()


def test_new_pacific_day_unpauses(engine):
    t = [datetime(2026, 11, 10, 7, 0, tzinfo=timezone.utc)]
    q = QuotaLedger(engine, {}, clock=lambda: t[0])
    q.record("videos.insert"); q.mark_exceeded()
    assert q.is_paused() and q.used() == 1600
    t[0] = datetime(2026, 11, 10, 8, 1, tzinfo=timezone.utc)
    assert not q.is_paused() and q.used() == 0
