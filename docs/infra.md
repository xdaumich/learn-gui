# Infrastructure and Code Structure

This document summarizes the current runtime architecture and how major components
interact in the Telemetry Console.

## Repository layout

- `client/` — React + Vite frontend (UI panels, layout state, WebRTC hook).
- `server/` — FastAPI backend (WebRTC signaling, Rerun bridge, recording).
- `tests/` — Vitest + Pytest coverage for client/server.
- `scripts/` — Dev helpers (setup, dev, lint, demos).
- `external/` — Git submodules (DepthAI SDK, Rerun SDK, URDF assets).

## Client (React/Vite)

**Entrypoint**
- `client/index.html` → `client/src/main.tsx` → `client/src/App.tsx`

**Core layout**
- `LayoutContext` holds `mode`, `focusTarget`, `splitRatio`, and keyboard shortcuts.
- `App.tsx` composes the page and conditionally shows panels based on mode.

**Panels and UI**
- `VideoPanel` mounts `useWebRTC` and renders received video tracks.
- `RerunPanel` embeds the Rerun web viewer via iframe.
- `TopBar` hosts `ModeSwitcher` plus control/status placeholders.
- `ResizeHandle`, `CompactHeader`, `FloatingDot`, `TimelineBar` provide UI chrome.

**WebRTC hook**
- `useWebRTC` fetches `/webrtc/cameras`, creates recv-only transceivers, POSTs
  the SDP offer to `/webrtc/offer`, and manages incoming tracks.

## Server (FastAPI)

**Entrypoint**
- `server/main.py` configures the app + CORS and wires endpoints.

**HTTP endpoints**
- `GET /health`
- `GET /rerun/status`
- `GET /webrtc/cameras`
- `POST /webrtc/offer`
- `GET/POST /recording/status|start|stop`

**Modules**
- `webrtc.py` — DepthAI camera discovery, aiortc peer connections, shared pipeline
  management, and `DepthAIVideoTrack`.
- `data_log.py` — Zarr-based recording manager for RGB frames + synthetic pose.
- `rerun_bridge.py` — starts Rerun gRPC + web viewer, loads URDF, sends blueprint.
- `schemas.py` — Pydantic request/response models.

## Runtime interactions

- **WebRTC**: `useWebRTC` creates an offer → `/webrtc/offer` → server builds an
  answer and attaches DepthAI tracks → client receives media in `VideoPanel`.
- **Camera discovery**: client calls `/webrtc/cameras` to decide transceiver count.
- **Recording**: when recording is active, `DepthAIVideoTrack` writes frames to
  Zarr via `RecordingManager`.
- **Rerun**: server runs gRPC on `9876` and web viewer on `9090`; client embeds
  the viewer via iframe.

## 1. System architecture

High-level view — how the three runtime layers connect.

```mermaid
flowchart LR
  subgraph HW["Hardware"]
    CAM["DepthAI\nCameras"]
  end

  subgraph SRV["Server :8000 (FastAPI)"]
    direction TB
    WEB_RTC["webrtc.py\nDepthAIVideoTrack"]
    RERUN["rerun_bridge.py"]
    DLOG["data_log.py\nZarr recording"]
  end

  subgraph UI["Client :5173 (React / Vite)"]
    direction TB
    VP["VideoPanel"]
    RP["RerunPanel"]
  end

  CAM -- "RGB frames" --> WEB_RTC
  WEB_RTC -- "WebRTC\nvideo tracks" --> VP
  WEB_RTC -. "frames\n(when recording)" .-> DLOG
  RERUN -- "gRPC :9876\n+ Web :9090" --> RP

  style HW fill:#2d2d2d,stroke:#666,color:#ccc
  style SRV fill:#1e293b,stroke:#475569,color:#e2e8f0
  style UI  fill:#1a1a2e,stroke:#5c5c8a,color:#e2e8f0
```

## 2. Client component tree

```mermaid
flowchart TB
  main["main.tsx"] --> App
  App --> LP["LayoutProvider\n(LayoutContext)"]

  LP --> TopBar
  LP --> Content["content-area"]
  LP --> Footer

  TopBar --> MS["ModeSwitcher"]
  Content --> VP["VideoPanel"]
  Content --> RH["ResizeHandle"]
  Content --> RP["RerunPanel"]
  Footer --> TB_["TimelineBar"]
  Footer --> FD["FloatingDot\n(zen only)"]

  VP --> hook["useWebRTC"]
  hook --> RTC["RTCPeerConnection"]

  RP --> iframe["iframe :9090\nRerun Web Viewer"]

  style LP fill:#312e81,stroke:#6366f1,color:#e0e7ff
  style hook fill:#1e3a5f,stroke:#38bdf8,color:#e0f2fe
```

## 3. Server module map

```mermaid
flowchart TB
  main["main.py\n(FastAPI app)"]

  main --> ep1["GET /webrtc/cameras"]
  main --> ep2["POST /webrtc/offer"]
  main --> ep3["GET /rerun/status"]
  main --> ep4["/recording/*"]

  ep1 & ep2 --> webrtc["webrtc.py"]
  ep3 --> rerun["rerun_bridge.py"]
  ep4 --> dlog["data_log.py"]

  webrtc --> pipe["DepthAI\npipeline"]
  webrtc --> track["DepthAIVideoTrack"]
  track -. "append()" .-> dlog
  rerun --> grpc["Rerun gRPC :9876"]
  rerun --> web["Rerun Web :9090"]
  rerun --> urdf["external/\ndexmate-urdf"]

  style main fill:#1e293b,stroke:#475569,color:#e2e8f0
  style webrtc fill:#1e3a5f,stroke:#38bdf8,color:#e0f2fe
  style rerun fill:#312e81,stroke:#6366f1,color:#e0e7ff
  style dlog fill:#3b2e1a,stroke:#f59e0b,color:#fef3c7
```

## 4. WebRTC signaling sequence

```mermaid
sequenceDiagram
  participant B as Browser (useWebRTC)
  participant S as Server (main.py)
  participant W as webrtc.py
  participant D as DepthAI Camera

  B->>S: GET /webrtc/cameras
  S->>W: list_camera_sockets()
  W-->>S: [CAM_A, CAM_B, …]
  S-->>B: ["CAM_A","CAM_B",…]

  Note over B: create RTCPeerConnection<br/>add N recv-only transceivers

  B->>S: POST /webrtc/offer {sdp}
  S->>W: create_answer(sdp)
  W->>D: start pipeline (if needed)
  D-->>W: output queues
  W-->>S: SDP answer + peer connection
  S-->>B: {sdp answer}

  Note over B: setRemoteDescription

  D->>W: RGB frames (continuous)
  W->>B: WebRTC video tracks
  B->>B: render in VideoPanel
```

## Notes / TODOs

- `useTimeSync` and telemetry ingestion are placeholders with TODOs in code.
