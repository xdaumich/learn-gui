import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { LayoutProvider } from "../../client/src/contexts/LayoutContext";
import VideoPanel from "../../client/src/components/VideoPanel";

const connectMock = vi.fn();
const disconnectMock = vi.fn();
const webRtcState = {
  streams: [
    { id: "stream-1", stream: {} as MediaStream },
    { id: "stream-2", stream: {} as MediaStream },
  ],
  connectionState: "connected" as const,
  expectedCameraCount: 2 as number | null,
  partialLive: false,
  connect: connectMock,
  disconnect: disconnectMock,
};

vi.mock("../../client/src/hooks/useWebRTC", () => ({
  useWebRTC: () => webRtcState,
}));

describe("VideoPanel", () => {
  beforeEach(() => {
    connectMock.mockReset();
    disconnectMock.mockReset();
  });

  test("starts WebRTC and shows connection status", async () => {
    webRtcState.partialLive = false;
    webRtcState.expectedCameraCount = 2;
    webRtcState.streams = [
      { id: "stream-1", stream: {} as MediaStream },
      { id: "stream-2", stream: {} as MediaStream },
    ];

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

  test("shows camera error banner when expected streams are missing", async () => {
    webRtcState.partialLive = true;
    webRtcState.expectedCameraCount = 3;
    webRtcState.streams = [{ id: "stream-1", stream: {} as MediaStream }];

    render(
      <LayoutProvider>
        <VideoPanel />
      </LayoutProvider>,
    );

    await waitFor(() => {
      expect(connectMock).toHaveBeenCalled();
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Camera stream error: 1/3 live (2 missing)",
    );
  });
});
