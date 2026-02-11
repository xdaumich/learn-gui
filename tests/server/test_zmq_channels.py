"""Tests for ZMQ channel constants and serialization."""

import numpy as np


def test_ports_are_distinct():
    from telemetry_console.zmq_channels import (
        RECORDER_CONTROL_PORT,
        RECORDER_STATUS_PORT,
        ROBOT_STATE_PORT,
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
