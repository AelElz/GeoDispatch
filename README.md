# GeoDispatch

**AI-powered emergency dispatch system** using Nokia CAMARA APIs for real-time device geolocation, an LLM-based triage agent, and a live map dashboard.

---

## Architecture

```
┌─────────────┐     WebSocket      ┌──────────────────┐     HTTP      ┌─────────────────┐
│  Dashboard   │◄──────────────────►│   Go Supervisor   │◄────────────►│  Python Agent    │
│  (SolidJS +  │   (real-time map   │  (orchestration,  │  /decide     │  (FastAPI +      │
│   Leaflet)   │    updates)        │   state, routing) │              │   Ollama LLM)    │
└─────────────┘                    └────────┬─────────┘              └────────┬─────────┘
   :3000                                    │                                 │
                                            │ SQL                             │ HTTP
                                   ┌────────▼─────────┐              ┌───────▼──────────┐
                                   │   PostgreSQL +    │              │     Ollama        │
                                   │     PostGIS       │              │  (qwen2.5:3b)    │
                                   └──────────────────┘              └──────────────────┘
                                      :5432                            internal
                                            │
                                   ┌────────▼─────────┐
                                   │   Mock CAMARA     │
                                   │  (Nokia NaC sim)  │
                                   └──────────────────┘
                                      :8081
```

| Service | Port | Description |
|---|---|---|
| **Dashboard** | `3000` | SolidJS + Leaflet real-time dispatch map |
| **Supervisor** | `8080` | Go backend — state management, WebSocket, CAMARA integration |
| **Agent** | `8000` | Python FastAPI — AI triage decisions via Ollama |
| **Ollama** | internal | LLM runtime serving `qwen2.5:3b` custom models |
| **PostgreSQL + PostGIS** | `5432` | Spatial database with shelter/device data |
| **Mock CAMARA** | `8081` | Nokia Network-as-Code API simulator |

---

## Prerequisites

- **Docker** (v20+) and **Docker Compose** (v2+)
- **Git**
- ~4 GB free disk space (Ollama model download)
- ~8 GB RAM recommended

### macOS (with Colima)

If you use [Colima](https://github.com/abiosoft/colima) instead of Docker Desktop:

```bash
# Install (if not already)
brew install colima docker docker-compose

# Start with enough resources
colima start --cpu 4 --memory 8
```

### macOS (with Docker Desktop)

Make sure Docker Desktop is running before proceeding.

---

## Quick Start

### 1. Clone the repository

```bash
git clone <repository-url>
cd GeoDispatch
```

### 2. Navigate to the deploy directory

```bash
cd deploy
```

### 3. Generate environment files

```bash
make prepare
```

This copies `.env.example` → `.env`. Edit `.env` if you have real Nokia CAMARA API keys.

### 4. Build and start all services

```bash
make up
```

> **⚠️ First run takes 5–15 minutes.** Docker pulls base images and Ollama downloads the `qwen2.5:3b` model (~1.9 GB). Subsequent runs use cached images and are much faster.

### 5. Verify everything is running

```bash
make status
```

You should see all containers as `Up` and `healthy`:

```
geodispatch_dashboard        Up (healthy)
geodispatch-app              Up
geodispatch_supervisor_dev   Up (healthy)
geodispatch_mock_camara      Up (healthy)
geodispatch-ollama           Up (healthy)
geodispatch_postgres_dev     Up (healthy)
```

### 6. Open the dashboard

Open your browser and navigate to:

```
http://localhost:3000
```

---

## Triggering a Disaster Event

The dashboard starts in an idle state ("awaiting AI decision"). To trigger the dispatch pipeline, send a sensor event to the supervisor:

### Earthquake example

```bash
curl -X POST http://localhost:8080/sensor \
  -H "Content-Type: application/json" \
  -d '{
    "type": "earthquake",
    "latitude": 36.7525,
    "longitude": 3.0420,
    "magnitude": 6.5
  }'
```

### Flood example

```bash
curl -X POST http://localhost:8080/sensor \
  -H "Content-Type: application/json" \
  -d '{
    "type": "flood",
    "latitude": 36.7525,
    "longitude": 3.0420,
    "magnitude": 4.0
  }'
```

### Heatwave example

```bash
curl -X POST http://localhost:8080/sensor \
  -H "Content-Type: application/json" \
  -d '{
    "type": "heatwave",
    "latitude": 36.7525,
    "longitude": 3.0420,
    "magnitude": 45.0
  }'
```

After triggering, the supervisor will:

1. Query the CAMARA mock for nearby device locations
2. Send device data to the AI Agent for triage
3. Push real-time results via WebSocket to the dashboard
4. The map will display device markers with dispatch decisions

---

## Useful Commands

| Command | Description |
|---|---|
| `make up` | Build and start all services |
| `make down` | Stop all services |
| `make status` | Show container status |
| `make logs` | Tail logs from all services |
| `make build` | Build images without starting |
| `make clean` | Stop services and remove volumes/images |
| `make re` | Full clean rebuild from scratch |

### View individual service logs

```bash
docker logs -f geodispatch_supervisor_dev   # Supervisor
docker logs -f geodispatch-app              # Agent
docker logs -f geodispatch-ollama           # Ollama
docker logs -f geodispatch_dashboard        # Dashboard
docker logs -f geodispatch_postgres_dev     # Database
```

### Health check endpoints

```bash
curl http://localhost:8080/health    # Supervisor (readiness)
curl http://localhost:8080/livez     # Supervisor (liveness)
curl http://localhost:8000/health    # Agent
```

---

## Environment Variables

Key variables in `deploy/.env`:

| Variable | Default | Description |
|---|---|---|
| `GEODISPATCH_ENV` | `development` | Environment mode |
| `MOCK_CAMARA_PORT` | `8081` | Mock CAMARA API port |
| `NOKIA_NAC_API_KEY` | *(empty)* | Real Nokia API key (empty = use mock) |
| `DASHBOARD_PORT` | `3000` | Dashboard port |
| `INTEGRATION_AGENT_URL` | `http://app:8000/decide` | Agent endpoint |
| `INTEGRATION_DATABASE_URL` | `postgres://geodispatch:...` | Database connection |

---

## Troubleshooting

### "Ollama is still starting"

The first run downloads ~1.9 GB of model weights. Monitor progress:

```bash
docker logs -f geodispatch-ollama
```

Wait until you see `geodispatch-models-ready` in the logs.

### "database connection failed"

Make sure you ran `make prepare` before `make up`. If the issue persists:

```bash
make down
make clean
make up
```

### Port conflicts

If ports 3000, 5432, 8000, 8080, or 8081 are in use, stop the conflicting services or edit `deploy/.env` to change the port mappings.

### Docker daemon not running

```bash
# If using Colima:
colima start --cpu 4 --memory 8

# If using Docker Desktop:
# Open Docker Desktop application
```

### Full reset (nuclear option)

```bash
cd deploy
make fclean
docker volume rm geodispatch-ollama-models geodispatch_postgres_dev_data 2>/dev/null
make up
```

---

## Project Structure

```
GeoDispatch/
├── agent/              # Python AI Agent (FastAPI + Ollama)
│   ├── main.py         # FastAPI entrypoint
│   ├── services/       # Ollama integration
│   ├── models/         # Pydantic schemas
│   ├── prompts/        # LLM prompt templates
│   ├── modelfiles/     # Ollama Modelfiles (earthquake, flood, heatwave)
│   └── docker-compose.yml
├── supervisor/         # Go Supervisor (orchestration + CAMARA)
│   ├── cmd/            # Go entrypoint
│   ├── internal/       # Core logic
│   ├── migrations/     # SQL schema
│   ├── scripts/        # Mock servers + seeds
│   └── docker-compose.yml
├── dashboard/          # SolidJS + Leaflet Frontend
│   └── interface/      # Vite project
│       ├── src/        # SolidJS components
│       └── public/     # Static assets
├── contracts/          # Shared API schemas
├── deploy/             # Docker Compose orchestration
│   ├── docker-compose.yml  # Main compose file
│   ├── Makefile            # Dev workflow commands
│   ├── .env.example        # Environment template
│   └── docker/             # Dockerfiles + nginx config
├── UI:UIX/             # Design mockups
└── env                 # Global environment reference
```

---

## License

Built at the Ignite Hackathon.
