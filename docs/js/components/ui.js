/* UI helpers: safe DOM builder (koi innerHTML nahi), formatters, states, confirm, toast. */
(function () {
  'use strict';
  const DY = (window.DY = window.DY || {});
  DY.views = DY.views || {};

  /** h('div', {class:'x', onclick:fn}, child, 'text') — text hamesha textContent se jaata hai. */
  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === 'class') el.className = v;
        else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
        else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
        else if (k === 'dataset') Object.assign(el.dataset, v);
        else if (k === 'value') el.value = v;
        else if (k === 'checked' || k === 'disabled' || k === 'selected' || k === 'required') el[k] = !!v;
        else if (k === 'href' || k === 'src') el.setAttribute(k, safeUrl(v));
        else el.setAttribute(k, v === true ? '' : String(v));
      }
    }
    append(el, children);
    return el;
  }
  function append(el, children) {
    for (const c of children.flat(Infinity)) {
      if (c === null || c === undefined || c === false) continue;
      el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return el;
  }
  /** Sirf http(s), relative, data:image aur # links. javascript: jaisi cheezein block. */
  function safeUrl(u) {
    const s = String(u || '').trim();
    if (/^(https?:|#|\.\/|\.\.\/|\/|data:image\/)/i.test(s) || /^[\w.-]+(\/|\.|$)/.test(s)) {
      if (/^\s*javascript:/i.test(s)) return '#';
      return s;
    }
    return '#';
  }
  /** SVG icon (static paths, hamare apne). */
  const ICONS = {
    overview: 'M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z',
    channels: 'M21 3H3a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5v2h8v-2h5a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm0 14H3V5h18v12zM10 8v6l5-3-5-3z',
    queue: 'M4 6H2v14a2 2 0 0 0 2 2h14v-2H4V6zm16-4H8a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2zm-1 9h-4v4h-2v-4H9V9h4V5h2v4h4v2z',
    drive: 'M7.71 3.5 1.15 15l3.43 6 6.55-11.5L7.71 3.5zm1.62 0 6.56 11.5h6.96L16.29 3.5H9.33zM8.28 16.5 4.85 22.5h13.1l3.43-6H8.28z',
    metadata: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 0 0 0-1.41l-2.34-2.34a1 1 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
    scheduler: 'M19 4h-1V2h-2v2H8V2H6v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 16H5V9h14v11zM7 11h5v5H7z',
    analytics: 'M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z',
    quota: 'M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 18a8 8 0 1 1 8-8 8 8 0 0 1-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z',
    health: 'M12 21.35 10.55 20C5.4 15.36 2 12.28 2 8.5A5.5 5.5 0 0 1 7.5 3 6 6 0 0 1 12 5.09 6 6 0 0 1 16.5 3 5.5 5.5 0 0 1 22 8.5c0 3.78-3.4 6.86-8.55 11.54z',
    leaderboard: 'M7.5 21H2V9h5.5v12zm7.25-18h-5.5v18h5.5V3zM22 11h-5.5v10H22V11z',
    vpn: 'M12 1 3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z',
    settings: 'M19.14 12.94a7.07 7.07 0 0 0 0-1.88l2.03-1.58a.5.5 0 0 0 .12-.64l-1.92-3.32a.5.5 0 0 0-.6-.22l-2.39.96a7 7 0 0 0-1.62-.94l-.36-2.54A.5.5 0 0 0 13.9 2h-3.84a.5.5 0 0 0-.49.42l-.36 2.54a7 7 0 0 0-1.62.94l-2.39-.96a.5.5 0 0 0-.6.22L2.68 8.48a.5.5 0 0 0 .12.64l2.03 1.58a7.07 7.07 0 0 0 0 1.88l-2.03 1.58a.5.5 0 0 0-.12.64l1.92 3.32a.5.5 0 0 0 .6.22l2.39-.96c.5.39 1.04.7 1.62.94l.36 2.54a.5.5 0 0 0 .49.42h3.84a.5.5 0 0 0 .49-.42l.36-2.54a7 7 0 0 0 1.62-.94l2.39.96a.5.5 0 0 0 .6-.22l1.92-3.32a.5.5 0 0 0-.12-.64l-2.03-1.58zM12 15.6A3.6 3.6 0 1 1 15.6 12 3.6 3.6 0 0 1 12 15.6z',
    more: 'M6 10a2 2 0 1 0 2 2 2 2 0 0 0-2-2zm12 0a2 2 0 1 0 2 2 2 2 0 0 0-2-2zm-6 0a2 2 0 1 0 2 2 2 2 0 0 0-2-2z',
    search: 'M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16a6.47 6.47 0 0 0 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0A4.5 4.5 0 1 1 14 9.5 4.5 4.5 0 0 1 9.5 14z',
    spark: 'M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4z'
  };
  function icon(name) {
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    const p = document.createElementNS(NS, 'path');
    p.setAttribute('fill', 'currentColor');
    p.setAttribute('d', ICONS[name] || ICONS.more);
    svg.appendChild(p);
    return svg;
  }

  // ---------- Formatters: null/undefined => '—' (kabhi 0 nahi) ----------
  const DASH = '—';
  const isNil = (v) => v === null || v === undefined || v === '' || (typeof v === 'number' && Number.isNaN(v));
  function num(v) {
    if (isNil(v)) return DASH;
    return new Intl.NumberFormat('en-IN').format(v);
  }
  function compact(v) {
    if (isNil(v)) return DASH;
    return new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 }).format(v);
  }
  function pct(v, digits = 0) {
    if (isNil(v)) return DASH;
    return `${Number(v).toFixed(digits)}%`;
  }
  function dur(minutes) {
    if (isNil(minutes)) return DASH;
    const hrs = minutes / 60;
    return hrs >= 1 ? `${compact(Math.round(hrs))} hrs` : `${Math.round(minutes)} min`;
  }
  function dt(v) {
    if (isNil(v)) return DASH;
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return DASH;
    return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  }
  function ago(v) {
    if (isNil(v)) return DASH;
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return DASH;
    const s = Math.round((Date.now() - d.getTime()) / 1000);
    const fut = s < 0; const a = Math.abs(s);
    const unit = a < 60 ? `${a} sec` : a < 3600 ? `${Math.round(a / 60)} min` : a < 86400 ? `${Math.round(a / 3600)} ghante` : `${Math.round(a / 86400)} din`;
    return fut ? `${unit} mein` : `${unit} pehle`;
  }
  function bytes(v) {
    if (isNil(v)) return DASH;
    const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0; let n = v;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(n < 10 && i ? 1 : 0)} ${u[i]}`;
  }
  function initials(name) {
    return String(name || '?').replace(/\(.*?\)/g, '').trim().split(/\s+/).slice(0, 2).map((w) => w[0] || '').join('').toUpperCase() || '?';
  }
  function hash(s) { let x = 0; for (const c of String(s)) x = (x * 31 + c.charCodeAt(0)) | 0; return Math.abs(x); }

  function avatar(name, url) {
    if (url && /^https:\/\//i.test(url)) {
      return h('img', { class: 'avatar', src: url, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer', width: 44, height: 44 });
    }
    return h('span', { class: `avatar c${hash(name) % 4}`, 'aria-hidden': 'true' }, initials(name));
  }

  // ---------- Status chips ----------
  const STATUS = {
    DISCOVERED: ['muted', 'Mila (Drive)'], QUEUED: ['muted', 'Line mein'], DOWNLOADING: ['cyan', 'Download ho raha'],
    READY: ['cyan', 'Ready'], UPLOADING: ['gold', 'Upload ho raha'], PROCESSING: ['gold', 'YouTube processing'],
    VERIFYING: ['cyan', 'Check ho raha'], COMPLETED: ['green', 'Ho gaya'], FAILED: ['red', 'Fail'],
    RETRY_WAIT: ['orange', 'Retry ka intezaar'], CANCELLED: ['muted', 'Cancel']
  };
  const LIVE = new Set(['DOWNLOADING', 'UPLOADING', 'PROCESSING', 'VERIFYING']);
  function statusChip(s) {
    const [tone, label] = STATUS[s] || ['muted', s || DASH];
    return h('span', { class: `chip chip-${tone}${LIVE.has(s) ? ' chip-live' : ''}`, title: s }, label);
  }
  function chip(tone, text) { return h('span', { class: `chip chip-${tone}` }, text); }

  // ---------- States ----------
  function loading(count = 4) {
    return h('div', { class: 'grid grid-stats', 'aria-busy': 'true', 'aria-label': 'Load ho raha hai' },
      Array.from({ length: count }, () => h('div', { class: 'skeleton' })));
  }
  function empty(title, text, action) {
    return h('div', { class: 'state', role: 'status' }, h('h3', null, title), text ? h('p', null, text) : null, action || null);
  }
  function errorState(err, onRetry) {
    const msg = (err && err.message) || 'Kuch galat ho gaya.';
    return h('div', { class: 'state error', role: 'alert' },
      h('h3', null, 'Data load nahi hua'),
      h('p', null, msg),
      onRetry ? h('button', { class: 'btn', type: 'button', onclick: onRetry }, 'Dobara try karo') : null);
  }
  function sectionHead(title, sub, ...actions) {
    return h('div', { class: 'section-head' },
      h('div', null, h('h2', null, title), sub ? h('p', null, sub) : null),
      actions.length ? h('div', { class: 'btn-row' }, actions) : null);
  }
  function stat(label, value, sub, accent = 'gold') {
    return h('div', { class: `card stat accent-${accent}` },
      h('div', { class: 'stat-label' }, label),
      h('div', { class: 'stat-value' }, value),
      sub ? h('div', { class: 'stat-sub' }, sub) : null);
  }
  function progress(pctVal, tone, label) {
    const bar = h('span');
    const v = isNil(pctVal) ? 0 : Math.max(0, Math.min(100, pctVal));
    bar.style.width = `${v}%`;
    return h('div', { class: `progress ${tone || ''}`, role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': isNil(pctVal) ? null : Math.round(v), 'aria-label': label || 'Progress' }, bar);
  }
  function toggle(checked, label, onchange, disabled) {
    const input = h('input', { type: 'checkbox', role: 'switch', checked, disabled, 'aria-label': label });
    input.addEventListener('change', () => onchange(input.checked, input));
    return h('label', { class: 'switch' }, input, h('span', { class: 'track', 'aria-hidden': 'true' }));
  }

  // ---------- Confirm dialog (destructive actions) ----------
  function confirmAction(text, okLabel = 'Haan, karo', title = 'Pakka?') {
    const dlg = document.getElementById('confirm-dialog');
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-text').textContent = text;
    document.getElementById('confirm-ok').textContent = okLabel;
    if (typeof dlg.showModal !== 'function') return Promise.resolve(window.confirm(text));
    return new Promise((resolve) => {
      dlg.returnValue = 'cancel';
      const done = () => { dlg.removeEventListener('close', done); resolve(dlg.returnValue === 'ok'); };
      dlg.addEventListener('close', done);
      dlg.showModal();
      dlg.querySelector('button[value="cancel"]').focus();
    });
  }

  // ---------- Toast ----------
  function toast(text, tone = 'info', ms = 3500) {
    const box = document.getElementById('toasts');
    const t = h('div', { class: `toast ${tone}` }, text);
    box.appendChild(t);
    setTimeout(() => t.remove(), ms);
  }

  /** Button ko busy dikhata hai jab tak promise chale. */
  async function busy(btn, fn) {
    if (btn.disabled) return;
    const old = Array.from(btn.childNodes);
    btn.disabled = true; btn.setAttribute('aria-busy', 'true');
    btn.replaceChildren(h('span', { class: 'spinner', 'aria-hidden': 'true' }), ' Ruko...');
    try { return await fn(); } finally {
      btn.disabled = false; btn.removeAttribute('aria-busy'); btn.replaceChildren(...old);
    }
  }

  /** Standard view loader: loading -> data/empty/error. */
  async function load(container, fetcher, render, skeletonCount) {
    container.replaceChildren(loading(skeletonCount));
    try {
      const data = await fetcher();
      container.replaceChildren();
      render(data);
    } catch (err) {
      container.replaceChildren(errorState(err, () => load(container, fetcher, render, skeletonCount)));
    }
  }

  DY.ui = { h, append, icon, num, compact, pct, dur, dt, ago, bytes, DASH, isNil, avatar, statusChip, chip, STATUS,
    loading, empty, errorState, sectionHead, stat, progress, toggle, confirmAction, toast, busy, load, initials };
})();
