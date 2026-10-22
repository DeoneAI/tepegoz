# Validation — 21 October 2026

Software checks, simulated acquisition and physical evidence are kept separate. The Week‑1 acceptance gate is not marked complete.

| Check | Result / evidence | Limit |
|---|---|---|
| Node test suite | **14 passed**: clock, nearest matching, schema v2, rates, auth/origin, receiver persistence/replay, live JPEG, GNSS CSV, sequence gaps, sensor probe and USB bridge behavior | Handler/USB/sensor tests use fixtures or injected dependencies |
| Python Parquet suite | **2 passed**, PyArrow 26.0.0 | Typed int64 timestamps, null GNSS fields, bounded multi-batch round-trip, unchanged raw JSONL, empty output and active-session refusal; synthetic data |
| Static production build | Passed: Node-built `dist/` from `web/` | Does not deploy the PC receiver |
| Browser end-to-end | Headless installed Chrome; USB UI/device selection/QR, localhost phone pairing, gyro-unavailable modal, no camera during preflight, capture upload, telemetry ingest, save and PC inventory; no JavaScript page errors | ADB responses, camera and motion input were simulated; no physical performance claim |
| Responsive visual review | Desktop settings and inventory; mobile 390 px preflight dialog reviewed from screenshots | This is desktop Chrome emulation, not an on-device visual audit |
| Mermaid diagrams | Architecture, sequence and radar parsed and rendered with Mermaid 11; SVG fallbacks exported and visually reviewed | Radar scores are explicitly qualitative decision rubric, not measured benchmarks |
| Android Platform-Tools | Official Windows portable ADB installed under `.tools/platform-tools`; version 37.0.1; discovery executed | No attached authorized device was listed; real USB reverse/capture remains unverified |
| Existing physical phone data | A previous session contained 2,263 accelerometer and 2,263 linear acceleration samples, zero gyroscope samples; its recorded average saved FPS was approximately 0.55 and clock RTT approximately 562 ms | One development recording; not a compliant two-minute full-IMU/stress benchmark; no gyro hardware conclusion from browser output |
| Static hosting | A previous production frontend deployment returned READY; deployment configuration is included in `vercel.json` | Account/project binding is local and excluded from Git; the backend remains on PC |
| Physical USB/Wi‑Fi comparison | **Not completed** | Authorized phone, data cable, driver, fixed settings and controlled-duration captures required |
| Full W1 stress / calibration / display latency | **Not completed** | See `STRESS-TEST.md`; no measured camera intrinsics/extrinsics or true capture-to-display experiment |

The receiver test's tiny JPEG-signature fixture proves protocol/file handling, not JPEG image quality. The separate simulated browser test uses Chrome's fake media device to exercise actual JPEG encoding/upload and receiver acceptance. Neither establishes hardware exposure timestamps or achieved phone FPS/Hz.

## Reproduce

```powershell
npm.cmd test
npm.cmd run build
python -m pip install -r scripts/requirements-parquet.txt
python -m unittest discover -s tests -p "test_*.py"
```

Without optional PyArrow, Python tests explicitly skip. During development PyArrow was installed only under `.tools/python` and tests were run with `PYTHONPATH` pointing there. The browser QA harness and screenshots are development artifacts in `.tools/`; they use an isolated test collector/data directory, not personal recordings.

USB acceptance requires the real workflow in the README and the added USB/preflight checklist in `STRESS-TEST.md`. Missing gyro, a browser timestamp estimate or insufficient achieved rate must remain visible in any final lead/senior report.
