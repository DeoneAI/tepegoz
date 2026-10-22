# Week 1 — one-page design decision note

**Problem.** Acquire timestamped RGB and available phone IMU/GNSS on a PC, inspect data live, preserve accepted measurements and replay associations reproducibly. Phone and browser frontend perform acquisition only; perception inference is outside this milestone.

**Stack.** Static vanilla-JavaScript UI, Node.js collector using built-ins, indexed JPEG HTTP(S) uploads and batched JSON telemetry. USB uses Android ADB reverse with a localhost phone page; remote capture uses an HTTPS tunnel. Both routes share schema v2, auth, persistence and replay. Browser acquisition avoids APK distribution but gives up native sensor inventory, hardware timestamp/accuracy guarantees and background operation.

| Decision | Rationale and acknowledged cost |
|---|---|
| USB / ADB + HTTPS tunnel | USB removes WAN hops; requires cable, driver, debugging approval. HTTPS supports remote link-based capture; adds RTT/outage risk. USB is not USB tethering or WebUSB. |
| Custom timestamped JPEG POST | Explicit metadata, independent replay files and storage ACK. This is **not standard MJPEG, RTSP or WebRTC**; it is a documented deviation from the listed transport options. Encoding/bandwidth and one-request-per-frame ACK limit throughput. |
| HTTP batches → TCP collector | Browser-native, inspectable, auth and bounded retry/dedup. Raw UDP/TCP sockets are unavailable to ordinary browser pages. WSS could reduce request overhead but needs backpressure/reconnect semantics. Tunnel internals may use QUIC/UDP. |
| CSV + JSONL; optional offline Parquet | Simple live logging and complete canonical messages; Parquet adds typed/compressed analysis after finalization without a collector dependency. No live Parquet append claim. |
| Nearest sample within ±100 ms | Deterministic matching in original phone time; missing stays missing. No interpolation/fusion is invented. The window is not synchronization accuracy. |

**Availability and permissions.** Mobile preflight observes real motion/Generic Gyroscope readings before camera capture and displays an info dialog. A missing reading is “unavailable or blocked,” not proof of absent physical hardware. PC inventory records capabilities, actual per-sensor rates, counts and gaps. Camera starts on explicit capture; GNSS is separate opt-in; audio is never requested. Admin and upload-only session keys are separated. ADB controls require local socket/Host/Origin plus admin auth and fixed argument arrays; physical transport and reverse mapping are verified.

**Timing.** One phone monotonic domain, serialized as decimal nanosecond strings. Five NTP-style exchanges retain minimum RTT, resync every 15 seconds and record offset/drift estimates. Frame source is exposed captureTime, presentation estimate or callback estimate. Ingest latency is measured through full body receipt, not through display. Camera buffering, rolling shutter, network asymmetry and browser dispatch remain unmeasured errors. Native Camera2/SensorManager or iOS capture/motion APIs are the upgrade for stronger timing.

**Overload and persistence.** One frame upload in flight; busy/failed target attempts count as skips. Telemetry queue ≤2000, batch ≤500, flush attempted every 100 ms; retried IDs deduplicate. Per-stream sequence gaps and phone buffer drops are distinct, overlapping diagnostics. Metadata/telemetry appends fsync; frame ACK follows writes. Multi-file atomicity/power-loss consistency is not guaranteed. Stop serializes with writes; restart requires fresh pairing. Preview fetches only the newest saved JPEG, independently of slim sensor polling; localhost dashboard avoids a remote round trip.

**Acceptance.** Software/fixture tests and simulated browser capture validate code paths, not hardware. Actual USB authorization/capture, gyro availability, sustained FPS/Hz, capture-to-display experiment, checkerboard/extrinsics and a compliant two-minute replay remain physical acceptance work. Calibration stays null. See [task status](../README.md), [full trade-offs](TRANSPORTS.md) and [stress protocol](STRESS-TEST.md). A smooth preview alone does not pass W1.
