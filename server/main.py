"""FastAPI entry point -- all routes start here."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import rerun_bridge
import webrtc
from schemas import SDPOffer, SDPAnswer

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


@app.post("/webrtc/offer", response_model=SDPAnswer)
async def webrtc_offer(offer: SDPOffer) -> SDPAnswer:
    track_factory = getattr(app.state, "track_factory", None)
    answer, pc = await webrtc.create_answer(
        offer.sdp,
        offer.type,
        track_factory=track_factory,
    )

    if not hasattr(app.state, "peer_connections"):
        app.state.peer_connections = set()
    app.state.peer_connections.add(pc)

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange() -> None:
        if pc.iceConnectionState == "failed":
            await pc.close()
            app.state.peer_connections.discard(pc)

    return SDPAnswer(sdp=answer.sdp, type=answer.type)


# TODO: add telemetry ingestion routes
# TODO: add WebSocket sync endpoint
