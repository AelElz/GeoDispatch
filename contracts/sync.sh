#!/bin/sh
# Copy the canonical contracts (contracts/examples/*.json) to the services that
# keep their own copy, so each service repo builds and tests on its own.
#
#   sh contracts/sync.sh           copy canonical -> copies
#   sh contracts/sync.sh --check   compare byte-for-byte; exit 1 listing drift
#
# Run it from anywhere: paths are resolved from this script's location. It
# expects the layout where contracts/, supervisor/ and agent/ are siblings
# (both the development tree and the deploy/ submodule layout). A service
# directory that is not checked out is skipped with a note, not an error.
#
# Copies are never edited by hand: change the canonical file, then run this.
set -eu

usage() {
	echo "usage: sh contracts/sync.sh [--check]" >&2
	exit 2
}

MODE=sync
case "${1:-}" in
"") ;;
--check) MODE=check ;;
*) usage ;;
esac
[ "$#" -le 1 ] || usage

CONTRACTS_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(dirname -- "$CONTRACTS_DIR")
CANON="$CONTRACTS_DIR/examples"

# The supervisor README is a generated pointer rather than a copy of
# docs/README.md: the full document stays in one place and cannot drift.
# --check still compares it byte-for-byte against this text.
supervisor_readme() {
	cat <<'EOF'
# Contracts: synced copies (do not edit)

The JSON files in this directory are byte-identical copies of the canonical
GeoDispatch contracts (contract version 2):

| File | Canonical source |
|---|---|
| `ai_request.json` | `contracts/examples/ai_request.json` |
| `ai_response.json` | `contracts/examples/ai_response.json` |
| `camara_device.json` | `contracts/examples/camara_device.json` |
| `sensor_input.json` | `contracts/examples/sensor_input.json` |
| `ws_update.json` | `contracts/examples/ws_update.json` |

The canonical source is the `contracts` repository: the `contracts/` directory
next to `supervisor/` (in the deploy layout, the `contracts/` submodule). The
contracts, the WebSocket v2 flow and the migration notes are documented in
`contracts/docs/README.md` and `contracts/CHANGELOG.md`.

To change a contract, edit the canonical file and run `sh contracts/sync.sh`.
`sh contracts/sync.sh --check` compares every checked-out service copy with
the canonical files and exits 1 when any copy has drifted.
EOF
}

DRIFT=""
CHANGED=0

rel() {
	case "$1" in
	"$ROOT"/*) printf '%s\n' "${1#"$ROOT"/}" ;;
	*) printf '%s\n' "$1" ;;
	esac
}

# copy_one <canonical file> <copy>
copy_one() {
	src=$1
	dst=$2
	if [ ! -f "$src" ]; then
		echo "error: canonical file missing: $(rel "$src")" >&2
		exit 1
	fi
	if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
		return 0
	fi
	if [ "$MODE" = check ]; then
		DRIFT="$DRIFT
  $(rel "$dst")"
	else
		cp "$src" "$dst"
		echo "synced $(rel "$dst")"
		CHANGED=$((CHANGED + 1))
	fi
}

# service_ready <service root> <copy dir>: notes the skip and returns 1 when
# the service is not checked out; creates the copy dir in sync mode.
service_ready() {
	if [ ! -d "$1" ]; then
		echo "skip $(rel "$1")/ (not checked out here)"
		return 1
	fi
	if [ ! -d "$2" ] && [ "$MODE" = sync ]; then
		mkdir -p "$2"
	fi
	return 0
}

SUP="$ROOT/supervisor/contracts"
if service_ready "$ROOT/supervisor" "$SUP"; then
	for name in ai_request ai_response camara_device sensor_input ws_update; do
		copy_one "$CANON/$name.json" "$SUP/$name.json"
	done
	if [ -f "$SUP/README.md" ] && supervisor_readme | cmp -s - "$SUP/README.md"; then
		:
	elif [ "$MODE" = check ]; then
		DRIFT="$DRIFT
  $(rel "$SUP/README.md")"
	else
		supervisor_readme >"$SUP/README.md"
		echo "synced $(rel "$SUP/README.md")"
		CHANGED=$((CHANGED + 1))
	fi
fi

AGT="$ROOT/agent/contracts/examples"
if service_ready "$ROOT/agent" "$AGT"; then
	for name in ai_request ai_response; do
		copy_one "$CANON/$name.json" "$AGT/$name.json"
	done
fi

if [ "$MODE" = check ]; then
	if [ -n "$DRIFT" ]; then
		echo "contract copies differ from contracts/examples (run: sh contracts/sync.sh):$DRIFT" >&2
		exit 1
	fi
	echo "contract copies match the canonical files"
	exit 0
fi

if [ "$CHANGED" -eq 0 ]; then
	echo "contract copies already up to date"
fi
