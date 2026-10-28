# Weeks 2–3: recorded perception and estimation

The PC now has executable lane, detector, tracker, depth, Kalman and motion-study modules. Acquisition remains in the browser/Node collector. Public recordings validate these PC code paths; they do not substitute for the outstanding phone/USB/timing acceptance evidence. See [measured benchmark CSV](reports/vision_benchmark.csv) and [benchmark provenance](reports/vision_benchmark.json).

## Reproduce the road baselines

Use Python 3.10+ and a separate environment where possible:

```bash
python -m pip install -r scripts/requirements-vision.txt
python scripts/fetch_assets.py --group vision
python scripts/fetch_assets.py --group roads
python scripts/fetch_assets.py --group depth
python scripts/run_perception.py .tools/datasets/roads/solidWhiteRight.mp4 --output .tools/experiments/my-road-run --max-frames 100 --stride 2 --depth both
```

The same command accepts a finalized collector session directory in place of a video. It preserves phone frame indices and original time strings. Public videos use explicitly labeled media-time estimates and have no invented IMU stream. Single-image examples and public EuRoC data are separate evidence sources, not phone captures.

Use `--mode lanes`, `--mode objects`, `--mode depth --depth both`, or `--mode combined`; choose `--lanes classical|yolop|both`. `--no-prediction` disables the tracker's motion transition for an ablation. Depth is off unless requested. The CPU ONNX adapters use a configurable thread count and do not silently download or substitute models.

Each new output directory contains independent lane, detection, track and requested depth JSONL, raw float32 compressed depth maps, original-index preview JPEGs, an overlay MP4, `benchmark.csv` and `run.json`. Run metadata records model SHA-256, source-code hashes, settings, hardware and timing. Output directories must be empty, preserving earlier experiments. Phone-session MP4 previews use a constant display FPS; JSONL retains the original variable timing.

Aggregate completed runs with:

```bash
python scripts/summarize_benchmarks.py .tools/experiments/my-road-run --output .tools/experiments/my-summary
```

The complete matched three-scene benchmark, including prediction and depth alternatives, is:

```bash
python scripts/run_road_benchmarks.py --output .tools/experiments/my-road-benchmarks
```

It runs 15 cases serially and preserves each run directory. The [results report](reports/WEEKS-2-3.md) records actual speed, labeled detector results, failure review and limits. Fetch the independent class-balanced detector subset and day/night/snow examples with:

```bash
python scripts/fetch_coco_subset.py
python scripts/evaluate_detector.py --output .tools/experiments/my-detector-comparison
python scripts/fetch_assets.py --group road-images
python scripts/evaluate_scene_images.py --output .tools/experiments/my-scene-images
python scripts/evaluate_depth_boxes.py .tools/experiments/my-road-run --output .tools/experiments/my-depth-roi
```

Measured end-to-end throughput includes decode, inference, rendering and saving; model load is excluded. Module timings are separately reported. Running multiple timed experiments concurrently changes CPU contention and is unsuitable for a matched speed comparison.

## Geometry and lane interpretation

The pinhole model is `u = fx X/Z + cx`, `v = fy Y/Z + cy`. Intrinsics, distortion and a measured camera/mount transform are required for metric geometry. One uncalibrated RGB image does not determine scale: a smaller nearby object and a larger distant object can occupy similar pixel areas. Image proximity is not physical distance.

A homography maps a plane between views. A road-plane BEV requires a defensible plane/calibration assumption; slopes, nonplanar surfaces and moving objects violate it. A vanishing point describes projected parallel directions, not every curved road. Curvature in pixels is not curvature in inverse meters. The current lane code does not claim a calibrated BEV or metric lane width. See [OpenCV projection/calibration](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html).

The classical baseline uses HLS white/yellow masks, grayscale blur/Canny, a trapezoidal ROI, Hough segments and a robust quadratic `x(y)` fit for each side. The mask fitter selects nearby image-center candidates, trims large residuals and rejects crossing or implausible bottom widths. Perspective convergence near the horizon is valid. Shadows, glare, snow, worn markings, non-lane edges, junctions and tight curves can remove or corrupt support.

The pretrained alternative is [YOLOP](https://github.com/hustvl/YOLOP)'s lane-segmentation head. The adapter uses its centered letterbox, RGB/ImageNet normalization and two-class lane mask. Segmentation labels pixels; road-user detection produces boxes/classes and tracking associates them across time. These are different tasks. YOLOP's full multi-head inference cost is included even though this adapter consumes only the lane output.

Outputs contain left/right boundaries, a centerline, corridor and a heuristic support/fit confidence. Confidence is not a calibrated probability. Corridor shading needs confidence ≥0.4; the image-center offset indicator needs ≥0.6. It refers to image geometry, not a validated vehicle departure alarm. Missing sides remain null. Availability/continuity counts do not establish lane accuracy; review overlays and failures.

## Detection and tracking

[YOLOX-Tiny](https://github.com/Megvii-BaseDetection/YOLOX/tree/main/demo/ONNXRuntime) uses COCO's actual class IDs: person 0, bicycle 1, car 2, motorcycle 3, bus 5 and truck 7. Other model classes are filtered. The adapter decodes the raw grid/stride head, multiplies objectness by class score and uses class-aware NMS. A confidence threshold is a tunable score cutoff, not a correctness guarantee.

IoU is intersection area divided by union area. Precision is `TP/(TP+FP)` and recall is `TP/(TP+FN)` under a specified class/IoU matching protocol. AP integrates a precision–recall curve; mAP also requires a declared class/IoU averaging scheme. Unlabeled runtime logs cannot produce credible mAP or ground-truth ID switches. Small/distant objects, partial occlusion and glare need explicit miss/false-positive review, not only a smooth overlay.

The local tracker is inspired by [SORT](https://arxiv.org/abs/1602.00763) and [ByteTrack](https://arxiv.org/abs/2110.06864); it is not either official implementation. Its state is `[cx, cy, width, height, vx, vy, vwidth, vheight]` in pixels and seconds. Matrices are:

```text
F = [I4  dt*I4]       H = [I4  0]
    [ 0     I4]
G = [0.5*dt²*I4]      Q = 25*G*Gᵀ
    [    dt*I4]       R = diag(4,4,9,9)
```

After prediction, same-class IoU-gated Hungarian assignment first matches high-confidence detections. A second pass can recover existing tracks from lower-confidence boxes; low-confidence boxes cannot create new tracks. IDs confirm after two observations and expire after a bounded missing interval (default 0.7 s). Predicted boxes are gray, `observed=false`, with stale age. They are not fresh detections. Object motion and ego-motion both affect image coordinates; these velocities are not world velocities. ID count and short-track count are fragmentation proxies, not labeled ID-switch accuracy.

## Depth contracts

Both candidates are Depth Anything V2 ViT-S ONNX exports: the relative model and the outdoor Virtual-KITTI-fine-tuned metric model. The original [Depth Anything V2 paper](https://arxiv.org/abs/2406.09414) and [author repository](https://github.com/DepthAnything/Depth-Anything-V2) distinguish relative and metric training. The [ONNX conversion/release](https://github.com/fabio-sim/Depth-Anything-ONNX) is a community inference artifact, not a new independent depth method. ViT-S weights are Apache-2.0; larger original variants have different terms. Exact downloads, sizes and hashes are in `configs/assets.json`.

| Output | Representation | Interpretation |
|---|---|---|
| Relative | `arbitrary_inverse_depth` | Larger generally means nearer; no meters or fixed cross-frame scale |
| Outdoor metric | `model_m_unvalidated` | Learned model-meter prediction, larger farther, outdoor training maximum 80 m; not independently validated road distance |

Dynamic input dimensions preserve aspect ratio in multiples of 14; the selected long edge and actual tensor shape are recorded. Input-size changes affect quality and speed. CPU memory and GPU VRAM are different quantities; these runs use CPU inference and do not establish GPU performance.

The interior median uses the central 50% of a detection/observed-track box, with at least 16 positive finite pixels. P10/P90 describe pixel-value spread, not calibrated uncertainty. Empty/tiny/off-image boxes return missing. Background leakage, thin objects, occlusion and model boundaries can still bias the result; predicted stale tracks do not get fresh object-depth claims. Raw float maps are preserved for quantitative work; colorized images are displays.

Relative colorbars use per-frame 2nd/98th percentiles and remain labeled arbitrary inverse depth. Metric displays use a fixed 0–80 model-meter range with an unvalidated label. The reported normalized adjacent-map change is unregistered: true scene/camera motion and normalization changes contribute, so it is not a pure temporal-flicker error. Depth accuracy metrics such as AbsRel, RMSE or scale-aligned error require matching ground truth and explicit alignment rules. A relative-depth value cannot be substituted into TTC as meters.

## Kalman learning exercises

Run the deterministic lab:

```bash
python scripts/run_estimation_lab.py --output .tools/experiments/estimation-lab
```

`localization/filters.py` implements prediction, innovation, gain and Joseph covariance updates. `P` describes state uncertainty, `Q` process-model uncertainty and `R` observation uncertainty. Covariance is not an independently measured accuracy guarantee.

```text
x_prior = F*x_previous           P_prior = F*P*Fᵀ + Q
y = z - H*x_prior                S = H*P_prior*Hᵀ + R
K = P_prior*Hᵀ*S⁻¹               x_post = x_prior + K*y
P_post = (I-KH)*P_prior*(I-KH)ᵀ + K*R*Kᵀ
```

The implementation solves linear systems instead of explicitly inverting S. The Joseph form and symmetry restoration improve numerical behavior. The position filter uses `[px,py,vx,vy]`, variable dt, a discrete per-interval acceleration-noise model, missing observations and optional Mahalanobis innovation gating. A turning trajectory violates the constant-velocity model; increasing Q can help follow turns but also follows noise more strongly. An incorrect R or gate can reject valid motion. The lab plots straight/turning trajectories, errors, model covariance envelopes and Q tuning with a fixed synthetic seed, never as phone evidence.

The scalar lab also runs a 240-step position random-walk filter against the same noisy/missing observation sequence for R=0.25, 2.25 and 25. It exports `scalar-timeseries.csv` and estimate/error/covariance plots, including a one-second observation gap and an unmodeled position step. Raw and filtered RMSE are compared on the same observed timestamps; all-time filtered RMSE is reported separately. Higher R can suppress noise while delaying genuine changes. This time-series experiment is separate from the three hand-calculated single updates below.

For `x=10, P=4, Q=1, z=14`, `P_prior=5`:

| R | K | Posterior x | Posterior variance |
|---|---|---|---|
| 1 | 0.833333 | 13.333333 | 0.833333 |
| 9 | 0.357143 | 11.428571 | 3.214286 |
| 100 | 0.047619 | 10.190476 | 4.761905 |

For a heading-aware EKF state `[x,y,θ,v]`, `x'=x+v cos(θ)dt`, `y'=y+v sin(θ)dt`. The nonzero derivatives include `dx'/dθ=−v sin(θ)dt`, `dy'/dθ=v cos(θ)dt`, `dx'/dv=cos(θ)dt`, `dy'/dv=sin(θ)dt`. The code derives these and tests them against numerical derivatives. Normalize angle innovations across ±π and check observability; a gyro alone cannot determine absolute north or eliminate its own bias drift. Linear KF and an EKF study model are not by themselves VIO or SLAM.

The yaw-bias exercise gives 1.1 rad (63.0254°) without correction and 1.0 rad (57.2958°) after subtracting 0.01 rad/s over 10 s. The difference is 0.1 rad (5.7296°). A phone's gyro Z axis is not necessarily the vehicle's vertical/yaw axis; see the [frame guide](FRAMES-AND-TIMING.md).

## Public motion demonstration

```bash
python scripts/fetch_euroc.py --frames 600
python scripts/run_motion_dataset.py --dataset .tools/datasets/euroc-v101 --output .tools/experiments/motion-euroc
```

The [ETH EuRoC dataset](https://projects.asl.ethz.ch/datasets/euroc-mav/) supplies real images/IMU, measured intrinsics and camera–IMU extrinsics. The fetcher obtains a bounded subset from a pinned mirror because the original host has moved and the current repository rate-limits this environment. ZIP CRCs and per-file hashes are recorded; the whole archive is not independently SHA-256-verified. Raw source times remain integer nanoseconds before subtraction.

Gyro integration uses midpoint angular rates and quaternion composition. Missing intervals stay flagged. A quiet-window search in the initial five seconds can estimate gyro bias under an explicitly reported stationary assumption; it uses no ground-truth bias. Slow rotation can be confused with bias, and gravity/initial yaw require careful interpretation. Quaternions avoid Euler gimbal-lock in propagation; Euler yaw is only a display, rotation matrices explain coordinate changes, and all representations still share calibration/bias limitations.

The VO demo undistorts images, tracks corners with forward/backward LK checks, estimates an essential matrix with RANSAC and uses cheirality/parallax/homography checks before accepting a relative pose. Its monocular translation scale is arbitrary. An attitude-only complementary experiment blends accepted camera rotations with gyro increments in the calibrated camera frame and gates large disagreements. Ground truth is used only for evaluation and one fixed initial orientation alignment, never as estimator feedback. This is a supporting visual-inertial experiment, not a complete metric VIO/SLAM solution. Failed/negative results must remain visible in the report.

The two first motion ablations are separately reproducible:

```bash
python scripts/run_gyro_flow_ablation.py --output .tools/experiments/my-gyro-flow
python scripts/run_tracking_motion_ablation.py --output .tools/experiments/my-controlled-rotation
```

The first uses real EuRoC gyro and images; the second creates known synthetic camera rotations of a public road still. Their evidence types must not be merged. Wrong-sign controls and no-improvement cases remain in the results.

## Independent full VIO demonstration

Docker with a Linux engine is optional and used only for the isolated public demonstration. The [adapter/Dockerfile](../integrations/openvins/Dockerfile) pins OpenVINS commit `69488123ed9362dd44b6f28e7f4680abbff1442b`, builds its ROS-free interface and feeds the selected **raw** EuRoC camera/IMU files. The camera configuration matches the downloaded calibration. Mono mode and fixed camera intrinsics/extrinsics/time offset are explicit changes to the supplied stereo configuration. Native distortion is handled by OpenVINS; do not feed the already-undistorted derived replay JPEGs to this demo.

```bash
python scripts/run_openvins_demo.py --output .tools/experiments/my-openvins
```

The first call builds a local image; later calls reuse Docker layers. `--skip-build` uses the existing pinned image. No ports are exposed and the execution container has no network. The dataset mount is read-only. The C++ runner reads camera and IMU files, never ground truth. Static initialization delay stays visible. It exports initialized pose/online bias states as CSV, with the estimator's metric scale intact. The Python evaluator subsequently applies **one fixed first-matched-pose SE(3) alignment, scale 1**, compares nearest reference samples within 10 ms, and saves trajectory/error plots, source/image hashes and limits. This is an upstream mono VIO demonstration, not custom phone VIO or a verified loop-closing SLAM integration. See the [measured result](reports/openvins-euroc.json).

## Same-session public color camera and real gyro

KITTI supplies a synchronized/rectified color camera and OXTS stream. The fetcher uses verified HTTP byte ranges to select 1,205 camera 02 frames and 1,206 packets from the large official S3 archive, plus date-specific calibration. It does not download the entire approximately 21 GB archive. Original PNGs and timestamp text remain unchanged; the derived session labels its public source, native axes, approximate 10 Hz OXTS rate, calendar timezone ambiguity and JPEG conversion.

```bash
python scripts/fetch_kitti_subset.py
python scripts/import_kitti_session.py
python scripts/analyze_session.py .tools/datasets/kitti-replay --output .tools/experiments/my-kitti-alignment
node pc/replay.mjs .tools/datasets/kitti-replay
python scripts/run_perception.py .tools/datasets/kitti-replay --output .tools/experiments/my-kitti-rgb --mode objects
python scripts/run_perception.py .tools/datasets/kitti-replay --output .tools/experiments/my-kitti-imu --mode objects --imu-assist --calibration .tools/datasets/kitti-replay/motion-calibration.json
python scripts/compare_session_tracking.py .tools/experiments/my-kitti-rgb .tools/experiments/my-kitti-imu --output .tools/experiments/my-kitti-comparison.json
python scripts/run_perception.py .tools/datasets/kitti-replay --output .tools/experiments/my-kitti-integrated --depth both --imu-assist --calibration .tools/datasets/kitti-replay/motion-calibration.json --max-frames 100 --stride 2
```

The comparison refuses different indexed detector outputs. IDs/short-track totals remain proxies without exhaustive semantic identities. In rotation-only assistance, `R_body_camera` maps camera to the saved IMU axes and `H=K R_current_previous K^-1` warps box state/covariance before prediction. Intrinsics, image size, units and axes must match. Missing or discontinuous gyro disables assistance explicitly. Phone defaults require matches within 25 ms and gaps ≤0.1 s; the KITTI calibration explicitly declares a 50 ms match tolerance and 0.25 s gap limit for its lower sample rate. No phone axes or bias calibration are invented. These are processing limits, not timestamp-accuracy guarantees.

EuRoC can also exercise the common replay path with `python scripts/import_euroc_session.py`; that import undistorts grayscale source images using the supplied camera calibration. KITTI is the actual color-road/IMU integration evidence. Both imports keep public-data manifests and cannot pass physical phone/USB acceptance. Read [dataset/model attribution](THIRD-PARTY.md) before redistributing downloaded imagery.
