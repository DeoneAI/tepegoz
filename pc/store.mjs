// Session index. Recording files in data/<id>/ stay the source of truth; this index makes the
// library fast and queryable and survives restarts.
//
// 1. SQLite (built into Node 22.5+ as node:sqlite): always on, free, no install, one file data/sessions.sqlite.
// 2. Supabase (optional): set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to mirror session metadata
//    (never frames or raw IMU) to a free hosted Postgres so the team can see the session list.
//    Mirror failures are logged and never block recording.
import path from 'node:path';
import { readdir, readFile } from 'node:fs/promises';

const SCHEMA = `
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL,
  connection_mode TEXT,
  frames INTEGER,
  samples INTEGER,
  duration_s REAL,
  device_user_agent TEXT,
  manifest TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_created ON sessions(created_at DESC);`;

/** Flatten a manifest into an index row (the full manifest is kept as JSON). */
export function toRow(manifest) {
  const m = manifest.metrics || {};
  return {
    id: manifest.id, name: manifest.name, created_at: manifest.created_at, ended_at: manifest.ended_at ?? null,
    status: manifest.status, connection_mode: manifest.connection_mode ?? null,
    frames: m.frames ?? null, samples: m.samples ?? null, duration_s: m.duration_s ?? null,
    device_user_agent: manifest.device?.user_agent ?? null,
    manifest: JSON.stringify(manifest), updated_at: new Date().toISOString(),
  };
}

export function createSupabaseMirror({ url = process.env.SUPABASE_URL, key = process.env.SUPABASE_SERVICE_ROLE_KEY, table = 'sessions', fetchImpl = fetch, log = console.warn } = {}) {
  if (!url || !key) return null;
  const endpoint = `${url.replace(/\/$/, '')}/rest/v1/${table}?on_conflict=id`;
  return {
    async upsert(row) {
      const { manifest, ...meta } = row;
      try {
        const response = await fetchImpl(endpoint, {
          method: 'POST',
          // Legacy service_role keys are JWTs (eyJ…) and also go in Authorization; new sb_secret_… keys only in apikey.
          headers: { apikey: key, ...(key.startsWith('eyJ') ? { Authorization: `Bearer ${key}` } : {}), 'Content-Type': 'application/json', Prefer: 'resolution=merge-duplicates,return=minimal' },
          body: JSON.stringify({ ...meta, manifest: JSON.parse(manifest) }),
          signal: AbortSignal.timeout(8000),
        });
        if (!response.ok) log(`Supabase mirror: HTTP ${response.status} ${await response.text().catch(() => '')}`.slice(0, 300));
      } catch (error) {
        log(`Supabase mirror unavailable: ${error.message}`);
      }
    },
  };
}

export async function openStore(dataRoot, { mirror = createSupabaseMirror(), log = console.warn } = {}) {
  let db = null;
  try {
    const { DatabaseSync } = await import('node:sqlite');
    db = new DatabaseSync(path.join(dataRoot, 'sessions.sqlite'));
    db.exec('PRAGMA journal_mode = WAL;' + SCHEMA);
  } catch (error) {
    log(`SQLite index unavailable (${error.message}); the library falls back to reading manifests.`);
  }
  const upsertStatement = db?.prepare(`INSERT INTO sessions (id, name, created_at, ended_at, status, connection_mode, frames, samples, duration_s, device_user_agent, manifest, updated_at)
    VALUES (:id, :name, :created_at, :ended_at, :status, :connection_mode, :frames, :samples, :duration_s, :device_user_agent, :manifest, :updated_at)
    ON CONFLICT(id) DO UPDATE SET name=excluded.name, ended_at=excluded.ended_at, status=excluded.status, connection_mode=excluded.connection_mode,
      frames=excluded.frames, samples=excluded.samples, duration_s=excluded.duration_s, device_user_agent=excluded.device_user_agent,
      manifest=excluded.manifest, updated_at=excluded.updated_at`);

  const store = {
    kind: db ? 'sqlite' : 'files',
    mirrored: Boolean(mirror),
    /** Record the latest manifest. Never throws: indexing must not break recording. */
    save(manifest) {
      const row = toRow(manifest);
      try { upsertStatement?.run(row); } catch (error) { log(`SQLite index write failed: ${error.message}`); }
      mirror?.upsert(row);
    },
    /** Manifests, newest first; null when SQLite is unavailable (caller scans files). */
    list() {
      if (!db) return null;
      return db.prepare('SELECT manifest FROM sessions ORDER BY created_at DESC').all().map(r => JSON.parse(r.manifest));
    },
    /** Index any session folder that is missing or newer on disk (files remain authoritative). */
    async backfill(isSessionId) {
      if (!db) return 0;
      let count = 0;
      for (const dir of await readdir(dataRoot)) {
        if (!isSessionId(dir)) continue;
        try { store.save(JSON.parse(await readFile(path.join(dataRoot, dir, 'manifest.json'), 'utf8'))); count++; } catch { /* incomplete folder */ }
      }
      return count;
    },
    close() { try { db?.close(); } catch { /* already closed */ } },
  };
  return store;
}
