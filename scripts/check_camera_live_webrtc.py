#!/usr/bin/env python3
"""Smoke-check camera live readiness through the MJPEG path.

This script is intended for `make dev` startup guards. It verifies:
1) API health is reachable.
2) Cameras are discoverable through `/cameras`.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value else default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout_s: float = 5.0,
) -> Any:
    data: bytes | None = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, method=method, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def _wait_for_health(health_url: str, *, timeout_s: float, poll_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            payload = _request_json(health_url, timeout_s=5.0)
            if payload.get("status") == "ok":
                print("[camera-guard] API health check passed.", flush=True)
                return
        except Exception as exc:  # pragma: no cover - guarded by integration runtime
            last_error = exc
        time.sleep(poll_s)

    details = f"last_error={last_error}" if last_error else "no response payload"
    raise RuntimeError(f"API health check timed out after {timeout_s:.1f}s ({details}).")


def _load_camera_names(cameras_url: str) -> list[str]:
    payload = _request_json(cameras_url, timeout_s=5.0)
    if not isinstance(payload, list):
        raise RuntimeError("`/cameras` did not return a JSON array.")

    names = [str(item) for item in payload if isinstance(item, str)]
    if not names:
        raise RuntimeError("No cameras detected by `/cameras`.")
    return names


def _wait_for_camera_names(
    cameras_url: str,
    *,
    timeout_s: float,
    poll_s: float,
    min_cameras: int = 0,
) -> list[str]:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    best: list[str] = []

    while time.monotonic() < deadline:
        try:
            names = _load_camera_names(cameras_url)
            if len(names) > len(best):
                best = names
                print(
                    f"[camera-guard] Discovered {len(best)} camera(s) so far: "
                    f"{', '.join(best)}.",
                    flush=True,
                )
            if min_cameras <= 0 or len(best) >= min_cameras:
                return best
        except Exception as exc:
            last_error = exc
        time.sleep(poll_s)

    if best:
        return best

    details = f"last_error={last_error}" if last_error else "no camera payload"
    raise RuntimeError(
        f"Camera discovery timed out after {timeout_s:.1f}s (`/cameras`, {details})."
    )


def _wait_for_robot_live(
    robot_status_url: str,
    *,
    timeout_s: float,
    poll_s: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_payload: dict[str, Any] | None = None
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            payload = _request_json(robot_status_url, timeout_s=5.0)
            if isinstance(payload, dict):
                last_payload = payload
                if payload.get("alive") is True:
                    return payload
        except Exception as exc:  # pragma: no cover - guarded by integration runtime
            last_error = exc
        time.sleep(poll_s)

    details = f"last_payload={last_payload}"
    if last_error is not None:
        details += f", last_error={last_error}"
    raise RuntimeError(
        "Robot liveness check timed out "
        f"after {timeout_s:.1f}s ({details})."
    )


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def main() -> int:
    base_url = _normalize_base_url(_env_str("CAMERA_GUARD_API_BASE_URL", "http://127.0.0.1:8000"))
    timeout_s = _env_float("CAMERA_GUARD_TIMEOUT_S", 45.0)
    poll_s = _env_float("CAMERA_GUARD_POLL_S", 0.5)
    require_robot = _env_bool("CAMERA_GUARD_REQUIRE_ROBOT", True)
    min_cameras = _env_int("CAMERA_GUARD_MIN_CAMERAS", 3)

    health_url = f"{base_url}/health"
    cameras_url = f"{base_url}/cameras"
    robot_status_url = f"{base_url}/robot/status"

    try:
        _wait_for_health(health_url, timeout_s=timeout_s, poll_s=poll_s)
        camera_names = _wait_for_camera_names(
            cameras_url,
            timeout_s=timeout_s,
            poll_s=poll_s,
            min_cameras=min_cameras,
        )
        print(
            f"[camera-guard] PASS: "
            f"{len(camera_names)} camera(s) online ({', '.join(camera_names)}).",
            flush=True,
        )
        if min_cameras > 0 and len(camera_names) < min_cameras:
            print(
                f"[camera-guard] ERROR: "
                f"only {len(camera_names)} camera(s) detected after full timeout, "
                f"minimum required is {min_cameras}.",
                file=sys.stderr,
            )
            return 1
        if require_robot:
            robot_status = _wait_for_robot_live(
                robot_status_url,
                timeout_s=timeout_s,
                poll_s=poll_s,
            )
            age_s = robot_status.get("age_s")
            age_text = f"{float(age_s):.2f}s" if isinstance(age_s, (int, float)) else "unknown"
            print(
                "[camera-guard] PASS: "
                f"robot trajectory heartbeat is live (age={age_text}).",
                flush=True,
            )
        else:
            print("[camera-guard] Robot liveness check skipped by env.", flush=True)
        return 0
    except urllib.error.URLError as exc:
        print(f"[camera-guard] ERROR: API request failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[camera-guard] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
