import { useCallback, useRef, useState } from "react";
import { API_BASE_URL, CAMERA_LIVE_GRACE_MS } from "../config";

type MJPEGState = "idle" | "connecting" | "connected" | "disconnected" | "failed";
type CameraEntry = { name: string; url: string };

const CAMERAS_URL = `${API_BASE_URL}/cameras`;
const RETRY_MS = 400;
const CONNECT_TIMEOUT_MS = 12_000;

function streamUrlForCamera(cameraName: string): string {
  return `${API_BASE_URL}/stream/${encodeURIComponent(cameraName.toLowerCase())}`;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, Math.max(0, ms));
  });
}

export function useMJPEG() {
  const [cameras, setCameras] = useState<CameraEntry[]>([]);
  const [connectionState, setConnectionState] = useState<MJPEGState>("idle");
  const [expectedCameraCount, setExpectedCameraCount] = useState<number | null>(null);
  const [partialLiveGateOpen, setPartialLiveGateOpen] = useState(false);
  const connectTokenRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const partialLiveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearPartialLiveTimer = useCallback(() => {
    if (partialLiveTimerRef.current) {
      clearTimeout(partialLiveTimerRef.current);
      partialLiveTimerRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    connectTokenRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setCameras([]);
    setExpectedCameraCount(null);
    clearPartialLiveTimer();
    setPartialLiveGateOpen(false);
    setConnectionState("idle");
  }, [clearPartialLiveTimer]);

  const connect = useCallback(async () => {
    const controller = new AbortController();
    abortRef.current = controller;
    connectTokenRef.current += 1;
    const token = connectTokenRef.current;

    setConnectionState("connecting");

    function isActive(): boolean {
      return connectTokenRef.current === token && !controller.signal.aborted;
    }

    const deadline = Date.now() + CONNECT_TIMEOUT_MS;

    while (isActive()) {
      try {
        const response = await fetch(CAMERAS_URL, { signal: controller.signal });
        const names = await response.json();
        if (!isActive()) return;

        if (Array.isArray(names) && names.length > 0) {
          const validNames = names.filter((n): n is string => typeof n === "string");
          setExpectedCameraCount(validNames.length);
          setCameras(validNames.map((name) => ({ name, url: streamUrlForCamera(name) })));
          setConnectionState("connected");
          clearPartialLiveTimer();
          setPartialLiveGateOpen(false);
          partialLiveTimerRef.current = setTimeout(
            () => setPartialLiveGateOpen(true),
            CAMERA_LIVE_GRACE_MS,
          );
          return;
        }
      } catch {
        if (!isActive()) return;
      }

      if (Date.now() >= deadline) {
        setConnectionState("failed");
        return;
      }
      await delay(RETRY_MS);
    }
  }, [clearPartialLiveTimer]);

  const partialLive =
    connectionState === "connected" &&
    partialLiveGateOpen &&
    expectedCameraCount !== null &&
    cameras.length < expectedCameraCount;

  return {
    cameras,
    connectionState,
    expectedCameraCount,
    partialLive,
    connect,
    disconnect,
  };
}
