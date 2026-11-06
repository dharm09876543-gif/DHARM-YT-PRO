(function () {
  'use strict';
  const { h, sectionHead, toast, busy, confirmAction, chip } = DY.ui;

  DY.views.settings = {
    title: 'Settings',
    render(main) {
      const urlInput = h('input', { id: 'set-url', type: 'url', inputmode: 'url', placeholder: 'https://dharm-yt-api.example.com', value: DY.api.getBackend(), autocomplete: 'off', spellcheck: 'false', 'aria-describedby': 'set-url-h' });
      const urlErr = h('div', { class: 'error-text', role: 'alert' });
      const modeChip = h('span');
      const drawMode = () => modeChip.replaceChildren(DY.api.isDemo() ? chip('gold', 'Demo mode') : DY.auth.isLoggedIn() ? chip('green', `Login: ${DY.auth.getUser()}`) : chip('orange', 'Not logged in'));

      const saveUrl = h('button', { class: 'btn btn-gold', type: 'submit' }, 'Save URL');
      const testBtn = h('button', { class: 'btn btn-cyan', type: 'button', onclick: (e) => busy(e.currentTarget, async () => {
        if (DY.api.isDemo()) { toast('Save the URL first.', 'warn'); return; }
        try { await DY.api.request('/api/status', { auth: false }); toast('Backend connection OK ✓', 'ok'); }
        catch (err) { toast(err.message, 'err'); }
      }) }, 'Connection test');
      const clearBtn = h('button', { class: 'btn btn-danger', type: 'button', onclick: async () => {
        if (DY.api.isDemo()) return;
        if (!(await confirmAction('The backend URL will be removed and you will be logged out. The dashboard will switch to demo mode.', 'Yes, remove'))) return;
        await DY.auth.logout(); DY.api.setBackend(''); urlInput.value = ''; toast('Demo mode on', 'warn'); DY.app.refreshChrome(); rerender();
      } }, 'Remove URL (demo mode)');

      const urlForm = h('form', { class: 'card stack', novalidate: true, onsubmit: (e) => {
        e.preventDefault();
        urlErr.textContent = '';
        try {
          const before = DY.api.getBackend();
          const saved = DY.api.setBackend(urlInput.value);
          if (saved !== before) DY.auth.clear();
          urlInput.value = saved;
          toast(saved ? 'Backend URL saved. Now log in.' : 'URL empty — demo mode', saved ? 'ok' : 'warn');
          DY.app.refreshChrome(); rerender();
        } catch (err) { urlErr.textContent = err.message; urlInput.classList.add('input-error'); urlInput.focus(); }
      } },
        h('div', { class: 'card-head' }, h('h3', null, '1. Backend URL'), modeChip),
        h('div', { class: 'field' }, h('label', { for: 'set-url' }, 'Backend address'), urlInput,
          h('span', { class: 'hint', id: 'set-url-h' }, 'The https address of your FastAPI backend. Saved only in this browser (localStorage). Never put a secret or API key here.'), urlErr),
        h('div', { class: 'btn-row' }, saveUrl, testBtn, DY.api.isDemo() ? null : clearBtn));
      urlInput.addEventListener('input', () => { urlInput.classList.remove('input-error'); urlErr.textContent = ''; });

      // Login
      const user = h('input', { id: 'set-user', type: 'text', autocomplete: 'username', autocapitalize: 'off', spellcheck: 'false', required: true });
      const pass = h('input', { id: 'set-pass', type: 'password', autocomplete: 'current-password', required: true });
      const loginErr = h('div', { class: 'error-text', role: 'alert' });
      const loginBtn = h('button', { class: 'btn btn-gold', type: 'submit' }, 'Login');
      let loginCard;
      if (DY.api.isDemo()) {
        loginCard = h('div', { class: 'card stack' }, h('h3', null, '2. Login'),
          h('p', { class: 'muted' }, 'No login is needed in demo mode. After you save a backend URL above, the login form appears here.'));
      } else if (DY.auth.isLoggedIn()) {
        loginCard = h('div', { class: 'card stack' }, h('h3', null, '2. Login'),
          h('p', null, 'Logged in as: ', h('strong', null, DY.auth.getUser() || '—')),
          h('p', { class: 'hint' }, 'The session token lives only in this tab (sessionStorage). Closing the tab logs you out.'),
          h('div', { class: 'btn-row' }, h('button', { class: 'btn btn-danger', type: 'button', onclick: async () => {
            if (!(await confirmAction('Log out?', 'Yes, log out'))) return;
            await DY.auth.logout(); toast('Logged out', 'ok'); DY.app.refreshChrome(); rerender();
          } }, 'Logout')));
      } else {
        loginCard = h('form', { class: 'card stack', onsubmit: (e) => {
          e.preventDefault(); loginErr.textContent = '';
          if (!user.value.trim() || !pass.value) { loginErr.textContent = 'Enter both username and password.'; return; }
          busy(loginBtn, async () => {
            try { await DY.auth.login(user.value.trim(), pass.value); pass.value = ''; toast('Logged in ✓', 'ok'); DY.app.refreshChrome(); location.hash = '#overview'; }
            catch (err) { pass.value = ''; loginErr.textContent = err.message; }
          });
        } },
          h('h3', null, '2. Login'),
          h('div', { class: 'form-grid two' },
            h('div', { class: 'field' }, h('label', { for: 'set-user' }, 'Username'), user),
            h('div', { class: 'field' }, h('label', { for: 'set-pass' }, 'Password'), pass)),
          loginErr,
          h('p', { class: 'hint' }, 'The password is sent only to the backend and is never saved in the browser.'),
          h('div', { class: 'btn-row' }, loginBtn));
      }

      const cacheBtn = h('button', { class: 'btn btn-ghost', type: 'button', onclick: async () => {
        if (!(await confirmAction('Clear the app\'s cached files and reload the page? (Settings are kept)', 'Yes, reload'))) return;
        try {
          if (window.caches) { const ks = await caches.keys(); await Promise.all(ks.map((k) => caches.delete(k))); }
          if (navigator.serviceWorker) { const rs = await navigator.serviceWorker.getRegistrations(); await Promise.all(rs.map((r) => r.unregister())); }
        } catch (_) { /* ignore */ }
        location.reload();
      } }, 'Update app / clear cache');

      const root = h('div', { class: 'stack' },
        sectionHead('Settings', 'Connect a backend and log in'),
        urlForm, loginCard,
        h('div', { class: 'card stack' }, h('h3', null, '3. App'),
          h('p', { class: 'hint' }, 'To add to your home screen: browser menu → "Add to Home screen".'),
          h('div', { class: 'btn-row' }, cacheBtn, h('a', { class: 'btn btn-ghost', href: 'privacy.html' }, 'Privacy policy'))));
      main.append(root);
      drawMode();

      function rerender() { main.replaceChildren(); DY.views.settings.render(main); }
    }
  };
})();
