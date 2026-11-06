"""YouTube channel ko OAuth se jodo (local PC par chalayein, browser khulega).

  python main.py connect --folder DRIVE_FOLDER_ID          naya channel jodo
  python main.py connect --channel UCxxxx                  pehle se jude channel ko reconnect
  python main.py connect --no-browser                      link print karo, khud kholo

DATABASE_URL wahi rakhein jo GitHub Actions use karta hai, taaki tokens wahan save hon.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.runtime import bootstrap  # noqa: E402

args_in = sys.argv[2:] if len(sys.argv) > 1 and sys.argv[1] == "connect" else sys.argv[1:]
ap = argparse.ArgumentParser(prog="main.py connect", description="YouTube channel OAuth connect")
ap.add_argument("--channel", help="UC... (reconnect / sahi channel check)")
ap.add_argument("--folder", help="Drive folder ID (naye channel ke liye zaroori)")
ap.add_argument("--timezone", default="Asia/Kolkata")
ap.add_argument("--port", type=int, default=8080)
ap.add_argument("--no-browser", action="store_true")
a = ap.parse_args(args_in)

eng, cipher, settings, _, _ = bootstrap()
from googleapiclient.discovery import build  # noqa: E402

from src.auth.oauth import OAuthError, connect_channel, run_installed_flow  # noqa: E402
from src.services.channel_service import ChannelService  # noqa: E402
from src.services.quota import QuotaLedger  # noqa: E402

try:
    print("Browser mein Google account chunein aur saari permissions Allow karein...")
    creds = run_installed_flow(port=a.port, open_browser=not a.no_browser)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    r = connect_channel(ChannelService(eng, cipher), creds, yt, expected_channel_id=a.channel,
                        drive_folder_id=a.folder, timezone_name=a.timezone,
                        quota=QuotaLedger(eng, settings))
    print(f"Jud gaya: {r.channel_name} ({r.channel_id})" + (" - naya channel bana" if r.registered else ""))
    print("Tokens encrypted save ho gaye. Ab: python main.py run")
except OAuthError as e:
    print("Galti:", e); sys.exit(1)
