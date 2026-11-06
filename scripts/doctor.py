"""Full setup check in one command: python scripts/doctor.py"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ok = True
def check(name, passed, hint=""):
    global ok
    print(f"[{'OK' if passed else 'XX'}] {name}" + ("" if passed else f"  -> {hint}"))
    ok &= passed

check("Python 3.10+", sys.version_info >= (3, 10), "Update Python")
try:
    import yaml, sqlalchemy, cryptography  # noqa: F401,E401
    check("Libraries installed", True)
except ImportError as e:
    check("Libraries installed", False, f"pip install -r requirements.txt ({e.name})")

if (ROOT / ".env").exists():
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
check(".env file", (ROOT / ".env").exists(), "cp .env.example .env")
check("TOKEN_ENCRYPTION_KEY", bool(os.getenv("TOKEN_ENCRYPTION_KEY")), "python scripts/generate_key.py")
check("GOOGLE_CLIENT_ID", bool(os.getenv("GOOGLE_CLIENT_ID")), "docs: SETUP.md step 2")

from src.config import validate_all  # noqa: E402
errs = validate_all()
check("Config files", not errs, "; ".join(errs[:3]))
try:
    from src.database.connection import get_engine
    from sqlalchemy import text
    with get_engine().connect() as c:
        c.execute(text("SELECT 1"))
    check("Database connection", True)
except Exception as e:  # noqa: BLE001
    check("Database connection", False, str(e)[:120])

print("\nAll good!" if ok else "\nFix the items marked 'XX' above.")
sys.exit(0 if ok else 1)
