#!/usr/bin/env python3
"""Smoke-check camera live readiness through the WebRTC signaling path.

This script is intended for `make dev` startup guards. It verifies:
1) API health is reachable.
2) Cameras are discoverable through `/webrtc/cameras`.
3) A WebRTC session receives at least one frame per expected camera track.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamTrack


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value else default


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
                print("[camera-guard:webrtc] API health check passed.", flush=True)
                return
        except Exception as exc:  # pragma: no cover - guarded by integration runtime
            last_error = exc
        time.sleep(poll_s)

    details = f"last_error={last_error}" if last_error else "no response payload"
    raise RuntimeError(f"API health check timed out after {timeout_s:.1f}s ({details}).")


def _load_camera_names(cameras_url: str) -> list[str]:
    payload = _request_json(cameras_url, timeout_s=5.0)
    if not isinstance(payload, list):
        raise RuntimeError("`/webrtc/cameras` did not return a JSON array.")

    names = [str(item) for item in payload if isinstance(item, str)]
    if not names:
        raise RuntimeError("No cameras detected by `/webrtc/cameras`.")
    return names


async def _wait_for_first_frame(
    track: MediaStreamTrack,
    *,
    label: str,
    frame_labels: list[str],
    errors: list[str],
) -> None:
    try:
        await track.recv()
        frame_labels.append(label)
    except Exception as exc:  # pragma: no cover - guarded by integration runtime
        errors.append(f"{label}: {exc}")


async def _verify_webrtc_frames(
    offer_url: str,
    camera_names: list[str],
    *,
    timeout_s: float,
    http_timeout_s: float,
) -> tuple[int, list[str], list[str]]:
    expected_count = len(camera_names)
    pc = RTCPeerConnection()

    received_labels: list[str] = []
    errors: list[str] = []
    consume_tasks: list[asyncio.Task[None]] = []
    tracks_seen: list[str] = []

    @pc.on("track")
    def on_track(track: MediaStreamTrack) -> None:
        label = f"{track.kind}-{len(tracks_seen) + 1}"
        tracks_seen.append(label)
        consume_tasks.append(
            asyncio.create_task(
                _wait_for_first_frame(
                    track,
                    label=label,
                    frame_labels=received_labels,
                    errors=errors,
                )
            )
        )

    for _ in camera_names:
        pc.addTransceiver("video", direction="recvonly")

    try:
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        answer_payload = _request_json(
            offer_url,
            method="POST",
            payload={"sdp": offer.sdp, "type": offer.type},
            timeout_s=http_timeout_s,
        )
        answer = RTCSessionDescription(sdp=answer_payload["sdp"], type=answer_payload["type"])
        await pc.setRemoteDescription(answer)

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if len(received_labels) >= expected_count:
                break
            await asyncio.sleep(0.1)
    finally:
        for task in consume_tasks:
            if not task.done():
                task.cancel()
        if consume_tasks:
            await asyncio.gather(*consume_tasks, return_exceptions=True)
        await pc.close()

    return len(tracks_seen), received_labels, errors


def main() -> int:
    base_url = _normalize_base_url(_env_str("CAMERA_GUARD_API_BASE_URL", "http://127.0.0.1:8000"))
    timeout_s = _env_float("CAMERA_GUARD_TIMEOUT_S", 20.0)
    poll_s = _env_float("CAMERA_GUARD_POLL_S", 0.5)
    frame_timeout_s = _env_float("CAMERA_GUARD_FRAME_TIMEOUT_S", timeout_s)
    http_timeout_s = _env_float("CAMERA_GUARD_HTTP_TIMEOUT_S", max(10.0, timeout_s))

    health_url = f"{base_url}/health"
    cameras_url = f"{base_url}/webrtc/cameras"
    offer_url = f"{base_url}/webrtc/offer"

    try:
        _wait_for_health(health_url, timeout_s=timeout_s, poll_s=poll_s)
        camera_names = _load_camera_names(cameras_url)
        print(
            f"[camera-guard:webrtc] Expected cameras: {len(camera_names)} "
            f"({', '.join(camera_names)}).",
            flush=True,
        )
        tracks_seen, received_labels, errors = asyncio.run(
            _verify_webrtc_frames(
                offer_url,
                camera_names,
                timeout_s=frame_timeout_s,
                http_timeout_s=http_timeout_s,
            )
        )
        expected_count = len(camera_names)
        received_count = len(received_labels)
        if received_count < expected_count:
            missing = expected_count - received_count
            error_details = f"; track_errors={errors}" if errors else ""
            print(
                "[camera-guard:webrtc] ERROR: "
                f"only {received_count}/{expected_count} camera streams delivered first frames "
                f"(tracks_seen={tracks_seen}, missing={missing}){error_details}",
                file=sys.stderr,
            )
            return 1

        print(
            "[camera-guard:webrtc] PASS: "
            f"received first frames for {received_count}/{expected_count} streams.",
            flush=True,
        )
        return 0
    except urllib.error.URLError as exc:
        print(f"[camera-guard:webrtc] ERROR: API request failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[camera-guard:webrtc] ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
