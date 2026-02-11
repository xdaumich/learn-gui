"""Tests for telemetry_console.env ZMQ state publishing."""

import time
import threading

import numpy as np
import zmq

from telemetry_console.zmq_channels import ROBOT_STATE_PORT, unpack_state


def test_env_publishes_state_on_step(monkeypatch):
    """RobotEnv.step() should publish cmd+state via ZMQ PUB."""
    # Patch out Rerun calls so we don't need a running server
    import telemetry_console.viewer as viewer
    monkeypatch.setattr(viewer, "_running", True)
    monkeypatch.setattr(viewer, "_web_url", "http://fake:9090")

    import rerun as rr
    monkeypatch.setattr(rr, "set_time", lambda *a, **kw: None)
    monkeypatch.setattr(rr, "log", lambda *a, **kw: None)
    monkeypatch.setattr(viewer, "load_vega_1p_model", lambda: None)
    monkeypatch.setattr(viewer, "send_robot_blueprint", lambda **kw: None)
    monkeypatch.setattr(viewer, "log_arm_transforms", lambda *a, **kw: None)
    monkeypatch.setattr(viewer, "get_joint_limits", lambda: {
        name: (-3.14, 3.14) for name in viewer.ARM_JOINT_NAMES
    })

    from telemetry_console.env import RobotEnv

    # Use a non-default port to avoid conflicts with other tests
    test_port = 15555

    # Create the env first so the PUB socket binds
    env = RobotEnv(hz=20, tau=0.1, zmq_pub_port=test_port)

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVTIMEO, 2000)
    sub.connect(f"tcp://127.0.0.1:{test_port}")
    time.sleep(0.3)  # let SUB fully connect to PUB

    env.reset()
    action = np.zeros(env.action_dim, dtype=np.float32)
    env.step(action)

    # Should receive at least one state message
    topic = sub.recv()
    raw = sub.recv()
    data = unpack_state(raw)
    assert "cmd" in data
    assert "state" in data
    assert "t_ns" in data
    assert len(data["cmd"]) == env.action_dim

    env.close()
    sub.close()
    ctx.term()
