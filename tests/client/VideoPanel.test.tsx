import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import VideoPanel from "../../client/src/components/VideoPanel";

const connectMock = vi.fn();
const disconnectMock = vi.fn();

vi.mock("../../client/src/hooks/useWebRTC", () => ({
  useWebRTC: () => ({
    stream: null,
    connectionState: "connecting",
    connect: connectMock,
    disconnect: disconnectMock,
  }),
}));

describe("VideoPanel", () => {
  test("starts WebRTC and shows connection status", async () => {
    render(<VideoPanel />);

    await waitFor(() => {
      expect(connectMock).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(/video stream/i)).toBeVisible();
    expect(screen.getByText(/connecting/i)).toBeVisible();
  });
});
