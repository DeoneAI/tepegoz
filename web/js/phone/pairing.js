// Pairing link parsing. The link hash carries server, session id, upload key and route.
// The key is moved into sessionStorage and the hash is removed from the address bar.

import { isLocalHost, validateServer } from '../lib/http.js';

export const PAIRING_KEY = 'tepegoz-pairing';
const LEGACY_PAIRING_KEY = 'sensorlink-pairing';
const SESSION_ID = /^[a-f0-9]{24}$/;
const UPLOAD_KEY = /^[a-f0-9]{48}$/;

export function validatePairingServer(server, mode, location) {
  const local = mode === 'usb-adb' && isLocalHost(location.hostname);
  const origin = validateServer(server, { local });
  if (local && origin !== location.origin) throw new Error('USB pairing must use the same localhost origin as this phone page.');
  return origin;
}

/** Build the phone link the dashboard shares (hash, so it never reaches server logs). */
export function buildPairingLink(pageOrigin, { server, session, key, mode }) {
  const link = new URL('/phone.html', pageOrigin);
  link.hash = new URLSearchParams({ server, session, key, mode }).toString();
  return link.href;
}

/** Read pairing from the URL hash (preferred) or from this tab's storage. Returns null if invalid. */
export function readPairing({ location, storage, history }) {
  try {
    const hash = new URLSearchParams(location.hash.slice(1));
    if (hash.has('key')) {
      const mode = hash.get('mode') || 'tunnel';
      const pairing = { server: validatePairingServer(hash.get('server'), mode, location), session: hash.get('session'), key: hash.get('key'), mode };
      if (!SESSION_ID.test(pairing.session) || !UPLOAD_KEY.test(pairing.key)) throw new Error('Invalid link');
      storage.setItem(PAIRING_KEY, JSON.stringify(pairing));
      history?.replaceState(null, '', location.pathname);
      return pairing;
    }
    const saved = JSON.parse(storage.getItem(PAIRING_KEY) || storage.getItem(LEGACY_PAIRING_KEY) || 'null');
    if (saved) validatePairingServer(saved.server, saved.mode, location);
    return saved;
  } catch {
    return null;
  }
}
