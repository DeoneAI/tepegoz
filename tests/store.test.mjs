import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { openStore, createSupabaseMirror, toRow } from '../pc/store.mjs';
import { parseTunnelUrl, createTunnel } from '../pc/tunnel.mjs';
import { EventEmitter } from 'node:events';

const manifest = (id, created, extra = {}) => ({ id, name: `s-${id.slice(0, 4)}`, created_at: created, status: 'recording', connection_mode: 'tunnel', ...extra });

test('SQLite index survives reopen, upserts by id and lists newest first', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'tepegoz-store-'));
  try {
    const a = 'a'.repeat(24), b = 'b'.repeat(24);
    let store = await openStore(dir, { mirror: null, log: () => {} });
    assert.equal(store.kind, 'sqlite');
    store.save(manifest(a, '2026-11-01T00:00:00Z'));
    store.save(manifest(b, '2026-11-02T00:00:00Z'));
    store.save(manifest(a, '2026-11-01T00:00:00Z', { status: 'completed', metrics: { frames: 12, samples: 340, duration_s: 9.5 } }));
    store.close();
    store = await openStore(dir, { mirror: null, log: () => {} });
    const list = store.list();
    assert.deepEqual(list.map(m => m.id), [b, a]);
    assert.equal(list[1].status, 'completed');
    store.close();
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('backfill indexes existing session folders from their manifest files', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'tepegoz-store-'));
  try {
    const id = 'c'.repeat(24);
    await mkdir(path.join(dir, id));
    await writeFile(path.join(dir, id, 'manifest.json'), JSON.stringify(manifest(id, '2026-10-30T00:00:00Z')));
    await mkdir(path.join(dir, 'not-a-session'));
    const store = await openStore(dir, { mirror: null, log: () => {} });
    assert.equal(await store.backfill(x => /^[a-f0-9]{24}$/.test(x)), 1);
    assert.equal(store.list()[0].id, id);
    store.close();
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('Supabase mirror is off without credentials and upserts metadata (not frames) with them', async () => {
  assert.equal(createSupabaseMirror({ url: '', key: '' }), null);
  const calls = [];
  const mirror = createSupabaseMirror({ url: 'https://x.supabase.co/', key: 'k', fetchImpl: async (u, o) => { calls.push([u, o]); return { ok: true }; } });
  await mirror.upsert(toRow(manifest('d'.repeat(24), '2026-11-03T00:00:00Z', { metrics: { frames: 3 } })));
  assert.equal(calls[0][0], 'https://x.supabase.co/rest/v1/sessions?on_conflict=id');
  assert.match(calls[0][1].headers.Prefer, /merge-duplicates/);
  const body = JSON.parse(calls[0][1].body);
  assert.equal(body.frames, 3); assert.equal(typeof body.manifest, 'object');
  const failing = createSupabaseMirror({ url: 'https://x', key: 'k', fetchImpl: async () => { throw new Error('offline'); }, log: () => {} });
  await failing.upsert(toRow(manifest('e'.repeat(24), '2026-11-03T00:00:00Z'))); // must not throw
});

test('tunnel reads the quick-tunnel address from cloudflared output and reports a missing binary', async () => {
  assert.equal(parseTunnelUrl('INF |  https://calm-river-12ab.trycloudflare.com  |'), 'https://calm-river-12ab.trycloudflare.com');
  assert.equal(parseTunnelUrl('no url here'), null);
  const child = Object.assign(new EventEmitter(), { stdout: new EventEmitter(), stderr: new EventEmitter(), kill() {} });
  const seen = [];
  const tunnel = createTunnel({ port: 8787, root: '.', spawnImpl: () => child });
  const started = tunnel.start(url => seen.push(url));
  child.stderr.emit('data', Buffer.from('Your quick Tunnel: https://a-b-c.trycloudflare.com'));
  assert.equal((await started).url, 'https://a-b-c.trycloudflare.com'); assert.deepEqual(seen, ['https://a-b-c.trycloudflare.com']);
  tunnel.stop();
  const missing = Object.assign(new EventEmitter(), { stdout: new EventEmitter(), stderr: new EventEmitter(), kill() {} });
  const t2 = createTunnel({ port: 8787, root: '.', spawnImpl: () => missing });
  const p2 = t2.start();
  missing.emit('error', Object.assign(new Error('spawn cloudflared ENOENT'), { code: 'ENOENT' }));
  assert.match((await p2).error, /not installed/);
});
