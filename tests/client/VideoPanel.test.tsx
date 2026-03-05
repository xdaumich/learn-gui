import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import VideoPanel from "../../client/src/components/VideoPanel";

function fakeStream(): MediaStream {
  const track = { readyState: "live", id: `track-${Math.random()}` } as MediaStreamTrack;
  return {
    getVideoTracks: () => [track],
    getAudioTracks: () => [],
    getTracks: () => [track],
  } as unknown as MediaStream;
}

const connectMock = vi.fn();
const disconnectMock = vi.fn();
const webRtcState = {
  streams: [
    { id: "left:stream-1", name: "left", stream: fakeStream() },
    { id: "center:stream-2", name: "center", stream: fakeStream() },
    { id: "right:stream-3", name: "right", stream: fakeStream() },
  ],
  connectionState: "connected" as const,
  expectedCameraCount: 3 as number | null,
  partialLive: false,
  connect: connectMock,
  disconnect: disconnectMock,
};

vi.mock("../../client/src/hooks/useWebRTC", () => ({
  useWebRTC: () => webRtcState,
}));

describe("VideoPanel", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    connectMock.mockReset();
    disconnectMock.mockReset();
    webRtcState.partialLive = false;
    webRtcState.expectedCameraCount = 3;
    webRtcState.connectionState = "connected";
    webRtcState.streams = [
      { id: "left:stream-1", name: "left", stream: fakeStream() },
      { id: "center:stream-2", name: "center", stream: fakeStream() },
      { id: "right:stream-3", name: "right", stream: fakeStream() },
    ];
  });

  test("renders three camera tiles for left/center/right", async () => {
    webRtcState.partialLive = false;
    webRtcState.expectedCameraCount = 3;
    webRtcState.streams = [
      { id: "left:stream-1", name: "left", stream: fakeStream() },
      { id: "center:stream-2", name: "center", stream: fakeStream() },
      { id: "right:stream-3", name: "right", stream: fakeStream() },
    ];

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
    webRtcState.partialLive = true;
    webRtcState.expectedCameraCount = 3;
    webRtcState.streams = [{ id: "left:stream-1", name: "left", stream: fakeStream() }];

    render(<VideoPanel />);

    await waitFor(() => {
      expect(connectMock).toHaveBeenCalled();
    });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Camera stream error: 1/3 live (2 missing)",
    );
  });

  test("no error banner when all three cameras are streaming", async () => {
    webRtcState.partialLive = false;
    webRtcState.expectedCameraCount = 3;
    webRtcState.streams = [
      { id: "left:stream-1", name: "left", stream: fakeStream() },
      { id: "center:stream-2", name: "center", stream: fakeStream() },
      { id: "right:stream-3", name: "right", stream: fakeStream() },
    ];

    render(<VideoPanel />);

    await waitFor(() => {
      expect(connectMock).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getAllByTestId("camera-stream")).toHaveLength(3);
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("each video element receives its srcObject stream", async () => {
    const streams = [
      { id: "left:s1", name: "left", stream: fakeStream() },
      { id: "center:s2", name: "center", stream: fakeStream() },
      { id: "right:s3", name: "right", stream: fakeStream() },
    ];
    webRtcState.streams = streams;

    render(<VideoPanel />);

    await waitFor(() => {
      expect(connectMock).toHaveBeenCalled();
    });

    const videos = screen.getAllByTestId("camera-stream") as HTMLVideoElement[];
    expect(videos).toHaveLength(3);

    for (const video of videos) {
      expect(video.srcObject).not.toBeNull();
      const src = video.srcObject as MediaStream;
      expect(typeof src.getVideoTracks).toBe("function");
      expect(src.getVideoTracks().length).toBeGreaterThan(0);
    }
  });

  test("calls play() on each video element when stream is attached", async () => {
    const playSpy = vi
      .spyOn(HTMLVideoElement.prototype, "play")
      .mockResolvedValue(undefined);

    render(<VideoPanel />);

    await waitFor(() => {
      expect(screen.getAllByTestId("camera-stream")).toHaveLength(3);
    });

    // play() must be called at least once per tile so video actually starts
    expect(playSpy.mock.calls.length).toBeGreaterThanOrEqual(3);
  });

  test("each video stream has a live-state video track", async () => {
    render(<VideoPanel />);

    await waitFor(() => {
      expect(connectMock).toHaveBeenCalled();
    });

    const videos = screen.getAllByTestId("camera-stream") as HTMLVideoElement[];
    expect(videos).toHaveLength(3);

    for (const video of videos) {
      const src = video.srcObject as MediaStream;
      expect(src).not.toBeNull();
      const tracks = src.getVideoTracks();
      expect(tracks.length).toBeGreaterThan(0);
      // track must be live — not ended or muted-out
      expect(tracks[0].readyState).toBe("live");
    }
  });

  test("video tiles display ordered labels center/left/right", async () => {
    webRtcState.streams = [
      { id: "right:s3", name: "right", stream: fakeStream() },
      { id: "left:s1", name: "left", stream: fakeStream() },
      { id: "center:s2", name: "center", stream: fakeStream() },
    ];

    render(<VideoPanel />);

    await waitFor(() => {
      expect(screen.getAllByTestId("camera-stream")).toHaveLength(3);
    });

    const labels = screen.getAllByTestId("camera-stream").map((video) => {
      const tile = video.closest(".camera-tile");
      return tile?.querySelector(".camera-label")?.textContent;
    });
    expect(labels).toEqual(["Center", "Left", "Right"]);
  });
});
