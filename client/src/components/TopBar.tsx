import { useState, useCallback, useRef, useEffect } from "react";
import { useLayout } from "../contexts/LayoutContext";
import { useRecording } from "../hooks/useRecording";
import { TOPBAR_HOVER_DELAY_MS } from "../config";
import ModeSwitcher from "./ModeSwitcher";

const RECORDING_STATUS_LABELS: Record<string, string> = {
  recording: "Recording",
  starting: "Starting",
  stopping: "Stopping",
  error: "Error",
  idle: "Idle",
};

export default function TopBar() {
  const { isZen } = useLayout();
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
    leaveTimer.current = setTimeout(() => setHovered(false), TOPBAR_HOVER_DELAY_MS);
  }, [clearLeaveTimer]);

  const handleBarEnter = useCallback(() => {
    clearLeaveTimer();
  }, [clearLeaveTimer]);

  useEffect(() => clearLeaveTimer, [clearLeaveTimer]);

  const visible = !isZen || hovered;
  const isRecording = phase === "recording";
  const isWorking = phase === "starting" || phase === "stopping";
  const recordingLabel = isRecording ? "Stop" : "Rec";
  const recordingStatus = RECORDING_STATUS_LABELS[phase] ?? "Idle";

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
        </div>
        <div className="status-group">
          <span className="status-text">Rec: {recordingStatus}</span>
          {runId && <span className="status-text">Run: {runId}</span>}
          <ModeSwitcher />
        </div>
      </header>
    </>
  );
}
