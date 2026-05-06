#!/usr/bin/env python3
"""Initialize durable state for linkedin-full-pipeline monitored runs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATE = Path("/tmp/linkedin_full_pipeline_state.json")
EARLY_CAREER_URL = (
    "https://www.linkedin.com/jobs/search/?keywords=software%20engineer&"
    "geoId=103644278&location=United%20States&f_TPR=r86400&f_E=2&"
    "origin=JOB_SEARCH_PAGE_SEARCH_BUTTON"
)
BROAD_FALLBACK_URL = (
    "https://www.linkedin.com/jobs/search-results/?currentJobId=4411219442&"
    "keywords=software%20engineer&origin=JOBS_HOME_KEYWORD_HISTORY&geoId=103644278&"
    "distance=0.0&f_TPR=r86400&f_SAL=f_SA_id_227001%3A276001"
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_existing(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build linkedin-full-pipeline run state.")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--max-jobs", type=int, default=12, help="Maximum jobs to durably process in this run")
    parser.add_argument("--batch-size", type=int, default=1, help="Jobs per fresh Codex CLI process")
    parser.add_argument("--resume", action="store_true", help="Preserve existing state and only refresh policy fields")
    args = parser.parse_args()

    existing = load_existing(args.state) if args.resume else {}
    state: dict[str, Any] = {
        "schemaVersion": 1,
        "createdAt": existing.get("createdAt") or now_iso(),
        "updatedAt": now_iso(),
        "repo": str(ROOT),
        "runPolicy": {
            "mode": "monitored-cli-batches",
            "maxJobs": args.max_jobs,
            "batchSize": args.batch_size,
            "standingApproval": "Tailor, track, outreach when possible, and submit high-confidence routine applications.",
            "outreachMode": existing.get("runPolicy", {}).get("outreachMode", "active"),
            "earlyCareerFirst": True,
            "locationGate": ["NYC", "SF Bay Area", "US remote/hybrid", "Seattle", "Washington DC"],
            "stateFile": str(args.state),
        },
        "search": {
            "phase": existing.get("search", {}).get("phase", "early-career"),
            "earlyCareerUrl": EARLY_CAREER_URL,
            "broadFallbackUrl": BROAD_FALLBACK_URL,
            "saturationReason": existing.get("search", {}).get("saturationReason", ""),
            "stopRequested": bool(existing.get("search", {}).get("stopRequested", False)),
        },
        "items": existing.get("items", []),
        "events": existing.get("events", []),
    }
    args.state.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.state}")
    print(f"Processed items preserved: {len(state['items'])}")
    print(f"Max jobs: {args.max_jobs}; batch size: {args.batch_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
