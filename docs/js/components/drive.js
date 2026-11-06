(function () {
  'use strict';
  const { h, num, bytes, ago, chip, sectionHead, load, empty, progress, toast, busy, stat } = DY.ui;

  DY.views.drive = {
    title: 'Google Drive',
    render(main) {
      const box = h('div');
      const scanBtn = h('button', { class: 'btn btn-gold', type: 'button', onclick: (e) => busy(e.currentTarget, async () => {
        try { const r = await DY.api.post('/api/drive/scan'); toast(`Scan complete: ${num(r && r.new_files)} new files${DY.api.isDemo() ? ' (demo)' : ''}`, 'ok'); }
        catch (err) { toast(err.message, 'err'); }
      }) }, 'Scan now');
      main.append(sectionHead('Google Drive', 'Videos are picked up from these folders. A file moves to Trash only after its upload is verified (never a permanent delete).', scanBtn), box);

      load(box, () => DY.api.get('/api/drive'), (d) => {
        const st = d.storage || {};
        const used = st.limit_bytes && !DY.ui.isNil(st.used_bytes) ? Math.round((st.used_bytes / st.limit_bytes) * 100) : null;
        const folders = d.folders || [];
        const pending = folders.length && folders.every((f) => !DY.ui.isNil(f.pending_files)) ? folders.reduce((a, f) => a + f.pending_files, 0) : null;
        const storageCard = stat('Drive storage', used === null ? DY.ui.DASH : `${used}%`, `${bytes(st.used_bytes)} / ${bytes(st.limit_bytes)}`, used >= 90 ? 'red' : 'cyan');
        storageCard.append(progress(used, used >= 90 ? 'bad' : '', 'Drive storage'));
        box.append(
          h('div', { class: 'grid grid-stats', style: { marginBottom: '12px' } },
            stat('Connection', d.connected ? 'Connected' : 'No', d.account_label || DY.ui.DASH, d.connected ? 'green' : 'red'),
            stat('Folders', num(folders.length), 'Linked to channels', 'gold'),
            stat('Pending files', num(pending), 'Waiting to upload', 'cyan'),
            storageCard),
          folders.length
            ? h('div', { class: 'table-wrap' }, h('table', null,
                h('caption', { class: 'sr-only' }, 'Drive folders'),
                h('thead', null, h('tr', null, h('th', null, 'Folder'), h('th', null, 'Channel'), h('th', { class: 'num' }, 'Pending'), h('th', { class: 'num' }, 'Trashed'), h('th', null, 'Last scan'), h('th', null, 'Status'))),
                h('tbody', null, folders.map((f) => h('tr', null,
                  h('td', null, '📁 ', f.name),
                  h('td', { class: 'muted' }, f.channel_name || DY.ui.DASH),
                  h('td', { class: 'num' }, num(f.pending_files)),
                  h('td', { class: 'num' }, num(f.trashed_after_upload)),
                  h('td', null, ago(f.last_scan_at)),
                  h('td', null, f.status === 'ok' ? chip('green', 'OK') : chip('red', 'No access'))))))
              )
            : empty('No folders linked', 'Link a Drive folder ID to a channel.')
        );
      }, 4);
    }
  };
})();
