import { useLayout } from "../contexts/LayoutContext";

type CompactHeaderProps = {
  chip: string;
  chipVariant?: "rerun";
  label?: string;
  metrics: [string, string, string];
  focusTarget: "camera" | "rerun";
  focusKey: string;
};

export default function CompactHeader({
  chip,
  chipVariant,
  label,
  metrics,
  focusTarget,
  focusKey,
}: CompactHeaderProps): React.JSX.Element {
  const { mode, focusTarget: activeFocus, focusPanel, exitFocus } = useLayout();
  const isFocused = mode === "focus" && activeFocus === focusTarget;

  return (
    <div className="compact-header">
      <div className="compact-header__left">
        <span
          className={`compact-chip${chipVariant ? ` compact-chip--${chipVariant}` : ""}`}
        >
          {chip}
        </span>
        {label && <span className="compact-label">{label}</span>}
      </div>
      <div className="compact-header__metrics">
        <span>{metrics[0]}</span>
        <span className="metric-divider">|</span>
        <span>{metrics[1]}</span>
        <span className="metric-divider">|</span>
        <span>{metrics[2]}</span>
      </div>
      <button
        className="maximize-btn"
        onClick={() => (isFocused ? exitFocus() : focusPanel(focusTarget))}
        type="button"
        title={isFocused ? "Restore (Esc)" : `Focus (${focusKey})`}
      >
        {isFocused ? "\u2921" : "\u2922"}
      </button>
    </div>
  );
}
