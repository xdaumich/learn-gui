import { useState } from "react";
import { useLayout } from "../contexts/LayoutContext";
import { RERUN_WEB_URL } from "../config";
import CompactHeader from "./CompactHeader";

const RERUN_PANEL_PLACEHOLDER_METRICS: [string, string, string] = ["Wall time", "-- msg/s", "--"];

export default function RerunPanel() {
  const { isZen } = useLayout();
  const [loaded, setLoaded] = useState(false);

  return (
    <section className={`rerun-panel ${isZen ? "panel--zen" : "panel"}`}>
      {!isZen && (
        <CompactHeader
          chip="RERUN"
          chipVariant="rerun"
          metrics={RERUN_PANEL_PLACEHOLDER_METRICS}
          focusTarget="rerun"
          focusKey="2"
        />
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
