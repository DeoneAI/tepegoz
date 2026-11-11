// Dashboard entry point: routing between pages and wiring the feature modules together.

import { $, createToast, enhanceDialogs } from '../lib/dom.js';
import { initTheme } from '../lib/theme.js';
import { createContext } from './context.js';
import { createLivePage } from './live.js';
import { createConnection } from './connection.js';
import { createLibrary } from './library.js';
import { createReplay } from './replay.js';
import { loadProjectStatus, renderProject } from './project.js';

const PAGES = { live: 'Live acquisition', sessions: 'Session library', project: 'Project status', guide: 'Setup & protocol' };

initTheme($('theme-btn'));
const ctx = createContext();
const toast = createToast($('toast'));
enhanceDialogs();

const replay = createReplay(ctx, { toast });
const library = createLibrary(ctx, { toast, openReplay: replay.open });

function showPage(name) {
  if (!PAGES[name]) name = 'live';
  for (const page of Object.keys(PAGES)) $(`${page}-page`).hidden = page !== name;
  for (const link of document.querySelectorAll('[data-page]')) {
    const active = link.dataset.page === name;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  }
  $('crumb').textContent = PAGES[name];
  if (name === 'sessions') library.load();
  if (location.hash.slice(1) !== name) history.replaceState(null, '', `#${name}`);
}

createLivePage(ctx, { toast, openReplay: replay.open });
createConnection(ctx, { toast, onConnected: library.load, showPage });

for (const link of document.querySelectorAll('[data-page]')) {
  link.addEventListener('click', event => { event.preventDefault(); showPage(link.dataset.page); });
}
window.addEventListener('hashchange', () => {
  // The sign-in link pasted into an already-open tab only changes the hash: reload so it is consumed.
  if (location.hash.includes('token=')) return location.reload();
  showPage(location.hash.slice(1));
});
showPage(location.hash.slice(1) || 'live');

loadProjectStatus()
  .then(renderProject)
  .catch(error => { $('project-updated').textContent = error.message; });
