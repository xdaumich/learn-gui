"""Zarr-based episode logging for camera + synthetic trajectories."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import zarr
from numcodecs import Blosc

DEFAULT_SINE_AMP = 0.1
DEFAULT_SINE_HZ = 0.5


def _default_compressor() -> Blosc:
    return Blosc(cname="zstd", clevel=3, shuffle=Blosc.BITSHUFFLE)


class ZarrEpisodeLogger:
    """Append-only logger for an episode stored as a Zarr group."""

    def __init__(
        self,
        store_path: Path,
        *,
        height: int,
        width: int,
        sine_amp: float = DEFAULT_SINE_AMP,
        sine_hz: float = DEFAULT_SINE_HZ,
        chunk_t: int = 8,
        compressor: Optional[Blosc] = None,
    ) -> None:
        self.store_path = Path(store_path)
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self._height = height
        self._width = width
        self._sine_amp = sine_amp
        self._sine_hz = sine_hz
        self._chunk_t = chunk_t
        self._lock = threading.Lock()
        self._closed = False
        self._t0_ns: int | None = None

        codec = compressor or _default_compressor()
        self._group = zarr.open_group(self.store_path, mode="a")
        self._rgb = self._group.require_dataset(
            "rgb",
            shape=(0, height, width, 3),
            chunks=(chunk_t, height, width, 3),
            dtype="u1",
            compressor=codec,
        )
        self._t_ns = self._group.require_dataset(
            "t_ns",
            shape=(0,),
            chunks=(chunk_t,),
            dtype="i8",
            compressor=codec,
        )
        self._ee_pose = self._group.require_dataset(
            "ee_pose",
            shape=(0, 7),
            chunks=(chunk_t, 7),
            dtype="f4",
            compressor=codec,
        )

        self._group.attrs.setdefault("height", height)
        self._group.attrs.setdefault("width", width)
        self._group.attrs.setdefault("sine_amp", float(sine_amp))
        self._group.attrs.setdefault("sine_hz", float(sine_hz))

    def set_metadata(self, *, run_id: str, camera_name: str) -> None:
        self._group.attrs.setdefault("run_id", run_id)
        self._group.attrs.setdefault("camera_name", camera_name)

    @property
    def samples(self) -> int:
        return int(self._t_ns.shape[0])

    def append(self, rgb_frame: np.ndarray, t_ns: int) -> None:
        if self._closed:
            return

        if rgb_frame.shape != (self._height, self._width, 3):
            raise ValueError(
                f"Expected frame shape {(self._height, self._width, 3)}, got {rgb_frame.shape}"
            )

        with self._lock:
            if self._t0_ns is None:
                self._t0_ns = int(t_ns)
                self._group.attrs.setdefault("t0_ns", self._t0_ns)

            index = self.samples
            self._rgb.resize((index + 1, self._height, self._width, 3))
            self._t_ns.resize((index + 1,))
            self._ee_pose.resize((index + 1, 7))

            self._rgb[index] = rgb_frame
            self._t_ns[index] = int(t_ns)
            self._ee_pose[index] = self._sine_pose(int(t_ns))

    def _sine_pose(self, t_ns: int) -> np.ndarray:
        t0 = self._t0_ns if self._t0_ns is not None else t_ns
        t_sec = (t_ns - t0) * 1e-9
        x = self._sine_amp * math.sin(2.0 * math.pi * self._sine_hz * t_sec)
        return np.array([x, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0], dtype=np.float32)

    def close(self) -> None:
        self._closed = True


@dataclass
class RecordingState:
    active: bool
    run_id: str | None
    samples: int
    state: str


class RecordingManager:
    def __init__(
        self,
        base_dir: Path,
        *,
        sine_amp: float = DEFAULT_SINE_AMP,
        sine_hz: float = DEFAULT_SINE_HZ,
        chunk_t: int = 8,
    ) -> None:
        self.base_dir = Path(base_dir)
        self._sine_amp = sine_amp
        self._sine_hz = sine_hz
        self._chunk_t = chunk_t
        self._lock = threading.Lock()
        self._active = False
        self._run_id: str | None = None
        self._loggers: dict[str, ZarrEpisodeLogger] = {}
        self._last_samples = 0

    @property
    def run_id(self) -> str | None:
        return self._run_id

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def status(self) -> RecordingState:
        return RecordingState(
            active=self._active,
            run_id=self._run_id,
            samples=self._samples_written(),
            state="recording" if self._active else "idle",
        )

    def start(self) -> RecordingState:
        with self._lock:
            if self._active:
                return RecordingState(
                    active=True,
                    run_id=self._run_id,
                    samples=self._samples_written(),
                    state="already_active",
                )

            self.base_dir.mkdir(parents=True, exist_ok=True)
            timestamp = int(time.time() * 1000)
            self._run_id = time.strftime("%Y%m%d_%H%M%S") + f"_{timestamp % 1000:03d}"
            self._active = True
            self._loggers = {}
            self._last_samples = 0
            return RecordingState(
                active=True,
                run_id=self._run_id,
                samples=0,
                state="started",
            )

    def stop(self) -> RecordingState:
        with self._lock:
            if not self._active:
                return RecordingState(
                    active=False,
                    run_id=self._run_id,
                    samples=self._samples_written(),
                    state="already_stopped",
                )

            self._last_samples = self._samples_written()
            for logger in self._loggers.values():
                logger.close()
            self._loggers = {}
            self._active = False
            return RecordingState(
                active=False,
                run_id=self._run_id,
                samples=self._last_samples,
                state="stopped",
            )

    def get_logger(self, camera_name: str, *, height: int, width: int) -> ZarrEpisodeLogger | None:
        with self._lock:
            if not self._active or self._run_id is None:
                return None
            logger = self._loggers.get(camera_name)
            if logger is None:
                store_path = self.base_dir / self._run_id / f"{camera_name}.zarr"
                logger = ZarrEpisodeLogger(
                    store_path,
                    height=height,
                    width=width,
                    sine_amp=self._sine_amp,
                    sine_hz=self._sine_hz,
                    chunk_t=self._chunk_t,
                )
                logger.set_metadata(run_id=self._run_id, camera_name=camera_name)
                self._loggers[camera_name] = logger
            return logger

    def _samples_written(self) -> int:
        if self._active:
            return sum(logger.samples for logger in self._loggers.values())
        return self._last_samples
