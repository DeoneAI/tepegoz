# Local hand-back evidence template

Copy this template into an ignored local folder, for example `data/handoff-notes/`. Fill it with actual observations. Keep raw media, observer videos, identifiers/location and credentials out of Git; agree separately which sanitized reports/plots can be shared.

## Setup and provenance

| Field | Value |
|---|---|
| Reviewer / capture operator | Pending |
| Date, time and timezone | Pending |
| Branch / commit / dirty-worktree notes | Pending |
| PC OS / CPU / RAM | Pending |
| Node / Python / OpenCV / ONNX Runtime versions | Pending |
| CPU/GPU provider and threads; GPU VRAM if actually measured | Pending |
| Exact phone model / OS / browser | Pending |
| Requested camera / JPEG settings and actual negotiated settings | Pending |
| Mount orientation / camera used / calibration reference | Pending |
| Team frontend origin / route / network type | Pending; never include keys or tokens |

Status vocabulary: **not run**, **pass with evidence**, **fail with evidence**, **blocked by dependency**, **not measured**. Do not use zero as a placeholder for an unmeasured metric.

## Week 1 sessions

| Condition | Route | Source type | Session ID | Camera+accel+gyro common overlap | Status / notes |
|---|---|---|---|---|---|
| Indoor stationary | Pending | Phone | Pending | Pending | Not run |
| Controlled rotation | Pending | Phone | Pending | Pending | Not run |
| Walking/handheld | Pending | Phone | Pending | Pending | Not run |
| Passenger-only road-facing | Pending | Phone | Pending | Pending | Not run |
| Matched stationary/rotation comparison | Other route | Phone | Pending | Pending | Not run |
| Interruption/recovery | Pending | Phone | Pending | Pending | Not run; intentional failure |
| Permission/background/lock behavior | Pending | Phone | Pending | Pending | Not run; intentional failure |

For each session attach the analyzer report/plots, manifest/clock metrics, source folder reference and operator review. Record saved/frame-span FPS, per-sensor Hz plus interval/rate variation, missing/duplicate/regressing records, sequence gaps/skips, nearest-match coverage/deltas, estimated ingest p50/p95, ingest-jitter definition, clock RTT/offset/drift and calibration notes. Keep intentionally failed runs distinct from clean baselines.

| Additional physical evidence | Result / artifact |
|---|---|
| Sensor permission versus actual gyro availability | Pending |
| Real USB transport / reverse mapping / Internet-disabled check | Pending |
| External event-to-display latency: observer FPS, repetitions, frame pairs, median/p95, uncertainty | Pending |
| Checkerboard raw captures, board dimensions/measured square size, fitted K/D, held-out diagnostics | Pending |
| Camera-to-IMU / phone-to-vehicle transforms: method, axes, dimensions and uncertainty or unknowns | Pending |
| Week 1 unresolved limitations / next action | Pending |

## Week 2 experiments

| Scene / source type | Run folder / settings | Module and end-to-end timing | Reviewed frame range / labels | Findings |
|---|---|---|---|---|
| Scene 1 | Pending | Pending | Pending | Not run |
| Scene 2 | Pending | Pending | Pending | Not run |
| Scene 3 | Pending | Pending | Pending | Not run |
| Prediction enabled/disabled | Pending | Pending | Pending | Not run |

Record independent JSONL/overlay locations, original indices/time basis, detector class map/thresholds/NMS, lane boundary/centerline missing/false cases, class-specific misses/false positives, labeled accuracy protocol if available, occlusion/identity failures and three representative failures. Distinguish measured ID switches from unique-ID/short-track proxies. State night-video coverage versus still-only review. Explain the chosen model and a no-improvement case.

## Week 3 experiments

| Required evidence | Artifact / result / unresolved issue |
|---|---|
| Relative and learned metric depth on the same indexed frames, with honest units | Pending |
| Box-depth ROI sensitivity, stale/occluded/background cases, timing and temporal diagnostic | Pending |
| Scalar hand calculations, 1D noisy sequence, 2D KF/Joseph/turning/missing-data plots and Jacobian explanation | Pending |
| EuRoC gyro/VO/attitude/flow demo and assumptions/failures | Pending |
| Independent OpenVINS run, or explicit Docker/local reproduction dependency | Pending |
| Real KITTI camera/IMU comparison versus separate synthetic rotation control | Pending |
| Implemented phone quaternion/yaw export, exact time/axes/bias assumptions, quiet/gap markers | Pending |
| Phone image undistortion/derived-session provenance and measured matching motion calibration | Pending |
| Same-input phone RGB-only versus motion-assisted comparison, including negative cases | Pending |
| Phone orientation versus vehicle heading example | Pending |
| Week 3 remaining limitations / next action | Pending |

## Sharing and next review

- Raw session/private-media transfer location: pending; not a Git commit.
- Sanitized reports/plots approved to share: pending.
- Current scripts/tests pass, skips and failures: pending; attach exact commands/output and environment.
- Concrete blocked dependency, owner and next action: pending.
- Interpretation: which requirements are proven, which use only public/synthetic evidence, and which remain unmeasured: pending.

Do not mark the entire week complete merely because an overlay looks smooth or a script exits successfully. Link each required claim to evidence with matching scope.
