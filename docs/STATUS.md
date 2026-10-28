# Tepegoz progress tracker

Last updated: **28 October 2026** (Asia/Baku).

Current milestone: **Weeks 2–3 PC baselines completed with public-data evidence; Week 1 physical acceptance remains partial**. No finalized phone recording is available; the user requested continuing with public datasets. This file records development progress, not an automatic repository monitor. The full checklist is in [ROADMAP.md](ROADMAP.md), results in [the measured report](reports/WEEKS-2-3.md), and checks in [VALIDATION.md](VALIDATION.md).

## Milestones

| Milestone | Status | Remaining acceptance work |
|---|---|---|
| W1: acquisition, synchronization, recording and replay | Software implemented; physical gate partial | Phone camera/IMU recording, USB/tunnel comparison, measured timing/rates and phone calibration; diagrams and public-data timeline analysis now exist |
| W2: lanes and object detection/tracking | Public-data baseline complete | Three indexed road clips, classical/YOLOP comparison, Tiny/Nano labeled subset, tracking ablation and failure review; phone-domain validation remains pending |
| W3: depth and motion-assisted processing | Public-data baseline complete; phone workflow pending | Two depth alternatives, KF/gyro/VO/OpenVINS demos and public motion ablations exist. Phone yaw-export adapter, derived image preparation and measured matching motion calibration remain; no validated meter distance or custom phone VIO |
| W4: final integration and submission | Pending | Some offline integration/benchmarks already work; live phone demonstration, final report/video, technical defense and full acceptance still required |

## Latest completed work

- [x] Implement and execute lanes, six-class detection/tracking, two depth models and per-track associations with explicit units, confidence and stale flags.
- [x] Benchmark 15 matched road cases serially; save model/code hashes, independent indexed logs, raw depth maps and overlays. Document qualitative day/night/snow failures and the small labeled COCO detector comparison.
- [x] Implement scalar/2D Joseph-form Kalman filtering and mathematical exercises, variable dt/missing/outlier/turning cases, covariance plots and checked nonlinear Jacobian.
- [x] Process 600 real EuRoC frames/5,993 IMU samples with calibrated VO/gyro and attitude-only fusion; retain failures, quiet-window assumptions and wrong-sign controls.
- [x] Build/run pinned OpenVINS separately on real camera/IMU inputs: 488 initialized poses, 0.204 m position RMSE after one fixed initial-pose alignment with scale 1, no GT estimator feedback. Short public dataset evidence only.
- [x] Import 125.09 seconds of real KITTI color/OXTS data into labeled replay; verify two replay runs are identical and all 1,205 frames have nearby accel/gyro samples under the declared analysis window.
- [x] Compare identical real-road detections with/without gyro rotation; reduce fragmentation proxies while explicitly leaving identity accuracy unmeasured. Run 100 indexed frames with lanes, tracks, both depths and real gyro assistance.
- [x] Fix the final JPEG Stop race as well as telemetry draining. Verify **23 Node + 40 Python tests**, the static build and source-provenance checks; actual model/Docker demonstrations are separate from fixture tests.
- [x] Bound archive downloads before body consumption, test ignored/oversized ranges, and verify the streamed implementation against the public ZIP endpoint.
- [x] Re-audit the original PDF through Day 15; add the missing 240-step scalar noisy-observation experiment/CSV, mark the assumed quiet interval on real IMU plots, and distinguish semantic/instance/lane/detection tasks in the glossary. See the [requirement evidence audit](reports/THROUGH-WEEK-3-AUDIT.md).
- [x] Add the [checkerboard calibration workflow](CALIBRATION.md), including held-out views, duplicate/size checks, corner previews, lens correction preview and residual diagnostics. Execute it on 13 public images; keep phone/mount calibration unclaimed.
- [x] Publish the latest frontend to [tepegoz-tawny.vercel.app](https://tepegoz-tawny.vercel.app) on Vercel Hobby. Verify public access, all 10 built assets and capture/security headers; keep recordings, credentials and offline modules out of frontend uploads. The PC collector remains required.
- [x] Prepare the [coworker handoff](handoff/START-HERE.md), three week guides and an evidence template. Use the coworker's existing Vercel project, recreate ignored local dependencies/assets, and leave branch/commit/push operations to the repository owner. Explicitly identify the remaining phone orientation/export and image/calibration preparation tasks.
- [x] Review project architecture and compare the attached assignment with the repository PDF. All 11 pages have identical extracted text.
- [x] Fix phone Stop to await active telemetry uploads and drain queued samples.
- [x] Keep unsent telemetry visible and offer bounded retries before PC finalization.
- [x] Commit collector sequence counters and sample metrics after successful storage; roll back failed log appends and attempt failed-frame cleanup.
- [x] Reject further session mutations and completed-session claims when log rollback fails.
- [x] Add the [phone/body, camera, vehicle and world diagram](FRAMES-AND-TIMING.md) with transform notation and gravity direction.
- [x] Implement finalized-session analysis with alignment CSV/JSON and shared-time video/gyro/acceleration plots. Real-device timeline evidence remains pending.

## Next work

| Priority | Task | Required evidence / dependency |
|---|---|---|
| 1 | Confirm real accelerometer and gyroscope availability | Authorized physical phone; observed readings and measured rates. Evaluate native acquisition if browser gyro is unavailable |
| 2 | Record and replay a compliant two-minute camera + accelerometer + gyroscope session | Finalized local session, clock log, frame metadata, sensor counts and alignment results |
| 3 | Compare USB and HTTPS tunnel at matched settings | Physical cable/ADB authorization, sustained FPS/Hz, interruption/recovery results and measured latency definitions |
| 4 | Apply the working public-data timelines and inference to a phone recording | EuRoC/KITTI analysis and real dataset calibration work; physical phone samples and phone-specific calibration are still needed |
| 5 | Finish timing, calibration and stress-test evidence | Capture-to-display experiment, calibration results or documented practical limits, and the [acceptance matrix](STRESS-TEST.md) |

## Open decisions and dependencies

- Custom JPEG POST differs from the listed video examples; the justified selection and comparison are documented, without claiming MJPEG/RTSP/WebRTC implementation. A stricter external rubric may require revisiting it.
- Logging uses live CSV/JSONL and optional finalized-session Parquet. The source does not explicitly require live Parquet append; this is the selected implementation, not an approval dependency.
- Browser timestamps remain estimates; clock correction and the ±100 ms association window do not establish hardware exposure timing.
- Physical-device availability, real gyro readings and measured calibration cannot be replaced by fixture tests.
- The latest code, tests and documentation changes are currently uncommitted. The frontend is deployed; local Vercel account/project bindings and credentials remain ignored.

Update this tracker when work is completed or new evidence changes a milestone. Keep individual assignment checkboxes in [ROADMAP.md](ROADMAP.md); mark a gate complete only when its acceptance evidence exists.
