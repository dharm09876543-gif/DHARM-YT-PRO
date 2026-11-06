# DHARM YT PRO

Multi-channel YouTube automation platform: Google Drive se videos uthao, apne authorized YouTube channels par upload karo, schedule karo, aur sab kuch mobile dashboard se manage karo. 100% GitHub Actions cloud par chalta hai, PC on rakhne ki zaroorat nahi.

**Repository:** `DHARM-YT-PRO` · **Database:** `dharm_yt` · **APIs:** YouTube Data API v3, YouTube Analytics API, Google Drive API, Gemini API

## Shuru kaise karein (5 minute)
```bash
git clone https://github.com/dharm09876543-gif/DHARM-YT-PRO.git
cd DHARM-YT-PRO
pip install -r requirements.txt
cp .env.example .env
python main.py keygen      # keys banao, .env mein daalo
python main.py init-db     # database tables
python main.py doctor      # sab check
```
Google Cloud setup step-by-step: **[SETUP_HINDI.md](SETUP_HINDI.md)**

## Commands
| Command | Kaam |
|---|---|
| `python main.py doctor` | Poora setup ek baar mein check |
| `python main.py validate` | Config files ki galtiyan dikhata hai |
| `python main.py init-db` | Database tables banata hai (dobara chalana safe) |
| `python main.py keygen` | Encryption keys banata hai |
| `python main.py channels list` | Saare channels, auth status, uploaded/queue/failed |
| `python main.py channels add UC... "Naam" FOLDER_ID` | Naya channel jodo |
| `python main.py channels enable/disable/rename/folder/health/remove` | Channel manage karo |
| `python main.py ai video.mp4 --notes "topic"` | Gemini se title, description, tags |
| `python main.py connect --folder DRIVE_FOLDER_ID` | Naya YouTube channel OAuth se jodo (browser khulega, local PC par) |
| `python main.py connect --channel UC...` | Jude channel ko reconnect (revoke/expire ke baad) |
| `python main.py run` | Saare channels: Drive discover -> schedule -> upload -> verify -> Drive trash |
| `python main.py run --steps discover,plan` | Sirf naye videos dhoondho aur slot do (upload nahi) |
| `python main.py cleanup [--dry-run]` | Verified videos ki Drive files Trash mein (YouTube se dobara verify karke) |
| `python main.py audit` | Atke lock, FAILED, verify baaki, trash baaki, aaj ka quota (sirf DB) |
| `python main.py analytics --days 7` | YouTube Analytics (views, watch time, subs) database mein |
| `python main.py health` | DB + channels auth + jobs ki health (problem par exit 1 + Telegram) |
| `pytest` | Saare tests |

## Drive folder ka structure (har channel)
```
DRIVE_FOLDER_ID/
  video1.mp4               (ya videos/ subfolder ke andar)
  video1.json / video1.txt (optional: title, description, tags)
  thumbnails/video1.jpg    (optional: same naam, JPG/PNG, max 2MB)
```
`.json`: `{"title": "...", "description": "...", "tags": ["a","b"], "category_id": "22"}` ·
`.txt`: pehli line title, `tags: a, b` line, baaki description. Sidecar na ho to Gemini (agar `GEMINI_API_KEY`), warna filename hi title.

## GitHub Actions (cloud par automatic)
| Workflow | Kab | Kaam |
|---|---|---|
| `upload.yml` | har 3 ghante + manual | `python main.py run` |
| `drive_cleanup.yml` | har 6 ghante + manual | `python main.py cleanup` (upload ke saath ek hi concurrency group) |
| `analytics.yml` | roz 03:30 UTC | `python main.py analytics --days 7` |
| `health_check.yml` | har 6 ghante | `python main.py health` |

Secrets: `DATABASE_URL` (PostgreSQL), `TOKEN_ENCRYPTION_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, optional `GOOGLE_CLOUD_PROJECT`, `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. `DATABASE_URL` ya `TOKEN_ENCRYPTION_KEY` na ho to workflow saaf message ke saath ruk jaata hai.
Channel connect hamesha local PC par (`python main.py connect`) usi `DATABASE_URL` + `TOKEN_ENCRYPTION_KEY` ke saath karein jo GitHub Secrets mein hain.

## Roadmap
| Phase | Kaam | Status |
|---|---|---|
| 1 | Project scaffold, config, security base | ✅ Done (tested) |
| 2 | Database (8 tables, constraints, migrations) | 🟡 Schema + migrations ready & tested; Postgres CI pending first run |
| 3 | Google Drive integration | 🟡 Code + mock tests done; real Drive unverified |
| 4 | YouTube OAuth (per channel) | 🟡 Code + mock tests done; real consent unverified |
| 5 | Upload engine (resumable, duplicate guard) | 🟡 Code + tests (fake server + real googleapiclient over mocked HTTP); real upload unverified |
| 6 | Metadata, thumbnails + **Gemini AI titles/descriptions/tags** | 🟡 Sab code + mock tests; real Gemini/thumbnail unverified |
| 7 | Multi-channel manager (100+) | 🟡 Channel service + CLI + connect flow (tested with mocks) |
| 8 | Quota + scheduling | 🟡 Ledger + planner + executor done (tested); real quota numbers Console se verify karein |
| 9 | Surfshark WireGuard (optional) | ⏳ |
| 10 | FastAPI backend + mobile PWA dashboard | ⏳ |
| 11 | Production testing & rollout | ⏳ |

Details: [STATUS.md](STATUS.md)

## Zaroori baatein
- **Quota:** ek Google Cloud project ka default quota 10,000 units/din hai; ek upload lagbhag 1,600 units = ~6 uploads/din. 100+ channels ke liye Google se quota increase (YouTube API audit) zaroori hai. VPN se quota nahi badhta.
- Unverified Google project se upload hue videos private lock rehte hain jab tak audit pass na ho.
- Har channel ka malik khud OAuth se permission deta hai; service account kaam nahi karta.
- Drive se video sirf verified upload ke baad **Trash** mein jaata hai, kabhi permanent delete nahi.
- Secrets (`.env`, tokens, `client_secret.json`, WireGuard config) kabhi commit na karein; `.gitignore` inhe rokta hai aur CI secret-scan karta hai.
- RAJ FB PRO project is repo se bilkul alag hai; uski koi file, secret ya database yahan use nahi hota.

License: MIT
