"""Saare enabled channels: discover -> plan -> upload -> verify -> cleanup.

  python main.py run                    sab steps
  python main.py run --steps discover,plan   sirf kuch steps
  python main.py run --channel UCxxxx   ek channel
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.runtime import bootstrap, channel_defaults, make_ctx_factory  # noqa: E402

args_in = sys.argv[2:] if len(sys.argv) > 1 and sys.argv[1] == "run" else sys.argv[1:]
ap = argparse.ArgumentParser(prog="main.py run")
ap.add_argument("--steps", default="discover,plan,upload,cleanup")
ap.add_argument("--channel")
a = ap.parse_args(args_in)

eng, cipher, settings, sched, chcfg = bootstrap()
from src.scheduler.executor import run_all, summary  # noqa: E402
from src.services.alerts import send_alert  # noqa: E402
from src.services.channel_service import ChannelService  # noqa: E402
from src.services.quota import QuotaLedger  # noqa: E402

chans = [c for c in ChannelService(eng, cipher).list(enabled_only=True)
         if (not a.channel or c["channel_id"] == a.channel)]
ready = [c for c in chans if c["auth_status"] == "active"]
for c in chans:
    if c["auth_status"] != "active":
        print(f"Skip {c['channel_name']}: auth={c['auth_status']} -> python main.py connect --channel {c['channel_id']}")
results = run_all(eng, ready, make_ctx_factory(eng, cipher, settings), settings, sched, chcfg,
                  steps=tuple(a.steps.split(",")), defaults_for=channel_defaults(chcfg))
text_out = summary(results)
q = QuotaLedger(eng, settings)
text_out += f"\nQuota aaj (Pacific): {q.used()}/{q.limit} units" + ("  [PAUSED]" if q.is_paused() else "")
print(text_out)
if any(r.completed or r.errors or r.stopped for r in results):
    send_alert(text_out)
sys.exit(0 if all(r.ok for r in results) else 1)
