# SDK Refactor Implementation Plan

> Status: Historical planning document, not the current implementation source of truth.
> Current implementation status lives in `.cursor/plans/web-viz.plan.md` and `README.md`.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure the monolithic server into five independent processes (`run_gui`, `run_camera`, `run_robot`, `run_recorder`, `run_replay`) that communicate via ZMQ + existing buses (MediaMTX, Rerun gRPC), packaged as a single installable Python SDK (`telemetry_console`).

**Architecture:** Each runner is a standalone OS process with no cross-imports to other runners. Shared code lives in small utility modules (`zmq_channels.py`, `viewer.py`). Video flows through MediaMTX RTSP/WHEP. Telemetry flows through Rerun gRPC. Robot state and recording control flow through ZMQ PUB/SUB and REQ/REP. Replay renders everything (video + trajectories + 3D) through Rerun image/scalar logs.

**Tech Stack:** Python 3.10, pyzmq, msgpack, FastAPI, Rerun SDK, DepthAI, PyAV, Zarr, React/Vite (client unchanged)

---

## Status update (current `main`)

Reviewed against current `main` on 2026-02-11.

This refactor plan has now been executed in milestones:

- Task 1-2: dependency + ZMQ channel foundation merged.
- Task 3-4: `viewer.py` and `camera.py` extracted; compatibility shims kept.
- Task 5-7: `env.py`, `recorder.py`, and `replay.py` added with tests.
- Task 8-12: `gui_api.py`, `cli.py`, script entry points, package exports, and
  backward-compat shims are in place.
- Task 13: infrastructure docs updated to the split-runner model.

### Current branch reality vs original target

| Area | Original target in this plan | Status on current `main` |
|---|---|---|
| Process model | Five independent runners (`tc-gui`, `tc-camera`, `tc-robot`, `tc-recorder`, `tc-replay`) | Implemented in CLI + dev orchestration; robot runner is enabled by default and can be disabled via env. |
| Package split | `server/telemetry_console/*` package extraction | Implemented. |
| Entry points | `project.scripts` for `tc-*` CLIs | Implemented in `server/pyproject.toml`. |
| Camera delivery | MediaMTX relay | Implemented (`tc-camera` publisher + WHEP clients). |
| Client signaling | Legacy `/webrtc/offer` replacement | Implemented (WHEP path). |
| Startup reliability | pre-clean + camera guards | Preserved in `scripts/dev.sh` with milestone cutover. |
| Infra docs alignment | Final doc pass | Updated in `docs/infra.md` and README. |

### Operational note

`make dev` now starts `tc-robot` by default to keep trajectory + 3D telemetry live.
Use `RUN_ROBOT_RUNNER=0 make dev` to skip it intentionally.

---

## Current state and coupling to break

These are the imports that create tight coupling today:

| File | Imports | Problem |
|---|---|---|
| `server/webrtc.py:15` | `from data_log import RecordingManager` | Camera process knows about recording |
| `server/webrtc.py:170` | `recording_manager: RecordingManager \| None` | Every publisher thread holds a recorder reference |
| `server/main.py:12-14` | `import data_log, rerun_bridge, webrtc` | Monolith bundles all subsystems |
| `server/robot_env.py:9,11` | `import rerun as rr; import rerun_bridge` | Robot env directly calls Rerun (OK, but should also publish state via ZMQ) |
| `server/main.py:76-78` | `webrtc.ensure_streaming(recording_manager=...)` | Camera discovery endpoint wires recording into camera relay |

Target: after this refactor, **no runner module imports another runner module**. They share only `zmq_channels.py` (port constants + serialization) and `viewer.py` (Rerun utility functions).

## Target package layout

```
telemetry_console/
├── __init__.py                  # version string, re-export public API
├── zmq_channels.py              # ports, topics, pack/unpack helpers
├── viewer.py                    # Rerun server init, URDF, blueprints, logging helpers
├── camera.py                    # DepthAI pipeline + relay publishers (no recording)
├── env.py                       # RobotEnv base class (gym-like SDK interface)
├── recorder.py                  # RTSP subscriber + ZMQ subscriber + Zarr writer
├── replay.py                    # Zarr reader + Rerun logger
├── gui_api.py                   # thin FastAPI: health, rerun status, recording toggle via ZMQ
├── schemas.py                   # Pydantic models
├── cli.py                       # argparse entry points for all five runners
├── client/                      # React app (moved from repo root, unchanged)
│   ├── index.html
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   ├── contexts/
│   │   ├── hooks/
│   │   └── ...
│   └── ...
└── scripts/
    └── dev.sh                   # launches all five processes
```

Entry points (registered in `pyproject.toml`):

```
tc-gui       → telemetry_console.cli:run_gui
tc-camera    → telemetry_console.cli:run_camera
tc-robot     → telemetry_console.cli:run_robot
tc-recorder  → telemetry_console.cli:run_recorder
tc-replay    → telemetry_console.cli:run_replay
```

## ZMQ socket layout

```
Port   Pattern    Publisher       Subscriber        Content
────── ────────── ────────────── ─────────────────  ────────────────────────────
5555   PUB/SUB    run_robot       run_recorder      joint cmd + state + t_ns
5556   PUB/SUB    run_recorder    run_gui (API)     recording status updates
5557   REQ/REP    run_gui (API)   run_recorder      start/stop recording commands
```

Serialization: msgpack for all payloads. Topic prefix bytes for PUB/SUB filtering.

## Data flow (after refactor)

```
run_camera                                run_robot
  │ H.264 ffmpeg                            │ rr.log()
  ▼                                         │ zmq PUB :5555
MediaMTX (:8554 RTSP → :8889 WHEP)         ▼
  │                                    Rerun gRPC :9876
  │ WHEP tracks                        Rerun Web  :9090
  ▼                                         │
run_gui (VideoPanel)               run_gui (RerunPanel)
  │                                         ▲
  │ zmq REQ :5557 (start/stop)              │
  ▼                                         │
run_recorder                           run_replay
  │ RTSP subscribe (av)                  │ zarr read
  │ zmq SUB :5555 (robot state)          │ rr.log(Image + Scalars)
  │ zmq PUB :5556 (status)               │
  ▼                                      ▼
data_logs/<run_id>/*.zarr           Rerun gRPC :9876
```

---

## Task 1: Add `pyzmq` + `msgpack` dependencies

**Files:**
- Modify: `server/pyproject.toml`

**Step 1: Add dependencies**

Add `pyzmq` and `msgpack` to the `dependencies` list in `server/pyproject.toml`:

```toml
dependencies = [
    "fastapi",
    "uvicorn[standard]",
    "av",
    "opencv-python",
    "rerun-sdk",
    "pydantic",
    "depthai",
    "dexmate_urdf",
    "zarr",
    "numcodecs",
    "pyzmq",
    "msgpack",
]
```

**Step 2: Sync the environment**

Run: `cd server && uv sync`
Expected: resolves and installs pyzmq + msgpack without conflicts.

**Step 3: Verify imports**

Run: `cd server && uv run python -c "import zmq; import msgpack; print('ok')"`
Expected: `ok`

**Step 4: Commit**

```bash
git add server/pyproject.toml server/uv.lock
git commit -m "chore: add pyzmq and msgpack dependencies"
```

---

## Task 2: Create `telemetry_console/zmq_channels.py`

The shared constants and serialization helpers that every process agrees on.

**Files:**
- Create: `server/telemetry_console/__init__.py`
- Create: `server/telemetry_console/zmq_channels.py`
- Test: `tests/server/test_zmq_channels.py`

**Step 1: Write the failing test**

```python
# tests/server/test_zmq_channels.py
"""Tests for ZMQ channel constants and serialization."""

import numpy as np


def test_ports_are_distinct():
    from telemetry_console.zmq_channels import (
        ROBOT_STATE_PORT,
        RECORDER_STATUS_PORT,
        RECORDER_CONTROL_PORT,
    )
    ports = [ROBOT_STATE_PORT, RECORDER_STATUS_PORT, RECORDER_CONTROL_PORT]
    assert len(set(ports)) == 3, "All ZMQ ports must be unique"


def test_pack_unpack_roundtrip():
    from telemetry_console.zmq_channels import pack_state, unpack_state

    joint_names = ["L_arm_j1", "R_arm_j1"]
    cmd = np.array([0.1, -0.2], dtype=np.float32)
    state = np.array([0.05, -0.1], dtype=np.float32)
    t_ns = 1_000_000_000

    raw = pack_state(joint_names=joint_names, cmd=cmd, state=state, t_ns=t_ns)
    assert isinstance(raw, bytes)

    data = unpack_state(raw)
    assert data["joint_names"] == joint_names
    assert data["t_ns"] == t_ns
    np.testing.assert_array_almost_equal(data["cmd"], cmd)
    np.testing.assert_array_almost_equal(data["state"], state)


def test_pack_unpack_control_roundtrip():
    from telemetry_console.zmq_channels import pack_control, unpack_control

    raw = pack_control(command="start", run_id=None)
    data = unpack_control(raw)
    assert data["command"] == "start"
    assert data["run_id"] is None

    raw = pack_control(command="stop", run_id="20260209_120000_001")
    data = unpack_control(raw)
    assert data["command"] == "stop"
    assert data["run_id"] == "20260209_120000_001"


def test_pack_unpack_status_roundtrip():
    from telemetry_console.zmq_channels import pack_status, unpack_status

    raw = pack_status(active=True, run_id="run_001", samples=42)
    data = unpack_status(raw)
    assert data["active"] is True
    assert data["run_id"] == "run_001"
    assert data["samples"] == 42
```

**Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest ../tests/server/test_zmq_channels.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'telemetry_console'`

**Step 3: Create the package and module**

```python
# server/telemetry_console/__init__.py
"""Telemetry Console SDK."""

__version__ = "0.2.0"
```

```python
# server/telemetry_console/zmq_channels.py
"""ZMQ port assignments, topic prefixes, and serialization helpers.

Every process imports from here to agree on the wire format.
No runner-specific logic belongs in this module.
"""

from __future__ import annotations

import msgpack
import numpy as np

# ── Port assignments ──────────────────────────────────────────────
ROBOT_STATE_PORT = 5555       # PUB/SUB: robot env → recorder
RECORDER_STATUS_PORT = 5556   # PUB/SUB: recorder → gui
RECORDER_CONTROL_PORT = 5557  # REQ/REP: gui → recorder

# ── Topic prefixes (for PUB/SUB filtering) ────────────────────────
TOPIC_ROBOT_STATE = b"state"
TOPIC_RECORDER_STATUS = b"rec_status"

# ── Robot state (PUB on :5555) ────────────────────────────────────

def pack_state(
    *,
    joint_names: list[str],
    cmd: np.ndarray,
    state: np.ndarray,
    t_ns: int,
) -> bytes:
    """Serialize a robot state snapshot for ZMQ PUB."""
    return msgpack.packb({
        "joint_names": joint_names,
        "cmd": cmd.tolist(),
        "state": state.tolist(),
        "t_ns": int(t_ns),
    })


def unpack_state(raw: bytes) -> dict:
    """Deserialize a robot state snapshot from ZMQ SUB."""
    data = msgpack.unpackb(raw, raw=False)
    data["cmd"] = np.array(data["cmd"], dtype=np.float32)
    data["state"] = np.array(data["state"], dtype=np.float32)
    return data


# ── Recorder control (REQ/REP on :5557) ──────────────────────────

def pack_control(*, command: str, run_id: str | None = None) -> bytes:
    """Serialize a recording control command (start / stop / status)."""
    return msgpack.packb({"command": command, "run_id": run_id})


def unpack_control(raw: bytes) -> dict:
    """Deserialize a recording control command."""
    return msgpack.unpackb(raw, raw=False)


# ── Recorder status (PUB on :5556) ───────────────────────────────

def pack_status(*, active: bool, run_id: str | None, samples: int) -> bytes:
    """Serialize a recording status update."""
    return msgpack.packb({
        "active": active,
        "run_id": run_id,
        "samples": int(samples),
    })


def unpack_status(raw: bytes) -> dict:
    """Deserialize a recording status update."""
    return msgpack.unpackb(raw, raw=False)
```

**Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest ../tests/server/test_zmq_channels.py -v`
Expected: 4 tests PASS

**Step 5: Commit**

```bash
git add server/telemetry_console/ tests/server/test_zmq_channels.py
git commit -m "feat(sdk): add zmq_channels with port constants and serialization"
```

---

## Task 3: Extract `telemetry_console/viewer.py` from `rerun_bridge.py`

Split `server/rerun_bridge.py` into two concerns:
- `viewer.py` — Rerun server lifecycle, URDF loading, blueprints, joint-transform logging (shared utility)
- The sine-wave demo streaming stays in `rerun_bridge.py` for backward compat (will be removed later)

**Files:**
- Create: `server/telemetry_console/viewer.py`
- Modify: `server/rerun_bridge.py` (thin wrapper that imports from `viewer.py`)
- Test: `tests/server/test_viewer.py`

**Step 1: Write the failing test**

```python
# tests/server/test_viewer.py
"""Tests for telemetry_console.viewer utility module."""


def test_joint_names_defined():
    from telemetry_console.viewer import ARM_JOINT_NAMES
    assert len(ARM_JOINT_NAMES) == 14
    assert ARM_JOINT_NAMES[0] == "L_arm_j1"
    assert ARM_JOINT_NAMES[7] == "R_arm_j1"


def test_default_ports():
    from telemetry_console.viewer import DEFAULT_GRPC_PORT, DEFAULT_WEB_PORT
    assert DEFAULT_GRPC_PORT == 9876
    assert DEFAULT_WEB_PORT == 9090


def test_is_running_initially_false():
    from telemetry_console.viewer import is_running
    # Module-level state starts as False (no Rerun started in test)
    assert is_running() is False


def test_web_url_initially_none():
    from telemetry_console.viewer import web_url
    assert web_url() is None
```

**Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest ../tests/server/test_viewer.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Create `viewer.py`**

Move the following from `server/rerun_bridge.py` into `server/telemetry_console/viewer.py`:
- All constants (`DEFAULT_GRPC_PORT`, `DEFAULT_WEB_PORT`, joint name tuples, camera defaults)
- Module-level state (`_running`, `_web_url`, `_urdf_tree`, `_robot_root`)
- Functions: `is_running()`, `web_url()`, `_vega_1p_urdf_path()`, `load_vega_1p_model()`, `start()`, `_send_blueprint()`, `send_robot_blueprint()`, `_get_3d_view_contents()`, `_default_eye_controls()`, `log_arm_transforms()`, `get_joint_limits()`

The key content is the full body of `server/rerun_bridge.py` lines 1-312 (everything except `stream_sine_wave`, `_log_series_style`, `_log_shoulder_transforms`), reorganized as `telemetry_console.viewer`.

Then update `server/rerun_bridge.py` to become a thin re-export wrapper:

```python
# server/rerun_bridge.py
"""Backward-compat shim — delegates to telemetry_console.viewer."""

from telemetry_console.viewer import (  # noqa: F401
    ARM_JOINT_NAMES,
    DEFAULT_3D_CAMERA_POSITION,
    DEFAULT_3D_CAMERA_LOOK_TARGET,
    DEFAULT_GRPC_PORT,
    DEFAULT_WEB_PORT,
    LEFT_ARM_JOINT_NAMES,
    RIGHT_ARM_JOINT_NAMES,
    get_joint_limits,
    is_running,
    load_vega_1p_model,
    log_arm_transforms,
    send_robot_blueprint,
    start,
    web_url,
)

# Demo-only streaming (kept here, not in SDK)
from telemetry_console.viewer import _vega_1p_urdf_path  # noqa: F401
import math, time, rerun as rr  # noqa: E401

# ... keep stream_sine_wave, _log_series_style, _log_shoulder_transforms here
```

**Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest ../tests/server/test_viewer.py ../tests/server/test_rerun_sine.py -v`
Expected: all pass (new tests + existing backward-compat tests)

**Step 5: Commit**

```bash
git add server/telemetry_console/viewer.py server/rerun_bridge.py tests/server/test_viewer.py
git commit -m "refactor(sdk): extract viewer.py from rerun_bridge"
```

---

## Task 4: Extract `telemetry_console/camera.py` from `webrtc.py`

Remove the `RecordingManager` coupling. The camera module only discovers + encodes + publishes RTSP.

**Files:**
- Create: `server/telemetry_console/camera.py`
- Modify: `server/webrtc.py` (thin shim)
- Test: `tests/server/test_camera_module.py`

**Step 1: Write the failing test**

```python
# tests/server/test_camera_module.py
"""Tests for telemetry_console.camera (no recording dependency)."""

import inspect


def test_camera_module_does_not_import_data_log():
    """The camera module must not depend on recording."""
    import telemetry_console.camera as cam
    source = inspect.getsource(cam)
    assert "data_log" not in source
    assert "RecordingManager" not in source


def test_ensure_streaming_signature_has_no_recording_manager():
    import telemetry_console.camera as cam
    sig = inspect.signature(cam.ensure_streaming)
    assert "recording_manager" not in sig.parameters


def test_camera_relay_publisher_has_no_recording_manager():
    import telemetry_console.camera as cam
    sig = inspect.signature(cam.CameraRelayPublisher.__init__)
    assert "recording_manager" not in sig.parameters


def test_camera_constants():
    from telemetry_console.camera import DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FPS
    assert DEFAULT_WIDTH == 640
    assert DEFAULT_HEIGHT == 480
    assert DEFAULT_FPS == 30
```

**Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest ../tests/server/test_camera_module.py -v`
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Create `camera.py`**

Copy `server/webrtc.py` into `server/telemetry_console/camera.py` with these changes:

1. **Remove** `from data_log import RecordingManager` (line 15)
2. **Remove** `recording_manager` parameter from `CameraRelayPublisher.__init__` (line 170)
3. **Remove** `self._recording_manager` and its property/setter (lines 176, 185-191)
4. **Remove** `self._decoder`, `self._decoder_error`, `self._logging_error` fields (lines 180-182)
5. **Remove** the `_maybe_record()` method entirely (lines 269-304)
6. **Remove** the `self._maybe_record(payload, packet)` call in `run()` (line 206)
7. **Remove** `recording_manager` parameter from `ensure_streaming()` (line 406)
8. **Remove** `recording_manager=recording_manager` from the `CameraRelayPublisher()` constructor call (line 449)
9. **Remove** `publisher.recording_manager = recording_manager` (line 454)

The `CameraRelayPublisher.run()` loop becomes:

```python
def run(self) -> None:
    self._start_ffmpeg()
    while not self._stop_event.is_set():
        packet = self._queue.tryGet()
        if packet is None:
            time.sleep(0.002)
            continue
        payload = bytes(packet.getData())
        if not payload:
            continue
        self._forward(payload)
    self._close_ffmpeg()
```

Keep `H264Decoder` in this module (it's useful for tests) but it's no longer called from the publisher.

**Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest ../tests/server/test_camera_module.py -v`
Expected: 4 tests PASS

**Step 5: Commit**

```bash
git add server/telemetry_console/camera.py tests/server/test_camera_module.py
git commit -m "refactor(sdk): extract camera.py without recording coupling"
```

---

## Task 5: Extract `telemetry_console/env.py` with ZMQ publishing

Move `RobotEnv` and add ZMQ PUB so `run_recorder` can subscribe to robot state.

**Files:**
- Create: `server/telemetry_console/env.py`
- Modify: `server/robot_env.py` (thin shim)
- Test: `tests/server/test_env_zmq.py`

**Step 1: Write the failing test**

```python
# tests/server/test_env_zmq.py
"""Tests for telemetry_console.env ZMQ state publishing."""

import time
import threading

import numpy as np
import zmq

from telemetry_console.zmq_channels import ROBOT_STATE_PORT, unpack_state


def test_env_publishes_state_on_step(monkeypatch):
    """RobotEnv.step() should publish cmd+state via ZMQ PUB."""
    # Patch out Rerun calls so we don't need a running server
    import telemetry_console.viewer as viewer
    monkeypatch.setattr(viewer, "_running", True)
    monkeypatch.setattr(viewer, "_web_url", "http://fake:9090")

    import rerun as rr
    monkeypatch.setattr(rr, "set_time", lambda *a, **kw: None)
    monkeypatch.setattr(rr, "log", lambda *a, **kw: None)
    monkeypatch.setattr(viewer, "load_vega_1p_model", lambda: None)
    monkeypatch.setattr(viewer, "send_robot_blueprint", lambda **kw: None)
    monkeypatch.setattr(viewer, "log_arm_transforms", lambda *a, **kw: None)
    monkeypatch.setattr(viewer, "get_joint_limits", lambda: {
        name: (-3.14, 3.14) for name in viewer.ARM_JOINT_NAMES
    })

    from telemetry_console.env import RobotEnv

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVTIMEO, 2000)
    sub.connect(f"tcp://127.0.0.1:{ROBOT_STATE_PORT}")
    time.sleep(0.1)  # let SUB connect

    env = RobotEnv(hz=20, tau=0.1, zmq_pub_port=ROBOT_STATE_PORT)
    env.reset()
    action = np.zeros(env.action_dim, dtype=np.float32)
    env.step(action)

    # Should receive at least one state message
    topic = sub.recv()
    raw = sub.recv()
    data = unpack_state(raw)
    assert "cmd" in data
    assert "state" in data
    assert "t_ns" in data
    assert len(data["cmd"]) == env.action_dim

    env.close()
    sub.close()
    ctx.term()
```

**Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest ../tests/server/test_env_zmq.py -v`
Expected: FAIL

**Step 3: Create `env.py`**

Copy `server/robot_env.py` into `server/telemetry_console/env.py` with these changes:

1. Replace `import rerun_bridge` with `from telemetry_console import viewer`
2. Replace all `rerun_bridge.` calls with `viewer.` calls
3. Add ZMQ PUB socket to `__init__`:

```python
import zmq
from telemetry_console.zmq_channels import (
    ROBOT_STATE_PORT,
    TOPIC_ROBOT_STATE,
    pack_state,
)

class RobotEnv:
    JOINT_NAMES = tuple(viewer.ARM_JOINT_NAMES)

    def __init__(
        self,
        hz: float = 20.0,
        tau: float = 0.1,
        *,
        open_browser: bool = False,
        viewer_window_seconds: float = 5.0,
        zmq_pub_port: int = ROBOT_STATE_PORT,
    ) -> None:
        # ... existing validation ...
        # ZMQ publisher
        self._zmq_ctx = zmq.Context()
        self._zmq_pub = self._zmq_ctx.socket(zmq.PUB)
        self._zmq_pub.bind(f"tcp://*:{zmq_pub_port}")
        # ... rest of init ...
```

4. Extend `_log_state` to also publish via ZMQ:

```python
def _log_state(self, timestamp: float) -> None:
    rr.set_time("wall_time", timestamp=timestamp)
    joint_positions: dict[str, float] = {}
    for idx, joint_name in enumerate(self._joint_names):
        cmd_value = float(self._cmd[idx])
        state_value = float(self._state[idx])
        rr.log(f"trajectory/cmd/{joint_name}", rr.Scalars(cmd_value))
        rr.log(f"trajectory/state/{joint_name}", rr.Scalars(state_value))
        joint_positions[joint_name] = state_value
    viewer.log_arm_transforms(joint_positions)

    # Publish to ZMQ for recorder
    t_ns = int(timestamp * 1e9)
    self._zmq_pub.send(TOPIC_ROBOT_STATE, zmq.SNDMORE)
    self._zmq_pub.send(pack_state(
        joint_names=self._joint_names,
        cmd=self._cmd,
        state=self._state,
        t_ns=t_ns,
    ))
```

5. Clean up ZMQ in `close()`:

```python
def close(self) -> None:
    self._closed = True
    self._zmq_pub.close()
    self._zmq_ctx.term()
```

**Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest ../tests/server/test_env_zmq.py -v`
Expected: PASS

Also run existing env tests to confirm backward compat:
Run: `cd server && uv run pytest ../tests/server/test_robot_env.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add server/telemetry_console/env.py tests/server/test_env_zmq.py
git commit -m "feat(sdk): extract env.py with ZMQ state publishing"
```

---

## Task 6: Create `telemetry_console/recorder.py`

Independent process: subscribes to RTSP (camera frames) + ZMQ (robot state), writes Zarr. Controlled via ZMQ REQ/REP.

**Files:**
- Create: `server/telemetry_console/recorder.py`
- Test: `tests/server/test_recorder_zmq.py`

**Step 1: Write the failing test**

```python
# tests/server/test_recorder_zmq.py
"""Tests for telemetry_console.recorder ZMQ control interface."""

import threading
import time

import zmq

from telemetry_console.zmq_channels import (
    RECORDER_CONTROL_PORT,
    RECORDER_STATUS_PORT,
    pack_control,
    unpack_status,
)


def test_recorder_responds_to_status_query(tmp_path):
    from telemetry_console.recorder import Recorder

    rec = Recorder(
        base_dir=tmp_path / "logs",
        zmq_control_port=RECORDER_CONTROL_PORT,
        zmq_status_port=RECORDER_STATUS_PORT,
        rtsp_urls=[],  # no cameras for this test
        zmq_state_port=0,  # disabled
    )

    t = threading.Thread(target=rec.run, daemon=True)
    t.start()
    time.sleep(0.3)  # let recorder bind

    ctx = zmq.Context()
    req = ctx.socket(zmq.REQ)
    req.setsockopt(zmq.RCVTIMEO, 2000)
    req.connect(f"tcp://127.0.0.1:{RECORDER_CONTROL_PORT}")

    # Query status
    req.send(pack_control(command="status"))
    reply = unpack_status(req.recv())
    assert reply["active"] is False
    assert reply["samples"] == 0

    rec.stop()
    req.close()
    ctx.term()


def test_recorder_start_stop_cycle(tmp_path):
    from telemetry_console.recorder import Recorder

    rec = Recorder(
        base_dir=tmp_path / "logs",
        zmq_control_port=RECORDER_CONTROL_PORT + 10,  # avoid port conflict
        zmq_status_port=RECORDER_STATUS_PORT + 10,
        rtsp_urls=[],
        zmq_state_port=0,
    )

    t = threading.Thread(target=rec.run, daemon=True)
    t.start()
    time.sleep(0.3)

    ctx = zmq.Context()
    req = ctx.socket(zmq.REQ)
    req.setsockopt(zmq.RCVTIMEO, 2000)
    req.connect(f"tcp://127.0.0.1:{RECORDER_CONTROL_PORT + 10}")

    # Start
    req.send(pack_control(command="start"))
    reply = unpack_status(req.recv())
    assert reply["active"] is True
    assert reply["run_id"] is not None

    # Stop
    req.send(pack_control(command="stop"))
    reply = unpack_status(req.recv())
    assert reply["active"] is False

    rec.stop()
    req.close()
    ctx.term()
```

**Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest ../tests/server/test_recorder_zmq.py -v`
Expected: FAIL

**Step 3: Create `recorder.py`**

The `Recorder` class:
- Binds ZMQ REP on control port (start/stop/status)
- Binds ZMQ PUB on status port (broadcasts state changes)
- Optionally connects ZMQ SUB to robot state port
- Optionally subscribes to RTSP streams via `av` for camera frames
- Manages `RecordingManager` + `ZarrEpisodeLogger` internally (moves `data_log.py` logic here)
- Main loop polls ZMQ control socket + RTSP frames + ZMQ state socket

```python
# server/telemetry_console/recorder.py
"""Independent recording process: RTSP + ZMQ → Zarr."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Sequence

import numpy as np
import zmq

from telemetry_console.zmq_channels import (
    RECORDER_CONTROL_PORT,
    RECORDER_STATUS_PORT,
    ROBOT_STATE_PORT,
    TOPIC_ROBOT_STATE,
    pack_status,
    unpack_control,
    unpack_state,
)

# Re-use existing Zarr classes (they have no runner dependencies)
import sys, os  # noqa: E401
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data_log import RecordingManager  # noqa: E402


class Recorder:
    """Recording process controlled via ZMQ."""

    def __init__(
        self,
        base_dir: Path,
        *,
        zmq_control_port: int = RECORDER_CONTROL_PORT,
        zmq_status_port: int = RECORDER_STATUS_PORT,
        zmq_state_port: int = ROBOT_STATE_PORT,
        rtsp_urls: Sequence[str] = (),
    ) -> None:
        self._base_dir = Path(base_dir)
        self._control_port = zmq_control_port
        self._status_port = zmq_status_port
        self._state_port = zmq_state_port
        self._rtsp_urls = list(rtsp_urls)
        self._stop_event = threading.Event()
        self._manager = RecordingManager(self._base_dir)

    def run(self) -> None:
        """Main loop: poll ZMQ control, optionally ingest RTSP + state."""
        ctx = zmq.Context()

        control = ctx.socket(zmq.REP)
        control.bind(f"tcp://*:{self._control_port}")

        status_pub = ctx.socket(zmq.PUB)
        status_pub.bind(f"tcp://*:{self._status_port}")

        poller = zmq.Poller()
        poller.register(control, zmq.POLLIN)

        # Optional: subscribe to robot state
        state_sub = None
        if self._state_port > 0:
            state_sub = ctx.socket(zmq.SUB)
            state_sub.setsockopt(zmq.SUBSCRIBE, TOPIC_ROBOT_STATE)
            state_sub.connect(f"tcp://127.0.0.1:{self._state_port}")
            poller.register(state_sub, zmq.POLLIN)

        while not self._stop_event.is_set():
            events = dict(poller.poll(timeout=100))

            if control in events:
                raw = control.recv()
                msg = unpack_control(raw)
                reply = self._handle_command(msg)
                control.send(reply)
                status_pub.send(reply)

            if state_sub is not None and state_sub in events:
                state_sub.recv()  # topic frame
                raw = state_sub.recv()
                # TODO: write robot state to Zarr alongside camera frames
                _ = unpack_state(raw)

        control.close()
        status_pub.close()
        if state_sub is not None:
            state_sub.close()
        ctx.term()

    def _handle_command(self, msg: dict) -> bytes:
        command = msg.get("command", "status")
        if command == "start":
            state = self._manager.start()
        elif command == "stop":
            state = self._manager.stop()
        else:
            state = self._manager.status()
        return pack_status(
            active=state.active,
            run_id=state.run_id,
            samples=state.samples,
        )

    def stop(self) -> None:
        self._stop_event.set()
```

**Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest ../tests/server/test_recorder_zmq.py -v`
Expected: 2 tests PASS

**Step 5: Commit**

```bash
git add server/telemetry_console/recorder.py tests/server/test_recorder_zmq.py
git commit -m "feat(sdk): add recorder with ZMQ control interface"
```

---

## Task 7: Create `telemetry_console/replay.py`

Reads a Zarr episode and logs everything through Rerun (images + scalars + transforms).

**Files:**
- Create: `server/telemetry_console/replay.py`
- Test: `tests/server/test_replay.py`

**Step 1: Write the failing test**

```python
# tests/server/test_replay.py
"""Tests for telemetry_console.replay."""

import numpy as np
import zarr


def test_replayer_iterates_episode(tmp_path):
    from telemetry_console.replay import Replayer

    # Create a minimal Zarr episode
    store_path = tmp_path / "episode.zarr"
    group = zarr.open_group(store_path, mode="w")
    n_frames = 5
    h, w = 4, 4
    group.create_dataset("rgb", data=np.random.randint(0, 255, (n_frames, h, w, 3), dtype="u1"))
    group.create_dataset("t_ns", data=np.arange(n_frames, dtype="i8") * 50_000_000)
    group.attrs["height"] = h
    group.attrs["width"] = w

    replayer = Replayer(store_path)
    frames = list(replayer.iter_frames())
    assert len(frames) == n_frames
    assert frames[0]["rgb"].shape == (h, w, 3)
    assert frames[0]["t_ns"] == 0


def test_replayer_handles_empty_episode(tmp_path):
    from telemetry_console.replay import Replayer

    store_path = tmp_path / "empty.zarr"
    group = zarr.open_group(store_path, mode="w")
    group.create_dataset("rgb", shape=(0, 4, 4, 3), dtype="u1")
    group.create_dataset("t_ns", shape=(0,), dtype="i8")

    replayer = Replayer(store_path)
    frames = list(replayer.iter_frames())
    assert frames == []
```

**Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest ../tests/server/test_replay.py -v`
Expected: FAIL

**Step 3: Create `replay.py`**

```python
# server/telemetry_console/replay.py
"""Replay a Zarr episode through Rerun (images + scalars + 3D)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import rerun as rr
import zarr

from telemetry_console import viewer


class Replayer:
    """Read a Zarr episode and iterate or stream through Rerun."""

    def __init__(self, zarr_path: Path | str) -> None:
        self._path = Path(zarr_path)
        self._group = zarr.open_group(self._path, mode="r")

    @property
    def n_frames(self) -> int:
        return int(self._group["t_ns"].shape[0])

    def iter_frames(self) -> Iterator[dict[str, Any]]:
        """Yield dicts with keys rgb, t_ns, and optionally joint data."""
        n = self.n_frames
        for i in range(n):
            frame: dict[str, Any] = {
                "rgb": np.array(self._group["rgb"][i]),
                "t_ns": int(self._group["t_ns"][i]),
            }
            if "joint_cmd" in self._group:
                frame["joint_cmd"] = np.array(self._group["joint_cmd"][i])
            if "joint_state" in self._group:
                frame["joint_state"] = np.array(self._group["joint_state"][i])
            yield frame

    def play(self, *, speed: float = 1.0) -> None:
        """Stream frames to Rerun at real-time pace (scaled by speed)."""
        prev_t_ns: int | None = None
        joint_names = list(viewer.ARM_JOINT_NAMES)

        for frame in self.iter_frames():
            t_ns = frame["t_ns"]
            t_sec = t_ns * 1e-9

            # Sleep to match real-time pace
            if prev_t_ns is not None and speed > 0:
                dt = (t_ns - prev_t_ns) * 1e-9 / speed
                if dt > 0:
                    time.sleep(dt)
            prev_t_ns = t_ns

            rr.set_time("wall_time", timestamp=t_sec)
            rr.log("cameras/rgb", rr.Image(frame["rgb"]))

            # Replay joint data if available
            joint_cmd = frame.get("joint_cmd")
            joint_state = frame.get("joint_state")
            if joint_cmd is not None and joint_state is not None:
                positions: dict[str, float] = {}
                for idx, name in enumerate(joint_names):
                    if idx < len(joint_cmd):
                        rr.log(f"trajectory/cmd/{name}", rr.Scalars(float(joint_cmd[idx])))
                    if idx < len(joint_state):
                        val = float(joint_state[idx])
                        rr.log(f"trajectory/state/{name}", rr.Scalars(val))
                        positions[name] = val
                viewer.log_arm_transforms(positions)
```

**Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest ../tests/server/test_replay.py -v`
Expected: 2 tests PASS

**Step 5: Commit**

```bash
git add server/telemetry_console/replay.py tests/server/test_replay.py
git commit -m "feat(sdk): add replay module for Zarr episode playback via Rerun"
```

---

## Task 8: Create `telemetry_console/gui_api.py`

Thin FastAPI app: health, rerun status, recording toggle via ZMQ (no direct recording manager).

**Files:**
- Create: `server/telemetry_console/gui_api.py`
- Modify: `server/main.py` (become a shim that imports from `gui_api`)
- Test: `tests/server/test_gui_api.py`

**Step 1: Write the failing test**

```python
# tests/server/test_gui_api.py
"""Tests for the thin GUI API."""

import inspect


def test_gui_api_does_not_import_webrtc():
    import telemetry_console.gui_api as gui_api
    source = inspect.getsource(gui_api)
    assert "import webrtc" not in source
    assert "from webrtc" not in source


def test_gui_api_does_not_import_data_log():
    import telemetry_console.gui_api as gui_api
    source = inspect.getsource(gui_api)
    assert "import data_log" not in source
    assert "from data_log" not in source


def test_gui_api_has_health_endpoint():
    from telemetry_console.gui_api import app
    routes = [r.path for r in app.routes]
    assert "/health" in routes
```

**Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest ../tests/server/test_gui_api.py -v`
Expected: FAIL

**Step 3: Create `gui_api.py`**

```python
# server/telemetry_console/gui_api.py
"""Thin FastAPI app for the GUI process.

Routes:
  GET  /health
  GET  /rerun/status
  GET  /recording/status   → ZMQ REQ to recorder
  POST /recording/start    → ZMQ REQ to recorder
  POST /recording/stop     → ZMQ REQ to recorder
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import zmq

from telemetry_console import viewer
from telemetry_console.zmq_channels import (
    RECORDER_CONTROL_PORT,
    pack_control,
    unpack_status,
)
from telemetry_console.schemas import RecordingStatus

app = FastAPI(title="Telemetry Console GUI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_zmq_ctx: zmq.Context | None = None
_zmq_req: zmq.Socket | None = None


def _get_recorder_socket() -> zmq.Socket:
    global _zmq_ctx, _zmq_req
    if _zmq_ctx is None:
        _zmq_ctx = zmq.Context()
    if _zmq_req is None:
        _zmq_req = _zmq_ctx.socket(zmq.REQ)
        _zmq_req.setsockopt(zmq.RCVTIMEO, 2000)
        _zmq_req.connect(f"tcp://127.0.0.1:{RECORDER_CONTROL_PORT}")
    return _zmq_req


def _send_recording_command(command: str) -> dict:
    sock = _get_recorder_socket()
    sock.send(pack_control(command=command))
    return unpack_status(sock.recv())


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/rerun/status")
async def rerun_status():
    return {"running": viewer.is_running(), "web_url": viewer.web_url()}


@app.get("/recording/status", response_model=RecordingStatus)
async def recording_status() -> RecordingStatus:
    data = _send_recording_command("status")
    return RecordingStatus(
        active=data["active"],
        run_id=data.get("run_id"),
        samples=data.get("samples", 0),
        state="recording" if data["active"] else "idle",
    )


@app.post("/recording/start", response_model=RecordingStatus)
async def recording_start() -> RecordingStatus:
    data = _send_recording_command("start")
    return RecordingStatus(
        active=data["active"],
        run_id=data.get("run_id"),
        samples=data.get("samples", 0),
        state="started" if data["active"] else "idle",
    )


@app.post("/recording/stop", response_model=RecordingStatus)
async def recording_stop() -> RecordingStatus:
    data = _send_recording_command("stop")
    return RecordingStatus(
        active=data["active"],
        run_id=data.get("run_id"),
        samples=data.get("samples", 0),
        state="stopped",
    )
```

Also move schemas:

```python
# server/telemetry_console/schemas.py
"""Pydantic models for request/response payloads."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class RecordingStatus(BaseModel):
    active: bool
    run_id: str | None = None
    samples: int = 0
    state: str
```

**Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest ../tests/server/test_gui_api.py -v`
Expected: 3 tests PASS

**Step 5: Commit**

```bash
git add server/telemetry_console/gui_api.py server/telemetry_console/schemas.py tests/server/test_gui_api.py
git commit -m "feat(sdk): add gui_api with ZMQ-based recording control"
```

---

## Task 9: Create `telemetry_console/cli.py` with entry points

Five entry-point functions, one per runner.

**Files:**
- Create: `server/telemetry_console/cli.py`
- Modify: `server/pyproject.toml` (add `[project.scripts]`)
- Test: `tests/server/test_cli.py`

**Step 1: Write the failing test**

```python
# tests/server/test_cli.py
"""Tests for CLI entry points."""

import importlib


def test_cli_module_imports():
    mod = importlib.import_module("telemetry_console.cli")
    assert callable(getattr(mod, "run_gui", None))
    assert callable(getattr(mod, "run_camera", None))
    assert callable(getattr(mod, "run_robot", None))
    assert callable(getattr(mod, "run_recorder", None))
    assert callable(getattr(mod, "run_replay", None))
```

**Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest ../tests/server/test_cli.py -v`
Expected: FAIL

**Step 3: Create `cli.py`**

```python
# server/telemetry_console/cli.py
"""CLI entry points for each runner process."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run_gui() -> None:
    """Start Vite client + Rerun viewer + thin FastAPI API."""
    parser = argparse.ArgumentParser(description="Start the GUI viewer process.")
    parser.add_argument("--port", type=int, default=8000, help="API server port")
    parser.add_argument("--no-client", action="store_true", help="Skip Vite dev server")
    args = parser.parse_args()

    # Start Vite client
    if not args.no_client:
        client_dir = Path(__file__).resolve().parents[1] / "client"
        if (client_dir / "package.json").is_file():
            subprocess.Popen(["npm", "run", "dev"], cwd=str(client_dir))

    # Start Rerun viewer
    from telemetry_console import viewer
    viewer.start()

    # Start FastAPI
    import uvicorn
    uvicorn.run("telemetry_console.gui_api:app", host="0.0.0.0", port=args.port)


def run_camera() -> None:
    """Start DepthAI camera relay to MediaMTX."""
    parser = argparse.ArgumentParser(description="Start camera relay to MediaMTX.")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()

    from telemetry_console.camera import ensure_streaming, list_camera_sockets

    sockets = list_camera_sockets()
    if not sockets:
        print("[tc-camera] No cameras found.")
        sys.exit(1)

    print(f"[tc-camera] Starting relay for {len(sockets)} camera(s)...")
    ensure_streaming(
        camera_sockets=sockets,
        width=args.width,
        height=args.height,
        fps=args.fps,
    )

    print("[tc-camera] Streaming. Press Ctrl+C to stop.")
    try:
        import time
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        from telemetry_console.camera import stop_streaming
        stop_streaming()


def run_robot() -> None:
    """Start the robot control loop (demo or custom)."""
    parser = argparse.ArgumentParser(description="Start robot env control loop.")
    parser.add_argument("--hz", type=float, default=20.0)
    parser.add_argument("--tau", type=float, default=0.15)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--no-open-browser", action="store_true")
    args = parser.parse_args()

    import time
    import numpy as np
    from telemetry_console.env import RobotEnv

    env = RobotEnv(hz=args.hz, tau=args.tau, open_browser=not args.no_open_browser)
    env.reset()
    low, high = env.get_action_space()

    print(f"[tc-robot] Running demo at {args.hz} Hz. Ctrl+C to stop.")
    try:
        t0 = time.time()
        while True:
            t = time.time() - t0
            action = np.zeros(env.action_dim, dtype=np.float32)
            # Simple demo motion
            action[0] = np.pi / 2
            action[3] = -np.pi / 2 + 0.5 * np.sin(t * 0.5)
            action[7] = -np.pi / 2
            action[10] = -np.pi / 2 + 0.5 * np.sin(t * 0.5)
            action = np.clip(action, low, high)
            env.step(action)
            if args.duration is not None and t >= args.duration:
                break
            time.sleep(1.0 / env.hz)
    except KeyboardInterrupt:
        pass
    finally:
        env.close()


def run_recorder() -> None:
    """Start the recording process (ZMQ-controlled)."""
    parser = argparse.ArgumentParser(description="Start the recorder process.")
    parser.add_argument("--log-dir", type=str, default="data_logs")
    args = parser.parse_args()

    from telemetry_console.recorder import Recorder

    rec = Recorder(base_dir=Path(args.log_dir))
    print(f"[tc-recorder] Ready. Waiting for start command on ZMQ.")
    try:
        rec.run()
    except KeyboardInterrupt:
        rec.stop()


def run_replay() -> None:
    """Replay a Zarr episode through Rerun."""
    parser = argparse.ArgumentParser(description="Replay a recorded episode.")
    parser.add_argument("zarr_path", help="Path to .zarr episode directory")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--no-open-browser", action="store_true")
    args = parser.parse_args()

    from telemetry_console import viewer
    from telemetry_console.replay import Replayer

    viewer.start(open_browser=not args.no_open_browser)

    replayer = Replayer(args.zarr_path)
    print(f"[tc-replay] Playing {replayer.n_frames} frames at {args.speed}x speed.")
    replayer.play(speed=args.speed)
    print("[tc-replay] Done.")
```

**Step 4: Add entry points to `pyproject.toml`**

Append to `server/pyproject.toml`:

```toml
[project.scripts]
tc-gui      = "telemetry_console.cli:run_gui"
tc-camera   = "telemetry_console.cli:run_camera"
tc-robot    = "telemetry_console.cli:run_robot"
tc-recorder = "telemetry_console.cli:run_recorder"
tc-replay   = "telemetry_console.cli:run_replay"
```

**Step 5: Run tests**

Run: `cd server && uv run pytest ../tests/server/test_cli.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add server/telemetry_console/cli.py server/pyproject.toml tests/server/test_cli.py
git commit -m "feat(sdk): add CLI entry points for all five runners"
```

---

## Task 10: Update `scripts/dev.sh` and `Makefile`

Replace the old process model with the new five-runner model.

**Files:**
- Modify: `scripts/dev.sh`
- Modify: `Makefile`

**Step 1: Update `scripts/dev.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

trap 'kill 0; exit' SIGINT SIGTERM

echo "==> Starting GUI (Vite + Rerun + API)..."
uv run --project server tc-gui --no-client &
(cd client && npm run dev) &

if command -v mediamtx >/dev/null 2>&1; then
  echo "==> Starting MediaMTX relay..."
  mediamtx &
else
  echo "==> MediaMTX not found; camera streaming offline."
  echo "    Install with: brew install mediamtx"
fi

echo "==> Starting camera relay..."
uv run --project server tc-camera &

echo "==> Starting recorder..."
uv run --project server tc-recorder &

echo "==> Starting robot demo..."
uv run --project server tc-robot --no-open-browser &

wait
```

**Step 2: Update `Makefile`**

Add new targets:

```makefile
gui:
	uv run --project server tc-gui

camera:
	uv run --project server tc-camera

recorder:
	uv run --project server tc-recorder

replay:
	uv run --project server tc-replay $(ARGS)
```

**Step 3: Verify**

Run: `make dev`
Expected: All five processes start; Vite on `:5173`, API on `:8000`, Rerun on `:9090/:9876`

**Step 4: Commit**

```bash
git add scripts/dev.sh Makefile
git commit -m "chore: update dev.sh and Makefile for five-runner model"
```

---

## Task 11: Update backward-compat shims and run full test suite

Make `server/main.py`, `server/webrtc.py`, `server/robot_env.py` into thin shims that re-export from `telemetry_console.*` so existing tests pass without modification.

**Files:**
- Modify: `server/main.py`
- Modify: `server/webrtc.py`
- Modify: `server/robot_env.py`
- Modify: `server/schemas.py`

**Step 1: Update shims**

`server/main.py`:
```python
"""Backward-compat entry point — delegates to telemetry_console.gui_api."""
from telemetry_console.gui_api import app  # noqa: F401
```

`server/robot_env.py`:
```python
"""Backward-compat shim."""
from telemetry_console.env import RobotEnv  # noqa: F401
```

`server/schemas.py`:
```python
"""Backward-compat shim."""
from telemetry_console.schemas import HealthResponse, RecordingStatus  # noqa: F401
```

`server/webrtc.py` stays as a shim re-exporting from `telemetry_console.camera` plus legacy `ensure_streaming` with the `recording_manager` parameter (ignored, for API compat):

```python
"""Backward-compat shim for webrtc module."""
from telemetry_console.camera import (  # noqa: F401
    ensure_streaming as _ensure_streaming,
    stop_streaming,
    list_camera_sockets,
    order_camera_sockets,
    CameraRelayPublisher,
    DEFAULT_WIDTH,
    DEFAULT_HEIGHT,
    DEFAULT_FPS,
)


def ensure_streaming(*, recording_manager=None, **kwargs):
    """Compat wrapper: ignores recording_manager."""
    return _ensure_streaming(**kwargs)
```

**Step 2: Run full test suite**

Run: `cd server && uv run pytest ../tests/server -v`
Expected: All existing tests pass (some may need minor import path fixes)

Run: `cd client && npm test`
Expected: All client tests pass (unchanged)

**Step 3: Commit**

```bash
git add server/main.py server/webrtc.py server/robot_env.py server/schemas.py
git commit -m "refactor(sdk): convert legacy modules to backward-compat shims"
```

---

## Task 12: Update `telemetry_console/__init__.py` public API

**Files:**
- Modify: `server/telemetry_console/__init__.py`

**Step 1: Add public re-exports**

```python
# server/telemetry_console/__init__.py
"""Telemetry Console SDK.

Usage (in your robot project):

    from telemetry_console import RobotEnv

    class MyRobot(RobotEnv):
        ...
"""

__version__ = "0.2.0"

from telemetry_console.env import RobotEnv  # noqa: F401
from telemetry_console.recorder import Recorder  # noqa: F401
from telemetry_console.replay import Replayer  # noqa: F401
```

**Step 2: Verify**

Run: `cd server && uv run python -c "from telemetry_console import RobotEnv, Recorder, Replayer; print('ok')"`
Expected: `ok`

**Step 3: Commit**

```bash
git add server/telemetry_console/__init__.py
git commit -m "feat(sdk): export RobotEnv, Recorder, Replayer from package root"
```

---

## Task 13: Update `docs/infra.md` with the new architecture

**Files:**
- Modify: `docs/infra.md`

**Step 1: Update the doc**

Replace the current content with the new five-runner architecture, ZMQ socket layout, and updated diagrams. Reference the new package layout and entry points.

**Step 2: Commit**

```bash
git add docs/infra.md
git commit -m "docs: update infra.md for five-runner SDK architecture"
```

---

## Dependency graph (final state)

```
telemetry_console/
  zmq_channels.py   ← no imports from package
  viewer.py          ← rerun-sdk only
  schemas.py         ← pydantic only
  camera.py          ← depthai, av (no zmq, no data_log, no viewer)
  env.py             ← viewer, zmq_channels
  recorder.py        ← zmq_channels, data_log (Zarr classes)
  replay.py          ← viewer, zarr
  gui_api.py         ← viewer, zmq_channels, schemas
  cli.py             ← imports each module lazily inside its function
```

**No runner module imports another runner module.**

---

Historical plan section ends here.

Current branch status: this plan has been implemented in milestone increments.
Keep the status section at the top updated for operational adjustments and any
follow-up refactors.
