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
| `pytest` | Saare tests |

## Roadmap
| Phase | Kaam | Status |
|---|---|---|
| 1 | Project scaffold, config, security base | ✅ Done (tested) |
| 2 | Database (8 tables, constraints, migrations) | 🟡 Schema + migrations ready & tested; Postgres CI pending first run |
| 3 | Google Drive integration | ⏳ |
| 4 | YouTube OAuth (per channel) | ⏳ |
| 5 | Upload engine (resumable, duplicate guard) | ⏳ |
| 6 | Metadata, thumbnails + **Gemini AI titles/descriptions/tags** | ⏳ |
| 7 | Multi-channel manager (100+) | ⏳ |
| 8 | Quota + scheduling | ⏳ |
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
