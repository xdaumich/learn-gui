"""Save MJPEG snapshots or video clips from a remote mjpeg_debug server.

Requires: pip install opencv-python

Usage:
    # Set Thor IP once (or pass --host each time)
    export THOR_IP=10.112.210.46

    # Snapshot all cameras
    python scripts/save_mjpeg.py --host $THOR_IP snapshot

    # Snapshot one camera
    python scripts/save_mjpeg.py --host $THOR_IP snapshot --camera center

    # Record 10s video from all cameras
    python scripts/save_mjpeg.py --host $THOR_IP record --duration 10

    # Record center only, custom output dir
    python scripts/save_mjpeg.py --host $THOR_IP record --camera center --out ./captures
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib import request as urllib_request

import cv2


def _get_cameras(base_url: str) -> list[str]:
    with urllib_request.urlopen(f"{base_url}/cameras", timeout=5) as resp:
        return json.loads(resp.read().decode())


def snapshot(base_url: str, cameras: list[str], out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    for name in cameras:
        url = f"{base_url}/stream/{name}"
        cap = cv2.VideoCapture(url)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            print(f"  FAIL: {name} — no frame received")
            continue

        path = out_dir / f"{name}_{ts}.jpg"
        cv2.imwrite(str(path), frame)
        print(f"  OK: {path}")


def record(base_url: str, cameras: list[str], out_dir: Path, duration: float, fps: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    caps = {}
    writers = {}
    for name in cameras:
        url = f"{base_url}/stream/{name}"
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            print(f"  FAIL: {name} — cannot open stream")
            continue

        ret, frame = cap.read()
        if not ret:
            print(f"  FAIL: {name} — no initial frame")
            cap.release()
            continue

        h, w = frame.shape[:2]
        path = out_dir / f"{name}_{ts}.mp4"
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        writer.write(frame)
        caps[name] = cap
        writers[name] = (writer, path)

    if not caps:
        print("No cameras available")
        return

    print(f"Recording {len(caps)} camera(s) for {duration}s...")
    end = time.time() + duration
    frames = {name: 1 for name in caps}

    while time.time() < end:
        for name, cap in caps.items():
            ret, frame = cap.read()
            if ret:
                writers[name][0].write(frame)
                frames[name] += 1

    for name in caps:
        caps[name].release()
        writers[name][0].release()
        print(f"  OK: {writers[name][1]} ({frames[name]} frames)")


def main():
    parser = argparse.ArgumentParser(description="Save MJPEG snapshots or video clips")
    parser.add_argument("--host", default=os.environ.get("THOR_IP", "127.0.0.1"),
                        help="MJPEG server host (default: $THOR_IP or 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8001, help="MJPEG server port (default: 8001)")
    parser.add_argument("--out", type=Path, default=Path("captures"), help="Output directory (default: ./captures)")
    parser.add_argument("--camera", help="Single camera name (default: all)")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot", help="Save a single JPEG from each camera")
    rec = sub.add_parser("record", help="Record video clips")
    rec.add_argument("--duration", type=float, default=10, help="Recording duration in seconds (default: 10)")
    rec.add_argument("--fps", type=int, default=30, help="Video FPS (default: 30)")

    args = parser.parse_args()
    base_url = f"http://{args.host}:{args.port}"

    try:
        all_cameras = _get_cameras(base_url)
    except Exception as e:
        print(f"Cannot reach MJPEG server at {base_url}: {e}", file=sys.stderr)
        sys.exit(1)

    cameras = [args.camera] if args.camera else all_cameras
    print(f"Server: {base_url}  Cameras: {cameras}")

    if args.command == "snapshot":
        snapshot(base_url, cameras, args.out)
    elif args.command == "record":
        record(base_url, cameras, args.out, args.duration, args.fps)


if __name__ == "__main__":
    main()
