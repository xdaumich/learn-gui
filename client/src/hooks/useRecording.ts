import { useCallback, useEffect, useState } from "react";
import { API_BASE_URL } from "../config";

export type RecordingPhase = "idle" | "starting" | "recording" | "stopping" | "error";

type RecordingPayload = {
  active: boolean;
  run_id?: string | null;
};

const RECORDING_STATUS_URL = `${API_BASE_URL}/recording/status`;
const RECORDING_START_URL = `${API_BASE_URL}/recording/start`;
const RECORDING_STOP_URL = `${API_BASE_URL}/recording/stop`;

function normalizePhase(active: boolean): RecordingPhase {
  return active ? "recording" : "idle";
}

export function useRecording() {
  const [phase, setPhase] = useState<RecordingPhase>("idle");
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const applyPayload = useCallback((payload: RecordingPayload) => {
    setRunId(payload.run_id ?? null);
    setPhase(normalizePhase(Boolean(payload.active)));
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch(RECORDING_STATUS_URL);
      if (!response.ok) {
        throw new Error(`Status request failed (${response.status})`);
      }
      const payload = (await response.json()) as RecordingPayload;
      applyPayload(payload);
      setError(null);
    } catch (err) {
      setPhase("error");
      setError(err instanceof Error ? err.message : "Failed to fetch status");
    }
  }, [applyPayload]);

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  const start = useCallback(async () => {
    if (phase === "recording" || phase === "starting") {
      return;
    }
    setPhase("starting");
    setError(null);
    try {
      const response = await fetch(RECORDING_START_URL, { method: "POST" });
      if (!response.ok) {
        throw new Error(`Start request failed (${response.status})`);
      }
      const payload = (await response.json()) as RecordingPayload;
      applyPayload(payload);
    } catch (err) {
      setPhase("error");
      setError(err instanceof Error ? err.message : "Failed to start recording");
    }
  }, [applyPayload, phase]);

  const stop = useCallback(async () => {
    if (phase === "idle" || phase === "stopping") {
      return;
    }
    setPhase("stopping");
    setError(null);
    try {
      const response = await fetch(RECORDING_STOP_URL, { method: "POST" });
      if (!response.ok) {
        throw new Error(`Stop request failed (${response.status})`);
      }
      const payload = (await response.json()) as RecordingPayload;
      applyPayload(payload);
    } catch (err) {
      setPhase("error");
      setError(err instanceof Error ? err.message : "Failed to stop recording");
    }
  }, [applyPayload, phase]);

  const toggle = useCallback(() => {
    if (phase === "recording") {
      void stop();
    } else {
      void start();
    }
  }, [phase, start, stop]);

  return {
    phase,
    runId,
    error,
    start,
    stop,
    toggle,
  };
}
