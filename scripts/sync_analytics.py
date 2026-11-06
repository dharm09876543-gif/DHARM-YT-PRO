"""YouTube Analytics -> analytics_snapshots.

  python main.py analytics            last 7 days
  python main.py analytics --days 28
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.runtime import bootstrap, make_ctx_factory  # noqa: E402

args_in = sys.argv[2:] if len(sys.argv) > 1 and sys.argv[1] == "analytics" else sys.argv[1:]
ap = argparse.ArgumentParser(prog="main.py analytics")
ap.add_argument("--days", type=int, default=7)
a = ap.parse_args(args_in)

eng, cipher, settings, _, _ = bootstrap()
from src.analytics.sync import sync_channel  # noqa: E402
from src.services.channel_service import ChannelService  # noqa: E402

end = date.today() - timedelta(days=1)          # Analytics data arrives 1-2 days late
start = end - timedelta(days=a.days - 1)
factory, bad = make_ctx_factory(eng, cipher, settings), False
for ch in ChannelService(eng, cipher).list(enabled_only=True):
    if ch["auth_status"] != "active":
        print(f"Skip {ch['channel_name']}: auth={ch['auth_status']}"); continue
    try:
        n = sync_channel(eng, factory(ch).analytics, ch["channel_id"], start, end)
        print(f"{ch['channel_name']}: {n} days of data ({start} - {end})")
    except Exception as e:  # noqa: BLE001 - one channel failing must not stop the rest
        bad = True; print(f"!! {ch['channel_name']}: {type(e).__name__}: {e}")
sys.exit(1 if bad else 0)
