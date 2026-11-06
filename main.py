"""DHARM YT PRO - entry point.

  python main.py doctor      setup check
  python main.py validate    config check
  python main.py init-db     database tables banayein
  python main.py keygen      encryption keys banayein
"""
import runpy
import sys
from pathlib import Path

CMDS = {"doctor": "doctor.py", "validate": "validate_config.py",
        "init-db": "initialize_db.py", "keygen": "generate_key.py"}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in CMDS:
        print(__doc__)
        sys.exit(1)
    runpy.run_path(str(Path(__file__).parent / "scripts" / CMDS[cmd]), run_name="__main__")
