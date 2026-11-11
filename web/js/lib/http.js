// Collector HTTP client. Every request carries a bearer key, no referrer and no cache.

const LOCAL_HOSTS = ['localhost', '127.0.0.1'];
export const isLocalHost = hostname => LOCAL_HOSTS.includes(hostname);

/**
 * Accept only a bare origin. HTTPS is required, except plain http on localhost when `local` is true.
 * Returns the normalized origin or throws with a user-facing message.
 */
export function validateServer(value, { local = true } = {}) {
  const url = new URL(value);
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('Use only the collector origin, without a path or credentials.');
  }
  const localHttp = local && url.protocol === 'http:' && isLocalHost(url.hostname);
  if (url.protocol !== 'https:' && !localHttp) throw new Error('Use an HTTPS collector URL for phone access.');
  return url.origin;
}

/** fetch() wrapper: throws Error(message) with .status on non-2xx, using the collector's JSON error text. */
export async function request(server, key, route, options = {}) {
  const response = await fetch(server + route, {
    ...options,
    headers: { Authorization: `Bearer ${key}`, ...options.headers },
    signal: options.signal || AbortSignal.timeout(12000),
    referrerPolicy: 'no-referrer',
    cache: 'no-store',
  });
  if (!response.ok) {
    let message;
    try { message = (await response.json()).error; } catch { message = `Request failed (${response.status})`; }
    const error = new Error(message || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return response;
}

export const post = (server, key, route, value) =>
  request(server, key, route, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(value),
  }).then(response => response.json());

/** A bound client for one collector origin + key. */
export function createClient(server, key) {
  return {
    server,
    get: (route, options) => request(server, key, route, options),
    getJson: (route, options) => request(server, key, route, options).then(r => r.json()),
    post: (route, value) => post(server, key, route, value),
    upload: (route, body, headers) => request(server, key, route, { method: 'POST', headers, body }),
  };
}

/** Turn browser network failures into actionable text. */
export const explainNetworkError = (error, hint) => (error?.message === 'Failed to fetch' ? hint : error?.message || String(error));
