// "Connect your phone" dialog + session creation and the pairing panel.
//
// On the collector PC (http://localhost:8787) the dashboard is already signed in by the start-up link,
// so the only choice left is the phone route:
//   Wi-Fi / mobile data → the collector starts a temporary HTTPS tunnel; the phone opens the page through it.
//   USB cable (Android) → ADB maps the phone's localhost:8787 to this PC.
// Opening the dashboard from another computer (e.g. the Vercel copy) is an advanced option.

import { $, el } from '../lib/dom.js';
import { explainNetworkError, request, validateServer } from '../lib/http.js';
import { buildPairingLink } from '../phone/pairing.js';

export function createConnection(ctx, { toast, onConnected, showPage }) {
  let pairURL = null;

  const route = () => document.querySelector('input[name="route"]:checked')?.value || 'wifi';
  const token = () => ctx.config?.token || $('server-token').value.trim();
  const local = (path, options) => request(location.origin, token(), path, options).then(r => r.json());

  // ---------------------------------------------------------------- dialog
  function showRoute() {
    const r = route();
    $('wifi-setup').hidden = r !== 'wifi';
    $('usb-setup').hidden = r !== 'usb';
  }

  async function openSettings() {
    const signedIn = Boolean(ctx.config?.token);
    $('local-setup').hidden = !ctx.isLocalPage;
    $('remote-setup').open = !ctx.isLocalPage;
    $('token-field').hidden = signedIn;
    $('signed-in').hidden = !signedIn;
    $('server-url').value = ctx.config && !ctx.isLocalPage ? ctx.config.server : '';
    $('server-token').value = '';
    $('connection-error').textContent = '';
    const usb = ctx.config?.mode === 'usb-adb';
    $(usb ? 'route-usb' : 'route-wifi').checked = true;
    showRoute();
    $('settings-dialog').showModal();
    if (ctx.isLocalPage && signedIn) refreshTunnel();
  }

  function renderTunnel(status) {
    const box = $('tunnel-status');
    if (status.url) {
      box.className = 'route-status ok';
      box.textContent = `Secure link is running: ${status.url}`;
      $('tunnel-start').hidden = true;
    } else if (status.starting) {
      box.className = 'route-status';
      box.textContent = 'Starting the secure link…';
    } else {
      box.className = status.error ? 'route-status warn' : 'route-status';
      box.textContent = status.error ? `${status.error} ${status.install_hint}` : 'Not started yet. It starts automatically when you continue.';
      $('tunnel-start').hidden = false;
    }
  }

  async function refreshTunnel() {
    try { renderTunnel((await local('/api/connection')).tunnel); } catch { /* shown on submit */ }
  }

  async function startTunnel() {
    renderTunnel({ starting: true });
    const status = await local('/api/tunnel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', signal: AbortSignal.timeout(40000) });
    renderTunnel(status);
    if (!status.url) throw new Error(status.error ? `${status.error} ${status.install_hint}` : 'The secure link did not start.');
    return status.url;
  }

  async function connect(event) {
    event.preventDefault();
    const button = event.submitter;
    button.disabled = true;
    $('connection-error').textContent = '';
    try {
      let config;
      const remote = !ctx.isLocalPage || $('server-url').value.trim();
      if (remote) {
        const remoteToken = $('remote-token').value.trim() || ctx.config?.token;
        if (!remoteToken) throw new Error('Paste the collector token from the PC.');
        config = { server: validateServer($('server-url').value.trim()), token: remoteToken, mode: 'tunnel' };
        await request(config.server, config.token, '/api/sessions');
      } else {
        if (!token()) throw new Error('Open the sign-in link printed by the collector, or paste its token.');
        await request(location.origin, token(), '/api/sessions'); // checks the token
        if (route() === 'wifi') {
          config = { server: await startTunnel(), token: token(), mode: 'tunnel' };
        } else {
          const serial = $('usb-device').value;
          if (!serial) throw new Error('Click "Find my phone" and pick your device first.');
          const usb = await local('/api/usb', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ serial }), signal: AbortSignal.timeout(45000) });
          config = { server: usb.phone_origin, token: token(), mode: 'usb-adb' };
        }
      }
      ctx.saveConfig(config);
      ctx.active = null;
      ctx.emit('connection');
      ctx.setOnline(true);
      $('settings-dialog').close();
      toast(config.mode === 'usb-adb' ? 'USB link ready. Create a session to pair your phone.' : 'Ready. Create a session and scan the QR code with your phone.');
      await onConnected();
    } catch (error) {
      $('connection-error').textContent = explainNetworkError(error, 'Cannot reach the collector. Is "npm start" still running on the PC?');
    } finally {
      button.disabled = false;
    }
  }

  async function findUsbDevices() {
    const button = $('usb-check');
    button.disabled = true;
    try {
      const result = await local('/api/usb');
      $('usb-device').replaceChildren(...result.devices.map(device =>
        el('option', { value: device.serial, text: `${device.model || device.serial} · ${device.state}`, disabled: device.state !== 'device' })));
      $('usb-status').textContent = !result.available ? result.error
        : result.devices.length ? 'Phone found. Continue to connect.'
        : 'No phone found. Plug in the cable, unlock the phone and allow USB debugging.';
    } catch (error) {
      $('usb-status').textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  // ---------------------------------------------------------------- sessions + pairing
  function openCreate() {
    if (!ctx.config || !ctx.online) return openSettings();
    // Signed in on the PC but no phone route chosen yet.
    if (ctx.isLocalPage && ctx.config.server === location.origin && ctx.config.mode !== 'usb-adb') {
      toast('First choose how your phone connects.');
      return openSettings();
    }
    if (ctx.active?.recording) { toast('Stop & save the current session before creating another.'); return; }
    $('create-dialog').showModal();
  }

  async function createSession(event) {
    event.preventDefault();
    event.submitter.disabled = true;
    try {
      const mode = ctx.config.mode || 'tunnel';
      const session = await ctx.client().post('/api/sessions', { name: $('new-name').value, connection_mode: mode });
      // The phone page is served by the collector through the phone's route (tunnel or USB);
      // from a remote dashboard it is served by that site.
      pairURL = buildPairingLink(ctx.isLocalPage ? ctx.config.server : location.origin,
        { server: ctx.config.server, session: session.id, key: session.phone_key, mode });
      showPairing(mode);
      $('create-dialog').close();
      showPage('live');
      ctx.setActive(session);
      toast('Session created. Scan the QR code with your phone.');
    } catch (error) {
      toast(error.message);
    } finally {
      event.submitter.disabled = false;
    }
  }

  function showPairing(mode) {
    $('phone-link').value = pairURL;
    $('connection-mode-tag').textContent = mode === 'usb-adb' ? 'USB' : 'WI-FI';
    $('pairing-empty').hidden = true;
    $('pairing-ready').hidden = false;
    const box = $('qr-wrap');
    box.replaceChildren();
    try {
      const qr = window.qrcode();
      qr.addData(pairURL);
      qr.make();
      box.innerHTML = qr.createSvgTag(); // generated locally from our own link; no user HTML
    } catch {
      box.append(el('div', { className: 'qr-fallback', text: 'Link too long for a QR code. Use Copy or Share below.' }));
    }
  }

  async function copyLink() {
    try { await navigator.clipboard.writeText(pairURL); toast('Pairing link copied.'); }
    catch { $('phone-link').select(); toast('Select and copy the pairing link.'); }
  }

  async function shareLink() {
    try {
      if (navigator.share) await navigator.share({ title: 'Tepegoz phone capture', url: pairURL });
      else await navigator.clipboard.writeText(pairURL);
      toast('Pairing link ready to share.');
    } catch (error) {
      if (error.name !== 'AbortError') toast('Use Copy link to share this session.');
    }
  }

  // ---------------------------------------------------------------- wiring
  $('settings-btn').addEventListener('click', openSettings);
  $('connection-form').addEventListener('submit', connect);
  for (const input of document.querySelectorAll('input[name="route"]')) input.addEventListener('change', showRoute);
  $('tunnel-start').addEventListener('click', () => startTunnel().catch(error => { $('connection-error').textContent = error.message; }));
  $('usb-check').addEventListener('click', findUsbDevices);
  for (const id of ['new-session', 'pair-create', 'pair-shortcut']) $(id).addEventListener('click', openCreate);
  $('create-form').addEventListener('submit', createSession);
  $('copy-link').addEventListener('click', copyLink);
  $('share-link').addEventListener('click', shareLink);

  return { openSettings, openCreate };
}
