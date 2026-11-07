"""DHARM YT PRO - entry point.

  python main.py doctor      setup check
  python main.py validate    config check
  python main.py init-db     create database tables
  python main.py keygen      generate encryption keys
  python main.py channels    channel manager (list/add/enable/disable/vpn/health)
  python main.py ai FILE     title, description, tags with Gemini
  python main.py connect     connect a YouTube channel via OAuth (browser)
  python main.py connect-url finish a connect from the pasted localhost URL (GitHub Actions)
  python main.py run         discover -> plan -> upload -> verify -> cleanup (--channel UC.. for one)
  python main.py cleanup     trash Drive files of verified videos (--dry-run)
  python main.py audit       report of stuck/failed jobs (DB only)
  python main.py analytics   YouTube Analytics -> database
  python main.py health      DB + channels + jobs health check
  python main.py status-export  public dashboard snapshot (counts only, no secrets)
"""
import runpy
import sys
from pathlib import Path

CMDS = {"doctor": "doctor.py", "validate": "validate_config.py",
        "init-db": "initialize_db.py", "keygen": "generate_key.py",
        "channels": "channels.py", "ai": "ai_metadata.py",
        "connect": "connect_channel.py", "connect-url": "connect_from_url.py", "run": "run_uploads.py", "cleanup": "verify_drive_cleanup.py",
        "audit": "audit_uploads.py", "analytics": "sync_analytics.py", "health": "health_check.py", "status-export": "export_status.py"}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in CMDS:
        print(__doc__)
        sys.exit(1)
    runpy.run_path(str(Path(__file__).parent / "scripts" / CMDS[cmd]), run_name="__main__")
