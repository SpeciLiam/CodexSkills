#!/usr/bin/env python3
"""Chat-facing monitor for the LinkedIn early-career weekly workflow."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
STATE_PATH = Path("/tmp/linkedin_early_career_weekly_state.json")
LOCK_PATH = Path("/tmp/linkedin_early_career_weekly_worker.lock")
LOG_DIR = Path("/tmp/linkedin_early_career_weekly_monitor_logs")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"items": [], "search": {}, "runPolicy": {}, "events": []}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def active_lock_detail(path: Path = LOCK_PATH) -> str:
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return f"lock exists at {path}"
    pid = data.get("pid")
    host = data.get("host") or "unknown host"
    created = data.get("createdAt") or "unknown time"
    if isinstance(pid, int):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return ""
        except PermissionError:
            return f"lock active at {path}: pid={pid} host={host} createdAt={created}"
        return f"lock active at {path}: pid={pid} host={host} createdAt={created}"
    return f"lock exists at {path}: host={host} createdAt={created}"


def done_count(state: dict[str, Any]) -> int:
    done_states = {
        "submitted",
        "applied",
        "already_applied",
        "already_submitted",
        "manual",
        "archived",
        "closed",
        "duplicate",
        "skipped",
        "tailor_failed",
    }
    return sum(1 for item in state.get("items", []) if item.get("state") in done_states)


def progress_signature(state: dict[str, Any]) -> str:
    search = state.get("search", {})
    item_bits = []
    for item in state.get("items", []):
        item_bits.append(
            {
                "key": item.get("key") or item.get("postingKey") or item.get("jobUrl"),
                "state": item.get("state"),
                "resumePdf": item.get("resumePdf"),
                "updatedAt": item.get("updatedAt"),
            }
        )
    signature = {
        "done": done_count(state),
        "items": item_bits,
        "search": {
            "currentResultIndex": search.get("currentResultIndex"),
            "lastJobUrl": search.get("lastJobUrl"),
            "visitedCount": len(search.get("visitedJobUrls", []) or []),
            "skippedCount": len(search.get("skippedJobUrls", []) or []),
            "stopRequested": search.get("stopRequested"),
            "saturationReason": search.get("saturationReason"),
        },
    }
    return json.dumps(signature, sort_keys=True, ensure_ascii=True)


def stop_requested(state: dict[str, Any]) -> bool:
    return bool(state.get("search", {}).get("stopRequested"))


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
    parser = argparse.ArgumentParser(description="Monitor LinkedIn early-career weekly stage workers.")
    parser.add_argument("--resume", action="store_true", help="Reuse existing /tmp state")
    parser.add_argument("--max-jobs", type=int, default=0, help="0 means continue until search saturation")
    parser.add_argument("--freshness-seconds", type=int, default=604_800)
    parser.add_argument("--search-url", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--reasoning-effort", default="medium", choices=("minimal", "low", "medium", "high", "xhigh"))
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--child-sandbox", default="danger-full-access", choices=("read-only", "workspace-write", "danger-full-access"))
    parser.add_argument("--max-stages", type=int, default=0)
    parser.add_argument("--max-restarts", type=int, default=0, help="0 means keep restarting while progress is possible")
    parser.add_argument("--restart-sleep", type=int, default=10)
    parser.add_argument("--no-refresh", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"monitor_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
    print(f"linkedin-early-career-weekly monitor log: {log_path}")

    model = args.model or ""

    lock_detail = active_lock_detail()
    if lock_detail:
        raise SystemExit(
            "Refusing to start another LinkedIn weekly monitor while a worker is active: "
            f"{lock_detail}"
        )

    if not args.resume:
        if not args.no_refresh:
            refresh_rc = run_and_tee(
                ["python3", "skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py"],
                log_path,
            )
            if refresh_rc != 0:
                return refresh_rc
        build_cmd = [
            "python3",
            "skills/linkedin-early-career-weekly/scripts/build_run_state.py",
            "--max-jobs",
            str(args.max_jobs),
            "--freshness-seconds",
            str(args.freshness_seconds),
            "--reasoning-effort",
            args.reasoning_effort,
            "--child-sandbox",
            args.child_sandbox,
        ]
        if args.search_url:
            build_cmd.extend(["--search-url", args.search_url])
        if model:
            build_cmd.extend(["--model", model])
        build_rc = run_and_tee(build_cmd, log_path)
        if build_rc != 0:
            return build_rc

    restarts = 0
    while True:
        before = load_state()
        before_done = done_count(before)
        before_signature = progress_signature(before)
        max_jobs = int(before.get("runPolicy", {}).get("maxJobs") or args.max_jobs or 0)

        if stop_requested(before):
            print("Run complete: search saturation requested.")
            return 0
        if max_jobs and before_done >= max_jobs:
            print(f"Run complete: reached max jobs {before_done}/{max_jobs}.")
            return 0

        cmd = [
            "python3",
            "-u",
            "skills/linkedin-early-career-weekly/scripts/run_stages.py",
            "--timeout",
            str(args.timeout),
            "--reasoning-effort",
            args.reasoning_effort,
            "--child-sandbox",
            args.child_sandbox,
        ]
        if model:
            cmd.extend(["--model", model])
        if args.max_stages:
            cmd.extend(["--max-stages", str(args.max_stages)])
        if args.dry_run:
            cmd.append("--dry-run")

        rc = run_and_tee(cmd, log_path)
        after = load_state()
        after_done = done_count(after)
        after_signature = progress_signature(after)
        print(f"\nmonitor progress: done {before_done} -> {after_done}; rc={rc}")

        if args.dry_run:
            return rc
        if stop_requested(after):
            return rc
        if max_jobs and after_done >= max_jobs:
            return rc
        if args.max_stages:
            print("Stopped because --max-stages was set.")
            return rc

        if after_signature != before_signature:
            restarts = 0
            print("Progress made; continuing.")
            continue

        if args.max_restarts == 0:
            print("No meaningful item/search progress; stopping until the blocker changes.")
            return rc or 1

        restarts += 1
        if args.max_restarts and restarts > args.max_restarts:
            print(f"Stopped after {args.max_restarts} restart attempt(s).")
            return rc or 1
        print(f"No new progress; retry {restarts} in {args.restart_sleep}s.")
        time.sleep(args.restart_sleep)


if __name__ == "__main__":
    raise SystemExit(main())
