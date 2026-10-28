# Domain and workflow glossary

| Term | Meaning in this project |
|---|---|
| Acquisition | Reading camera/sensors and attaching timestamps; distinct from model inference |
| IMU | Inertial measurement unit; accelerometer and gyroscope streams here; GNSS is separate |
| Accelerometer / specific force | An inertial signal requiring gravity/bias/frame interpretation; not simply vehicle acceleration |
| Gyroscope | Angular velocity in rad/s, not attitude or heading itself |
| GNSS | Satellite navigation family; browser location can also be network/fusion-assisted |
| Reference frame | Coordinate system attached to phone/body, camera, vehicle or world |
| Intrinsics / distortion | Camera projection/lens parameters requiring calibration |
| Extrinsics | Rotation and translation between reference frames, including mount geometry |
| Monotonic clock / domain | A time base tied to a page/device/boot; not interchangeable with wall-clock epoch time |
| Capture timestamp / receive time | Time attached to acquisition versus arrival at the PC |
| Offset / skew / drift | Clock difference, clock-frequency difference and their evolution over time |
| RTT / jitter | Request round-trip duration and variability of delay |
| Ingest latency | Clock-corrected arrival estimate; excludes display stages |
| Capture-to-display latency | Full acquisition-to-screen duration requiring a suitable external measurement |
| Rolling shutter | Different image rows being exposed at different times |
| FPS / Hz | Frames or samples per second; requested, observed and saved rates differ |
| Backpressure | Limiting work when downstream processing/storage cannot keep up |
| ACK / retry / deduplication | Acceptance response, retransmission attempt and suppression of duplicate sequence IDs |
| Sequence gap | Missing received IDs; not a complete measurement of underlying packet loss |
| Bounded queue | Finite buffer whose overflow must be counted rather than silently accumulating latency |
| CSV / JSONL / Parquet | Tabular text, complete JSON messages per line and typed columnar analytic storage |
| Session / manifest | A capture run and its device, timing, calibration and metric metadata |
| Collector token / phone key | PC admin credential and separate per-session upload credential |
| Pairing / preflight | Binding a phone to a session and checking browser sensor access before capture |
| ADB reverse / localhost | Android-to-PC port forwarding and each device's own loopback interface |
| HTTPS tunnel / static hosting | Public transport into a local receiver and delivery of frontend files; neither is the recording store |
| Nearest / interpolation | Selecting an existing nearby sample versus estimating between bracketing samples; only nearest is implemented |
| Replay / acceptance gate | Reproducing saved timestamps and the evidence needed to complete a milestone |
| Semantic segmentation | Per-pixel class labels; two cars can share the same class label without separate identities |
| Instance segmentation | A separate pixel mask for each object instance; two cars have distinct masks/instance IDs |
| Object detection | Class/confidence and a bounding box per detection; a box is not a pixel mask or persistent identity |
| Lane detection | Lane boundaries/centerline or lane-pixel segmentation followed by fitting; boundaries need continuity/geometry checks |
| Relative / learned metric / validated metric depth | Arbitrary scene scale, a model trained to predict meters, and distance independently verified against references; these are different evidence levels |
| KF / EKF | Linear Kalman filter and local linearization for nonlinear dynamics/measurements; the project implements scalar/2D filters and a heading-Jacobian study |
| VO / VIO / SLAM | Visual odometry, visual-inertial odometry and localization with mapping; local VO/attitude experiments and a separate pinned OpenVINS demo exist |
| Ablation | Controlled comparison with a component/cue enabled and disabled |
| Stale age / uncertainty | How old an output is and how uncertain it is; required fields in planned fusion interfaces |
