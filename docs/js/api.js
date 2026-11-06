/* API client.
 * - Talks only to the backend URL the user configured (localStorage: dy.backendUrl).
 * - Auth: bearer session token obtained at login (auth.js, sessionStorage).
 * - No backend URL => DEMO MODE: sample data, nothing goes over the network.
 * - There is no secret/API key in this file, and there never should be.
 */
(function () {
  'use strict';
  const DY = (window.DY = window.DY || {});
  const KEY = 'dy.backendUrl';
  const TIMEOUT_MS = 20000;

  class ApiError extends Error {
    constructor(message, status, code) { super(message); this.status = status; this.code = code; }
  }

  /** https:// required; http only for localhost/127.0.0.1 (local testing). */
  function normalizeUrl(raw) {
    const s = String(raw || '').trim().replace(/\/+$/, '');
    if (!s) return '';
    let u;
    try { u = new URL(s); } catch (_) { throw new ApiError('Invalid URL. Example: https://dharm-yt-api.example.com', 0, 'bad_url'); }
    const local = ['localhost', '127.0.0.1', '[::1]'].includes(u.hostname);
    if (u.protocol !== 'https:' && !(u.protocol === 'http:' && local)) {
      throw new ApiError('For security only https:// URLs are allowed (http only on localhost).', 0, 'insecure_url');
    }
    if (u.username || u.password) throw new ApiError('Do not put a username/password in the URL.', 0, 'creds_in_url');
    if (u.search || u.hash) throw new ApiError('Do not put ? or # in the URL, only the base address.', 0, 'bad_url');
    return u.origin + u.pathname.replace(/\/+$/, '');
  }

  function getBackend() { try { return localStorage.getItem(KEY) || ''; } catch (_) { return ''; } }
  function setBackend(raw) {
    const url = normalizeUrl(raw);
    if (url) localStorage.setItem(KEY, url); else localStorage.removeItem(KEY);
    return url;
  }
  const isDemo = () => !getBackend();

  async function request(path, { method = 'GET', body, auth = true, signal } = {}) {
    if (isDemo()) return demoRoute(method, path, body);
    const base = getBackend();
    const headers = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const token = auth && DY.auth ? DY.auth.getToken() : null;
    if (auth && !token) throw new ApiError('Login required. Go to Settings and log in.', 401, 'no_session');
    if (token) headers.Authorization = `Bearer ${token}`;

    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    if (signal) signal.addEventListener('abort', () => ctrl.abort());
    let res;
    try {
      res = await fetch(base + path, {
        method, headers, body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: ctrl.signal, credentials: 'omit', cache: 'no-store', mode: 'cors', referrerPolicy: 'no-referrer'
      });
    } catch (e) {
      throw new ApiError(e.name === 'AbortError' ? 'The backend did not respond in time.' : 'Could not reach the backend. Check the URL or your internet connection.', 0, 'network');
    } finally { clearTimeout(t); }

    let data = null;
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) { try { data = await res.json(); } catch (_) { data = null; } }

    if (res.status === 401 && !auth) {
      throw new ApiError('Wrong username or password.', 401, 'bad_login');
    }
    if (res.status === 401) {
      if (DY.auth) DY.auth.clear();
      throw new ApiError('Session expired. Please log in again.', 401, 'unauthorized');
    }
    if (!res.ok) {
      const msg = (data && (data.message || data.detail)) || `Backend error (${res.status})`;
      throw new ApiError(typeof msg === 'string' ? msg : `Backend error (${res.status})`, res.status, data && data.code);
    }
    return data;
  }

  // ---------------- DEMO MODE ----------------
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const clone = (x) => JSON.parse(JSON.stringify(x));
  async function demoRoute(method, path, body) {
    await wait(250 + Math.random() * 250);
    const D = DY.demo;
    const [p, qs] = path.split('?');
    const q = new URLSearchParams(qs || '');
    const m = (re) => p.match(re);
    if (method === 'GET') {
      if (p === '/api/overview') return clone(D.overview);
      if (p === '/api/channels') {
        const s = (q.get('q') || '').toLowerCase();
        return { sample: true, items: clone(D.channels.filter((c) => !s || c.name.toLowerCase().includes(s) || c.drive_folder_name.toLowerCase().includes(s))) };
      }
      if (p === '/api/queue') return { sample: true, items: clone(D.queue) };
      if (p === '/api/drive') return clone(D.drive);
      if (p === '/api/schedules') return { sample: true, items: clone(D.schedules) };
      if (p === '/api/analytics') {
        const r = q.get('range') || '28d';
        const days = r === 'custom' ? Math.min(366, Math.max(1, Math.round((new Date(q.get('end')) - new Date(q.get('start'))) / 864e5) + 1)) : null;
        return D.analytics(r, days);
      }
      if (p === '/api/quota') return clone(D.quota);
      if (p === '/api/health') return clone(D.health);
      if (p === '/api/leaderboard') return { sample: true, items: clone(D.channels) };
      if (p === '/api/vpn') return clone(D.vpn);
      if (p === '/api/me') return { sample: true, username: 'demo' };
      if (p === '/api/status') return { ok: true, sample: true };
    }
    if (method === 'PATCH' && m(/^\/api\/channels\/([\w-]+)$/)) {
      const c = D.channels.find((x) => x.id === m(/^\/api\/channels\/([\w-]+)$/)[1]);
      if (c && body && typeof body.enabled === 'boolean') c.enabled = body.enabled;
      return { ok: true, sample: true, item: clone(c) };
    }
    if (method === 'POST' && m(/^\/api\/queue\/([\w-]+)\/(retry|cancel)$/)) {
      const [, id, act] = m(/^\/api\/queue\/([\w-]+)\/(retry|cancel)$/);
      const j = D.queue.find((x) => x.id === id);
      if (j) { j.status = act === 'retry' ? 'QUEUED' : 'CANCELLED'; j.error = null; j.progress = 0; }
      return { ok: true, sample: true };
    }
    if (method === 'DELETE' && m(/^\/api\/schedules\/([\w-]+)$/)) {
      const id = m(/^\/api\/schedules\/([\w-]+)$/)[1];
      D.schedules = D.schedules.filter((s) => s.id !== id);
      return { ok: true, sample: true };
    }
    if (method === 'POST' && p === '/api/drive/scan') return { ok: true, sample: true, new_files: 3 };
    if (method === 'POST' && p === '/api/ai/metadata') {
      const topic = (body && body.notes) || 'sample topic';
      return {
        sample: true,
        title: `[SAMPLE] ${topic.slice(0, 60)} | Complete guide`,
        description: `[SAMPLE — Demo mode, no Gemini call was made]\n\nThis video explains ${topic} in simple language.\n\n#sample #demo`,
        tags: ['sample', 'demo', 'english', ...topic.toLowerCase().split(/\s+/).filter(Boolean).slice(0, 4)]
      };
    }
    if (method === 'POST' && p === '/api/metadata') return { ok: true, sample: true };
    if (method === 'POST' && p === '/api/vpn/check') return { ok: true, sample: true };
    throw new ApiError(`This action is not available in demo mode: ${method} ${p}`, 404, 'demo_missing');
  }

  DY.api = {
    ApiError, normalizeUrl, getBackend, setBackend, isDemo, request,
    get: (p, o) => request(p, { ...o, method: 'GET' }),
    post: (p, b, o) => request(p, { ...o, method: 'POST', body: b === undefined ? {} : b }),
    patch: (p, b, o) => request(p, { ...o, method: 'PATCH', body: b }),
    del: (p, o) => request(p, { ...o, method: 'DELETE' })
  };
})();
