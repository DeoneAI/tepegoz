# Acquisition contract

This document describes the implemented browser client and PC receiver. It does not claim native Android Camera2/SensorManager access or completed hardware acceptance.

## Where information appears

| Information | Documentation | Mobile client | PC dashboard / manifest |
|---|---|---|---|
| Sensor meaning, units, frames and API limits | Full contract | Short pre-capture explanation | Axis/unit labels |
| Availability and permissions | Detection limits | Check sensors and result dialog | Reported capabilities |
| Rates | Requested vs measured definitions | Probe rates and capture accel rate | Per-sensor received Hz/count/gaps |
| Privacy and retention | Data-flow description | Explicit camera/motion access and optional location | Local recording files and metadata |

## Sensor inventory

| Stream | Values / reference frame | API | Rate and quality |
|---|---|---|---|
| RGB camera | JPEG image coordinates; camera/vehicle transform uncalibrated | `getUserMedia`, video-frame callbacks, canvas JPEG | Ideal camera 30 FPS; JPEG target 10/15/30, actual settings and saved FPS recorded separately |
| Accelerometer | x/y/z m/s² including gravity; portrait phone +X right, +Y top, +Z out | `accelerationIncludingGravity` | Browser event rate; hardware accuracy unavailable |
| Linear acceleration | x/y/z m/s² in phone frame | `DeviceMotionEvent.acceleration` | Optional browser gravity-compensated estimate, not an independently calibrated native signal |
| Gyroscope | x/y/z rad/s in phone frame | `rotationRate` or real Generic `Gyroscope` | Map beta/gamma/alpha to X/Y/Z and convert deg/s × π/180; Generic API requests 60 Hz, achieved rate is measured |
| GNSS/location | Latitude/longitude deg, altitude m, speed m/s, heading deg; WGS84 | `watchPosition` | Callback rate, horizontal accuracy and optional altitude accuracy; fixes may be fused/network-assisted |
| Other sensors | Not collected | No magnetometer/barometer/vendor-sensor pipeline | Absence of implementation is not absence of hardware |

Camera access begins on capture. The explicit sensor check reads motion before recording; it does not start camera capture or collect a location fix. GNSS requires a separate opt-in; audio is never requested. Browser hardware accuracy is not fabricated.

## Preflight and missing gyroscopes

Check sensors observes real finite motion readings for approximately 1.8 seconds, attempts Generic Gyroscope where supported, reads permission states and stops its test listeners/sensors. Zero angular velocity is a valid finite reading. Probe samples are not appended to the recording.

States include `available`, `permission-denied`, `insecure-context` and `unavailable-or-blocked`. No usable browser reading does **not** prove physical absence: hardware, browser support, OS policy and permission can be indistinguishable. `NotReadableError` is also not a definitive native inventory result. A native Android sensor query and the exact device specification are the stronger checks.

The dialog permits explicit continuation with available sensors, while leaving the full IMU gate unmet. Capabilities are sent with device metadata when capture begins. Real Generic Gyroscope readings can be used as a fallback when DeviceMotion does not expose rotation; orientation is not differentiated into invented gyro data.

## Browser and native API boundary

| Option | Benefit | Cost / status |
|---|---|---|
| Current custom browser client | Link-based setup, shared auth/schema/replay, no APK distribution | Hardware time/accuracy and background rates are constrained; implemented |
| Android Camera2 + SensorManager + Location APIs | Native camera metadata, sensor inventory/accuracy and greater sampling control | APK, lifecycle, permissions and clock-domain validation; not implemented |
| iOS AVFoundation + Core Motion + Core Location | Native camera/motion access | Separate signed app and platform-specific timing/permissions; not implemented |
| Existing tools such as phyphox | Independent sensor inventory, remote access and export | Adapter and correlation tests needed for this camera/IMU contract; research alternative |

Native is not automatically synchronized: Android `SensorEvent.timestamp` shares `elapsedRealtimeNanos()` time base; Camera2 REALTIME timestamps can be compared to that base, while UNKNOWN timestamps do not provide accurate cross-subsystem comparison. Native high-rate sensor permission rules do not grant the browser an equivalent rate.

References: [Android sensors](https://developer.android.com/develop/sensors-and-location/sensors/sensors_overview), [SensorEvent](https://developer.android.com/reference/android/hardware/SensorEvent), [Camera2 timestamp sources](https://developer.android.com/reference/android/hardware/camera2/CameraMetadata), [Apple AVFoundation](https://developer.apple.com/av-foundation/), [Core Motion](https://developer.apple.com/documentation/coremotion/cmdevicemotion), [phyphox](https://phyphox.org/docs/remote-interface/), [browser Sensor APIs](https://developer.mozilla.org/en-US/docs/Web/API/Sensor_APIs).

## Telemetry schema v2

```json
{
  "session_id": "0123456789abcdef01234567",
  "sensor_type": "gyroscope",
  "timestamp_ns": "123456789000",
  "sequence_id": 42,
  "frame_axes": "phone_portrait_x_right_y_up_z_out",
  "values": {"x": 0.01, "y": -0.02, "z": 0.03},
  "units": "rad_s",
  "quality": "browser_accuracy_unavailable",
  "timestamp_source": "browser_event_time"
}
```

| Field | Contract |
|---|---|
| `session_id` | 24 hex characters, matching the request route |
| `sensor_type` | `accelerometer`, `linear_acceleration`, `gyroscope`, `gnss` |
| `timestamp_ns` | Decimal string in the phone monotonic domain, not Unix time; nanosecond units are not precision claims |
| `sequence_id` | Per-type nonnegative integer starting at zero; retry preserves the ID |
| `frame_axes` | IMU `phone_portrait_x_right_y_up_z_out`; GNSS `wgs84_geodetic` |
| `values` | Finite IMU x/y/z; GNSS latitude/longitude with optional altitude/speed/heading; missing optional values are null |
| `units` | Type-consistent `m_s2`, `rad_s` or `deg_m_mps` |
| `quality` | Browser IMU `browser_accuracy_unavailable`; GNSS `browser_geolocation_accuracy` |
| `accuracy_m` | Required nonnegative horizontal uncertainty for GNSS |
| `altitude_accuracy_m` | Optional GNSS vertical uncertainty |
| `timestamp_source` | Browser event, Generic Sensor monotonic time, or GNSS wall-to-monotonic estimate |
| `server_receive_ns` | Added by the PC; a separate clock domain requiring offset correction |

The receiver validates fields, finite values, units, axes and session binding. Sequence IDs suppress duplicates/out-of-order samples. Format validation does not establish hardware timing accuracy. Historical v1 recordings can be replayed; sender/receiver upgrades should use a fresh session.

## Rates, clocks and associations

Received per-sensor Hz is `(N−1)/(last_phone_time−first_phone_time)` for at least two samples; otherwise it is null. It describes accepted samples across their phone-time span, not the hardware's nominal rate. Setup delay is excluded. Saved video FPS remains an average over session duration.

Phone messages use one page-monotonic clock. Five NTP-style exchanges estimate server-minus-phone offset; retain minimum RTT and repeat every 15 seconds. `offset=((t1−t0)+(t2−t3))/2`; `RTT=(t3−t0)−(t2−t1)`. A PC boot ID separates server clock epochs. GNSS wall timestamps are converted to labeled monotonic estimates.

RTT/2 is a symmetric-path uncertainty estimate, not a complete bound on network asymmetry, event dispatch, rolling shutter or camera buffering. Frame time uses exposed captureTime, otherwise presentation/callback estimates. Ingest latency covers full body receipt, not PC display fetch/decode/scanout.

Replay selects the nearest same-clock sample per sensor type, with maximum ±100 ms mismatch and explicit missing values/deltas. No interpolation hides gaps. The window is not a hardware synchronization guarantee. Intrinsics/distortion/extrinsics remain null until measured.

The [coordinate-frame and timing guide](FRAMES-AND-TIMING.md) diagrams phone/body, camera, vehicle and world conventions. The offline analyzer exports same-phone-clock frame↔sensor matches and shared-time plots from finalized sessions; real-device plots and calibration evidence are still required.

## Authentication, storage and overload

The collector token grants PC control/read access; a separate phone key grants upload to one session. Phone fragments are removed from the address bar after loading and retained in tab sessionStorage. USB management requires admin auth plus local socket/Host/Origin and fixed ADB argument arrays. Localhost pairing is permitted only for the explicit same-origin USB mode; ordinary LAN HTTP does not receive that exception.

One JPEG request may be in flight; busy/failed target opportunities are counted as skips. Telemetry attempts to flush every 100 ms, with batches up to 500 and a buffer up to 2000 samples. Timeouts retry bounded telemetry with the same IDs. Sequence gaps and buffer drops can overlap; TCP retransmissions are not application sequence gaps.

Metadata/telemetry appends fsync and frame ACK follows completed writes. Sequence counters and received-sample metrics commit only after storage succeeds. A handled write failure restores affected log lengths and attempts to remove an unacknowledged JPEG so the same sequence IDs can be retried. If log rollback itself fails, further session mutations return 503 and require inspection. Multi-file atomicity and power-loss consistency are not guaranteed.

Phone Stop awaits the active telemetry request, then makes up to four batch-flush attempts. If samples remain queued, capture stays stopped and a retry button is shown; keep the tab open and retry before PC Stop & save finalizes. A session that has already ended reports unsent samples explicitly. This queue remains in memory, not durable browser storage. Restart invalidates upload keys; raw recordings remain local. Parquet conversion is optional and post-finalization, preserves int64 times/nulls, checks row count and leaves raw logs unchanged.
