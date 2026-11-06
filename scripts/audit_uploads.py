"""Upload audit (DB only, no API calls): stuck jobs, failures, verify pending, trash pending, quota.

  python main.py audit
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.runtime import bootstrap  # noqa: E402

eng, cipher, settings, _, _ = bootstrap(need_google=False)
from src.services.audit import audit  # noqa: E402

rep = audit(eng, settings)
print(rep["text"])
sys.exit(1 if rep["problems"] else 0)
