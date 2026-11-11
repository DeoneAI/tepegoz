// Shared dashboard state: the collector connection, the active session and a change signal.
// Modules read `ctx` and call ctx.emit(); nothing else holds global mutable state.

import { createClient, isLocalHost, validateServer } from '../lib/http.js';

const STORAGE_KEY = 'tepegoz-connection';
const LEGACY_KEY = 'sensorlink-connection';

function loadConfig(storage) {
  try { return JSON.parse(storage.getItem(STORAGE_KEY) || storage.getItem(LEGACY_KEY) || 'null'); } catch { return null; }
}

/**
 * The collector prints http://localhost:8787/#token=… at start-up. Opening that link on the PC signs
 * the dashboard in: the token moves to this tab's session storage and leaves the address bar.
 */
function consumeLoginLink(storage, location, history) {
  if (!isLocalHost(location.hostname)) return;
  const token = new URLSearchParams(location.hash.slice(1)).get('token');
  if (!token || !/^[\w.-]{16,256}$/.test(token)) return;
  storage.setItem(STORAGE_KEY, JSON.stringify({ server: location.origin, token, mode: 'tunnel' }));
  history?.replaceState(null, '', `${location.pathname}#live`);
}

/**
 * "View from another device" on the collector PC opens the hosted dashboard at
 * /#collector=https://….trycloudflare.com&token=… . Save both and clear them from the address bar.
 * The #fragment never leaves the browser, so the token is not sent to the hosting site.
 */
export function consumeRemoteLink(storage, location, history) {
  if (isLocalHost(location.hostname)) return false;
  const params = new URLSearchParams(location.hash.slice(1));
  const collector = params.get('collector');
  const token = params.get('token');
  if (!collector || !token || !/^[\w.-]{16,256}$/.test(token)) return false;
  let server;
  try { server = validateServer(collector, { local: false }); } catch { return false; }
  storage.setItem(STORAGE_KEY, JSON.stringify({ server, token, mode: 'tunnel' }));
  history?.replaceState(null, '', `${location.pathname}#live`);
  return true;
}

export function createContext({ storage = sessionStorage, location = window.location, history = window.history } = {}) {
  consumeLoginLink(storage, location, history);
  consumeRemoteLink(storage, location, history);
  const listeners = new Set();
  // On the collector PC the dashboard is trusted without a token (see pc/local.mjs).
  const localDefault = isLocalHost(location.hostname) ? { server: location.origin, token: '', mode: 'tunnel' } : null;
  const ctx = {
    config: loadConfig(storage) ?? localDefault,
    online: false,
    active: null,          // session currently shown on the Live page
    sensor: 'accelerometer',
    isLocalPage: isLocalHost(location.hostname),

    /** On the collector PC the dashboard talks to its own origin; elsewhere to the configured tunnel. */
    collectorOrigin(server = ctx.config?.server) {
      return ctx.isLocalPage ? location.origin : server;
    },
    client() {
      if (!ctx.config) throw new Error('Connect your PC collector first.');
      return createClient(ctx.collectorOrigin(), ctx.config.token);
    },
    saveConfig(config) {
      ctx.config = config;
      storage.setItem(STORAGE_KEY, JSON.stringify(config));
      storage.removeItem(LEGACY_KEY);
    },
    setActive(session) { ctx.active = session; ctx.emit('session'); },
    setOnline(value) { if (ctx.online !== value) { ctx.online = value; ctx.emit('online'); } },
    on(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    emit(reason) { for (const listener of listeners) listener(reason, ctx); },
  };
  return ctx;
}
