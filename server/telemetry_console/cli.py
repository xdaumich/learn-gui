"""CLI entry points for each runner process."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_ROBOT_HEARTBEAT_PATH = Path("data_logs/.robot_heartbeat.json")


def run_gui() -> None:
    """Start Vite client + Rerun viewer + thin FastAPI API."""
    parser = argparse.ArgumentParser(description="Start the GUI viewer process.")
    parser.add_argument("--port", type=int, default=8000, help="API server port")
    parser.add_argument("--no-client", action="store_true", help="Skip Vite dev server")
    parser.add_argument(
        "--no-rerun",
        action="store_true",
        help="Skip starting embedded Rerun services (video-only debug mode).",
    )
    args = parser.parse_args()

    if not args.no_client:
        client_dir = Path(__file__).resolve().parents[2] / "client"
        if (client_dir / "package.json").is_file():
            subprocess.Popen(["npm", "run", "dev"], cwd=str(client_dir))

    from telemetry_console import viewer

    if not args.no_rerun:
        viewer.start()

    import uvicorn

    uvicorn.run("telemetry_console.gui_api:app", host="0.0.0.0", port=args.port)


def run_camera() -> None:
    """Start DepthAI camera relay to MediaMTX."""
    parser = argparse.ArgumentParser(description="Start camera relay to MediaMTX.")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--startup-timeout", type=float, default=20.0)
    parser.add_argument("--retry-interval", type=float, default=0.5)
    parser.add_argument(
        "--min-cameras",
        type=int,
        default=int(os.environ.get("MIN_CAMERAS", "3")),
        help="Keep retrying during startup until this many camera streams are active.",
    )
    args = parser.parse_args()

    from telemetry_console.camera import ensure_streaming, list_stream_targets, stop_streaming

    startup_timeout = float(args.startup_timeout)
    min_cameras = max(1, int(args.min_cameras))
    deadline: float | None = None
    if startup_timeout > 0:
        deadline = time.time() + max(0.1, startup_timeout)
    retry_interval = max(0.05, float(args.retry_interval))
    last_error: Exception | None = None
    active_streams: list[str] = []
    try:
        while deadline is None or time.time() < deadline:
            try:
                active_streams = ensure_streaming(
                    camera_sockets=None,
                    width=args.width,
                    height=args.height,
                    fps=args.fps,
                )
                if len(active_streams) >= min_cameras:
                    break
                # Have some streams but not enough — keep retrying for remaining slots.
            except Exception as exc:  # pragma: no cover - hardware/runtime dependent
                # DepthAI can intermittently throw RuntimeError/ValueError while USB
                # devices are booting. Keep retrying until startup timeout.
                last_error = exc
            time.sleep(retry_interval)
    except KeyboardInterrupt:
        stop_streaming()
        return

    if not active_streams:
        if deadline is None:
            print("[tc-camera] Waiting for cameras (startup timeout disabled).")
        elif last_error is None:
            print("[tc-camera] No cameras found before startup timeout.")
        else:
            print(f"[tc-camera] Failed to start relay: {last_error}")
        sys.exit(1)

    def _print_stream_state(stream_names: list[str]) -> tuple[tuple[str, str, str], ...]:
        print(
            f"[tc-camera] Streaming {len(stream_names)} camera stream(s): "
            f"{', '.join(stream_names)}. Press Ctrl+C to stop."
        )
        snapshot: list[tuple[str, str, str]] = []
        for target in list_stream_targets():
            snapshot.append((target.stream_name, target.device_name, target.device_id))
            print(
                f"[tc-camera]   slot={target.stream_name} "
                f"model={target.device_name} mxid={target.device_id}"
            )
        return tuple(snapshot)

    last_snapshot = _print_stream_state(active_streams)
    try:
        while True:
            time.sleep(max(0.25, retry_interval))
            try:
                refreshed = ensure_streaming(
                    camera_sockets=None,
                    width=args.width,
                    height=args.height,
                    fps=args.fps,
                )
            except Exception as exc:  # pragma: no cover - hardware/runtime dependent
                # Keep running so reconnection can recover streams.
                last_error = exc
                continue
            if refreshed != active_streams:
                active_streams = refreshed
                last_snapshot = _print_stream_state(active_streams)
                continue
            snapshot = tuple(
                (target.stream_name, target.device_name, target.device_id)
                for target in list_stream_targets()
            )
            if snapshot != last_snapshot:
                last_snapshot = _print_stream_state(active_streams)
    except KeyboardInterrupt:
        stop_streaming()


def _write_robot_heartbeat(
    *,
    heartbeat_path: Path,
    alive: bool,
    step_count: int,
    elapsed_s: float,
) -> None:
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "alive": bool(alive),
        "updated_at_s": time.time(),
        "step_count": int(step_count),
        "elapsed_s": float(elapsed_s),
    }
    heartbeat_path.write_text(json.dumps(payload), encoding="utf-8")


def _parse_grpc_host_port(grpc_url: str) -> tuple[str, int]:
    parsed = urlparse(grpc_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 9876
    return host, int(port)


def _wait_for_grpc_listener(
    *,
    grpc_url: str,
    timeout_s: float,
    retry_interval_s: float,
) -> None:
    host, port = _parse_grpc_host_port(grpc_url)
    deadline = time.time() + max(0.1, float(timeout_s))
    last_error: OSError | None = None

    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(max(0.05, float(retry_interval_s)))

    details = f" ({last_error})" if last_error else ""
    raise RuntimeError(
        f"Timed out waiting for Rerun gRPC listener at {host}:{port}{details}"
    )


def run_robot() -> None:
    """Start the robot control loop (demo or custom)."""
    parser = argparse.ArgumentParser(description="Start robot env control loop.")
    parser.add_argument("--hz", type=float, default=20.0)
    parser.add_argument("--tau", type=float, default=0.15)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--no-open-browser", action="store_true")
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=20.0,
        help="How long to wait for external Rerun gRPC listener.",
    )
    parser.add_argument(
        "--retry-interval",
        type=float,
        default=0.5,
        help="Retry interval while waiting for external Rerun gRPC listener.",
    )
    parser.add_argument(
        "--rerun-grpc-url",
        type=str,
        default=os.environ.get("RERUN_GRPC_URL", ""),
        help="Existing Rerun gRPC URL to publish into (empty => start local viewer).",
    )
    parser.add_argument(
        "--rerun-web-url",
        type=str,
        default=os.environ.get("RERUN_WEB_URL", ""),
        help="Rerun web URL used for status/links when using --rerun-grpc-url.",
    )
    parser.add_argument(
        "--heartbeat-path",
        type=str,
        default=os.environ.get("ROBOT_HEARTBEAT_PATH", str(DEFAULT_ROBOT_HEARTBEAT_PATH)),
        help="Path to robot heartbeat JSON used by dev guards.",
    )
    args = parser.parse_args()

    import numpy as np

    from telemetry_console.env import RobotEnv

    heartbeat_path = Path(args.heartbeat_path).expanduser().resolve()
    if args.rerun_grpc_url:
        try:
            _wait_for_grpc_listener(
                grpc_url=args.rerun_grpc_url,
                timeout_s=args.startup_timeout,
                retry_interval_s=args.retry_interval,
            )
        except RuntimeError as exc:
            print(f"[tc-robot] Failed startup: {exc}")
            sys.exit(1)

    env = RobotEnv(
        hz=args.hz,
        tau=args.tau,
        open_browser=not args.no_open_browser,
        rerun_grpc_url=args.rerun_grpc_url or None,
        rerun_web_url=args.rerun_web_url or None,
    )
    env.reset()
    _write_robot_heartbeat(
        heartbeat_path=heartbeat_path,
        alive=True,
        step_count=0,
        elapsed_s=0.0,
    )
    low, high = env.get_action_space()

    print(f"[tc-robot] Running demo at {args.hz} Hz. Ctrl+C to stop.")
    step_count = 0
    try:
        t0 = time.time()
        while True:
            t = time.time() - t0
            action = np.zeros(env.action_dim, dtype=np.float32)
            action[0] = np.pi / 2
            action[3] = -np.pi / 2 + 0.5 * np.sin(t * 0.5)
            action[7] = -np.pi / 2
            action[10] = -np.pi / 2 + 0.5 * np.sin(t * 0.5)
            action = np.clip(action, low, high)
            env.step(action)
            step_count += 1
            _write_robot_heartbeat(
                heartbeat_path=heartbeat_path,
                alive=True,
                step_count=step_count,
                elapsed_s=t,
            )
            if args.duration is not None and t >= args.duration:
                break
            time.sleep(1.0 / env.hz)
    except KeyboardInterrupt:
        pass
    finally:
        _write_robot_heartbeat(
            heartbeat_path=heartbeat_path,
            alive=False,
            step_count=step_count,
            elapsed_s=0.0,
        )
        env.close()


def run_recorder() -> None:
    """Start the recording process (ZMQ-controlled)."""
    parser = argparse.ArgumentParser(description="Start the recorder process.")
    parser.add_argument("--log-dir", type=str, default="data_logs")
    args = parser.parse_args()

    from telemetry_console.recorder import Recorder

    rec = Recorder(base_dir=Path(args.log_dir))
    print("[tc-recorder] Ready. Waiting for start command on ZMQ.")
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
