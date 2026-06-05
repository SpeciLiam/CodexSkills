#!/usr/bin/env python3
"""Build durable state for the LinkedIn early-career weekly workflow."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATE = Path("/tmp/linkedin_early_career_weekly_state.json")
DEFAULT_LOCK = Path("/tmp/linkedin_early_career_weekly_worker.lock")
DEFAULT_OUTPUT_DIR = Path("/tmp/linkedin_early_career_weekly_outputs")
DEFAULT_DESCRIPTION_DIR = Path("/tmp/linkedin_early_career_weekly_descriptions")
DEFAULT_MODEL = os.environ.get("CODEX_LATEST_MODEL", "gpt-5.5")
DEFAULT_FRESHNESS_SECONDS = 604_800


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def early_career_url(
    freshness_seconds: int,
    *,
    keywords: str,
    location: str,
    geo_id: str,
) -> str:
    params = {
        "keywords": keywords,
        "geoId": geo_id,
        "location": location,
        "f_TPR": f"r{freshness_seconds}",
        "f_E": "2",
        "origin": "JOB_SEARCH_PAGE_SEARCH_BUTTON",
    }
    return "https://www.linkedin.com/jobs/search/?" + urlencode(params)


def load_existing(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def active_lock_detail(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return f"lock exists at {path}"
    pid = data.get("pid")
    host = data.get("host") or socket.gethostname()
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


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def preserved_search(existing: dict[str, Any]) -> dict[str, Any]:
    search = existing.get("search", {})
    if not isinstance(search, dict):
        return {}
    return search


def main() -> int:
    parser = argparse.ArgumentParser(description="Build linkedin-early-career-weekly run state.")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK)
    parser.add_argument(
        "--allow-active-lock",
        action="store_true",
        help="Dangerous: rebuild state even when a worker lock is active",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--description-dir", type=Path, default=DEFAULT_DESCRIPTION_DIR)
    parser.add_argument("--resume", action="store_true", help="Preserve existing items/events/search cursor")
    parser.add_argument("--max-jobs", type=int, default=0, help="0 means continue until search saturation")
    parser.add_argument("--freshness-seconds", type=int, default=DEFAULT_FRESHNESS_SECONDS)
    parser.add_argument("--keywords", default="software engineer")
    parser.add_argument("--location", default="United States")
    parser.add_argument("--geo-id", default="103644278")
    parser.add_argument("--search-url", default="", help="Override the generated LinkedIn search URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Default worker model; use 'default' to omit -m")
    parser.add_argument(
        "--reasoning-effort",
        default="medium",
        choices=("minimal", "low", "medium", "high", "xhigh"),
    )
    parser.add_argument(
        "--child-sandbox",
        default="danger-full-access",
        choices=("read-only", "workspace-write", "danger-full-access"),
    )
    args = parser.parse_args()

    lock_detail = active_lock_detail(args.lock_file)
    if lock_detail and not args.allow_active_lock:
        raise SystemExit(
            "Refusing to rebuild LinkedIn weekly state while a worker is active: "
            f"{lock_detail}"
        )

    existing = load_existing(args.state) if args.resume else {}
    existing_search = preserved_search(existing)
    search_url = args.search_url or early_career_url(
        args.freshness_seconds,
        keywords=args.keywords,
        location=args.location,
        geo_id=args.geo_id,
    )

    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.description_dir.mkdir(parents=True, exist_ok=True)

    state: dict[str, Any] = {
        "schemaVersion": 1,
        "createdAt": existing.get("createdAt") or now_iso(),
        "updatedAt": now_iso(),
        "repo": str(ROOT),
        "runPolicy": {
            "mode": "linkedin-early-career-weekly",
            "workerAgent": "codex",
            "model": args.model,
            "reasoningEffort": args.reasoning_effort,
            "childSandbox": args.child_sandbox,
            "maxJobs": args.max_jobs,
            "stateFile": str(args.state),
            "lockFile": str(args.lock_file),
            "outputDir": str(args.output_dir),
            "descriptionDir": str(args.description_dir),
            "autoCommit": False,
            "standingApproval": (
                "Dedupe, tailor a truthful one-page resume when needed, attempt one "
                "application with Liam's Chrome profile, and submit high-confidence "
                "routine applications with confirmation evidence."
            ),
            "browserPolicy": {
                "linkedinSourcing": {
                    "requiredProfile": "Liam",
                    "account": "liamvanpj@gmail.com",
                    "profileDirectory": "Default",
                    "allowedAutomation": ["Codex Chrome plugin", "Codex Computer Use"],
                    "disallowedAutomation": ["Playwright", "Playwright CLI", "Puppeteer", "npx browser tooling", "public scraping fallback"],
                    "tabIsolation": "Must create an agent-owned Codex Chrome tab group before LinkedIn navigation; fail closed if spawned workers cannot access the extension endpoint.",
                },
                "applications": {
                    "requiredProfile": "Liam",
                    "account": "liamvanpj@gmail.com",
                    "profileDirectory": "Default",
                    "chromePluginFirst": True,
                    "computerUseFallback": True,
                    "allowedAutomation": ["Codex Chrome plugin", "Codex Computer Use"],
                    "disallowedAutomation": ["Playwright", "Playwright CLI", "Puppeteer", "npx browser tooling", "public scraping fallback"],
                    "tabIsolation": "Must create an agent-owned Codex Chrome tab group before ATS navigation; fail closed if spawned workers cannot access the extension endpoint.",
                },
            },
            "applicationAnswerContext": "skills/linkedin-easy-apply-nodriver/references/application-defaults.md",
        },
        "search": {
            "phase": "early-career-weekly",
            "searchUrl": search_url,
            "freshnessSeconds": args.freshness_seconds,
            "keywords": args.keywords,
            "location": args.location,
            "geoId": args.geo_id,
            "currentResultIndex": int(existing_search.get("currentResultIndex") or 0),
            "scrollCheckpoint": existing_search.get("scrollCheckpoint", ""),
            "lastJobUrl": existing_search.get("lastJobUrl", ""),
            "visitedJobUrls": existing_search.get("visitedJobUrls", []),
            "skippedJobUrls": existing_search.get("skippedJobUrls", []),
            "duplicateStreak": int(existing_search.get("duplicateStreak") or 0),
            "noUsableStreak": int(existing_search.get("noUsableStreak") or 0),
            "stopRequested": bool(existing_search.get("stopRequested", False)),
            "saturationReason": existing_search.get("saturationReason", ""),
        },
        "items": existing.get("items", []) if args.resume else [],
        "events": existing.get("events", []) if args.resume else [],
    }

    write_json_atomic(args.state, state)
    print(f"Wrote {args.state}")
    print(f"Search URL: {search_url}")
    print(f"Items preserved: {len(state['items'])}")
    print(f"Max jobs: {args.max_jobs or 'unlimited'}")
    print(f"Model: {args.model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
