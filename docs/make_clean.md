# Dev Setup Cleanup

Simplified the development setup from three workflows to one.

## What changed

**Before:** Three separate dev workflows:
- `make dev` — full local stack
- `make dev_host` — Mac host (Vite + FastAPI)
- `make dev_remote` — Jetson Thor (MediaMTX + tc-camera)

**After:** Single `make dev` runs everything on Jetson Thor. The Mac (or any other machine) just opens a browser — no code needed.

## Why

The aiortc migration (`docs/aiortc.md`) replaced the 3-process video pipeline (tc-camera + ffmpeg + MediaMTX) with direct WebRTC in the FastAPI process. This eliminated the need for:
- `tc-camera` CLI entry point
- MediaMTX RTSP/WHEP relay
- Separate host/remote orchestration scripts

With everything handled by `tc-gui` (FastAPI + aiortc), there's no reason for the split dev workflow.

## What was removed

| File | Was | Why removed |
|------|-----|-------------|
| `scripts/dev_host.sh` | Mac-only orchestrator (Vite + FastAPI) | Everything runs on Thor now |
| `scripts/dev_remote.sh` | Thor-only orchestrator (MediaMTX + tc-camera) | MediaMTX/tc-camera replaced by aiortc |
| `scripts/setup_remote.sh` | Server-only dependency install | Single `make setup` handles all deps |
| `.env.host.example` | Mac host env config | No code runs on Mac |
| `.env.remote.example` | Thor env config | Merged into `.env.example` |
| `client/.env` | Hardcoded Tailscale IP for API | Dynamic URL resolution from browser hostname |

Makefile targets removed: `setup_host`, `setup_remote`, `dev_host`, `dev_remote`, `dev_remove`, `dev_remote_cleanup`

## New workflow

```bash
# On Jetson Thor:
make setup    # once
make dev      # runs Vite + FastAPI (with aiortc cameras) + optional Rerun/robot

# On any other machine:
# Open browser to http://<thor-ip>:5173
```

## Dynamic URL resolution

The frontend (`client/src/config.ts`) now derives backend URLs from `window.location.hostname`:

```
Browser at http://10.0.0.50:5173
  → API_BASE_URL = http://10.0.0.50:8000 (auto)
  → RERUN_WEB_ORIGIN = http://10.0.0.50:9090 (auto)
```

No `VITE_API_BASE_URL` env var needed. Override still works if set explicitly.

## Debug servers (unchanged)

```bash
make mjpeg       # OAK MJPEG debug server (:8001)
make mjpeg_elp   # ELP Global Shutter MJPEG (:8002)
```
