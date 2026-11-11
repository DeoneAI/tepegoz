// Pure timing logic: frame↔sample association, clock estimates and replay scheduling.
// No DOM access, so every function here is unit-tested in Node.

/**
 * Nearest sample to `targetNs` in a list sorted by timestamp_ns, within ±maxMs.
 * Returns the sample plus alignment_delta_ms, or null. Missing data stays missing.
 */
export function nearestSample(samples, targetNs, maxMs = 100) {
  let lo = 0;
  let hi = samples.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (Number(samples[mid].timestamp_ns) < targetNs) lo = mid + 1;
    else hi = mid;
  }
  const candidates = [samples[lo - 1], samples[lo]].filter(Boolean);
  if (!candidates.length) return null;
  const distance = sample => Math.abs(Number(sample.timestamp_ns) - targetNs);
  const best = candidates.reduce((a, b) => (distance(a) <= distance(b) ? a : b));
  const delta = (Number(best.timestamp_ns) - targetNs) / 1e6;
  return Math.abs(delta) <= maxMs ? { ...best, alignment_delta_ms: delta } : null;
}

/**
 * NTP-style estimate from one exchange: phone t0/t3, collector t1/t2 (all ms).
 * offset = collector − phone; rtt excludes collector processing time.
 */
export function exchangeEstimate({ t0, t1, t2, t3 }) {
  return {
    offset_ms: ((t1 - t0) + (t2 - t3)) / 2,
    rtt_ms: Math.max(0, (t3 - t0) - (t2 - t1)),
    phone_ms: (t0 + t3) / 2,
  };
}

/** Choose the minimum-RTT estimate (least queueing error). */
export const bestEstimate = estimates => [...estimates].sort((a, b) => a.rtt_ms - b.rtt_ms)[0] ?? null;

/**
 * Wall-clock time (performance.now() ms) at which `nextFrame` is due, given the replay anchor
 * { wall, phone (ns), speed }. Preserves original phone timing scaled by speed.
 */
export const replayDueAt = (anchor, nextFrameNs) => anchor.wall + (Number(nextFrameNs) - anchor.phone) / 1e6 / anchor.speed;

/** Sort replay payload in place by capture time, keeping index/sequence as tie-breakers. */
export function sortReplay(data) {
  data.frames.sort((a, b) => Number(a.timestamp_ns) - Number(b.timestamp_ns) || a.frame_index - b.frame_index);
  data.samples.sort((a, b) => Number(a.timestamp_ns) - Number(b.timestamp_ns) || a.sequence_id - b.sequence_id);
  const groups = {};
  for (const sample of data.samples) (groups[sample.sensor_type] ??= []).push(sample);
  return { ...data, groups };
}
