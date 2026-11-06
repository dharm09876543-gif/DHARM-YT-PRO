(function () {
  'use strict';
  const { h, num, dt, ago, sectionHead, load, empty, stat, progress, isNil } = DY.ui;
  const sum = (arr, k) => (arr.length && arr.every((x) => !isNil(x[k])) ? arr.reduce((a, x) => a + x[k], 0) : null);
  const pctOf = (u, l) => (isNil(u) || !l ? null : Math.round((u / l) * 100));

  DY.views.quota = {
    title: 'Quota Tracker',
    render(main) {
      const box = h('div');
      main.append(sectionHead('Quota Tracker', 'Har Google Cloud project: 10,000 units/din (default). 1 upload ≈ 1,600 units. VPN se quota nahi badhta.'), box);
      load(box, () => DY.api.get('/api/quota'), (d) => {
        const ps = d.projects || [];
        const used = sum(ps, 'used');
        const limit = sum(ps, 'limit');
        const cost = d.cost || {};
        const left = !isNil(limit) && !isNil(used) ? limit - used : null;
        const uploadsLeft = left !== null && cost.upload ? Math.floor(left / cost.upload) : null;
        box.append(
          h('div', { class: 'grid grid-stats', style: { marginBottom: '12px' } },
            stat('Aaj use hua', num(used), `${num(limit)} mein se`, pctOf(used, limit) >= 85 ? 'red' : 'gold'),
            stat('Bacha', num(left), 'units', 'green'),
            stat('Aur uploads', num(uploadsLeft), `@ ${num(cost.upload)} units/upload`, 'cyan'),
            stat('Reset', ago(d.resets_at), `${dt(d.resets_at)} (Pacific midnight)`, 'muted')),
          h('div', { class: 'card', style: { marginBottom: '12px' } }, h('h3', { style: { marginBottom: '10px' } }, 'Projects'),
            ps.length ? h('ul', { class: 'list' }, ps.map((p) => {
              const pc = pctOf(p.used, p.limit);
              return h('li', { class: 'item', style: { flexDirection: 'column', alignItems: 'stretch', background: 'var(--card-2)' } },
                h('div', { style: { display: 'flex', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap' } },
                  h('strong', { class: 'mono' }, p.name), h('span', { class: 'small muted' }, `${num(p.used)} / ${num(p.limit)} · ${DY.ui.pct(pc)} · ${num(p.uploads_today)} uploads aaj`)),
                progress(pc, pc >= 85 ? 'bad' : '', `${p.name} quota`));
            })) : empty('Koi project nahi', null)),
          h('div', { class: 'grid grid-2' },
            h('div', { class: 'card' }, h('h3', { style: { marginBottom: '10px' } }, 'Kis kaam ka kitna'),
              h('dl', { class: 'kv' },
                h('dt', null, 'Video upload'), h('dd', null, `${num(cost.upload)} units`),
                h('dt', null, 'Thumbnail set'), h('dd', null, `${num(cost.thumbnail)} units`),
                h('dt', null, 'Metadata update'), h('dd', null, `${num(cost.metadata_update)} units`),
                h('dt', null, 'List / read'), h('dd', null, `${num(cost.list)} unit`))),
            h('div', { class: 'card' }, h('h3', { style: { marginBottom: '10px' } }, 'Pichhle 7 din'),
              (d.history || []).length ? h('div', { class: 'meter' }, d.history.map((r) => {
                const pc = pctOf(r.used, limit);
                return h('div', null, h('div', { class: 'field-row small' }, h('span', { class: 'muted' }, r.date), h('span', null, num(r.used))), progress(pc, pc >= 85 ? 'bad' : '', r.date));
              })) : empty('History nahi', null))),
          h('p', { class: 'callout warn small', style: { marginTop: '12px' } }, '100+ channels ke liye Google se quota increase (YouTube API audit) chahiye. Audit ke bina unverified project ke uploads private lock rehte hain.')
        );
      }, 4);
    }
  };
})();
