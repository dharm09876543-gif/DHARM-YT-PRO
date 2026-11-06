"""Channel manager CLI.

  python main.py channels list
  python main.py channels add UCxxxxxxxx "Channel Naam" DRIVE_FOLDER_ID
  python main.py channels enable|disable UCxxxx
  python main.py channels folder UCxxxx NEW_FOLDER_ID
  python main.py channels rename UCxxxx "Naya Naam"
  python main.py channels health
  python main.py channels remove UCxxxx --yes
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.database.connection import get_engine, run_migrations  # noqa: E402
from src.services.channel_service import ChannelError, ChannelService  # noqa: E402

args = sys.argv[2:] if len(sys.argv) > 1 and sys.argv[1] == "channels" else sys.argv[1:]
eng = get_engine(); run_migrations(eng)
svc = ChannelService(eng)
try:
    cmd = args[0] if args else "list"
    if cmd == "list":
        rows = svc.list()
        if not rows:
            print("Koi channel nahi. Jodne ke liye: channels add UC... \"Naam\" FOLDER_ID")
        for r in rows:
            flag = "ON " if r["enabled"] else "OFF"
            print(f"[{flag}] {r['channel_name']:<28} {r['channel_id']}  auth={r['auth_status']}  "
                  f"uploaded={r['uploaded']} queue={r['queued']} failed={r['failed']}")
    elif cmd == "add":
        svc.add(args[1], args[2], args[3]); print("Channel jud gaya. Ab OAuth se connect karein.")
    elif cmd in ("enable", "disable"):
        getattr(svc, cmd)(args[1]); print(f"{cmd} ho gaya")
    elif cmd == "folder":
        svc.set_folder(args[1], args[2]); print("Folder badal gaya")
    elif cmd == "rename":
        svc.rename(args[1], args[2]); print("Naam badal gaya")
    elif cmd == "health":
        for h in svc.health():
            print(("OK  " if h["ok"] else "!!  ") + h["name"] + ("" if h["ok"] else "  -> " + ", ".join(h["issues"])))
    elif cmd == "remove":
        svc.remove(args[1], confirm="--yes" in args); print("Authorization hata di, channel disable")
    else:
        print(__doc__)
except (ChannelError, IndexError) as e:
    print("Galti:", e or "argument kam hain"); print(__doc__); sys.exit(1)
