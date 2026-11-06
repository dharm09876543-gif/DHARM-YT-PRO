(function () {
  'use strict';
  const { h, icon, num, ago, avatar, chip, sectionHead, load, empty, toggle, confirmAction, toast } = DY.ui;

  const AUTH = { active: ['green', 'Auth OK'], expired: ['red', 'Token expire'], not_connected: ['orange', 'Connect nahi'], revoked: ['red', 'Permission hata di'] };
  const authChip = (s) => { const [t, l] = AUTH[s] || ['muted', s || DY.ui.DASH]; return chip(t, l); };

  DY.views.channels = {
    title: 'Channels',
    render(main) {
      let filter = 'all';
      let items = [];
      const search = h('input', { type: 'search', placeholder: 'Channel ya folder dhundo...', 'aria-label': 'Channels search', autocomplete: 'off' });
      const seg = h('div', { class: 'segmented', role: 'group', 'aria-label': 'Filter' });
      const listBox = h('div');
      const count = h('span', { class: 'muted small', 'aria-live': 'polite' });
      [['all', 'Sab'], ['enabled', 'Chalu'], ['disabled', 'Band'], ['auth', 'Auth problem']].forEach(([k, l]) => {
        seg.append(h('button', { type: 'button', 'aria-pressed': String(k === filter), onclick: (e) => {
          filter = k; seg.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b === e.currentTarget))); draw();
        } }, l));
      });

      main.append(
        sectionHead('Channels', 'Har channel ka auth, folder aur upload on/off'),
        h('div', { class: 'card', style: { marginBottom: '12px' } },
          h('div', { class: 'btn-row', style: { alignItems: 'center' } },
            h('div', { class: 'search' }, icon('search'), search), seg, count)),
        listBox
      );

      function draw() {
        const s = search.value.trim().toLowerCase();
        const rows = items.filter((c) => {
          if (s && !(`${c.name} ${c.drive_folder_name || ''} ${c.youtube_channel_id || ''}`.toLowerCase().includes(s))) return false;
          if (filter === 'enabled') return c.enabled;
          if (filter === 'disabled') return !c.enabled;
          if (filter === 'auth') return c.auth_status !== 'active';
          return true;
        });
        count.textContent = `${rows.length} / ${items.length} channels`;
        if (!items.length) { listBox.replaceChildren(empty('Abhi koi channel nahi', 'CLI se jodo: python main.py channels add UC... "Naam" FOLDER_ID')); return; }
        if (!rows.length) { listBox.replaceChildren(empty('Kuch nahi mila', 'Search ya filter badal ke dekho.')); return; }
        listBox.replaceChildren(h('ul', { class: 'list' }, rows.map(row)));
      }

      function row(c) {
        const li = h('li', { class: `item${c.enabled ? '' : ' disabled-row'}` },
          avatar(c.name, c.thumbnail_url),
          h('div', { class: 'item-main' },
            h('div', { class: 'item-title', title: c.name }, c.name),
            h('div', { class: 'item-meta' },
              authChip(c.auth_status),
              h('span', { title: 'Drive folder' }, '📁 ', c.drive_folder_name || DY.ui.DASH),
              h('span', null, '⬆ ', num(c.uploaded)),
              h('span', null, '⏳ ', num(c.queued)),
              c.failed ? h('span', { style: { color: '#fca5a5' } }, '✕ ', num(c.failed)) : null,
              h('span', null, 'Last: ', ago(c.last_upload_at))
            )
          ),
          h('div', { class: 'item-side' },
            toggle(c.enabled, `${c.name} upload ${c.enabled ? 'band' : 'chalu'} karein`, async (on, input) => {
              if (!on) {
                const ok = await confirmAction(`"${c.name}" ke uploads band ho jaayenge. Queue ruk jaayegi. Pakka band karna hai?`, 'Haan, band karo');
                if (!ok) { input.checked = true; return; }
              }
              input.disabled = true;
              try {
                await DY.api.patch(`/api/channels/${encodeURIComponent(c.id)}`, { enabled: on });
                c.enabled = on; li.classList.toggle('disabled-row', !on);
                toast(`${c.name}: ${on ? 'chalu' : 'band'} ✓${DY.api.isDemo() ? ' (demo)' : ''}`, 'ok');
              } catch (e) { input.checked = !on; toast(e.message, 'err'); }
              finally { input.disabled = false; }
            }),
            h('span', { class: 'small muted' }, c.enabled ? 'Chalu' : 'Band')
          )
        );
        return li;
      }

      let t;
      search.addEventListener('input', () => { clearTimeout(t); t = setTimeout(draw, 120); });
      load(listBox, () => DY.api.get('/api/channels'), (d) => { items = (d && d.items) || []; draw(); }, 6);
    }
  };
})();
