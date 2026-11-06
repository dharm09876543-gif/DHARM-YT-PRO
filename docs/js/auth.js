/* Login / session.
 * The password is never saved. Only the short-lived session token from the backend
 * is kept in sessionStorage (closing the tab = logout). */
(function () {
  'use strict';
  const DY = (window.DY = window.DY || {});
  const TOKEN = 'dy.session';
  const listeners = new Set();

  function read() {
    try { return JSON.parse(sessionStorage.getItem(TOKEN) || 'null'); } catch (_) { return null; }
  }
  function getToken() {
    const s = read();
    if (!s || !s.token) return null;
    if (s.expires_at && new Date(s.expires_at).getTime() <= Date.now()) { clear(); return null; }
    return s.token;
  }
  function getUser() { const s = read(); return s && getToken() ? s.username : null; }
  function clear() { try { sessionStorage.removeItem(TOKEN); } catch (_) { /* ignore */ } emit(); }
  function emit() { listeners.forEach((fn) => { try { fn(); } catch (_) { /* ignore */ } }); }
  function onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }

  /** POST /api/auth/login {username, password} -> {token, expires_at?, username?} */
  async function login(username, password) {
    if (DY.api.isDemo()) throw new DY.api.ApiError('Save a backend URL first. No login is needed in demo mode.', 0, 'demo');
    const data = await DY.api.request('/api/auth/login', { method: 'POST', body: { username, password }, auth: false });
    if (!data || typeof data.token !== 'string' || !data.token) throw new DY.api.ApiError('The backend did not return a token.', 0, 'no_token');
    sessionStorage.setItem(TOKEN, JSON.stringify({ token: data.token, expires_at: data.expires_at || null, username: data.username || username }));
    emit();
    return data;
  }
  async function logout() {
    try { if (!DY.api.isDemo() && getToken()) await DY.api.request('/api/auth/logout', { method: 'POST', body: {} }); }
    catch (_) { /* even if the server is down, clear the local session */ }
    clear();
  }

  DY.auth = { login, logout, getToken, getUser, clear, onChange, isLoggedIn: () => !!getToken() };
})();
