import { useLayout } from "../contexts/LayoutContext";

export default function FloatingDot() {
  const { toggleZen } = useLayout();

  return (
    <button
      className="floating-dot"
      onClick={toggleZen}
      title="V: Disconnected  R: Idle  00:00:00 — Click or press Z for controls"
      type="button"
    >
      <span className="dot-indicator" />
      <span className="dot-label">Live</span>
    </button>
  );
}
