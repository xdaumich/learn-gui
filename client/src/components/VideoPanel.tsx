import { useEffect, useMemo, useRef } from "react";

import { useWebRTC } from "../hooks/useWebRTC";

export default function VideoPanel() {
  const { stream, connectionState, connect, disconnect } = useWebRTC();
  const videoRef = useRef<HTMLVideoElement | null>(null);

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

  useEffect(() => {
    const video = videoRef.current;
    if (!video) {
      return;
    }
    if (stream) {
      video.srcObject = stream;
    } else {
      video.srcObject = null;
    }
  }, [stream]);

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
        <div className={`media-placeholder ${stream ? "has-video" : ""}`}>
          <video
            ref={videoRef}
            className="video-stream"
            autoPlay
            playsInline
            muted
          />
          {!stream && (
            <>
              <div className="placeholder-label">Video stream</div>
              <div className="placeholder-meta">{statusText}</div>
            </>
          )}
          {stream && <div className="stream-status">{statusText}</div>}
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
