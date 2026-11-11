// Project page: roadmap status, open gates and measured benchmark highlights from /assets/project-status.json.
// The data file is static and versioned with the code, so the page works without a collector.

import { $, el } from '../lib/dom.js';

const STATE_CLASS = { done: 'ok', partial: 'warn', pending: '', blocked: 'bad' };

export async function loadProjectStatus(fetchImpl = fetch) {
  const response = await fetchImpl('/assets/project-status.json', { cache: 'no-store' });
  if (!response.ok) throw new Error(`Project status unavailable (${response.status})`);
  return response.json();
}

/** Fraction of checklist items done, for the sidebar progress bar. */
export const progress = status => (status.checklist.total ? status.checklist.done / status.checklist.total : 0);

export function renderProject(status) {
  $('project-updated').textContent = `Status as of ${status.updated}`;
  $('checklist-summary').textContent = `${status.checklist.done} of ${status.checklist.total} checklist items done`;
  $('checklist-bar').style.setProperty('--value', String(progress(status)));

  $('milestones').replaceChildren(...status.milestones.map(m =>
    el('article', { className: 'milestone' },
      el('header', {},
        el('span', { className: 'week', text: m.week }),
        el('span', { className: `state ${STATE_CLASS[m.state] ?? ''}`, text: m.label })),
      el('h3', { text: m.title }),
      el('p', { text: m.remaining }))));

  $('next-steps').replaceChildren(...status.next.map(text => el('li', { text })));

  $('bench-rows').replaceChildren(...status.benchmarks.rows.map(row =>
    el('tr', {}, ...status.benchmarks.columns.map(col => el('td', { className: col.numeric ? 'num' : '', text: row[col.key] ?? '—' })))));
  $('bench-head').replaceChildren(el('tr', {}, ...status.benchmarks.columns.map(col => el('th', { className: col.numeric ? 'num' : '', text: col.label }))));
  $('bench-note').textContent = status.benchmarks.note;

  $('decisions').replaceChildren(...status.decisions.map(d =>
    el('div', {}, el('dt', { text: d.topic }), el('dd', { text: d.decision }))));

  // Sidebar milestone card
  const current = status.milestones.find(m => m.state !== 'done') ?? status.milestones.at(-1);
  $('milestone-title').textContent = current.title;
  $('milestone-week').textContent = `${current.week} · ${current.label}`;
  $('milestone-track').replaceChildren(...status.milestones.map(m => el('i', { className: STATE_CLASS[m.state] ?? '' })));
}
