# tests/server/test_recorder_zmq.py
"""Tests for telemetry_console.recorder ZMQ control interface."""

import threading
import time

import zmq

from telemetry_console.zmq_channels import (
    RECORDER_CONTROL_PORT,
    RECORDER_STATUS_PORT,
    pack_control,
    unpack_status,
)


def test_recorder_responds_to_status_query(tmp_path):
    from telemetry_console.recorder import Recorder

    rec = Recorder(
        base_dir=tmp_path / "logs",
        zmq_control_port=RECORDER_CONTROL_PORT + 20,
        zmq_status_port=RECORDER_STATUS_PORT + 20,
        rtsp_urls=[],
        zmq_state_port=0,
    )

    t = threading.Thread(target=rec.run, daemon=True)
    t.start()
    time.sleep(0.3)

    ctx = zmq.Context()
    req = ctx.socket(zmq.REQ)
    req.setsockopt(zmq.RCVTIMEO, 2000)
    req.connect(f"tcp://127.0.0.1:{RECORDER_CONTROL_PORT + 20}")

    req.send(pack_control(command="status"))
    reply = unpack_status(req.recv())
    assert reply["active"] is False
    assert reply["samples"] == 0

    rec.stop()
    req.close()
    ctx.term()


def test_recorder_start_stop_cycle(tmp_path):
    from telemetry_console.recorder import Recorder

    rec = Recorder(
        base_dir=tmp_path / "logs",
        zmq_control_port=RECORDER_CONTROL_PORT + 30,
        zmq_status_port=RECORDER_STATUS_PORT + 30,
        rtsp_urls=[],
        zmq_state_port=0,
    )

    t = threading.Thread(target=rec.run, daemon=True)
    t.start()
    time.sleep(0.3)

    ctx = zmq.Context()
    req = ctx.socket(zmq.REQ)
    req.setsockopt(zmq.RCVTIMEO, 2000)
    req.connect(f"tcp://127.0.0.1:{RECORDER_CONTROL_PORT + 30}")

    req.send(pack_control(command="start"))
    reply = unpack_status(req.recv())
    assert reply["active"] is True
    assert reply["run_id"] is not None

    req.send(pack_control(command="stop"))
    reply = unpack_status(req.recv())
    assert reply["active"] is False

    rec.stop()
    req.close()
    ctx.term()
