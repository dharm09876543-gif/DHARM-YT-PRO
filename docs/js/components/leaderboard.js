(function () {
  'use strict';
  const { h, num, compact, pct, avatar, sectionHead, load, empty, isNil } = DY.ui;

  const COLS = [
    ['subscribers', 'Subscribers', (c) => compact(c.subscribers)],
    ['views_28d', 'Views (28d)', (c) => compact(c.views_28d)],
    ['watch_hours_28d', 'Watch hrs', (c) => compact(c.watch_hours_28d)],
    ['ctr', 'CTR', (c) => pct(c.ctr, 1)],
    ['uploaded', 'Uploads', (c) => num(c.uploaded)]
  ];

  DY.views.leaderboard = {
    title: 'Top 50 Channels',
    render(main) {
      let items = [];
      let sortKey = 'views_28d';
      let dir = -1;
      const sel = h('select', { 'aria-label': 'Sort by', style: { width: 'auto' } }, COLS.map(([k, l]) => h('option', { value: k, selected: k === sortKey }, `Sort: ${l}`)));
      sel.addEventListener('change', () => { sortKey = sel.value; dir = -1; draw(); });
      const box = h('div');
      main.append(sectionHead('Top 50 Channels', 'Leaderboard. Channels without data ("—") are listed last.', sel), box);

      function sorted() {
        return items.slice().sort((a, b) => {
          const x = a[sortKey], y = b[sortKey];
          if (isNil(x) && isNil(y)) return 0;
          if (isNil(x)) return 1;
          if (isNil(y)) return -1;
          return (x - y) * dir;
        }).slice(0, 50);
      }
      function draw() {
        if (!items.length) { box.replaceChildren(empty('No channels', null)); return; }
        sel.value = sortKey;
        const head = h('tr', null, h('th', { scope: 'col' }, '#'), h('th', { scope: 'col' }, 'Channel'),
          COLS.map(([k, l]) => h('th', { scope: 'col', class: 'num', 'aria-sort': k === sortKey ? (dir < 0 ? 'descending' : 'ascending') : 'none' },
            h('button', { class: 'sort', type: 'button', 'aria-label': `Sort by ${l}`, onclick: () => { if (sortKey === k) dir = -dir; else { sortKey = k; dir = -1; } draw(); } },
              l, k === sortKey ? (dir < 0 ? ' ▼' : ' ▲') : ''))));
        const rows = sorted().map((c, i) => h('tr', null,
          h('td', { class: `rank${i < 3 ? ' top' : ''}` }, i < 3 ? ['🥇', '🥈', '🥉'][i] : i + 1),
          h('td', null, h('div', { class: 'cell-name' }, avatar(c.name, c.thumbnail_url), h('span', { title: c.name }, c.name))),
          COLS.map(([k, , f]) => h('td', { class: 'num' }, f(c)))));
        box.replaceChildren(h('div', { class: 'table-wrap' }, h('table', null, h('caption', { class: 'sr-only' }, 'Top 50 channels'), h('thead', null, head), h('tbody', null, rows))));
      }
      load(box, () => DY.api.get('/api/leaderboard'), (d) => { items = (d && d.items) || []; draw(); }, 2);
    }
  };
})();
