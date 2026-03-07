import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { useWebRTC } from "../hooks/useWebRTC";

const STALLED_STREAM_RECOVERY_COOLDOWN_MS = 30_000;
const STALLED_STREAM_RECONNECT_DELAY_MS = 800;
const DEFAULT_NATIVE_ASPECT_RATIO = 16 / 9;
const DEFAULT_DISPLAY_ASPECT_RATIOS: Record<string, number> = {
  left: 9 / 16,
  center: 4 / 3,
  right: 9 / 16,
};

export default function VideoPanel() {
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
  const [displayAspectRatios, setDisplayAspectRatios] = useState<Record<string, number>>(
    DEFAULT_DISPLAY_ASPECT_RATIOS,
  );
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
  const handleAspectRatioChange = useCallback((cameraName: string, aspectRatio: number) => {
    if (!cameraName || !Number.isFinite(aspectRatio) || aspectRatio <= 0) {
      return;
    }
    setDisplayAspectRatios((current) => {
      if (Math.abs((current[cameraName] ?? 0) - aspectRatio) < 0.001) {
        return current;
      }
      return { ...current, [cameraName]: aspectRatio };
    });
  }, []);
  const orderedStreams = useMemo(
    () =>
      [...streams].sort((left, right) => {
        const leftIndex = streamOrder.indexOf((left.name ?? "").toLowerCase());
        const rightIndex = streamOrder.indexOf((right.name ?? "").toLowerCase());
        return leftIndex - rightIndex;
      }),
    [streams, streamOrder],
  );
  const cameraWidthWeights = useMemo(() => {
    const left = 0.5 * (displayAspectRatios.left ?? DEFAULT_DISPLAY_ASPECT_RATIOS.left);
    const center = displayAspectRatios.center ?? DEFAULT_DISPLAY_ASPECT_RATIOS.center;
    const right = 0.5 * (displayAspectRatios.right ?? DEFAULT_DISPLAY_ASPECT_RATIOS.right);
    return { left, center, right };
  }, [displayAspectRatios]);

  const cameraTiles = useMemo(
    () =>
      orderedStreams.map((entry) => {
        const slot = entry.name ?? "";
        const name = slot.toLowerCase();
        const label = slot ? slot.charAt(0).toUpperCase() + slot.slice(1) : "Camera";
        const variant = name === "center" ? "hero" : "wrist";
        const widthWeight = cameraWidthWeights[name] ?? 1;
        return (
          <VideoTile
            key={slot || entry.id}
            stream={entry.stream}
            cameraName={slot}
            label={label}
            monitorEnabled={connectionState === "connected"}
            onStalled={recoverStalledStream}
            onAspectRatioChange={handleAspectRatioChange}
            variant={variant}
            widthWeight={widthWeight}
          />
        );
      }),
    [cameraWidthWeights, connectionState, handleAspectRatioChange, orderedStreams, recoverStalledStream],
  );

  return (
    <section className="video-panel">
      <div className={`media-placeholder ${hasStreams ? "has-video" : ""}`}>
        {cameraGuardMessage && (
          <div className="stream-error" role="alert">
            {cameraGuardMessage}
          </div>
        )}
        {hasStreams ? (
          <>
            <div className="camera-grid">
              {cameraTiles}
            </div>
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
  onAspectRatioChange: (cameraName: string, aspectRatio: number) => void;
  variant?: "hero" | "wrist";
  widthWeight: number;
};

function VideoTile({
  stream,
  cameraName,
  label,
  monitorEnabled,
  onStalled,
  onAspectRatioChange,
  variant,
  widthWeight,
}: VideoTileProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const normalizedCameraName = cameraName.toLowerCase();
  const isRotated = normalizedCameraName === "left" || normalizedCameraName === "right";
  const rotationClass =
    normalizedCameraName === "left"
      ? "video-stream--rotate-left"
      : normalizedCameraName === "right"
        ? "video-stream--rotate-right"
        : "";
  const [nativeAspectRatio, setNativeAspectRatio] = useState(
    normalizedCameraName === "center" ? 4 / 3 : DEFAULT_NATIVE_ASPECT_RATIO,
  );
  const displayAspectRatio = isRotated ? 1 / nativeAspectRatio : nativeAspectRatio;
  const tileStyle: CSSProperties = {
    aspectRatio: displayAspectRatio,
    flex: `${widthWeight} 1 0px`,
    ...(isRotated ? { ["--native-aspect-ratio" as const]: `${nativeAspectRatio}` } : {}),
  };

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
    const video = videoRef.current;
    if (!video) {
      return;
    }

    const updateAspectRatio = () => {
      if (video.videoWidth <= 0 || video.videoHeight <= 0) {
        return;
      }
      const nextNativeAspectRatio = video.videoWidth / video.videoHeight;
      setNativeAspectRatio((current) =>
        Math.abs(current - nextNativeAspectRatio) < 0.001 ? current : nextNativeAspectRatio,
      );
      onAspectRatioChange(
        normalizedCameraName,
        isRotated ? video.videoHeight / video.videoWidth : nextNativeAspectRatio,
      );
    };

    updateAspectRatio();
    video.addEventListener("loadedmetadata", updateAspectRatio);
    video.addEventListener("resize", updateAspectRatio);
    return () => {
      video.removeEventListener("loadedmetadata", updateAspectRatio);
      video.removeEventListener("resize", updateAspectRatio);
    };
  }, [isRotated, normalizedCameraName, onAspectRatioChange, stream]);

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
    <div
      className={`camera-tile ${variant === "hero" ? "camera-tile--hero" : "camera-tile--wrist"}`}
      data-camera={normalizedCameraName}
      style={tileStyle}
    >
      <video
        ref={videoRef}
        className={`video-stream ${rotationClass}`.trim()}
        autoPlay
        playsInline
        muted
        data-testid="camera-stream"
      />
      <div className="camera-label">{label}</div>
    </div>
  );
}
