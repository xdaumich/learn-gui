import { useState } from "react";

const RERUN_WEB_PORT = 9090;
const RERUN_GRPC_PORT = 9876;
const RERUN_WEB_URL = `http://localhost:${RERUN_WEB_PORT}?url=rerun%2Bhttp://localhost:${RERUN_GRPC_PORT}/proxy`;

export default function RerunPanel() {
  const [loaded, setLoaded] = useState(false);

  return (
    <section className="panel rerun-panel">
      <div className="panel-header">
        <div>
          <h2>Trajectory + 3D Model</h2>
          <p className="panel-subtitle">Rerun split view</p>
        </div>
        <span className="panel-chip">rerun</span>
      </div>
      <div className="panel-body">
        <div className="media-placeholder is-rerun">
          {!loaded && (
            <div className="placeholder-overlay">
              <div className="placeholder-label">Rerun Split View</div>
              <div className="placeholder-meta">Connecting to {RERUN_WEB_URL} …</div>
            </div>
          )}
          <iframe
            src={RERUN_WEB_URL}
            title="Rerun Web Viewer"
            onLoad={() => setLoaded(true)}
            className="rerun-iframe"
            style={{ opacity: loaded ? 1 : 0 }}
            allow="fullscreen"
          />
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
