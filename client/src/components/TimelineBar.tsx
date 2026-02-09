export default function TimelineBar() {
  return (
    <footer className="timeline-bar">
      <div className="timeline-track">
        <div className="track-fill" />
        <div className="track-thumb" />
      </div>
      <div className="timeline-meta">
        <span>00:00:00</span>
        <span className="divider" />
        <span>Live</span>
      </div>
    </footer>
  );
}
