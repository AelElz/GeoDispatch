# GeoDispatch Deploy Manual

This guide explains the deploy repository by workflow: what each command does,
why it exists, what it verifies, and how to interpret failures.

Run commands from the repository root:

```bash
cd /home/kojack/Desktop/deploy
```

## 1. Repository responsibility

`deploy` is the integration layer. It combines four Git submodules with the
root Docker Compose configuration, environment wiring, validation, CI, and
handoff documentation.

| Component | Responsibility | Owner |
|---|---|---|
| `supervisor/` | Go orchestration, CAMARA lookup, zone assignment, dispatch | Ilias |
| `agent/` | Python AI decisions for device batches | Yassine |
| `dashboard/` | SolidJS/Leaflet operator interface | Saad / Ayoub |
| `contracts/` | Shared JSON schemas and message examples | Shared |

The architectural rule is: Go assigns danger zones; the AI agent chooses
actions; the dashboard displays results. Deploy work should preserve that split.

## 2. First-time setup

### Clone and initialize

```bash
git clone --recurse-submodules https://github.com/geoDispatch/deploy.git
cd deploy
```

`--recurse-submodules` downloads the exact service commits recorded by the
parent repository. If the repository is already cloned, run:

```bash
make init
```

`make init` runs `git submodule update --init --recursive`. It repairs missing
submodules without selecting arbitrary latest service code.

### Create local configuration

```bash
make prepare
```

This creates the root `.env` and, when available, `supervisor/.env` from their
templates. Existing files are not overwritten. `.env` is ignored by Git and
must not contain credentials that are committed or copied into templates.

## 3. Configuration and service addresses

Edit the local `.env` after `make prepare` when defaults are not suitable:

- `INTEGRATION_AGENT_URL`: supervisor decision endpoint; default
  `http://app:8000/decide`.
- `INTEGRATION_DATABASE_URL`: supervisor PostgreSQL connection.
- `MOCK_CAMARA_PORT`: local CAMARA fallback host port; default `8081`.
- `NOKIA_NAC_API_KEY`, `NOKIA_NAC_BASE_URL`, `NOKIA_NAC_HOST`, and
  `NOKIA_NAC_TOKEN`: optional official CAMARA sandbox settings. Empty API key
  means use the local fallback.
- `DASHBOARD_PORT`: dashboard host port; default `3000`.
- `DASHBOARD_WS_URL`: browser WebSocket address; default
  `ws://localhost:3000/ws`.

The root Compose override intentionally routes the integrated supervisor to
`app`, `postgres`, and the supervisor-owned CAMARA fallback, not a standalone
mock agent.

Expected host endpoints:

| Service | Endpoint | Meaning |
|---|---|---|
| Dashboard | <http://localhost:3000> | Operator UI |
| Supervisor | <http://localhost:8080/health> | Go health endpoint |
| Agent | <http://localhost:8000/health> | AI health endpoint |
| CAMARA fallback | <http://localhost:8081/qos> | Local network API health |
| PostgreSQL | `localhost:5432` | Supervisor persistence |

## 4. Build, run, inspect, and stop

### Build only

```bash
make build
```

Prepares configuration and runs `docker compose build`. Use it to find
Dockerfile or dependency problems without starting containers.

### Start the integrated stack

```bash
make up
```

Prepares configuration, builds images, and runs `docker compose up -d --build`.
`-d` leaves services in the background; `--build` includes local source edits.

### Inspect containers

```bash
make status
```

This runs `docker compose ps`. It shows running, restarting, unhealthy, and
exited containers, but does not replace endpoint health checks.

### Follow logs

```bash
make logs
docker compose logs -f supervisor
docker compose logs -f dashboard
```

`make logs` follows every service. Service-specific commands narrow diagnosis.
`Ctrl-C` stops log streaming only; it does not stop containers.

### Stop while preserving volumes

```bash
make down
```

This removes containers and the Compose network but preserves named database
and model volumes.

## 5. Fast validation checks

### Run the unified fast suite

```bash
make check
```

This runs `python3 scripts/check.py`, prints green `PASS`, red `FAIL`, or
yellow `SKIP`, and returns a non-zero exit code if any required check fails.
It is the normal pre-commit and CI entry point.

The suite performs four checks:

1. **Compose configuration** — `docker compose config --quiet` merges the root
   and included service definitions without starting containers. It catches
   invalid YAML, missing includes, and unresolved Compose wiring.
2. **Static deploy smoke checks** — `scripts/smoke_check.py` repeats Compose
   rendering and confirms static deploy configuration works without requiring
   running services.
3. **Contract schemas and examples** — `scripts/validate_contracts.py`
   discovers every contract JSON file, checks Draft 7 schema validity, and
   validates every embedded example. This protects service message boundaries.
4. **Whitespace and patch errors** — `git diff --check` catches trailing
   whitespace and malformed patch whitespace before review.

Plain output is available when needed:

```bash
python3 scripts/check.py --no-color
```

The `NO_COLOR=1` environment variable also disables ANSI colors.

### Run individual checks

```bash
make smoke-check
docker compose config --quiet
git diff --check
make contract-check
```

`make smoke-check` is the static-only deploy check. `docker compose config
--quiet` answers only whether Compose can render. `git diff --check` validates
patch hygiene. `make contract-check` intentionally fails on invalid schemas or
examples; never weaken it to hide a contract defect.

## 6. Full tests and runtime checks

### Run the full suite

```bash
make test
```

This runs `python3 scripts/check.py --test`: all fast checks, then runtime
health probes and available component tests. It returns non-zero for a real
failure, so it can be used in CI.

The additional checks are:

- **Live health probes** — requests the dashboard root, agent `/health`,
  supervisor `/health`, and CAMARA `/qos`. This proves the running stack is
  reachable, not merely syntactically valid.
- **Supervisor Go tests** — runs `go test ./...` when `supervisor/go.mod` and
  the Go toolchain are available.
- **Dashboard tests** — runs `npm test -- --run` when `npm` and
  `dashboard/interface/node_modules` are available; otherwise reports a
  yellow skip and explains that `npm ci` is needed first.

Start the stack before runtime probes:

```bash
python3 scripts/smoke_check.py --running
```

This first renders Compose, then probes each endpoint listed above. A
connection error means the stack is unavailable; inspect `make status` and
service logs before changing application code.

## 7. Update submodules safely

Inspect state before updating:

```bash
git status --short --branch
git submodule status
```

Update only through fast-forward merges:

```bash
make update-submodules
```

The target fetches each submodule's `origin/main` and runs `git merge
--ff-only`, preventing accidental merge commits or silent overwrite of local
service work.

Review the parent gitlink changes afterward:

```bash
git diff --submodule=log
git status --short
```

Pulling a submodule does not update the parent commit automatically. The parent
must intentionally commit the new gitlink pointers.

## 8. Cleanup and rebuild

```bash
make clean
```

Runs `docker compose down --volumes --rmi local`. It removes containers,
volumes, and locally built images, including local database/model data. Use it
only when a destructive clean rebuild is intended.

```bash
make fclean
```

Convenience alias for `make clean`; it is not safer than `make clean`.

```bash
make re
```

Runs `make fclean`, then the default `make all` target (`prepare`, `build`, and
`up`) to reproduce a clean first-start environment.

## 9. CI and handoff

`.github/workflows/deploy.yml` runs on pushes to `main` and pull requests. It
checks out recursive submodules, installs the contract dependency, runs
`make smoke-check`, and runs `make contract-check`. CI therefore catches both
Compose integration breakage and contract incompatibilities.

Before handoff:

```bash
make check
git diff --check
git diff --submodule=log
git status --short --branch
```

Then update `codex-logChanges.md` with the change, reason, and evidence;
`WORKING_STATUS.md` with current and next work; and `issuesProgress.md` with
open, blocked, in-progress, and fixed issues.

## 10. Boundaries and troubleshooting

The deploy owner maintains Compose wiring, environment integration, CI, health
checks, smoke checks, and contract validation. Do not fix Go, Python, or
SolidJS application logic here; report service defects to their owners.

Do not change a shared contract schema or example until the contracts owner
confirms the intended message shape. A failing contract check is evidence of an
integration problem.

If Docker reports permission errors for `/var/run/docker.sock`, static checks
can still run, but image builds and live probes must wait for Docker access. If
the known WebSocket contract mismatch fails `make check` or `make test`, keep
the failure visible and coordinate with the contracts owner.
