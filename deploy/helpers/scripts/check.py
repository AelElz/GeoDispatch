#!/usr/bin/env python3
"""Run the deploy validation suite with readable colored results.

Fast checks run by default. Pass ``--test`` to include live health probes and
available component test suites. A non-zero exit status means at least one
check failed.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    cwd: Path = ROOT
    optional: bool = False


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def run(check: Check, color: bool) -> bool:
    try:
        result = subprocess.run(
            list(check.command),
            cwd=check.cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        result_output = str(exc)
        result_code = 1
    else:
        result_output = result.stdout.strip()
        result_code = result.returncode

    if result_code == 0:
        label = f"{GREEN}PASS{RESET}" if color else "PASS"
        print(f"[{label}] {check.name}")
        return True

    if check.optional and result_code == 125:
        label = f"{YELLOW}SKIP{RESET}" if color else "SKIP"
        print(f"[{label}] {check.name}")
        return True

    label = f"{RED}FAIL{RESET}" if color else "FAIL"
    print(f"[{label}] {check.name}")
    if result_output:
        for line in result_output.splitlines()[-12:]:
            print(f"       {line}")
    return False


def fast_checks() -> list[Check]:
    return [
        Check("Compose configuration", ("docker", "compose", "config", "--quiet")),
        Check("Static deploy smoke checks", (sys.executable, str(SCRIPT_DIR / "smoke_check.py"))),
        Check("Contract schemas and examples", (sys.executable, str(SCRIPT_DIR / "validate_contracts.py"))),
        Check("Whitespace and patch errors", ("git", "diff", "--check")),
    ]


def test_checks() -> list[Check]:
    checks = [
        Check(
            "Live service health probes",
            (sys.executable, str(SCRIPT_DIR / "smoke_check.py"), "--running"),
        ),
    ]

    if (ROOT / "supervisor" / "go.mod").is_file() and command_exists("go"):
        checks.append(Check("Supervisor Go tests", ("go", "test", "./..."), ROOT / "supervisor"))
    if (ROOT / "agent" / "pyproject.toml").is_file() and command_exists("pytest"):
        checks.append(Check("Agent Python tests", ("pytest", "-q"), ROOT / "agent"))
    if (ROOT / "dashboard" / "interface" / "package.json").is_file() and command_exists("npm"):
        if (ROOT / "dashboard" / "interface" / "node_modules").is_dir():
            checks.append(
                Check(
                    "Dashboard tests",
                    ("npm", "test", "--", "--run"),
                    ROOT / "dashboard" / "interface",
                )
            )
        else:
            checks.append(
                Check(
                    "Dashboard tests (run npm ci first)",
                    ("sh", "-c", "exit 125"),
                    optional=True,
                )
            )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--test",
        action="store_true",
        help="include live health probes and available component test suites",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="disable green/red/yellow output",
    )
    args = parser.parse_args()
    color = not args.no_color and os.environ.get("NO_COLOR") is None

    checks = fast_checks() + (test_checks() if args.test else [])
    failed = 0
    print(f"GeoDispatch deploy checks ({'full' if args.test else 'fast'})")
    for check in checks:
        if not run(check, color):
            failed += 1

    if failed:
        label = f"{RED}FAILED{RESET}" if color else "FAILED"
        print(f"\n{label}: {failed} check(s) failed.")
        return 1

    label = f"{GREEN}SUCCESS{RESET}" if color else "SUCCESS"
    print(f"\n{label}: all checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
