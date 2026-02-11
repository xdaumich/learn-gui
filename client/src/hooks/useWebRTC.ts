import { useCallback, useRef, useState } from "react";
import {
  API_BASE_URL,
  CAMERA_LIVE_GRACE_MS,
  ICE_GATHER_TIMEOUT_MS,
  WHEP_BASE_URL,
  WHEP_CONNECT_RETRY_MS,
  WHEP_CONNECT_TIMEOUT_MS,
} from "../config";

type WebRTCState = RTCPeerConnectionState | "idle";
type StreamEntry = { id: string; stream: MediaStream };
type PeerEntry = { id: string; pc: RTCPeerConnection };

const CAMERAS_URL = `${API_BASE_URL}/webrtc/cameras`;

function isWhepRetryableStatus(status: number): boolean {
  return status === 404 || status === 425 || status === 503;
}

function stopStreamTracks(entries: StreamEntry[]): void {
  entries.forEach((entry) => {
    entry.stream.getTracks().forEach((track) => track.stop());
  });
}

function streamPathForCamera(cameraName: string): string {
  return cameraName.toLowerCase();
}

function whepUrlForCamera(cameraName: string): string {
  const streamPath = encodeURIComponent(streamPathForCamera(cameraName));
  return `${WHEP_BASE_URL}/${streamPath}/whep`;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, Math.max(0, ms));
  });
}

async function waitForIceGatheringComplete(
  pc: RTCPeerConnection,
  timeoutMs: number,
): Promise<void> {
  if (pc.iceGatheringState === "complete") {
    return;
  }
  if (typeof pc.addEventListener !== "function") {
    return;
  }

  await new Promise<void>((resolve) => {
    let done = false;
    const cleanup = () => {
      if (done) {
        return;
      }
      done = true;
      clearTimeout(timer);
      pc.removeEventListener("icegatheringstatechange", onStateChange);
      resolve();
    };
    const onStateChange = () => {
      if (pc.iceGatheringState === "complete") {
        cleanup();
      }
    };
    const timer = setTimeout(cleanup, Math.max(0, timeoutMs));
    pc.addEventListener("icegatheringstatechange", onStateChange);
    onStateChange();
  });
}

function summarizeConnectionState(peers: PeerEntry[]): WebRTCState {
  if (peers.length === 0) {
    return "idle";
  }
  const states = peers.map((entry) => entry.pc.connectionState);
  if (states.some((state) => state === "failed")) {
    return "failed";
  }
  if (states.some((state) => state === "connected")) {
    return "connected";
  }
  if (states.some((state) => state === "connecting" || state === "new")) {
    return "connecting";
  }
  if (states.some((state) => state === "disconnected")) {
    return "disconnected";
  }
  if (states.every((state) => state === "closed")) {
    return "closed";
  }
  return "disconnected";
}

export function useWebRTC() {
  const peersRef = useRef<PeerEntry[]>([]);
  const streamsRef = useRef<StreamEntry[]>([]);
  const connectTokenRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const partialLiveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [streams, setStreams] = useState<StreamEntry[]>([]);
  const [connectionState, setConnectionState] = useState<WebRTCState>("idle");
  const [expectedCameraCount, setExpectedCameraCount] = useState<number | null>(null);
  const [partialLiveGateOpen, setPartialLiveGateOpen] = useState(false);

  const clearPartialLiveTimer = useCallback(() => {
    if (partialLiveTimerRef.current) {
      clearTimeout(partialLiveTimerRef.current);
      partialLiveTimerRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    // Invalidate any in-flight connect() attempt and abort pending fetches.
    connectTokenRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;

    const peers = peersRef.current;
    peersRef.current = [];

    peers.forEach(({ pc }) => {
      pc.ontrack = null;
      pc.onconnectionstatechange = null;
      pc.close();
    });

    stopStreamTracks(streamsRef.current);
    streamsRef.current = [];
    setStreams([]);
    setExpectedCameraCount(null);
    clearPartialLiveTimer();
    setPartialLiveGateOpen(false);
    setConnectionState(peers.length > 0 ? "disconnected" : "idle");
  }, [clearPartialLiveTimer]);

  const syncConnectionState = useCallback(() => {
    const state = summarizeConnectionState(peersRef.current);
    setConnectionState(state);
    clearPartialLiveTimer();
    setPartialLiveGateOpen(false);
    if (state === "connected") {
      partialLiveTimerRef.current = setTimeout(
        () => setPartialLiveGateOpen(true),
        CAMERA_LIVE_GRACE_MS,
      );
    }
  }, [clearPartialLiveTimer]);

  const connect = useCallback(async () => {
    if (peersRef.current.length > 0) {
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    connectTokenRef.current += 1;
    const token = connectTokenRef.current;

    setConnectionState("connecting");

    function isCurrent(): boolean {
      return connectTokenRef.current === token;
    }

    function isActive(): boolean {
      return isCurrent() && !controller.signal.aborted;
    }

    function addTrackStream(track: MediaStreamTrack, cameraName: string): void {
      const trackId = `${cameraName}:${track.id}`;
      setStreams((prev) => {
        if (prev.some((entry) => entry.id === trackId)) {
          return prev;
        }
        const next = [...prev, { id: trackId, stream: new MediaStream([track]) }];
        streamsRef.current = next;
        return next;
      });
    }

    async function fetchCameraNames(): Promise<string[] | null> {
      try {
        const response = await fetch(CAMERAS_URL, { signal: controller.signal });
        const cameras = await response.json();
        if (!isActive()) {
          return null;
        }
        if (!Array.isArray(cameras)) {
          return [];
        }
        return cameras.filter((camera): camera is string => typeof camera === "string");
      } catch {
        if (!isActive()) {
          return null;
        }
        return [];
      }
    }

    async function connectCamera(cameraName: string): Promise<void> {
      const pc = new RTCPeerConnection();
      const peer: PeerEntry = { id: cameraName, pc };
      peersRef.current = [...peersRef.current, peer];

      pc.ontrack = (event) => {
        if (!isActive()) {
          return;
        }
        addTrackStream(event.track, cameraName);
      };

      pc.onconnectionstatechange = () => {
        if (!isActive()) {
          return;
        }
        syncConnectionState();
        if (pc.connectionState === "failed") {
          disconnect();
        }
      };

      pc.addTransceiver("video", { direction: "recvonly" });
      const offer = await pc.createOffer();
      if (!isActive()) {
        return;
      }
      await pc.setLocalDescription(offer);
      await waitForIceGatheringComplete(pc, ICE_GATHER_TIMEOUT_MS);
      if (!isActive()) {
        return;
      }

      const streamUrl = whepUrlForCamera(cameraName);
      const deadline = Date.now() + WHEP_CONNECT_TIMEOUT_MS;
      let response: Response | null = null;
      while (isActive()) {
        response = await fetch(streamUrl, {
          method: "POST",
          headers: { "Content-Type": "application/sdp" },
          signal: controller.signal,
          body: pc.localDescription?.sdp ?? offer.sdp ?? "",
        });
        if (response.ok) {
          break;
        }
        const isRetryable = isWhepRetryableStatus(response.status);
        if (!isRetryable || Date.now() >= deadline) {
          throw new Error(`WHEP request failed (${response.status})`);
        }
        await delay(WHEP_CONNECT_RETRY_MS);
      }
      if (!isActive()) {
        return;
      }
      if (!response || !response.ok) {
        throw new Error(`WHEP request for ${cameraName} timed out waiting for stream availability.`);
      }
      const answerSdp = await response.text();
      if (!answerSdp) {
        throw new Error("WHEP request returned empty SDP answer.");
      }

      if (!isActive()) {
        return;
      }
      await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });
    }

    try {
      const cameraNames = await fetchCameraNames();
      if (cameraNames === null) {
        return;
      }
      if (cameraNames.length === 0) {
        setExpectedCameraCount(0);
        setConnectionState("disconnected");
        return;
      }
      setExpectedCameraCount(cameraNames.length);

      for (const cameraName of cameraNames) {
        if (!isActive()) {
          return;
        }
        await connectCamera(cameraName);
      }

      if (isActive()) {
        syncConnectionState();
      }
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
  }, [disconnect, syncConnectionState]);

  const partialLive =
    connectionState === "connected" &&
    partialLiveGateOpen &&
    expectedCameraCount !== null &&
    streams.length < expectedCameraCount;

  return {
    streams,
    connectionState,
    expectedCameraCount,
    partialLive,
    connect,
    disconnect,
  };
}
