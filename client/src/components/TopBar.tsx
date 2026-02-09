import { useState, useCallback, useRef, useEffect } from "react";
import { useLayout } from "../contexts/LayoutContext";
import { useRecording } from "../hooks/useRecording";
import ModeSwitcher from "./ModeSwitcher";

export default function TopBar() {
  const { mode } = useLayout();
  const isZen = mode === "zen";
  const { phase, runId, toggle: toggleRecording } = useRecording();
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
  const isRecording = phase === "recording";
  const isWorking = phase === "starting" || phase === "stopping";
  const recordingLabel = isRecording ? "Stop" : "Rec";
  const recordingStatus =
    phase === "recording"
      ? "Recording"
      : phase === "starting"
        ? "Starting"
        : phase === "stopping"
          ? "Stopping"
          : phase === "error"
            ? "Error"
            : "Idle";

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
        className={[
          "top-bar",
          isZen && "top-bar--zen",
          visible && "top-bar--visible",
        ]
          .filter(Boolean)
          .join(" ")}
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
          <button
            className={["control-button", isRecording && "is-recording"]
              .filter(Boolean)
              .join(" ")}
            type="button"
            onClick={toggleRecording}
            disabled={isWorking}
            aria-pressed={isRecording}
            title={runId ? `Recording ${runId}` : "Start recording"}
          >
            {recordingLabel}
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
          <span className="status-text">R: {recordingStatus}</span>
          <span className="status-text">S: --</span>
          <ModeSwitcher />
        </div>
      </header>
    </>
  );
}
