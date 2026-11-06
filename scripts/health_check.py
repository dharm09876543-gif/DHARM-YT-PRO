"""Health check (GitHub Actions + local): DB, migrations, channels auth, atke jobs, quota.

  python main.py health
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.runtime import bootstrap  # noqa: E402

eng, cipher, settings, _, _ = bootstrap(need_google=False)
from src.config import validate_all  # noqa: E402
from src.services.alerts import send_alert  # noqa: E402
from src.services.audit import audit  # noqa: E402
from src.services.channel_service import ChannelService  # noqa: E402

issues = [f"config: {e}" for e in validate_all()]
for h in ChannelService(eng, cipher).health():
    print(("OK  " if h["ok"] else "!!  ") + h["name"] + ("" if h["ok"] else "  -> " + ", ".join(h["issues"])))
    if not h["ok"] and "disabled" not in h["issues"]:
        issues.append(f"{h['name']}: {', '.join(h['issues'])}")
rep = audit(eng, settings)
print(rep["text"])
if rep["problems"]:
    issues.append(f"audit: {rep['problems']} problem(s)")
if issues:
    print("\nHealth: problem mile ->\n - " + "\n - ".join(issues))
    send_alert("Health check problem:\n" + "\n".join(issues[:10]))
    sys.exit(1)
print("\nHealth: sab theek")
