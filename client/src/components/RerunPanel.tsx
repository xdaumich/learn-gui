import { useState } from "react";
import { useLayout } from "../contexts/LayoutContext";

const RERUN_WEB_PORT = 9090;
const RERUN_GRPC_PORT = 9876;
const RERUN_WEB_URL = `http://localhost:${RERUN_WEB_PORT}?url=rerun%2Bhttp://localhost:${RERUN_GRPC_PORT}/proxy`;

export default function RerunPanel() {
  const { mode, focusPanel, exitFocus, focusTarget } = useLayout();
  const isZen = mode === "zen";
  const isFocused = mode === "focus" && focusTarget === "rerun";
  const [loaded, setLoaded] = useState(false);

  return (
    <section className={`rerun-panel ${isZen ? "panel--zen" : "panel"}`}>
      {!isZen && (
        <div className="compact-header">
          <div className="compact-header__left">
            <span className="compact-chip compact-chip--rerun">RERUN</span>
          </div>
          <div className="compact-header__metrics">
            <span>Wall time</span>
            <span className="metric-divider">|</span>
            <span>-- msg/s</span>
            <span className="metric-divider">|</span>
            <span>--</span>
          </div>
          <button
            className="maximize-btn"
            onClick={() => (isFocused ? exitFocus() : focusPanel("rerun"))}
            type="button"
            title={isFocused ? "Restore (Esc)" : "Focus (2)"}
          >
            {isFocused ? "\u2921" : "\u2922"}
          </button>
        </div>
      )}
      <div className="media-placeholder is-rerun">
        {!loaded && (
          <div className="placeholder-overlay">
            <div className="placeholder-label">Rerun Split View</div>
            <div className="placeholder-meta">Connecting…</div>
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
    </section>
  );
}
