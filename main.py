"""DHARM YT PRO - entry point.

  python main.py doctor      setup check
  python main.py validate    config check
  python main.py init-db     database tables banayein
  python main.py keygen      encryption keys banayein
  python main.py channels    channel manager (list/add/enable/disable/health)
  python main.py ai FILE     Gemini se title, description, tags
  python main.py connect     YouTube channel OAuth se jodo (browser)
  python main.py run         discover -> plan -> upload -> verify -> cleanup
  python main.py cleanup     verified videos ki Drive files trash (--dry-run)
  python main.py audit       atke/fail jobs ki report (sirf DB)
  python main.py analytics   YouTube Analytics -> database
  python main.py health      DB + channels + jobs health check
"""
import runpy
import sys
from pathlib import Path

CMDS = {"doctor": "doctor.py", "validate": "validate_config.py",
        "init-db": "initialize_db.py", "keygen": "generate_key.py",
        "channels": "channels.py", "ai": "ai_metadata.py",
        "connect": "connect_channel.py", "run": "run_uploads.py", "cleanup": "verify_drive_cleanup.py",
        "audit": "audit_uploads.py", "analytics": "sync_analytics.py", "health": "health_check.py"}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in CMDS:
        print(__doc__)
        sys.exit(1)
    runpy.run_path(str(Path(__file__).parent / "scripts" / CMDS[cmd]), run_name="__main__")
