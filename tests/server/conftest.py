"""Shared fixtures for server tests."""

import pytest


@pytest.fixture
def base_url():
    """Base URL for the FastAPI dev server."""
    return "http://localhost:8000"
