// Canvas line chart for X/Y/Z inertial traces. Colors come from CSS custom properties.

const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export function drawTraces(canvas, samples) {
  const box = canvas.getBoundingClientRect();
  if (!box.width) return;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = box.width * dpr;
  canvas.height = box.height * dpr;
  const c = canvas.getContext('2d');
  c.scale(dpr, dpr);
  const w = box.width;
  const h = box.height;

  c.strokeStyle = css('--grid');
  c.lineWidth = 0.6;
  for (let i = 0; i < 5; i++) { const y = 12 + i * (h - 24) / 4; c.beginPath(); c.moveTo(0, y); c.lineTo(w, y); c.stroke(); }
  for (let i = 0; i < 9; i++) { const x = i * w / 8; c.beginPath(); c.moveTo(x, 7); c.lineTo(x, h - 7); c.stroke(); }
  if (samples.length < 2) return;

  const values = samples.flatMap(s => Object.values(s.values));
  const min = Math.min(-1, ...values);
  const max = Math.max(1, ...values);
  const pad = (max - min) * 0.1;
  const start = Number(samples[0].timestamp_ns);
  const span = Number(samples.at(-1).timestamp_ns) - start || 1;
  const colors = { x: css('--axis-x'), y: css('--axis-y'), z: css('--axis-z') };

  for (const axis of ['x', 'y', 'z']) {
    c.strokeStyle = colors[axis];
    c.lineWidth = 1.5;
    c.beginPath();
    samples.forEach((sample, i) => {
      const x = (Number(sample.timestamp_ns) - start) / span * w;
      const y = h - 10 - (sample.values[axis] - min + pad) / (max - min + 2 * pad) * (h - 20);
      if (i) c.lineTo(x, y); else c.moveTo(x, y);
    });
    c.stroke();
  }
}
