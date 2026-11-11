// Recording backup in Supabase Storage (free tier), so a collector on a host with a temporary disk
// (for example Render's free plan) keeps finished sessions across restarts and sleep.
//
// A session folder is packed into a few parts (<= 40 MB each, under Supabase's 50 MB free limit) and uploaded to
// <bucket>/<session id>/part-0000.bin … plus index.json. Restore downloads the parts and writes the files back.
// Failures are logged and never block recording.
import path from 'node:path';
import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises';

const PART_BYTES = 40 * 1024 * 1024;

/** All files under dir as relative POSIX paths. */
async function walk(dir, prefix = '') {
  const files = [];
  for (const entry of await readdir(path.join(dir, prefix), { withFileTypes: true })) {
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) files.push(...await walk(dir, rel));
    else if (entry.isFile()) files.push(rel);
  }
  return files;
}

/** Pack files as repeated "<json header>\n<bytes>", starting a new part when one reaches PART_BYTES. */
export async function pack(dir, limit = PART_BYTES) {
  const parts = [];
  let current = [], size = 0;
  for (const rel of (await walk(dir)).sort()) {
    const bytes = await readFile(path.join(dir, rel));
    const entry = [Buffer.from(`${JSON.stringify({ p: rel, n: bytes.length })}\n`), bytes];
    if (size > 0 && size + bytes.length > limit) { parts.push(Buffer.concat(current)); current = []; size = 0; }
    current.push(...entry); size += bytes.length;
  }
  if (current.length) parts.push(Buffer.concat(current));
  return parts;
}

/** Write the files of one packed part below dir. Refuses paths that could leave dir. */
export async function unpack(buffer, dir) {
  let offset = 0, count = 0;
  while (offset < buffer.length) {
    const end = buffer.indexOf(10, offset);
    if (end < 0) throw new Error('Backup part is corrupt');
    const { p, n } = JSON.parse(buffer.subarray(offset, end).toString());
    if (!/^[\w.-]+(\/[\w.-]+)*$/.test(p) || p.split('/').includes('..') || !Number.isInteger(n) || n < 0) throw new Error('Backup part has an unsafe path');
    const bytes = buffer.subarray(end + 1, end + 1 + n);
    if (bytes.length !== n) throw new Error('Backup part is truncated');
    const target = path.join(dir, ...p.split('/'));
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, bytes);
    offset = end + 1 + n; count++;
  }
  return count;
}

export function createBackup({ url = process.env.SUPABASE_URL, key = process.env.SUPABASE_SERVICE_ROLE_KEY, bucket = process.env.BACKUP_BUCKET || 'recordings', fetchImpl = fetch, log = console.warn } = {}) {
  if (!url || !key) return null;
  const base = `${url.replace(/\/$/, '')}/storage/v1`;
  const auth = { apikey: key, ...(key.startsWith('eyJ') ? { Authorization: `Bearer ${key}` } : {}) };
  const object = (id, name) => `${base}/object/${bucket}/${id}/${name}`;
  let bucketReady = null;

  const ensureBucket = () => bucketReady ??= fetchImpl(`${base}/bucket`, {
    method: 'POST', headers: { ...auth, 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: bucket, name: bucket, public: false }), signal: AbortSignal.timeout(10000),
  }).then(response => { if (!response.ok && response.status !== 409 && response.status !== 400) throw new Error(`HTTP ${response.status}`); }); // already exists = fine

  async function put(id, name, bytes, type) {
    const response = await fetchImpl(object(id, name), { method: 'POST', headers: { ...auth, 'Content-Type': type, 'x-upsert': 'true' }, body: bytes, signal: AbortSignal.timeout(120000) });
    if (!response.ok) throw new Error(`upload ${name}: HTTP ${response.status} ${(await response.text().catch(() => '')).slice(0, 120)}`);
  }
  async function get(id, name) {
    const response = await fetchImpl(object(id, name), { headers: auth, signal: AbortSignal.timeout(120000) });
    if (!response.ok) throw new Error(`download ${name}: HTTP ${response.status}`);
    return Buffer.from(await response.arrayBuffer());
  }

  return {
    bucket,
    /** Upload a session folder. Returns true on success. */
    async upload(id, dir) {
      try {
        await ensureBucket();
        const parts = await pack(dir);
        for (const [i, part] of parts.entries()) await put(id, `part-${String(i).padStart(4, '0')}.bin`, part, 'application/octet-stream');
        await put(id, 'index.json', JSON.stringify({ parts: parts.length, uploaded_at: new Date().toISOString() }), 'application/json');
        return true;
      } catch (error) {
        bucketReady = null;
        log(`Backup upload failed for ${id}: ${error.message}`);
        return false;
      }
    },
    /** Download a session folder. Returns the number of restored files, 0 when there is no backup. */
    async restore(id, dir) {
      try {
        const { parts } = JSON.parse((await get(id, 'index.json')).toString());
        let files = 0;
        for (let i = 0; i < parts; i++) files += await unpack(await get(id, `part-${String(i).padStart(4, '0')}.bin`), dir);
        return files;
      } catch (error) {
        log(`Backup restore failed for ${id}: ${error.message}`);
        return 0;
      }
    },
  };
}
