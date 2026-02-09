import { useCallback, useRef, useState } from "react";

type WebRTCState = RTCPeerConnectionState | "idle";
type StreamEntry = { id: string; stream: MediaStream };

const SIGNALING_URL = "http://localhost:8000/webrtc/offer";
const CAMERAS_URL = "http://localhost:8000/webrtc/cameras";

function stopStreamTracks(entries: StreamEntry[]): void {
  entries.forEach((entry) => {
    entry.stream.getTracks().forEach((track) => track.stop());
  });
}

export function useWebRTC() {
  const peerRef = useRef<RTCPeerConnection | null>(null);
  const streamsRef = useRef<StreamEntry[]>([]);
  const connectTokenRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const [streams, setStreams] = useState<StreamEntry[]>([]);
  const [connectionState, setConnectionState] = useState<WebRTCState>("idle");

  const disconnect = useCallback(() => {
    // Invalidate any in-flight connect() attempt and abort pending fetches.
    connectTokenRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;

    const pc = peerRef.current;
    peerRef.current = null;

    if (pc) {
      pc.ontrack = null;
      pc.onconnectionstatechange = null;
      pc.close();
    }

    stopStreamTracks(streamsRef.current);
    streamsRef.current = [];
    setStreams([]);
    setConnectionState(pc ? "disconnected" : "idle");
  }, []);

  const connect = useCallback(async () => {
    if (peerRef.current) {
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    connectTokenRef.current += 1;
    const token = connectTokenRef.current;

    const pc = new RTCPeerConnection();
    peerRef.current = pc;
    setConnectionState("connecting");

    const isCurrent = (): boolean => peerRef.current === pc && connectTokenRef.current === token;
    const isActive = (): boolean => isCurrent() && !controller.signal.aborted;

    const addTrackStream = (track: MediaStreamTrack): void => {
      const trackId = track.id;
      setStreams((prev) => {
        if (prev.some((entry) => entry.id === trackId)) {
          return prev;
        }
        const next = [...prev, { id: trackId, stream: new MediaStream([track]) }];
        streamsRef.current = next;
        return next;
      });
    };

    const fetchCameraCount = async (): Promise<number | null> => {
      try {
        const response = await fetch(CAMERAS_URL, { signal: controller.signal });
        const cameras = await response.json();
        if (!isActive()) {
          return null;
        }
        if (Array.isArray(cameras) && cameras.length > 0) {
          return cameras.length;
        }
        return 1;
      } catch {
        if (!isActive()) {
          return null;
        }
        return 1;
      }
    };

    const addVideoTransceivers = (count: number): void => {
      const capabilities = RTCRtpReceiver.getCapabilities?.("video");
      const h264Codecs =
        capabilities?.codecs?.filter((codec) => codec.mimeType?.toLowerCase().includes("h264")) ??
        [];

      for (let i = 0; i < count; i += 1) {
        if (!isActive() || pc.signalingState === "closed") {
          return;
        }
        const transceiver = pc.addTransceiver("video", { direction: "recvonly" });
        if (h264Codecs.length > 0 && transceiver.setCodecPreferences) {
          transceiver.setCodecPreferences(h264Codecs);
        }
      }
    };

    pc.ontrack = (event) => {
      if (!isActive()) {
        return;
      }
      addTrackStream(event.track);
    };

    pc.onconnectionstatechange = () => {
      if (!isActive()) {
        return;
      }
      setConnectionState(pc.connectionState);
      if (pc.connectionState === "failed") {
        disconnect();
      }
    };

    try {
      const cameraCount = await fetchCameraCount();
      if (cameraCount === null) {
        return;
      }
      addVideoTransceivers(cameraCount);
      if (!isActive()) {
        return;
      }

      const offer = await pc.createOffer();
      if (!isActive()) {
        return;
      }
      await pc.setLocalDescription(offer);
      if (!isActive()) {
        return;
      }

      const response = await fetch(SIGNALING_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({ sdp: offer.sdp, type: offer.type }),
      });
      const answer = await response.json();

      if (!isActive()) {
        return;
      }
      await pc.setRemoteDescription(answer);
    } catch (error) {
      // If this attempt is obsolete (StrictMode/HMR remount), don't tear down the current PC.
      if (!isActive()) {
        return;
      }
      disconnect();
      throw error;
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
    }
  }, [disconnect]);

  return { streams, connectionState, connect, disconnect };
}
