# Telemetry Console

WebRTC camera viewer + Rerun trajectory viewer with synchronized timeline.

## Repo layout

```
client/          React + Vite frontend
server/          FastAPI backend (WebRTC signaling, Rerun bridge)
tests/           All tests (client + server)
external/        Git submodules (depthai-core, rerun, dexmate-urdf)
scripts/         Dev scripts (setup, dev, lint)
```

## Quick start

```bash
make setup       # install all deps (npm + uv + submodules)
make dev         # start client + server concurrently
make test        # run all tests
```

## Individual commands

```bash
make test-client   # vitest only
make test-server   # pytest only
make lint          # ruff + tsc
make clean         # remove build artifacts
```

## External dependencies

Tracked as git submodules under `external/`:

- **depthai-core** -- Luxonis DepthAI camera SDK
- **rerun** -- Rerun visualization (web viewer + SDK)
- **dexmate-urdf** -- Robot URDF models
