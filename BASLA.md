# Getting started

For continuing on a new coworker PC after the repository owner publishes the handoff branch, use [Start here: Weeks 1–3 handoff](docs/handoff/START-HERE.md). It includes fresh-machine dependencies and the remaining phone-specific work.

This guide runs **Tepegoz / Sensorlink acquisition**. To continue on public datasets without a phone, use the [offline perception and estimation guide](docs/PERCEPTION-AND-ESTIMATION.md). Read the [measured results](docs/reports/WEEKS-2-3.md) and [roadmap](docs/ROADMAP.md) for status.

## 1. Run the PC collector

Install Node.js 22 or later, clone the repository and run:

```bash
git clone https://github.com/DeoneAI/tepegoz.git
cd tepegoz
npm start
```

No npm dependencies are needed for the current runtime. In Windows PowerShell use `npm.cmd start` if script policy blocks `npm.ps1`.

Open **http://localhost:8787** on the PC. Copy the collector token printed in the terminal into **Connection settings**. This is an admin credential: keep it on the PC; phone pairing uses a separate upload-only key.

## 2. Choose a connection route

### Android over USB

1. Install the official [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools). Put `adb` on PATH, place the extracted `platform-tools/` directory under `.tools/`, or set `ADB_PATH` before starting the collector. Local tools are not included in the repository.
2. Connect a data-capable USB cable. Enable **Developer options → USB debugging**, unlock the phone and approve this PC's debugging authorization prompt. Windows may require an OEM USB driver.
3. In the **localhost PC dashboard**, enter the collector token and select **USB cable / Android ADB**.
4. Click **Find USB devices**, select an authorized device and **Test & connect**. The backend checks physical USB transport, configures ADB reverse and verifies the mapping.

USB setup must be managed from the local dashboard, not from the hosted frontend. It does not require Cloudflare, WebUSB or USB tethering. A fresh phone link will use localhost, which reaches the PC only while the ADB mapping and cable are active.

### Wi-Fi or mobile network

Install a trusted HTTPS tunnel tool, then run this in a separate terminal:

```bash
cloudflared tunnel --url http://127.0.0.1:8787
```

Add the exact frontend and tunnel origins to `ALLOWED_ORIGINS` and restart the collector. Example for PowerShell:

```powershell
$env:ALLOWED_ORIGINS='https://YOUR-FRONTEND.example,https://YOUR-TUNNEL.trycloudflare.com,http://localhost:8787,http://127.0.0.1:8787'
npm.cmd start
```

The tunnel hostname is known after starting the tunnel. Replace both placeholders with actual origins. In dashboard settings select **Wi-Fi / Internet HTTPS tunnel**, enter the HTTPS collector origin and collector token, then connect. Include the tunnel origin if it serves the phone page. Recreate pairing after a tunnel URL change.

## 3. Pair and check sensors

Create **New session** and scan/open its link on the phone. Run **Check sensors** before capture. The popup reports real observed availability, measured probe rates and access warnings; it does not start the camera or collect a location fix.

Choose the optional GNSS checkbox before capture if location is needed. Review the popup, continue and grant camera permission. Audio is never requested. If no gyro data is observed, the app can record available sensors, but the full Week 1 IMU acceptance gate remains unmet. A browser warning does not prove physical hardware absence.

## 4. Record, finalize and replay

Keep the phone page visible and the screen active. Keep the collector and either the USB cable/mapping or HTTPS tunnel running.

1. Stop capture on the phone and wait for the final frame and telemetry uploads to finish. If samples remain queued, keep the page open, restore the connection and use **Retry remaining telemetry uploads** before finalizing on the PC. Closing the tab loses the in-memory queue.
2. Click **Stop & save** on the PC.
3. Open **Session library → Replay**, or run:

```bash
node pc/replay.mjs data/SESSION_ID
node pc/replay.mjs data/SESSION_ID --realtime
```

Recordings are stored under `data/<session-id>/`: JPEGs, IMU/GNSS CSV, canonical JSONL, clock estimates and a manifest. They are ignored by Git. Optional Parquet conversion is documented in the README.

For a saved session, run `python scripts/analyze_session.py data/SESSION_ID --no-plot` to export alignment CSV and a JSON report. Install `scripts/requirements-analysis.txt` and omit `--no-plot` to generate gyro/acceleration/video timelines. See the [analysis guide and frame diagram](docs/FRAMES-AND-TIMING.md). The report identifies missing gyro and associations; it does not certify hardware acceptance.

Phone **Saved frames** counts successful storage acknowledgements; **Skipped frames** counts busy/failed target attempts. A selected target FPS is not proof of the achieved rate. Ingest latency is not full display latency.

## Troubleshooting

| Symptom | Check |
|---|---|
| ADB not found | Install Platform-Tools; set `ADB_PATH` or use `.tools/platform-tools/`; restart the collector |
| Unauthorized/offline USB device | Unlock the phone, approve the debugging prompt, check cable/driver and refresh devices |
| USB localhost link cannot connect | Verify `adb -s SERIAL reverse --list`, collector port and the cable; create fresh pairing if needed |
| Tunnel cannot reach collector | Check the process/port and tunnel origin; verify exact `ALLOWED_ORIGINS` |
| Gyroscope empty | Review preflight/permissions; native inventory may be needed; do not infer hardware from the phone model alone |
| Camera/sensors blocked | Use trusted HTTPS or the ADB localhost route and check `isSecureContext`/permissions |
| Old session stops working after restart | Upload keys do not survive collector restart; create a fresh session |

## What is verified?

The software has Node protocol/sensor/USB tests, optional Python Parquet tests and documented simulated-browser checks. Real USB hardware, sustained rates, calibration, true display latency and a compliant two-minute full-IMU recording remain acceptance work. See [validation](docs/VALIDATION.md) and the [physical test protocol](docs/STRESS-TEST.md).
