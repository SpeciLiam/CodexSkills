#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CAPTURE_DIR = Path("/tmp/codexskills-job-intake")
LISTENER = ROOT / "skills" / "job-intake" / "scripts" / "run_job_listener.py"
TAILOR_QUEUE = ROOT / "skills" / "resume-tailor" / "scripts" / "tailor_intake_queue.py"
PROMOTE_READY = ROOT / "skills" / "finish-applications" / "scripts" / "promote_to_ready.py"


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


def parse_listener_summary(stdout: str) -> tuple[int, int]:
    start = stdout.find("{")
    if start < 0:
        return 0, 0
    try:
        summary, _ = json.JSONDecoder().raw_decode(stdout[start:])
    except json.JSONDecodeError:
        return 0, 0
    return int(summary.get("captured", 0)), int(summary.get("newRows", 0))


def parse_count(stdout: str, patterns: tuple[str, ...]) -> int:
    for pattern in patterns:
        match = re.search(pattern, stdout, re.I)
        if match:
            return int(match.group(1))
    return 0


def cleanup(source: str) -> None:
    for path in CAPTURE_DIR.glob(f"{source}_page*.json"):
        path.unlink(missing_ok=True)
    (CAPTURE_DIR / f"{source}_capture.json").unlink(missing_ok=True)
    (CAPTURE_DIR / f"{source}_streak.json").unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize a rolling intake capture into tracker-owned artifacts.")
    parser.add_argument("--source", required=True, choices=["linkedin", "greenhouse"])
    args = parser.parse_args()

    capture_path = CAPTURE_DIR / f"{args.source}_capture.json"
    jobs_path = CAPTURE_DIR / f"{args.source}_jobs.json"
    jobs = json.loads(capture_path.read_text(encoding="utf-8") if capture_path.exists() else "[]")
    if not isinstance(jobs, list):
        raise SystemExit(f"{capture_path} must contain a JSON array")
    jobs_path.write_text(json.dumps(jobs, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    listener_result = run([sys.executable, str(LISTENER), "--sources", args.source])
    if listener_result.returncode != 0:
        sys.stderr.write(listener_result.stderr)
        sys.stdout.write(listener_result.stdout)
        return listener_result.returncode
    captured, new_rows = parse_listener_summary(listener_result.stdout)
    if captured == 0:
        captured = len(jobs)

    tailored = 0
    promoted = 0
    if new_rows:
        if TAILOR_QUEUE.exists():
            tailor_result = run([sys.executable, str(TAILOR_QUEUE), "--max-jobs", "20"])
            if tailor_result.returncode != 0:
                sys.stderr.write(tailor_result.stderr)
                sys.stdout.write(tailor_result.stdout)
                return tailor_result.returncode
            tailored = parse_count(tailor_result.stdout, (r"tailored[^0-9]*(\d+)", r"(\d+)\s+tailored"))
        if PROMOTE_READY.exists():
            promote_result = run([sys.executable, str(PROMOTE_READY), "--auto", "--min-fit", "9"])
            if promote_result.returncode != 0:
                sys.stderr.write(promote_result.stderr)
                sys.stdout.write(promote_result.stdout)
                return promote_result.returncode
            promoted = parse_count(promote_result.stdout, (r"promoted[^0-9]*(\d+)", r"(\d+)\s+promoted"))

    cleanup(args.source)
    print(
        f"FINALIZED {args.source}: {captured} captured, {new_rows} new tracker rows, "
        f"{tailored} tailored, {promoted} promoted to Ready to Apply"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
