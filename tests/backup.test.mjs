import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { pack, unpack, createBackup } from '../pc/backup.mjs';
import { openStore } from '../pc/store.mjs';

async function sampleSession() {
  const dir = await mkdtemp(path.join(tmpdir(), 'tepegoz-bk-'));
  await mkdir(path.join(dir, 'frames'));
  await writeFile(path.join(dir, 'manifest.json'), '{"id":"x"}');
  await writeFile(path.join(dir, 'frames.jsonl'), 'a\nb\n');
  await writeFile(path.join(dir, 'frames', '00000001.jpg'), Buffer.from([0xff, 0xd8, 10, 10, 0xff, 0xd9]));
  await writeFile(path.join(dir, 'frames', '00000002.jpg'), Buffer.from([0xff, 0xd8, 0, 0xff, 0xd9]));
  return dir;
}

test('a session folder survives pack and unpack byte for byte, including binary frames', async () => {
  const src = await sampleSession(), out = await mkdtemp(path.join(tmpdir(), 'tepegoz-bk-out-'));
  try {
    const parts = await pack(src);
    assert.equal(parts.length, 1);
    assert.equal(await unpack(parts[0], out), 4);
    for (const f of ['manifest.json', 'frames.jsonl', 'frames/00000001.jpg', 'frames/00000002.jpg']) {
      assert.deepEqual(await readFile(path.join(out, f)), await readFile(path.join(src, f)));
    }
  } finally { await rm(src, { recursive: true, force: true }); await rm(out, { recursive: true, force: true }); }
});

test('large sessions are split into several parts that restore completely', async () => {
  const src = await sampleSession(), out = await mkdtemp(path.join(tmpdir(), 'tepegoz-bk-out-'));
  try {
    const parts = await pack(src, 5);
    assert.ok(parts.length > 1);
    let files = 0;
    for (const part of parts) files += await unpack(part, out);
    assert.equal(files, 4);
  } finally { await rm(src, { recursive: true, force: true }); await rm(out, { recursive: true, force: true }); }
});

test('unpack refuses paths that could escape the session folder', async () => {
  const out = await mkdtemp(path.join(tmpdir(), 'tepegoz-bk-out-'));
  try {
    for (const p of ['../evil', '/abs', 'a/../../b', 'C:/x']) {
      const bad = Buffer.concat([Buffer.from(`${JSON.stringify({ p, n: 1 })}\n`), Buffer.from('x')]);
      await assert.rejects(unpack(bad, out), /unsafe path/);
    }
    await assert.rejects(unpack(Buffer.concat([Buffer.from('{"p":"ok.txt","n":9}\n'), Buffer.from('x')]), out), /truncated/);
  } finally { await rm(out, { recursive: true, force: true }); }
});

test('upload then restore through Supabase Storage (fake server) returns the same files', async () => {
  const src = await sampleSession(), out = await mkdtemp(path.join(tmpdir(), 'tepegoz-bk-out-'));
  const objects = new Map(); const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push(`${options.method || 'GET'} ${url.replace('https://p.supabase.co', '')}`);
    if (url.endsWith('/storage/v1/bucket')) return new Response('{}', { status: 200 });
    if (options.method === 'POST') { objects.set(url, Buffer.from(options.body)); return new Response('{}', { status: 200 }); }
    return objects.has(url) ? new Response(objects.get(url)) : new Response('missing', { status: 404 });
  };
  try {
    const backup = createBackup({ url: 'https://p.supabase.co', key: 'sb_secret_x', fetchImpl, log: () => {} });
    assert.equal(await backup.upload('0123456789abcdef01234567', src), true);
    assert.ok(calls.every(c => !c.includes('Authorization')));
    assert.equal(await backup.restore('0123456789abcdef01234567', out), 4);
    assert.deepEqual(await readFile(path.join(out, 'frames', '00000001.jpg')), await readFile(path.join(src, 'frames', '00000001.jpg')));
    assert.equal(await backup.restore('ffffffffffffffffffffffff', out), 0, 'no backup means nothing restored, no throw');
    assert.equal(createBackup({ url: '', key: '' }), null, 'backup is off without Supabase settings');
  } finally { await rm(src, { recursive: true, force: true }); await rm(out, { recursive: true, force: true }); }
});

test('the session list is rebuilt from Supabase after the temporary disk is wiped', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'tepegoz-bk-db-'));
  const manifest = { id: 'aaaaaaaaaaaaaaaaaaaaaaaa', name: 'Cloud run', created_at: '2026-11-11T10:00:00Z', status: 'completed', metrics: { frames: 5 } };
  const mirror = { upsert: async () => {}, list: async () => [manifest, { id: 'not-a-session' }] };
  const store = await openStore(dir, { mirror, log: () => {} });
  try {
    assert.equal(await store.restoreFromMirror(id => /^[a-f0-9]{24}$/.test(id)), 1);
    assert.equal(store.list()[0].name, 'Cloud run');
    assert.equal(await store.restoreFromMirror(id => /^[a-f0-9]{24}$/.test(id)), 0, 'already known sessions are not added twice');
  } finally { store.close(); await rm(dir, { recursive: true, force: true }); }
});
