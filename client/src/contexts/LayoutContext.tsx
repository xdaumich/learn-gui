import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";

export type DisplayMode = "zen" | "compact" | "focus";
export type FocusTarget = "camera" | "rerun" | null;

interface LayoutContextValue {
  mode: DisplayMode;
  focusTarget: FocusTarget;
  splitRatio: number;
  setMode: (mode: DisplayMode) => void;
  focusPanel: (target: "camera" | "rerun") => void;
  exitFocus: () => void;
  setSplitRatio: (ratio: number) => void;
}

const LayoutContext = createContext<LayoutContextValue | null>(null);

export function useLayout(): LayoutContextValue {
  const ctx = useContext(LayoutContext);
  if (!ctx) throw new Error("useLayout must be used within LayoutProvider");
  return ctx;
}

const SPLIT_KEY = "telemetry-split-ratio";
const SPLIT_MIN = 0.15;
const SPLIT_MAX = 0.7;
export const DEFAULT_SPLIT = 0.35;

function clampSplitRatio(value: number): number {
  return Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, value));
}

function loadSplit(): number {
  try {
    const stored = localStorage.getItem(SPLIT_KEY);
    if (stored) {
      const val = parseFloat(stored);
      if (val >= SPLIT_MIN && val <= SPLIT_MAX) return val;
    }
  } catch {
    /* ignore */
  }
  return DEFAULT_SPLIT;
}

export function LayoutProvider({ children }: { children: ReactNode }): JSX.Element {
  const [mode, setModeRaw] = useState<DisplayMode>("zen");
  const [focusTarget, setFocusTarget] = useState<FocusTarget>(null);
  const [splitRatio, setSplitRatioRaw] = useState(loadSplit);

  const setMode = useCallback((m: DisplayMode) => {
    setModeRaw(m);
    if (m !== "focus") setFocusTarget(null);
  }, []);

  const focusPanel = useCallback((target: "camera" | "rerun") => {
    setModeRaw("focus");
    setFocusTarget(target);
  }, []);

  const exitFocus = useCallback(() => {
    setModeRaw("compact");
    setFocusTarget(null);
  }, []);

  const setSplitRatio = useCallback((ratio: number) => {
    const clamped = clampSplitRatio(ratio);
    setSplitRatioRaw(clamped);
    try {
      localStorage.setItem(SPLIT_KEY, String(clamped));
    } catch {
      /* ignore */
    }
  }, []);

  // Keyboard shortcuts — every key works from every mode
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const el = e.target as HTMLElement;
      if (
        el?.tagName === "INPUT" ||
        el?.tagName === "TEXTAREA" ||
        el?.isContentEditable
      )
        return;

      switch (e.key.toLowerCase()) {
        case "z":
          e.preventDefault();
          // Z always goes to zen, unless already zen → compact
          if (mode === "zen") setMode("compact");
          else setMode("zen");
          break;
        case "f":
          e.preventDefault();
          // F toggles focus on rerun from any mode
          if (mode === "focus" && focusTarget === "rerun") exitFocus();
          else focusPanel("rerun");
          break;
        case "escape":
          // Esc goes one level back: focus → compact → zen
          if (mode === "focus") exitFocus();
          else if (mode === "compact") setMode("zen");
          break;
        case "1":
          e.preventDefault();
          // 1 toggles focus on camera from any mode
          if (mode === "focus" && focusTarget === "camera") exitFocus();
          else focusPanel("camera");
          break;
        case "2":
          e.preventDefault();
          // 2 toggles focus on rerun from any mode
          if (mode === "focus" && focusTarget === "rerun") exitFocus();
          else focusPanel("rerun");
          break;
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [mode, focusTarget, focusPanel, exitFocus, setMode]);

  return (
    <LayoutContext.Provider
      value={{
        mode,
        focusTarget,
        splitRatio,
        setMode,
        focusPanel,
        exitFocus,
        setSplitRatio,
      }}
    >
      {children}
    </LayoutContext.Provider>
  );
}
