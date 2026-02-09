import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";

type DisplayMode = "zen" | "compact" | "focus";
type FocusTarget = "camera" | "rerun" | null;

interface LayoutContextValue {
  mode: DisplayMode;
  focusTarget: FocusTarget;
  splitRatio: number;
  setMode: (mode: DisplayMode) => void;
  toggleZen: () => void;
  focusPanel: (target: "camera" | "rerun") => void;
  exitFocus: () => void;
  setSplitRatio: (ratio: number) => void;
}

const LayoutContext = createContext<LayoutContextValue | null>(null);

export function useLayout() {
  const ctx = useContext(LayoutContext);
  if (!ctx) throw new Error("useLayout must be used within LayoutProvider");
  return ctx;
}

const SPLIT_KEY = "telemetry-split-ratio";
const DEFAULT_SPLIT = 0.35;

function loadSplit(): number {
  try {
    const stored = localStorage.getItem(SPLIT_KEY);
    if (stored) {
      const val = parseFloat(stored);
      if (val >= 0.15 && val <= 0.7) return val;
    }
  } catch {
    /* ignore */
  }
  return DEFAULT_SPLIT;
}

export function LayoutProvider({ children }: { children: ReactNode }) {
  const [mode, setModeRaw] = useState<DisplayMode>("zen");
  const [focusTarget, setFocusTarget] = useState<FocusTarget>(null);
  const [splitRatio, setSplitRatioRaw] = useState(loadSplit);

  const setMode = useCallback((m: DisplayMode) => {
    setModeRaw(m);
    if (m !== "focus") setFocusTarget(null);
  }, []);

  const toggleZen = useCallback(() => {
    setModeRaw((prev) => (prev === "zen" ? "compact" : "zen"));
    setFocusTarget(null);
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
    const clamped = Math.max(0.15, Math.min(0.7, ratio));
    setSplitRatioRaw(clamped);
    try {
      localStorage.setItem(SPLIT_KEY, String(clamped));
    } catch {
      /* ignore */
    }
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
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
          toggleZen();
          break;
        case "f":
          e.preventDefault();
          setModeRaw((prev) => {
            if (prev === "compact") {
              setFocusTarget("rerun");
              return "focus";
            }
            if (prev === "focus") {
              setFocusTarget(null);
              return "compact";
            }
            return prev;
          });
          break;
        case "escape":
          setModeRaw((prev) => {
            if (prev === "focus") {
              setFocusTarget(null);
              return "compact";
            }
            if (prev === "compact") return "zen";
            return prev;
          });
          break;
        case "1":
          setModeRaw((prev) => {
            if (prev === "compact") {
              setFocusTarget("camera");
              return "focus";
            }
            return prev;
          });
          break;
        case "2":
          setModeRaw((prev) => {
            if (prev === "compact") {
              setFocusTarget("rerun");
              return "focus";
            }
            return prev;
          });
          break;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toggleZen]);

  return (
    <LayoutContext.Provider
      value={{
        mode,
        focusTarget,
        splitRatio,
        setMode,
        toggleZen,
        focusPanel,
        exitFocus,
        setSplitRatio,
      }}
    >
      {children}
    </LayoutContext.Provider>
  );
}
