/* App shell: hash router, navigation, demo banner, service worker. */
(function () {
  'use strict';
  const { h, icon } = DY.ui;

  const ROUTES = [
    ['overview', 'Overview', 'overview'],
    ['channels', 'Channels', 'channels'],
    ['queue', 'Upload Queue', 'queue'],
    ['drive', 'Google Drive', 'drive'],
    ['metadata', 'Metadata', 'metadata'],
    ['scheduler', 'Scheduler', 'scheduler'],
    ['analytics', 'Analytics', 'analytics'],
    ['quota', 'Quota', 'quota'],
    ['health', 'Health & Audit', 'health'],
    ['leaderboard', 'Top 50', 'leaderboard'],
    ['vpn', 'VPN', 'vpn'],
    ['settings', 'Settings', 'settings']
  ];
  const BOTTOM = ['overview', 'channels', 'queue', 'metadata'];
  const $ = (id) => document.getElementById(id);
  const main = $('main');
  const sheet = $('more-sheet');

  function current() {
    const r = (location.hash || '#overview').slice(1).split('?')[0];
    return ROUTES.some(([k]) => k === r) ? r : 'overview';
  }

  function buildNav() {
    const link = (k, label, ic, short) => h('a', { href: `#${k}`, dataset: { route: k } }, icon(ic), h('span', null, short || label));
    $('side-nav').replaceChildren(...ROUTES.map(([k, l, i]) => link(k, l, i)));
    $('more-links').replaceChildren(...ROUTES.map(([k, l, i]) => link(k, l, i)));
    const short = { overview: 'Home', channels: 'Channels', queue: 'Queue', metadata: 'Metadata' };
    $('bottom-nav').replaceChildren(
      ...BOTTOM.map((k) => { const [, l, i] = ROUTES.find((r) => r[0] === k); return link(k, l, i, short[k]); }),
      h('button', { type: 'button', id: 'more-btn', 'aria-haspopup': 'dialog', 'aria-expanded': 'false', onclick: openSheet }, icon('more'), h('span', null, 'Aur'))
    );
  }
  function markNav(route) {
    document.querySelectorAll('[data-route]').forEach((a) => {
      if (a.dataset.route === route) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    const more = $('more-btn');
    if (more) { if (!BOTTOM.includes(route)) more.setAttribute('aria-current', 'page'); else more.removeAttribute('aria-current'); }
  }

  function openSheet() {
    sheet.hidden = false; $('more-btn').setAttribute('aria-expanded', 'true');
    const first = sheet.querySelector('[aria-current="page"]') || sheet.querySelector('a');
    if (first) first.focus();
  }
  function closeSheet() { if (sheet.hidden) return; sheet.hidden = true; const b = $('more-btn'); if (b) { b.setAttribute('aria-expanded', 'false'); } }
  sheet.addEventListener('click', (e) => { if (e.target.closest('[data-close="sheet"]') || e.target.closest('a')) closeSheet(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSheet(); });

  function refreshChrome() {
    const demo = DY.api.isDemo();
    $('demo-banner').hidden = !demo;
    document.body.classList.toggle('is-demo', demo);
    const pill = $('conn-pill');
    if (demo) { pill.className = 'pill pill-gold'; pill.textContent = 'DEMO'; pill.title = 'Sample data — backend set nahi'; }
    else if (DY.auth.isLoggedIn()) { pill.className = 'pill pill-green'; pill.textContent = 'LIVE'; pill.title = `Backend: ${DY.api.getBackend()}`; }
    else { pill.className = 'pill pill-red'; pill.textContent = 'LOGIN'; pill.title = 'Login nahi hai'; }
  }

  function render() {
    closeSheet();
    const route = current();
    const view = DY.views[route];
    const label = (ROUTES.find((r) => r[0] === route) || [])[1] || 'Overview';
    $('page-title').textContent = view.title || label;
    document.title = `${view.title || label} · DHARM YT PRO`;
    markNav(route);
    document.body.className = document.body.className.replace(/\broute-\S+/g, '').trim();
    document.body.classList.add(`route-${route}`);
    refreshChrome();
    main.replaceChildren();
    // Backend hai par login nahi: protected pages ki jagah login ki taraf bhejo
    if (!DY.api.isDemo() && !DY.auth.isLoggedIn() && route !== 'settings') {
      main.append(DY.ui.empty('Login zaroori hai', 'Backend jud gaya hai. Data dekhne ke liye login karein.',
        h('a', { href: '#settings', class: 'btn btn-gold' }, 'Login karo')));
      return;
    }
    try { view.render(main); } catch (err) { main.append(DY.ui.errorState(err, render)); }
    main.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }

  $('refresh-btn').addEventListener('click', render);
  window.addEventListener('hashchange', render);
  DY.auth.onChange(refreshChrome);
  window.addEventListener('storage', (e) => { if (e.key === 'dy.backendUrl') render(); });

  DY.app = { render, refreshChrome };
  buildNav();
  render();

  // Service worker: sirf http(s) par (file:// par browser allow nahi karta)
  if ('serviceWorker' in navigator && /^https?:$/.test(location.protocol)) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('service-worker.js', { scope: './' }).catch(() => { /* offline support optional */ });
    });
  }
})();
