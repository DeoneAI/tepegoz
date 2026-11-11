// Bounded telemetry queue with single-flight batched upload.
//
// Invariants (covered by tests/phone.test.mjs):
// - At most one batch is in flight; flush() while uploading returns that same promise.
// - A failed batch is put back at the FRONT, so ordering is preserved and later samples are not lost.
// - The queue never exceeds `limit`; oldest samples are dropped and counted.
// - HTTP 409/410 means the PC ended the session: the queue stops uploading and reports it once.

const SESSION_ENDED = new Set([409, 410]);

export function createTelemetryQueue({ upload, limit = 2000, batchSize = 500, onSessionEnded = () => {}, onRetryableError = () => {} }) {
  let buffer = [];
  let inFlight = null;
  let ended = false;
  let dropped = 0;
  const sequence = {};

  function trim() {
    if (buffer.length > limit) {
      const removed = buffer.length - limit;
      buffer.splice(0, removed);
      dropped += removed;
    }
  }

  /** Append one sample; assigns a per-sensor sequence_id. */
  function push(sample) {
    const sequence_id = sequence[sample.sensor_type] ?? 0;
    sequence[sample.sensor_type] = sequence_id + 1;
    buffer.push({ ...sample, sequence_id });
    trim();
  }

  function flush() {
    if (inFlight) return inFlight;
    if (!buffer.length || ended) return Promise.resolve();
    const batch = buffer.splice(0, batchSize);
    inFlight = Promise.resolve()
      .then(() => upload(batch, { dropped_samples: dropped }))
      .catch(async error => {
        buffer.unshift(...batch);
        if (buffer.length > limit) {
          dropped += buffer.length - limit;
          buffer.length = limit;
        }
        if (SESSION_ENDED.has(error?.status)) {
          ended = true;
          await onSessionEnded(error);
        } else {
          onRetryableError(error);
        }
      })
      .finally(() => { inFlight = null; });
    return inFlight;
  }

  /** Wait for any in-flight batch, then retry the remainder a bounded number of times. */
  async function drain(maxAttempts = 4) {
    if (inFlight) await inFlight;
    let attempts = 0;
    while (buffer.length && !ended && attempts++ < maxAttempts) await flush();
    return buffer.length === 0;
  }

  return {
    push,
    flush,
    drain,
    get pending() { return buffer.length; },
    get dropped() { return dropped; },
    get ended() { return ended; },
    get uploading() { return Boolean(inFlight); },
  };
}
