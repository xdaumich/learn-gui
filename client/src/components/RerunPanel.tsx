export default function RerunPanel() {
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
