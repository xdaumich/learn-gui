import "./App.css";

function TopBar() {
  return (
    <header className="top-bar">
      <div className="brand">
        <span className="brand-mark" />
        Telemetry Console
      </div>
      <div className="control-group">
        <button className="control-button" type="button">
          Connect
        </button>
        <button className="control-button" type="button">
          Record
        </button>
        <button className="control-button" type="button">
          Pause
        </button>
        <button className="control-button is-live" type="button">
          Live
        </button>
      </div>
      <div className="status-group">
        <span className="status-pill">Video: Disconnected</span>
        <span className="status-pill">Rerun: Idle</span>
        <span className="status-pill">Sync: --</span>
      </div>
    </header>
  );
}

function VideoPanel() {
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

function RerunPanel() {
  return (
    <section className="panel rerun-panel">
      <div className="panel-header">
        <div>
          <h2>Rerun Viewer</h2>
          <p className="panel-subtitle">Trajectory, pose, and point cloud</p>
        </div>
        <span className="panel-chip">iframe</span>
      </div>
      <div className="panel-body">
        <div className="media-placeholder is-rerun">
          <div className="placeholder-label">Rerun Web Viewer</div>
          <div className="placeholder-meta">Waiting for server URL</div>
        </div>
        <div className="panel-metrics">
          <div className="metric">
            <span className="metric-label">Timeline</span>
            <span className="metric-value">Wall time</span>
          </div>
          <div className="metric">
            <span className="metric-label">Data Rate</span>
            <span className="metric-value">-- msg/s</span>
          </div>
          <div className="metric">
            <span className="metric-label">Entities</span>
            <span className="metric-value">--</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function TimelineBar() {
  return (
    <footer className="timeline-bar">
      <div className="timeline-title">Timeline</div>
      <div className="timeline-track">
        <div className="track-fill" />
        <div className="track-thumb" />
      </div>
      <div className="timeline-meta">
        <span>00:00:00</span>
        <span className="divider" />
        <span>Live mode</span>
      </div>
    </footer>
  );
}

function App() {
  return (
    <div className="app">
      <TopBar />
      <main className="main-grid">
        <VideoPanel />
        <RerunPanel />
      </main>
      <TimelineBar />
    </div>
  );
}

export default App;
