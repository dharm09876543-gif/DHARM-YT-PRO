"""Helpers used only by .github/workflows/upload.yml.

  python scripts/actions_helper.py matrix [--max 256] [--offset N] [--out matrix.json]
      Prints {"include": [...], "count": n, "total": m} for enabled + connected channels.
      Needs DATABASE_URL. No channel names, no secrets in the output.

  python scripts/actions_helper.py select-wg --profile ch01
      Reads SECRETS_JSON (= toJSON(secrets)), masks WG_CONF_CH01 with ::add-mask:: and appends it to
      $GITHUB_ENV for the next steps. Never prints the config. Exit 0 also when it is missing (the run
      itself then skips that channel's uploads and alerts).
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.vpn.actions import build_matrix, github_env_block, mask_commands, select_wg_secret  # noqa: E402

ap = argparse.ArgumentParser(prog="actions_helper.py")
sub = ap.add_subparsers(dest="cmd", required=True)
m = sub.add_parser("matrix")
m.add_argument("--max", type=int, default=256)
m.add_argument("--offset", type=int, default=0)
m.add_argument("--out", help="write the JSON here instead of stdout")
s = sub.add_parser("select-wg")
s.add_argument("--profile", required=True)
a = ap.parse_args()

if a.cmd == "matrix":
    from src.runtime import load_dotenv
    from src.database.connection import get_engine, run_migrations
    from src.services.channel_service import ChannelService
    load_dotenv()
    eng = get_engine(); run_migrations(eng)
    include, total = build_matrix(ChannelService(eng).list(enabled_only=True), a.max, a.offset)
    if total > len(include):
        print(f"::warning title=Matrix limit::{total} channels eligible but a matrix holds at most {len(include)} "
              "jobs; the rest rotate in on the next runs.")
    out = json.dumps({"include": include, "count": len(include), "total": total}, separators=(",", ":"))
    if a.out:
        Path(a.out).write_text(out, encoding="utf-8")
        print(f"Matrix: {len(include)} channel job(s) of {total} eligible.")
    else:
        print(out)
else:
    var, value = select_wg_secret(os.environ.get("SECRETS_JSON", ""), a.profile)
    if not value:
        print(f"::warning title=VPN secret missing::{var} is not set; uploads for this channel will be skipped.")
        sys.exit(0)
    for line in mask_commands(value):
        print(line)                       # consumed by the runner, shown in logs as ***
    env_file = os.environ.get("GITHUB_ENV")
    if not env_file:
        sys.exit("GITHUB_ENV is not set (this command is meant for GitHub Actions)")
    with open(env_file, "a", encoding="utf-8") as f:
        f.write(github_env_block(var, value))
    print(f"{var} loaded for this job (masked).")
