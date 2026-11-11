// Live acquisition page: session status polling, latest camera frame, metrics, IMU chart, inventory.

import { $, el, setText, toggle } from '../lib/dom.js';
import { duration, fmt, frameLabel, nsToSeconds } from '../lib/format.js';
import { drawTraces } from './chart.js';

const SENSORS = [
  ['accelerometer', 'Accelerometer', 'm/s²'],
  ['linear_acceleration', 'Linear acceleration', 'm/s²'],
  ['gyroscope', 'Gyroscope', 'rad/s'],
  ['gnss', 'GNSS', 'deg, m, m/s'],
];
const UNITS = { accelerometer: ['m/s²', 'including gravity'], gyroscope: ['rad/s', 'phone axes'] };

export function createLivePage(ctx, { toast, openReplay }) {
  let statusBusy = false;
  let imageBusy = false;
  let lastFrame = -1;
  let frameURL = null;

  function setStep(id, done) {
    toggle(id, 'done', done);
  }

  function renderOnline() {
    const pill = $('collector-status');
    pill.classList.toggle('online', ctx.online);
    pill.lastElementChild.textContent = ctx.online ? 'Collector online' : 'Collector offline';
    setStep('step-server', ctx.online);
  }

  function render() {
    const s = ctx.active;
    if (!s) return;
    const m = s.metrics || {};
    const live = Boolean(m.phone_connected);
    setText('session-name', s.name);
    setText('session-id', s.id);
    setText('session-duration', duration(m.duration_s));
    setText('fps', m.frames ? fmt(m.fps) : '—');
    setText('hz', m.samples ? fmt(m.imu_hz) : '—');
    setText('latency', fmt(m.latency_p95_ms, 0));
    setText('gaps', m.sequence_gaps ?? '—');
    setText('dropped', m.phone_dropped_frames ?? 0);

    for (const id of ['session-dot', 'device-dot']) toggle(id, 'online', live);
    toggle('record-dot', 'online', s.recording && live);
    setText('record-label', s.recording ? (live ? 'Recording to PC' : 'Waiting for phone') : 'Saved to PC');
    setText('feed-status', !s.recording ? '● SESSION SAVED' : live ? '● LIVE · RECORDING' : '● AWAITING DEVICE');
    $('stop-session').disabled = !s.recording;
    $('replay-current').disabled = !m.frames;
    setStep('step-phone', live);
    setStep('step-stream', m.samples && m.frames);

    setText('clock-offset', fmt(m.clock_offset_ms, 2) + ' ms');
    setText('clock-rtt', fmt(m.clock_rtt_ms, 1) + ' ms');
    setText('clock-error', '± ' + fmt(m.clock_uncertainty_ms, 1) + ' ms');
    setText('clock-drift', fmt(m.clock_drift_ppm, 1) + ' ppm');
    setText('sync-tag', s.clock ? 'ESTIMATED' : 'UNSYNCED');
    toggle('sync-tag', 'accent', s.clock);

    const ua = s.device?.user_agent;
    setText('device-name', ua ? deviceLabel(ua) : 'No device yet');
    setText('device-detail', s.device ? `${s.device.connection_mode === 'usb-adb' ? 'USB / ADB' : 'HTTPS'} · ${s.device.client || 'browser'}` : 'Pair a phone to begin');

    const sample = s.latest?.[ctx.sensor];
    for (const axis of ['x', 'y', 'z']) setText('axis-' + axis, fmt(sample?.values?.[axis], 3));
    setText('sensor-status', sample ? `${fmt(m.per_sensor_hz?.[ctx.sensor])} Hz · browser accuracy unknown` : 'No measurements / sensor may be unavailable');
    const traces = s.telemetry?.filter(x => x.sensor_type === ctx.sensor).slice(-150) || [];
    $('chart-empty').hidden = traces.length > 0;
    drawTraces($('imu-chart'), traces);

    renderInventory(s);
    if (s.last_frame) {
      const f = s.last_frame;
      setText('frame-number', frameLabel(f.frame_index));
      setText('frame-time', `${nsToSeconds(f.timestamp_ns)} s · ${f.timestamp_source}`);
      setText('frame-size', `${f.width} × ${f.height}`);
      setText('camera-format', `${f.width} × ${f.height} / JPEG`);
    }
  }

  function renderInventory(s) {
    setText('device-route', ctx.config?.mode === 'usb-adb' ? 'USB / ADB' : 'HTTPS');
    $('sensor-inventory-rows').replaceChildren(...SENSORS.map(([key, label, unit]) => {
      const state = s.device?.capabilities?.sensors?.[key]?.state || 'not checked';
      return el('tr', {},
        el('td', { text: `${label} / ${unit}` }),
        el('td', {}, el('span', { className: `state ${state === 'available' ? 'ok' : state === 'not checked' ? '' : 'warn'}`, text: state })),
        el('td', { text: fmt(s.metrics?.per_sensor_hz?.[key], 1) }),
        el('td', { text: s.metrics?.sensor_counts?.[key] ?? 0 }),
        el('td', { text: s.metrics?.sequence_gaps_by_stream?.[key] ?? 0 }));
    }));
    setText('sample-drop-summary', `Phone buffer drops: ${s.metrics?.phone_dropped_samples ?? 0} · Received sequence gaps: ${s.metrics?.sequence_gaps ?? 0}`);
    const gnss = s.latest?.gnss;
    setText('gnss-latest', gnss
      ? `GNSS: ${fmt(gnss.values.latitude, 6)}, ${fmt(gnss.values.longitude, 6)} · horizontal accuracy ${fmt(gnss.accuracy_m)} m`
      : 'GNSS: no received fix. Location is optional; no coordinate is invented.');
  }

  function selectSensor(name) {
    ctx.sensor = name;
    for (const button of document.querySelectorAll('[data-sensor]')) button.classList.toggle('active', button.dataset.sensor === name);
    const [unit, note] = UNITS[name];
    $('sensor-unit').replaceChildren(document.createTextNode(unit + ' '), el('span', { text: note }));
    render();
  }

  async function pollStatus() {
    if (!ctx.config || statusBusy) return;
    statusBusy = true;
    const connection = ctx.config;
    const sessionId = ctx.active?.id;
    try {
      const client = ctx.client();
      if (sessionId) {
        const s = await client.getJson(`/api/sessions/${sessionId}?sensor=${ctx.sensor}`);
        if (ctx.config !== connection || ctx.active?.id !== sessionId) return;
        if (s.metrics) { ctx.active = { ...ctx.active, ...s }; render(); }
      } else {
        await client.get('/api/sessions');
      }
      if (ctx.config === connection) ctx.setOnline(true);
    } catch {
      if (ctx.config === connection) ctx.setOnline(false);
    } finally {
      statusBusy = false;
    }
  }

  // Image polling is independent of status polling; the collector sends only the newest JPEG.
  async function pollImage() {
    if (!ctx.config || !ctx.active || imageBusy) return;
    imageBusy = true;
    const sessionId = ctx.active.id;
    const connection = ctx.config;
    let next = null;
    try {
      const response = await ctx.client().get(`/api/sessions/${sessionId}/live-image`, { headers: { 'X-After-Frame': String(lastFrame) } });
      if (response.status === 204) return;
      const meta = JSON.parse(response.headers.get('X-Frame-Meta'));
      next = URL.createObjectURL(await response.blob());
      const img = new Image();
      img.src = next;
      await img.decode();
      if (ctx.active?.id !== sessionId || ctx.config !== connection) return;
      const previous = frameURL;
      frameURL = next;
      next = null;
      $('live-image').src = frameURL;
      $('live-image').hidden = false;
      $('camera-empty').hidden = true;
      lastFrame = meta.frame_index;
      if (previous) URL.revokeObjectURL(previous);
    } catch {
      // Connectivity is reported by status polling; keep the last image on screen.
    } finally {
      if (next) URL.revokeObjectURL(next);
      imageBusy = false;
    }
  }

  async function stopSession() {
    if (!ctx.active) return;
    try {
      const saved = await ctx.client().post(`/api/sessions/${ctx.active.id}/stop`, {});
      ctx.setActive(saved);
      toast('Session saved to your PC. Replay is ready.');
    } catch (error) {
      toast(error.message);
    }
  }

  // ---------------------------------------------------------------- wiring
  for (const button of document.querySelectorAll('[data-sensor]')) button.addEventListener('click', () => selectSensor(button.dataset.sensor));
  $('stop-session').addEventListener('click', stopSession);
  $('replay-current').addEventListener('click', () => ctx.active && openReplay(ctx.active.id));
  window.addEventListener('resize', render);
  ctx.on(reason => {
    if (reason === 'online') renderOnline();
    if (reason === 'session') { lastFrame = -1; render(); }
    if (reason === 'connection') { lastFrame = -1; }
  });
  renderOnline();
  setInterval(pollStatus, 250);
  setInterval(pollImage, 80);
  pollStatus();

  return { render };
}

/** Short device label from a user agent string (display only). */
export function deviceLabel(userAgent) {
  const android = /Android [\d.]+; ([^;)]+)/.exec(userAgent);
  if (android) return android[1].replace(/ Build.*/, '').trim();
  if (/iPhone/.test(userAgent)) return 'iPhone';
  if (/iPad/.test(userAgent)) return 'iPad';
  return 'Browser client';
}
