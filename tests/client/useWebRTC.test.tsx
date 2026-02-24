import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { useEffect } from "react";

import { useWebRTC } from "../../client/src/hooks/useWebRTC";

type HookApi = ReturnType<typeof useWebRTC>;

class FakeRTCPeerConnection {
  static instances: FakeRTCPeerConnection[] = [];

  connectionState: RTCPeerConnectionState = "new";
  localDescription: RTCSessionDescriptionInit | null = null;
  remoteDescription: RTCSessionDescriptionInit | null = null;
  ontrack: ((event: RTCTrackEvent) => void) | null = null;
  onconnectionstatechange: (() => void) | null = null;

  transceivers: Array<{
    kind: string;
    init?: RTCRtpTransceiverInit;
    setCodecPreferences?: (codecs: unknown[]) => void;
  }> = [];

  constructor() {
    FakeRTCPeerConnection.instances.push(this);
  }

  addTransceiver(kind: string, init?: RTCRtpTransceiverInit) {
    const transceiver = {
      kind,
      init,
      setCodecPreferences: vi.fn(),
    };
    this.transceivers.push(transceiver);
    return transceiver;
  }

  async createOffer(): Promise<RTCSessionDescriptionInit> {
    return { type: "offer", sdp: "offer-sdp" };
  }

  async setLocalDescription(desc: RTCSessionDescriptionInit): Promise<void> {
    this.localDescription = desc;
  }

  async setRemoteDescription(desc: RTCSessionDescriptionInit): Promise<void> {
    this.remoteDescription = desc;
    this.connectionState = "connected";
    this.onconnectionstatechange?.();
  }

  close(): void {
    this.connectionState = "closed";
    this.onconnectionstatechange?.();
  }
}

class FakeMediaStream {
  private tracks: MediaStreamTrack[];

  constructor(tracks: MediaStreamTrack[] = []) {
    this.tracks = tracks;
  }

  getTracks() {
    return this.tracks;
  }
}

function Harness({ onReady }: { onReady: (api: ReturnType<typeof useWebRTC>) => void }) {
  const api = useWebRTC();
  useEffect(() => {
    onReady(api);
  }, [api, onReady]);
  return null;
}

describe("useWebRTC", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  test(
    "connect negotiates WHEP for all three cameras",
    async () => {
      FakeRTCPeerConnection.instances = [];
      vi.stubGlobal("RTCPeerConnection", FakeRTCPeerConnection);
      vi.stubGlobal("MediaStream", FakeMediaStream);

      const fetchMock = vi.fn().mockImplementation((url: string) => {
        if (url.endsWith("/webrtc/cameras")) {
          return Promise.resolve({
            json: async () => ["left", "center", "right"],
          });
        }
        return Promise.resolve({
          ok: true,
          status: 201,
          text: async () => "answer-sdp",
        });
      });
      vi.stubGlobal("fetch", fetchMock);

      const apiRef: { current: HookApi | null } = { current: null };
      render(
        <Harness
          onReady={(value) => {
            apiRef.current = value;
          }}
        />,
      );
      await waitFor(() => {
        expect(apiRef.current).not.toBeNull();
      });
      expect((apiRef.current as HookApi).connectionState).toBe("idle");
      await (apiRef.current as HookApi).connect();

      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8000/webrtc/cameras",
        expect.objectContaining({ signal: expect.anything() }),
      );
      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8889/left/whep",
        expect.objectContaining({
          method: "POST",
          headers: { "Content-Type": "application/sdp" },
        }),
      );
      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8889/center/whep",
        expect.objectContaining({
          method: "POST",
        }),
      );
      expect(fetchMock).toHaveBeenCalledWith(
        "http://localhost:8889/right/whep",
        expect.objectContaining({
          method: "POST",
        }),
      );
      await waitFor(() => {
        expect((apiRef.current as HookApi).connectionState).toBe("connected");
      });
      expect((apiRef.current as HookApi).expectedCameraCount).toBe(3);

      expect(FakeRTCPeerConnection.instances).toHaveLength(3);
      const [firstPc, secondPc, thirdPc] = FakeRTCPeerConnection.instances;
      expect(firstPc.transceivers).toHaveLength(1);
      expect(secondPc.transceivers).toHaveLength(1);
      expect(thirdPc.transceivers).toHaveLength(1);

      firstPc.ontrack?.(
        { track: { id: "track-1" } as MediaStreamTrack, streams: [] } as unknown as RTCTrackEvent,
      );
      secondPc.ontrack?.(
        { track: { id: "track-2" } as MediaStreamTrack, streams: [] } as unknown as RTCTrackEvent,
      );
      thirdPc.ontrack?.(
        { track: { id: "track-3" } as MediaStreamTrack, streams: [] } as unknown as RTCTrackEvent,
      );

      await waitFor(() => {
        expect((apiRef.current as HookApi).streams).toHaveLength(3);
      });
      expect((apiRef.current as HookApi).partialLive).toBe(false);
    },
    15000,
  );

  test(
    "flags partial live when fewer than 3 cameras are streaming",
    async () => {
      FakeRTCPeerConnection.instances = [];
      vi.stubGlobal("RTCPeerConnection", FakeRTCPeerConnection);
      vi.stubGlobal("MediaStream", FakeMediaStream);

      const fetchMock = vi.fn().mockImplementation((url: string) => {
        if (url.endsWith("/webrtc/cameras")) {
          return Promise.resolve({
            json: async () => ["left", "center", "right"],
          });
        }
        return Promise.resolve({
          ok: true,
          status: 201,
          text: async () => "answer-sdp",
        });
      });
      vi.stubGlobal("fetch", fetchMock);

      const apiRef: { current: HookApi | null } = { current: null };
      render(
        <Harness
          onReady={(value) => {
            apiRef.current = value;
          }}
        />,
      );
      await waitFor(() => {
        expect(apiRef.current).not.toBeNull();
      });

      await (apiRef.current as HookApi).connect();

      await waitFor(() => {
        expect((apiRef.current as HookApi).connectionState).toBe("connected");
        expect((apiRef.current as HookApi).expectedCameraCount).toBe(3);
      });

      const firstPc = FakeRTCPeerConnection.instances[0];
      firstPc.ontrack?.(
        { track: { id: "track-1" } as MediaStreamTrack, streams: [] } as unknown as RTCTrackEvent,
      );

      await waitFor(() => {
        expect((apiRef.current as HookApi).streams).toHaveLength(1);
        expect((apiRef.current as HookApi).partialLive).toBe(false);
      });

      await new Promise((resolve) => setTimeout(resolve, 4500));
      await waitFor(() => {
        expect((apiRef.current as HookApi).partialLive).toBe(true);
      });
    },
    20000,
  );
});
