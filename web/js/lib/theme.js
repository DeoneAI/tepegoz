// Light / dark theme. Follows the OS until the user picks one; the choice is a per-browser convenience.
const KEY = 'tepegoz-theme';

function read() { try { return localStorage.getItem(KEY); } catch { return null; } }
function write(value) { try { localStorage.setItem(KEY, value); } catch { /* storage blocked: theme still applies for this page */ } }

export function initTheme(button) {
  const saved = read();
  if (saved === 'light' || saved === 'dark') document.documentElement.dataset.theme = saved;
  button?.addEventListener('click', () => {
    const systemDark = matchMedia('(prefers-color-scheme: dark)').matches;
    const current = document.documentElement.dataset.theme || (systemDark ? 'dark' : 'light');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    write(next);
    window.dispatchEvent(new Event('resize')); // redraw canvas charts with the new colours
  });
}
