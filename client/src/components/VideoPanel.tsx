import { useEffect, useMemo, useRef } from "react";

import { useWebRTC } from "../hooks/useWebRTC";

export default function VideoPanel() {
  const { streams, connectionState, connect, disconnect } = useWebRTC();
  const hasStreams = streams.length > 0;

  const statusText = useMemo(() => {
    switch (connectionState) {
      case "connected":
        return "Live connection";
      case "connecting":
        return "Connecting...";
      case "failed":
        return "Connection failed";
      case "disconnected":
        return "Disconnected";
      case "closed":
        return "Closed";
      case "new":
        return "Starting...";
      case "idle":
        return "Idle";
      default:
        return "No peer connection";
    }
  }, [connectionState]);

  useEffect(() => {
    void connect();
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
    <section className="panel video-panel">
      <div className="panel-header">
        <div>
          <h2>Live Camera</h2>
          <p className="panel-subtitle">WebRTC low-latency feed</p>
        </div>
        <span className="panel-chip">H264</span>
      </div>
      <div className="panel-body">
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
        <div className="panel-metrics">
          <div className="metric">
            <span className="metric-label">Capture Time</span>
            <span className="metric-value">--:--:--</span>
          </div>
          <div className="metric">
            <span className="metric-label">Frame Rate</span>
            <span className="metric-value">-- fps</span>
          </div>
          <div className="metric">
            <span className="metric-label">Latency</span>
            <span className="metric-value">-- ms</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function VideoTile({ stream, label }: { stream: MediaStream; label: string }) {
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
