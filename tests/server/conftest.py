"""Shared fixtures for server tests."""

import os
import sys

import pytest

# Ensure the server package directory is importable from tests
_server_dir = os.path.join(os.path.dirname(__file__), "..", "..", "server")
sys.path.insert(0, os.path.abspath(_server_dir))


@pytest.fixture
def base_url():
    """Base URL for the FastAPI dev server."""
    return "http://localhost:8000"
