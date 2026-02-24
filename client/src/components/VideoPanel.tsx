import { useCallback, useEffect, useMemo, useRef } from "react";

import { useWebRTC } from "../hooks/useWebRTC";
import { useLayout } from "../contexts/LayoutContext";
import CompactHeader from "./CompactHeader";

const CAMERA_PANEL_PLACEHOLDER_METRICS: [string, string, string] = ["--:--:--", "-- fps", "-- ms"];
const STALLED_STREAM_RECOVERY_COOLDOWN_MS = 30_000;
const STALLED_STREAM_RECONNECT_DELAY_MS = 800;

export default function VideoPanel() {
  const { isZen } = useLayout();
  const {
    streams,
    connectionState,
    expectedCameraCount,
    partialLive,
    connect,
    disconnect,
  } = useWebRTC();
  const hasStreams = streams.length > 0;
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastRecoveryAtRef = useRef(0);
  const liveCount = streams.length;
  const missingCount =
    expectedCameraCount !== null ? Math.max(expectedCameraCount - liveCount, 0) : 0;
  const cameraGuardMessage =
    expectedCameraCount !== null && partialLive
      ? `Camera stream error: ${liveCount}/${expectedCameraCount} live (${missingCount} missing)`
      : null;

  const statusText = useMemo(() => {
    switch (connectionState) {
      case "connected":
        return "Live";
      case "connecting":
        return "Connecting…";
      case "failed":
        return "Failed";
      case "disconnected":
        return "Disconnected";
      case "closed":
        return "Closed";
      case "new":
        return "Starting…";
      case "idle":
        return "Idle";
      default:
        return "No peer";
    }
  }, [connectionState]);

  useEffect(() => {
    void Promise.resolve(connect()).catch(() => {
      // Keep UI stable; connection errors are reflected via connectionState.
    });
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  useEffect(() => {
    if (!["disconnected", "failed", "closed"].includes(connectionState)) {
      return;
    }
    const timer = setTimeout(() => {
      void Promise.resolve(connect()).catch(() => {});
    }, 3000);
    return () => {
      clearTimeout(timer);
    };
  }, [connectionState, connect]);

  const recoverStalledStream = useCallback(
    (_cameraName: string) => {
      if (connectionState !== "connected") {
        return;
      }
      if (reconnectTimerRef.current) {
        return;
      }
      const now = Date.now();
      if (now - lastRecoveryAtRef.current < STALLED_STREAM_RECOVERY_COOLDOWN_MS) {
        return;
      }
      lastRecoveryAtRef.current = now;
      disconnect();
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        void Promise.resolve(connect()).catch(() => {
          // Retry is handled by connection-state transitions.
        });
      }, STALLED_STREAM_RECONNECT_DELAY_MS);
    },
    [connect, connectionState, disconnect],
  );

  useEffect(() => {
    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };
  }, []);

  const streamOrder = useMemo(() => ["left", "center", "right"], []);
  const orderedStreams = useMemo(
    () =>
      [...streams].sort((left, right) => {
        const leftIndex = streamOrder.indexOf((left.name ?? "").toLowerCase());
        const rightIndex = streamOrder.indexOf((right.name ?? "").toLowerCase());
        return leftIndex - rightIndex;
      }),
    [streams, streamOrder],
  );
  const tiles = useMemo(
    () =>
      orderedStreams.map((entry) => {
        const slot = entry.name ?? "";
        const label = slot ? slot.charAt(0).toUpperCase() + slot.slice(1) : "Camera";
        return (
          <VideoTile
            key={slot || entry.id}
            stream={entry.stream}
            cameraName={slot}
            label={label}
            monitorEnabled={connectionState === "connected"}
            onStalled={recoverStalledStream}
          />
        );
      }),
    [connectionState, orderedStreams, recoverStalledStream],
  );

  return (
    <section className={`video-panel ${isZen ? "panel--zen" : "panel"}`}>
      {!isZen && (
        <CompactHeader
          chip="CAM"
          label="H264"
          metrics={CAMERA_PANEL_PLACEHOLDER_METRICS}
          focusTarget="camera"
          focusKey="1"
        />
      )}
      <div className={`media-placeholder ${hasStreams ? "has-video" : ""}`}>
        {cameraGuardMessage && (
          <div className="stream-error" role="alert">
            {cameraGuardMessage}
          </div>
        )}
        {hasStreams ? (
          <>
            <div className="camera-grid">{tiles}</div>
            <div className="stream-status">{statusText}</div>
          </>
        ) : (
          <>
            <div className="placeholder-label">Video stream</div>
            <div className="placeholder-meta">{statusText}</div>
          </>
        )}
      </div>
    </section>
  );
}

type VideoTileProps = {
  stream: MediaStream;
  cameraName: string;
  label: string;
  monitorEnabled: boolean;
  onStalled: (cameraName: string) => void;
};

function VideoTile({ stream, cameraName, label, monitorEnabled, onStalled }: VideoTileProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    video.srcObject = stream;
    const playResult = video.play();
    if (playResult && typeof playResult.catch === "function") {
      playResult.catch(() => {});
    }
    return () => {
      video.srcObject = null;
    };
  }, [stream]);

  useEffect(() => {
    if (!monitorEnabled) {
      return;
    }
    const video = videoRef.current;
    if (!video) {
      return;
    }
    const track = stream.getVideoTracks()[0];
    if (!track) {
      return;
    }

    const tickMs = 2000;
    const stallThresholdMs = 15_000;
    const warmupMs = 8000;
    const warmupUntil = Date.now() + warmupMs;
    let stagnantMs = 0;
    let lastTime = -1;
    let triedSoftRecovery = false;

    const interval = setInterval(() => {
      if (track.readyState !== "live") {
        return;
      }
      if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
        return;
      }
      if (video.paused) {
        const result = video.play();
        if (result && typeof result.catch === "function") {
          result.catch(() => {});
        }
        return;
      }
      const currentTime = video.currentTime;
      if (currentTime > lastTime + 0.001) {
        lastTime = currentTime;
        stagnantMs = 0;
        triedSoftRecovery = false;
        return;
      }
      if (Date.now() < warmupUntil) {
        return;
      }
      stagnantMs += tickMs;
      if (!triedSoftRecovery && stagnantMs >= stallThresholdMs / 2) {
        triedSoftRecovery = true;
        video.srcObject = stream;
        const result = video.play();
        if (result && typeof result.catch === "function") {
          result.catch(() => {});
        }
        return;
      }
      if (stagnantMs >= stallThresholdMs) {
        onStalled(cameraName || label.toLowerCase());
        stagnantMs = 0;
        triedSoftRecovery = false;
      }
    }, tickMs);

    return () => {
      clearInterval(interval);
    };
  }, [cameraName, label, monitorEnabled, onStalled, stream]);

  return (
    <div className="camera-tile">
      <video
        ref={videoRef}
        className="video-stream"
        autoPlay
        playsInline
        muted
        data-testid="camera-stream"
      />
      <div className="camera-label">{label}</div>
    </div>
  );
}
