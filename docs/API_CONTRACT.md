# Dashboard ↔ Backend API contract (Phase 10)

Dashboard (`docs/`, GitHub Pages) ek static PWA hai. Yeh sirf user ke configure kiye backend URL se baat karta hai
(Settings → Backend URL, browser `localStorage` key `dy.backendUrl`). Backend URL na ho to dashboard **Demo mode** mein
sample data (`js/demo-data.js`) dikhata hai aur koi network request nahi karta.

## Rules (backend ke liye)
- Sirf `https://` (local testing: `http://localhost` / `127.0.0.1`).
- CORS: `Access-Control-Allow-Origin: https://<user>.github.io` (wildcard mat lagao), allow headers `Authorization, Content-Type`,
  methods `GET, POST, PATCH, DELETE, OPTIONS`. Cookies use nahi hote (`credentials: 'omit'`).
- Auth: `POST /api/auth/login` → bearer session token (short-lived). Har protected request: `Authorization: Bearer <token>`.
  Token sirf `sessionStorage` (`dy.session`) mein rehta hai. Password kabhi browser mein save nahi hota.
- `401` → dashboard session hata ke login maangta hai. Error body: `{"detail": "Hinglish message"}` ya `{"message": "..."}`.
- **Null ka matlab "data nahi"** — dashboard null ko `—` dikhata hai. Jo value pata nahi, use `0` mat bhejo, `null` bhejo.
- Responses JSON; `Cache-Control: no-store` rakho. Service worker API responses kabhi cache nahi karta.

## Endpoints

| Method | Path | Body / Query | Response |
|---|---|---|---|
| GET | `/api/status` | — (no auth) | `{ok: true}` |
| POST | `/api/auth/login` | `{username, password}` (no auth) | `{token, expires_at?, username?}` |
| POST | `/api/auth/logout` | `{}` | `{ok}` |
| GET | `/api/overview` | — | `{channels:{total,active,disabled}, uploaded_total, queue, processing, failed, scheduled, views_28d, subscribers_total, quota:{used,limit}, last_run:{at,status:'success'\|'failed',workflow}, latest_errors:[{at,source,message}]}` |
| GET | `/api/channels` | `?q=` optional | `{items:[{id, youtube_channel_id, name, thumbnail_url (https or null), auth_status:'active'\|'expired'\|'not_connected'\|'revoked', enabled, drive_folder_name, drive_folder_id, uploaded, queued, failed, subscribers, views_28d, watch_hours_28d, ctr, last_upload_at, timezone}]}` |
| PATCH | `/api/channels/{id}` | `{enabled: bool}` | `{ok, item}` |
| GET | `/api/queue` | — | `{items:[{id, file_name, channel_id, channel_name, status, progress (0-100\|null), size_bytes, attempts, error, updated_at}]}` — `status` ∈ `DISCOVERED, QUEUED, DOWNLOADING, READY, UPLOADING, PROCESSING, VERIFYING, COMPLETED, FAILED, RETRY_WAIT, CANCELLED` (same as `videos.upload_status` CHECK) |
| POST | `/api/queue/{id}/retry` | `{}` | `{ok}` |
| POST | `/api/queue/{id}/cancel` | `{}` | `{ok}` (Drive file ko touch nahi karna) |
| GET | `/api/drive` | — | `{connected, account_label, folders:[{id,name,channel_name,pending_files,trashed_after_upload,last_scan_at,status:'ok'\|'no_access'}], storage:{used_bytes,limit_bytes}}` |
| POST | `/api/drive/scan` | `{}` | `{ok, new_files}` |
| POST | `/api/ai/metadata` | `{notes, file_name, language:'Hindi'\|'Hinglish'\|'English', channel_id, channel_name}` | `{title, description, tags:[]}` (src/ai/gemini.py; Gemini key sirf backend par) |
| POST | `/api/metadata` | `{channel_id, file_name, title, description, tags, category_id, privacy_status, publish_at (ISO UTC\|null), made_for_kids}` | `{ok}` — server par `VideoMetadata.clean()/errors()` dobara chalao |
| GET | `/api/schedules` | — | `{items:[{id,title,channel_name,scheduled_at,privacy,status:'pending'\|'published'\|'failed'\|'cancelled'}]}` |
| DELETE | `/api/schedules/{id}` | — | `{ok}` |
| GET | `/api/analytics` | `?range=today\|7d\|28d\|90d\|custom&start=YYYY-MM-DD&end=YYYY-MM-DD` | `{totals:{views,watch_minutes,subscribers_gained,revenue,avg_ctr}, series:[{date,views,watch_minutes,subscribers_gained}], top_videos:[{title,channel_name,views}]}` |
| GET | `/api/quota` | — | `{projects:[{name,used,limit,uploads_today}], cost:{upload,thumbnail,metadata_update,list}, resets_at, history:[{date,used}]}` |
| GET | `/api/health` | — | `{checks:[{name,status:'ok'\|'warn'\|'fail',detail}], audit:[{at,actor,action,target}]}` |
| GET | `/api/leaderboard` | — | `{items:[channel objects as /api/channels]}` (dashboard top 50 sort karta hai) |
| GET | `/api/vpn` | — | `{enabled, provider, status:'connected'\|'disconnected', server, public_ip, last_check_at, note}` |
| POST | `/api/vpn/check` | `{}` | `{ok}` |

Health/detail strings mein secrets, tokens, emails ya file paths mat bhejo — dashboard unhe seedha dikhata hai.
