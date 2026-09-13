#!/usr/bin/env python3
"""Run deterministic deploy checks against the rendered or running stack."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def ensure_env() -> None:
    env_file = ROOT / ".env"
    example_env = ROOT / ".env.example"
    if not env_file.is_file() and example_env.is_file():
        shutil.copyfile(example_env, env_file)

    supervisor_env = ROOT / "supervisor" / ".env"
    supervisor_example = ROOT / "supervisor" / ".env.example"
    if not supervisor_env.is_file() and supervisor_example.is_file():
        shutil.copyfile(supervisor_example, supervisor_env)


def run_config() -> None:
    ensure_env()
    result = subprocess.run(
        ["docker", "compose", "config", "--quiet"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "docker compose config failed")
    print("PASS compose configuration")


def check_http(url: str) -> None:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}")
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError(f"{url}: {exc}") from exc
    print(f"PASS {url}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--running",
        action="store_true",
        help="also probe service health endpoints; requires the stack to be running",
    )
    args = parser.parse_args()

    try:
        run_config()
        if args.running:
            for url in (
                "http://localhost:3000/",
                "http://localhost:8000/health",
                "http://localhost:8080/health",
                "http://localhost:8081/qos",
            ):
                check_http(url)
        else:
            print("PASS static smoke checks (use --running for health probes)")
    except RuntimeError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
