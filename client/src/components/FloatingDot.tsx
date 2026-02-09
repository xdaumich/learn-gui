import { useState } from "react";
import { useLayout } from "../contexts/LayoutContext";
import ModeSwitcher from "./ModeSwitcher";

export default function FloatingDot() {
  const { setMode } = useLayout();
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`floating-dot-container${expanded ? " floating-dot-container--expanded" : ""}`}
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => setExpanded(false)}
    >
      {expanded ? (
        <ModeSwitcher />
      ) : (
        <button
          className="floating-dot"
          onClick={() => setMode("compact")}
          title="V: Disconnected  R: Idle  00:00:00 — Click or press Z for controls"
          type="button"
        >
          <span className="dot-indicator" />
          <span className="dot-label">Live</span>
        </button>
      )}
    </div>
  );
}
