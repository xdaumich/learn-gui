import { useCallback, useRef } from "react";
import { useLayout, DEFAULT_SPLIT } from "../contexts/LayoutContext";

export default function ResizeHandle() {
  const { setSplitRatio } = useLayout();
  const dragging = useRef(false);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      dragging.current = true;
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    [],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragging.current) return;
      const contentArea = (e.target as HTMLElement).parentElement;
      if (!contentArea) return;
      const rect = contentArea.getBoundingClientRect();
      const ratio = (e.clientY - rect.top) / rect.height;
      setSplitRatio(ratio);
    },
    [setSplitRatio],
  );

  const onPointerUp = useCallback(() => {
    dragging.current = false;
  }, []);

  const onDoubleClick = useCallback(() => {
    setSplitRatio(DEFAULT_SPLIT);
  }, [setSplitRatio]);

  return (
    <div
      className="resize-handle"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onDoubleClick={onDoubleClick}
    />
  );
}
