# Test Plan: 3-Camera Streaming Verification

## Goals

1. GUI snapshot with all three cameras streaming
2. All three camera devices detected
3. GUI properly plays video (currentTime advances = decode verified)
4. CLAUDE.md rule: run `make dev` + `make test` for every feature/milestone

---

## Prerequisites

### Install `@playwright/test`

`client/package.json` currently has `"playwright"` (browser binaries only). The test runner, `expect`, and `toHaveScreenshot()` require the separate `@playwright/test` package:

```bash
cd client && npm install -D @playwright/test
```

### `depthai` availability

`CameraRelayPublisher` and device detection functions import `depthai`. Server tests that import from `telemetry_console.camera` will fail if `depthai` is not installed. Add `pytest.importorskip("depthai")` at the top of new test classes that directly instantiate `CameraRelayPublisher` to skip gracefully in CI environments without hardware SDK.

---

## Files to Create

### `tests/integration/playwright.config.ts`

Playwright config for integration tests.

- **ESM-safe `__dirname`**: Use `import { dirname } from "path"; import { fileURLToPath } from "url"; const __dirname = dirname(fileURLToPath(import.meta.url));` since `client/package.json` has `"type": "module"` (no native `__dirname` in ESM).
- `testDir: __dirname` → `tests/integration/`
- `baseURL`: `process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173"`
- `workers: 1` (WebRTC state is global)
- Chromium headless with H.265 flags matching guard script:
  `--enable-features=WebRtcAllowH265Receive,PlatformHEVCDecoderSupport`
- Per-test timeout: 60 000 ms
- No `webServer` block — expects `make dev` already running
- Screenshots on failure saved to `docs/assets/screenshots/`

### `tests/integration/camera-snapshot.spec.ts`

Four Playwright tests requiring a live `make dev` stack:

| Test | Assertion |
|---|---|
| `renders three live camera tiles` | `[data-testid="camera-stream"]` count = 3; labels = `["Left", "Center", "Right"]` |
| `all three camera streams are live` | Each video: `readyState >= 2` AND `track.readyState === "live"` (polls ≤ 20 s) |
| `snapshot: three cameras, no error banner` | `[role="alert"]` absent; saves `docs/assets/screenshots/integration-3cam-snapshot.png`; `toHaveScreenshot("3cam-all-live.png")` baseline |
| `video currentTime advances for all three streams` | Sample `currentTime` at t₀, wait 2 s, sample t₁; assert `t₁[i] > t₀[i]` for all 3 — verifies H.264 decode |

Snapshot baselines stored in `tests/integration/__snapshots__/` (generated on first run, compared on subsequent runs).

### `tests/client/VideoTile.test.tsx`

Unit tests for the `VideoTile` stall monitor inside `VideoPanel`. Key constants from source ([client/src/components/VideoPanel.tsx:208-210](../client/src/components/VideoPanel.tsx)):
- `tickMs = 2000`, `warmupMs = 8000`, `stallThresholdMs = 15_000`
- Soft recovery at `stallThresholdMs / 2 = 7_500`

**Setup strategy:**
- `vi.useFakeTimers()` + `vi.setSystemTime(new Date(60_000))` — pre-advancing past the 30 s `recoverStalledStream` cooldown (`lastRecoveryAtRef` initializes to `0` at [VideoPanel.tsx:23](../client/src/components/VideoPanel.tsx); at fake-time 82 000 ms when stall first fires, `82000 - 0 = 82000 >= 30000` so cooldown is expired and `disconnect()` is callable)
- `Object.defineProperty(video, "readyState", { value: 2 })` — jsdom video is always unready by default
- In jsdom, `video.currentTime` is always `0`. First tick: `0 > lastTime(-1) + 0.001` = TRUE → sets `lastTime=0`. After that: `0 > 0.001` = FALSE → stagnant accumulation begins
- For "currentTime advances" test: use a getter that increments per-read: `let ct = 1.0; Object.defineProperty(video, "currentTime", { get: () => (ct += 0.1), configurable: true })`
- Mock `useWebRTC` with `vi.mock(...)`, wrap renders in `<LayoutProvider>`

| Test | Advance (fake ms) | Assertion |
|---|---|---|
| warmup blocks stall detection | 7 900 | `disconnectMock` NOT called |
| soft recovery fires at 7 500 ms post-warmup | 14 000 | `video.play` spy called (srcObject reassigned) |
| `onStalled` fires at 15 000 ms post-warmup → disconnect | 22 000 | `disconnectMock` called |
| advancing `currentTime` resets `stagnantMs` → no stall | 10 000 stagnant, then incrementing getter, then 10 000 more | `disconnectMock` NOT called |
| `track.readyState = "ended"` → monitor skips | 30 000 | `disconnectMock` NOT called |
| `video.readyState < 2` → monitor skips | 30 000 | `disconnectMock` NOT called |
| 30 s cooldown: second stall within 30 s ignored | trigger stall + 15 000 more | `disconnectMock` called exactly once |
| `connectionState !== "connected"` → `monitorEnabled=false` | 30 000 | `disconnectMock` NOT called |

---

## Files to Modify

### `tests/server/test_multi_device_detection.py`

Append two new test classes (reuse existing `_fake_device_info` helper and imports).

**`TestCameraRelayPublisherHealthiness`** — 5 tests for `CameraRelayPublisher.is_healthy()`:

Guard with `pytest.importorskip("depthai")` at class level since `CameraRelayPublisher.__init__` requires a `dai.MessageQueue` (use `MagicMock(spec=dai.MessageQueue)`).

| Test | Setup | Expected |
|---|---|---|
| Thread never started | default publisher | `False` |
| Thread alive, payload just now | `patch is_alive=True`, `_last_payload_monotonic_s = time.monotonic()` | `True` |
| Thread alive, payload 10 s ago, threshold 5 s | `_last_payload_monotonic_s = now - 10` | `False` |
| Thread alive, payload 3 s ago, threshold 5 s | `_last_payload_monotonic_s = now - 3` | `True` |
| Zero threshold clamped ≥ 0.5 s | fresh payload, `max_silence_s=0.0` | `True` |

Mock strategy: `patch.object(publisher, "is_alive", return_value=True)` + set `publisher._last_payload_monotonic_s` directly.

**`TestEnsureStreamingPartialFailure`** — 1 test:
- Mock `_resolve_target_streams` → 3 targets (left, center, right)
- Mock `_start_stream_for_target` → raises `RuntimeError` for "center", succeeds (no-op) for others
- **Global state isolation**: Use a `monkeypatch` fixture to replace `_active_publishers`, `_active_pipelines`, `_active_devices`, and `_active_stream_targets` with fresh empty dicts/lists before the test. This avoids leaking state into other tests and removes the need for manual cleanup in try/finally blocks.
- Assert return value is `["left", "right"]` — `ensure_streaming` returns `[target.stream_name for target in started_targets]` ([camera.py:603](../server/telemetry_console/camera.py)), where `started_targets` only includes targets whose `_start_stream_for_target` did not raise.

### `scripts/check_camera_live_gui.mjs`

Enhance the success path (lines 183-189) to also verify decode. After `liveCount >= expectedCount` is confirmed, **replace** the immediate `return 0` with a decode verification step:

1. Add `readCurrentTimes(page)` — `page.evaluate` returning `videos.map(v => v.currentTime)`
2. Add `verifyCurrentTimeAdvancing(page, {pollIntervalMs=2000})` — sample t₀, wait 2 s, sample t₁, return `{results, advancingCount}`
3. In `run()`, after tiles are live, call the decode check:
   - `advancingCount < expectedCount` → save failure snapshot with per-camera details, `return 1`
   - All advancing → save success snapshot with decode confirmation, `return 0`

This makes `make dev-guard` (and `make dev`) also verify H.264 decode, not just stream presence.

### `Makefile`

Add `test-integration` to `.PHONY` and as a target after `test-server`:

```makefile
test-integration:
	cd client && npx playwright test --config ../tests/integration/playwright.config.ts
```

### `CLAUDE.md`

Add under `### Testing`:

```markdown
### Integration test requirement

For every new feature or milestone:
1. `make dev` — confirm the full stack boots and camera guard passes (includes video decode check).
2. `make test` — all unit tests must pass.
3. `make test-integration` — run Playwright integration tests against the live stack (requires `make dev` running).
```

---

## Compatibility

- **Existing vitest tests**: unchanged. `VideoTile.test.tsx` uses the same `vi.mock("useWebRTC")` pattern as `VideoPanel.test.tsx`. Vitest glob (`tests/client/**/*.test.{ts,tsx}`) picks it up automatically.
- **Existing pytest tests**: unchanged. New classes are appended to `test_multi_device_detection.py` following the existing `@patch` + `_fake_device_info` pattern. `monkeypatch` isolates globals.
- **`make test`** unaffected — Playwright tests are in `tests/integration/` with their own config, outside vitest's glob.
- **Guard script change** is additive — currentTime check only runs after the existing live-check passes.

---

## Verification

```bash
# Unit tests (no stack required):
make test-client           # includes VideoTile.test.tsx
make test-server           # includes TestCameraRelayPublisherHealthiness

# Integration tests (requires make dev in another terminal):
make dev                   # now also checks currentTime advancement
make test-integration      # runs camera-snapshot.spec.ts in Playwright
```

First `make test-integration` run generates snapshot baselines in `tests/integration/__snapshots__/`. Subsequent runs compare for visual regression.
