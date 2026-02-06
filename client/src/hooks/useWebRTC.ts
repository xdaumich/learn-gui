import { useCallback, useRef, useState } from "react";

type WebRTCState = RTCPeerConnectionState | "idle";

const SIGNALING_URL = "http://localhost:8000/webrtc/offer";

export function useWebRTC() {
  const peerRef = useRef<RTCPeerConnection | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [connectionState, setConnectionState] = useState<WebRTCState>("idle");

  const disconnect = useCallback(() => {
    const pc = peerRef.current;
    if (!pc) {
      setConnectionState("idle");
      setStream(null);
      return;
    }

    pc.ontrack = null;
    pc.onconnectionstatechange = null;
    pc.close();
    peerRef.current = null;
    setStream(null);
    setConnectionState("disconnected");
  }, []);

  const connect = useCallback(async () => {
    if (peerRef.current) {
      return;
    }

    const pc = new RTCPeerConnection();
    peerRef.current = pc;
    setConnectionState("connecting");

    pc.ontrack = (event) => {
      if (event.streams[0]) {
        setStream(event.streams[0]);
      } else {
        const fallback = new MediaStream([event.track]);
        setStream(fallback);
      }
    };

    pc.onconnectionstatechange = () => {
      setConnectionState(pc.connectionState);
      if (pc.connectionState === "failed") {
        disconnect();
      }
    };

    const transceiver = pc.addTransceiver("video", { direction: "recvonly" });
    const capabilities = RTCRtpReceiver.getCapabilities?.("video");
    if (capabilities?.codecs && transceiver.setCodecPreferences) {
      const h264 = capabilities.codecs.filter((codec) =>
        codec.mimeType?.toLowerCase().includes("h264"),
      );
      if (h264.length > 0) {
        transceiver.setCodecPreferences(h264);
      }
    }

    try {
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const response = await fetch(SIGNALING_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sdp: offer.sdp, type: offer.type }),
      });
      const answer = await response.json();

      await pc.setRemoteDescription(answer);
    } catch (error) {
      disconnect();
      throw error;
    }
  }, [disconnect]);

  return { stream, connectionState, connect, disconnect };
}
