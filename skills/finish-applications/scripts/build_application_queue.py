#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "application-visualizer" / "src" / "data" / "tracker-data.json"
ACTIVE_SKIP_STATUSES = {"applied", "rejected", "archived", "online assessment", "interviewing", "offer"}


def norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def load_cache(root: Path) -> dict[str, Any]:
    path = root / "application-visualizer" / "src" / "data" / "tracker-data.json"
    if not path.exists():
        raise SystemExit(
            f"Missing tracker cache: {path}\n"
            "Run: python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def is_ready(app: dict[str, Any], min_fit: int, include_low_fit: bool) -> bool:
    if app.get("applied"):
        return False
    status = norm(app.get("status", ""))
    if status in ACTIVE_SKIP_STATUSES:
        return False
    if status != "resume tailored":
        return False
    if not app.get("jobLink") or not app.get("resumePdf"):
        return False
    fit = int(app.get("fitScore") or 0)
    return include_low_fit or fit >= min_fit


def score(app: dict[str, Any]) -> tuple[int, int, str, str]:
    fit = int(app.get("fitScore") or 0)
    reach = 1 if app.get("reachOut") else 0
    source_boost = 1 if norm(app.get("source")) in {"ashby", "greenhouse", "lever", "company site"} else 0
    return fit, reach + source_boost, str(app.get("dateAdded") or ""), str(app.get("company") or "")


def queue_item(app: dict[str, Any]) -> dict[str, Any]:
    resume_pdf = app.get("resumePdf") or ""
    resume_exists = bool(resume_pdf and Path(resume_pdf).expanduser().exists())
    return {
        "company": app.get("company", ""),
        "role": app.get("role", ""),
        "fitScore": app.get("fitScore", 0),
        "reachOut": app.get("reachOut", False),
        "status": app.get("status", ""),
        "dateAdded": app.get("dateAdded", ""),
        "location": app.get("location", ""),
        "source": app.get("source", ""),
        "postingKey": app.get("postingKey", ""),
        "jobLink": app.get("jobLink", ""),
        "resumePdf": resume_pdf,
        "resumeExists": resume_exists,
        "notes": app.get("notes", ""),
    }


def build_queue(data: dict[str, Any], limit: int, min_fit: int, include_low_fit: bool) -> list[dict[str, Any]]:
    applications = [app for app in data.get("applications", []) if isinstance(app, dict)]
    ready = [app for app in applications if is_ready(app, min_fit=min_fit, include_low_fit=include_low_fit)]
    return [queue_item(app) for app in sorted(ready, key=score, reverse=True)[:limit]]


def print_text(items: list[dict[str, Any]]) -> None:
    print("Ready Unapplied Applications")
    print("============================")
    if not items:
        print("No ready unapplied applications found.")
        return
    for index, item in enumerate(items, start=1):
        exists = "yes" if item["resumeExists"] else "missing"
        print(
            f"{index}. {item['company']} | {item['role']} | "
            f"Fit {item['fitScore']} | {item['source']} | Resume: {exists}"
        )
        print(f"   Posting key: {item['postingKey']}")
        print(f"   Job: {item['jobLink']}")
        print(f"   Resume: {item['resumePdf']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a queue of tailored, unapplied applications.")
    parser.add_argument("--root", default=None, help="Optional repo root override")
    parser.add_argument("--limit", type=int, default=10, help="Maximum applications to list")
    parser.add_argument("--min-fit", type=int, default=8, help="Minimum fit score unless --include-low-fit is set")
    parser.add_argument("--include-low-fit", action="store_true", help="Include fit scores below --min-fit")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve() if args.root else ROOT
    items = build_queue(load_cache(root), args.limit, args.min_fit, args.include_low_fit)
    if args.format == "json":
        print(json.dumps(items, indent=2))
    else:
        print_text(items)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
