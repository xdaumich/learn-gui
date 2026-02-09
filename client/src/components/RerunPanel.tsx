import { useState } from "react";
import { useLayout } from "../contexts/LayoutContext";
import CompactHeader from "./CompactHeader";

const RERUN_WEB_PORT = 9090;
const RERUN_GRPC_PORT = 9876;
const RERUN_WEB_URL = `http://localhost:${RERUN_WEB_PORT}?url=rerun%2Bhttp://localhost:${RERUN_GRPC_PORT}/proxy`;

export default function RerunPanel() {
  const { mode } = useLayout();
  const isZen = mode === "zen";
  const [loaded, setLoaded] = useState(false);

  return (
    <section className={`rerun-panel ${isZen ? "panel--zen" : "panel"}`}>
      {!isZen && (
        <CompactHeader
          chip="RERUN"
          chipVariant="rerun"
          metrics={["Wall time", "-- msg/s", "--"]}
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
