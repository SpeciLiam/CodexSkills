#!/usr/bin/env python3
"""Chat-friendly monitor for linkedin-apply-all queue workers."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = Path("/tmp/linkedin_apply_all_state.json")
LOG_DIR = Path("/tmp/linkedin_apply_all_monitor_logs")
DONE_STATES = {
    "submitted",
    "applied",
    "manual",
    "manual_apply_needed",
    "archived",
    "skipped",
    "duplicate",
    "queued_for_tailoring",
}


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"items": [], "search": {}, "runPolicy": {}}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def done_count(state: dict[str, Any]) -> int:
    return sum(1 for item in state.get("items", []) if item.get("state") in DONE_STATES)


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
    parser = argparse.ArgumentParser(description="Monitor LinkedIn apply-all queue workers.")
    parser.add_argument("--resume", action="store_true", help="Reuse existing /tmp state")
    parser.add_argument("--search-url")
    parser.add_argument("--freshness", default="24h", help="24h, week, or month")
    parser.add_argument("--freshness-seconds", type=int)
    parser.add_argument("--worker", choices=("codex", "claude"), default="codex")
    parser.add_argument("--max-jobs", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--missing-resume-policy", choices=("queue_for_tailoring", "tailor", "skip"), default="queue_for_tailoring")
    parser.add_argument("--manual-circuit-breaker", type=int, default=5)
    parser.add_argument("--max-restarts", type=int, default=3)
    parser.add_argument("--restart-sleep", type=int, default=10)
    parser.add_argument("--max-workers", type=int, default=0)
    parser.add_argument("--codex-model")
    parser.add_argument("--claude-model")
    parser.add_argument("--claude-permission", default="acceptEdits")
    parser.add_argument("--timeout", type=int, default=2700)
    parser.add_argument("--child-sandbox", default="danger-full-access", choices=("read-only", "workspace-write", "danger-full-access"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"monitor_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
    print(f"linkedin-apply-all monitor log: {log_path}")

    if not args.resume:
        refresh_rc = run_and_tee(["python3", "skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py"], log_path)
        if refresh_rc != 0:
            return refresh_rc
        build_cmd = [
            "python3",
            "skills/linkedin-apply-all/scripts/build_run_state.py",
            "--freshness",
            args.freshness,
            "--worker",
            args.worker,
            "--max-jobs",
            str(args.max_jobs),
            "--batch-size",
            str(args.batch_size),
            "--missing-resume-policy",
            args.missing_resume_policy,
            "--manual-circuit-breaker",
            str(args.manual_circuit_breaker),
        ]
        if args.search_url:
            build_cmd.extend(["--search-url", args.search_url])
        if args.freshness_seconds is not None:
            build_cmd.extend(["--freshness-seconds", str(args.freshness_seconds)])
        build_rc = run_and_tee(build_cmd, log_path)
        if build_rc != 0:
            return build_rc

    restarts = 0
    while True:
        before = load_state()
        before_done = done_count(before)
        max_jobs = int(before.get("runPolicy", {}).get("maxJobs") or args.max_jobs)
        if before.get("search", {}).get("stopRequested") or before_done >= max_jobs:
            print("Run complete or search saturated.")
            return 0

        cmd = [
            "python3",
            "-u",
            "skills/linkedin-apply-all/scripts/run_queue.py",
            "--batch-size",
            str(args.batch_size),
            "--worker",
            args.worker,
            "--timeout",
            str(args.timeout),
            "--child-sandbox",
            args.child_sandbox,
        ]
        if args.codex_model:
            cmd.extend(["--codex-model", args.codex_model])
        if args.claude_model:
            cmd.extend(["--claude-model", args.claude_model])
        if args.claude_permission:
            cmd.extend(["--claude-permission", args.claude_permission])
        if args.max_workers:
            cmd.extend(["--max-workers", str(args.max_workers)])
        if args.dry_run:
            cmd.append("--dry-run")

        rc = run_and_tee(cmd, log_path)
        after = load_state()
        after_done = done_count(after)
        print(f"\nmonitor progress: done {before_done} -> {after_done}; rc={rc}")

        if after.get("search", {}).get("stopRequested") or after_done >= max_jobs:
            return rc
        if args.max_workers:
            print("Stopped because --max-workers total cap was delegated to run_queue.")
            return rc
        if args.dry_run:
            return rc
        if after_done > before_done and rc == 0:
            restarts = 0
            print("Progress made; continuing.")
            continue

        restarts += 1
        if restarts > args.max_restarts:
            print(f"Stopped after {args.max_restarts} restart attempt(s).")
            return rc or 1
        print(f"Runner stopped without enough progress; retry {restarts}/{args.max_restarts} in {args.restart_sleep}s.")
        time.sleep(args.restart_sleep)


if __name__ == "__main__":
    raise SystemExit(main())
