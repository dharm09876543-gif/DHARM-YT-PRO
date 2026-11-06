# Dashboard ↔ Backend API contract (Phase 10)

The dashboard (`docs/`, GitHub Pages) is a static PWA. It talks only to the backend URL the user configured
(Settings → Backend URL, browser `localStorage` key `dy.backendUrl`). Without a backend URL the dashboard runs in
**Demo mode**: it shows sample data (`js/demo-data.js`) and makes no network requests.

## Rules (for the backend)
- `https://` only (local testing: `http://localhost` / `127.0.0.1`).
- CORS: `Access-Control-Allow-Origin: https://<user>.github.io` (no wildcard), allow headers `Authorization, Content-Type`,
  methods `GET, POST, PATCH, DELETE, OPTIONS`. Cookies are not used (`credentials: 'omit'`).
- Auth: `POST /api/auth/login` → bearer session token (short-lived). Every protected request: `Authorization: Bearer <token>`.
  The token lives only in `sessionStorage` (`dy.session`). The password is never saved in the browser.
- `401` → the dashboard clears the session and asks for login. Error body: `{"detail": "English message"}` or `{"message": "..."}`.
- **Null means "no data"** — the dashboard shows null as `—`. If a value is unknown, send `null`, never `0`.
- Responses are JSON; send `Cache-Control: no-store`. The service worker never caches API responses.

## Endpoints

| Method | Path | Body / Query | Response |
|---|---|---|---|
| GET | `/api/status` | — (no auth) | `{ok: true}` |
| POST | `/api/auth/login` | `{username, password}` (no auth) | `{token, expires_at?, username?}` |
| POST | `/api/auth/logout` | `{}` | `{ok}` |
| GET | `/api/overview` | — | `{channels:{total,active,disabled}, uploaded_total, queue, processing, failed, scheduled, views_28d, subscribers_total, quota:{used,limit}, last_run:{at,status:'success'\|'failed',workflow}, latest_errors:[{at,source,message}]}` |
| GET | `/api/channels` | `?q=` optional | `{items:[{id, youtube_channel_id, name, thumbnail_url (https or null), auth_status:'active'\|'expired'\|'not_connected'\|'revoked', enabled, drive_folder_name, drive_folder_id, uploaded, queued, failed, subscribers, views_28d, watch_hours_28d, ctr, last_upload_at, timezone}]}` |
| PATCH | `/api/channels/{id}` | `{enabled: bool}` | `{ok, item}` |
| GET | `/api/queue` | — | `{items:[{id, file_name, channel_id, channel_name, status, progress (0-100\|null), size_bytes, attempts, error, updated_at}]}` — `status` ∈ `DISCOVERED, QUEUED, DOWNLOADING, READY, UPLOADING, PROCESSING, VERIFYING, COMPLETED, FAILED, RETRY_WAIT, CANCELLED` (same as the `videos.upload_status` CHECK) |
| POST | `/api/queue/{id}/retry` | `{}` | `{ok}` |
| POST | `/api/queue/{id}/cancel` | `{}` | `{ok}` (must not touch the Drive file) |
| GET | `/api/drive` | — | `{connected, account_label, folders:[{id,name,channel_name,pending_files,trashed_after_upload,last_scan_at,status:'ok'\|'no_access'}], storage:{used_bytes,limit_bytes}}` |
| POST | `/api/drive/scan` | `{}` | `{ok, new_files}` |
| POST | `/api/ai/metadata` | `{notes, file_name, language:'English'\|'Hindi'\|'Hinglish' (default 'English'), channel_id, channel_name}` | `{title, description, tags:[]}` (src/ai/gemini.py; the Gemini key stays on the backend) |
| POST | `/api/metadata` | `{channel_id, file_name, title, description, tags, category_id, privacy_status, publish_at (ISO UTC\|null), made_for_kids}` | `{ok}` — run `VideoMetadata.clean()/errors()` again on the server |
| GET | `/api/schedules` | — | `{items:[{id,title,channel_name,scheduled_at,privacy,status:'pending'\|'published'\|'failed'\|'cancelled'}]}` |
| DELETE | `/api/schedules/{id}` | — | `{ok}` |
| GET | `/api/analytics` | `?range=today\|7d\|28d\|90d\|custom&start=YYYY-MM-DD&end=YYYY-MM-DD` | `{totals:{views,watch_minutes,subscribers_gained,revenue,avg_ctr}, series:[{date,views,watch_minutes,subscribers_gained}], top_videos:[{title,channel_name,views}]}` |
| GET | `/api/quota` | — | `{projects:[{name,used,limit,uploads_today}], cost:{upload,thumbnail,metadata_update,list}, resets_at, history:[{date,used}]}` |
| GET | `/api/health` | — | `{checks:[{name,status:'ok'\|'warn'\|'fail',detail}], audit:[{at,actor,action,target}]}` |
| GET | `/api/leaderboard` | — | `{items:[channel objects as /api/channels]}` (the dashboard sorts the top 50) |
| GET | `/api/vpn` | — | `{enabled, provider, require_for_channels_with_profile, last_check_at, note, channels:[{channel_id, channel_name, vpn_profile (e.g. 'ch01'\|null), status:'verified'\|'failed'\|'not_required'\|'unknown', masked_ip (e.g. '185.x.x.12'\|null), last_check_at}]}` — **never** send the WireGuard config, private keys or a full IP |
| POST | `/api/vpn/check` | `{}` | `{ok}` |

Never put secrets, tokens, emails, file paths or full IP addresses in health/detail strings — the dashboard displays them as-is.
