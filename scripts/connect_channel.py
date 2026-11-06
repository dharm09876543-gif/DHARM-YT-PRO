"""Connect a YouTube channel via OAuth (run on a local PC, a browser opens).

  python main.py connect --folder DRIVE_FOLDER_ID          add a new channel
  python main.py connect --channel UCxxxx                  reconnect an existing channel
  python main.py connect --no-browser                      print the link, open it yourself

Use the same DATABASE_URL as GitHub Actions, so the tokens are saved there.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.runtime import bootstrap  # noqa: E402

args_in = sys.argv[2:] if len(sys.argv) > 1 and sys.argv[1] == "connect" else sys.argv[1:]
ap = argparse.ArgumentParser(prog="main.py connect", description="YouTube channel OAuth connect")
ap.add_argument("--channel", help="UC... (reconnect / check it is the right channel)")
ap.add_argument("--folder", help="Drive folder ID (required for a new channel)")
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
    print("Choose the Google account in the browser and Allow all permissions...")
    creds = run_installed_flow(port=a.port, open_browser=not a.no_browser)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    r = connect_channel(ChannelService(eng, cipher), creds, yt, expected_channel_id=a.channel,
                        drive_folder_id=a.folder, timezone_name=a.timezone,
                        quota=QuotaLedger(eng, settings))
    print(f"Connected: {r.channel_name} ({r.channel_id})" + (" - new channel created" if r.registered else ""))
    print("Tokens saved encrypted. Next: python main.py run")
except OAuthError as e:
    print("Error:", e); sys.exit(1)
