(function () {
  'use strict';
  const { h, num, compact, dur, pct, sectionHead, load, empty, stat, isNil, DASH } = DY.ui;

  const RANGES = [['today', 'Aaj'], ['7d', '7 din'], ['28d', '28 din'], ['90d', '90 din'], ['custom', 'Custom']];
  const isoDay = (d) => d.toISOString().slice(0, 10);

  DY.views.analytics = {
    title: 'Analytics',
    render(main) {
      let range = '28d';
      const seg = h('div', { class: 'segmented', role: 'group', 'aria-label': 'Date range' });
      const start = h('input', { type: 'date', 'aria-label': 'Start date', max: isoDay(new Date()) });
      const end = h('input', { type: 'date', 'aria-label': 'End date', max: isoDay(new Date()) });
      start.value = isoDay(new Date(Date.now() - 13 * 864e5)); end.value = isoDay(new Date());
      const applyBtn = h('button', { class: 'btn btn-gold btn-sm', type: 'button', onclick: () => fetchNow() }, 'Dekho');
      const customRow = h('div', { class: 'btn-row', hidden: true, style: { alignItems: 'center', marginTop: '10px' } },
        h('label', { class: 'small muted' }, 'Se ', start), h('label', { class: 'small muted' }, 'Tak ', end), applyBtn);
      const box = h('div');
      RANGES.forEach(([k, l]) => seg.append(h('button', { type: 'button', 'aria-pressed': String(k === range), onclick: (e) => {
        range = k; seg.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b === e.currentTarget)));
        customRow.hidden = k !== 'custom';
        if (k !== 'custom') fetchNow();
      } }, l)));

      main.append(
        sectionHead('Analytics', 'YouTube Analytics ka data 1-2 din late aata hai. Jahan data nahi hai wahan "—" dikhega (0 nahi).'),
        h('div', { class: 'card', style: { marginBottom: '12px' } }, seg, customRow),
        box);

      function fetchNow() {
        let qs = `range=${encodeURIComponent(range)}`;
        if (range === 'custom') {
          if (!start.value || !end.value || start.value > end.value) { DY.ui.toast('Start date, end date se pehle honi chahiye.', 'warn'); return; }
          qs += `&start=${start.value}&end=${end.value}`;
        }
        load(box, () => DY.api.get(`/api/analytics?${qs}`), render, 4);
      }

      function render(d) {
        const t = d.totals || {};
        box.append(h('div', { class: 'grid grid-stats', style: { marginBottom: '12px' } },
          stat('Views', compact(t.views), num(t.views), 'cyan'),
          stat('Watch time', dur(t.watch_minutes), isNil(t.watch_minutes) ? 'Data nahi' : `${num(t.watch_minutes)} min`, 'gold'),
          stat('Naye subscribers', compact(t.subscribers_gained), num(t.subscribers_gained), 'green'),
          stat('Avg CTR', pct(t.avg_ctr, 1), 'Impressions click-through', 'muted')));

        const series = d.series || [];
        const card = h('div', { class: 'card', style: { marginBottom: '12px' } }, h('div', { class: 'card-head' }, h('h3', null, 'Roz ke views'), h('span', { class: 'small muted' }, 'Dhaari wala = data abhi nahi aaya')));
        if (!series.length || series.every((r) => isNil(r.views))) {
          card.append(empty('Is range ka data abhi nahi aaya', 'Kal dobara dekho.'));
        } else {
          const max = Math.max(...series.map((r) => r.views || 0), 1);
          const bars = h('div', { class: 'bars', role: 'img', 'aria-label': `Roz ke views, ${series.length} din` });
          series.forEach((r) => {
            const b = h('div', { class: `bar${isNil(r.views) ? ' null' : ''}`, title: `${r.date}: ${isNil(r.views) ? `${DASH} (data nahi)` : num(r.views)}` });
            if (!isNil(r.views)) b.style.height = `${Math.max(2, (r.views / max) * 100)}%`;
            bars.append(b);
          });
          card.append(bars, h('div', { class: 'bars-axis' }, h('span', null, series[0].date), h('span', null, series[series.length - 1].date)));
        }
        box.append(card);

        const tv = d.top_videos || [];
        box.append(h('div', { class: 'card' }, h('h3', { style: { marginBottom: '10px' } }, 'Top videos'),
          tv.length ? h('div', { class: 'table-wrap' }, h('table', null,
            h('thead', null, h('tr', null, h('th', null, '#'), h('th', null, 'Video'), h('th', null, 'Channel'), h('th', { class: 'num' }, 'Views'))),
            h('tbody', null, tv.map((v, i) => h('tr', null, h('td', { class: 'rank' }, i + 1), h('td', null, v.title), h('td', { class: 'muted' }, v.channel_name || DASH), h('td', { class: 'num' }, num(v.views)))))))
            : empty('Koi video data nahi', null)));
      }
      fetchNow();
    }
  };
})();
