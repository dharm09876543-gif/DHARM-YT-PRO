(function () {
  'use strict';
  const { h, dt, ago, chip, sectionHead, load, empty } = DY.ui;
  const T = { ok: ['green', 'OK'], warn: ['gold', 'Dhyan do'], fail: ['red', 'Kharab'] };

  DY.views.health = {
    title: 'Health & Audit',
    render(main) {
      const box = h('div');
      main.append(sectionHead('Health & Audit', 'System checks (python main.py doctor jaisa) aur kisne kya kiya'), box);
      load(box, () => DY.api.get('/api/health'), (d) => {
        const checks = d.checks || [];
        const audit = d.audit || [];
        box.append(h('div', { class: 'grid grid-2' },
          h('div', { class: 'card' }, h('h3', { style: { marginBottom: '10px' } }, 'System checks'),
            checks.length ? h('ul', { class: 'err-list' }, checks.map((c) => {
              const [tone, label] = T[c.status] || ['muted', c.status || DY.ui.DASH];
              return h('li', null, h('span', { class: 'msg' }, h('strong', null, c.name), h('br'), h('span', { class: 'small muted' }, c.detail || DY.ui.DASH)), chip(tone, label));
            })) : empty('Checks nahi mile', null)),
          h('div', { class: 'card' }, h('h3', { style: { marginBottom: '10px' } }, 'Audit log'),
            audit.length ? h('ul', { class: 'err-list' }, audit.map((a) => h('li', null,
              h('span', { class: 'msg' }, h('span', { class: 'mono', style: { color: 'var(--cyan)' } }, a.action), ' · ', a.target || DY.ui.DASH, h('br'), h('span', { class: 'small muted' }, a.actor || DY.ui.DASH)),
              h('span', { class: 'when', title: dt(a.at) }, ago(a.at))))) : empty('Audit log khaali', null))));
      }, 2);
    }
  };
})();
