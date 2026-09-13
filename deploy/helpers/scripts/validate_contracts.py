#!/usr/bin/env python3
"""Validate every JSON Schema and embedded example in the contracts submodule.

The checker deliberately discovers schemas instead of keeping a hard-coded
list. Adding, removing, or evolving a contract only requires updating the
contracts submodule; this command will pick it up automatically.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft7Validator, FormatChecker
    from jsonschema.exceptions import SchemaError
except ImportError:
    sys.exit(
        "Missing dependency: install with "
        "python3 -m pip install -r requirements-contract.txt"
    )


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"


def fail(path: Path, message: str) -> None:
    print(f"FAIL {path.relative_to(ROOT)}: {message}")


def main() -> int:
    if not CONTRACTS.is_dir():
        fail(CONTRACTS, "contracts submodule is missing; run `make init`")
        return 1

    files = sorted(CONTRACTS.rglob("*.json"))
    if not files:
        fail(CONTRACTS, "no JSON contract files found")
        return 1

    failures = 0
    checked = 0
    examples_checked = 0

    for path in files:
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            fail(path, f"invalid JSON ({exc})")
            failures += 1
            continue

        if not isinstance(schema, dict):
            fail(path, "a contract schema must be a JSON object")
            failures += 1
            continue

        # The repository currently uses Draft 7. Keeping this check explicit
        # prevents silently validating a future schema with the wrong rules.
        if schema.get("$schema") != "http://json-schema.org/draft-07/schema#":
            fail(path, "expected JSON Schema Draft 7 declaration")
            failures += 1
            continue

        try:
            Draft7Validator.check_schema(schema)
            validator = Draft7Validator(schema, format_checker=FormatChecker())
        except SchemaError as exc:
            fail(path, f"invalid Draft 7 schema ({exc.message})")
            failures += 1
            continue

        checked += 1
        examples = schema.get("examples", [])
        if not isinstance(examples, list):
            fail(path, "examples must be an array when present")
            failures += 1
            continue

        for index, example in enumerate(examples):
            errors = sorted(validator.iter_errors(example), key=lambda error: list(error.path))
            if errors:
                fail(path, f"example {index} violates schema: {errors[0].message}")
                failures += 1
            else:
                examples_checked += 1

    if failures:
        print(f"Contract check failed: {failures} issue(s) across {len(files)} file(s).")
        return 1

    print(f"Contract check passed: {checked} Draft 7 schema(s), {examples_checked} example(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
