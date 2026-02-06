export default function VideoPanel() {
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
        <div className="media-placeholder">
          <div className="placeholder-label">Video stream</div>
          <div className="placeholder-meta">No peer connection</div>
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
