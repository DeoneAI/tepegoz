import test from 'node:test';
import assert from 'node:assert/strict';
import { createCapture } from '../web/js/phone/capture.js';
import { createTelemetryQueue } from '../web/js/phone/telemetry-queue.js';

// Drive the real capture controller with a fake view, transport and browser environment.
function phone(post, upload = async () => ({})) {
  const ui = { status: '', stop: { hidden: true, disabled: false, label: '' }, start: { hidden: false, disabled: false, label: '' } };
  const view = {
    status: text => { ui.status = text; },
    stopButton: state => Object.assign(ui.stop, Object.fromEntries(Object.entries(state).filter(([, v]) => v !== undefined))),
    startButton: state => Object.assign(ui.start, Object.fromEntries(Object.entries(state).filter(([, v]) => v !== undefined))),
    captureState() {}, captureStarted() {}, stats() {}, sensorResult() {},
    options: () => ({ fps: 10, width: 640, gnss: false }),
  };
  const env = {
    now: () => 0,
    timers: { setInterval: () => 0, clearInterval() {} },
    media: { encode: async () => ({ blob: {}, width: 640, height: 360, mediaTime: 0 }), scheduleNext() {}, close() {} },
    motion: { add() {}, remove() {} },
    wakeLock: async () => null,
  };
  const capture = createCapture({ sessionId: '0123456789abcdef01234567', mode: 'tunnel', transport: { post: (route, value) => post(route, value), upload }, view, env });
  capture.begin();
  return { capture, ui, enqueue(value) { capture.record('accelerometer', { x: value, y: 0, z: 0 }, 'm_s2', value); } };
}
const deferred = () => { let resolve, reject; const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; }); return { promise, resolve, reject }; };
const tick = async (n = 2) => { for (let i = 0; i < n; i++) await Promise.resolve(); };

test('phone Stop waits for the final JPEG acknowledgment before inviting PC finalization', async () => {
  const ack = deferred(); let requested = false;
  const client = phone(async () => ({}), async () => { requested = true; await ack.promise; return {}; });
  const frame = client.capture.frame(100, { captureTime: 90, mediaTime: 0.1 });
  await tick(3); assert.equal(requested, true);
  let stopped = false; const stop = client.capture.stopFromUser().then(() => { stopped = true; });
  await tick(); assert.equal(stopped, false);
  ack.resolve(); await frame; await stop;
  assert.match(client.ui.status, /Use Stop & save/);
});

test('phone Stop waits for active upload then drains samples captured while it was in flight', async () => {
  const first = deferred(), calls = [];
  const client = phone(async (route, payload) => { calls.push(payload); if (calls.length === 1) await first.promise; return { accepted: payload.samples.length }; });
  client.enqueue(1); const upload = client.capture.flush(); await tick(1); client.enqueue(2);
  let stopped = false; const stop = client.capture.stopFromUser().then(() => { stopped = true; });
  await tick();
  assert.equal(stopped, false); assert.equal(calls.length, 1);
  first.resolve(); await upload; await stop;
  assert.deepEqual(calls.map(c => Array.from(c.samples, s => s.sequence_id)), [[0], [1]]);
  assert.equal(client.capture.pending, 0); assert.equal(client.ui.stop.hidden, true);
  assert.match(client.ui.status, /Use Stop & save/);
});

test('phone Stop retries an active failed batch without losing subsequent queued samples', async () => {
  const first = deferred(), calls = [];
  const client = phone(async (route, payload) => { calls.push(payload); if (calls.length === 1) await first.promise; return {}; });
  client.enqueue(1); const upload = client.capture.flush(); await tick(1); client.enqueue(2);
  const stop = client.capture.stopFromUser(); first.reject(new Error('Connection lost')); await upload; await stop;
  assert.deepEqual(calls.map(c => Array.from(c.samples, s => s.sequence_id)), [[0], [0, 1]]);
  assert.equal(client.capture.pending, 0);
});

test('phone Stop waits for an upload even when the waiting buffer is empty', async () => {
  const first = deferred(); const client = phone(() => first.promise);
  client.enqueue(1); client.capture.flush(); let stopped = false;
  const stop = client.capture.stop().then(() => { stopped = true; });
  await tick(); assert.equal(stopped, false);
  first.resolve({}); await stop; assert.equal(client.capture.pending, 0);
});

test('failed stop keeps telemetry and offers a retry before PC finalization', async () => {
  let offline = true, calls = 0;
  const client = phone(async () => { calls++; if (offline) throw new Error('Offline'); return {}; });
  client.enqueue(1); await client.capture.stopFromUser();
  assert.equal(calls, 4, 'stop retries are bounded'); assert.equal(client.capture.pending, 1);
  assert.equal(client.ui.stop.hidden, false); assert.equal(client.ui.stop.disabled, false);
  assert.match(client.ui.status, /1 telemetry samples still queued/);
  offline = false; await client.capture.stopFromUser();
  assert.equal(client.capture.pending, 0); assert.equal(client.ui.stop.hidden, true);
  assert.match(client.ui.status, /Use Stop & save/);
});

test('ended sessions report unsent telemetry instead of claiming a successful flush', async () => {
  const client = phone(async () => { throw Object.assign(new Error('Session stopped'), { status: 409 }); });
  client.enqueue(1); await client.capture.stopFromUser();
  assert.equal(client.capture.pending, 1); assert.equal(client.ui.stop.hidden, true);
  assert.match(client.ui.status, /1 telemetry samples not uploaded/);
});

test('samples recorded while stopped are ignored and frames are skipped while one is uploading', async () => {
  const gate = deferred(); let uploads = 0;
  const client = phone(async () => ({}), async () => { uploads++; await gate.promise; });
  const first = client.capture.frame(0, {});
  client.capture.frame(200, {}); // second frame while the first is still uploading → counted skip, no upload
  await tick(3); assert.equal(uploads, 1);
  gate.resolve(); await first;
  await client.capture.stop(false);
  client.enqueue(5); assert.equal(client.capture.pending, 0);
});

test('telemetry queue keeps a bounded buffer and counts dropped samples', async () => {
  const queue = createTelemetryQueue({ upload: async () => ({}), limit: 3 });
  for (let i = 0; i < 5; i++) queue.push({ sensor_type: 'gyroscope', value: i });
  assert.equal(queue.pending, 3); assert.equal(queue.dropped, 2);
});
