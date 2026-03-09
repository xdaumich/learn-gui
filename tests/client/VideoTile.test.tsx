import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import VideoPanel from "../../client/src/components/VideoPanel";

// ---------------------------------------------------------------------------
// Shared mock state
// ---------------------------------------------------------------------------

const connectMock = vi.fn();
const disconnectMock = vi.fn();
const mjpegState = {
  cameras: [] as { name: string; url: string }[],
  connectionState: "connected" as string,
  expectedCameraCount: 1 as number | null,
  partialLive: false,
  connect: connectMock,
  disconnect: disconnectMock,
};

vi.mock("../../client/src/hooks/useMJPEG", () => ({
  useMJPEG: () => mjpegState,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderSingleTile(url?: string) {
  const u = url ?? "http://localhost:8000/stream/left";
  mjpegState.cameras = [{ name: "left", url: u }];
  render(<VideoPanel />);
}

function getImg(): HTMLImageElement {
  return screen.getAllByTestId("camera-stream")[0] as HTMLImageElement;
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe("MJPEGTile", () => {
  beforeEach(() => {
    connectMock.mockReset();
    disconnectMock.mockReset();
    mjpegState.connectionState = "connected";
    mjpegState.expectedCameraCount = 1;
    mjpegState.partialLive = false;
  });

  afterEach(() => {
    cleanup();
  });

  test("renders img with correct src", () => {
    renderSingleTile("http://localhost:8000/stream/left");
    const img = getImg();
    expect(img.tagName).toBe("IMG");
    expect(img.getAttribute("src")).toBe("http://localhost:8000/stream/left");
  });

  test("img has alt text with camera label", () => {
    renderSingleTile();
    const img = getImg();
    expect(img.getAttribute("alt")).toBe("Left camera");
  });

  test("left camera has rotation class", () => {
    mjpegState.cameras = [{ name: "left", url: "http://localhost:8000/stream/left" }];
    render(<VideoPanel />);
    const img = getImg();
    expect(img.className).toContain("video-stream--rotate-left");
  });

  test("center camera has no rotation class", () => {
    mjpegState.cameras = [{ name: "center", url: "http://localhost:8000/stream/center" }];
    render(<VideoPanel />);
    const img = getImg();
    expect(img.className).not.toContain("rotate-left");
    expect(img.className).not.toContain("rotate-right");
  });
});
