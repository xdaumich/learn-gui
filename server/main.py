"""FastAPI entry point -- all routes start here."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


# TODO: add signaling routes (POST /offer, etc.)
# TODO: add telemetry ingestion routes
# TODO: add WebSocket sync endpoint
