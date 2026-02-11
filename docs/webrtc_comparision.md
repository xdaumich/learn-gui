# WebRTC Infrastructure Comparison

This document compares the upstream Luxonis example at
`external/oak-examples/streaming/webrtc-streaming` with the current project
architecture documented in `docs/infra.md`.

## Scope Compared

- Upstream example:
  `external/oak-examples/streaming/webrtc-streaming/main.py` (+ `utils/` and local client build)
- Current project:
  `docs/infra.md` (client + server runtime architecture)

## High-Level Summary

- The upstream example is a compact, single-process WebRTC streamer built on
  `aiohttp` + `aiortc` + `depthai`.
- The current project has evolved into a full telemetry console architecture:
  React frontend, FastAPI backend, WebRTC signaling, recording, and Rerun
  integration.
- Core overlap remains in the WebRTC offer/answer flow and shared DepthAI
  pipeline concerns.
- Major divergence is in system breadth (multi-module backend, richer frontend,
  and observability tooling).

## Side-by-Side Comparison

| Area | Upstream example (`oak-examples`) | Current project (`docs/infra.md`) |
|---|---|---|
| Backend framework | `aiohttp` app with routes `/`, `/client.js`, `/offer` | FastAPI app with `/webrtc/*`, `/rerun/*`, `/recording/*`, `/health` |
| Frontend | Static built bundle served by Python app (`client/build/client.js`) | Separate React + Vite app (`client/`) |
| Signaling endpoint | `POST /offer` with raw SDP payload | `POST /webrtc/offer` with structured API layout |
| Camera discovery | Implicit in transform setup | Explicit `GET /webrtc/cameras` for track planning |
| Media tracks | Single `VideoTransform` track per peer connection loop | Multiple camera tracks represented in client grid and server WebRTC module |
| DepthAI pipeline lifecycle | Global `pipeline` singleton, restarted on new offer when needed | Shared/reused pipeline management in `webrtc.py` (documented), integrated with app modules |
| Processing options | Rich transform options via data channel + NN/depth modes (`utils/transform.py`) | Infra doc emphasizes streaming + recording + Rerun; no equivalent NN/depth option surface documented |
| Data channel | Present (`setup_datachannel`) for runtime controls | Not highlighted in current infra documentation |
| Extra runtime systems | None beyond streaming demo | Rerun bridge (gRPC/web viewer), Zarr recording manager, layout-aware frontend |
| Deployment modes | Peripheral mode and standalone device mode (RVC4) in README | Dev-focused local architecture docs (client/server split + ports) |
| CORS | Added via `aiohttp_cors` wildcard | Configured in FastAPI app setup |

## What Stayed Conceptually Similar

- Browser creates SDP offer and posts it to backend.
- Backend creates `RTCPeerConnection`, sets remote description, creates answer.
- DepthAI pipeline feeds `VideoStreamTrack` objects to WebRTC.
- Peer connection set is tracked and closed on shutdown.

## What Changed Significantly

- **System boundaries:** from one demo server to a multi-service architecture.
- **API surface:** from one signaling endpoint to domain-specific API groups.
- **Frontend responsibilities:** from static demo client to stateful UI with
  panel modes and dedicated WebRTC hook.
- **Runtime outputs:** from video-only stream to video + recording + Rerun
  visualization.
- **Operational model:** upstream includes device-side standalone mode, while the
  current infra doc describes host-driven development/runtime.

## Documentation Gaps Identified in `docs/infra.md`

- Upstream-inspired controls (data channel options, NN/depth transform knobs) are
  not described, even though they are part of the reference implementation.
- Upstream standalone (`oakctl`) mode is not represented in current infra docs.
- Pipeline lifecycle strategy is referenced at high level, but upstream-style
  restart/recreate behavior and trade-offs are not explicitly contrasted.

## Recommended Follow-Ups

1. Add a short "heritage" section in `docs/infra.md` that links this project's
   WebRTC path back to the upstream `oak-examples` implementation.
2. Document whether data channel control is intentionally removed, deferred, or
   replaced in current architecture.
3. Explicitly capture host-only vs standalone-device runtime decisions to avoid
   ambiguity for future contributors.
4. If NN/depth transform features are planned, add a roadmap note in infra docs
   to connect current architecture with upstream capabilities.
