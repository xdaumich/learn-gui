"""Save WebRTC snapshots or video clips from the tc-gui WHEP endpoint.

Requires: aiortc, av, opencv-python (all in server venv)

Usage:
    export THOR_IP=192.168.5.20

    uv run --project server python scripts/save_webrtc.py --host $THOR_IP snapshot
    uv run --project server python scripts/save_webrtc.py --host $THOR_IP snapshot --camera center
    uv run --project server python scripts/save_webrtc.py --host $THOR_IP record --duration 10
    uv run --project server python scripts/save_webrtc.py --host $THOR_IP record --camera left --out ./captures
"""

from __future__ import annotations

import argparse
import asyncio
import fractions
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib import request as urllib_request

import av
import cv2
from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)


def _get_cameras(api_url: str) -> list[str]:
    with urllib_request.urlopen(f"{api_url}/webrtc/cameras", timeout=5) as resp:
        return json.loads(resp.read().decode())


def _whep_offer(api_url: str, camera: str, sdp: str) -> str:
    """POST SDP offer to the WHEP endpoint and return the SDP answer."""
    data = sdp.encode()
    req = urllib_request.Request(
        f"{api_url}/webrtc/{camera}/whep",
        data=data,
        headers={"Content-Type": "application/sdp"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=10) as resp:
        return resp.read().decode()


def _ice_config() -> RTCConfiguration:
    return RTCConfiguration(
        iceServers=[RTCIceServer(urls="stun:stun.l.google.com:19302")]
    )


async def _connect(api_url: str, camera: str) -> tuple[RTCPeerConnection, asyncio.Event, list]:
    """Create a WHEP connection and return (pc, ready_event, frames_list)."""
    pc = RTCPeerConnection(configuration=_ice_config())
    pc.addTransceiver("video", direction="recvonly")

    frames: list[av.VideoFrame] = []
    ready = asyncio.Event()

    @pc.on("track")
    def on_track(track):
        async def _recv():
            while True:
                try:
                    frame = await asyncio.wait_for(track.recv(), timeout=5)
                except (asyncio.TimeoutError, Exception):
                    break
                frames.append(frame)
                if not ready.is_set():
                    ready.set()
        asyncio.ensure_future(_recv())

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    # Wait for ICE gathering to complete before sending the offer
    for _ in range(100):
        if pc.iceGatheringState == "complete":
            break
        await asyncio.sleep(0.1)

    answer_sdp = _whep_offer(api_url, camera, pc.localDescription.sdp)
    await pc.setRemoteDescription(
        RTCSessionDescription(sdp=answer_sdp, type="answer")
    )

    return pc, ready, frames


async def snapshot(api_url: str, cameras: list[str], out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    for name in cameras:
        print(f"  Connecting to {name}...")
        pc, ready, frames = await _connect(api_url, name)

        try:
            await asyncio.wait_for(ready.wait(), timeout=10)
        except asyncio.TimeoutError:
            print(f"  FAIL: {name} — no frame received within 10s")
            await pc.close()
            continue

        # Give a moment for a clean frame
        await asyncio.sleep(0.5)

        frame = frames[-1]
        img = frame.to_ndarray(format="bgr24")
        path = out_dir / f"{name}_{ts}.jpg"
        cv2.imwrite(str(path), img)
        print(f"  OK: {path} ({frame.width}x{frame.height})")
        await pc.close()


async def record(api_url: str, cameras: list[str], out_dir: Path, duration: float, fps: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    connections = {}
    for name in cameras:
        print(f"  Connecting to {name}...")
        pc, ready, frames = await _connect(api_url, name)
        connections[name] = (pc, ready, frames)

    # Wait for all cameras to produce at least one frame
    for name, (pc, ready, frames) in list(connections.items()):
        try:
            await asyncio.wait_for(ready.wait(), timeout=10)
        except asyncio.TimeoutError:
            print(f"  FAIL: {name} — no frame received within 10s")
            await pc.close()
            del connections[name]

    if not connections:
        print("No cameras available")
        return

    print(f"Recording {len(connections)} camera(s) for {duration}s...")
    # Clear accumulated frames and record for the specified duration
    frame_counts = {}
    for name, (pc, ready, frames) in connections.items():
        frames.clear()
        frame_counts[name] = 0

    await asyncio.sleep(duration)

    # Write MP4 files using PyAV
    for name, (pc, ready, frames) in connections.items():
        if not frames:
            print(f"  FAIL: {name} — no frames captured")
            await pc.close()
            continue

        path = out_dir / f"{name}_{ts}.mp4"
        first = frames[0]

        output = av.open(str(path), "w")
        stream = output.add_stream("libx264", rate=fps)
        stream.width = first.width
        stream.height = first.height
        stream.pix_fmt = "yuv420p"
        stream.time_base = fractions.Fraction(1, fps)
        stream.options = {"preset": "fast", "crf": "23"}

        for i, frame in enumerate(frames):
            # Reformat to yuv420p for the encoder
            out_frame = frame.reformat(format="yuv420p")
            out_frame.pts = i
            out_frame.time_base = fractions.Fraction(1, fps)
            for packet in stream.encode(out_frame):
                output.mux(packet)

        # Flush encoder
        for packet in stream.encode():
            output.mux(packet)

        output.close()
        await pc.close()
        print(f"  OK: {path} ({len(frames)} frames, {first.width}x{first.height})")


def main():
    parser = argparse.ArgumentParser(description="Save WebRTC snapshots or video clips")
    parser.add_argument("--host", default=os.environ.get("THOR_IP", "127.0.0.1"),
                        help="tc-gui server host (default: $THOR_IP or 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="tc-gui server port (default: 8000)")
    parser.add_argument("--out", type=Path, default=Path("captures"), help="Output directory (default: ./captures)")
    parser.add_argument("--camera", help="Single camera name (default: all)")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot", help="Save a single JPEG from each camera")
    rec = sub.add_parser("record", help="Record video clips")
    rec.add_argument("--duration", type=float, default=10, help="Recording duration in seconds (default: 10)")
    rec.add_argument("--fps", type=int, default=30, help="Video FPS (default: 30)")

    args = parser.parse_args()
    api_url = f"http://{args.host}:{args.port}"

    try:
        all_cameras = _get_cameras(api_url)
    except Exception as e:
        print(f"Cannot reach tc-gui at {api_url}: {e}", file=sys.stderr)
        sys.exit(1)

    cameras = [args.camera] if args.camera else all_cameras
    print(f"Server: {api_url}  Cameras: {cameras}")

    if args.command == "snapshot":
        asyncio.run(snapshot(api_url, cameras, args.out))
    elif args.command == "record":
        asyncio.run(record(api_url, cameras, args.out, args.duration, args.fps))


if __name__ == "__main__":
    main()
