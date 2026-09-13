# Contracts changelog

The contract version is the integer carried by WebSocket frames (`v`), by
`POST /sensor` 202 replies and `GET /capabilities` / `GET /health`
(`contract_version`), and by the `x-contract-version` keyword of the
versioned schemas. Full documentation: [`docs/README.md`](docs/README.md).

## v2 — 2026-09-12

Event-driven dashboard contract. **Breaking** for every WebSocket client and
for `POST /sensor` callers; the AI agent wire format is unchanged.

### `ws_update.json` (rewritten)
- Frame envelope `{v, type, event_id, seq, timestamp, replay, payload}`: all
  seven fields required, no others. `v` is 2; `seq` is per event (event_start
  = 1, then +1 per frame), 0 on control frames; `replay` marks frames re-sent
  inside a connection snapshot.
- Schema is a `oneOf` over one definition per frame type (`type` const), so
  each frame matches exactly one branch; `additionalProperties: false` on every
  object; `x-contract-version: 2`.
- New control frames `snapshot_begin`, `snapshot_end`, `heartbeat`; new event
  frames `event_context` (area context: devices in radius, ≤ 3 nearest
  shelters with no occupancy, network state, declared `network_source`,
  `sms_gateway`) and `event_complete` (terminal status, failure counters,
  `sms_not_sent_no_gateway`, `fatal_error`).
- `event_start` adds `depth_km`, `sensor_timestamp`, `zone_bands`
  (0.33 / 0.66 / 1.0); `radius_km` is > 0 and ≤ 500.
- `device_update` is the full device state (stage, action, escalation
  annotation, priority, confidence, `sms_status`, `rescue_status`,
  `reachability_status`, `reachability_assumed`, `distance_km`,
  `location_accuracy_m`); consistency rules (e.g. `sms_sent` iff
  `sms_status == sent`, `action` null unless decided) are part of the schema.
- `zone_summary` replaces the flat `*_total` / `*_reachable` / `red_rescue`
  fields with per-zone `ZoneStats` plus `devices_in_radius`, `triaged`,
  `location_failed`; it is cumulative replacement state.
- `narrative_update` adds `batch_index` (max 2000 chars, no phone numbers).
- `error` adds `stage` and the codes `CAMARA_ERROR`, `AGENT_INVALID_RESPONSE`,
  `INTERNAL_ERROR`; `fatal` is true iff the pipeline stops (always followed by
  `event_complete` failed); `message` never contains a phone number.
- `examples` is now an array of valid frames (the v1 keyed object failed the
  deploy checker).

### `sensor_input.json`
- `event_id` 1..64 chars matching `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$`;
  `timestamp` ≥ 1; `radius_km` > 0 and ≤ 500; `depth_km` ≤ 800;
  `x-contract-version: 2`. Only disaster types reported `operational` by the
  new `GET /capabilities` are accepted at runtime (today: earthquake).
- `POST /sensor` replies: 202 accepted (not completed), 200 duplicate, 400,
  403, 405, 409 `pipeline_busy` / `event_id_conflict`, 413, 415, 422
  `validation_failed` with per-field reasons, 503 `database_unavailable`.

### `ai_request.json` / `ai_response.json`
- Field sets unchanged. `ai_request.devices` gains `maxItems: 20`, the batch
  limit the supervisor and the agent already enforced.
- The supervisor's Go-only `DeviceDecision.ShelterName` (never part of this
  contract) is removed.

### `camara_device.json`
- Field sets unchanged. The top level is a `oneOf` over the five shapes and
  `examples` holds one valid instance of each (Casablanca fixture data).

### Tooling
- `sync.sh` copies the canonical files to `supervisor/contracts/` and
  `agent/contracts/examples/`; `sync.sh --check` fails on drift. The
  supervisor, agent and dashboard tests also check copies and field sets
  against the canonical files.

## v1

Initial locked contracts: `sensor_input`, `camara_device`, `ai_request`,
`ai_response`, and `ws_update` with the `{type, event_id, timestamp, payload}`
envelope and the `event_start`, `device_update`, `zone_summary`,
`narrative_update`, `error` messages.
