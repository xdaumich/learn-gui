import "./App.css";
import TopBar from "./components/TopBar";
import VideoPanel from "./components/VideoPanel";
import RerunPanel from "./components/RerunPanel";
import TimelineBar from "./components/TimelineBar";

export default function App() {
  return (
    <div className="app">
      <TopBar />
      <main className="main-grid">
        <VideoPanel />
        <RerunPanel />
      </main>
      <TimelineBar />
    </div>
  );
}
