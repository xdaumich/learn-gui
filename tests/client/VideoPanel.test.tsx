import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { LayoutProvider } from "../../client/src/contexts/LayoutContext";
import VideoPanel from "../../client/src/components/VideoPanel";

const connectMock = vi.fn();
const disconnectMock = vi.fn();

vi.mock("../../client/src/hooks/useWebRTC", () => ({
  useWebRTC: () => ({
    streams: [
      { id: "stream-1", stream: {} },
      { id: "stream-2", stream: {} },
    ],
    connectionState: "connected",
    connect: connectMock,
    disconnect: disconnectMock,
  }),
}));

describe("VideoPanel", () => {
  test("starts WebRTC and shows connection status", async () => {
    render(
      <LayoutProvider>
        <VideoPanel />
      </LayoutProvider>,
    );

    await waitFor(() => {
      expect(connectMock).toHaveBeenCalledTimes(1);
    });

    // In zen mode (default), stream status is still visible
    expect(screen.getByText(/live/i)).toBeInTheDocument();
    expect(screen.getAllByTestId("camera-stream")).toHaveLength(2);
  });
});
