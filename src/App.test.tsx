import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import App from "./App";

describe("App layout", () => {
  test("renders top controls and panel placeholders", () => {
    render(<App />);

    expect(screen.getByRole("button", { name: /connect/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /record/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /pause/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /live/i })).toBeVisible();
    expect(screen.getByText(/live camera/i)).toBeVisible();
    expect(screen.getByText(/rerun viewer/i)).toBeVisible();
    expect(screen.getAllByText(/timeline/i).length).toBeGreaterThan(0);
  });
});
