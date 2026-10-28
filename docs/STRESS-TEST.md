# Week 01 physical-device acceptance sheet

Status: **formal multi-condition acceptance is not completed**. Live phone recordings were inspected during development and a gyro-free recording was observed; this does not establish a complete physical-device acceptance report. Synthetic and simulated browser tests are not hardware evidence.

Record the exact physical phone model and variant (do not infer it from the interface's old Galaxy A15 label), Android/browser versions, PC CPU/RAM, network, tunnel route, camera settings, screen orientation and mount. For every condition, record at least two minutes and finalize on the PC. New-PC operators should start with the [coworker Week 1 guide](handoff/WEEK-1.md).

| Condition | Session ID | Duration | Saved frames | FPS | Accel Hz | Gyro Hz | Ingest p50/p95 ms | RTT ms | Jitter ms | Sequence gaps / skipped frames | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Indoor stationary | — | — | — | — | — | — | — | — | — | — | Gyro availability and acceleration gravity direction |
| Stationary / phone rotation | — | — | — | — | — | — | — | — | — | — | Verify phone axes and gyro signs |
| Walking / handheld | — | — | — | — | — | — | — | — | — | — | Motion blur, camera buffer and alignment mismatch |
| Road-facing / passenger only | — | — | — | — | — | — | — | — | — | — | Never handle phone while driving |
| Network interruption / 10 s | — | — | — | — | — | — | — | — | — | — | Bounded queue and counted losses |
| Background / screen lock | — | — | — | — | — | — | — | — | — | — | Browser suspension is an expected limit |

For each session verify:

1. Every saved JPEG has one frame record with index and phone timestamp; confirm no untimestamped orphan appears after a normal stop.
2. Gyro and accelerometer have real finite X/Y/Z values, increasing per-type sequence IDs and documented units. All-zero samples are not proof of available hardware without motion testing.
3. Read `clock.jsonl`; note RTT/2 uncertainty and drift over time. Camera estimates remain estimates.
4. Use replay and the offline replay command. Run `python scripts/analyze_session.py data/SESSION_ID` (install `scripts/requirements-analysis.txt` for plots, or add `--no-plot`). Inspect `analysis/analysis.json`, `alignment.csv` and timeline plots for missing associations, absolute matching deltas, common stream overlap and JPEG/log mismatches. The checks are prerequisites, not an automatic W1 pass. The two-minute example must be an actual recording.
5. Check raw file counts/metadata, stop finalization, restart replay, and permission denial behavior.
6. Record camera-to-display latency with a filmed/visible reference clock or an external event experiment if the assignment requires that metric. UI ingest latency alone does not establish it.
7. Photograph a checkerboard only if calibration is feasible; do not populate intrinsics/extrinsics without calibration results. Document mount rotation.

### USB and preflight acceptance additions

1. Record cable/driver/Platform-Tools version and Android debugging authorization. Verify `get-devpath` reports USB and `reverse --list` confirms the selected port; do not use wireless ADB as USB evidence.
2. From the local PC dashboard select USB, create a fresh session, scan its localhost link and record whether `isSecureContext` is true. Repeat with Internet access disabled to demonstrate that the application data path uses the cable.
3. Run Check sensors before capture. Verify available/denied/unavailable-or-blocked states, no camera stream during preflight, and explicit continuation when gyro is unavailable. Confirm capabilities persist to the manifest.
4. Compare matched camera settings and durations for USB vs tunnel. Report actual saved FPS, per-sensor phone-time Hz, counts, gaps, skips, RTT and ingest latency. Do not infer full display latency from ingest p95.
5. Disconnect/reconnect the cable. Confirm bounded loss, operator-visible failure, successful remapping/fresh pairing and readable pre-disconnect files. Do not assume an ACK timeout proves the frame never reached disk.
6. After finalization export Parquet. Compare row count and int64 timestamps/null fields to canonical JSONL; keep raw files. A recording-state session must refuse export.

Acceptance requires the actual camera + accelerometer + gyro stream to pass timing/alignment checks. Missing gyro, unmeasured hardware capture time, or insufficient achieved rate must be reported and may require the native Android route.
