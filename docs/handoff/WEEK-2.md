# Week 2 handoff: validate lanes, detection and tracking

Complete [setup](START-HERE.md) and establish a readable finalized recording using [Week 1](WEEK-1.md). Public-data work can proceed while phone issues are investigated, but keep its source label separate.

The baseline implementations already exist: `perception/lanes.py`, `models.py`, `tracking.py`, `render.py`, and the indexed input/CLI. The task is to reproduce, inspect and evaluate them on your hardware and actual phone scenes, not start another detector implementation.

## 1. Understand the reference behavior

Read the geometry/lane/tracker sections of [PERCEPTION-AND-ESTIMATION.md](../PERCEPTION-AND-ESTIMATION.md), the [glossary](../GLOSSARY.md), and [reference results/failures](../reports/WEEKS-2-3.md). Be able to explain:

- Semantic versus instance segmentation, lane fitting, boxes, confidence and class-aware NMS.
- Why a corridor can be confidently wrong and image proximity is not metric distance.
- The box Kalman state, F/H/Q/R, prediction/update, Hungarian IoU association, low-score recovery and stale tracks.
- Why image-coordinate velocity mixes ego-motion and object motion.

The current classical lane method has weak coverage on some scenes; Tiny has weak bicycle/truck results in the small labeled subset. These are documented findings, not missing model files to replace silently.

## 2. Download models/samples and run a public smoke test

```powershell
& .\.venv\Scripts\python.exe scripts/fetch_assets.py --group vision
& .\.venv\Scripts\python.exe scripts/fetch_assets.py --group roads
& .\.venv\Scripts\python.exe scripts/run_perception.py .tools/datasets/roads/solidWhiteRight.mp4 --output .tools/experiments/w2-public-smoke-01 --mode combined --max-frames 30 --stride 2
```

Open `overlay.mp4` and `previews/`. Inspect `run.json`, `benchmark.csv`, independent lane logs, `detections.jsonl` and `tracks.jsonl`. Both classical and YOLOP lane methods run by default; depth is off. Every output should preserve original source indices/timestamp labels, including intentional stride gaps.

## 3. Reproduce the matched three-scene benchmark

```powershell
& .\.venv\Scripts\python.exe scripts/fetch_assets.py --group depth
& .\.venv\Scripts\python.exe scripts/run_road_benchmarks.py --output .tools/experiments/w2-public-bench-01
$benchmarkRuns = Get-ChildItem .tools/experiments/w2-public-bench-01 -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'run.json') } | ForEach-Object { $_.FullName }
& .\.venv\Scripts\python.exe scripts/summarize_benchmarks.py @benchmarkRuns --output .tools/experiments/w2-public-bench-01-summary
```

The runner executes 15 cases serially across white-marking, yellow-marking and curved/shadowed clips: lanes, objects/tracks, combined, prediction-disabled tracking and both-depth integration. Depth cases bridge into Week 3. Check your own hardware/provider/thread settings and module mean/p95 times. Do not run another heavy inference job during a matched speed experiment.

Optional independent quality reproduction:

```powershell
& .\.venv\Scripts\python.exe scripts/fetch_coco_subset.py
& .\.venv\Scripts\python.exe scripts/evaluate_detector.py --output .tools/experiments/w2-detector-subset-01
& .\.venv\Scripts\python.exe scripts/fetch_assets.py --group road-images
& .\.venv\Scripts\python.exe scripts/evaluate_scene_images.py --output .tools/experiments/w2-scene-images-01
```

The detector comparison uses a selected 15-image/85-instance COCO subset, not full-COCO mAP. Day/night/snow example stills help inspect failure modes; they do not prove nighttime video continuity. Keep original image/license metadata.

## 4. Run your real phone footage separately and together

Replace the placeholder once, in this PowerShell terminal:

```powershell
$phoneSession = 'data/REPLACE_WITH_FINALIZED_SESSION_ID'
& .\.venv\Scripts\python.exe scripts/run_perception.py $phoneSession --output .tools/experiments/w2-phone-lanes-01 --mode lanes --max-frames 100 --stride 2
& .\.venv\Scripts\python.exe scripts/run_perception.py $phoneSession --output .tools/experiments/w2-phone-objects-01 --mode objects --max-frames 100 --stride 2
& .\.venv\Scripts\python.exe scripts/run_perception.py $phoneSession --output .tools/experiments/w2-phone-combined-01 --mode combined --max-frames 100 --stride 2
& .\.venv\Scripts\python.exe scripts/run_perception.py $phoneSession --output .tools/experiments/w2-phone-no-prediction-01 --mode objects --no-prediction --max-frames 100 --stride 2
```

These are bounded first checks, not validation of the entire two-minute recording. After inspecting them, repeat with **new output names and without `--max-frames`** for the full sequence. Record the stride; it is deliberate inference subsampling, not acquisition loss. Repeat on distinct road scenes; the existing public three-scene comparison does not establish phone-domain performance.

Do not treat the session overlay MP4's constant playback FPS as original capture timing. JSONL original timestamps/indices are authoritative. Confirm left/right/centerline/corridor are gated when confidence is weak, observed versus predicted boxes differ visibly, and trajectory/ID logs agree with the rendered frames.

## 5. Review quality and record failures

Select and retain an explicit review sample with frame indices, reviewer and source. Include curves, weak/worn markings, shade, junctions, distant objects and occlusion when available. If night video is unavailable, state that rather than extrapolating from the six stills.

Use the [lane-quality review protocol](../LANE-QUALITY.md). The combined Day 7 continuity/missing/false/day-night benchmark remains open until that scoped evidence exists; runtime/confidence availability and illustrative stills do not close it.

For lanes, note missing sides, wrong boundaries, crossing/implausible corridors and centerline discontinuity. Existing confidence-availability counts are useful but not labeled lane accuracy. For detections, document the six actual supported classes (person, bicycle, car, motorcycle, bus, truck), score/NMS settings, misses and false positives. Label a small phone sample if reporting class-specific precision/recall; do not invent mAP from raw output logs.

For tracking, inspect short occlusions and cases where the same real object changes ID or different objects share an ID. A small consecutively labeled clip can support an explicitly scoped ID-switch result. The current aggregate unique-ID/short-track counts are only fragmentation proxies. Report a no-improvement case as well as improvements; the reference yellow-clip prediction ablation does not improve that proxy.

Before comparing prediction enabled/disabled, confirm matching inputs, stride, detector model and thresholds. This is separate from Week 3's calibrated RGB-versus-IMU comparison; `compare_session_tracking.py` is designed for that latter pair, not the prediction toggle alone.

## Week 2 hand-back and completion check

Return your benchmark CSV/JSON, source/commit/hardware/settings, independent indexed lane/detection/track outputs, representative overlays, an annotated failure list and model-selection notes. Keep raw private media local or share through an agreed private channel. Use [the evidence template](EVIDENCE-TEMPLATE.md).

The public baseline is already implemented/evaluated. Phone-domain acceptance remains open until actual phone road footage is processed/reviewed with stable indices, independent outputs and honest quality findings. Do not mark measured accuracy or ground-truth identity stability complete when only proxies were collected.
