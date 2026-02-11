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
