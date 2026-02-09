import { useState, useCallback, useRef, useEffect } from "react";
import { useLayout } from "../contexts/LayoutContext";

export default function TopBar() {
  const { mode, toggleZen } = useLayout();
  const isZen = mode === "zen";
  const [hovered, setHovered] = useState(false);
  const leaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearLeaveTimer = useCallback(() => {
    if (leaveTimer.current) {
      clearTimeout(leaveTimer.current);
      leaveTimer.current = null;
    }
  }, []);

  const handleZoneEnter = useCallback(() => {
    clearLeaveTimer();
    setHovered(true);
  }, [clearLeaveTimer]);

  const handleLeave = useCallback(() => {
    clearLeaveTimer();
    leaveTimer.current = setTimeout(() => setHovered(false), 400);
  }, [clearLeaveTimer]);

  const handleBarEnter = useCallback(() => {
    clearLeaveTimer();
  }, [clearLeaveTimer]);

  useEffect(() => clearLeaveTimer, [clearLeaveTimer]);

  const visible = !isZen || hovered;

  return (
    <>
      {isZen && (
        <div
          className="hover-zone"
          onMouseEnter={handleZoneEnter}
          onMouseLeave={handleLeave}
        />
      )}
      <header
        className={`top-bar ${isZen ? "top-bar--zen" : ""} ${visible ? "top-bar--visible" : ""}`}
        onMouseEnter={handleBarEnter}
        onMouseLeave={handleLeave}
      >
        <div className="brand">
          <span className="brand-mark" />
          Telemetry
        </div>
        <div className="control-group">
          <button className="control-button" type="button">
            Connect
          </button>
          <button className="control-button" type="button">
            Rec
          </button>
          <button className="control-button" type="button">
            Pause
          </button>
          <button className="control-button is-live" type="button">
            Live
          </button>
        </div>
        <div className="status-group">
          <span className="status-text">V: --</span>
          <span className="status-text">R: Idle</span>
          <span className="status-text">S: --</span>
          {!isZen && (
            <button
              className="zen-toggle"
              onClick={toggleZen}
              type="button"
              title="Zen mode (Z)"
            >
              Z
            </button>
          )}
        </div>
      </header>
    </>
  );
}
