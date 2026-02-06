#!/usr/bin/env python3
"""Start the Rerun bridge and stream a live sine-wave demo.

Run from repo root:
    python3 scripts/run_rerun_demo.py

The script re-execs into server/.venv so that all dependencies are available.
"""

from __future__ import annotations

import os
import sys


def _reexec_in_venv() -> None:
    """Re-exec the script using the server venv Python if we aren't already in it."""
    venv_python = os.path.join(
        os.path.dirname(__file__), "..", "server", ".venv", "bin", "python"
    )
    venv_python = os.path.abspath(venv_python)

    if os.path.isfile(venv_python) and os.path.realpath(sys.executable) != os.path.realpath(venv_python):
        os.execv(venv_python, [venv_python, *sys.argv])


def main() -> None:
    _reexec_in_venv()

    # Ensure the server package is importable
    server_dir = os.path.join(os.path.dirname(__file__), "..", "server")
    sys.path.insert(0, os.path.abspath(server_dir))

    import rerun_bridge  # noqa: E402  (imported after path manipulation)

    print("Starting Rerun bridge …")
    url = rerun_bridge.start(open_browser=False)
    print(f"Web viewer ready at {url}")
    print("Streaming sine wave — press Ctrl+C to stop.")

    try:
        rerun_bridge.stream_sine_wave()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
