import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { useMJPEG } from "../hooks/useMJPEG";

const DEFAULT_NATIVE_ASPECT_RATIO = 16 / 9;
const DEFAULT_DISPLAY_ASPECT_RATIOS: Record<string, number> = {
  left: 9 / 16,
  center: 4 / 3,
  right: 9 / 16,
};

export default function VideoPanel() {
  const {
    cameras,
    connectionState,
    expectedCameraCount,
    partialLive,
    connect,
    disconnect,
  } = useMJPEG();
  const hasCameras = cameras.length > 0;
  const [displayAspectRatios, setDisplayAspectRatios] = useState<Record<string, number>>(
    DEFAULT_DISPLAY_ASPECT_RATIOS,
  );
  const liveCount = cameras.length;
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
      case "idle":
        return "Idle";
      default:
        return "No peer";
    }
  }, [connectionState]);

  useEffect(() => {
    void Promise.resolve(connect()).catch(() => {});
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  useEffect(() => {
    if (!["disconnected", "failed"].includes(connectionState)) {
      return;
    }
    const timer = setTimeout(() => {
      void Promise.resolve(connect()).catch(() => {});
    }, 3000);
    return () => {
      clearTimeout(timer);
    };
  }, [connectionState, connect]);

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
  const orderedCameras = useMemo(
    () =>
      [...cameras].sort((a, b) => {
        const ai = streamOrder.indexOf(a.name.toLowerCase());
        const bi = streamOrder.indexOf(b.name.toLowerCase());
        return ai - bi;
      }),
    [cameras, streamOrder],
  );
  const cameraWidthWeights = useMemo(() => {
    const left = 0.5 * (displayAspectRatios.left ?? DEFAULT_DISPLAY_ASPECT_RATIOS.left);
    const center = displayAspectRatios.center ?? DEFAULT_DISPLAY_ASPECT_RATIOS.center;
    const right = 0.5 * (displayAspectRatios.right ?? DEFAULT_DISPLAY_ASPECT_RATIOS.right);
    return { left, center, right };
  }, [displayAspectRatios]);

  const cameraTiles = useMemo(
    () =>
      orderedCameras.map((entry) => {
        const name = entry.name.toLowerCase();
        const label = name.charAt(0).toUpperCase() + name.slice(1);
        const variant = name === "center" ? "hero" : "wrist";
        const widthWeight = cameraWidthWeights[name as keyof typeof cameraWidthWeights] ?? 1;
        return (
          <MJPEGTile
            key={name}
            url={entry.url}
            cameraName={name}
            label={label}
            onAspectRatioChange={handleAspectRatioChange}
            variant={variant}
            widthWeight={widthWeight}
          />
        );
      }),
    [cameraWidthWeights, handleAspectRatioChange, orderedCameras],
  );

  return (
    <section className="video-panel">
      <div className={`media-placeholder ${hasCameras ? "has-video" : ""}`}>
        {cameraGuardMessage && (
          <div className="stream-error" role="alert">
            {cameraGuardMessage}
          </div>
        )}
        {hasCameras ? (
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

type MJPEGTileProps = {
  url: string;
  cameraName: string;
  label: string;
  onAspectRatioChange: (cameraName: string, aspectRatio: number) => void;
  variant?: "hero" | "wrist";
  widthWeight: number;
};

function MJPEGTile({
  url,
  cameraName,
  label,
  onAspectRatioChange,
  variant,
  widthWeight,
}: MJPEGTileProps) {
  const imgRef = useRef<HTMLImageElement | null>(null);
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

  const handleLoad = useCallback(() => {
    const img = imgRef.current;
    if (!img || img.naturalWidth <= 0 || img.naturalHeight <= 0) return;
    const nextNative = img.naturalWidth / img.naturalHeight;
    setNativeAspectRatio((current) =>
      Math.abs(current - nextNative) < 0.001 ? current : nextNative,
    );
    onAspectRatioChange(
      normalizedCameraName,
      isRotated ? img.naturalHeight / img.naturalWidth : nextNative,
    );
  }, [isRotated, normalizedCameraName, onAspectRatioChange]);

  return (
    <div
      className={`camera-tile ${variant === "hero" ? "camera-tile--hero" : "camera-tile--wrist"}`}
      data-camera={normalizedCameraName}
      style={tileStyle}
    >
      <img
        ref={imgRef}
        src={url}
        className={`video-stream ${rotationClass}`.trim()}
        onLoad={handleLoad}
        data-testid="camera-stream"
        alt={`${label} camera`}
      />
      <div className="camera-label">{label}</div>
    </div>
  );
}
