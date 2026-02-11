"""Gym-like robot-arm environment with Rerun-backed visualization and ZMQ publishing."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import rerun as rr
import zmq

from telemetry_console import viewer
from telemetry_console.zmq_channels import (
    ROBOT_STATE_PORT,
    TOPIC_ROBOT_STATE,
    pack_state,
)


class RobotEnv:
    """A simple joint-space control environment for the vega_1p arms."""

    JOINT_NAMES = tuple(viewer.ARM_JOINT_NAMES)

    def __init__(
        self,
        hz: float = 20.0,
        tau: float = 0.1,
        *,
        open_browser: bool = False,
        viewer_window_seconds: float = 5.0,
        zmq_pub_port: int = ROBOT_STATE_PORT,
        rerun_grpc_url: str | None = None,
        rerun_web_url: str | None = None,
    ) -> None:
        if hz <= 0:
            raise ValueError("hz must be > 0")
        if tau <= 0:
            raise ValueError("tau must be > 0")
        if viewer_window_seconds <= 0:
            raise ValueError("viewer_window_seconds must be > 0")

        self.hz = float(hz)
        self.dt = 1.0 / self.hz
        self.tau = float(tau)
        self._open_browser = bool(open_browser)
        self._viewer_window_seconds = float(viewer_window_seconds)
        self._rerun_grpc_url = rerun_grpc_url
        self._rerun_web_url = rerun_web_url

        self._joint_names = list(self.JOINT_NAMES)
        self._limits = viewer.get_joint_limits()
        self._low = np.array([self._limits[name][0] for name in self._joint_names], dtype=np.float32)
        self._high = np.array([self._limits[name][1] for name in self._joint_names], dtype=np.float32)

        self._cmd = np.zeros(self.action_dim, dtype=np.float32)
        self._state = np.zeros(self.action_dim, dtype=np.float32)
        self._state_vel = np.zeros(self.action_dim, dtype=np.float32)
        self._last_step_t: float | None = None
        self._viewer_url: str | None = None
        self._closed = False

        # ZMQ PUB socket for broadcasting state to recorder
        self._zmq_ctx = zmq.Context()
        self._zmq_pub = self._zmq_ctx.socket(zmq.PUB)
        self._zmq_pub.bind(f"tcp://127.0.0.1:{zmq_pub_port}")

    @property
    def action_dim(self) -> int:
        return len(self._joint_names)

    @property
    def viewer_url(self) -> str | None:
        return self._viewer_url

    def _ensure_running(self) -> None:
        if self._rerun_grpc_url:
            viewer.connect_grpc(
                url=self._rerun_grpc_url,
                external_web_url=self._rerun_web_url,
            )
            self._viewer_url = self._rerun_web_url or viewer.web_url()
        elif not viewer.is_running():
            self._viewer_url = viewer.start(open_browser=self._open_browser)
        elif self._viewer_url is None:
            self._viewer_url = viewer.web_url()
        viewer.load_vega_1p_model()
        viewer.send_robot_blueprint(window_seconds=self._viewer_window_seconds)

    def _log_state(self, timestamp: float) -> None:
        rr.set_time("wall_time", timestamp=timestamp)
        joint_positions: dict[str, float] = {}
        for idx, joint_name in enumerate(self._joint_names):
            cmd_value = float(self._cmd[idx])
            state_value = float(self._state[idx])
            rr.log(f"trajectory/cmd/{joint_name}", rr.Scalars(cmd_value))
            rr.log(f"trajectory/state/{joint_name}", rr.Scalars(state_value))
            joint_positions[joint_name] = state_value
        viewer.log_arm_transforms(joint_positions)

        # Publish to ZMQ for recorder
        t_ns = int(timestamp * 1e9)
        self._zmq_pub.send(TOPIC_ROBOT_STATE, zmq.SNDMORE)
        self._zmq_pub.send(pack_state(
            joint_names=self._joint_names,
            cmd=self._cmd,
            state=self._state,
            t_ns=t_ns,
        ))

    def reset(self) -> np.ndarray:
        """Zero all joints, return observation, and initialize visualization."""
        if self._closed:
            raise RuntimeError("RobotEnv is closed")

        self._ensure_running()
        self._cmd.fill(0.0)
        self._state.fill(0.0)
        self._state_vel.fill(0.0)
        self._last_step_t = time.time()
        self._log_state(self._last_step_t)
        return self.get_observation()

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, dict[str, Any]]:
        """Apply an action and advance the first-order joint dynamics."""
        if self._closed:
            raise RuntimeError("RobotEnv is closed")

        action_vec = np.asarray(action, dtype=np.float32).reshape(-1)
        if action_vec.shape != (self.action_dim,):
            raise ValueError(f"Expected action shape ({self.action_dim},), got {action_vec.shape}")

        if self._last_step_t is None:
            self._ensure_running()
            self._last_step_t = time.time() - self.dt

        self._cmd = np.clip(action_vec, self._low, self._high)
        now = time.time()
        dt = max(now - self._last_step_t, 1e-6)
        alpha = min(dt / self.tau, 1.0)

        previous_state = self._state.copy()
        self._state = self._state + (self._cmd - self._state) * alpha
        self._state_vel = (self._state - previous_state) / dt
        self._last_step_t = now

        self._log_state(now)

        reward = -float(np.abs(self._cmd - self._state).sum())
        info = {
            "cmd": self.get_action(),
            "state": self._state.copy(),
            "t": now,
        }
        return self.get_observation(), reward, False, info

    def get_observation(self) -> np.ndarray:
        """Return [joint_position(14), joint_velocity(14)]."""
        return np.concatenate([self._state, self._state_vel]).copy()

    def get_action(self) -> np.ndarray:
        """Return the latest commanded joint positions."""
        return self._cmd.copy()

    def get_action_space(self) -> tuple[np.ndarray, np.ndarray]:
        """Return (low, high) joint limits for all arm joints."""
        return self._low.copy(), self._high.copy()

    def close(self) -> None:
        """Mark the environment as closed and clean up ZMQ resources."""
        self._closed = True
        self._zmq_pub.close()
        self._zmq_ctx.term()
