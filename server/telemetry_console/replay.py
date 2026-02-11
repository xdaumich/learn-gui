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
