# GeoDispatch — Data Contracts (v2)

JSON Schema (Draft-07) contracts for every inter-service boundary of the
disaster-dispatch pipeline. **Current contract version: 2** (see
[`../CHANGELOG.md`](../CHANGELOG.md)).

These contracts are LOCKED once published.
Do not change without notifying all team members.

Every file in `examples/` is a JSON **Schema** whose top-level `examples` array
holds valid **instances**. The deploy checker
(`deploy/helpers/scripts/validate_contracts.py`) requires every `*.json` under
`contracts/` to be a Draft-07 schema and validates each example against it, so
no other JSON files live in this repository.

## Architecture boundaries

```
[Disaster sensor / operator console]
      │  POST /sensor          (sensor_input.json)
      │  GET  /capabilities    GET /health    GET /livez
      ▼
[Go supervisor] ──── CAMARA APIs ────▶ network source (declared by config:
      │                                 mock_camara in development, nokia_nac)
      │  POST /decide          (ai_request.json → ai_response.json)
      ▼
[Python AI agent]  — one request per zone batch, ≤ 20 devices
      │
[Go supervisor]
      ├──▶ SMS gateway          (SMS_GATEWAY; not configured today → nothing is sent)
      ├──▶ rescue_flags table   (PostgreSQL)
      └──▶ GET /ws  WebSocket   (ws_update.json, v2 frames)  ──▶ [Dashboard]
```

## Files

| File | Schema | Direction | Consumed by |
|---|---|---|---|
| `examples/sensor_input.json` | `SensorInput` | Sensor → Go | `internal/sensor` (decode + validation), dashboard launcher |
| `examples/camara_device.json` | CAMARA Location / Reachability / Verification / Congestion responses, `TriagedDevice` | Network → Go | `internal/camara`, mock CAMARA fixtures |
| `examples/ai_request.json` | `AgentRequest` | Go → Python AI | `internal/agent` + Python agent (`models/schemas.py`) |
| `examples/ai_response.json` | `AgentResponse` + `DeviceDecision` | Python AI → Go | `internal/agent`, `pipeline.ValidateAgentResponse` |
| `examples/ws_update.json` | v2 frame envelope + every payload | Go → dashboard | `internal/dashboard` hub + dashboard `src/lib/validate.js` |
| `sync.sh` | — | — | copies canonical files to the services (see below) |
| `CHANGELOG.md` | — | — | contract history |

---

## Critical rules

> **Go calculates zones. AI decides actions. Never reversed.**

- All timestamps on the wire: **Unix milliseconds** (integers). CAMARA
  timestamps inside `camara_device.json` / `ai_request.json` stay ISO-8601.
- All phone numbers: **E.164** (`^\+[1-9]\d{1,14}$`). Clients display them
  masked only; the supervisor never logs raw numbers.
- All zones: **lowercase** `"red"` | `"orange"` | `"green"`.
- `zone` is **always set by Go haversine**. The AI may annotate an escalation
  (`zone_escalated` / `escalated_zone` on the dashboard) but never replaces it.
- `reasoning` in `DeviceDecision` is **internal audit only** — never sent to
  the dashboard, never shown to users, never sent in SMS.
- No WebSocket payload carries `reasoning`, `sms_message` or `shelter_name`.
- Nothing is labelled "live CAMARA". The supervisor *declares* its configured
  network source (`network_source`); clients present it as "declared by
  supervisor configuration (unverified)".

---

## WebSocket contract v2 — `GET /ws`

### Envelope (every frame)

```json
{ "v": 2, "type": "event_start", "event_id": "EQ-20260912-0001", "seq": 1,
  "timestamp": 1757700000000, "replay": false, "payload": { } }
```

| Field | Type | Rule |
|---|---|---|
| `v` | int | always `2` |
| `type` | string | one of the 10 frame types below |
| `event_id` | string | event the frame belongs to (`^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$`). `""` only on control frames when the supervisor holds no event |
| `seq` | int | event frames: per-event sequence, `event_start` = 1, each later frame = previous + 1. Control frames: `0` |
| `timestamp` | int ≥ 1 | server emit time (Unix ms). Replayed frames keep their ORIGINAL emit time |
| `replay` | bool | `true` only for frames re-sent inside a connection snapshot (never on control frames) |
| `payload` | object | per type |

All seven fields are required; no other envelope field is allowed. The schema
is a `oneOf` over one definition per type (keyed by `"type": {"const": …}`), so
every frame matches exactly one branch. Every object forbids unknown fields.

### Frame types

| Type | Kind | Payload (all fields required) | Semantics |
|---|---|---|---|
| `snapshot_begin` | control | `head_seq`, `active`, `lifecycle` | FIRST frame on every connection |
| `snapshot_end` | control | `head_seq`, `replayed` | end of the snapshot; live frames follow |
| `heartbeat` | control | `head_seq`, `active`, `lifecycle` | every `WS_HEARTBEAT_SEC` (15 s) |
| `event_start` | event, seq 1 | `disaster_type`, `severity`, `epicenter`, `radius_km`, `depth_km`, `tsunami_risk`, `aftershock_risk`, `sensor_timestamp`, `zone_bands` | new event; a live `event_start` blanks ALL previous event state |
| `event_context` | event | `devices_in_radius`, `shelters_status`, `shelters[≤3]`, `network{congestion_level, qos_status}`, `network_source`, `sms_gateway` | latest wins (full replacement); re-sent when a value changes (e.g. QoS upgrade) |
| `device_update` | event | full device state (below) | replaces the previous state of the same phone |
| `zone_summary` | event | `red`, `orange`, `green` (`ZoneStats`), `devices_in_radius`, `triaged`, `location_failed` | cumulative replacement, NOT an increment |
| `narrative_update` | event | `zone`, `narrative` (1..2000 chars), `batch_index` | latest per zone replaces that zone's narrative |
| `error` | event | `code`, `message`, `phone`, `fatal`, `stage` | see the fatal rule |
| `event_complete` | event | `status`, `duration_ms`, `devices_in_radius`, `devices_triaged`, `devices_decided`, `failures{location, reachability, decision, sms, rescue}`, `sms_not_sent_no_gateway`, `fatal_error` | terminal, exactly once per event; nothing follows it for that event |

Control payloads: `lifecycle` ∈ `idle | running | completed |
completed_with_failures | no_devices | failed`; `active` is true iff a
pipeline is running (`lifecycle == running`); with `event_id: ""` the payload
is `head_seq 0, active false, lifecycle idle`.

`event_context` enums: `shelters_status` `ok | unavailable` (unavailable = the
database query failed, `shelters` is then `[]`); `congestion_level` `LOW |
MEDIUM | HIGH | CRITICAL | UNKNOWN`; `qos_status` `inactive | requested |
active | failed`; `network_source` `mock_camara | nokia_nac` (declared,
unverified); `sms_gateway` `configured | not_configured`. Shelters carry
`name, address, location, distance_km, capacity` — there is **no occupancy**
anywhere (the database has none).

#### `device_update` payload

| Field | Rule |
|---|---|
| `phone` | E.164 |
| `latitude` / `longitude` | ±90 / ±180 |
| `location_accuracy_m` | ≥ 0 (CAMARA area radius) |
| `zone` | `red / orange / green` — Go haversine band, AUTHORITATIVE |
| `distance_km` | ≥ 0, Go haversine |
| `reachable` | `reachability_status != NOT_CONNECTED` |
| `reachability_status` | `CONNECTED_DATA / CONNECTED_SMS / NOT_CONNECTED` (CAMARA, not the AI) |
| `reachability_assumed` | true when the reachability lookup failed and NOT_CONNECTED was assumed |
| `stage` | `triaged` (located, awaiting AI) / `decided` / `decision_failed` |
| `action` | `sms / rescue_flag / both / none`; `null` unless `stage == decided` |
| `zone_escalated`, `escalated_zone` | AI escalation annotation, display only. `escalated_zone` is null unless escalated and is strictly more severe than `zone` |
| `rescue_priority` | 0..10; 0 = none, 1 = most urgent. ≥ 1 exactly when the action is `rescue_flag` or `both` |
| `confidence` | 0..1, `null` unless decided |
| `sms_status` | `not_requested` / `sent` (gateway accepted) / `failed` / `not_configured` (AI asked for SMS, no gateway: NOTHING was sent) |
| `sms_sent` | true iff `sms_status == sent` |
| `rescue_flag` | true iff action ∈ {`rescue_flag`, `both`} — in ANY zone |
| `rescue_status` | `not_requested` / `recorded` (persisted to `rescue_flags`) / `failed` |

Every located device produces at least two frames: `triaged`, then `decided`
or `decision_failed` (a device whose location lookup fails is skipped and
counted in `location_failed`). The schema encodes these "iff / null unless" rules with
`if/then/else`, so an inconsistent frame is invalid, not just odd.

#### Zone bands

`event_start.zone_bands` gives the OUTER edge of each band as a fraction of
`radius_km` (Go `zones` package constants, also served by `GET /capabilities`):

| Zone | Distance from epicentre | `zone_bands` | Risk |
|---|---|---|---|
| `red` | ≤ 0.33 × `radius_km` | `0.33` | Critical — immediate danger |
| `orange` | ≤ 0.66 × `radius_km` | `0.66` | High — evacuation recommended |
| `green` | ≤ 1.0 × `radius_km` | `1.0` | Moderate — alert and monitor |

The values are pinned in `ws_update.json` at
`definitions.ZoneBands.properties.<zone>.const`; dashboard fallbacks and the Go
constants are contract-tested against them. Go may encode `1.0` as `1`.

#### Errors and the fatal rule

`code` ∈ `CAMARA_TIMEOUT | CAMARA_ERROR | AGENT_ERROR | AGENT_INVALID_RESPONSE |
SMS_FAILED | DB_ERROR | QOS_FAILED | INTERNAL_ERROR`; `stage` ∈ `lookup |
context | triage | decision | dispatch | pipeline`; `phone` is E.164 when the
error is device-specific, else `""`. `message` never contains a phone number
(upstream text is redacted), and neither does a narrative — the schema rejects
any run of 8+ digits in both.

**`fatal == true` iff the pipeline stops because of this error.** A fatal error
is always followed by `event_complete` with `status: "failed"` and
`fatal_error: {code, message}`. The code never implies fatality: the same code
can be fatal in one place and not in another.

| Code | Typical source | Usually |
|---|---|---|
| `CAMARA_TIMEOUT` / `CAMARA_ERROR` | location / reachability / congestion lookups | non-fatal: device skipped (location) or NOT_CONNECTED assumed (reachability) |
| `AGENT_ERROR` / `AGENT_INVALID_RESPONSE` | agent transport error / response rejected by `ValidateAgentResponse` | non-fatal: every device of that batch becomes `decision_failed` |
| `SMS_FAILED` | SMS gateway rejected a message | non-fatal |
| `DB_ERROR` | device lookup (fatal) · shelter query, rescue flag, device log (non-fatal) | depends on stage |
| `QOS_FAILED` | QoS on Demand request / upgrade | non-fatal |
| `INTERNAL_ERROR` | `PIPELINE_TIMEOUT_SEC` exceeded, internal fault | fatal |

#### `event_complete` status

| `status` | When |
|---|---|
| `completed` | no failures (every `failures.*` is 0) |
| `completed_with_failures` | any `failures.*` > 0 |
| `no_devices` | `devices_in_radius == 0` |
| `failed` | a fatal error stopped the pipeline; `fatal_error` is set |

`sms_not_sent_no_gateway` counts decisions that asked for SMS while no gateway
is configured. It does not by itself turn `completed` into
`completed_with_failures`, but the UI must state it ("N SMS not sent — no SMS
gateway configured").

### Connection flow: snapshot, live stream, heartbeat, completion

```
client connects ─▶ snapshot_begin {head_seq, active, lifecycle}      seq 0
                   ┌ replayed frames (replay: true, original seq + timestamp):
                   │ 1. event_start
                   │ 2. event_context (latest)
                   │ 3. device_update — latest frame of EVERY phone, seq ascending
                   │ 4. zone_summary (latest)
                   │ 5. narrative_update — latest per zone: red, orange, green
                   │ 6. error — the most recent ≤ 100, seq ascending
                   └ 7. event_complete (if the held event finished)
                   snapshot_end {head_seq, replayed}                  seq 0
live frames ─────▶ seq > head_seq, no gap, no duplicate
every 15 s ──────▶ heartbeat {head_seq, active, lifecycle}            seq 0
event ends ──────▶ event_complete (exactly once), then nothing for that event
```

- `snapshot_begin` is the FIRST frame on every connection. Its `event_id` is the
  event the supervisor holds — running, or the last finished one (retained
  until the next event starts) — or `""` when it holds none.
- Categories that do not exist yet are skipped. Registration and snapshot
  happen atomically with publishing, so nothing is lost between them.
- A supervisor restart loses the held event: a reconnecting client then gets
  `snapshot_begin` with `event_id: ""` and must say the event is no longer held.
- A client too slow to keep up is disconnected (close code 1013); on reconnect
  its new snapshot restores the exact state. Frames are never silently dropped.

### Client obligations (dashboard)

- **Validate every frame** before touching state (this schema is the
  reference). Invalid frames are counted and dropped, never crash the console
  and never refresh the "last frame" freshness clock.
- **Gate by event.** Event frames must match the active `event_id`; others are
  counted `foreign`. A frame for an event whose `event_start` was never
  received is NOT adopted — it is counted foreign and triggers a resync.
- **Sequence.** Live frames with `seq ≤ lastSeq` are `duplicate` (dropped,
  counted); `seq > lastSeq + 1` is a gap (counted, frame applied, resync
  requested). Inside a snapshot, ordering is not checked; at `snapshot_end`
  `lastSeq = head_seq`. A heartbeat whose `head_seq` is greater than the last
  seq seen also means frames were lost.
- **Resync** = close the socket and reconnect (the new snapshot restores exact
  state). At most one resync per 5 s.

---

## Supervisor HTTP API

### `POST /sensor` — body: `sensor_input.json`

Checks run in this order; every response is JSON (`Content-Type:
application/json`).

| Status | Body | When |
|---|---|---|
| 405 | — (`Allow: POST, OPTIONS`) | method is not POST (OPTIONS is the CORS preflight) |
| 403 | `{"error":"origin_not_allowed"}` | an `Origin` header is present and not allowed |
| 415 | error JSON | media type is not `application/json` (parameters such as charset are fine) |
| 413 | error JSON | body larger than `SENSOR_MAX_BODY_BYTES` (default 16384) |
| 400 | `{"error":"invalid_json","detail":"…"}` | not exactly one JSON object, trailing content, syntax error |
| 422 | `{"error":"validation_failed","fields":{"<json path>":"<reason>"}}` | field validation failed: missing field (`"required"`), unknown field (`"unknown field"`), range/enum/pattern violation, or a disaster type that is not operational (`"unsupported: not implemented by this supervisor"`) |
| 409 | `{"error":"pipeline_busy","active_event_id":"…"}` | a DIFFERENT event is running (single incident) |
| 200 | `{"status":"duplicate","event_id":"…","lifecycle":"…"}` | same `event_id` as the held event with an IDENTICAL payload; nothing started |
| 409 | `{"error":"event_id_conflict","event_id":"…","detail":"…"}` | same `event_id` with a different payload, or the id already exists in the `events` table (e.g. used before a restart) |
| 503 | `{"error":"database_unavailable"}` | inserting the event failed |
| 202 | `{"status":"accepted","event_id":"…","contract_version":2}` | pipeline started — **accepted, not completed**; progress arrives as WebSocket frames |

Field rules (mirrored by `sensor_input.json`): `event_id` 1..64 chars,
`^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$`; `disaster_type` ∈ earthquake / flood /
heatwave and operational (today only earthquake); `timestamp` integer > 0
(Unix ms); `severity` 0..10; `epicenter.latitude` −90..90,
`epicenter.longitude` −180..180; `radius_km` > 0 and ≤ 500; `depth_km` 0..800;
`aftershock_risk` LOW / MEDIUM / HIGH; `tsunami_risk` boolean. All numbers
finite; all nine fields required.

### `GET /capabilities`

```json
{
  "contract_version": 2,
  "disaster_types": { "earthquake": "operational", "flood": "unsupported", "heatwave": "unsupported" },
  "limits": {
    "event_id_max_length": 64,
    "severity": { "min": 0, "max": 10 },
    "radius_km": { "exclusive_min": 0, "max": 500 },
    "depth_km": { "min": 0, "max": 800 }
  },
  "zone_bands": { "red": 0.33, "orange": 0.66, "green": 1.0 },
  "single_incident": true
}
```

Clients offer only `operational` types; the supervisor validates regardless.

### `GET /health` (readiness) and `GET /livez` (liveness)

`/livez` → 200 text `ok` while the process serves. `/health` → HTTP 200 when
every check is ok, else 503:

```json
{
  "status": "ready",
  "contract_version": 2,
  "checks": {
    "database": { "ok": true, "latency_ms": 2 },
    "agent":    { "ok": true, "latency_ms": 5 },
    "camara":   { "ok": true, "mode": "mock", "checked": true, "latency_ms": 1 }
  },
  "pipeline": { "event_id": "…", "lifecycle": "running", "active": true },
  "websocket": { "clients": 1, "frames_published": 120, "slow_client_disconnects": 0, "max_queue_depth": 44 }
}
```

A failed check carries `"ok": false, "error": "<short reason, no secrets or
phones>"`. Checks run concurrently with a 2 s timeout each. The agent check is
`GET` on the agent URL with `/decide` replaced by `/health`; the CAMARA check
probes `<MOCK_NOKIA_NAC_BASE_URL>/health` in mock mode and is reported as
`{ "ok": true, "mode": "real", "checked": false }` (not probed) in real mode.

`/sensor`, `/health` and `/capabilities` send CORS headers to allowed origins
(`ALLOWED_ORIGINS`); `/ws` refuses disallowed origins with 403.

---

## AI agent boundary (`ai_request.json` / `ai_response.json`)

Go groups triaged devices by its own zone in the order red, orange, green,
sorts each zone by `distance_km` (then phone) and splits it into batches of at
most 20 (`AGENT_BATCH_SIZE`). **A request never mixes zones.** `batch_index`
starts at 0 and increments per request, so a large zone takes several batches.

| Action | SMS requested | Rescue flagged |
|---|---|---|
| `sms` | ✅ | ❌ |
| `rescue_flag` | ❌ | ✅ |
| `both` | ✅ | ✅ |
| `none` | ❌ | ❌ |

`rescue_priority`: `0` = not flagged, `1–10` = flagged (1 = highest urgency,
dispatched first).

Go rejects a whole response (`AGENT_INVALID_RESPONSE`, every device of the
batch becomes `decision_failed`) when: `event_id` or `zone` differ from the
request; the decision count differs from the device count; a phone is
unknown, duplicated or missing; `action` or `zone_confirmed` is not a valid
value; `zone_escalated` is false but `zone_confirmed` differs from the device
zone, or true but `zone_confirmed` is not strictly more severe
(green < orange < red); `rescue_priority` is outside 0..10, 0 for a rescue
action, or > 0 for a non-rescue action; an `sms`/`both` action has an empty
`sms_message`; `confidence` is outside 0..1.

`DeviceDecision` has no `shelter_name`: the agent never sends one and the SMS
text names the shelter itself.

---

## Migration from v1

Breaking changes in v2 (details in [`../CHANGELOG.md`](../CHANGELOG.md)):

**WebSocket envelope**
- New required fields `v` (= 2), `seq` and `replay`; all seven envelope fields
  are required and no others are allowed.
- `ws_update.json` is a `oneOf` over per-type frame definitions; `examples` is
  an array of complete frames (the v1 examples were a keyed object that did not
  validate).
- New frame types: `snapshot_begin`, `snapshot_end`, `heartbeat` (control, seq
  0), `event_context`, `event_complete`. Every connection starts with a
  snapshot; clients must implement the sequence/gap/duplicate rules.

**Payloads**
- `event_start`: adds `depth_km`, `sensor_timestamp`, `zone_bands`;
  `radius_km` must be > 0 and ≤ 500 (was ≥ 0).
- `device_update`: is now the FULL device state. Adds `location_accuracy_m`,
  `distance_km`, `reachability_status`, `reachability_assumed`, `stage`,
  `action`, `zone_escalated`, `escalated_zone`, `rescue_priority`,
  `confidence`, `sms_status`, `rescue_status`. Each device sends ≥ 2 frames.
  `sms_sent` is true only when the gateway accepted the message (v1 reported
  sends that never happened); `rescue_flag` is independent of zone.
- `zone_summary`: the flat `red_total`, `red_reachable`, `red_rescue`,
  `orange_*`, `green_*` fields are replaced by nested `red` / `orange` /
  `green` `ZoneStats` objects plus `devices_in_radius`, `triaged`,
  `location_failed`. It is cumulative replacement state, not an increment.
- `narrative_update`: adds `batch_index`; max 2000 chars; phone numbers masked.
- `error`: adds `stage`; new codes `CAMARA_ERROR`, `AGENT_INVALID_RESPONSE`,
  `INTERNAL_ERROR`; `phone` must be E.164 or `""`; `message` never contains a
  phone number. The fatal rule changed: `fatal` is true iff the pipeline
  stops, and is always followed by `event_complete {status: "failed"}`.
  `AGENT_ERROR` and a failed shelter query are no longer fatal.
- Shelters appear in `event_context` (≤ 3 nearest, no occupancy) instead of
  being hard-coded in the dashboard.

**`POST /sensor`**
- `sensor_input.json`: `event_id` limited to 1..64 chars and
  `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$`; `radius_km` > 0 and ≤ 500; `depth_km`
  ≤ 800; `timestamp` ≥ 1. Unknown fields are rejected.
- Only operational disaster types are accepted (today earthquake); flood and
  heatwave get 422.
- Responses: 202 means accepted (not completed); new 409 `pipeline_busy` /
  `event_id_conflict`, 200 `duplicate`, 413, 415, 422 `validation_failed`
  with per-field reasons, 503 `database_unavailable`.
- New endpoints: `GET /capabilities`, `GET /livez`; `GET /health` is a JSON
  readiness report.

**Other contracts**
- `ai_request.json`: `devices` has `maxItems: 20` (the batch limit Go and the
  agent already enforced).
- `camara_device.json`: the top level is a `oneOf` over its five shapes and
  `examples` holds one instance of each (v1 had a single keyed bundle).
- The Go `DeviceDecision.ShelterName` field (never part of `ai_response.json`)
  is removed; `ai_response.json` is unchanged.

---

## Canonical source and copies

`contracts/` (this repository) is the **only** place contracts are edited.
Services keep byte-identical copies so each repository builds and tests alone:

| Copy | Of |
|---|---|
| `supervisor/contracts/{ai_request,ai_response,camara_device,sensor_input,ws_update}.json` | `examples/*.json` |
| `supervisor/contracts/README.md` | a generated pointer back to this document |
| `agent/contracts/examples/{ai_request,ai_response}.json` | `examples/ai_request.json`, `examples/ai_response.json` |

After editing a canonical file run, from the directory that holds `contracts/`,
`supervisor/` and `agent/` (the development tree or `deploy/`):

```sh
sh contracts/sync.sh           # copy canonical -> copies
sh contracts/sync.sh --check   # exit 1 and list every drifted copy
```

Drift is also caught by the service tests whenever the canonical directory is
present: `go test ./internal/contracts/` (supervisor), `python3
tests/validate_contract.py` (agent: byte equality + Pydantic field sets) and
the dashboard contract test (`src/lib/contract.test.js`).

---

## Development fixtures

The supervisor's development database and mock CAMARA cover **two fixture
geographies**:

| Area | Phones | Fixture epicentre |
|---|---|---|
| Casablanca | `+212600000001` … `+212600000040` | 33.5731, −7.5898 |
| Budapest | `+36719991001` … `+36719991040` | 47.4979, 19.0402 |

These are DEVELOPMENT FIXTURES (seeded only when the Postgres volume is first
created), not real subscribers. An event outside the seeded coverage
**correctly** finds zero devices and completes with `status: "no_devices"` —
that is not a bug. The `ws_update.json`, `camara_device.json` and
`sensor_input.json` examples use the Casablanca fixtures (`sensor_input.json`
also has a Budapest one). The `ai_request.json` / `ai_response.json` examples
are the agent team's illustrative Rabat batch: they show the two shapes, not a
matched request/response pair (the response has two decisions for a
one-device request, which `ValidateAgentResponse` would reject).

---

## Who owns what

- Ilias (Go)     → produces ai_request.json, consumes ai_response.json
- Yassine (Python) → consumes ai_request.json, produces ai_response.json
- Saad / Ayoub (Dashboard)  → consumes ws_update.json
- Houssam (DevOps) → validates all contracts in integration tests
