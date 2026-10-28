# Transport decisions — implemented stack and alternatives

The present goal is inspectable acquisition and reproducible replay. Using the same HTTP application protocol for frames and telemetry does not make their timing/quality requirements identical. The current path is not advertised as low-latency encoded video.

## Actual protocol layers

| Layer | Current implementation |
|---|---|
| Frame application | One JPEG + metadata per HTTP(S) POST; storage acknowledgement; one request in flight |
| Telemetry application | JSON batch POST; flush attempted every 100 ms; batch ≤500; buffer ≤2000; per-type sequence IDs |
| PC receiver | Node HTTP/1.1 over TCP loopback, authentication and exact-origin checks |
| USB route | Phone HTTP localhost → ADB reverse → USB cable → PC loopback HTTP |
| Remote route | Phone HTTPS → tunnel provider/edge → cloudflared → local HTTP collector |
| Tunnel lower layer | Development connector used QUIC/UDP; browser-edge may negotiate HTTP/2 or HTTP/3 |
| Viewer | Independent selected-sensor polling and latest-saved-JPEG polling; local dashboard avoids a WAN read-back hop |

“TCP-based local HTTP collector” is accurate; “the entire path uses TCP” is not. A tunnel's QUIC transport does not mean the application implements a raw UDP telemetry protocol. HTTP, WebSocket and TCP describe different layers.

## USB versus Wi-Fi

| Route | Benefit | Cost / failure mode | Status |
|---|---|---|---|
| USB / ADB reverse | No application WAN hop; same auth/schema/storage/replay; does not need an Internet data path | Android debugging authorization, cable/driver, foreground browser and verified mapping required | Backend and UI implemented; physical acceptance outstanding |
| Wi-Fi/LTE + HTTPS tunnel | Remote QR/link setup without APK/cable; trusted HTTPS | WAN RTT, bandwidth, tunnel uptime; accountless Quick Tunnel URL is temporary | Implemented remote route |
| USB tethering | Provides a network interface | Requires separate routing/discovery/trusted-HTTPS setup | Not automated; not the same as ADB reverse |

USB does not improve hardware timestamp accuracy, add a missing gyro or guarantee browser sampling rates. Compare actual achieved metrics with matched settings rather than claiming 30 FPS/100 Hz from the transport choice.

## Frame transport: MJPEG / RTSP / WebRTC

**Current protocol: custom timestamped JPEG HTTP(S) POST. Standard MJPEG, RTSP and WebRTC are not implemented.** A sequence of JPEG uploads is not a `multipart/x-mixed-replace` MJPEG stream. If the plan requires one of the named protocols strictly, this is an explicit **DEVIATION** to accept or replace.

| Option | Used? | Benefits | Trade-offs / reason not selected |
|---|---|---|---|
| **JPEG HTTP(S) POST** | **Yes** | Browser fetch; dependency-free receiver; explicit index/time/source; independent replay files; storage ACK | No inter-frame compression; per-frame encode/upload/ACK limits bandwidth/throughput. Chosen for a simple storage-first acquisition prototype |
| MJPEG | No | Persistent multipart response; frames independently decodable; can reduce request overhead | Still needs a browser-camera publisher/bridge, metadata correlation, auth/backpressure design; high bandwidth remains |
| RTSP/RTP | No | Native camera/FFmpeg/GStreamer ecosystem; media timestamps and stream control | Ordinary mobile browser is not an RTSP publisher/player; native app/bridge, decoder and routing work required. RTSP controls sessions; media can use RTP over UDP/TCP |
| WebRTC | No; live-preview upgrade candidate | Browser-native real-time media, compression and congestion control; potentially direct browser-to-browser path | Signaling, ICE/STUN and sometimes TURN; archive recording and frame↔IMU correlation remain separate; codec/jitter buffers are not zero latency |

For smooth remote preview, WebRTC plus a separately specified archival path is the stronger design fit. That upgrade must distinguish preview delivery from confirmed disk persistence. RTSP implies a native/bridge decision; MJPEG still needs a persistent publisher/receiver and metadata contract. These are future options, not hidden existing features.

### Latency and implemented optimizations

With one frame in flight, best-case saved throughput is limited approximately by `1 / (encode + upload + storage + ACK duration)`. A measured high tunnel RTT does not support a claimed 15 FPS just because the target selector says 15. Enlarging a stale-frame queue can worsen live delay.

The current implementation reduces avoidable overhead:

1. Fixed `/frame` URL and `X-Frame-Meta` header instead of a unique query URL per frame. Successful CORS preflights advertise 600-second reuse; browsers may impose their own limits.
2. Chart responses contain only the selected sensor's most recent 150 samples; accepted recording data remains intact.
3. Image requests do not wait for telemetry; the newest saved JPEG is served from memory and unchanged frames return bodyless 204.
4. The localhost PC dashboard reads control/chart/image traffic locally; phone traffic uses the configured USB or HTTPS route.

Smaller capture width can reduce bandwidth. A lower target FPS reduces attempted opportunities, not necessarily transaction delay. Record actual camera dimensions and achieved rates; portrait dimensions may differ from selector labels. Ingest latency is not full capture-to-display latency.

## Telemetry transport: UDP / WebSocket / TCP

The application uses **HTTP(S) JSON batch POST into a TCP-based HTTP collector**. No custom TCP framing, raw UDP sender or WebSocket channel is implemented.

| Option | Used? | Benefits | Trade-offs / decision |
|---|---|---|---|
| **HTTP(S) batches** | **Yes** | Ordinary browser API, existing auth/CORS, inspectable JSON, batch ACK and bounded retry/dedup | Request/response overhead and queue pressure under high RTT; chosen for initial receiver simplicity |
| UDP datagrams | No | Low native-sender overhead; delayed data can be discarded | Ordinary browser has no raw UDP socket; loss/reordering/MTU, security, congestion control and NAT/firewall behavior need a protocol; reliable archive requires additional work |
| WebSocket / WSS | No | Persistent duplex browser channel can reduce per-message HTTP overhead | Generally retains TCP ordered-stream/head-of-line behavior; still needs bounded buffers, reconnect/resume, ACK/dedup and server upgrade handling |
| Custom TCP sockets | No | Native applications can control framing and batching | Ordinary browser cannot open raw TCP; native app/bridge needed. TCP preserves bytes, not message boundaries; explicit framing/lifecycle required |

A successful batch ACK confirms accepted writes. Retries preserve sequence IDs; duplicate/out-of-order samples are suppressed. There is no exactly-once or lossless guarantee across arbitrary outages. Bounded-buffer drops and received sequence gaps can overlap; do not add them as unique packet loss. TCP retransmissions may hide underlying network loss from application sequence counters.

## Recording and durability

| Format | Current role | Benefit | Cost |
|---|---|---|---|
| CSV | Live IMU and GNSS | Inspectable table, common analysis tools | Nested metadata/types need an external contract |
| JSONL | Canonical telemetry, frame and clock metadata | Complete optional fields and provenance | Text overhead and limited columnar query performance |
| JPEG files | Accepted camera frames | Independent replay and inspection | Many files, high bandwidth/storage; not RAW/Bayer |
| Parquet | Optional finalized-session conversion | Typed times/nulls, compression and columnar analysis | Python/PyArrow dependency and offline conversion step; no live append |

Metadata/telemetry fsync remains enabled; disabling it to claim a speedup would change durability semantics. Handled write failures restore affected log lengths before allowing a retry; sequence counters and sample metrics advance only after successful storage. Failed frame writes also attempt JPEG cleanup. If log rollback fails, the session rejects further mutations until the collector is restarted and the files inspected. These recovery steps do not make JPEG writes and metadata appends crash-atomic. Power-loss consistency is not guaranteed.

## When to revisit the decision

- Missing gyro or insufficient browser rates: evaluate native acquisition or suitable hardware.
- Encoding/storage dominates even over USB: profile measured stages and consider native encoding/recording.
- Remote live latency dominates: evaluate WebRTC preview with explicit timestamp correlation and archive semantics.
- Telemetry RTT/buffering limits target rate: design and test WSS ACK/reconnect/queue behavior.
- Exposure-time accuracy is mandatory: implement a native acquisition path and validate clock domains; do not relabel callback estimates as hardware timestamps.

## Primary references

- [WebRTC](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API), [RTSP RFC 7826](https://www.rfc-editor.org/rfc/rfc7826), [MJPEG multipart type](https://www.iana.org/assignments/media-types/multipart/x-mixed-replace).
- [WebSocket](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket), [TCP RFC 9293](https://www.rfc-editor.org/rfc/rfc9293), [UDP RFC 768](https://www.rfc-editor.org/rfc/rfc768).
- [Cloudflare connector protocols](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/cloudflared-parameters/run-parameters/), [CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS).
- [ADB](https://developer.android.com/tools/adb), [ADB reverse/local server](https://developer.android.com/develop/ui/views/layout/webapps/access-local-server), [Parquet](https://arrow.apache.org/docs/python/parquet/parquet.html).
