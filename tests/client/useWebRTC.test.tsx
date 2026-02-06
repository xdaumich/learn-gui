import { render, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { useEffect } from "react";

import { useWebRTC } from "../../client/src/hooks/useWebRTC";

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
    setCodecPreferences?: (codecs: RTCRtpCodecCapability[]) => void;
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
  test("connect negotiates an offer and updates connection state", async () => {
    vi.stubGlobal("RTCPeerConnection", FakeRTCPeerConnection);
    vi.stubGlobal("RTCRtpReceiver", {
      getCapabilities: () => ({
        codecs: [{ mimeType: "video/H264" }],
      }),
    });
    vi.stubGlobal("MediaStream", FakeMediaStream);

    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith("/webrtc/cameras")) {
        return Promise.resolve({
          json: async () => ["CAM_A", "CAM_B"],
        });
      }
      return Promise.resolve({
        json: async () => ({ type: "answer", sdp: "answer-sdp" }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    let api: ReturnType<typeof useWebRTC> | null = null;
    render(<Harness onReady={(value) => (api = value)} />);

    expect(api?.connectionState).toBe("idle");
    await api?.connect();

    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/webrtc/cameras");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/webrtc/offer",
      expect.objectContaining({
        method: "POST",
      }),
    );
    await waitFor(() => {
      expect(api?.connectionState).toBe("connected");
    });

    const pc = FakeRTCPeerConnection.instances[0];
    expect(pc.transceivers).toHaveLength(2);
    pc.ontrack?.({ track: { id: "track-1" } as MediaStreamTrack, streams: [] } as RTCTrackEvent);
    pc.ontrack?.({ track: { id: "track-2" } as MediaStreamTrack, streams: [] } as RTCTrackEvent);

    await waitFor(() => {
      expect(api?.streams).toHaveLength(2);
    });
  });
});
