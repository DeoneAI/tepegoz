// Optional built-in HTTPS tunnel for Wi-Fi / mobile-data phones (Cloudflare quick tunnel).
// Phones need HTTPS for camera and motion sensors; a quick tunnel gives a temporary
// https://<random>.trycloudflare.com address that forwards to this collector.
// The phone then loads /phone.html from that same address, so no CORS or ALLOWED_ORIGINS setup is needed.
import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';

const URL_PATTERN = /https:\/\/[a-z0-9-]+\.trycloudflare\.com/;

export function findCloudflared(root, env = process.env) {
  if (env.CLOUDFLARED_PATH) return env.CLOUDFLARED_PATH;
  const bundled = path.join(root, '.tools', process.platform === 'win32' ? 'cloudflared.exe' : 'cloudflared');
  return existsSync(bundled) ? bundled : 'cloudflared';
}

/** Extract the public quick-tunnel URL from cloudflared's log output, or null. */
export const parseTunnelUrl = text => text.match(URL_PATTERN)?.[0] ?? null;

export function createTunnel({ port, root, spawnImpl = spawn, timeoutMs = 30000 }) {
  let child = null;
  let url = null;
  let error = null;
  let starting = null;

  function status() {
    return { running: Boolean(child && url), starting: Boolean(starting), url, error,
      install_hint: 'Install once: winget install --id Cloudflare.cloudflared  (or put cloudflared.exe in .tools/)' };
  }

  function start(onUrl = () => {}) {
    if (url) return Promise.resolve(status());
    if (starting) return starting;
    error = null;
    starting = new Promise(resolve => {
      const done = () => { clearTimeout(timer); starting = null; resolve(status()); };
      const timer = setTimeout(() => { error = 'The tunnel did not report an address within 30 s. Check the internet connection.'; stop(); done(); }, timeoutMs);
      try {
        child = spawnImpl(findCloudflared(root), ['tunnel', '--no-autoupdate', '--url', `http://localhost:${port}`], { windowsHide: true });
      } catch (e) {
        error = 'cloudflared could not start: ' + e.message; child = null; done(); return;
      }
      const read = chunk => {
        const found = parseTunnelUrl(String(chunk));
        if (found && !url) { url = found; onUrl(url); done(); }
      };
      child.stdout?.on('data', read);
      child.stderr?.on('data', read);
      child.on('error', e => {
        error = e.code === 'ENOENT' ? 'cloudflared is not installed.' : 'cloudflared failed: ' + e.message;
        child = null; url = null; done();
      });
      child.on('exit', () => { child = null; url = null; if (starting) done(); });
    });
    return starting;
  }

  function stop() {
    try { child?.kill(); } catch { /* already gone */ }
    child = null; url = null;
  }

  return { start, stop, status };
}
