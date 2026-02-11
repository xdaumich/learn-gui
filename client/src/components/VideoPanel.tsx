import { useEffect, useMemo, useRef } from "react";

import { useWebRTC } from "../hooks/useWebRTC";
import { useLayout } from "../contexts/LayoutContext";
import CompactHeader from "./CompactHeader";

export default function VideoPanel() {
  const { mode } = useLayout();
  const isZen = mode === "zen";
  const {
    streams,
    connectionState,
    expectedCameraCount,
    partialLive,
    connect,
    disconnect,
  } = useWebRTC();
  const hasStreams = streams.length > 0;
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

  const tiles = useMemo(
    () =>
      streams.map((entry, index) => (
        <VideoTile
          key={entry.id}
          stream={entry.stream}
          label={`Camera ${index + 1}`}
        />
      )),
    [streams],
  );

  return (
    <section className={`video-panel ${isZen ? "panel--zen" : "panel"}`}>
      {!isZen && (
        <CompactHeader
          chip="CAM"
          label="H264"
          metrics={["--:--:--", "-- fps", "-- ms"]}
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
  label: string;
};

function VideoTile({ stream, label }: VideoTileProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    video.srcObject = stream;
    return () => {
      video.srcObject = null;
    };
  }, [stream]);

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
