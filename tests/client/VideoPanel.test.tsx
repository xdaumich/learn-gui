import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import VideoPanel from "../../client/src/components/VideoPanel";

const connectMock = vi.fn();
const disconnectMock = vi.fn();
const mjpegState = {
  cameras: [
    { name: "left", url: "http://localhost:8000/stream/left" },
    { name: "center", url: "http://localhost:8000/stream/center" },
    { name: "right", url: "http://localhost:8000/stream/right" },
  ],
  connectionState: "connected" as string,
  expectedCameraCount: 3 as number | null,
  partialLive: false,
  connect: connectMock,
  disconnect: disconnectMock,
};

vi.mock("../../client/src/hooks/useMJPEG", () => ({
  useMJPEG: () => mjpegState,
}));

describe("VideoPanel", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    connectMock.mockReset();
    disconnectMock.mockReset();
    mjpegState.partialLive = false;
    mjpegState.expectedCameraCount = 3;
    mjpegState.connectionState = "connected";
    mjpegState.cameras = [
      { name: "left", url: "http://localhost:8000/stream/left" },
      { name: "center", url: "http://localhost:8000/stream/center" },
      { name: "right", url: "http://localhost:8000/stream/right" },
    ];
  });

  test("renders three camera tiles for left/center/right", async () => {
    render(<VideoPanel />);

    await waitFor(() => {
      expect(connectMock).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText(/live/i)).toBeInTheDocument();

    const tiles = screen.getAllByTestId("camera-stream");
    expect(tiles).toHaveLength(3);

    expect(screen.getByText("Left")).toBeInTheDocument();
    expect(screen.getByText("Center")).toBeInTheDocument();
    expect(screen.getByText("Right")).toBeInTheDocument();
  });

  test("shows camera error banner when expected streams are missing", async () => {
    mjpegState.partialLive = true;
    mjpegState.expectedCameraCount = 3;
    mjpegState.cameras = [{ name: "left", url: "http://localhost:8000/stream/left" }];

    render(<VideoPanel />);

    await waitFor(() => {
      expect(connectMock).toHaveBeenCalled();
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Camera stream error: 1/3 live (2 missing)",
    );
  });

  test("no error banner when all three cameras are streaming", async () => {
    render(<VideoPanel />);

    await waitFor(() => {
      expect(connectMock).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getAllByTestId("camera-stream")).toHaveLength(3);
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("each img element has correct src URL", async () => {
    render(<VideoPanel />);

    await waitFor(() => {
      expect(connectMock).toHaveBeenCalled();
    });

    const imgs = screen.getAllByTestId("camera-stream") as HTMLImageElement[];
    expect(imgs).toHaveLength(3);

    const srcs = imgs.map((img) => img.getAttribute("src"));
    expect(srcs).toContain("http://localhost:8000/stream/left");
    expect(srcs).toContain("http://localhost:8000/stream/center");
    expect(srcs).toContain("http://localhost:8000/stream/right");
  });

  test("camera tiles display ordered labels left/center/right", async () => {
    mjpegState.cameras = [
      { name: "right", url: "http://localhost:8000/stream/right" },
      { name: "left", url: "http://localhost:8000/stream/left" },
      { name: "center", url: "http://localhost:8000/stream/center" },
    ];

    render(<VideoPanel />);

    await waitFor(() => {
      expect(screen.getAllByTestId("camera-stream")).toHaveLength(3);
    });

    const labels = screen.getAllByTestId("camera-stream").map((img) => {
      const tile = img.closest(".camera-tile");
      return tile?.querySelector(".camera-label")?.textContent;
    });
    expect(labels).toEqual(["Left", "Center", "Right"]);
  });
});
