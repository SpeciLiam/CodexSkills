#!/usr/bin/env python3
"""Monitored entrypoint for finish-app-script.

This wrapper is intentionally small: refresh/build once, run the rotating
batch runner, and restart it a few times if it stops while queued rows remain.
The batch runner still owns commits and pushes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = Path("/tmp/fa_script_run_state.json")
LOG_DIR = Path("/tmp/fa_script_monitor_logs")
SYSTEMIC_BLOCKER_TERMS = (
    "apple event error -1743",
    "browser access blocker",
    "chrome computer use unavailable",
    "computer use access denied",
    "computer use approval denied",
    "computer use itself is unavailable",
    "appnotfound(\"chrome\")",
)


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"items": []}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def state_counts() -> dict[str, int]:
    counts = {"queued": 0, "submitted": 0, "manual": 0, "archived": 0, "skipped": 0}
    for item in load_state().get("items", []):
        state = str(item.get("state") or "")
        if state in counts:
            counts[state] += 1
    return counts


def has_systemic_blocker() -> bool:
    for item in load_state().get("items", []):
        if item.get("state") != "manual":
            continue
        haystack = " ".join(
            str(item.get(field) or "")
            for field in ("blocker", "result", "notes")
        ).lower()
        if any(term in haystack for term in SYSTEMIC_BLOCKER_TERMS):
            return True
    return False


def run_and_tee(cmd: list[str], log_path: Path) -> int:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n\n[{dt.datetime.now().isoformat(timespec='seconds')}] $ {' '.join(cmd)}\n")
        process = subprocess.Popen(
            cmd,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            log.write(line)
        return process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor and restart finish-app-script batches.")
    parser.add_argument("--resume", action="store_true", help="Use the existing state file; skip refresh/build")
    parser.add_argument("--max-restarts", type=int, default=3, help="Retries after a stopped run with queued rows")
    parser.add_argument("--restart-sleep", type=int, default=10, help="Seconds to wait before retrying")
    parser.add_argument("--batch-size", type=int, default=2, help="Rows per fresh Codex process")
    parser.add_argument("--max-batches", type=int, default=0, help="Forwarded to run_batches.py")
    parser.add_argument("--model", default="gpt-5.5", help="Forwarded to run_batches.py")
    parser.add_argument("--timeout", type=int, default=1800, help="Forwarded to run_batches.py")
    parser.add_argument(
        "--child-sandbox",
        choices=("read-only", "workspace-write", "danger-full-access"),
        default="danger-full-access",
        help="Forwarded to run_batches.py",
    )
    parser.add_argument("--no-commit", action="store_true", help="Forwarded to run_batches.py")
    parser.add_argument("--no-push", action="store_true", help="Forwarded to run_batches.py")
    parser.add_argument("--dry-run", action="store_true", help="Forwarded to run_batches.py")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"monitor_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
    print(f"finish-app-script monitor log: {log_path}")

    if not args.resume:
        refresh_rc = run_and_tee(
            ["python3", "skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py"],
            log_path,
        )
        if refresh_rc != 0:
            return refresh_rc
        build_rc = run_and_tee(
            ["python3", "skills/finish-app-script/scripts/build_queue.py"],
            log_path,
        )
        if build_rc != 0:
            return build_rc

    restarts = 0
    while True:
        before = state_counts()
        if before["queued"] == 0:
            print("\nNo queued rows remain.")
            return 0

        cmd = [
            "python3",
            "skills/finish-app-script/scripts/run_batches.py",
            "--batch-size",
            str(args.batch_size),
            "--model",
            args.model,
            "--timeout",
            str(args.timeout),
            "--child-sandbox",
            args.child_sandbox,
        ]
        if args.max_batches:
            cmd.extend(["--max-batches", str(args.max_batches)])
        if args.no_commit:
            cmd.append("--no-commit")
        if args.no_push:
            cmd.append("--no-push")
        if args.dry_run:
            cmd.append("--dry-run")

        rc = run_and_tee(cmd, log_path)
        after = state_counts()
        print(
            "\nmonitor counts: "
            f"queued {before['queued']} -> {after['queued']}, "
            f"submitted {before['submitted']} -> {after['submitted']}, "
            f"manual {before['manual']} -> {after['manual']}, "
            f"archived {before['archived']} -> {after['archived']}"
        )

        if after["queued"] == 0:
            print("\nQueue drained.")
            return rc
        if args.max_batches:
            print("\nStopped because --max-batches was set.")
            return rc
        if has_systemic_blocker():
            print("\nSystemic browser/Computer Use blocker detected; leaving queued rows untouched.")
            return rc or 2
        if after["queued"] < before["queued"] and rc == 0:
            restarts = 0
            print("\nProgress made and queued rows remain; continuing.")
            continue

        restarts += 1
        if restarts > args.max_restarts:
            print(f"\nStopped after {args.max_restarts} restart attempt(s) without enough progress.")
            return rc or 1
        print(f"\nRunner stopped with queued rows remaining; retry {restarts}/{args.max_restarts} in {args.restart_sleep}s.")
        time.sleep(args.restart_sleep)


if __name__ == "__main__":
    raise SystemExit(main())
