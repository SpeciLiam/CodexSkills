#!/usr/bin/env python3
"""Initialize durable state for linkedin-apply-all queue runs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATE = Path("/tmp/linkedin_apply_all_state.json")
DEFAULT_SEARCH_URL = (
    "https://www.linkedin.com/jobs/search-results/?keywords=software%20engineer&"
    "origin=JOBS_HOME_KEYWORD_HISTORY&geoId=103644278&distance=0.0&"
    "f_SAL=f_SA_id_227001%3A276001"
)
FRESHNESS_SECONDS = {
    "24h": 86_400,
    "day": 86_400,
    "daily": 86_400,
    "week": 604_800,
    "weekly": 604_800,
    "last-week": 604_800,
    "month": 2_592_000,
    "monthly": 2_592_000,
    "last-month": 2_592_000,
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_existing(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_freshness(name: str, override_seconds: int | None) -> tuple[str, int]:
    if override_seconds is not None:
        return f"{override_seconds}s", override_seconds
    key = name.strip().lower()
    if key not in FRESHNESS_SECONDS:
        allowed = ", ".join(sorted(FRESHNESS_SECONDS))
        raise SystemExit(f"Unknown freshness '{name}'. Use one of: {allowed}; or --freshness-seconds N")
    return key, FRESHNESS_SECONDS[key]


def with_freshness(url: str, seconds: int) -> str:
    parsed = urlparse(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params["f_TPR"] = f"r{seconds}"
    query = urlencode(params, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build linkedin-apply-all run state.")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--search-url", default=DEFAULT_SEARCH_URL)
    parser.add_argument("--freshness", default="24h", help="24h, week, or month")
    parser.add_argument("--freshness-seconds", type=int)
    parser.add_argument("--worker", choices=("codex", "claude"), default="codex")
    parser.add_argument("--max-jobs", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--missing-resume-policy", choices=("queue_for_tailoring", "tailor", "skip"), default="tailor")
    parser.add_argument("--manual-circuit-breaker", type=int, default=5)
    parser.add_argument("--commit-every-submissions", type=int, default=5)
    parser.add_argument("--resume", action="store_true", help="Preserve existing items and only refresh policy/search fields")
    args = parser.parse_args()

    freshness_label, freshness_seconds = parse_freshness(args.freshness, args.freshness_seconds)
    search_url = with_freshness(args.search_url, freshness_seconds)
    existing = load_existing(args.state) if args.resume else {}
    run_policy = existing.get("runPolicy", {})
    search = existing.get("search", {})

    state: dict[str, Any] = {
        "schemaVersion": 1,
        "createdAt": existing.get("createdAt") or now_iso(),
        "updatedAt": now_iso(),
        "repo": str(ROOT),
        "runPolicy": {
            "mode": "linkedin-apply-all",
            "worker": args.worker,
            "maxJobs": args.max_jobs,
            "batchSize": args.batch_size,
            "freshness": freshness_label,
            "freshnessSeconds": freshness_seconds,
            "missingResumePolicy": args.missing_resume_policy,
            "manualCircuitBreaker": args.manual_circuit_breaker,
            "commitEverySubmissions": args.commit_every_submissions,
            "continuePastPerApplicationBlockers": True,
            "outreachAllowed": False,
            "coverLetterPolicy": "Only create/include a cover letter when required by the application or explicitly requested by the posting.",
            "standingApproval": "Use exact tailored resumes and submit high-confidence routine applications with confirmation evidence; record blockers and continue.",
            "stateFile": str(args.state),
            "previousWorker": run_policy.get("worker"),
        },
        "search": {
            "url": search_url,
            "originalUrl": args.search_url,
            "currentResultIndex": int(search.get("currentResultIndex") or 0),
            "stopRequested": bool(search.get("stopRequested", False)),
            "saturationReason": search.get("saturationReason", ""),
        },
        "visitedJobUrls": existing.get("visitedJobUrls", []),
        "items": existing.get("items", []),
        "events": existing.get("events", []),
    }

    args.state.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = args.state.with_name(f".{args.state.name}.{dt.datetime.now(dt.timezone.utc).timestamp()}.tmp")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(args.state)
    print(f"Wrote {args.state}")
    print(f"Worker: {args.worker}; freshness: {freshness_label} ({freshness_seconds}s)")
    print(f"Search URL: {search_url}")
    print(f"Items preserved: {len(state['items'])}; visited URLs: {len(state['visitedJobUrls'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
