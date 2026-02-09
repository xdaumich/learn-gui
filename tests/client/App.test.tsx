import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import App from "../../client/src/App";

describe("App layout", () => {
  test("starts in zen mode and shows controls in compact mode", () => {
    render(<App />);

    // Zen mode: control buttons exist in DOM (topbar rendered but off-screen)
    expect(
      screen.getByRole("button", { name: /connect/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /pause/i }),
    ).toBeInTheDocument();

    // Content placeholders visible in zen
    expect(screen.getByText(/video stream/i)).toBeInTheDocument();

    // Floating dot visible in zen mode
    expect(screen.getByTitle(/click or press z/i)).toBeInTheDocument();

    // Switch to compact mode via Z key
    fireEvent.keyDown(window, { key: "z" });

    // Compact mode: panel header chips visible
    expect(screen.getByText("CAM")).toBeInTheDocument();
    expect(screen.getByText("RERUN")).toBeInTheDocument();
  });
});
