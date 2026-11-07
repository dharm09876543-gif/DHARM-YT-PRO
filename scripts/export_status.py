"""Write the public dashboard snapshot: python main.py status-export [--out FILE] [--run-status success|failed]"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.runtime import bootstrap  # noqa: E402
from src.services.status_export import assert_public_safe, build_status  # noqa: E402

args = sys.argv[2:] if len(sys.argv) > 1 and sys.argv[1] == "status-export" else sys.argv[1:]
out = Path(args[args.index("--out") + 1]) if "--out" in args else Path("status.json")
run_status = args[args.index("--run-status") + 1] if "--run-status" in args else "success"
eng, _, settings, _, _ = bootstrap(need_google=False)
from datetime import datetime, timezone  # noqa: E402
last = {"at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "status": run_status,
        "workflow": os.getenv("GITHUB_WORKFLOW", "upload.yml")}
blob = json.dumps(build_status(eng, settings, last), indent=1, default=str)
assert_public_safe(blob)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(blob)
print(f"Status snapshot written: {out} ({len(blob)} bytes)")
