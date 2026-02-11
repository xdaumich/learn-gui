#!/usr/bin/env python3
"""Start the Rerun bridge and stream a live sine-wave demo.

Run from repo root:
    uv run --project server python scripts/run_rerun_demo.py
"""

from __future__ import annotations

import rerun_bridge


def main() -> None:
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
