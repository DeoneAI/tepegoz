// Pure formatting helpers shared by the dashboard and the phone page.

/** Fixed-decimal number, or an em dash for anything that is not a finite number. */
export const fmt = (value, digits = 1) =>
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';

/** Milliseconds from a monotonic clock as a decimal nanosecond string (no precision claim). */
export const stamp = ms => String(Math.round(ms * 1e6));

/** Seconds as mm:ss. */
export function duration(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}

/** Nanosecond string → seconds with fixed decimals. */
export const nsToSeconds = (ns, digits = 3) => (Number(ns) / 1e9).toFixed(digits);

/** Six-digit, zero-padded frame label. */
export const frameLabel = index => `#${String(index).padStart(6, '0')}`;
