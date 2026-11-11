// "Connect your phone" dialog + session creation and the pairing panel.
//
// On the collector PC (http://localhost:8787) the dashboard is already signed in by the start-up link,
// so the only choice left is the phone route:
//   Wi-Fi / mobile data → the collector starts a temporary HTTPS tunnel; the phone opens the page through it.
//   USB cable (Android) → ADB maps the phone's localhost:8787 to this PC.
// Another device opens the online dashboard through a one-click link made here ("View from another device").

import { $, el } from '../lib/dom.js';
import { explainNetworkError, request, validateServer } from '../lib/http.js';
import { buildPairingLink } from '../phone/pairing.js';

/** Accept an address typed without a scheme (abc.trycloudflare.com → https://abc.trycloudflare.com). */
export const withScheme = value => (value && !/^[a-z][a-z0-9+.-]*:\/\//i.test(value) ? `https://${value}` : value);

export function createConnection(ctx, { toast, onConnected, showPage }) {
  let pairURL = null;

  // A collector running in the cloud (Render) also serves this page; /health says so. Vercel answers 404.
  let cloudHere = false;
  if (!ctx.isLocalPage) fetch('/health').then(r => r.json()).then(h => { cloudHere = h?.cloud === true; }).catch(() => {});

  const route = () => document.querySelector('input[name="route"]:checked')?.value || 'wifi';
  const token = () => ctx.config?.token || '';
  const local = (path, options) => request(location.origin, token(), path, options).then(r => r.json());

  // ---------------------------------------------------------------- dialog
  function showRoute() {
    const r = route();
    $('wifi-setup').hidden = r !== 'wifi';
    $('usb-setup').hidden = r !== 'usb';
  }

  async function openSettings() {
    $('local-setup').hidden = !ctx.isLocalPage;
    $('hosted-note').hidden = ctx.isLocalPage || cloudHere; // the online copy explains why Wi-Fi/USB live on the PC
    $('cloud-note').hidden = !cloudHere;
    $('settings-title').textContent = ctx.isLocalPage ? 'Connect phone' : 'Connect to your collector';
    $('share-setup').hidden = !ctx.isLocalPage; // only this PC can hand out a remote link
    // On the collector PC the remote fields are never needed: hide them so they cannot be filled by mistake.
    $('remote-setup').hidden = ctx.isLocalPage;
    $('remote-setup').open = !ctx.isLocalPage && (!ctx.config || cloudHere);
    $('signed-in').hidden = !ctx.online;
    $('server-url').value = ctx.config && !ctx.isLocalPage ? ctx.config.server : cloudHere ? location.origin : '';
    $('connection-error').textContent = '';
    const usb = ctx.config?.mode === 'usb-adb';
    $(usb ? 'route-usb' : 'route-wifi').checked = true;
    showRoute();
    $('settings-dialog').showModal();
    if (ctx.isLocalPage) refreshTunnel();
  }

  function renderTunnel(status) {
    const box = $('tunnel-status');
    if (status.url) {
      box.className = 'route-status ok';
      box.textContent = `Running · ${status.url.replace('https://', '')}`;
      $('tunnel-start').hidden = true;
    } else if (status.starting) {
      box.className = 'route-status';
      box.textContent = 'Starting…';
    } else {
      box.className = status.error ? 'route-status warn' : 'route-status';
      box.textContent = status.error ? `${status.error} ${status.install_hint}` : 'Not started';
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
      const remote = !ctx.isLocalPage;
      if (remote) {
        const remoteToken = $('remote-token').value.trim() || ctx.config?.token;
        const address = $('server-url').value.trim() || ctx.config?.server;
        if (!address || !remoteToken) {
          $('remote-setup').open = true;
          throw new Error('Open the link from "View from another device" on the collector PC, or enter the address and token.');
        }
        config = { server: validateServer(withScheme(address)), token: remoteToken, mode: 'tunnel' };
        await request(config.server, config.token, '/api/sessions');
      } else {
        await request(location.origin, token(), '/api/sessions'); // is the collector running?
        if (route() === 'wifi') {
          config = { server: await startTunnel(), token: token(), mode: 'tunnel' };
        } else {
          const serial = $('usb-device').value;
          if (!serial) throw new Error('Click Find and choose your phone first.');
          const usb = await local('/api/usb', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ serial }), signal: AbortSignal.timeout(45000) });
          config = { server: usb.phone_origin, token: token(), mode: 'usb-adb' };
        }
      }
      ctx.saveConfig(config);
      ctx.active = null;
      ctx.emit('connection');
      ctx.setOnline(true);
      $('settings-dialog').close();
      toast(config.mode === 'usb-adb' ? 'USB connected. Create a session.' : 'Wi-Fi link ready. Create a session.');
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
        : result.devices.length ? 'Phone found.'
        : 'No phone found. Check the cable, unlock the phone and allow USB debugging.';
    } catch (error) {
      $('usb-status').textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  // ---------------------------------------------------------------- view from another device
  let shareURL = null;

  async function createShareLink() {
    const button = $('share-create');
    button.disabled = true;
    $('share-status').className = 'route-status';
    $('share-status').textContent = 'Starting the secure link…';
    try {
      const response = await request(location.origin, token(), '/api/remote-link',
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', signal: AbortSignal.timeout(40000) });
      const link = await response.json();
      shareURL = link.url;
      $('share-host').textContent = new URL(link.hosted).host;
      $('share-status').className = 'route-status ok';
      $('share-status').textContent = 'Link ready. Scan it or open it on the other device.';
      $('share-open').href = shareURL;
      const box = $('share-qr');
      box.replaceChildren();
      try {
        const qr = window.qrcode(0, 'L');
        qr.addData(shareURL);
        qr.make();
        box.innerHTML = qr.createSvgTag(3, 0); // generated locally from our own link; no user HTML
      } catch {
        box.append(el('div', { className: 'qr-fallback', text: 'Use Copy link.' }));
      }
      $('share-ready').hidden = false;
      refreshTunnel();
    } catch (error) {
      $('share-status').className = 'route-status warn';
      $('share-status').textContent = explainNetworkError(error, 'Cannot reach the collector. Is "npm start" still running?');
    } finally {
      button.disabled = false;
    }
  }

  async function copyShareLink() {
    try { await navigator.clipboard.writeText(shareURL); toast('Link copied. Open it on the other device.'); }
    catch { toast('Use Open, then copy the address from the new tab.'); }
  }

  // ---------------------------------------------------------------- sessions + pairing
  function openCreate() {
    if (!ctx.config || !ctx.online) return openSettings();
    // Signed in on the PC but no phone route chosen yet.
    if (ctx.isLocalPage && ctx.config.server === location.origin && ctx.config.mode !== 'usb-adb') {
      toast('Choose how the phone connects first.');
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
      toast('Session created. Scan the QR code with the phone.');
    } catch (error) {
      toast(error.message);
    } finally {
      event.submitter.disabled = false;
    }
  }

  function showPairing(mode) {
    $('phone-link').value = pairURL;
    $('connection-mode-tag').textContent = mode === 'usb-adb' ? 'USB' : 'Wi-Fi';
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
  $('share-create').addEventListener('click', createShareLink);
  $('share-copy').addEventListener('click', copyShareLink);
  for (const id of ['new-session', 'pair-create', 'pair-shortcut']) $(id).addEventListener('click', openCreate);
  $('create-form').addEventListener('submit', createSession);
  $('copy-link').addEventListener('click', copyLink);
  $('share-link').addEventListener('click', shareLink);

  return { openSettings, openCreate };
}
