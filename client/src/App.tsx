import "./App.css";
import { LayoutProvider, useLayout } from "./contexts/LayoutContext";
import TopBar from "./components/TopBar";
import VideoPanel from "./components/VideoPanel";
import RerunPanel from "./components/RerunPanel";
import FloatingDot from "./components/FloatingDot";
import ResizeHandle from "./components/ResizeHandle";

function AppInner() {
  const { mode, isZen, isFocus, focusTarget, splitRatio } = useLayout();

  const showCamera = !isFocus || focusTarget === "camera";
  const showRerun = !isFocus || focusTarget === "rerun";

  return (
    <div className={`app mode-${mode}`}>
      <TopBar />
      <main
        className="content-area"
        style={{ "--split": splitRatio } as React.CSSProperties}
      >
        {showCamera && <VideoPanel />}
        {showCamera && showRerun && <ResizeHandle />}
        {showRerun && <RerunPanel />}
      </main>
      {isZen && <FloatingDot />}
    </div>
  );
}

export default function App() {
  return (
    <LayoutProvider>
      <AppInner />
    </LayoutProvider>
  );
}
