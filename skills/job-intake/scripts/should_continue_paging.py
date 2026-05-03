#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
APPLICATIONS_MD = ROOT / "application-trackers" / "applications.md"
CAPTURE_DIR = Path("/tmp/codexskills-job-intake")
SEEN_JOBS = CAPTURE_DIR / "seen_jobs.json"
LOW_FIT_RE = re.compile(r"\b(senior|staff|principal|manager|intern|internship|sales|recruiter|support)\b", re.I)


def load_json_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8") or "[]")
    if not isinstance(data, list):
        raise SystemExit(f"{path} must contain a JSON array")
    return [entry for entry in data if isinstance(entry, dict)]


def normalize(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def tracker_keys() -> set[str]:
    if not APPLICATIONS_MD.exists():
        return set()
    text = APPLICATIONS_MD.read_text(encoding="utf-8")
    keys: set[str] = set()
    header: list[str] = []
    for line in text.splitlines():
        if line.startswith("| Company |") and "Posting Key" in line:
            header = [cell.strip() for cell in line.strip().strip("|").split("|")]
            continue
        if not header or not line.startswith("| ") or set(line.replace("|", "").replace("-", "").strip()) == set():
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        row = dict(zip(header, cells))
        if row.get("Posting Key"):
            keys.add(row["Posting Key"])
        if row.get("Job Link"):
            keys.add(row["Job Link"])
    for field in ("currentJobId", "jobId", "job_id", "gh_jid"):
        keys.update(re.findall(rf"[?&]{field}=([^)&\s]+)", text))
    keys.update(re.findall(r"/jobs/view/(\d+)", text))
    return {normalize(key) for key in keys if normalize(key)}


def key(job: dict[str, Any]) -> str:
    return normalize(job.get("posting_key"))


def cached_keys(source: str) -> set[str]:
    if not SEEN_JOBS.exists():
        return set()
    try:
        data = json.loads(SEEN_JOBS.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        return set()
    entries = data.get("entries", {}) if isinstance(data, dict) else {}
    if not isinstance(entries, dict):
        return set()
    prefix = f"{source}:"
    return {normalize(cache_key.removeprefix(prefix)) for cache_key in entries if str(cache_key).startswith(prefix)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit a deterministic paging decision for the last captured page.")
    parser.add_argument("--source", required=True, choices=["linkedin", "greenhouse"])
    parser.add_argument("--last-page-jobs", required=True)
    args = parser.parse_args()

    last_page = load_json_array(Path(args.last_page_jobs).expanduser())
    if not last_page:
        print("STOP: empty")
        return 0

    last_keys = {key(job) for job in last_page if key(job)}
    captured = load_json_array(CAPTURE_DIR / f"{args.source}_capture.json")
    seen_before = {key(job) for job in captured if key(job)} - last_keys
    cached_before = cached_keys(args.source)
    tracked = tracker_keys()

    already_tracked = 0
    seen_this_run = 0
    cached_skip = 0
    low_fit_titles = 0
    new_relevant = 0

    for job in last_page:
        job_key = key(job)
        if job_key and job_key in tracked:
            already_tracked += 1
        elif job_key and job_key in cached_before:
            cached_skip += 1
        elif job_key and job_key in seen_before:
            seen_this_run += 1
        elif LOW_FIT_RE.search(str(job.get("role", ""))):
            low_fit_titles += 1
        else:
            new_relevant += 1

    streak_path = CAPTURE_DIR / f"{args.source}_streak.json"
    streak = 0
    if streak_path.exists():
        try:
            streak = int(json.loads(streak_path.read_text(encoding="utf-8")).get("low_yield_pages", 0))
        except (json.JSONDecodeError, TypeError, ValueError):
            streak = 0
    streak = 0 if new_relevant >= 3 else streak + 1
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    streak_path.write_text(
        json.dumps(
            {
                "low_yield_pages": streak,
                "already_tracked": already_tracked,
                "seen_this_run": seen_this_run,
                "cached_skip": cached_skip,
                "low_fit_titles": low_fit_titles,
                "new_relevant": new_relevant,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    if new_relevant >= 3:
        print("CONTINUE")
    elif streak >= 2:
        print("STOP: saturated")
    else:
        print("CONTINUE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
