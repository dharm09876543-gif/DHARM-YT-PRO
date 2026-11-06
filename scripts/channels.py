"""Channel manager CLI.

  python main.py channels list
  python main.py channels add UCxxxxxxxx "Channel Name" DRIVE_FOLDER_ID
  python main.py channels enable|disable UCxxxx
  python main.py channels folder UCxxxx NEW_FOLDER_ID
  python main.py channels rename UCxxxx "New Name"
  python main.py channels vpn --channel UCxxxx --profile ch01   upload through WireGuard profile ch01
  python main.py channels vpn --channel UCxxxx --clear          no VPN for this channel
  python main.py channels health
  python main.py channels remove UCxxxx --yes

A VPN profile is only a NAME. Its WireGuard config must be in the WG_CONF_<PROFILE> secret
(e.g. WG_CONF_CH01), never in the repo or the database.
"""
import argparse
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
            print("No channels. To add one: channels add UC... \"Name\" FOLDER_ID")
        for r in rows:
            flag = "ON " if r["enabled"] else "OFF"
            print(f"[{flag}] {r['channel_name']:<28} {r['channel_id']}  auth={r['auth_status']}  "
                  f"vpn={r.get('vpn_profile') or '-'}  "
                  f"uploaded={r['uploaded']} queue={r['queued']} failed={r['failed']}")
    elif cmd == "add":
        svc.add(args[1], args[2], args[3]); print("Channel added. Now connect it via OAuth.")
    elif cmd in ("enable", "disable"):
        getattr(svc, cmd)(args[1]); print(f"{cmd} done")
    elif cmd == "folder":
        svc.set_folder(args[1], args[2]); print("Folder updated")
    elif cmd == "rename":
        svc.rename(args[1], args[2]); print("Name updated")
    elif cmd == "vpn":
        ap = argparse.ArgumentParser(prog="main.py channels vpn")
        ap.add_argument("--channel", required=True, help="UC... channel id")
        g = ap.add_mutually_exclusive_group(required=True)
        g.add_argument("--profile", help="WireGuard profile name, e.g. ch01 (config in secret WG_CONF_CH01)")
        g.add_argument("--clear", action="store_true", help="remove the VPN profile from this channel")
        va = ap.parse_args(args[1:])
        svc.set_vpn_profile(va.channel, None if va.clear else va.profile)
        if va.clear:
            print(f"VPN profile cleared for {va.channel}: uploads use the runner IP")
        else:
            from src.vpn.wireguard import env_var_for
            print(f"VPN profile for {va.channel} set to {va.profile.strip().lower()}. "
                  f"Add its WireGuard config as the GitHub secret {env_var_for(va.profile)} "
                  "and set vpn.enabled: true in config/settings.yaml.")
    elif cmd == "health":
        for h in svc.health():
            print(("OK  " if h["ok"] else "!!  ") + h["name"] + ("" if h["ok"] else "  -> " + ", ".join(h["issues"])))
    elif cmd == "remove":
        svc.remove(args[1], confirm="--yes" in args); print("Authorization removed, channel disabled")
    else:
        print(__doc__)
except (ChannelError, IndexError) as e:
    print("Error:", e or "not enough arguments"); print(__doc__); sys.exit(1)
