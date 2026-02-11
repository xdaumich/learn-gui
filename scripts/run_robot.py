#!/usr/bin/env python3
"""Run a standalone robot-arm control loop with a gym-like API."""

from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np


def _reexec_in_venv() -> None:
    """Re-exec the script with the server venv Python if needed."""
    venv_python = os.path.join(
        os.path.dirname(__file__), "..", "server", ".venv", "bin", "python"
    )
    venv_python = os.path.abspath(venv_python)

    if os.path.isfile(venv_python) and os.path.realpath(sys.executable) != os.path.realpath(
        venv_python
    ):
        os.execv(venv_python, [venv_python, *sys.argv])


def _demo_action(t: float) -> np.ndarray:
    """Generate a smooth demonstration action for both arms."""
    action = np.zeros(14, dtype=np.float32)

    action[0] = np.pi / 2  # L_arm_j1
    action[1] = 0.0 * np.cos(t * 0.7)  # L_arm_j2
    action[2] = 0.0 * np.sin(t * 0.5)  # L_arm_j3
    action[3] = -np.pi / 2 + 0.5 * np.sin(t * 0.5)  # L_arm_j4

    action[7] = -np.pi / 2  # R_arm_j1
    action[8] = 0.0 * np.cos(t * 0.7)  # R_arm_j2
    action[9] = 0.0 * np.sin(t * 0.5)  # R_arm_j3
    action[10] = -np.pi / 2 + 0.5 * np.sin(t * 0.5)  # R_arm_j4
    return action


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run standalone robot arm control stream.")
    parser.add_argument("--hz", type=float, default=20.0, help="Control loop frequency in Hz.")
    parser.add_argument("--tau", type=float, default=0.15, help="State lag time constant.")
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=None,
        help="Optional finite runtime; omit for continuous streaming.",
    )
    browser_group = parser.add_mutually_exclusive_group()
    browser_group.add_argument(
        "--open-browser",
        dest="open_browser",
        action="store_true",
        help="Open the standalone Rerun viewer in a browser window.",
    )
    browser_group.add_argument(
        "--no-open-browser",
        dest="open_browser",
        action="store_false",
        help="Do not auto-open the Rerun viewer browser window.",
    )
    parser.set_defaults(open_browser=True)
    return parser.parse_args()


def main() -> None:
    _reexec_in_venv()
    args = _parse_args()

    server_dir = os.path.join(os.path.dirname(__file__), "..", "server")
    sys.path.insert(0, os.path.abspath(server_dir))

    from robot_env import RobotEnv  # noqa: E402  # pyright: ignore[reportMissingImports]

    env = RobotEnv(hz=args.hz, tau=args.tau, open_browser=args.open_browser)
    observation = env.reset()
    low, high = env.get_action_space()
    viewer_url = env.viewer_url or "http://localhost:9090"

    print("Robot env ready.")
    print(f"Rerun viewer: {viewer_url}")
    print("GUI panel URL: http://localhost:5173")
    print("Gym-like API available: reset(), step(action), get_observation(), get_action().")
    print(f"Observation shape: {observation.shape} (state(14) + velocity(14))")
    print(f"Action shape: {low.shape} (14 joints)")
    print("Streaming demo actions to Rerun -- press Ctrl+C to stop.")

    try:
        t0 = time.time()
        while True:
            t = time.time() - t0
            action = np.clip(_demo_action(t), low, high)
            env.step(action)
            if args.duration_seconds is not None and t >= args.duration_seconds:
                break
            time.sleep(1.0 / env.hz)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        env.close()


if __name__ == "__main__":
    main()
