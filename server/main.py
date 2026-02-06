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
    camera_sockets = getattr(app.state, "camera_sockets", None)
    answer, pc = await webrtc.create_answer(
        offer.sdp,
        offer.type,
        camera_sockets=camera_sockets,
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


@app.get("/webrtc/cameras")
async def webrtc_cameras() -> list[str]:
    camera_sockets = getattr(app.state, "camera_sockets", None)
    if camera_sockets is None:
        camera_sockets = webrtc.list_camera_sockets()
    return [socket.name for socket in camera_sockets]


# TODO: add telemetry ingestion routes
# TODO: add WebSocket sync endpoint
