#!/usr/bin/env python3
"""Monitored entrypoint for bounded LinkedIn outreach runs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = Path("/tmp/linkedin_outreach_run_state.json")
LOG_DIR = Path("/tmp/linkedin_outreach_monitor_logs")
SYSTEMIC_BLOCKER_TERMS = (
    "apple event error -1743",
    "browser access blocker",
    "chrome computer use unavailable",
    "computer use access denied",
    "computer use approval denied",
    "computer use itself is unavailable",
    "linkedin login",
    "linkedin signed out",
)


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"items": []}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def state_counts() -> dict[str, int]:
    counts = {"queued": 0, "labeled": 0, "verified": 0, "sent": 0, "manual": 0, "blocked": 0, "skipped": 0}
    for item in load_state().get("items", []):
        state = str(item.get("state") or "")
        if state in counts:
            counts[state] += 1
    return counts


def has_systemic_blocker() -> bool:
    for item in load_state().get("items", []):
        if item.get("state") not in {"manual", "blocked"}:
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
    parser = argparse.ArgumentParser(description="Monitor and restart LinkedIn outreach batches.")
    parser.add_argument("--resume", action="store_true", help="Use the existing state file; skip build")
    parser.add_argument("--contact-type", choices=("engineer", "recruiter"), default="engineer")
    parser.add_argument("--mode", choices=("label", "verify", "send"), default="label")
    parser.add_argument("--limit", type=int, default=0, help="Optional build limit")
    parser.add_argument("--max-restarts", type=int, default=3, help="Retries after a stopped run with queued rows")
    parser.add_argument("--restart-sleep", type=int, default=10, help="Seconds to wait before retrying")
    parser.add_argument("--batch-size", type=int, default=3, help="Rows per fresh Codex process")
    parser.add_argument("--max-batches", type=int, default=0, help="Forwarded to run_batches.py")
    parser.add_argument("--model", default="gpt-5.5", help="Forwarded to run_batches.py")
    parser.add_argument("--timeout", type=int, default=1200, help="Forwarded to run_batches.py")
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
    print(f"linkedin-outreach monitor log: {log_path}")

    if not args.resume:
        build_cmd = [
            "python3",
            "skills/linkedin-outreach/scripts/build_script_state.py",
            "--contact-type",
            args.contact_type,
            "--mode",
            args.mode,
        ]
        if args.limit:
            build_cmd.extend(["--limit", str(args.limit)])
        build_rc = run_and_tee(build_cmd, log_path)
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
            "-u",
            "skills/linkedin-outreach/scripts/run_batches.py",
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
            f"labeled {before['labeled']} -> {after['labeled']}, "
            f"verified {before['verified']} -> {after['verified']}, "
            f"sent {before['sent']} -> {after['sent']}, "
            f"manual {before['manual']} -> {after['manual']}, "
            f"blocked {before['blocked']} -> {after['blocked']}"
        )

        if after["queued"] == 0:
            print("\nQueue drained.")
            return rc
        if args.max_batches:
            print("\nStopped because --max-batches was set.")
            return rc
        if has_systemic_blocker():
            print("\nSystemic browser/LinkedIn blocker detected; leaving queued rows untouched.")
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
