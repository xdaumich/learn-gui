export default function TopBar() {
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
