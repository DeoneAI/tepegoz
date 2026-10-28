# Week 3 handoff: depth, orientation and motion experiments

Prerequisites: [setup](START-HERE.md), finalized camera/IMU evidence from [Week 1](WEEK-1.md), and understood indexed detection/tracking outputs from [Week 2](WEEK-2.md). Public demonstrations can run independently while phone issues remain open.

## 1. Reproduce depth and box association

```powershell
& .\.venv\Scripts\python.exe scripts/fetch_assets.py --group depth
$phoneSession = 'data/REPLACE_WITH_FINALIZED_SESSION_ID'
& .\.venv\Scripts\python.exe scripts/run_perception.py $phoneSession --output .tools/experiments/w3-phone-depth-01 --depth both --max-frames 30 --stride 2
& .\.venv\Scripts\python.exe scripts/evaluate_depth_boxes.py .tools/experiments/w3-phone-depth-01 --output .tools/experiments/w3-phone-depth-01-roi
```

Fetch `vision` models first if not already done in Week 2. Use this bounded run to inspect all four panels, then choose a new output name and process a larger/full sequence as resources allow. Saving both float maps every frame is expensive in CPU time and disk space; log actual settings and runtime rather than assuming live-rate performance.

Check the same original frame indices/timestamps across detections, tracks, depth logs and saved maps. Review box interior medians, tiny/off-image/occluded objects, background leakage and stale tracks. Predicted stale tracks should not acquire a fresh depth observation.

| Model output | Required interpretation |
|---|---|
| `arbitrary_inverse_depth` | Relative value, generally larger nearer; no meters or fixed cross-frame scale |
| `model_m_unvalidated` | Learned meter prediction, larger farther; not independently validated phone object distance |

Keep visible colorbars/units. P10/P90 are pixel-value spread, not calibrated confidence bounds. ROI sensitivity is not ground-truth depth error. Compare stationary and moving clips for temporal behavior, but call existing normalized adjacent-map change an **unregistered diagnostic**: it includes real motion, content and normalization effects, not only flicker. AbsRel/RMSE or certified meter accuracy need independent corresponding depth references. GPU VRAM remains unmeasured when using CPU inference.

## 2. Run and explain the Kalman exercises

```powershell
& .\.venv\Scripts\python.exe scripts/run_estimation_lab.py --output .tools/experiments/w3-kalman-01
```

Inspect `report.json`, the scalar three-R comparison, `scalar-timeseries.csv`/plots and the straight/turning 2D figures. Explain prediction, innovation, gain, P/Q/R, the Joseph update, variable dt, missing/outlier handling, turning-model error, covariance versus actual accuracy, and angle normalization.

Write your own calculation for x=10, P=4, Q=1, z=14 at R=9, then R=1 and 100; the guide has reference answers. Derive the heading model's `dx/dheading=-v*sin(heading)*dt` and `dy/dheading=v*cos(heading)*dt`. Explain what observations make a state observable and how incorrect Q/R or gating can fail. Solve the 0.11 rad/s measured rate minus 0.01 rad/s bias over 10 s in radians/degrees. Completed code does not replace being able to explain it.

## 3. Reproduce real visual/inertial motion on EuRoC

```powershell
& .\.venv\Scripts\python.exe scripts/fetch_euroc.py --frames 600
& .\.venv\Scripts\python.exe scripts/run_motion_dataset.py --output .tools/experiments/w3-euroc-motion-01
& .\.venv\Scripts\python.exe scripts/run_gyro_flow_ablation.py --output .tools/experiments/w3-euroc-flow-01
```

This is actual public monochrome camera/IMU data with supplied calibration. Inspect gyro/acceleration/yaw/error/flow plots and the shaded **assumed** quiet interval, VO rejection reasons, sign conventions and no/incorrect gyro controls. A quiet low-variance interval is not independent proof of stationarity. Ground truth is used for stated evaluation/alignment, not estimator feedback.

The local complementary estimator is attitude-only; essential VO translation has arbitrary scale and rejected intervals. Read [VO-VIO-SLAM.md](../VO-VIO-SLAM.md) to distinguish these from position/velocity/bias VIO, mapping, preintegration, optimization, loop closure and relocalization.

For the separate actual mono VIO demonstration, if your PC supports Docker's Linux engine:

```powershell
docker info
& .\.venv\Scripts\python.exe scripts/run_openvins_demo.py --output .tools/experiments/w3-openvins-01
```

The first run builds the pinned upstream adapter/image. `--skip-build` is only for an image already built on **your** PC; Docker images are not in the Git clone. Inspect initialized poses, initialization delay, trajectory/error plots and the reported fixed initial alignment with scale 1. If Docker is unavailable, read the committed reference evidence and record that local reproduction is pending, not that a new run succeeded. This is not a custom phone/global loop-closing SLAM integration.

## 4. Reproduce the real road RGB-versus-gyro comparison

This optional larger download is valuable for validating the common replay/motion path. The bounded fetcher selects 1,205 KITTI color frames and OXTS packets by byte ranges; do not download the entire large archive manually. Expect extracted images and range-cache disk usage.

```powershell
& .\.venv\Scripts\python.exe scripts/fetch_kitti_subset.py
& .\.venv\Scripts\python.exe scripts/import_kitti_session.py
& .\.venv\Scripts\python.exe scripts/analyze_session.py .tools/datasets/kitti-replay --output .tools/experiments/w3-kitti-alignment-01
node pc/replay.mjs .tools/datasets/kitti-replay
& .\.venv\Scripts\python.exe scripts/run_perception.py .tools/datasets/kitti-replay --output .tools/experiments/w3-kitti-rgb-01 --mode objects
& .\.venv\Scripts\python.exe scripts/run_perception.py .tools/datasets/kitti-replay --output .tools/experiments/w3-kitti-imu-01 --mode objects --imu-assist --calibration .tools/datasets/kitti-replay/motion-calibration.json
& .\.venv\Scripts\python.exe scripts/compare_session_tracking.py .tools/experiments/w3-kitti-rgb-01 .tools/experiments/w3-kitti-imu-01 --output .tools/experiments/w3-kitti-comparison-01.json
```

These are actual public native-axis/lower-rate OXTS samples, not phone-portrait/high-rate IMU. The importer supplies the matching rectified camera calibration. The comparison requires identical indexed detector records and leaves unmatched/initial gyro frames explicit. Unique IDs and short tracks remain proxies, not exhaustive ID-switch accuracy.

The separate known-rotation road-box stress test is synthetic motion over a real still:

```powershell
& .\.venv\Scripts\python.exe scripts/fetch_assets.py --group roads
& .\.venv\Scripts\python.exe scripts/run_tracking_motion_ablation.py --output .tools/experiments/w3-synthetic-rotation-01
```

Keep its known pure rotation/approximate reference-box assumptions separate from real IMU results. Correct compensation in the reference run preserved IDs but lost more observations; report that tradeoff and the wrong-sign case.

## Phone-specific work still required

The following are genuine remaining tasks; the public demos do not implement or verify them automatically:

| Task | Existing building blocks | Required work/evidence |
|---|---|---|
| Phone orientation/yaw export | `localization/orientation.py` quaternion integration/bias/gap helpers; `analyze_session.py` already plots real gyro/accel/time associations | Add a finalized-session adapter that reads phone gyro rad/s and exact timestamps, reports bias/initial-orientation assumptions, exports quaternion/relative-yaw plots, marks quiet/gap intervals and keeps raw data unchanged |
| Matching camera image geometry | `scripts/calibrate_camera.py` estimates raw K/distortion and produces a corrected preview | Prepare a **separate derived recording** of undistorted images with the matching K, dimensions, original frame IDs/times and provenance. The current calibration script does not undistort a full session |
| Camera/IMU and mount transforms | Null-valued `configs/motion-calibration.example.json`; frame guide | Obtain/document the required camera-to-saved-IMU rotation, axes and timing basis, and vehicle-mount transform where needed. Checkerboard board poses are not these transforms; never fill identity just to run the command |
| Phone RGB-versus-IMU evaluation | `SessionRotationCompensation`, indexed CLI and comparison script | Run matching inputs/settings with/without assistance only after image geometry/extrinsics are valid; review actual identity/lane effects and negative cases |

`run_motion_dataset.py` reads the EuRoC directory layout, **not a generic phone session**. Do not rename phone files to imitate EuRoC or pass them to that demo. Relative gyro orientation also does not establish world north or vehicle heading: show an actual stationary-vehicle/rotating-phone example or another documented frame/mount difference.

The rotation-only adapter assumes pinhole/rectified image coordinates and does not model raw lens distortion, camera translation, rolling shutter or independently moving objects. A raw checkerboard calibration file is not directly usable for `--imu-assist`: its mount rotation is deliberately null, and raw/undistorted K must not be mixed. Document what remains unknown rather than presenting unjustified fusion as completed.

After the phone-specific preparation is completed and reviewed, the existing supported command shape is:

```powershell
# Replace both paths with your prepared derived session and measured matching calibration.
$preparedSession = '.tools/derived/REPLACE_WITH_PREPARED_PHONE_SESSION'
$motionCalibration = '.tools/calibration/REPLACE_WITH_MEASURED_MOTION_CALIBRATION.json'
& .\.venv\Scripts\python.exe scripts/run_perception.py $preparedSession --output .tools/experiments/w3-phone-rgb-01 --mode objects --max-frames 100 --stride 2
& .\.venv\Scripts\python.exe scripts/run_perception.py $preparedSession --output .tools/experiments/w3-phone-imu-01 --mode objects --max-frames 100 --stride 2 --imu-assist --calibration $motionCalibration
& .\.venv\Scripts\python.exe scripts/compare_session_tracking.py .tools/experiments/w3-phone-rgb-01 .tools/experiments/w3-phone-imu-01 --output .tools/experiments/w3-phone-comparison-01.json
```

Those placeholder paths do not exist in a clone. This block describes the interface to use **after** the preparation task, not an already delivered phone workflow. Do not claim full-session results from its bounded 100-frame check.

## Week 3 hand-back and completion check

Provide indexed depth-associated tracks/maps/overlays, latency and temporal/ROI diagnostics with honest units, the math exercises and notes, public demo outputs or explicit local reproduction limits, real phone orientation/frame/calibration evidence, and a controlled motion comparison including failures/no-improvement cases. Use [the evidence template](EVIDENCE-TEMPLATE.md).

Public-data baseline artifacts already exist. Full phone evidence remains open until the actual phone stream and calibration/preparation tasks above are fulfilled. Metric depth validation, custom full phone VIO/SLAM, global loop closure and safety-grade TTC are stretch work, not a reason to fabricate measurements or delay the required baseline evidence.
