# server/telemetry_console/recorder.py
"""Independent recording process: RTSP + ZMQ -> Zarr."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Sequence

import numpy as np
import zmq

from telemetry_console.zmq_channels import (
    RECORDER_CONTROL_PORT,
    RECORDER_STATUS_PORT,
    ROBOT_STATE_PORT,
    TOPIC_ROBOT_STATE,
    pack_status,
    unpack_control,
    unpack_state,
)

# Re-use existing Zarr classes (they have no runner dependencies)
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data_log import RecordingManager  # noqa: E402


class Recorder:
    """Recording process controlled via ZMQ."""

    def __init__(
        self,
        base_dir: Path,
        *,
        zmq_control_port: int = RECORDER_CONTROL_PORT,
        zmq_status_port: int = RECORDER_STATUS_PORT,
        zmq_state_port: int = ROBOT_STATE_PORT,
        rtsp_urls: Sequence[str] = (),
    ) -> None:
        self._base_dir = Path(base_dir)
        self._control_port = zmq_control_port
        self._status_port = zmq_status_port
        self._state_port = zmq_state_port
        self._rtsp_urls = list(rtsp_urls)
        self._stop_event = threading.Event()
        self._manager = RecordingManager(self._base_dir)

    def run(self) -> None:
        """Main loop: poll ZMQ control, optionally ingest RTSP + state."""
        ctx = zmq.Context()

        control = ctx.socket(zmq.REP)
        control.bind(f"tcp://*:{self._control_port}")

        status_pub = ctx.socket(zmq.PUB)
        status_pub.bind(f"tcp://*:{self._status_port}")

        poller = zmq.Poller()
        poller.register(control, zmq.POLLIN)

        # Optional: subscribe to robot state
        state_sub = None
        if self._state_port > 0:
            state_sub = ctx.socket(zmq.SUB)
            state_sub.setsockopt(zmq.SUBSCRIBE, TOPIC_ROBOT_STATE)
            state_sub.connect(f"tcp://127.0.0.1:{self._state_port}")
            poller.register(state_sub, zmq.POLLIN)

        while not self._stop_event.is_set():
            events = dict(poller.poll(timeout=100))

            if control in events:
                raw = control.recv()
                msg = unpack_control(raw)
                reply = self._handle_command(msg)
                control.send(reply)
                status_pub.send(reply)

            if state_sub is not None and state_sub in events:
                state_sub.recv()  # topic frame
                raw = state_sub.recv()
                _ = unpack_state(raw)

        control.close()
        status_pub.close()
        if state_sub is not None:
            state_sub.close()
        ctx.term()

    def _handle_command(self, msg: dict) -> bytes:
        command = msg.get("command", "status")
        if command == "start":
            state = self._manager.start()
        elif command == "stop":
            state = self._manager.stop()
        else:
            state = self._manager.status()
        return pack_status(
            active=state.active,
            run_id=state.run_id,
            samples=state.samples,
        )

    def stop(self) -> None:
        self._stop_event.set()
