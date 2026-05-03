#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CAPTURE_DIR = Path("/tmp/codexskills-job-intake")
SEEN_JOBS = CAPTURE_DIR / "seen_jobs.json"
REQUIRED_FIELDS = ("company", "role", "location", "url", "posting_key", "posted_at")


def load_json_array(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid JSON: {error}") from error
    if not isinstance(data, list):
        raise SystemExit("capture page must be a JSON array")
    for index, entry in enumerate(data, start=1):
        if not isinstance(entry, dict):
            print(json.dumps(entry, indent=2, sort_keys=True))
            raise SystemExit(f"entry {index} is not an object")
        for field in REQUIRED_FIELDS:
            if not str(entry.get(field, "")).strip():
                print(json.dumps(entry, indent=2, sort_keys=True))
                raise SystemExit(f"missing required field '{field}'")
    return data


def load_capture(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8") or "[]")
    if not isinstance(data, list):
        raise SystemExit(f"{path} must contain a JSON array")
    return [entry for entry in data if isinstance(entry, dict)]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def load_seen(path: Path, ttl_minutes: int) -> dict[str, Any]:
    if not path.exists():
        return {"schemaVersion": 1, "ttlMinutes": ttl_minutes, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError:
        data = {}
    entries = data.get("entries", {}) if isinstance(data, dict) else {}
    if not isinstance(entries, dict):
        entries = {}
    cutoff = now_utc() - timedelta(days=7)
    filtered = {}
    for key, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        last_seen = parse_time(str(entry.get("lastSeenAt") or ""))
        if last_seen and last_seen >= cutoff:
            filtered[key] = entry
    return {"schemaVersion": 1, "ttlMinutes": ttl_minutes, "entries": filtered}


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and persist one captured job-results page.")
    parser.add_argument("--source", required=True, choices=["linkedin", "greenhouse"])
    parser.add_argument("--page", required=True, type=int)
    parser.add_argument("--jobs-json", required=True)
    parser.add_argument("--ttl-minutes", type=int, default=30)
    parser.add_argument("--gc", action="store_true", help="Drop seen-job entries not seen in the last seven days.")
    args = parser.parse_args()

    jobs = load_json_array(Path(args.jobs_json).expanduser())
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    seen_jobs = load_seen(SEEN_JOBS, args.ttl_minutes)
    seen_entries = seen_jobs["entries"]
    timestamp = now_utc().isoformat()
    capture_path = CAPTURE_DIR / f"{args.source}_capture.json"
    capture = load_capture(capture_path)

    seen = {str(entry.get("posting_key", "")).strip() for entry in capture}
    new_entries = []
    cached_skip = 0
    for job in jobs:
        key = str(job.get("posting_key", "")).strip()
        cache_key = f"{args.source}:{key}"
        cached = seen_entries.get(cache_key) if key else None
        first_seen = parse_time(str(cached.get("firstSeenAt") or "")) if isinstance(cached, dict) else None
        within_ttl = first_seen is not None and now_utc() - first_seen < timedelta(minutes=max(0, args.ttl_minutes))
        if isinstance(cached, dict) and within_ttl:
            cached["lastSeenAt"] = timestamp
            cached_skip += 1
            continue
        if key:
            seen_entries[cache_key] = {
                "firstSeenAt": cached.get("firstSeenAt", timestamp) if isinstance(cached, dict) else timestamp,
                "lastSeenAt": timestamp,
                "company": str(job.get("company", "")),
                "role": str(job.get("role", "")),
            }
        if key and key not in seen:
            new_entries.append(job)
            seen.add(key)
        elif key and args.ttl_minutes == 0:
            new_entries.append(job)

    combined = capture + new_entries
    atomic_write_json(capture_path, combined)
    seen_jobs["ttlMinutes"] = args.ttl_minutes
    atomic_write_json(SEEN_JOBS, seen_jobs)
    print(f"SAVED: {len(new_entries)} new, {cached_skip} cached-skip; total {args.source}: {len(combined)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
