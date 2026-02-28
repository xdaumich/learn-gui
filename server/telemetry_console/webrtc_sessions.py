import asyncio
import os
from dataclasses import dataclass, field

import depthai as dai
from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCRtpSender,
    RTCSessionDescription,
)
from aiortc.contrib.media import MediaRelay

from telemetry_console.camera import (
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    DEFAULT_KEYFRAME_INTERVAL,
    _build_h264_pipeline,
    _discover_device_profiles,
    _resolve_target_streams,
    CAMERA_STREAM_LAYOUT,
)
from telemetry_console.webrtc_track import H264Track


@dataclass
class CameraSlot:
    name: str          # "left" | "center" | "right"
    device: dai.Device
    pipeline: dai.Pipeline
    track: H264Track


@dataclass
class SessionManager:
    slots: dict[str, CameraSlot] = field(default_factory=dict)
    _peers: list[RTCPeerConnection] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _relay: MediaRelay = field(default_factory=MediaRelay)

    # --- Lifecycle ---

    def open_cameras(
        self,
        *,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: int = DEFAULT_FPS,
        keyframe_interval: int = DEFAULT_KEYFRAME_INTERVAL,
    ) -> list[str]:
        """Discover and open all available OAK cameras. Returns slot names started."""
        targets = _resolve_target_streams(None)
        for target in targets:
            if target.stream_name in self.slots:
                continue  # already open
            device = dai.Device(target.device_info)
            pipeline, queue = _build_h264_pipeline(
                device=device, width=width, height=height,
                fps=fps, keyframe_interval=keyframe_interval,
            )
            pipeline.start()
            track = H264Track(queue=queue, fps=fps)
            self.slots[target.stream_name] = CameraSlot(
                name=target.stream_name,
                device=device,
                pipeline=pipeline,
                track=track,
            )
        return [s for s in CAMERA_STREAM_LAYOUT if s in self.slots]

    def close_cameras(self) -> None:
        for slot in self.slots.values():
            try:
                slot.pipeline.stop()
            except Exception:
                pass
            try:
                slot.device.close()
            except Exception:
                pass
        self.slots.clear()

    # --- Signaling ---

    def _ice_config(self) -> RTCConfiguration:
        ice_host = os.environ.get("WEBRTC_ICE_HOST", "")
        servers = [RTCIceServer(urls="stun:stun.l.google.com:19302")]
        # TODO: if ice_host is set, configure host candidate for multi-NIC (issue #5)
        return RTCConfiguration(iceServers=servers)

    async def answer(self, camera: str, sdp_offer: str) -> str:
        """Create a WebRTC answer for a WHEP-style SDP offer. Returns SDP answer."""
        slot = self.slots.get(camera)
        if slot is None:
            raise KeyError(f"Camera '{camera}' not available")

        pc = RTCPeerConnection(configuration=self._ice_config())
        async with self._lock:
            self._peers.append(pc)

        @pc.on("connectionstatechange")
        async def on_state():
            if pc.connectionState in ("failed", "closed"):
                async with self._lock:
                    try:
                        self._peers.remove(pc)  # fix #1: list.remove not discard
                    except ValueError:
                        pass
                await pc.close()

        # Use MediaRelay to fan-out the single H264Track to multiple viewers
        # without frame-stealing (fix #3).
        relayed_track = self._relay.subscribe(slot.track)
        pc.addTrack(relayed_track)

        # Force H.264 codec — without this, aiortc picks VP8 (Chrome's first
        # preference) and the browser tries to decode our H.264 bytes as VP8.
        caps = RTCRtpSender.getCapabilities("video")
        h264_codecs = [c for c in caps.codecs if "h264" in c.mimeType.lower()]
        for transceiver in pc.getTransceivers():
            if transceiver.kind == "video" and h264_codecs:
                transceiver.setCodecPreferences(h264_codecs)

        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp_offer, type="offer"))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return pc.localDescription.sdp

    async def close_all_peers(self) -> None:
        async with self._lock:
            peers = list(self._peers)
            self._peers.clear()
        for pc in peers:
            await pc.close()


# Module-level singleton used by gui_api.py
session_manager = SessionManager()
