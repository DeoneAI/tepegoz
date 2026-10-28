# Coworker handoff: continue Weeks 1–3 on your PC

Prepared 28 October 2026. These instructions target **Windows PowerShell** from the repository root. The repository owner handles the branch, commits and push; begin after cloning/checking out the branch they provide. Do not continue from an older `main` checkout by mistake.

The acquisition interface still says **Sensorlink**. **Tepegoz** is the repository/project name.

## Read and execute in this order

1. Complete the fresh-PC setup below.
2. Follow [Week 1: physical recording and acceptance](WEEK-1.md).
3. Follow [Week 2: lanes, detection and tracking](WEEK-2.md).
4. Follow [Week 3: depth, orientation and first fusion](WEEK-3.md).
5. Fill in a copy of the [evidence template](EVIDENCE-TEMPLATE.md) as you work.

| Week | Already implemented and exercised | What you still need to do |
|---|---|---|
| 1 | Browser capture, sensor preflight, PC receiver, clock estimates, logging, plots/replay, analysis, USB bridge and checkerboard calibration tool | Verify your physical phone/PC, collect real synchronized recordings, compare connection routes, measure timing/rates/loss, calibrate your camera and document mount limits |
| 2 | Classical/YOLOP lanes, six-class YOLOX detection, Kalman-based tracking, independent logs/overlays, public-data benchmarks and error review | Reproduce on your hardware, evaluate actual phone road footage, review/label a small sample, document misses and tracking failures |
| 3 | Two depth models/box association, scalar/2D Kalman lab, real EuRoC gyro/VO/attitude experiments, pinned OpenVINS demo, real KITTI motion ablation | Reproduce the experiments, finish phone-specific yaw export and image/calibration preparation, then evaluate depth and motion assistance on phone data |

Do not rebuild these modules from scratch. Public-data evidence does not pass physical phone acceptance. Full custom phone SLAM, certified metric distance and Week 4's final submission/video are not prerequisites for these baseline exercises.

## What runs where

```text
Phone browser: camera + real available motion sensors
    -> USB/ADB OR HTTPS tunnel
Your PC: Node collector -> data/ recordings
Your PC: Python offline lanes / objects / tracks / depth / motion analysis
Vercel: static capture page and dashboard
```

Your PC is the recording server. Keep it awake, the collector running, and the cable/tunnel connected during capture. There is no paid cloud recording service in this setup. The hosted dashboard does not run the Python perception stack or store recordings on Vercel. The current phone client does not save an independent offline session.

## Fresh-PC installation

Install the following from their official sources. Use x64 versions on an x64 Windows PC.

| Tool | Required for | Source |
|---|---|---|
| Node.js **22.x** | Collector, frontend build and Node tests | [Node downloads](https://nodejs.org/en/download); choose 22.x for the tested baseline |
| Python **3.12** | Analysis, inference and Python tests | [Python Windows releases](https://www.python.org/downloads/windows/); also the version configured in CI |
| Android Platform-Tools / ADB | Android USB capture | [Google Platform-Tools](https://developer.android.com/tools/releases/platform-tools) |
| `cloudflared` | HTTPS-tunnel tests / hosted frontend connection | [Cloudflare downloads](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/downloads/) |
| Docker with a Linux engine | Only the independent OpenVINS reproduction | Optional; the rest of the project works without it |

No GPU is required for the existing CPU inference path. Model/dataset downloads and experiment outputs need disk space; allow several GB and check free space before long recordings or saving depth maps for every frame.

Open the supplied branch in VS Code. All commands below assume its root is your terminal's working directory. Check your environment and record the checkout revision:

```powershell
node --version
py -3.12 --version
git branch --show-current
git rev-parse --short HEAD
```

Create an isolated Python environment; these commands do not require PowerShell activation:

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r scripts/requirements-analysis.txt -r scripts/requirements-vision.txt -r scripts/requirements-parquet.txt
```

If the `py` launcher is unavailable, use your installed Python 3.12 executable to create `.venv`. Keep using the explicit `.venv` executable afterwards; do not accidentally install packages into a different interpreter.

Verify the checkout **before downloading datasets or connecting a phone**:

```powershell
npm.cmd test
npm.cmd run build
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

The handoff baseline has **23 Node tests and 40 Python tests**. With all requirements installed, none should skip. The tests use controlled inputs; passing them is not phone acceptance. `npm install` is not needed for the dependency-free Node collector/build. Optional Vercel CLI installation is separate.

## What is intentionally absent after cloning

| Ignored location | Meaning / what you do |
|---|---|
| `.tools/` | Downloaded models, public datasets, experiment outputs and development tools. Recreate with the documented fetch commands; do not expect the original developer's files |
| `data/` | Raw phone recordings. Your collector creates this locally. Transfer any agreed example separately, preserving its complete session folder |
| `.venv/`, `node_modules/` | Local dependencies; install on your PC |
| `.vercel/`, `.env*` | Machine/account bindings and credentials; do not copy the original developer's files |
| `dist/` | Generated frontend; recreate with `npm.cmd run build` |

Tracked `docs/reports/` contains selected reference metrics/plots, not the full raw experiments. Fetching assets checks the registered byte size/SHA-256. Your timing results may differ; record your own hardware, settings and versions. Keep licensing/attribution from [THIRD-PARTY.md](../THIRD-PARTY.md).

## Continue using your existing Vercel project

Use **your team's existing project** for the previous version. The additional `tepegoz-tawny.vercel.app` deployment is development reference only; you do not need to migrate to that Vercel account or copy its credentials.

After the owner publishes the handoff branch, verify in your existing Vercel project that the intended deployment uses that branch/commit. Use these project settings:

| Setting | Value |
|---|---|
| Root directory | Repository root (`.`) |
| Framework | Other / static frontend |
| Build command | `npm run build` |
| Output directory | `dist` |
| Node | 22.x for reproducibility |

Keep `vercel.json` and `.vercelignore` from this branch. Do not set the recording collector token as a frontend/Vercel environment variable. The collector token is generated on your PC and entered into dashboard connection settings.

Check that both `/` and `/phone.html` on the chosen team URL load on the phone. Preview deployment protection can require a Vercel login; confirm phone access before using the URL in a recording. Use the intended stable team URL and put its exact origin in the collector's `ALLOWED_ORIGINS`. Do not change project access policy or switch production branches without coordinating with the owner.

USB administration always uses `http://localhost:8787` on the collector PC. Hosted capture uses an HTTPS tunnel to that PC; detailed terminal order is in [Week 1](WEEK-1.md#https-tunnel-and-the-existing-vercel-site).

## Working rules and troubleshooting

- Run from the repository root. Every experiment needs a **new, empty output directory**; do not delete earlier evidence to reuse a name.
- Keep raw recordings unchanged. Derived images, plots and inference outputs go to separate folders under `.tools/experiments/`.
- Record source type: `phone`, `public dataset`, or `synthetic exercise`. Preserve frame indices, timestamps and model/code hashes.
- Run matched speed benchmarks serially; model-only FPS and end-to-end FPS are different measurements.
- Do not commit `data/`, `.tools/`, `.venv/`, `.env*`, `.vercel/`, pairing links, collector tokens or raw private media.

| Symptom | First action |
|---|---|
| `node`/`py` not found | Finish installation/PATH setup and reopen the VS Code terminal |
| Import/module missing | Run pip with `.venv\Scripts\python.exe`, then use that same executable for scripts/tests |
| Model missing/incomplete | Run the appropriate `fetch_assets.py --group ...`; do not rename a different model to bypass checks |
| ADB missing/unauthorized | Follow Week 1's extraction, cable, unlock and debugging authorization checks |
| Collector unreachable/CORS error | Check process, exact tunnel URL, `ALLOWED_ORIGINS` and the new token/session after a restart |
| Gyro unavailable | Separate browser permissions/support from actual hardware inventory; no synthetic replacement |
| Recording active/storage error | Finalize normally or investigate the storage error before analysis/inference |
| ONNX Runtime DLL/import failure | Check interpreter architecture and [official installation prerequisites](https://onnxruntime.ai/docs/install/); preserve the error text |

For evidence and remaining work use [the template](EVIDENCE-TEMPLATE.md), [the requirements audit](../reports/THROUGH-WEEK-3-AUDIT.md) and the individual week guides. A checked implementation item means code/demonstration exists; it does not certify physical measurements or the learner's understanding.
