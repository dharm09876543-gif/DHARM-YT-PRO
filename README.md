# DHARM YT PRO

Multi-channel YouTube automation platform: pick up videos from Google Drive, upload them to your own authorized YouTube channels, schedule them, and manage everything from a mobile dashboard. Runs 100% on GitHub Actions in the cloud — no need to keep a PC switched on.

**Repository:** `DHARM-YT-PRO` · **Database:** `dharm_yt` · **APIs:** YouTube Data API v3, YouTube Analytics API, Google Drive API, Gemini API

## Getting started (5 minutes)
```bash
git clone https://github.com/dharm09876543-gif/DHARM-YT-PRO.git
cd DHARM-YT-PRO
pip install -r requirements.txt
cp .env.example .env
python main.py keygen      # generate keys, put them in .env
python main.py init-db     # database tables
python main.py doctor      # check everything
```
Step-by-step Google Cloud setup: **[SETUP.md](SETUP.md)**

## Commands
| Command | What it does |
|---|---|
| `python main.py doctor` | Checks the whole setup in one go |
| `python main.py validate` | Shows mistakes in the config files |
| `python main.py init-db` | Creates the database tables (safe to run again) |
| `python main.py keygen` | Generates encryption keys |
| `python main.py channels list` | All channels, auth status, VPN profile, uploaded/queued/failed |
| `python main.py channels add UC... "Name" FOLDER_ID` | Add a new channel |
| `python main.py channels enable/disable/rename/folder/health/remove` | Manage a channel |
| `python main.py channels vpn --channel UC... --profile ch01` | Upload this channel through WireGuard profile `ch01` (`--clear` removes it) |
| `python main.py ai video.mp4 --notes "topic"` | Title, description, tags with Gemini (English by default; `--language Hindi` or `Hinglish`) |
| `python main.py connect --folder DRIVE_FOLDER_ID` | Connect a new YouTube channel via OAuth (opens a browser, run on your local PC) |
| `python main.py connect --channel UC...` | Reconnect an existing channel (after revoke/expiry) |
| `python main.py run` | All channels: Drive discover -> schedule -> upload -> verify -> Drive trash |
| `python main.py run --channel UC...` | Run one channel on its own (used by the GitHub Actions matrix) |
| `python main.py run --steps discover,plan` | Only find new videos and assign slots (no upload) |
| `python main.py cleanup [--dry-run]` | Move Drive files of verified videos to Trash (re-verified on YouTube first) |
| `python main.py audit` | Stuck locks, FAILED, verify pending, trash pending, today's quota (DB only) |
| `python main.py analytics --days 7` | YouTube Analytics (views, watch time, subs) into the database |
| `python main.py health` | DB + channel auth + job health (exit 1 + Telegram on problems) |
| `pytest` | All tests |

## Drive folder structure (per channel)
```
DRIVE_FOLDER_ID/
  video1.mp4               (or inside a videos/ subfolder)
  video1.json / video1.txt (optional: title, description, tags)
  thumbnails/video1.jpg    (optional: same name, JPG/PNG, max 50MB; Shorts 9:16 e.g. 1080x1920, set after processing)
```
`.json`: `{"title": "...", "description": "...", "tags": ["a","b"], "category_id": "22"}` ·
`.txt`: first line is the title, a `tags: a, b` line, the rest is the description. Without a sidecar, Gemini writes the metadata (if `GEMINI_API_KEY` is set) — in **English** by default, or Hindi/Hinglish via `defaults.language` in `config/channels.yaml`; otherwise the filename becomes the title.

## GitHub Actions (automatic in the cloud)
| Workflow | When | What |
|---|---|---|
| `upload.yml` | every 3 hours + manual | planner job → one matrix job per channel: `python main.py run --channel UC...` |
| `drive_cleanup.yml` | every 6 hours + manual | `python main.py cleanup` (same concurrency group as uploads) |
| `analytics.yml` | daily 03:30 UTC | `python main.py analytics --days 7` |
| `health_check.yml` | every 6 hours | `python main.py health` |

Secrets: `DATABASE_URL` (PostgreSQL), `TOKEN_ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, optional `GOOGLE_CLOUD_PROJECT`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and optional `WG_CONF_<PROFILE>` per VPN profile. If `DATABASE_URL` or `TOKEN_ENCRYPTION_KEY` is missing, the workflow stops with a clear message.
Always connect channels on your local PC (`python main.py connect`) with the same `DATABASE_URL` + `TOKEN_ENCRYPTION_KEY` that are in GitHub Secrets.

**Upload matrix:** the `plan` job lists enabled + connected channels (IDs and VPN profile names only) and the `upload` job runs one job per channel with `fail-fast: false`, so one broken channel never stops the others. `max-parallel` comes from the manual-run input `max_parallel`, else the repository variable `UPLOAD_MAX_PARALLEL`, else 4. A per-channel `concurrency` group guarantees a channel never runs twice at the same time. GitHub allows at most **256 jobs per matrix**; with more channels the planner takes a rotating window of 256 (based on the run number), so every channel gets its turn across runs.

## VPN (Phase 9, optional): a separate outgoing IP per channel
- Each channel can have a **VPN profile name** (e.g. `ch01`): `python main.py channels vpn --channel UC... --profile ch01`. Only the name is stored (`channels.vpn_profile`, migration 005).
- The WireGuard config for a profile comes **only** from the secret / env var `WG_CONF_<PROFILE>` (e.g. `WG_CONF_CH01`) containing the full `.conf` text. It is never written to the repo or the database. At runtime it is written to a `0600` temp file (in a `0700` temp dir) and deleted after the tunnel goes down.
- Before uploading, `src/vpn/wireguard.py` reads the public IP, brings the tunnel up with `wg-quick`, reads the public IP again (`vpn.ip_check_url`, default `https://api.ipify.org`) and **requires that it changed**. If the tunnel fails or the IP is unchanged, that channel's uploads are skipped for this run (jobs stay `QUEUED`), a Telegram alert is sent, and nothing is uploaded from the wrong IP. Only the tunnelled upload phase uses the VPN; discovery, planning and cleanup use the normal runner IP.
- Logs show only the masked IP (e.g. `185.x.x.12`) — never the config, keys or full IP.
- In GitHub Actions each channel runs in its own matrix job (its own runner), installs `wireguard-tools`, and picks its own `WG_CONF_<PROFILE>` out of `toJSON(secrets)` in a single helper step that masks it with `::add-mask::` and never echoes it. Locally, `python main.py run` handles VPN channels one at a time, because a tunnel changes routing for the whole machine.
- Settings (`config/settings.yaml`): `vpn.enabled`, `vpn.require_for_channels_with_profile` (default `true`), `vpn.ip_check_url`.

**Things to know before using a VPN:**
- **Shared vs fixed IPs:** normal Surfshark servers give **shared** IPs that many users use and that can change between connections. A **fixed, unique IP per channel** needs the Surfshark **Dedicated IP** add-on — one add-on per IP, so one per channel that needs its own fixed IP.
- **Quota:** a VPN does **not** change YouTube API quota. Quota is per **Google Cloud project**, no matter which IP the requests come from.
- **Google security checks:** many logins/uploads from VPN or datacenter IPs (GitHub Actions runners are datacenter IPs too) can trigger Google security checks, CAPTCHAs or account verification. Prefer stable IPs, avoid switching a channel between many locations, and keep OAuth consent on your local PC.

## Roadmap
| Phase | Work | Status |
|---|---|---|
| 1 | Project scaffold, config, security base | ✅ Done (tested) |
| 2 | Database (8 tables, constraints, migrations) | 🟡 Schema + migrations ready & tested; tests pass on Postgres in CI |
| 3 | Google Drive integration | 🟡 Code + mock tests done; real Drive unverified |
| 4 | YouTube OAuth (per channel) | 🟡 Code + mock tests done; real consent unverified |
| 5 | Upload engine (resumable, duplicate guard) | 🟡 Code + tests (fake server + real googleapiclient over mocked HTTP); real upload unverified |
| 6 | Metadata, thumbnails + **Gemini AI titles/descriptions/tags** | 🟡 All code + mock tests; real Gemini call verified; real thumbnail unverified |
| 7 | Multi-channel manager (100+) | 🟡 Channel service + CLI + connect flow (tested with mocks) |
| 8 | Quota + scheduling | 🟡 Ledger + planner + executor done (tested); verify real quota numbers in the Console |
| 9 | Surfshark WireGuard (optional), per-channel IP + matrix workflow | 🟡 Code + mocked tests; real WireGuard on Actions not run yet |
| 10 | FastAPI backend + mobile PWA dashboard | 🟡 PWA dashboard in `docs/` (demo mode); backend ⏳ |
| 11 | Production testing & rollout | ⏳ |

Details: [STATUS.md](STATUS.md)

## Important notes
- **Quota:** a Google Cloud project's default quota is 10,000 units/day; one upload is about 1,600 units = ~6 uploads/day. 100+ channels need a quota increase from Google (YouTube API audit). A VPN does not increase quota.
- Videos uploaded from an unverified Google project stay locked as private until the audit passes.
- Every channel owner grants permission themselves via OAuth; a service account does not work.
- A Drive video goes to **Trash** only after a verified upload — never a permanent delete.
- Never commit secrets (`.env`, tokens, `client_secret.json`, WireGuard configs); `.gitignore` blocks them and CI runs a secret scan.
- The RAJ FB PRO project is completely separate from this repo; none of its files, secrets or databases are used here.

License: MIT
