# GeoDispatch Setup Guide

This guide details local environment setup, submodule workflow, docker network configuration, and service port mappings.

## Prerequisites

- **Docker Desktop** (or Docker Engine + Docker Compose v2+)
- **Git** 2.13+
- **Make**

## Repository Setup & Submodule Operations

### Cloning & Submodule Initialization

Because GeoDispatch utilizes Git submodules for source ownership, submodules must be fetched before building docker containers:

```bash
# Option A: Clone with submodules
git clone --recurse-submodules <REPO_URL>

# Option B: Initialize in existing clone
git submodule update --init --recursive
# or
make init
```

### Syncing Submodules

Submodules pin to specific commits. When sub-repos update, update submodule refs using:
```bash
make update-submodules
```

## Environment Configuration

Copy `.env.example` to `.env`:
```bash
make prepare
```

> [!CAUTION]
> `.env` contains local environment variables and credentials (such as `CAMARA_API_KEY`). It is excluded by `.gitignore` and must **never** be committed.

## Service Endpoints & Port Mappings

| Env Var | Used By | Purpose / Target Endpoint | Default Value |
|---|---|---|---|
| `SUPERVISOR_PORT` | Host mapping | `go-supervisor` HTTP port | `8080` |
| `SUPERVISOR_HOST` | Internal network | Service hostname | `go-supervisor` |
| `AGENT_URL` | `go-supervisor` | Target URL for Python Agent `/decide` | `http://python-agent:8000` |
| `CAMARA_URL` | `go-supervisor` | Target URL for mock or real Nokia NaC API | `http://mock-camara:8090` |
| `CAMARA_API_KEY` | `go-supervisor`, `mock-camara` | Shared secret API credential | `mock-secret-key-12345` |
| `AGENT_PORT` | Host mapping | `python-agent` HTTP port | `8000` |
| `DASHBOARD_PORT` | Host mapping | `dashboard` HTTP port | `3000` |
| `SUPERVISOR_WS_URL` | `dashboard` | Client WebSocket connection URL | `ws://localhost:8080/ws` |
| `MOCK_CAMARA_PORT` | Host mapping | `mock-camara` HTTP port | `8090` |

## Docker Compose Verification

Validate the merged Compose file syntax across all included sub-compose definitions:

```bash
docker compose config
```
