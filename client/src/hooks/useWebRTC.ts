import { useCallback, useRef, useState } from "react";

type WebRTCState = RTCPeerConnectionState | "idle";
type StreamEntry = { id: string; stream: MediaStream };

const SIGNALING_URL = "http://localhost:8000/webrtc/offer";
const CAMERAS_URL = "http://localhost:8000/webrtc/cameras";

export function useWebRTC() {
  const peerRef = useRef<RTCPeerConnection | null>(null);
  const streamsRef = useRef<StreamEntry[]>([]);
  const [streams, setStreams] = useState<StreamEntry[]>([]);
  const [connectionState, setConnectionState] = useState<WebRTCState>("idle");

  const disconnect = useCallback(() => {
    const pc = peerRef.current;
    if (!pc) {
      setConnectionState("idle");
      streamsRef.current = [];
      setStreams([]);
      return;
    }

    pc.ontrack = null;
    pc.onconnectionstatechange = null;
    pc.close();
    peerRef.current = null;
    streamsRef.current.forEach((entry) => {
      entry.stream.getTracks().forEach((track) => track.stop());
    });
    streamsRef.current = [];
    setStreams([]);
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
      const trackId = event.track.id;
      setStreams((prev) => {
        if (prev.some((entry) => entry.id === trackId)) {
          return prev;
        }
        const next = [...prev, { id: trackId, stream: new MediaStream([event.track]) }];
        streamsRef.current = next;
        return next;
      });
    };

    pc.onconnectionstatechange = () => {
      setConnectionState(pc.connectionState);
      if (pc.connectionState === "failed") {
        disconnect();
      }
    };

    try {
      let cameraCount = 1;
      try {
        const response = await fetch(CAMERAS_URL);
        const cameras = await response.json();
        if (Array.isArray(cameras) && cameras.length > 0) {
          cameraCount = cameras.length;
        }
      } catch {
        cameraCount = 1;
      }

      for (let i = 0; i < cameraCount; i += 1) {
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
      }

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

  return { streams, connectionState, connect, disconnect };
}
