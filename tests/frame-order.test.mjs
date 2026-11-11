import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { Readable } from 'node:stream';

const token = 'test-only-collector-key';
test('frames that overtake each other on the network are stored in order and none is rejected', async t => {
  const data = await mkdtemp(path.join(tmpdir(), 'tepegoz-order-'));
  Object.assign(process.env, { SENSORLINK_TEST: '1', DATA_DIR: data, COLLECTOR_TOKEN: token, SUPABASE_URL: '', SUPABASE_SERVICE_ROLE_KEY: '' });
  const { server, closeStore } = await import('../pc/server.mjs');
  t.after(async () => { server.close(); closeStore(); await rm(data, { recursive: true, force: true }); });
  const req = async (route, key, method = 'GET', value, headers = {}) => {
    const bytes = value === undefined ? Buffer.alloc(0) : Buffer.isBuffer(value) ? value : Buffer.from(JSON.stringify(value));
    const input = Readable.from(bytes.length ? [bytes] : []); input.url = route; input.method = method; input.headers = { authorization: `Bearer ${key}`, ...headers };
    const out = { headers: {}, status: 200, bytes: Buffer.alloc(0), headersSent: false, setHeader() {}, writeHead(code) { this.status = code; this.headersSent = true; }, end(b) { this.bytes = Buffer.from(b || ''); }, destroy() {} };
    await server.listeners('request')[0](input, out);
    return { status: out.status, json: () => JSON.parse(out.bytes.toString()) };
  };
  const session = (await req('/api/sessions', token, 'POST', { name: 'order' })).json();
  const jpeg = Buffer.from([0xff, 0xd8, 1, 2, 3, 0xff, 0xd9]);
  const frame = (index, prev) => req(`/api/sessions/${session.id}/frame`, session.phone_key, 'POST', jpeg,
    { 'x-frame-meta': JSON.stringify({ frame_index: index, prev_frame_index: prev, timestamp_ns: String(index * 66_000_000), timestamp_source: 'callback_estimate', width: 640, height: 360 }) });
  // Frame 2 and 3 reach the collector before frame 1 and 0 (as on a jittery connection).
  const late = (ms, p) => new Promise(r => setTimeout(r, ms)).then(() => p());
  const results = await Promise.all([late(60, () => frame(0, -1)), late(40, () => frame(1, 0)), late(10, () => frame(2, 1)), late(0, () => frame(3, 2))]);
  assert.deepEqual(results.map(r => r.status), [200, 200, 200, 200]);
  const replay = (await req(`/api/sessions/${session.id}/replay`, token)).json();
  assert.deepEqual(replay.frames.map(f => f.frame_index), [0, 1, 2, 3]);
  // A frame whose predecessor never arrives is still stored after the short wait.
  assert.equal((await frame(6, 5)).status, 200);
  // The phone (pairing key) may finalize its own session, and a wrong key may not.
  assert.equal((await req(`/api/sessions/${session.id}/stop`, 'wrong-key', 'POST', {})).status, 401);
  const stopped = await req(`/api/sessions/${session.id}/stop`, session.phone_key, 'POST', {});
  assert.equal(stopped.status, 200);
  assert.equal(stopped.json().recording, false);
});
