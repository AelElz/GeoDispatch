# GeoDispatch — End-to-End Testing Plan & Verification Guide

This testing plan defines the validation strategy for the GeoDispatch multi-service stack. It is structured for DevOps and backend validation, ensuring data contract conformance, inter-service resilience, and accurate real-time disaster triage.

---

## 1. System Architecture & Testing Boundaries

```mermaid
flowchart TD
    subgraph Ingestion ["1. Ingestion Layer"]
        S[Disaster Sensor / Simulation Script] -->|POST /sensor| G[Go Supervisor :8080]
    end

    subgraph Data ["2. Data Layer"]
        G <-->|SQL / PostGIS :5432| DB[(PostgreSQL + PostGIS)]
    end

    subgraph Network ["3. Telco Intelligence"]
        G <-->|HTTP :8081| MC[Mock CAMARA / Nokia NaC]
    end

    subgraph AI ["4. Decision Engine"]
        G <-->|POST /decide :8000| AA[Python AI Agent]
        AA <-->|Internal API :11434| OL[Ollama Models]
    end

    subgraph Output ["5. Dispatch & Monitoring"]
        G -->|WS :8080/ws| WS[WebSocket Clients / Dashboard]
        G -->|Log / Flag| RF[(rescue_flags & device_logs)]
    end
```

### Critical Architecture Rules (Locked Contracts)
- **Go computes zones** (haversine formula against epicenter). **AI decides actions**. Never reversed.
- **Timestamps**: Unix milliseconds (`int64`).
- **Phone format**: E.164 (`+212XXXXXXXXX`).
- **Batch Processing Order**: Red (≤ 33% radius) $\rightarrow$ Orange (33–66%) $\rightarrow$ Green (66–100%).

---

## 2. Testing Phases Overview

| Phase | Target Scope | Key Verification | Tools / Method |
|---|---|---|---|
| **Phase 1: Smoke Tests** | Infrastructure & Connectivity | Containers healthy, ports open, unified `geodispatch-net` | `docker compose ps`, `curl` |
| **Phase 2: Database & Spatial** | PostgreSQL + PostGIS | Seed tables, spatial indexing, `PhonesNearEpicenter` | `psql` / `docker exec` |
| **Phase 3: Component Isolation** | Mock CAMARA & AI Agent | Standalone endpoint compliance & failure injection | `curl`, `pytest` |
| **Phase 4: Contract Conformance** | Inter-service JSON schemas | Strict adherence to `contracts/examples/*.json` | JSON Schema validator |
| **Phase 5: Disaster Simulation** | End-to-End Pipeline | Full earthquake triage run (Casablanca epicenter) | `simulate_disaster_morocco.go` |
| **Phase 6: WebSocket Feed** | Real-time broadcast | Correct sequence: `event_start` $\rightarrow$ `device_update` $\rightarrow$ `zone_summary` $\rightarrow$ `narrative` | `wscat` / `websocat` |
| **Phase 7: Resilience & Faults** | Failure Injection | CAMARA timeout, missing devices, invalid payloads | `?fail=timeout`, curl edge cases |

---

## 3. Detailed Test Execution Procedures

### Phase 1: Infrastructure & Smoke Tests

Ensure all 5 containers are up, healthy, and communicating over the unified `geodispatch-net` bridge network.

```bash
# 1.1 Verify container states
docker compose ps

# 1.2 Verify all containers share the single 'geodispatch-net' network
docker network inspect geodispatch-net --format '{{range .Containers}}{{.Name}} ({{.IPv4Address}}){{"\n"}}{{end}}'

# 1.3 Verify service health endpoints
curl -fsS http://localhost:8080/health && echo " -> Supervisor OK"
curl -fsS http://localhost:8000/health && echo " -> Agent OK"
curl -fsS http://localhost:8081/qos && echo " -> Mock CAMARA OK"

# 1.4 Verify Ollama has required models loaded
docker exec -it geodispatch-ollama ollama list
```
> **Pass Criteria**: All containers report `Up` or `Healthy`, network inspect shows all 5 containers attached to `geodispatch-net`, and all health probes return HTTP 200.

---

### Phase 2: Database Seeding & Spatial Queries

> [!IMPORTANT]
> The database migrations (`001_init.sql` and `002_events.sql`) initialize table structures, but device and shelter seeds reside in `supervisor/scripts/seed/`. If these tables are empty, the supervisor pipeline will abort with `"no phones found near epicenter"`.

Execute and verify seeds:
```bash
# 2.1 Verify PostGIS extension is active
docker exec -i geodispatch_postgres psql -U geodispatch_user -d geodispatch -c "SELECT PostGIS_Full_Version();"

# 2.2 Seed Shelters & Devices (if not already seeded)
docker exec -i geodispatch_postgres psql -U geodispatch_user -d geodispatch < supervisor/scripts/seed/seed_shelters.sql
docker exec -i geodispatch_postgres psql -U geodispatch_user -d geodispatch < supervisor/scripts/seed/seed_devices.sql

# 2.3 Verify seeded record counts
docker exec -i geodispatch_postgres psql -U geodispatch_user -d geodispatch -c "SELECT 'devices' AS table, count(*) FROM devices UNION ALL SELECT 'shelters', count(*) FROM shelters;"

# 2.4 Test spatial proximity query (Casablanca coordinates: 33.5731, -7.5898, radius 15km)
docker exec -i geodispatch_postgres psql -U geodispatch_user -d geodispatch -c "
SELECT phone, ST_Distance(location, ST_MakePoint(-7.5898, 33.5731)::geography) / 1000.0 AS dist_km
FROM devices
WHERE ST_DWithin(location, ST_MakePoint(-7.5898, 33.5731)::geography, 15000)
ORDER BY dist_km ASC
LIMIT 5;
"
```
> **Pass Criteria**: At least 36+ devices and 3+ shelters seeded. Proximity query returns phones ordered by distance.

---

### Phase 3: Component Isolation Tests

#### 3.1 Mock CAMARA Verification (Supervisor Mock on :8081)
Test that mock CAMARA handles location, reachability, and QoS:
```bash
# Location Retrieval
curl -s "http://localhost:8081/location?phone=+212600000001" | jq .

# Reachability Status
curl -s "http://localhost:8081/reachability?phone=+212600000001" | jq .

# QoS Status
curl -s http://localhost:8081/qos | jq .
```

#### 3.2 AI Agent Batch Decision (`POST /decide`)
Test the AI agent with a sample `red` zone batch payload:
```bash
curl -s -X POST http://localhost:8000/decide \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "test-event-001",
    "disaster_type": "earthquake",
    "severity": 6.8,
    "batch_index": 0,
    "total_batches": 3,
    "zone": "red",
    "nearest_shelters": [
      {"name": "Stade Mohammed V", "address": "Rue Ahmed El Joumari, Casablanca", "capacity": 500, "distance_km": 1.2}
    ],
    "devices": [
      {
        "phone": "+212600000001",
        "distance_km": 0.45,
        "zone": "red",
        "reachability": "CONNECTED_DATA",
        "roaming": false,
        "network_type": "5G"
      }
    ]
  }' | jq .
```
> **Pass Criteria**: Response contains `decisions` array with valid `action` (`sms`, `rescue_flag`, `both`, `none`), localized SMS text, and `narrative_report`.

---

### Phase 4: Full Disaster Simulation (End-to-End)

Run the full Morocco earthquake simulation script or inject the event payload into `POST /sensor`:

```bash
# Trigger simulation via Go script:
go run supervisor/scripts/simulation/simulate_disaster_morocco.go -host http://localhost:8080 -event EQ-MOROCCO-2026 -severity 6.8
```

Alternatively, post directly with `curl`:
```bash
curl -i -X POST http://localhost:8080/sensor \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "EQ-CASABLANCA-001",
    "disaster_type": "earthquake",
    "timestamp": '$(date +%s%3N)',
    "severity": 6.8,
    "epicenter": {
      "latitude": 33.5731,
      "longitude": -7.5898
    },
    "radius_km": 15.0,
    "depth_km": 10.0,
    "aftershock_risk": "HIGH",
    "tsunami_risk": false
  }'
```

#### Log Inspection
Monitor supervisor logs to verify execution flow:
```bash
docker compose logs -f supervisor
```
Observe the execution pipeline:
1. `🌍 GEODISPATCH EVENT STARTED`
2. Area calls: QoS on demand, nearest shelters query, congestion insights.
3. Concurrent CAMARA queries across phone batches.
4. Haversine zone classification (`🔴 RED`, `🟠 ORANGE`, `🟢 GREEN`).
5. Batch dispatch to AI agent (`POST /decide`).
6. Decision processing: SMS dispatch and `rescue_flags` recording.

---

### Phase 5: Verification of Persistence & Dispatch Records

After the simulation completes, verify that all triage results were recorded in PostgreSQL:

```bash
# 5.1 Check event record
docker exec -i geodispatch_postgres psql -U geodispatch_user -d geodispatch -c "SELECT id, disaster_type, severity, created_at FROM events WHERE id = 'EQ-CASABLANCA-001';"

# 5.2 Check device triage decisions
docker exec -i geodispatch_postgres psql -U geodispatch_user -d geodispatch -c "
SELECT zone, action, count(*), avg(confidence) as avg_conf
FROM device_logs
WHERE event_id = 'EQ-CASABLANCA-001'
GROUP BY zone, action;
"

# 5.3 Check flagged rescues
docker exec -i geodispatch_postgres psql -U geodispatch_user -d geodispatch -c "
SELECT phone, zone, rescue_priority, flagged_at
FROM rescue_flags
WHERE event_id = 'EQ-CASABLANCA-001'
ORDER BY rescue_priority ASC;
"
```
> **Pass Criteria**: `events` has 1 record, `device_logs` has entries for each processed phone with valid actions, and `rescue_flags` lists flagged individuals.

---

### Phase 6: WebSocket Live Feed Verification

Connect a WebSocket client to `ws://localhost:8080/ws` before triggering `POST /sensor`:

```bash
# Using websocat or wscat
websocat ws://localhost:8080/ws | jq -c '{type: .type, timestamp: .timestamp}'
```

Validate message sequence:
1. `event_start`: Received immediately on `/sensor` ingestion.
2. `device_update`: Streamed as devices complete CAMARA triage.
3. `zone_summary`: Streamed when each batch completes AI decision.
4. `narrative_update`: Streamed with situation report text.

---

### Phase 7: Chaos & Fault Tolerance Testing

| Test Case | Method | Expected System Behavior |
|---|---|---|
| **CAMARA Timeout** | Curl mock with `?fail=timeout` | Supervisor logs `CAMARA_TIMEOUT`, sets device status fallback, non-fatal. |
| **QoS Request Failure** | Set `?fail=qos_failed` on CAMARA QoS | Supervisor logs `QOS_FAILED`, broadcasts non-fatal WS error, continues device triage. |
| **Database Disconnect** | `docker stop geodispatch_postgres` | Supervisor responds with HTTP 500 / fatal `DB_ERROR` WS update; halts gracefully without silent corruption. |
| **Ollama Model Latency** | Sequential batch queuing | Supervisor waits for batch response before dispatching next zone batch (Red $\rightarrow$ Orange $\rightarrow$ Green). |
| **Malformed Sensor Payload** | Missing required fields on `POST /sensor` | Immediate `400 Bad Request`, pipeline not invoked. |

---

## 4. Test Execution Checklist for DevOps

- [ ] Network topology confirmed: only `geodispatch-net` exists; all 5 containers reachable.
- [ ] Database seeded: `devices` (≥36 rows) and `shelters` (≥3 rows) populated in PostGIS.
- [ ] Mock CAMARA responses verified against `contracts/examples/camara_device.json`.
- [ ] AI Agent `/decide` verified against `contracts/examples/ai_response.json`.
- [ ] Simulation executed: `simulate_disaster_morocco.go` finishes with zero fatal errors.
- [ ] Database tables `events`, `device_logs`, and `rescue_flags` successfully populated.
- [ ] WebSocket streaming order validated (`event_start` $\rightarrow$ `device_update` $\rightarrow$ `zone_summary`).
