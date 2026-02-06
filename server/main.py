"""FastAPI entry point -- all routes start here."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import rerun_bridge

app = FastAPI(title="Telemetry Console API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/rerun/status")
async def rerun_status():
    """Return the current state of the Rerun bridge."""
    return {
        "running": rerun_bridge.is_running(),
        "web_url": rerun_bridge.web_url(),
    }


# TODO: add signaling routes (POST /offer, etc.)
# TODO: add telemetry ingestion routes
# TODO: add WebSocket sync endpoint
