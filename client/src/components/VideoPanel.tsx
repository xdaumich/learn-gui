import { useEffect, useMemo, useRef } from "react";

import { useWebRTC } from "../hooks/useWebRTC";
import { useLayout } from "../contexts/LayoutContext";

export default function VideoPanel() {
  const { mode, focusPanel, exitFocus, focusTarget } = useLayout();
  const isZen = mode === "zen";
  const isFocused = mode === "focus" && focusTarget === "camera";
  const { streams, connectionState, connect, disconnect } = useWebRTC();
  const hasStreams = streams.length > 0;

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
    void connect().catch(() => {
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
        <div className="compact-header">
          <div className="compact-header__left">
            <span className="compact-chip">CAM</span>
            <span className="compact-label">H264</span>
          </div>
          <div className="compact-header__metrics">
            <span>--:--:--</span>
            <span className="metric-divider">|</span>
            <span>-- fps</span>
            <span className="metric-divider">|</span>
            <span>-- ms</span>
          </div>
          <button
            className="maximize-btn"
            onClick={() => (isFocused ? exitFocus() : focusPanel("camera"))}
            type="button"
            title={isFocused ? "Restore (Esc)" : "Focus (1)"}
          >
            {isFocused ? "\u2921" : "\u2922"}
          </button>
        </div>
      )}
      <div className={`media-placeholder ${hasStreams ? "has-video" : ""}`}>
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
