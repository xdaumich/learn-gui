import { useLayout, type DisplayMode } from "../contexts/LayoutContext";

const MODES: { id: DisplayMode; label: string; key: string }[] = [
  { id: "zen", label: "Zen", key: "Z" },
  { id: "compact", label: "Compact", key: "Z" },
  { id: "focus", label: "Focus", key: "F" },
];

export default function ModeSwitcher() {
  const { mode, setMode, focusPanel, focusTarget } = useLayout();

  const activeIndex = MODES.findIndex((m) => m.id === mode);

  function handleClick(target: DisplayMode) {
    if (target === "focus") {
      // Enter focus with last target or default to rerun
      focusPanel(focusTarget ?? "rerun");
    } else {
      setMode(target);
    }
  }

  return (
    <div className="mode-switcher" role="radiogroup" aria-label="Display mode">
      {/* Sliding highlight pill */}
      <span
        className="mode-switcher__indicator"
        style={{
          transform: `translateX(${activeIndex * 100}%)`,
        }}
      />
      {MODES.map((m) => (
        <button
          key={m.id}
          className={`mode-switcher__btn${mode === m.id ? " mode-switcher__btn--active" : ""}`}
          role="radio"
          aria-checked={mode === m.id}
          onClick={() => handleClick(m.id)}
          type="button"
          title={`${m.label} mode (${m.key})`}
        >
          <span className="mode-switcher__label">{m.label}</span>
          <kbd className="mode-switcher__kbd">{m.key}</kbd>
        </button>
      ))}
    </div>
  );
}
