# Week 1 handoff: collect and verify real phone data

Prerequisite: complete [fresh-PC setup](START-HERE.md). The software is present; this week's main remaining work is **physical evidence from your phone and PC**. Keep the [original requirement audit](../reports/THROUGH-WEEK-3-AUDIT.md) and [acceptance sheet](../STRESS-TEST.md) open while working.

## 1. Record the device/setup information

In a local copy of the [evidence template](EVIDENCE-TEMPLATE.md), write the exact phone model/variant, OS/browser versions, PC CPU/RAM, connection route, camera settings, screen orientation and mount. Do not infer hardware gyro availability from the product name or the interface's old Galaxy A15 label.

Download Google Platform-Tools and extract its folder so `.tools/platform-tools/adb.exe` exists, or install `adb` on PATH. The collector discovers the bundled path automatically.

On Android, enable Developer options and USB debugging. Connect a data-capable cable, unlock the phone and approve this PC. Check:

```powershell
& .\.tools\platform-tools\adb.exe devices -l
```

The phone should be listed as `device`. Resolve `unauthorized`, missing-device, cable and driver issues before continuing. This implemented USB route is Android/ADB, not iPhone USB or WebUSB.

## 2. Start the PC collector and pair over USB

In terminal A, from the project root:

```powershell
npm.cmd start
```

Keep it running and the PC awake. Open **http://localhost:8787** on the PC and copy its printed collector token into **Connection settings**. Keep the token private.

Select **USB cable / Android ADB → Find USB devices → choose the authorized device → Test & connect**. Create a fresh session named, for example, `usb-rotation-01`. Open its generated pairing link on the phone. The phone's localhost reaches the PC only because the verified ADB reverse mapping is active.

Tap **Check sensors before capture**. Allow requested motion permission and gently rotate the phone. Record the availability and probe rates. The preflight does not start the camera.

If gyro is unavailable, investigate browser motion permission, browser support and the exact physical sensor inventory. Missing browser readings do not prove missing hardware. If the hardware lacks gyro, a suitable different device or acquisition route is required; zero-filled/invented gyro is not a solution.

## 3. Capture a clean synchronized session

Start with 640-pixel requested width and 10 JPEG FPS for bring-up. Turn optional GNSS on only for a test that needs location. Continue from preflight and allow camera access. Confirm the phone camera and saved-frame count, PC preview, accelerometer and gyro samples all progress.

Record **130 seconds of active capture**, giving some margin to demonstrate at least 120 seconds of common camera/accelerometer/gyro overlap. For the controlled rotation run: 20 seconds stationary, 80 seconds of slow rotations about the three phone axes, then 30 seconds stationary. Keep a textured scene visible and the browser in the foreground.

Stop in this order: **phone Stop → wait for final frame/telemetry uploads → retry queued samples if needed → PC Stop & save**. Closing the phone tab before flushing loses its memory queue. A server restart invalidates old phone upload keys; create a new session afterwards.

Check **Session library → Replay**. The entire folder `data/SESSION_ID/` is the recording: manifest, clock log, telemetry, frame logs/CSV and JPEGs must stay together.

## 4. Analyze and inspect the actual files

Replace the placeholder with the real session ID:

```powershell
& .\.venv\Scripts\python.exe scripts/analyze_session.py data/SESSION_ID
node pc/replay.mjs data/SESSION_ID
& .\.venv\Scripts\python.exe scripts/export_parquet.py data/SESSION_ID
```

Parquet export is optional and runs after finalization; raw CSV/JSONL remain canonical. Inspect `analysis/analysis.json`, `alignment.csv`, `timeline.png` and `timeline.svg`:

- Real camera, accelerometer and gyro overlap for at least 120 seconds; no missing required stream.
- Every saved JPEG has a matching indexed metadata entry, and its timestamp-source label is defensible. Check missing/orphan files, duplicates, regressions and sequence gaps.
- Measured frame/sensor rates are plausible and sustained. Review intervals/short time windows as well as a whole-session average; a preflight probe rate is not sustained capture Hz.
- Inspect nearest-match differences and missing associations. The default ±100 ms window is a matching rule, not proof of timestamp accuracy.
- Interpret phone axes/gyro signs, stationary specific force and clock estimates using [FRAMES-AND-TIMING.md](../FRAMES-AND-TIMING.md). Browser timestamps remain labeled estimates; nanosecond units do not give nanosecond accuracy.

The analyzer deliberately reports `requires_physical_validation`; it does not issue an automatic acceptance pass. Record your review separately. It plots gyro/acceleration and association timing, not a phone orientation/yaw estimate; that remaining adapter task is listed in [Week 3](WEEK-3.md#phone-specific-work-still-required).

## 5. Complete the condition and failure matrix

Collect the four baseline conditions below as separate finalized sessions. Use at least 130 seconds active capture per baseline; label intentional failure tests separately.

| Condition | What to inspect |
|---|---|
| Indoor stationary | Continuous real readings, achieved rates, specific-force direction, frame/IMU alignment |
| Stationary/rotation | Axis signs, gyro response, bias/quiet intervals, visual motion alignment |
| Walking/handheld | Blur, buffering, vibration, rate variation and gaps |
| Road-facing, passenger-operated | Secure forward-facing view, actual mounting/camera configuration and road imagery |

For road capture, either use a portable PC with the cable or reach the running collector through a working mobile/Wi-Fi HTTPS route. The driver must not operate the recording. Do not claim a road session if the required equipment/conditions are unavailable; record the dependency.

After a clean baseline, repeat matched stationary/rotation settings over both USB and tunnel. Test higher requested settings, such as 1280-pixel width/15 JPEG FPS and then 30 FPS when sustainable. Log actual camera settings, target JPEG FPS and saved FPS separately; the browser may negotiate a different image size/rate.

Use separate sessions for a 10-second connection interruption/recovery, permission denial/restoration, switching apps and screen lock. For USB, also test cable removal/remapping and an Internet-disabled cable-only path. Keep pre-failure files and report losses/recovery behavior. Expected browser suspension is a limitation to measure, not hide.

## HTTPS tunnel and the existing Vercel site

Use your team's current frontend origin, not the original developer's account binding. Keep the tunnel running while you restart the collector to add its exact URL.

1. With the collector initially running in terminal A, start terminal B:

```powershell
cloudflared tunnel --url http://127.0.0.1:8787
```

2. Copy the printed `https://...trycloudflare.com` origin. Finalize any active recording before stopping terminal A with Ctrl+C. In terminal A, replace **both** example origins with the actual values:

```powershell
$env:ALLOWED_ORIGINS='http://localhost:8787,http://127.0.0.1:8787,https://YOUR-TEAM-SITE.vercel.app,https://YOUR-TUNNEL.trycloudflare.com'
npm.cmd start
```

3. Open the team's hosted dashboard. Select **Wi-Fi / Internet HTTPS tunnel**, enter the tunnel origin and this PC's collector token, connect, and create a **new** session. Open the new pairing link on the phone. Keep terminals A and B running.

A new quick tunnel can have a different URL; update the origin list before starting a new capture and recreate pairing. [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/) are temporary development/test endpoints. Do not assume a stable production URL or guaranteed uptime. If running the `START-PC.ps1` helper instead of the explicit commands, note that its current prompt accepts only one frontend origin; it does not add the tunnel origin automatically.

## 6. Measure actual display latency separately

Arrange a visible flash/event in the test phone's camera view. With another camera, film both that physical event and the PC preview at the same time. For about 30 repetitions, count observer-video frames from the original event to its displayed appearance:

`event-to-display delay_ms = frame_difference / observer_fps * 1000`

Preserve the observer video, event/frame pairs, observer FPS and uncertainty/refresh limits. Report median and p95 for each route/settings cohort. If that equipment is unavailable, mark display latency unmeasured.

Collector `latency_p50_ms`/`latency_p95_ms` are estimated **ingest** delay, not display delay. Its `jitter_ms` is the standard deviation of the retained ingest-latency window (up to 600 frames), not IMU sampling jitter. Collector saved FPS includes session time; the analyzer also computes rates from source timestamp spans. State which definition you use.

## 7. Calibrate your camera and document transforms

Follow [CALIBRATION.md](../CALIBRATION.md). Capture 15–20 distinct well-lit checkerboard views with unchanged lens/resolution/crop/focus settings; count internal corners and measure the printed square edge.

```powershell
& .\.venv\Scripts\python.exe scripts/calibrate_camera.py data/my-checkerboard-images --output .tools/experiments/phone-calibration-01 --columns 9 --rows 6 --square-size-m 0.025
```

Use the example dimensions/25 mm value only when they match your physical target. Inspect corners, training/held-out pose-fit residuals, diversity warnings and the corrected preview. Archive the calibration JSON with camera configuration details.

This tool does not estimate camera-to-IMU or phone-to-vehicle extrinsics/time offset. Photograph/document the mount and chosen axes; use measured geometry or dedicated calibration for transforms. Keep unknown fields null. Board-to-camera poses are not phone-mount transforms. Public sample-camera parameters must not be copied into your phone configuration.

## Week 1 hand-back and completion check

Provide the completed evidence sheet, finalized real sessions shared through an agreed private channel, analysis/clock/calibration reports, route comparison, true display-latency measurements or explicit missing evidence, and failure notes. Do not commit raw personal recordings or credentials.

Week 1 remains open if required gyro/overlap, physical condition tests, sustainable settings, timing interpretation or calibration/feasibility evidence is missing. A passing test suite, public KITTI replay or working preview alone cannot close it. Escalate a blocked sensor/device issue early rather than proceeding with a false full-IMU claim.
