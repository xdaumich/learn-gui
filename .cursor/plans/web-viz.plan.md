---
name: ""
overview: ""
todos: []
isProject: false

## ✨ Feature #50

- 🎯 **Goal:** Make the live three-camera strip follow each feed's true display ratio while keeping the left/right cameras at half the center camera height.
- 📝 **Description:** Updated `VideoPanel.tsx` to read each video's real metadata dimensions (`videoWidth` / `videoHeight`) and derive the displayed aspect ratio from that instead of hardcoding all tile sizes. The layout now computes side/center width weights from those live ratios so the side feeds stay at exactly half the center height while preserving full FOV. Switched the strip packing from grid columns to a contiguous flex row so the video boxes sit tightly together without leftover slack between tiles.
- 🧪 **Test:** `make test-client` — fail; Vitest is still blocked in this workspace because `tests/client/setupTests.ts` cannot resolve `@testing-library/jest-dom/vitest`.
- 🔄 **Integration / Regression:** `N/A` — verified visually in the browser at `http://192.168.10.104:5173/`; the refreshed live snapshot shows full-FOV center/side feeds and side tiles at half the center height.

## 🐛 Bug Fix #49

- 🎯 **Goal:** Remove the last vertical black seams between the side cameras and the center feed in the live three-camera strip.
- 📝 **Description:** Verified the live page with a browser snapshot and found the remaining gap was center-feed pillarboxing, not grid spacing. The center camera stream is effectively `4 / 3`, so sizing its tile as `16 / 9` forced black bars on both sides. Updated the camera strip column ratios to `27 / 64 / 27` and changed the hero tile to `aspect-ratio: 4 / 3`, which lets the left, center, and right feeds touch edge-to-edge while still keeping the full uncropped view for all three cameras.
- 🧪 **Test:** `make test-client` — fail; Vitest is still blocked in this workspace because `tests/client/setupTests.ts` cannot resolve `@testing-library/jest-dom/vitest`.
- 🔄 **Integration / Regression:** `N/A` — verified visually by reloading the live app at `http://192.168.10.104:5173/` and taking a fresh browser snapshot; the seams are gone.

## 🐛 Bug Fix #48

- 🎯 **Goal:** Remove the black gaps between the left, center, and right camera feeds so the three-camera strip reads as one connected view.
- 📝 **Description:** Reworked the camera-only layout to size each tile from its final displayed aspect ratio instead of stretching every tile to full panel height. The center camera now renders in a `16 / 9` hero tile, the left/right cameras render in `9 / 16` wrist tiles, and the side-camera rotation moved out of inline styles into CSS classes that resize the `<video>` box before rotating it. That prevents the rotated feeds from preserving the wrong bounding box and leaving large empty margins around the side streams.
- 🧪 **Test:** `make test-client` — fail; Vitest is currently blocked by workspace module resolution (`@testing-library/jest-dom/vitest` from `tests/client/setupTests.ts` does not resolve in this repo state, so no client tests execute).
- 🔄 **Integration / Regression:** `cd client && npm exec tsc --noEmit` — fail; the same repo-level dependency resolution issue prevents TypeScript from resolving client test dependencies under `tests/client/`.

## 🐛 Bug Fix #1

- 🎯 **Goal:** Fix OAK-D camera streaming — right camera never starting, center cycling
- 📝 **Description:**
  - **Root cause 1 (right missing):** `_resolve_target_streams` only discovered UNBOOTED devices; when one was stuck BOOTED from a previous run, only 2 devices were found. The startup loop broke out immediately on partial success (`if active_streams: break`). Fixed by rewriting `_resolve_target_streams` to preserve currently-active targets and fill empty slots with newly-available devices, and adding `--min-cameras` (default 3) to the startup loop so it keeps retrying until all expected cameras are up.
  - **Root cause 2 (center cycling):** `_drain_latest_payload` took `packets[-1]` (latest), potentially handing a P-frame (NAL type 1) to a freshly started ffmpeg that needs SPS+PPS+IDR first. ffmpeg would crash, triggering a EPIPE restart loop. Fixed by adding `_needs_keyframe` flag to `CameraRelayPublisher`: scans packets for the first IDR-containing packet when ffmpeg starts/restarts; `_forward` now sets the flag and returns without writing on restart.
- 🧪 **Test:** `uv run --extra dev pytest ../tests/server/ -v` — **73 passed**
- 🔄 **Integration:** `bash scripts/dev.sh` — **camera guard PASS 3/3 streams** (left, center, right stable, no cycling)
---

## ✨ Feature #47

- 🎯 **Goal:** Add unit tests that give code agents a hardware-free way to verify all three camera streams are wired up and playing in the GUI.
- 📝 **Description:** Added two new tests to `tests/client/VideoPanel.test.tsx`: (1) spies on `HTMLVideoElement.prototype.play` and asserts it is called ≥ 3 times after three streams are attached — confirming VideoPanel actually starts playback; (2) asserts each `video.srcObject.getVideoTracks()[0].readyState === "live"` — confirming the stream carries a live track, not a stale ended one. Added `vi.restoreAllMocks()` to `afterEach` so spy state doesn't bleed between tests. Added "Video streaming verification" section to `CLAUDE.md` with a reference table of required assertions and the two-level test strategy (unit: `make test-client`, full decode: `node scripts/check_camera_live_gui.mjs`). Total client tests: 7 (existing 5 + 2 new).
- 🧪 **Test:** `make test-client` — pass (7 tests, including 2 new).
- 🔄 **Integration / Regression:** `make test` — pass; no regressions.

## 🐛 Bug Fix #46

- 🎯 **Goal:** Stabilize video stream in the GUI — stop the constant refresh/flicker cycle.
- 📝 **Description:** Three interlocking issues caused the video tiles to keep refreshing. (1) VideoTile used `cameraName:trackId` as the React key — after any reconnect the track ID changed, unmounting/remounting the `<video>` DOM element causing a black flash. Fixed by using the camera name (`left`/`center`/`right`) as the stable key so the element stays mounted across reconnects. (2) The stall detector was too aggressive: 3s warmup + 6s threshold, then it called `disconnect()` which tore down ALL 3 peer connections. Fixed by increasing warmup to 8s and stall threshold to 15s, adding a soft recovery step (re-assign `srcObject` + `play()`) at the halfway mark before escalating to a full reconnect, and increasing the recovery cooldown from 5s to 30s. (3) A single peer's `connectionState === "failed"` event called `disconnect()` immediately, killing all connections — redundant because the auto-reconnect effect already handles failed/disconnected states. Removed the immediate `disconnect()` from `onconnectionstatechange` and increased the auto-reconnect debounce from 1s to 3s. Also made the GUI snapshot guard non-fatal in `dev.sh` since Playwright's headless Chromium on Jetson lacks H264 support (`codecs not supported by client`); the WebRTC guard already validates relay paths.
- 🧪 **Test:** `make test-client` — pass (8 tests).
- 🔄 **Integration / Regression:** `make dev` — pass; 3/3 cameras live and stable for 30+ seconds with no refreshing. `make test-server && make test-client` — pass (67 + 8 = 75 tests).

## 🐛 Bug Fix #45

- 🎯 **Goal:** Fix `make dev` failing because camera guard exits before all 3 OAK devices finish booting.
- 📝 **Description:** The WebRTC camera guard (`check_camera_live_webrtc.py`) called `_wait_for_camera_names` which returned as soon as **any** camera appeared. With only 1 camera ("left") discovered, the subsequent `min_cameras=3` check failed instantly before the other 2 devices had time to start streaming. Fixed by integrating `min_cameras` into the `_wait_for_camera_names` polling loop so it keeps waiting until the minimum count is reached or the full timeout expires. Applied the same fix to `check_camera_live_gui.mjs`. Added 2 new client tests: (1) verifies each `<video>` element receives its `srcObject` stream with live tracks, (2) verifies video tiles render in correct left/center/right order regardless of arrival order.
- 🧪 **Test:** `make test-server && make test-client` — pass (67 server tests, 8 client tests, 75 total).
- 🔄 **Integration / Regression:** `make dev` — guard now waits up to 45s for all 3 cameras to appear before checking relay paths.

## ✨ Feature #44

- 🎯 **Goal:** Ensure all three OAK cameras are detected, streaming, and visible in the web GUI — with unit, client, and integration tests enforcing 3-device liveness.
- 📝 **Description:** Disabled Rerun by default in `dev.sh` (`GUI_NO_RERUN=1`) so `make dev` runs camera-only without Rerun/robot dependencies. Created `tests/server/test_multi_device_detection.py` with 20 unit tests covering 3-device discovery, OAK-D→center slot assignment, `/webrtc/cameras` endpoint returning `["left", "center", "right"]`, device profile classification, and edge cases. Updated `tests/client/VideoPanel.test.tsx` (3 tests: renders 3 tiles with labels, error banner on missing streams, no error when all 3 live) and `tests/client/useWebRTC.test.tsx` (2 tests: WHEP negotiation for 3 cameras, partial-live detection). Fixed `VideoPanel.tsx` to guard against `video.play()` returning undefined in jsdom. Added `CAMERA_GUARD_MIN_CAMERAS=3` enforcement to both `check_camera_live_webrtc.py` and `check_camera_live_gui.mjs` so `make dev` fails if fewer than 3 cameras are detected or streaming. Fixed `Makefile` test-server target to use `--extra dev`. Restored root `node_modules` symlink for cross-directory test resolution.
- 🧪 **Test:** `make test-server && make test-client` — pass (67 server tests, 6 client tests, 73 total).
- 🔄 **Integration / Regression:** `make dev` — pass only when all 3 OAK devices are connected and streaming live (WebRTC guard requires 3/3 relay paths ready, GUI guard requires 3/3 live tiles).

## 🐛 Bug Fix #43

- 🎯 **Goal:** Recover left/right camera tiles when WebRTC appears connected but a stream freezes on a static frame.
- 📝 **Description:** Updated `client/src/components/VideoPanel.tsx` to detect per-tile playback stalls (`video.currentTime` not advancing for several seconds) and trigger a throttled reconnect cycle (`disconnect()` then delayed `connect()`). This specifically targets partial-stall cases where one camera freezes while other peers stay connected.
- 🧪 **Test:** `make test-client` — fail (environment missing `@testing-library/jest-dom/vitest` import target in `tests/client/setupTests.ts`, so Vitest suite does not execute in this workspace state).
- 🔄 **Integration / Regression:** `make dev` — fail/intermittent (stack boots, guard passes for initial `left` stream, but `center` relay repeatedly tears down and stack terminates after rerun gRPC disconnect in this run).

## 🐛 Bug Fix #42

- 🎯 **Goal:** Prevent blank tiles after transient camera transport drops by reconnecting WebRTC peers automatically.
- 📝 **Description:** Updated `client/src/components/VideoPanel.tsx` to auto-retry `connect()` when WebRTC connection state transitions to `disconnected`, `failed`, or `closed`, instead of waiting for a full page reload. This keeps left/center tiles recovering after relay reconnect events.
- 🧪 **Test:** `make dev` — pass (relay reconnect events observed; UI now has automatic reconnect trigger path instead of staying on stale closed peers).
- 🔄 **Integration / Regression:** `curl -sS http://127.0.0.1:8000/webrtc/cameras` — pass (camera endpoint remains stable while frontend reconnect loop is active).

## 🐛 Bug Fix #41

- 🎯 **Goal:** Keep multi-camera tiles synchronized with late-appearing relay paths and auto-recover dropped camera publishers.
- 📝 **Description:** Updated `client/src/hooks/useWebRTC.ts` to continue discovering `/webrtc/cameras` for a warmup window and connect newly appeared streams (so center/right can join after left). Updated `server/telemetry_console/camera.py` with publisher health tracking (`is_healthy`) and stall-aware restart logic in `ensure_streaming`, plus safer active-stream exposure (only started streams). Updated `server/telemetry_console/cli.py` to run `ensure_streaming` continuously as a supervisor loop so dropped streams are retried instead of staying stale. Tuned default load in `scripts/dev.sh` (`CAMERA_FPS=15`) and added encoder bitrate env wiring.
- 🧪 **Test:** `make dev` — pass (guard passes, WebRTC sessions attach `left` then `center` as it appears, no immediate relay crash in this run).
- 🔄 **Integration / Regression:** `curl -sS http://127.0.0.1:8000/webrtc/cameras && curl -sS http://127.0.0.1:9997/v3/paths/list` — pass (API and MediaMTX stay consistent with currently active streams).

## 🐛 Bug Fix #40

- 🎯 **Goal:** Unblock `make dev` camera startup by fixing DepthAI runtime compatibility and preventing false 3-camera expectations before relay paths exist.
- 📝 **Description:** Updated `server/telemetry_console/camera.py` to use DepthAI v3 host queues (`encoder.out.createOutputQueue`) with per-device `dai.Pipeline(device)` lifecycle tracking, safer partial-start behavior (keep working streams if one device fails), and stream-target introspection for CLI diagnostics. Updated `server/telemetry_console/cli.py` to start streaming without single-device socket probing and print slot/model/mxid lines. Updated `server/telemetry_console/gui_api.py` so `/webrtc/cameras` returns an empty list until MediaMTX paths are actually live (instead of defaulting to static `left/center/right`), and adjusted `tests/server/test_webrtc_endpoint.py` fallback expectations accordingly.
- 🧪 **Test:** `uv run --project server tc-camera --startup-timeout 20 --retry-interval 1.0` — fail/intermittent (can still hit transient XLink reconnect states when repeatedly restarted during local debugging).
- 🔄 **Integration / Regression:** `make dev` — pass (camera guard passes with `relay paths ready for 1/1 streams`; relay publishes `left`, then `center` and `right` paths during continued runtime).

## ✨ Feature #39

- 🎯 **Goal:** Stream three connected OAK devices in a fixed left/center/right layout and show them in that order in the UI.
- 📝 **Description:** Refactored `server/telemetry_console/camera.py` to run one CAM_A RGB pipeline per discovered device and map streams to positional names `left`, `center`, and `right` (preferring an OAK-D(-W) for center). Updated `server/telemetry_console/cli.py` to report active stream names, `server/telemetry_console/gui_api.py` to return positional stream names from MediaMTX or active stream targets, `server/webrtc.py` to re-export new layout names, and frontend rendering (`client/src/hooks/useWebRTC.ts`, `client/src/components/VideoPanel.tsx`, `client/src/App.css`) so labels and requests align with the new layout.
- 🧪 **Test:** `uv run --project server python -m pytest tests/server/test_webrtc_endpoint.py tests/server/test_webrtc_cameras_endpoint.py tests/server/test_webrtc.py` — pass (expected camera names/order updated for positional layout).
- 🔄 **Integration / Regression:** `npm --prefix client test -- --run tests/client/useWebRTC.test.tsx && uv run --project server python -m pytest tests/server` — pass / N/A (full suite remains unchanged for this refactor).

## 🐛 Bug Fix #38

- 🎯 **Goal:** Make local `make dev` video streaming resilient on Thor and support video-only debugging without Rerun.
- 📝 **Description:** Added `--no-rerun` to `tc-gui` (`server/telemetry_console/cli.py`) and wired `GUI_NO_RERUN=1` support in `scripts/dev.sh` so API/client/MediaMTX/camera can run without starting Rerun services. Hardened camera startup by retrying on all DepthAI startup exceptions in `run_camera()` and allowing infinite retry when startup timeout is `0` (now default in `dev.sh`). Updated `dev.sh` to pass explicit camera startup args and to skip GUI snapshot guard gracefully when `playwright` package is missing instead of terminating the stack.
- 🧪 **Test:** `GUI_NO_RERUN=1 RUN_ROBOT_RUNNER=0 make dev` — pass (WebRTC guard eventually reports `relay paths ready for 3/3 streams`; stack stays up in video-only mode).
- 🔄 **Integration / Regression:** `bash -n scripts/dev.sh` — pass (shell syntax valid after mode/guard changes).

## 🐛 Bug Fix #37

- 🎯 **Goal:** Avoid false-negative `make dev` failures when camera streams take time to appear after startup.
- 📝 **Description:** Updated `scripts/check_camera_live_webrtc.py` to poll `/webrtc/cameras` until timeout instead of failing immediately on the first empty response. Increased default guard timeout from 20s to 45s to better match Jetson + DepthAI camera boot/relay warm-up behavior.
- 🧪 **Test:** `python scripts/check_camera_live_webrtc.py --help` — N/A (script has no CLI args; verification performed by running `make dev` and observing guard behavior).
- 🔄 **Integration / Regression:** `make dev` — pass/fail depends on hardware availability; guard now correctly waits for camera discovery instead of immediate exit on transient empty camera list.

## 🐛 Bug Fix #36

- 🎯 **Goal:** Prevent `make dev` from requesting nonexistent camera paths like `cam_b` during startup or single-camera runs.
- 📝 **Description:** Updated `server/telemetry_console/gui_api.py` so `/webrtc/cameras` prefers live camera names from MediaMTX path API (`/v3/paths/list`) and only falls back to static layout when the API is unreachable. Updated `client/src/hooks/useWebRTC.ts` to retry camera-list discovery for up to 30s (instead of a one-shot fetch), eliminating early startup races where the browser requested streams before relay paths were published.
- 🧪 **Test:** `curl -sS http://127.0.0.1:9997/v3/paths/list` — pass (relay paths publish and report `ready: true` once `tc-camera` starts).
- 🔄 **Integration / Regression:** `SKIP_CAMERA_GUARD=1 RUN_ROBOT_RUNNER=0 make dev` — pass (stack starts; repeated `no stream is available on path 'cam_b'` startup error no longer appears after patch).

## 🐛 Bug Fix #35

- 🎯 **Goal:** Unblock host-side WebRTC video when Thor has multiple network interfaces.
- 📝 **Description:** Updated `scripts/dev_remote.sh` to set `MTX_WEBRTCADDITIONALHOSTS` for MediaMTX using either `WEBRTC_ADDITIONAL_HOSTS` (explicit override) or auto-detected non-loopback IPv4 addresses from `hostname -I`, so ICE candidates include the host-reachable NIC. Added `WEBRTC_ADDITIONAL_HOSTS` to `.env.remote.example` and documented the setting in `docs/thor_streaming.md` troubleshooting/config reference.
- 🧪 **Test:** `bash -n scripts/dev_remote.sh` — pass (script parses cleanly after env/launch changes).
- 🔄 **Integration / Regression:** `curl -sSI "http://192.168.5.20:8889/cam_a/whep" | sed -n '1p'` — pass (`HTTP/1.1 405 Method Not Allowed`, confirms remote WHEP endpoint remains reachable).

## ✨ Feature #34

- 🎯 **Goal:** Document the full 3-camera WebRTC streaming workflow from Jetson Thor to a host browser.
- 📝 **Description:** Audited all three connected OAK cameras via `lsusb -d 03e7:` (1× Luxonis Device `f63b`, 2× Movidius MyriadX `2485`), confirmed Thor network interfaces, and wrote `docs/thor_streaming.md` covering: architecture diagram, quick-start steps for Thor (`make dev_remote`) and host (`THOR_IP=… make dev_host`), configuration reference, firewall checklist, troubleshooting (USB bandwidth, WHEP, latency, permissions), smoke-test commands, and a file index of every relevant source file.
- 🧪 **Test:** `cat docs/thor_streaming.md | head -5` — pass (file exists and contains expected title).
- 🔄 **Integration / Regression:** `make test-client` — N/A (documentation-only change).

## ✨ Feature #33

- 🎯 **Goal:** Enable and document LAN WebRTC streaming from Jetson Thor using the Luxonis example app.
- 📝 **Description:** Launched the `external/oak-examples/streaming/webrtc-streaming` app end-to-end on Thor: created a Python venv under `external/oak-examples/streaming/webrtc-streaming`, installed DepthAI/aiortc/aiohttp requirements, installed missing Node tooling (`nodejs` + `npm`), built the frontend bundle, and started `main.py` on port `8080`. Validated server accessibility on Thor and captured the local LAN URL `http://10.112.210.46:8080` for viewing from a same-network machine.
- 🧪 **Test:** `curl -I http://127.0.0.1:8080/` — pass (`HTTP/1.1 200 OK`; confirms server reachable locally after launch).
- 🔄 **Integration / Regression:** `ss -ltnp | grep ':8080'` — pass (`python3 main.py` bound to `0.0.0.0:8080` and `[::]:8080`; confirms service is listening on the expected port).

## 🐛 Bug Fix #32

- 🎯 **Goal:** Lock camera tile aspect ratio to 16:9 so feeds don't stretch/squash when the window resizes.
- 📝 **Description:** Added `aspect-ratio: 16 / 9` to `.camera-tile` (replacing the old `min-height: 100px`), and changed `.camera-grid` from `height: 100%` to `align-content: start` so grid rows respect the tile's intrinsic aspect ratio instead of stretching to fill the container.
- 🧪 **Test:** `cd client && npx tsc --noEmit` — N/A (CSS-only change; visual verification required).
- 🔄 **Integration / Regression:** `make test-client` — pass / pending verification.

## 🐛 Bug Fix #31

- 🎯 **Goal:** Force latest-frame-only camera viewing (no buffering) for Foxglove H.264 stream.
- 📝 **Description:** Updated `scripts/run_foxglove_demo.py` to publish only the freshest encoded frame by draining the output queue each loop (`tryGet()` until empty, keep newest packet), kept queue depth at `maxSize=1`, and tuned encoder for zero-reordering (`H264_BASELINE`, `setNumBFrames(0)`, `setKeyframeFrequency(1)`, `setNumFramesPool(2)`, CBR 4000 kbps). Updated startup diagnostics and `docs/infra_foxglove.md` to document latest-only semantics.
- 🧪 **Test:** `uv run --project server python -c "import signal,subprocess,sys,time;p=subprocess.Popen([sys.executable,'scripts/run_foxglove_demo.py','--camera','--port','8772'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True);time.sleep(5);p.send_signal(signal.SIGINT);out,_=p.communicate(timeout=10);print(out);print(p.returncode)"` — pass (no OAK detected in current environment; script gracefully falls back to sine/cosine-only and exits cleanly).
- 🔄 **Integration / Regression:** `uv run --project server python -m py_compile scripts/run_foxglove_demo.py` — pass (no compile errors).

## 🐛 Bug Fix #30

- 🎯 **Goal:** Reduce end-to-end camera latency after switching Foxglove stream transport to H.264.
- 📝 **Description:** Tuned `scripts/run_foxglove_demo.py` for low-latency H.264 by switching to `H264_BASELINE`, disabling B-frames (`setNumBFrames(0)`), shortening GOP to 5 frames (`setKeyframeFrequency(5)`), forcing CBR at 4000 kbps, and reducing the encoder output queue depth to `maxSize=1` so stale frames are dropped instead of buffered. Added startup logging that prints active latency-tuning settings and updated `docs/infra_foxglove.md` to document the revised encoder profile and queue behavior.
- 🧪 **Test:** `uv run --project server python -c "import signal,subprocess,sys,time;p=subprocess.Popen([sys.executable,'scripts/run_foxglove_demo.py','--camera','--port','8771'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True);time.sleep(12);p.send_signal(signal.SIGINT);out,_=p.communicate(timeout=10);print(out);print(p.returncode)"` — pass (connected OAK stream starts on `/camera/color` and logs `H.264 low-latency config: baseline, bframes=0, gop=5, cbr=4000kbps, queue=1.`).
- 🔄 **Integration / Regression:** `uv run --project server python -m py_compile scripts/run_foxglove_demo.py` — pass (no compile errors).

## ✨ Feature #29

- 🎯 **Goal:** Switch Foxglove camera stream from MJPEG to on-device H.264 for smaller payloads and lower bandwidth.
- 📝 **Description:** Replaced the `VideoEncoder` MJPEG profile with `H264_MAIN` (IDR keyframe every 15 frames), switched the Foxglove schema from `ros.sensor_msgs.CompressedImage` to Foxglove's native `foxglove.CompressedVideo` with `format: "h264"`, and updated the message shape to match the `CompressedVideo` spec (top-level `timestamp` instead of nested `header.stamp`). H.264 inter-frame compression makes delta frames dramatically smaller than per-frame JPEG. Updated `docs/infra_foxglove.md` with revised diagrams, schema tables, and pipeline details.
- 🧪 **Test:** Smoke test with connected OAK device — pass (`Streaming OAK socket CAM_A on /camera/color`, clean SIGINT exit).
- 🔄 **Integration / Regression:** `uv run --project server python -m py_compile scripts/run_foxglove_demo.py` — pass (no compile errors).

## ✨ Feature #28

- 🎯 **Goal:** Move JPEG encoding from the host CPU to the OAK device hardware encoder.
- 📝 **Description:** Replaced the host-side NV12 decode + `cv2.imencode` JPEG encode path with an on-device `VideoEncoder` node using `Profile.MJPEG` (quality 80). The host now receives pre-encoded JPEG bytes over USB and only performs `base64` + JSON wrapping. Removed the `opencv-python` dependency from the camera code path. Updated `docs/infra_foxglove.md` with revised data-flow diagram and pipeline details.
- 🧪 **Test:** `uv run --project server python -c "import signal,subprocess,sys,time;p=subprocess.Popen([sys.executable,'scripts/run_foxglove_demo.py','--camera','--port','8769']);time.sleep(2);p.send_signal(signal.SIGINT);p.wait(timeout=8)"` — pass (graceful fallback, clean exit).
- 🔄 **Integration / Regression:** `uv run --project server python -m py_compile scripts/run_foxglove_demo.py` — pass (no compile errors).

## ✨ Feature #27

- 🎯 **Goal:** Add an optional Foxglove camera window that streams from a connected OAK camera.
- 📝 **Description:** Extended `scripts/run_foxglove_demo.py` with `--camera` and `--port` flags, added `/camera/color` publishing using a JSON `ros.sensor_msgs.CompressedImage` schema (JPEG + base64), and made camera mode gracefully fall back to sine/cosine-only streaming when no OAK device is detected. Added `scripts/foxglove-camera-layout.json` with a row split between an Image panel (`/camera/color`) and the existing sine/cosine Plot panel.
- 🧪 **Test:** `uv run --project server python -c "import signal,subprocess,sys,time;p=subprocess.Popen([sys.executable,'scripts/run_foxglove_demo.py','--camera','--port','8767']);time.sleep(2);p.send_signal(signal.SIGINT);p.wait(timeout=8)"` — pass (camera mode starts, reports no-hardware fallback clearly, and exits cleanly on SIGINT).
- 🔄 **Integration / Regression:** `uv run --project server python -m py_compile scripts/run_foxglove_demo.py && uv run --project server python -c "import json;from pathlib import Path;json.loads(Path('scripts/foxglove-camera-layout.json').read_text());print('layout-json-ok')"` — pass (`layout-json-ok` and no compile errors).

## ✨ Feature #26

- 🎯 **Goal:** Add a minimal Foxglove Studio example that streams a live sine-wave plot.
- 📝 **Description:** Created `scripts/run_foxglove_demo.py` using the `foxglove-sdk` package. The script starts a Foxglove WebSocket server on `ws://localhost:8765` and streams `/sine` and `/cosine` channels at ~30 Hz with JSON-encoded plot data. Added `foxglove-sdk` to `server/pyproject.toml` dependencies.
- 🧪 **Test:** `uv run --project server python scripts/run_foxglove_demo.py` — pass (server starts, streams data, connect via Foxglove app).
- 🔄 **Integration / Regression:** `uv run --project server python -c "import foxglove; from foxglove import Channel, Schema; print('OK')"` — pass.

## ✨ Feature #25

- 🎯 **Goal:** Make Thor/host runtime usage explicit and copy-paste friendly in the README.
- 📝 **Description:** Reworked `README.md` usage guidance into a practical runbook with separate first-time setup, daily startup, verification commands, cleanup helpers, and Wi-Fi fallback tuning for remote camera load.
- 🧪 **Test:** `N/A` — documentation-only update.
- 🔄 **Integration / Regression:** `N/A` — documentation-only update.

## ✨ Feature #24

- 🎯 **Goal:** Add a one-command Thor/host workflow so split deployment no longer requires manual multi-terminal command assembly.
- 📝 **Description:** Added split make targets (`setup_host`, `setup_remote`, `dev_host`, `dev_remote`, `dev_remote_cleanup`, `dev_remove` alias), introduced dedicated scripts (`scripts/dev_host.sh`, `scripts/dev_remote.sh`, `scripts/setup_remote.sh`) with cleanup and env-driven endpoint wiring, added `.env.host.example` and `.env.remote.example`, and updated `README.md` plus `docs/infra.md` with clear Thor/host startup and data-flow guidance.
- 🧪 **Test:** `cd server && uv run pytest ../tests/server/test_webrtc_cameras_endpoint.py -v` — pass (1 passed).
- 🔄 **Integration / Regression:** `npm --prefix client test -- --run` — pass (5/5 tests, 3 files).

## 🐛 Bug Fix #23

- 🎯 **Goal:** Restore live trajectory/3D robot updates in `make dev` and fail startup early when robot telemetry is missing.
- 📝 **Description:** Updated split-runner startup so `tc-robot` runs by default and connects to the existing GUI-hosted Rerun gRPC session (no second viewer bind), added robot heartbeat publishing in `tc-robot`, exposed `/robot/status` from GUI API, and extended `scripts/check_camera_live_webrtc.py` to require live robot heartbeat in addition to camera relay readiness.
- 🧪 **Test:** `make dev` — pass (`camera-guard:webrtc` relay 3/3 ready + robot heartbeat live, `camera-guard:gui` 3/3 live tiles, snapshot updated).
- 🔄 **Integration / Regression:** `make test` — pass (client: 5/5 vitest, server: 46/46 pytest).

## ✨ Feature #22 | 🐛 Bug Fix #22

- 🎯 **Goal:** Land the SDK refactor milestones (split runners + compatibility shims) without regressing startup guards or test stability.
- 📝 **Description:** Implemented `telemetry_console` module set (`zmq_channels`, `viewer`, `camera`, `env`, `recorder`, `replay`, `gui_api`, `cli`, `schemas`), added `tc-`* entry points in `server/pyproject.toml`, switched legacy modules (`main.py`, `webrtc.py`, `schemas.py`, `robot_env.py`) to compatibility shims, expanded server coverage for new modules, and updated dev orchestration (`scripts/dev.sh`, `Makefile`) to run split services while preserving pre-cleanup and camera guard checks. Also fixed split-runner startup reliability issues (Rerun port contention and stale runner cleanup for ZMQ ports/processes).
- 🧪 **Test:** `make test` — pass (client: 5/5 vitest, server: 40/40 pytest).
- 🔄 **Integration / Regression:** `make dev` — pass (`camera-guard:webrtc` relay paths 3/3 ready, `camera-guard:gui` live tiles 3/3, snapshot updated).

## ✨ Feature #21 | 🐛 Bug Fix #21

- 🎯 **Goal:** Remove hacky scaffolding and placeholder behavior across client/server/scripts to keep the codebase compact, minimal, and easier to maintain.
- 📝 **Description:** Added shared client runtime config (`client/src/config.ts`) and removed scattered hardcoded URLs/ports; simplified TopBar to remove non-functional controls and replaced nested status ternaries; removed dead placeholder components/hooks (`TimelineBar`, `useTimeSync`); added derived layout flags in `LayoutContext`; hardened backend relay error semantics (`/webrtc/cameras` now returns 503 with detail), replaced brittle `RecordingStatus(**state.__dict__)` mapping, converted server `print` calls to logging, and extracted relay timing magic numbers into named constants; removed duplicate/placeholder server tests and replaced with real smoke coverage; simplified setup/guard workflow by removing root `node_modules` symlink step, making `dev-guard` fail-fast in one command chain, and simplifying `run_rerun_demo.py` invocation assumptions; marked `docs/sdk_design.md` as historical to reduce doc/code mismatch confusion.
- 🧪 **Test:** `make lint && make test` — pass (ruff clean, client 5/5 vitest, server 19/19 pytest).
- 🔄 **Integration / Regression:** `make dev` — pass across all 3 milestones (stack restart + camera guards succeeded each run; GUI guard confirmed 3/3 live tiles).

## ✨ Feature #20

- 🎯 **Goal:** Align `docs/sdk_design.md` with the actual state of the current branch and the latest relay/guard commits.
- 📝 **Description:** Added a branch-status section to `docs/sdk_design.md` (reviewed at `main` commit `2a5fc79`), summarized recent commit impacts (`1701b9d` through `2a5fc79`), added a current-vs-target matrix, clarified that detailed tasks are historical reference, and replaced the stale “plan complete / which approach” tail with current-status guidance.
- 🧪 **Test:** `N/A` — documentation-only update.
- 🔄 **Integration / Regression:** `N/A` — documentation-only update.

## ✨ Feature #19

- 🎯 **Goal:** Finalize relay-only camera streaming with recording decode tap and remove legacy aiortc signaling path.
- 📝 **Description:** Removed server-side aiortc offer/answer track plumbing, kept DepthAI-to-MediaMTX relay as the only streaming path, added relay packet decode tap for recording-active Zarr logging, simplified relay/client guard code paths for readability, and refreshed infra/readme docs to reflect WHEP + H264-default behavior.
- 🧪 **Test:** `make test` — pass (client: 5/5 vitest, server: 19/19 pytest).
- 🔄 **Integration / Regression:** `make dev` — pass (`camera-guard:webrtc` 3/3 relay paths ready, `camera-guard:gui` 3/3 live tiles).

## 🐛 Bug Fix #20

- 🎯 **Goal:** Make every `make dev` run clean stale listeners/processes first so ghost background processes do not leak across runs.
- 📝 **Description:** Added robust pre-start cleanup in `scripts/dev.sh` for Vite/FastAPI/Rerun ports (`5173`, `8000`, `9876`, `9090`) with PID discovery via `lsof`, graceful `TERM`, forced `KILL` fallback, and post-cleanup free-port assertions. Added `--cleanup-only` + `DEV_SKIP_PRE_CLEANUP` support, wired `Makefile` with `dev-cleanup` and `dev: dev-cleanup`, and updated README command docs.
- 🧪 **Test:** `SKIP_CAMERA_GUARD=1 make dev` — pass (two consecutive launches: second run auto-cleaned stale listeners from the first run before startup; validated all four ports free after `make dev-cleanup`).
- 🔄 **Integration / Regression:** `make test` — pass (5 vitest, 12 pytest).

## 🐛 Bug Fix #19

- 🎯 **Goal:** Fail `make dev` fast when any camera is not live, and provide screenshot artifacts users can inspect.
- 📝 **Description:** Added startup camera guards for WebRTC (`scripts/check_camera_live_webrtc.py`) and GUI tile readiness (`scripts/check_camera_live_gui.mjs`), wired them into `scripts/dev.sh` with strict Vite/API port checks, and added a `make dev-guard` target. The GUI guard now writes success/failure snapshots to `docs/assets/screenshots/`. Also added partial-live UI error messaging in `useWebRTC` + `VideoPanel` and updated setup/docs for Playwright guard support.
- 🧪 **Test:** `make dev` — pass (WebRTC guard received 3/3 first frames, GUI guard confirmed 3/3 live tiles, generated `docs/assets/screenshots/camera-live-guard-success.png`).
- 🔄 **Integration / Regression:** `make test` — pass (5 vitest, 12 pytest).

## ✨ Feature #18

- 🎯 **Goal:** Keep snapshot images organized under `docs/assets/`.
- 📝 **Description:** Added a Cursor rule that always applies and directs all snapshot image files to be saved inside `docs/assets/` instead of the repo root or ad hoc folders.
- 🧪 **Test:** `N/A` — rule-only change.
- 🔄 **Integration / Regression:** `N/A` — rule-only change.

## 🐛 Bug Fix #17

- 🎯 **Goal:** Keep macOS `.DS_Store` out of the dexmate-urdf submodule.
- 📝 **Description:** Added a submodule `.gitignore` that excludes `.DS_Store` files so the submodule stays clean.
- 🧪 **Test:** `git -C external/dexmate-urdf status -uall` — not run
- 🔄 **Integration / Regression:** `git submodule status external/dexmate-urdf` — not run

## 🐛 Bug Fix #16

- 🎯 **Goal:** Ignore local `data_logs` artifacts in git status.
- 📝 **Description:** Added `data_logs/` to `.gitignore` to keep generated run data out of version control.
- 🧪 **Test:** `N/A` — configuration-only change.
- 🔄 **Integration / Regression:** `N/A` — no runnable checks for ignore rules.

## ✨ Feature #17

- 🎯 **Goal:** Add `docs/infra.md` — architecture overview with readable Mermaid diagrams.
- 📝 **Description:** Created four focused diagrams: (1) system architecture (HW → Server → Client), (2) client component tree, (3) server module map, (4) WebRTC signaling sequence. Replaced the single overcrowded graph with styled, directional flowcharts and a sequence diagram for better readability.
- 🧪 **Test:** `N/A` — pure documentation, no executable changes.
- 🔄 **Integration / Regression:** `N/A` — no code changes.

## ✨ Feature #16

- 🎯 **Goal:** Start/stop GUI recording and log camera + sine trajectory into Zarr with aligned timesteps.
- 📝 **Description:** Added a Zarr episode logger and recording manager on the server to append `rgb`, `t_ns`, and `ee_pose` per frame with shared timestamps. Wired `/recording/start`, `/recording/stop`, and `/recording/status`, and passed the recording manager into WebRTC tracks for per-frame logging. Connected the TopBar Rec button to the recording endpoints with live status text and a recording style. Documented default `data_logs/<run_id>/<camera>.zarr` output plus `DATA_LOG_DIR` override.
- 🧪 **Test:** `cd server && uv run pytest ../tests/server -v` — pass (12 tests)
- 🔄 **Integration / Regression:** `make test` — not run

## ✨ Feature #15

- 🎯 **Goal:** Animate the vega_1p shoulder joints from the live sine/cos trajectory
- 📝 **Description:** Cached the URDF tree on load, added joint-transform logging for `L_arm_j1` and `R_arm_j1`, and wired the sine/cos stream to emit shoulder transforms so the arms animate in the 3D view alongside the trajectory plot. Added tests for joint transform logging and URDF tree caching.
- 🧪 **Test:** `uv run --project server python -m pytest tests/server/test_rerun_sine.py` — pass (5 tests)
- 🔄 **Integration / Regression:** `uv run --project server python scripts/run_rerun_demo.py` — not run (manual, long-running)

## 🐛 Bug Fix #15

- 🎯 **Goal:** Fix non-native mode switching — all shortcuts now work from any mode, plus a visible ModeSwitcher UI
- 📝 **Description:** Rewrote `LayoutContext` keyboard handler so `Z`, `F`, `1`, `2`, and `Esc` all work from every mode (previously `F`/`1`/`2` were restricted to compact-only and `Z` broke from focus). Removed the old `toggleZen` helper and `zen-toggle` button. Created a new `ModeSwitcher` segmented pill component with a sliding CSS indicator that shows all three modes (Zen / Compact / Focus) as clickable radio buttons with keyboard-hint badges. Integrated into TopBar (always visible) and FloatingDot (expands on hover in zen mode). Updated README keyboard shortcuts table. Cleaned up unused `.zen-toggle` CSS.
- 🧪 **Test:** `npm --prefix client test -- --run` — pass (3 tests)
- 🔄 **Integration / Regression:** `npm --prefix client test -- --run` — pass (3 tests, all existing assertions unchanged)

## ✨ Feature #14

- 🎯 **Goal:** Simplify and refine the three-mode layout system for clarity, consistency, and maintainability
- 📝 **Description:** Extracted a shared `CompactHeader` component from duplicated compact-header JSX in `VideoPanel` and `RerunPanel` (eliminated ~30 lines of structural duplication). Simplified the `LayoutContext` keyboard shortcut handler from nested `setModeRaw` updaters with inline `setFocusTarget` calls to straightforward if/else using existing `focusPanel`, `exitFocus`, and `setMode` callbacks. Exported `DisplayMode`, `FocusTarget` types and `DEFAULT_SPLIT` constant from `LayoutContext` for reuse; replaced magic number `0.35` in `ResizeHandle` with the shared constant. Consolidated duplicated CSS rules for zen/compact video-panel and rerun-panel sizing into combined selectors. Cleaned up TopBar className concatenation with array-filter-join pattern. All CSS class names preserved for test stability.
- 🧪 **Test:** `npm --prefix client test -- --run` — pass (3 tests)
- 🔄 **Integration / Regression:** `npm --prefix client test -- --run` — pass (3 tests, all existing assertions unchanged)

## 🐛 Bug Fix #13

- 🎯 **Goal:** Simplify the WebRTC reliability code paths without changing behavior
- 📝 **Description:** Refactored the client `useWebRTC` hook to make StrictMode/HMR cancellation guards easier to follow (single `isActive()` gate + small helpers), kept fetch abort + stale-attempt no-op behavior, and streamlined server pipeline state reset/reuse logic while preserving the “don’t reopen device when pipeline is active” rule.
- 🧪 **Test:** `make test-client` — pass (3 vitest)
- 🔄 **Integration / Regression:** `make test` — pass (3 vitest, 9 pytest)

## ✨ Feature #13

- 🎯 **Goal:** Zen / Compact / Focus three-mode layout for maximum camera and rerun content
- 📝 **Description:** Replaced the fixed chrome-heavy layout (43% overhead) with a three-tier density system. **Zen** (default): bare camera + rerun panels fill 98% of the viewport, floating status dot, topbar auto-reveals on hover. **Compact** (press Z): slim 40px topbar, 28px inline panel headers with metrics, 28px timeline scrubber — 81% content. **Focus** (press F/1/2): single panel fills viewport — 87% content. Added `LayoutContext` for mode state + split ratio, `ResizeHandle` for draggable panel divider persisted in localStorage, `FloatingDot` for zen status, and keyboard shortcuts (Z, F, Escape, 1, 2). Rewrote all component rendering to be mode-aware and overhauled App.css for all three modes with 150ms transitions. Updated tests for the new default zen mode.
- 🧪 **Test:** `npm --prefix client test -- --run` — pass (3 tests)
- 🔄 **Integration / Regression:** `make dev` — pass (verified zen, compact, focus modes with live cameras + rerun in browser)

## 🐛 Bug Fix #11

- 🎯 **Goal:** Run the Rerun demo as part of `make dev`
- 📝 **Description:** Updated the dev script to start the Rerun demo alongside the Vite and FastAPI servers, and aligned the README quick-start command to reflect the combined startup.
- 🧪 **Test:** `bash scripts/dev.sh` — not run
- 🔄 **Integration / Regression:** `make test` — not run

## 🐛 Bug Fix #12

- 🎯 **Goal:** Make WebRTC camera streaming reliable during `make dev`
- 📝 **Description:** Avoided reopening the DepthAI device while the streaming pipeline is active (prevents intermittent `X_LINK`_* errors under dev-mode reconnects), reused an active pipeline instead of restarting it per-offer, and removed the `cv2` import from the server process by requesting RGB frames directly.
- 🧪 **Test:** `make dev` — pass (Live Camera shows 3 tiles + “Live connection”; no `InvalidStateError` spam)
- 🔄 **Integration / Regression:** `make test` — pass (3 vitest, 9 pytest)

## 🐛 Bug Fix #10

- 🎯 **Goal:** Ensure the visual tab only shows visual meshes
- 📝 **Description:** Replaced unsupported wildcard query expressions with explicit URDF-root paths so the visual tab includes only `visual_geometries` plus transforms, and the collision tab includes only `collision_geometries` plus transforms. Captured an updated visual-tab snapshot.
- 🧪 **Test:** `uv run --project server python -m pytest tests/server/test_rerun_sine.py -v` — pass (4 tests)
- 🔄 **Integration / Regression:** `uv run --project server python scripts/run_rerun_demo.py` + `npm run dev` — pass (Playwright snapshot `rerun-vega-visual-tab-v2.png`)

## ✨ Feature #10

- 🎯 **Goal:** Toggle visual vs collision meshes in the 3D viewer
- 📝 **Description:** Replaced the single 3D view with a tabbed container containing Visual and Collision views. Each view filters the opposite geometry root via query expressions, defaulting to the visual tab. Updated blueprint layout tests and captured a visual-tab snapshot.
- 🧪 **Test:** `uv run --project server python -m pytest tests/server/test_rerun_sine.py -v` — pass (4 tests)
- 🔄 **Integration / Regression:** `uv run --project server python scripts/run_rerun_demo.py` + `npm run dev` — pass (Playwright snapshot `rerun-vega-visual-tab.png`)

## ✨ Feature #9

- 🎯 **Goal:** Load the vega_1p URDF in the Rerun 3D viewer
- 📝 **Description:** Added vega_1p URDF loading during Rerun bridge startup using the built-in loader, plus tests for path resolution and logging. Captured a Playwright snapshot of the embedded viewer with the model visible.
- 🧪 **Test:** `uv run --project server python -m pytest tests/server/test_rerun_sine.py -v` — pass (4 tests)
- 🔄 **Integration / Regression:** `uv run --project server python scripts/run_rerun_demo.py` + `npm run dev` — pass (Playwright snapshot `rerun-vega-1p.png`; Vite dev server already running on `:5173`)

## ✨ Feature #8

- 🎯 **Goal:** Stack the live camera above a split trajectory + 3D model viewer
- 📝 **Description:** Updated the main grid to a two-row stack, refreshed the Rerun panel copy to reflect the split view, and switched the Rerun blueprint to a horizontal layout with a time-series trajectory on the left and a 3D model view on the right. Captured a refreshed integrated UI snapshot.
- 🧪 **Test:** `uv run --project server python scripts/run_rerun_demo.py` + `npm run dev` — pass (captured `rerun-sine-integrated.png`)
- 🔄 **Integration / Regression:** `npm --prefix client test` + `uv run --project server --extra dev python -m pytest tests/server/test_rerun_sine.py -v` — pass (1 vitest, 2 pytest)

## ✨ Feature #10

- 🎯 **Goal:** Stream all connected OAK cameras in the Live Camera panel grid
- 📝 **Description:** Added a `/webrtc/cameras` endpoint to expose connected camera sockets, updated WebRTC negotiation to add one video track per camera, and updated the client hook/UI to request per-camera transceivers and render a grid of video tiles with labels. Added server tests for multi-camera negotiation and camera list, plus client tests for multi-track handling and grid rendering.
- 🧪 **Test:** `npm test -- ../tests/client/useWebRTC.test.tsx` — pass (1 test)
- 🔄 **Integration / Regression:** `uv run pytest ../tests/server/test_webrtc.py ../tests/server/test_webrtc_endpoint.py ../tests/server/test_webrtc_cameras_endpoint.py -v` — pass (3 tests)

## ✨ Feature #9

- 🎯 **Goal:** Stream the RGB OAK camera into the web viewer via P2P WebRTC
- 📝 **Description:** Implemented aiortc DepthAI track and offer handling in `server/webrtc.py`, added `/webrtc/offer` FastAPI signaling with peer connection tracking, built a `useWebRTC` hook for H264-preferred negotiation, and wired `VideoPanel` to auto-connect and render the stream with status UI. Added server/client tests for WebRTC negotiation and hook behavior.
- 🧪 **Test:** `bash scripts/dev.sh` — pass (UI shows Live connection; snapshot saved to `artifacts/webrtc-live-rgb.png`; no camera image without attached OAK device)
- 🔄 **Integration / Regression:** `make test-server` — pass (6 tests)

## 🐛 Bug Fix #9

- 🎯 **Goal:** Make the Rerun plot fill the viewer window in the embedded iframe
- 📝 **Description:** Updated `.media-placeholder.is-rerun` styling to stretch grid items, remove padding, and hide overflow, plus added `.rerun-iframe` and `.placeholder-overlay` styles so the iframe fills the panel and the loading overlay sits on top. Updated `RerunPanel` to use the new iframe class. The embedded Rerun plot now fills the full viewer window instead of rendering at a small size.
- 🧪 **Test:** `uv run --project server python scripts/run_rerun_demo.py` + `npm run dev` — pass (Playwright snapshot `rerun-sine-fill.png` shows the plot fills the viewer area)
- 🔄 **Integration / Regression:** `N/A` — no automated regression run for this UI-only tweak

## ✨ Feature #7

- 🎯 **Goal:** Track Luxonis OAK examples as an external submodule
- 📝 **Description:** Added `external/oak-examples` as a git submodule pointing at `https://github.com/luxonis/oak-examples` to keep the upstream examples synced without vendoring the repo.
- 🧪 **Test:** `git submodule status external/oak-examples` — not run
- 🔄 **Integration / Regression:** `git submodule update --init --recursive` — not run

## ✨ Feature #6

- 🎯 **Goal:** Stream a live sine-wave trajectory in the Rerun Web Viewer embedded in the frontend
- 📝 **Description:** Implemented `server/rerun_bridge.py` with `start()` (inits Rerun, starts gRPC on port 9876, web viewer on 9090, sends a `TimeSeriesView` blueprint with a rolling 2-second `VisibleTimeRange`) and `stream_sine_wave()` (logs `sin`/`cos` scalars at 20 Hz using wall-clock `timestamp`). Created `scripts/run_rerun_demo.py` as a standalone entry point that re-execs into the server venv. Updated `client/src/components/RerunPanel.tsx` to embed the Rerun web viewer via `<iframe>` with auto-connect query param (`?url=rerun%2Bhttp://localhost:9876/proxy`). Added `GET /rerun/status` endpoint to `server/main.py`. Added `tests/server/test_rerun_sine.py` to verify bridge startup, port availability, and streaming.
- 🧪 **Test:** `cd server && uv run pytest ../tests/server/test_rerun_sine.py -v` — pass (1 test); Playwright verification: Rerun viewer direct page shows live sin/cos plot with 2-sec rolling window on `wall_time` timeline; integrated app at `localhost:5173` renders the Rerun iframe with the live trajectory.
- 🔄 **Integration / Regression:** `cd server && uv run pytest ../tests/server/test_server.py ../tests/server/test_rerun_sine.py -v` — pass (2 tests)

## 🐛 Bug Fix #8

- 🎯 **Goal:** Install OpenCV dependency for camera script
- 📝 **Description:** Added `opencv-python` to `server/pyproject.toml` so `scripts/run_camera.py` can import `cv2` when run via uv.
- 🧪 **Test:** `uv run --project server python scripts/run_camera.py` — not run
- 🔄 **Integration / Regression:** `make test-server` — not run

## 🐛 Bug Fix #7

- 🎯 **Goal:** Remove uv warning about exact Python version pin
- 📝 **Description:** Updated `server/pyproject.toml` to use `==3.10.`* for `requires-python`, matching uv's guidance to include a patch wildcard instead of an exact minor pin.
- 🧪 **Test:** `uv run --project server python scripts/run_camera.py` — not run
- 🔄 **Integration / Regression:** `make test-server` — not run

## 🐛 Bug Fix #6

- 🎯 **Goal:** Install all external submodules during setup
- 📝 **Description:** Added setup steps to install DepthAI requirements from `external/depthai-core`, plus editable installs for `external/rerun/rerun_py` and `external/dexmate-urdf`. Added `dexmate-urdf` to `server/pyproject.toml` so the server venv tracks the dependency explicitly.
- 🧪 **Test:** `bash scripts/setup.sh` — not run
- 🔄 **Integration / Regression:** `make setup` — not run

## 🐛 Bug Fix #5

- 🎯 **Goal:** Install external dependencies (depthai-core) during setup
- 📝 **Description:** `scripts/setup.sh` was not installing the DepthAI library from the `external/depthai-core` submodule. Added `server/.venv/bin/pip install depthai --force-reinstall` after `uv sync` to ensure the latest DepthAI wheel is properly installed in the server venv, following [Luxonis install docs](https://docs.luxonis.com/software-v3/depthai/).
- 🧪 **Test:** `bash scripts/setup.sh` — not run
- 🔄 **Integration / Regression:** `make setup` — not run

## ✨ Feature #5

- 🎯 **Goal:** Add a DepthAI camera streaming script with full environment setup
- 📝 **Description:** Created `scripts/run_camera.py` mirroring `external/depthai-core/examples/python/Camera/camera_all.py`. It discovers all connected OAK cameras, opens a full-resolution output queue per sensor, and displays each feed in an OpenCV window (press `q` to quit). Added `opencv-python` and `depthai` to server dependencies with a pytest import check. Updated `scripts/setup.sh` to source the server venv after `uv sync` so it is active without manual steps.
- 🧪 **Test:** `make test-server` — pass (2 tests); `server/.venv/bin/python scripts/run_camera.py` — requires physical OAK device
- 🔄 **Integration / Regression:** `uv run --project server python scripts/run_camera.py` — requires physical OAK device

## ✨ Feature #4

- 🎯 **Goal:** Restructure repo into professional client/server/tests layout
- 📝 **Description:** Reorganized flat repo into `client/` (React+Vite), `server/` (FastAPI), `tests/` (client+server), `external/` (submodules), `scripts/` (setup/dev/lint). Decomposed monolithic App.tsx into per-component files. Added Makefile with setup/dev/test/lint/clean targets. Created FastAPI server scaffold with signaling schemas. Symlinked root node_modules for cross-directory test resolution.
- 🧪 **Test:** `make test-client` — pass (1 test, vitest)
- 🔄 **Integration / Regression:** `make test-client` — pass

## ✨ Feature #3

- 🎯 **Goal:** Document how to run the frontend GUI
- 📝 **Description:** Run `npm install` then `npm run dev` from the repo root, open the printed local URL in a browser.
- 🧪 **Test:** `N/A` — not run (documentation only)
- 🔄 **Integration / Regression:** `N/A` — not run

## ✨ Feature #2

- 🎯 **Goal:** Scaffold the Version A frontend layout with placeholders
- 📝 **Description:** Build a two-panel WebRTC/Rerun shell with top controls, status pills, and a timeline bar, plus a test-backed UI scaffold.
- 🧪 **Test:** `npm test` — pass (vitest)
- 🔄 **Integration / Regression:** `N/A` — not run

## ✨ Feature #1

- 🎯 **Goal:** Prepare Python env and external deps with uv and submodules
- 📝 **Description:** Add uv setup instructions, requirements.txt, and track depthai-core, rerun, dexmate-urdf as git submodules under external_dependencies with a README
- 🧪 **Test:** `N/A` — not run (env setup only)
- 🔄 **Integration / Regression:** `N/A` — not run

