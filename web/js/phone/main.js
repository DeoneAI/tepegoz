// Phone page entry point: binds the DOM and browser APIs to the capture controller.

import { $, el, enhanceDialogs } from '../lib/dom.js';
import { fmt } from '../lib/format.js';
import { createClient } from '../lib/http.js';
import { readPairing } from './pairing.js';
import { probeSensors } from './sensors.js';
import { createCapture } from './capture.js';

const pairing = readPairing({ location, storage: sessionStorage, history });
const status = text => { $('phone-status').textContent = text; };

// ------------------------------------------------------------------ camera
function createMedia(video) {
  const canvas = document.createElement('canvas');
  let stream = null;
  let handle = null;
  return {
    async open(width) {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: width }, height: { ideal: Math.round(width * 9 / 16) }, frameRate: { ideal: 30, max: 30 } },
        audio: false,
      });
      video.srcObject = stream;
      await video.play();
      return stream.getVideoTracks()[0].getSettings();
    },
    async encode(maxWidth) {
      canvas.width = Math.min(maxWidth, video.videoWidth);
      canvas.height = Math.round(canvas.width * video.videoHeight / video.videoWidth);
      canvas.getContext('2d', { alpha: false }).drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.75));
      if (!blob) throw new Error('JPEG encoding failed');
      return { blob, width: canvas.width, height: canvas.height, mediaTime: video.currentTime };
    },
    scheduleNext(callback) {
      handle = video.requestVideoFrameCallback ? video.requestVideoFrameCallback(callback) : requestAnimationFrame(t => callback(t));
    },
    close() {
      if (handle !== null) {
        if (video.cancelVideoFrameCallback) video.cancelVideoFrameCallback(handle);
        else cancelAnimationFrame(handle);
        handle = null;
      }
      stream?.getTracks().forEach(track => track.stop());
      stream = null;
      video.srcObject = null;
    },
  };
}

// ------------------------------------------------------------------ view
const view = {
  status,
  startButton({ hidden, disabled, label } = {}) {
    const button = $('start-capture');
    if (hidden !== undefined) button.hidden = hidden;
    if (disabled !== undefined) button.disabled = disabled || !pairing || !isSecureContext;
    if (label) button.textContent = label;
  },
  stopButton({ hidden, disabled, label } = {}) {
    const button = $('stop-capture');
    if (hidden !== undefined) button.hidden = hidden;
    if (disabled !== undefined) button.disabled = disabled;
    if (label) button.textContent = label;
  },
  captureState: text => { $('phone-state').textContent = text; },
  options: () => ({ fps: Number($('target-fps').value), width: Number($('target-width').value), gnss: $('enable-gnss').checked }),
  captureStarted(camera) {
    $('phone-camera-empty').hidden = true;
    $('start-capture').hidden = true;
    $('stop-capture').hidden = false;
    for (const id of ['target-fps', 'target-width', 'enable-gnss', 'check-sensors']) $(id).disabled = true;
    $('phone-state').textContent = '● LIVE · SENDING';
    $('phone-resolution').textContent = `${camera.width}×${camera.height}`;
  },
  stats({ frames, dropped, accelHz, sensors }) {
    $('phone-frames').textContent = frames;
    $('phone-drops').textContent = dropped;
    $('phone-hz').textContent = accelHz;
    $('phone-capabilities').replaceChildren(...sensors.map(([name, state]) =>
      el('li', { className: state.startsWith('receiving') ? 'ok' : '' }, el('span', { text: name }), el('b', { text: state }))));
  },
  sensorResult(capabilities) {
    const rows = Object.entries(capabilities.sensors).map(([name, value]) =>
      el('li', { className: value.state === 'available' ? 'ok' : 'warn' },
        el('span', { text: name.replace('_', ' ') }),
        el('b', { text: `${value.state} · ${fmt(value.measured_hz)} Hz` }),
        el('small', { text: value.source })));
    $('sensor-check-results').replaceChildren(...rows);
    const available = capabilities.sensors.gyroscope.state === 'available';
    $('sensor-dialog-title').textContent = available ? 'Sensor check complete' : 'Gyroscope data is not available';
    $('sensor-check-warning').textContent = available
      ? 'Real gyro samples were observed. Achieved capture rates are measured again during recording.'
      : 'This browser returned no usable gyro samples. The sensor may be absent, blocked, or not exposed by this browser. Check Motion sensors permission or another browser. Continuing records available sensors; it does not pass the full IMU gate.';
    $('sensor-check-warning').classList.toggle('warn', !available);
    $('sensor-continue').textContent = available ? 'Continue to capture' : 'Continue with available sensors';
    if (!$('sensor-dialog').open) $('sensor-dialog').showModal();
  },
};

// ------------------------------------------------------------------ wiring
enhanceDialogs();
if (!isSecureContext) {
  status('HTTPS is required for camera and sensor access.');
  view.startButton({ disabled: true });
} else if (!pairing) {
  status('Open a fresh pairing link from the PC dashboard to start.');
  view.startButton({ disabled: true });
} else {
  status('Paired link ready. Check sensors, then start capture.');
  $('paired-session').textContent = `${pairing.mode === 'usb-adb' ? 'USB / ADB' : 'HTTPS'} · ${pairing.session.slice(0, 8)}…`;
  const client = createClient(pairing.server, pairing.key);
  const base = `/api/sessions/${pairing.session}`;
  const capture = createCapture({
    sessionId: pairing.session,
    mode: pairing.mode,
    transport: { post: (route, value) => client.post(base + route, value), upload: (route, body, headers) => client.upload(base + route, body, headers) },
    view,
    env: {
      now: () => performance.now(),
      timers: window,
      media: createMedia($('phone-video')),
      motion: { add: fn => window.addEventListener('devicemotion', fn), remove: fn => window.removeEventListener('devicemotion', fn) },
      geolocation: navigator.geolocation,
      createGyroscope: window.Gyroscope ? options => new window.Gyroscope(options) : null,
      wakeLock: async () => { try { return 'wakeLock' in navigator ? await navigator.wakeLock.request('screen') : null; } catch { return null; } },
      probeSensors: () => probeSensors(),
      device: () => ({ user_agent: navigator.userAgent, platform: navigator.platform, clock_origin_ms: performance.timeOrigin }),
    },
  });
  $('start-capture').addEventListener('click', () => capture.start());
  $('stop-capture').addEventListener('click', () => capture.stopFromUser());
  $('check-sensors').addEventListener('click', async event => {
    event.currentTarget.disabled = true;
    await capture.checkSensors();
    event.currentTarget.disabled = capture.running;
  });
  $('sensor-continue').addEventListener('click', () => { $('sensor-dialog').close(); capture.acceptPreflight(); });
  document.addEventListener('visibilitychange', () => capture.onVisibility(document.hidden));
  window.addEventListener('pagehide', () => { if (capture.running) capture.stop(false); });
}
