// Session library: list recordings stored on the PC, replay them and export files.

import { $, el, saveBlob } from '../lib/dom.js';

const statusOf = s => (s.live?.recording ? 'recording' : s.status === 'recording' ? 'interrupted' : s.status);

export function createLibrary(ctx, { toast, openReplay }) {
  async function download(id, file) {
    try {
      const blob = await ctx.client().get(`/api/sessions/${id}/export?file=${file}`).then(r => r.blob());
      saveBlob(blob, `${id}-${file}`);
    } catch (error) {
      toast(error.message);
    }
  }

  function row(s) {
    const status = statusOf(s);
    const button = (label, onClick) => el('button', { className: 'button secondary small', text: label, onclick: onClick });
    return el('tr', {},
      el('td', {}, el('strong', { text: s.name }), el('small', { text: s.id })),
      el('td', { text: new Date(s.created_at).toLocaleString() }),
      el('td', {}, el('span', { className: `state ${status === 'completed' ? 'ok' : status === 'interrupted' ? 'warn' : ''}`, text: status })),
      el('td', { className: 'num', text: s.live?.metrics?.frames ?? s.metrics?.frames ?? '—' }),
      el('td', { className: 'actions' },
        button('▷ Replay', () => openReplay(s.id)),
        button('↓ IMU CSV', () => download(s.id, 'imu.csv')),
        button('↓ Manifest', () => download(s.id, 'manifest.json'))));
  }

  async function load() {
    if (!ctx.config) { $('library-empty').hidden = false; return; }
    try {
      const list = await ctx.client().getJson('/api/sessions');
      $('session-rows').replaceChildren(...list.map(row));
      $('library-empty').hidden = list.length > 0;
      $('library-count').textContent = `${list.length} session${list.length === 1 ? '' : 's'}`;
      ctx.setOnline(true);
    } catch (error) {
      toast(error.message);
    }
  }

  $('refresh-sessions').addEventListener('click', load);
  return { load };
}
