import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import App from "../../client/src/App";

describe("App layout", () => {
  test("renders camera-only layout with video stream placeholder", () => {
    render(<App />);

    // Content placeholder visible (no cameras connected in test)
    expect(screen.getByText(/video stream/i)).toBeInTheDocument();
  });
});
