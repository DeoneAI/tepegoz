// Deterministic replay: frames follow their original phone timestamps; each frame shows the
// nearest accelerometer, gyroscope and GNSS sample within ±100 ms. Missing samples stay missing.

import { $ } from '../lib/dom.js';
import { fmt } from '../lib/format.js';
import { nearestSample, replayDueAt, sortReplay } from '../lib/timing.js';

export function createReplay(ctx, { toast }) {
  let replay = null;
  let playing = false;
  let timer = null;
  let imageURL = null;
  let version = 0;
  let anchor = null;

  function pause() {
    playing = false;
    clearTimeout(timer);
    $('play-replay').textContent = '▷ Play';
  }

  async function open(id) {
    pause();
    $('replay-dialog').showModal();
    $('replay-loading').hidden = false;
    $('replay-loading').textContent = 'Loading recorded session…';
    try {
      const data = sortReplay(await ctx.client().getJson(`/api/sessions/${id}/replay`));
      replay = { ...data, id, index: 0 };
      $('replay-name').textContent = data.manifest.name;
      $('replay-range').max = Math.max(0, data.frames.length - 1);
      $('replay-range').value = 0;
      if (!data.frames.length) {
        $('replay-loading').textContent = 'No recorded frames in this session.';
        $('play-replay').disabled = true;
        return;
      }
      $('play-replay').disabled = false;
      await show(0);
    } catch (error) {
      $('replay-loading').textContent = error.message;
    }
  }

  async function show(index) {
    const frame = replay?.frames[index];
    if (!frame) return;
    const current = ++version;
    replay.index = index;
    $('replay-range').value = index;
    const target = Number(frame.timestamp_ns);
    const aligned = ['accelerometer', 'gyroscope', 'gnss'].map(type => {
      const s = nearestSample(replay.groups[type] || [], target);
      return s ? `${type}: ${JSON.stringify(s.values)}   Δ ${fmt(s.alignment_delta_ms, 2)} ms` : `${type}: unavailable within ±100 ms`;
    });
    $('replay-meta').textContent = `Frame ${frame.frame_index} · ${(target / 1e9).toFixed(6)} s · ${frame.timestamp_source}\n${aligned.join('\n')}`;
    $('replay-position').textContent = `${index + 1} / ${replay.frames.length}`;
    try {
      const blob = await ctx.client().get(`/api/sessions/${replay.id}/image?index=${frame.frame_index}`).then(r => r.blob());
      if (current !== version) return;
      const url = URL.createObjectURL(blob);
      if (imageURL) URL.revokeObjectURL(imageURL);
      imageURL = url;
      $('replay-image').src = url;
      $('replay-loading').hidden = true;
    } catch (error) {
      toast(error.message);
    }
  }

  function step() {
    if (!playing || !replay) return;
    const index = replay.index;
    if (index >= replay.frames.length - 1) { pause(); return; }
    const due = replayDueAt(anchor, replay.frames[index + 1].timestamp_ns);
    timer = setTimeout(async () => {
      if (!playing) return;
      await show(index + 1);
      if (playing) step();
    }, Math.max(0, due - performance.now()));
  }

  async function togglePlay() {
    if (playing) return pause();
    if (!replay?.frames.length) return;
    if (replay.index >= replay.frames.length - 1) await show(0);
    anchor = { wall: performance.now(), phone: Number(replay.frames[replay.index].timestamp_ns), speed: Number($('replay-speed').value) };
    playing = true;
    $('play-replay').textContent = 'Ⅱ Pause';
    step();
  }

  $('play-replay').addEventListener('click', togglePlay);
  $('replay-speed').addEventListener('change', pause);
  $('replay-range').addEventListener('input', () => { pause(); show(Number($('replay-range').value)); });
  $('replay-dialog').addEventListener('close', () => { pause(); version++; });

  return { open };
}
