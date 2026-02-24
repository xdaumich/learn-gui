"""Shared fixtures for server tests."""

import os
import sys

# Ensure the server package directory is importable from tests
_server_dir = os.path.join(os.path.dirname(__file__), "..", "..", "server")
sys.path.insert(0, os.path.abspath(_server_dir))

# Allow importing standalone scripts (e.g. mjpeg_debug.py)
_scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(_scripts_dir))
