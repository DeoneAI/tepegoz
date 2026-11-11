// Phone capture controller: preflight → clock sync → camera + IMU + optional GNSS → upload → stop/drain.
// All browser APIs arrive through `env`, and all output goes through `view`, so the lifecycle
// is testable in Node (tests/phone.test.mjs) without a DOM.

import { finiteVector } from './sensors.js';
import { createTelemetryQueue } from './telemetry-queue.js';
import { bestEstimate, exchangeEstimate } from '../lib/timing.js';
import { fmt, stamp } from '../lib/format.js';

const AXES = 'phone_portrait_x_right_y_up_z_out';
const DEG_TO_RAD = Math.PI / 180;
const SESSION_ENDED = new Set([409, 410]);
const finiteRotation = r => r && ['alpha', 'beta', 'gamma'].every(k => typeof r[k] === 'number' && Number.isFinite(r[k]));

export const MESSAGES = {
  stopped: 'Phone capture stopped. Use Stop & save on the PC to finalize this session.',
  endedWith: n => `Session ended with ${n} telemetry samples not uploaded. Create a new session on the PC.`,
  queuedWith: n => `Capture stopped with ${n} telemetry samples still queued. Keep this page open, restore the connection, then tap Retry remaining telemetry uploads before saving on the PC.`,
};

/**
 * @param transport { post(route, json) → Promise<json>, upload(route, blob, headers) → Promise }
 *                  Routes are relative to /api/sessions/<id>.
 * @param view      UI sink: status, startButton, stopButton, captureState, lockOptions, stats, sensorResult, options
 * @param env       { now, timers, media, motion, geolocation, wakeLock, createGyroscope, probeSensors, device }
 */
// Several JPEGs may be uploading at once, so one slow round trip no longer caps the frame rate
// (over the internet each upload takes several hundred ms). The PC commits them in order using `prev_frame_index`.
export const MAX_FRAMES_IN_FLIGHT = 8;

export function createCapture({ sessionId, mode, transport, view, env, maxInFlight = MAX_FRAMES_IN_FLIGHT }) {
  const now = env.now;
  const timers = env.timers;
  let running = false;
  let starting = false;
  let capabilities = null;
  let preflightAccepted = false;
  let clock = null;
  let stats = freshStats();
  let frameIndex = 0;
  let lastFrameAt = -Infinity;
  const framesInFlight = new Set();
  let lastSentIndex = -1;
  let handles = {};

  const queue = createTelemetryQueue({
    upload: (samples, counters) => transport.post('/samples', { samples, dropped_frames: stats.droppedFrames, ...counters }),
    onSessionEnded: async () => {
      await stop(false);
      view.status('Session ended. Remaining telemetry could not be uploaded. Create a new session on the PC.');
    },
    onRetryableError: () => view.status('Upload interrupted. Retrying a bounded telemetry queue…'),
  });

  function freshStats() {
    return { startedAt: 0, storedFrames: 0, droppedFrames: 0, accelEvents: 0, accel: false, gyro: false, gnss: false };
  }

  // ---------------------------------------------------------------- telemetry
  function record(sensor_type, values, units, timestampMs, extra = {}) {
    if (!running) return;
    queue.push({ session_id: sessionId, sensor_type, timestamp_ns: stamp(timestampMs), frame_axes: AXES, values, units,
      quality: 'browser_accuracy_unavailable', ...extra });
  }

  function eventTime(event) {
    const t = event.timeStamp;
    return Number.isFinite(t) && t >= 0 && Math.abs(t - now()) < 60000 ? t : now();
  }

  function onMotion(event) {
    if (!running) return;
    const t = eventTime(event);
    const gravity = event.accelerationIncludingGravity;
    if (finiteVector(gravity)) {
      stats.accel = true; stats.accelEvents++;
      record('accelerometer', { x: gravity.x, y: gravity.y, z: gravity.z }, 'm_s2', t, { timestamp_source: 'browser_event_time', includes_gravity: true });
    }
    if (finiteVector(event.acceleration)) {
      const a = event.acceleration;
      record('linear_acceleration', { x: a.x, y: a.y, z: a.z }, 'm_s2', t, { timestamp_source: 'browser_event_time', includes_gravity: false });
    }
    const r = event.rotationRate;
    if (finiteRotation(r)) {
      stats.gyro = true;
      handles.gyroscope?.stop(); handles.gyroscope = null; // DeviceMotion gyro wins over the Generic Sensor fallback
      // Browser rotation rate (deg/s) → phone axes in rad/s: X←beta, Y←gamma, Z←alpha.
      record('gyroscope', { x: r.beta * DEG_TO_RAD, y: r.gamma * DEG_TO_RAD, z: r.alpha * DEG_TO_RAD }, 'rad_s', t, { timestamp_source: 'browser_event_time' });
    }
  }

  function startGenericGyroscope() {
    if (capabilities?.sensors.gyroscope.source !== 'GenericSensor.Gyroscope' || !env.createGyroscope) return;
    try {
      const gyro = env.createGyroscope({ frequency: 60 });
      gyro.addEventListener('reading', () => {
        if (!running || !finiteVector(gyro)) return;
        stats.gyro = true;
        record('gyroscope', { x: gyro.x, y: gyro.y, z: gyro.z }, 'rad_s', gyro.timestamp ?? now(), { timestamp_source: 'generic_sensor_monotonic' });
      });
      gyro.addEventListener('error', () => view.status('Gyroscope access was lost. Existing records are kept; check sensor permissions.'));
      gyro.start();
      handles.gyroscope = gyro;
    } catch (error) {
      view.status('Gyroscope could not start: ' + error.message);
    }
  }

  function startGnss() {
    handles.gnss = env.geolocation.watchPosition(position => {
      stats.gnss = true;
      const c = position.coords;
      const t = now() - (Date.now() - position.timestamp); // wall-clock fix time → monotonic estimate
      record('gnss', { latitude: c.latitude, longitude: c.longitude, altitude: c.altitude, speed: c.speed, heading: c.heading }, 'deg_m_mps', Math.max(0, t), {
        accuracy_m: c.accuracy, altitude_accuracy_m: c.altitudeAccuracy, frame_axes: 'wgs84_geodetic',
        quality: 'browser_geolocation_accuracy', timestamp_source: 'geolocation_wall_to_monotonic_estimate' });
    }, error => view.status('GPS unavailable: ' + error.message), { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 });
  }

  // ---------------------------------------------------------------- clock
  async function syncClock() {
    const estimates = [];
    for (let i = 0; i < 5; i++) {
      const t0 = now();
      const reply = await transport.post('/sync', { t0 });
      if (!reply.recording) {
        await stop();
        view.status('The session was stopped on the PC. Create a new session to continue.');
        return;
      }
      estimates.push(exchangeEstimate({ t0, t1: reply.t1, t2: reply.t2, t3: now() }));
    }
    clock = bestEstimate(estimates);
    await transport.post('/clock', { ...clock, method: 'minimum RTT of 5 NTP-style exchanges', samples: estimates });
  }

  // ---------------------------------------------------------------- frames
  async function uploadFrame(index, prev, meta) {
    try {
      const { width } = view.options();
      const image = await env.media.encode(width);
      const hasCapture = typeof meta.captureTime === 'number';
      const hasPresentation = typeof meta.presentationTime === 'number';
      const t = hasCapture ? meta.captureTime : hasPresentation ? meta.presentationTime : now();
      const payload = {
        frame_index: index, prev_frame_index: prev, timestamp_ns: stamp(t),
        timestamp_source: hasCapture ? 'captureTime' : hasPresentation ? 'presentationTime_estimate' : 'callback_estimate',
        media_time_s: meta.mediaTime ?? image.mediaTime, width: image.width, height: image.height,
      };
      await transport.upload('/frame', image.blob, { 'Content-Type': 'image/jpeg', 'X-Frame-Meta': JSON.stringify(payload) });
      stats.storedFrames++;
    } catch (error) {
      stats.droppedFrames++;
      if (SESSION_ENDED.has(error.status)) {
        await stop(false);
        view.status('Recording ended on the PC.');
      } else {
        view.status('Frame upload failed. Check your connection; skipped frames are counted.');
      }
    }
  }

  /** Video-frame callback. Encodes at most one JPEG at a time; overload skips are counted. */
  function frame(timestamp, meta = {}) {
    if (!running) return;
    env.media.scheduleNext(frame);
    const interval = 1000 / view.options().fps;
    if (timestamp - lastFrameAt < interval - 2) return;
    lastFrameAt = timestamp;
    const index = frameIndex++;
    if (framesInFlight.size >= maxInFlight) { stats.droppedFrames++; return; }
    const prev = lastSentIndex;
    lastSentIndex = index;
    const job = uploadFrame(index, prev, meta).finally(() => framesInFlight.delete(job));
    framesInFlight.add(job);
    return job;
  }

  // ---------------------------------------------------------------- lifecycle
  function begin() {
    running = true;
    stats = freshStats();
    stats.startedAt = now();
    handles.flush = timers.setInterval(() => queue.flush(), 100);
    handles.sync = timers.setInterval(() => syncClock().catch(() => view.status('Clock resynchronization failed; last estimate retained.')), 15000);
    handles.stats = timers.setInterval(reportStats, 1000);
  }

  function reportStats() {
    const elapsed = Math.max(0.001, (now() - stats.startedAt) / 1000);
    const state = present => (present ? 'receiving real samples' : elapsed < 4 ? 'checking…' : 'unavailable / permission blocked');
    view.stats({
      frames: stats.storedFrames, dropped: stats.droppedFrames, accelHz: fmt(stats.accelEvents / elapsed) + ' Hz',
      sensors: [['Accelerometer', state(stats.accel)], ['Gyroscope', state(stats.gyro)], ['GNSS', state(stats.gnss)]],
    });
    if (elapsed > 4 && !stats.gyro) view.status('Capture active. Gyroscope is unavailable or blocked: the full Week 01 IMU gate is not yet satisfied.');
  }

  async function checkSensors() {
    if (running) return;
    view.status('Checking real sensor readings before recording…');
    try {
      capabilities = await env.probeSensors();
      preflightAccepted = false;
      view.sensorResult(capabilities);
      view.status('Sensor check complete. Review the result before starting capture.');
    } catch (error) {
      view.status('Sensor check could not finish: ' + error.message);
    }
  }

  async function start() {
    if (running || starting) return;
    starting = true;
    view.startButton({ disabled: true });
    try {
      if (!capabilities) { await checkSensors(); return; }
      if (capabilities.sensors.gyroscope.state !== 'available' && !preflightAccepted) { view.sensorResult(capabilities); return; }
      view.status('Checking the collector and synchronizing clocks…');
      await syncClock();
      if (!clock) throw new Error('Session is not recording. Create a fresh session.');
      const options = view.options();
      const camera = await env.media.open(options.width);
      await transport.post('/device', { ...env.device(), camera, requested_jpeg_fps: options.fps, requested_width: options.width,
        client: 'browser-v3', connection_mode: mode, capabilities, sensor_accuracy: 'not exposed by DeviceMotionEvent' });
      begin();
      view.captureStarted(camera);
      env.motion.add(onMotion);
      startGenericGyroscope();
      handles.wake = await env.wakeLock();
      if (options.gnss && env.geolocation) startGnss();
      env.media.scheduleNext(frame);
      view.status('Streaming to your PC. Keep this page visible.');
    } catch (error) {
      await stop(false);
      view.status(error.message === 'Failed to fetch' ? 'Collector unreachable. Check tunnel, PC server, and allowed origin.' : error.message);
    } finally {
      starting = false;
      view.startButton({ disabled: false });
    }
  }

  function releaseDevices() {
    running = false;
    try { handles.gyroscope?.stop(); } catch { /* already stopped */ }
    env.motion.remove(onMotion);
    for (const key of ['flush', 'sync', 'stats']) timers.clearInterval(handles[key]);
    if (handles.gnss !== undefined && handles.gnss !== null) env.geolocation.clearWatch(handles.gnss);
    env.media.close();
    handles.wake?.release?.().catch?.(() => {});
    handles = {};
  }

  /** Stop capture. With flushPending, wait for the last JPEG and drain queued telemetry (bounded). */
  async function stop(flushPending = true) {
    releaseDevices();
    if (flushPending) {
      view.stopButton({ disabled: true });
      view.status('Stopping capture and finishing frame and telemetry uploads…');
      await Promise.allSettled([...framesInFlight]); // the JPEGs drawn before the stream was released
      await queue.drain(4);
    }
    view.stopButton({ hidden: !queue.pending || queue.ended, disabled: false, label: 'Retry remaining telemetry uploads' });
    view.startButton({ hidden: false, disabled: true, label: 'Open a new session to capture again' });
    view.captureState('● STOPPED');
    return !queue.pending;
  }

  async function stopFromUser() {
    const complete = await stop();
    view.status(complete ? MESSAGES.stopped : queue.ended ? MESSAGES.endedWith(queue.pending) : MESSAGES.queuedWith(queue.pending));
  }

  return {
    start, stop, stopFromUser, checkSensors, frame, begin, record,
    acceptPreflight() { preflightAccepted = true; return start(); },
    onVisibility(hidden) {
      if (hidden && running) view.status('Page hidden: capture may pause. Return to this page to continue.');
      else if (running) env.wakeLock().then(lock => { handles.wake = lock; });
    },
    get running() { return running; },
    get pending() { return queue.pending; },
    flush: () => queue.flush(),
  };
}
