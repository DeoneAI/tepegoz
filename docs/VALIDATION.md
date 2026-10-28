# Validation

## 28 October 2026 — branch acceptance and lane-render corrections

- Accepted `feat/weeks-1-3-baselines` (`cdee933`) into local `main` by fast-forward, then corrected two reviewed rendering defects: low-confidence boundaries/centerlines were drawn despite suppressed corridor shading, and the computed image-space offset indicator was not displayed. Shared thresholds now gate all lane geometry at 0.4 and a valid left/right/centered indicator at 0.6. The indicator explicitly states `UNCALIBRATED`; raw JSONL estimates remain unchanged by rendering.
- **23 Node tests and 44 Python tests passed without skips**, and the static frontend build passed. Four new renderer regressions cover actual sparse-mask fitter output, inclusive threshold boundaries, all three visible directions, missing/invalid geometry, and preservation of source pixels/raw estimates. Local runtime: Node 24.15.0, Python 3.14.4, NumPy 2.5.4, OpenCV 5.0.0 and ONNX Runtime 1.31.1; CI separately checks its declared runtimes.
- Ran the updated combined CLI on 20 frames of Udacity `solidWhiteRight.mp4` (indices 0–38, stride 2, CPU provider, four threads), using the pinned YOLOP and YOLOX Tiny models. It emitted independent logs, benchmark/run metadata, preview images and an MP4; source hashes stayed unchanged during the run. Inspected the first side-by-side preview: both lane methods show geometry and the image-space `CENTERED | UNCALIBRATED` label. This is a smoke check, not a replacement benchmark or a lane-accuracy measurement. Generated output remains ignored at `.tools/week2-render-fixed-smoke/`.
- Reopened Day 7 temporal/visual quality acceptance and added the [lane-quality protocol](LANE-QUALITY.md). Historical reports retain their original code hashes and measurements. Temporal/day-night review and the original phone-footage outcome remain pending; no physical recording or new frontend deployment is claimed here.

## 28 October 2026 — coworker handoff readiness

- Prepared [fresh-PC setup](handoff/START-HERE.md), separate Week 1/2/3 operator guides and an evidence template. The workflow uses the coworker's existing Vercel project and leaves branch/commit/push operations to the repository owner. Portable binaries, models/datasets, raw recordings and account credentials are explicitly not clone contents.
- Copied the current tracked and nonignored new source files into a separate source-only directory, with no `.tools/`, `data/`, `.venv/`, `.vercel/` or `.env.local`. **23 Node and 40 Python tests passed without skips**, and the static build produced all ten frontend files there. CLI help and asset-registry listing also worked. Runtimes/packages came from the available host environment; this verifies source/asset separation, not a newly provisioned coworker PC or a new Python 3.12 installation.
- Reviewed command flags and local document links. No new model download, physical phone recording or deployment was claimed for this check. Explicit remaining software tasks are the generic phone quaternion/yaw export adapter and complete derived-session image/calibration preparation; EuRoC-specific demos and checkerboard previews are not substitutes for them.

## 28 October 2026 — production frontend deployment

- Published **https://tepegoz-tawny.vercel.app** with Vercel CLI 65.5.0. Production deployment `dpl_CH1LrgoYyTWYmuyHktc8jHpoZuDN` returned `READY`; the selected account reports Hobby. No paid services were added. The Node recording collector and Python processing remain on the PC.
- Re-ran **23 Node tests** and the static build before publishing. Anonymous HTTPS requests return 200 for the dashboard and all ten frontend assets, whose bytes match the local build exactly. Camera/accelerometer/gyroscope permissions and CSP/security headers are present. `/pc/server.mjs`, `/.env.local` and `/data/` return 404. This verifies publishing, not physical capture or a live collector connection.
- The first upload's overly restrictive inclusion rules omitted the build script and failed before becoming ready. Corrected `.vercelignore` to exclude recordings, credentials, tools and offline processing while including `web/`, `scripts/build.mjs` and build configuration; the subsequent deployment succeeded.
- Updated `DEPLOY-VERCEL.ps1` to support the locally installed Node/CLI and report failed deployments. Account/project binding, local CLI, OIDC credentials and raw request evidence remain ignored. Public deployment evidence is in [the deployment report](reports/frontend-deployment.json).

## 28 October 2026 — public-data Weeks 2–3

- Completion audit against original PDF pages 2–4 and 8–9 found and closed a missing scalar time-series artifact: executed 240 predict/update steps with noisy/missing observations and three R settings, saved actual CSV/plots, and reviewed the rendering. Raw/filtered RMSE uses the same observed timestamps. The existing three single-update examples and 2D cases remain separate exercises.
- Re-ran the real 600-frame EuRoC motion demonstration with an explicit shaded assumed-quiet interval; its orientation errors and flow correlation reproduce the earlier results exactly. Reviewed the updated plot and refreshed the report artifacts. This remains an assumption, not proof of physical stationarity or phone heading.
- **23 Node tests passed**, including a new lifecycle regression that blocks the phone's stopped/finalize message until its in-flight JPEG acknowledgment completes. Six phone tests now cover frames and telemetry; collector storage rollback/finalization regressions remain covered.
- **40 Python tests passed**: eight alignment/report tests, two Parquet tests, two exact KITTI time/calibration tests, three bounded-download tests, three checkerboard-calibration tests, 21 vision/estimation tests and one real CLI small-video export test. Coverage includes Joseph covariance stability, variable dt/outlier gates, an analytic Jacobian versus numerical differentiation, exact-ns gyro integration, native-axis/rate limits, synthetic 3D essential-pose recovery, confidence association/staleness, camera-motion covariance, raw YOLOX decoding, lane fitting and robust depth ROI handling. All optional local dependencies were present; no checks skipped.
- Camera-calibration tests recover known synthetic projection under corner noise, verify held-out corners never enter intrinsic fitting, and reject duplicate-image inflation of view count. Executed the actual checkerboard CLI on 13 size/hash-verified OpenCV samples: 11 training + 2 held out, training RMS 0.2531 px, held-out pose-fit RMS 0.3395/0.2408 px. Reviewed detected/undistorted imagery and the residual plot. These are sample-camera fit diagnostics, not independently verified phone/mount calibration.
- Verified range responses before body consumption and bounded streamed archive blocks. Mocked ignored/oversized ranges never populate cache; an actual public ZIP block read returned the expected signature. This protects against accidentally downloading the entire large archive if a server ignores the range header.
- Actual CPU ONNX inference ran for 15 serial three-scene benchmark cases, six public day/night/snow images and a labeled 15-image/85-instance COCO subset. This is separate model-execution evidence, not unit tests with fake neural outputs. [Measured CSV](reports/vision_benchmark.csv) and [full results](reports/WEEKS-2-3.md) preserve settings, source/model hashes, timings and limits. No full-COCO mAP or unlabeled road tracking accuracy is claimed.
- Actual real EuRoC processing used 600 camera frames/5,993 IMU samples. Evaluated gyro, essential VO, attitude-only fusion and real gyro-seeded feature tracking; kept missing/degenerate VO intervals and wrong-sign controls. Visually reviewed the real gyro/acceleration/yaw/error/flow plots. Local complementary fusion is not full VIO/SLAM.
- Built and executed **OpenVINS commit `69488123ed9362dd44b6f28e7f4680abbff1442b`** through the ROS-free local Docker adapter. It exported 488 initialized poses, first at 5.6 s, with 0.2035 m position RMSE and 2.540° mean orientation error after one fixed initial-pose SE(3) alignment, scale 1. Ground truth is read only by the subsequent evaluator; the C++ estimator reads camera/IMU only. Visually reviewed the trajectory/error/online-bias plot. This short mono VIO dataset demo does not establish global loop closure or phone performance.
- Imported actual KITTI RGB/OXTS for **1,205 frames over 125.09 s**, preserving native axes and source timestamps. Analysis found no frame/sample sequence gaps, missing/orphan JPEGs or duplicate IDs. All frames align under the analysis ±100 ms window; p95 gyro mismatch 10.794 ms, maximum 70.559 ms. Two Node replay runs produced identical 1,205-line bytes; the hash is in [replay verification](reports/kitti-replay.json). This verifies processing/replay, not physical exposure timing.
- Real KITTI RGB-only versus gyro-assisted tracking uses **exactly identical indexed detection records**, verified by the comparison script. Assistance used 1,203/1,205 frames; the first unaligned/initialization frames remain explicit. Observed IDs 320→230 and tracks of ≤2 observations 132→78 are proxies, not ground-truth ID switches. These functional runs overlapped other work and their FPS is not used as a controlled speed comparison.
- Executed and visually reviewed a 100-frame KITTI run with both lane methods, detector/tracker, both depth alternatives and real calibrated gyro rotation on the same indexed frames. Saved independent logs, raw float maps, previews and video under ignored `.tools/experiments/kitti-integrated/`. Native times, actual calibration, missing-lane confidence, stale boxes and unvalidated depth units remain explicit.
- Camera/USB/tunnel hardware, true display latency, sustained phone rates and phone/mount calibration remain unverified. Public camera/IMU import never automatically marks W1 passed. Models, full datasets, private recordings and Docker binaries were not added to tracked source.
- Static frontend build passed. All 15 final benchmark code-hash sets match the current inference implementation, with no source changes during their runs. `git diff --check` passed. No commit was made; the subsequent frontend deployment is recorded above.

## 27 October 2026 — coordinate frames and session analysis

- Added an SVG diagram and [frame/timing guide](FRAMES-AND-TIMING.md) covering phone/body, camera, chosen vehicle/world conventions, transform direction and gravity. Rendered the SVG in headless Chrome and visually reviewed it.
- Added `scripts/analyze_session.py`: exact-integer timestamp subtraction, nearest association with explicit missing values, alignment CSV, JSON diagnostics, and Matplotlib SVG/PNG timelines. Reports include sequence and JPEG/log consistency checks; none certifies physical acceptance.
- **10 Python tests passed**: eight analysis tests (including actual CLI plot export) and the two existing Parquet tests. Coverage includes one-nanosecond window boundaries, ties/unsorted input, missing gyro, unchanged raw files, conflicting session IDs/units, malformed input, active/storage-error refusal and explicit incomplete sessions. Matplotlib 3.11.0 was available locally; CI installs analysis and Parquet dependencies.
- **22 Node tests passed**, static production build passed, and `git diff --check` passed after integration. Prior recording reliability fixes remain covered.
- Generated and visually reviewed a clearly labeled synthetic timeline with a gyro gap under ignored `.tools/analysis-qa/`. This checkout has no real recordings. Real-device synchronized timelines, measured capture timing, calibration and the W1 acceptance matrix remain outstanding.

## 27 October 2026 — recording reliability update

- **22 Node tests passed** on Windows with portable Node.js 22.23.4. Added five phone-lifecycle regressions for stopping during successful/failed uploads, an empty waiting buffer, bounded retries and ended sessions. These execute the actual phone script in a VM with a minimal DOM and controlled HTTP responses.
- Added three receiver regressions for telemetry/frame storage failure, rollback and retry without duplicate records or inflated counters, and refusal to finalize after rollback failure. File blockers and an injected truncation failure exercise the real HTTP handler and temporary recording files.
- Static production build and `git diff --check` passed. No physical-device or new browser visual/performance acceptance was performed for this update.
- Compared the supplied `Junior_Autonomous_Driving_Perception_One_Month_Plan_Expanded_VIO_SLAM_Kalman.pdf` against `docs/roadmap/assignment.pdf`: all 11 pages have identical extracted text, including Week 1 on page 2 and the learning addendum. PDF byte hashes differ. The repository checklist expands the same requirements with implementation status and outstanding evidence; existing protocol, timestamp and offline-Parquet limitations remain explicit.

## 21 October 2026 — original validation

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
