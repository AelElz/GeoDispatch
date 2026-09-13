# GeoDispatch Deployment (`deploy`)

This repository orchestrates the build, deployment, and local multi-service composition for **GeoDispatch**.

## Purpose

Use this documentation to:
- Deploy services consistently across environments
- Configure required environment variables and secrets
- Validate deployment health after release
- Troubleshoot common deployment failures
- Roll back safely when needed

## Architecture & Code Structure

```text
deploy/
├── .env.example                <- Master environment template (tracked)
├── .env                        <- Local environment file (gitignored)
├── .gitignore                  <- Git ignore configuration
├── .gitmodules                 <- Submodule repository tracking
├── docker-compose.yml          <- Root Compose file (includes service composes)
├── Makefile                    <- Dev/ops workflow automation
├── supervisor/                 <- Submodule: Go Supervisor service
├── agent/                      <- Submodule: Python Agent service
├── dashboard/                  <- Submodule: SolidJS + Leaflet Dashboard (Vite-based)
├── contracts/                  <- Submodule: Shared JSON Schemas & Examples
└── docs/                       <- Documentation & guides
    ├── README.md
    ├── SETUP.md
    └── LICENSE.md
```

### Core Components (Git Submodules)
- `supervisor` → Orchestration, state management, and CAMARA integration service
- `agent` → AI decision and triage engine
- `dashboard` → SolidJS + Leaflet real-time map interface
- `contracts` → Shared schemas and API contract specifications

### Networking
All services communicate over the unified `geodispatch-net` bridge network.

## Quick Start

### 1. Clone the Repository
When cloning for the first time, ensure submodules are included:
```bash
git clone --recurse-submodules https://github.com/geodispatch/deploy.git
cd deploy
```

If already cloned without `--recurse-submodules`:
```bash
make init
# or: git submodule update --init --recursive
```

### 2. Environment Setup
Generate your local `.env` file from the example template:
```bash
make prepare
```

### 3. Build & Run Services
Start all services in detached mode:
```bash
make up
```

Check running container status:
```bash
make status
# or: docker compose ps
```

Follow container logs:
```bash
make logs
```

Stop services:
```bash
make down
```

### 4. Updating Submodules
To pull the latest commits from all submodule main branches:
```bash
make update-submodules
```
