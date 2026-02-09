from __future__ import annotations

import numpy as np
import zarr

from data_log import ZarrEpisodeLogger


def test_zarr_episode_logger_aligns_samples(tmp_path) -> None:
    store_path = tmp_path / "run_001" / "cam_a.zarr"
    logger = ZarrEpisodeLogger(
        store_path,
        height=2,
        width=3,
        sine_amp=0.5,
        sine_hz=1.0,
        chunk_t=2,
    )

    frame0 = np.zeros((2, 3, 3), dtype=np.uint8)
    frame1 = np.full((2, 3, 3), 255, dtype=np.uint8)

    t0 = 1_000_000_000
    t1 = t0 + 250_000_000

    logger.append(frame0, t0)
    logger.append(frame1, t1)
    logger.close()

    root = zarr.open_group(store_path, mode="r")
    assert root["rgb"].shape == (2, 2, 3, 3)
    assert root["t_ns"].shape == (2,)
    assert root["ee_pose"].shape == (2, 7)

    t_ns = root["t_ns"][:]
    np.testing.assert_array_equal(t_ns, np.array([t0, t1], dtype=np.int64))

    rgb = root["rgb"][:]
    assert rgb.dtype == np.uint8
    np.testing.assert_array_equal(rgb[0], frame0)
    np.testing.assert_array_equal(rgb[1], frame1)

    ee_pose = root["ee_pose"][:]
    expected_x = np.array([0.0, 0.5], dtype=np.float32)
    np.testing.assert_allclose(ee_pose[:, 0], expected_x, atol=1e-5)
    np.testing.assert_allclose(ee_pose[:, 1:3], 0.0, atol=1e-6)
    np.testing.assert_allclose(ee_pose[:, 3:6], 0.0, atol=1e-6)
    np.testing.assert_allclose(ee_pose[:, 6], 1.0, atol=1e-6)
