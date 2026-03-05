import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import VideoPanel from "../../client/src/components/VideoPanel";

// ---------------------------------------------------------------------------
// Shared mock state (same pattern as VideoPanel.test.tsx)
// ---------------------------------------------------------------------------

function fakeStream(trackState: string = "live"): MediaStream {
  const track = { readyState: trackState, id: `track-${Math.random()}` } as MediaStreamTrack;
  return {
    getVideoTracks: () => [track],
    getAudioTracks: () => [],
    getTracks: () => [track],
  } as unknown as MediaStream;
}

const connectMock = vi.fn();
const disconnectMock = vi.fn();
const webRtcState = {
  streams: [] as { id: string; name: string; stream: MediaStream }[],
  connectionState: "connected" as string,
  expectedCameraCount: 1 as number | null,
  partialLive: false,
  connect: connectMock,
  disconnect: disconnectMock,
};

vi.mock("../../client/src/hooks/useWebRTC", () => ({
  useWebRTC: () => webRtcState,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Render a single VideoTile via VideoPanel with one stream. */
function renderSingleTile(stream?: MediaStream) {
  const s = stream ?? fakeStream();
  webRtcState.streams = [{ id: "left:s1", name: "left", stream: s }];
  render(<VideoPanel />);
}

/** Get the first video element. */
function getVideo(): HTMLVideoElement {
  return screen.getAllByTestId("camera-stream")[0] as HTMLVideoElement;
}

/** Prepare a video element for stall monitor testing.
 *  jsdom defaults: readyState=0, paused=true, currentTime=0.
 *  The stall monitor returns early if readyState < 2 or paused is true,
 *  so both must be overridden for stall accumulation to begin. */
function prepareVideoForStallMonitor(video: HTMLVideoElement) {
  Object.defineProperty(video, "readyState", { value: 2, configurable: true });
  Object.defineProperty(video, "paused", { value: false, configurable: true });
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe("VideoTile stall monitor", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Pre-advance past the 30 s recoverStalledStream cooldown.
    // lastRecoveryAtRef initializes to 0; at fake time 60_000 ms the
    // cooldown (30 000 ms) is always expired.
    vi.setSystemTime(new Date(60_000));

    connectMock.mockReset();
    disconnectMock.mockReset();
    webRtcState.connectionState = "connected";
    webRtcState.expectedCameraCount = 1;
    webRtcState.partialLive = false;
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  test("warmup blocks stall detection", () => {
    const stream = fakeStream();
    renderSingleTile(stream);
    const video = getVideo();
    prepareVideoForStallMonitor(video);

    // Advance 7 900 ms (within 8 000 ms warmup)
    vi.advanceTimersByTime(7_900);

    expect(disconnectMock).not.toHaveBeenCalled();
  });

  test("soft recovery fires at 7500 ms post-warmup", () => {
    const stream = fakeStream();
    renderSingleTile(stream);
    const video = getVideo();
    prepareVideoForStallMonitor(video);
    const playSpy = vi.spyOn(video, "play").mockReturnValue(Promise.resolve());

    // Advance past warmup (8000) + enough for stagnant to reach 7500
    // tick=2000: warmup ends after 8000ms, then stagnantMs accumulates each tick
    // After warmup: ticks at 10000, 12000, 14000 → stagnantMs = 2000, 4000, 6000
    // tick at 16000 → stagnantMs = 8000 ≥ 7500 → soft recovery fires
    // But first tick at 2000 sets lastTime=0 (currentTime 0 > -1+0.001 = TRUE)
    // Subsequent ticks: 0 > 0+0.001 = FALSE → stagnant begins at tick 4000
    // warmupUntil = start + 8000
    // Ticks during warmup (up to 8000): tick 2000 (sets lastTime=0), 4000, 6000, 8000 (stagnant but warmup skips)
    // Post-warmup ticks: 10000 (+2000 stagnant), 12000 (+2000=4000), 14000 (+2000=6000), 16000 (+2000=8000 ≥ 7500)
    // Total needed: 16000 ms → but we already advanced 0, so advance 14_000 from the render
    // Actually ticks start from setInterval creation, which is during mount.
    // Total advance: 14_000 ms should get to tick at 14_000 → stagnantMs=6000
    // Need 16_000 for stagnantMs=8000 ≥ 7500
    vi.advanceTimersByTime(16_000);

    // Soft recovery reassigns srcObject and calls play()
    expect(playSpy).toHaveBeenCalled();
    expect(disconnectMock).not.toHaveBeenCalled();
  });

  test("onStalled fires at 15000 ms post-warmup → disconnect", () => {
    const stream = fakeStream();
    renderSingleTile(stream);
    const video = getVideo();
    prepareVideoForStallMonitor(video);

    // Need stagnantMs ≥ 15_000 post-warmup
    // warmup = 8000, first tick sets lastTime=0, stagnant begins tick 4000
    // warmupUntil = start + 8000
    // post-warmup stagnant: 10000(+2000), 12000(+4000), 14000(+6000), 16000(+8000 → soft), 18000(+10000), 20000(+12000), 22000(+14000), 24000(+16000 ≥ 15000 → stall)
    // Wait: after soft recovery at 16000, triedSoftRecovery=true and stagnant continues accumulating
    // Actually soft recovery: stagnantMs stays (only resets triedSoftRecovery flag on time advance)
    // Re-reading code: soft recovery sets triedSoftRecovery=true and returns. stagnantMs is NOT reset.
    // Next ticks keep adding. At stagnantMs >= stallThresholdMs (15000): onStalled fires, then resets stagnantMs=0
    // So: 10000(2000), 12000(4000), 14000(6000), 16000(8000→soft,return), 18000(10000), 20000(12000), 22000(14000), 24000(16000≥15000→stall!)
    // Total: 24_000 ms
    vi.advanceTimersByTime(24_000);

    expect(disconnectMock).toHaveBeenCalled();
  });

  test("advancing currentTime resets stagnantMs → no stall", () => {
    const stream = fakeStream();
    renderSingleTile(stream);
    const video = getVideo();
    prepareVideoForStallMonitor(video);

    // Let stagnant accumulate for 10_000 ms (some post-warmup stagnation)
    vi.advanceTimersByTime(18_000);
    // stagnantMs should be around 10_000 (post-warmup stagnant ticks from 10000 to 18000)

    // Now make currentTime advance via a getter
    let ct = 1.0;
    Object.defineProperty(video, "currentTime", {
      get: () => (ct += 0.1),
      configurable: true,
    });

    // Advance 10 more seconds — currentTime is now advancing, so stagnantMs resets
    vi.advanceTimersByTime(10_000);

    expect(disconnectMock).not.toHaveBeenCalled();
  });

  test("track.readyState = 'ended' → monitor skips", () => {
    const stream = fakeStream("ended");
    renderSingleTile(stream);
    const video = getVideo();
    prepareVideoForStallMonitor(video);

    vi.advanceTimersByTime(30_000);

    expect(disconnectMock).not.toHaveBeenCalled();
  });

  test("video.readyState < 2 → monitor skips", () => {
    const stream = fakeStream();
    renderSingleTile(stream);
    // Don't override readyState — jsdom default is 0

    vi.advanceTimersByTime(30_000);

    expect(disconnectMock).not.toHaveBeenCalled();
  });

  test("30 s cooldown: second stall within 30 s ignored", () => {
    const stream = fakeStream();
    renderSingleTile(stream);
    const video = getVideo();
    prepareVideoForStallMonitor(video);

    // Trigger first stall: 24_000 ms as computed above
    vi.advanceTimersByTime(24_000);
    expect(disconnectMock).toHaveBeenCalledTimes(1);

    // Advance 15_000 more ms — within the 30 s cooldown
    // stagnantMs reset to 0 after stall, needs another 15_000 to accumulate
    // But recoverStalledStream checks Date.now() - lastRecoveryAt < 30_000
    vi.advanceTimersByTime(15_000);

    // disconnect should NOT be called again (cooldown active)
    expect(disconnectMock).toHaveBeenCalledTimes(1);
  });

  test("connectionState !== 'connected' → monitorEnabled=false", () => {
    webRtcState.connectionState = "connecting";
    const stream = fakeStream();
    renderSingleTile(stream);
    const video = getVideo();
    prepareVideoForStallMonitor(video);

    vi.advanceTimersByTime(30_000);

    expect(disconnectMock).not.toHaveBeenCalled();
  });
});
