import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { fmt, duration, frameLabel } from '../web/js/lib/format.js';
import { validateServer } from '../web/js/lib/http.js';
import { nearestSample, exchangeEstimate, bestEstimate, replayDueAt, sortReplay } from '../web/js/lib/timing.js';
import { readPairing, buildPairingLink, PAIRING_KEY } from '../web/js/phone/pairing.js';
import { progress } from '../web/js/dashboard/project.js';
import { deviceLabel } from '../web/js/dashboard/live.js';

test('format helpers never print NaN or Infinity', () => {
  assert.equal(fmt(NaN), '—'); assert.equal(fmt(Infinity), '—'); assert.equal(fmt('3'), '—'); assert.equal(fmt(1.234, 2), '1.23');
  assert.equal(duration(125.9), '02:05'); assert.equal(duration(undefined), '00:00'); assert.equal(frameLabel(42), '#000042');
});

test('collector origin must be HTTPS except localhost, and bare', () => {
  assert.equal(validateServer('https://abc.trycloudflare.com/'), 'https://abc.trycloudflare.com');
  assert.equal(validateServer('http://localhost:8787'), 'http://localhost:8787');
  assert.throws(() => validateServer('http://localhost:8787', { local: false }), /HTTPS/);
  assert.throws(() => validateServer('http://192.168.1.4:8787'), /HTTPS/);
  assert.throws(() => validateServer('https://x.test/path'), /origin/);
  assert.throws(() => validateServer('https://user:pw@x.test'), /origin/);
});

test('nearest sample respects the ±100 ms window and reports the signed delta', () => {
  const samples = [0, 50e6, 300e6].map((t, i) => ({ timestamp_ns: String(t), sequence_id: i }));
  assert.equal(nearestSample(samples, 60e6).sequence_id, 1);
  assert.equal(nearestSample(samples, 60e6).alignment_delta_ms, -10);
  assert.equal(nearestSample(samples, 180e6), null);
  assert.equal(nearestSample([], 0), null);
});

test('clock exchange picks the minimum round trip', () => {
  const a = exchangeEstimate({ t0: 0, t1: 105, t2: 106, t3: 10 });
  assert.equal(a.rtt_ms, 9); assert.equal(a.offset_ms, 100.5);
  const b = exchangeEstimate({ t0: 0, t1: 150, t2: 151, t3: 100 });
  assert.equal(bestEstimate([b, a]), a);
});

test('replay keeps original timing scaled by speed and groups samples by sensor', () => {
  assert.equal(replayDueAt({ wall: 1000, phone: 0, speed: 2 }, 500e6), 1250);
  const data = sortReplay({ frames: [{ timestamp_ns: '20', frame_index: 1 }, { timestamp_ns: '10', frame_index: 0 }],
    samples: [{ timestamp_ns: '5', sequence_id: 1, sensor_type: 'gyroscope' }, { timestamp_ns: '1', sequence_id: 0, sensor_type: 'gyroscope' }] });
  assert.deepEqual(data.frames.map(f => f.frame_index), [0, 1]);
  assert.deepEqual(data.groups.gyroscope.map(s => s.sequence_id), [0, 1]);
});

test('pairing links round-trip through the hash and invalid links are rejected', () => {
  const storage = new Map(); const store = { getItem: k => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, v) };
  const pairing = { server: 'https://collector.test', session: 'a'.repeat(24), key: 'b'.repeat(48), mode: 'tunnel' };
  const link = new URL(buildPairingLink('https://site.test', pairing));
  const location = { hash: link.hash, pathname: '/phone.html', hostname: 'site.test', origin: 'https://site.test' };
  assert.deepEqual(readPairing({ location, storage: store }), pairing);
  assert.ok(storage.get(PAIRING_KEY));
  const bad = { ...location, hash: '#' + new URLSearchParams({ ...pairing, key: 'short' }) };
  assert.equal(readPairing({ location: bad, storage: { getItem: () => null, setItem() {} } }), null);
});

test('project status data is complete and consistent', async () => {
  const status = JSON.parse(await readFile(new URL('../web/assets/project-status.json', import.meta.url), 'utf8'));
  assert.equal(status.milestones.length, 4);
  for (const m of status.milestones) assert.ok(['done', 'partial', 'pending', 'blocked'].includes(m.state), m.week);
  assert.ok(status.checklist.done <= status.checklist.total);
  assert.ok(progress(status) > 0 && progress(status) < 1);
  for (const row of status.benchmarks.rows) for (const col of status.benchmarks.columns) assert.ok(col.key in row, col.key);
});

test('device label is derived from the user agent, not hard-coded', () => {
  assert.equal(deviceLabel('Mozilla/5.0 (Linux; Android 14; SM-A155F Build/UP1A) Chrome/130'), 'SM-A155F');
  assert.equal(deviceLabel('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)'), 'iPhone');
});

test('every script and stylesheet referenced by the pages exists', async () => {
  for (const page of ['index.html', 'phone.html']) {
    const html = await readFile(new URL(`../web/${page}`, import.meta.url), 'utf8');
    for (const [, ref] of html.matchAll(/(?:src|href)="\/([^"#]+\.(?:js|css|svg))"/g)) {
      await readFile(new URL(`../web/${ref}`, import.meta.url));
    }
    assert.doesNotMatch(html, /style="/, `${page}: inline styles break the CSP`);
    assert.doesNotMatch(html, /<script>(?!<\/script>)/, `${page}: inline scripts break the CSP`);
  }
  const ids = async page => new Set([...(await readFile(new URL(`../web/${page}`, import.meta.url), 'utf8')).matchAll(/id="([^"]+)"/g)].map(m => m[1]));
  const dashboard = await ids('index.html');
  const phoneIds = await ids('phone.html');
  const check = async (dir, known) => {
    for (const file of await readdir(new URL(dir, import.meta.url))) {
      const source = await readFile(new URL(dir + file, import.meta.url), 'utf8');
      for (const [, id] of source.matchAll(/\$\('([a-z0-9-]+)'\)/g)) assert.ok(known.has(id), `${dir}${file} uses missing #${id}`);
      for (const [, id] of source.matchAll(/(?<![.\w])(?:setText|toggle)\('([a-z0-9-]+)'\s*,/g)) assert.ok(known.has(id), `${dir}${file} uses missing #${id}`);
    }
  };
  await check('../web/js/dashboard/', dashboard);
  await check('../web/js/phone/', phoneIds);
});
