#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / "application-visualizer" / "src" / "data" / "tracker-data.json"
ACTIVE_SKIP_STATUSES = {"applied", "rejected", "archived", "online assessment", "interviewing", "offer"}
RESUME_TAILOR_SCRIPTS = ROOT / "skills" / "resume-tailor" / "scripts"
if str(RESUME_TAILOR_SCRIPTS) not in sys.path:
    sys.path.append(str(RESUME_TAILOR_SCRIPTS))

from update_application_tracker import (
    build_row,
    ensure_tracker,
    parse_rows,
    render_tracker,
    row_from_cells,
    split_row,
    tracker_path,
)


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


def is_workday(app: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(app.get(field) or "")
        for field in ("source", "jobLink", "notes")
    ).lower()
    return "workday" in haystack or "myworkdayjobs" in haystack


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
    if is_workday(app):
        return False
    fit = int(app.get("fitScore") or 0)
    return include_low_fit or fit >= min_fit


def is_manual_workday(app: dict[str, Any], min_fit: int, include_low_fit: bool) -> bool:
    if app.get("applied") or not is_workday(app):
        return False
    status = norm(app.get("status", ""))
    if status in ACTIVE_SKIP_STATUSES:
        return False
    if status != "resume tailored":
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


def manual_item(app: dict[str, Any]) -> dict[str, Any]:
    item = queue_item(app)
    item["manualReason"] = "Workday posting; Liam should submit manually."
    return item


def build_queues(data: dict[str, Any], limit: int, min_fit: int, include_low_fit: bool) -> dict[str, list[dict[str, Any]]]:
    applications = [app for app in data.get("applications", []) if isinstance(app, dict)]
    ready = [app for app in applications if is_ready(app, min_fit=min_fit, include_low_fit=include_low_fit)]
    manual_workday = [app for app in applications if is_manual_workday(app, min_fit=min_fit, include_low_fit=include_low_fit)]
    return {
        "ready": [queue_item(app) for app in sorted(ready, key=score, reverse=True)[:limit]],
        "manualWorkday": [manual_item(app) for app in sorted(manual_workday, key=score, reverse=True)[:limit]],
    }


def append_note(existing: str, new_note: str) -> str:
    existing = existing.strip()
    if not existing:
        return new_note
    if new_note in existing:
        return existing
    return f"{existing}; {new_note}"


def mark_manual_workday(root: Path, items: list[dict[str, Any]], note_date: str) -> list[dict[str, str]]:
    if not items:
        return []
    tracker = tracker_path(root)
    ensure_tracker(tracker)
    lines = tracker.read_text(encoding="utf-8").splitlines()
    _, rows = parse_rows(lines)
    posting_keys = {norm(item.get("postingKey", "")) for item in items if item.get("postingKey")}
    note = f"Manual apply needed: Workday posting {note_date}"
    marked: list[dict[str, str]] = []
    updated_rows: list[str] = []

    for row_line in rows:
        row = row_from_cells(split_row(row_line))
        if row is None:
            updated_rows.append(row_line)
            continue
        if norm(row.get("Posting Key", "")) in posting_keys:
            before = row.get("Notes", "")
            row["Notes"] = append_note(before, note)
            if row["Notes"] != before:
                marked.append({"company": row["Company"], "role": row["Role"], "postingKey": row["Posting Key"]})
        updated_rows.append(build_row(row))

    tracker.write_text(render_tracker(updated_rows), encoding="utf-8")
    return marked


def print_section(title: str, items: list[dict[str, Any]]) -> None:
    print(title)
    print("=" * len(title))
    if not items:
        print("None.")
        print("")
        return
    for index, item in enumerate(items, start=1):
        exists = "yes" if item["resumeExists"] else "missing"
        print(
            f"{index}. {item['company']} | {item['role']} | "
            f"Fit {item['fitScore']} | {item['source']} | Resume: {exists}"
        )
        if item.get("manualReason"):
            print(f"   Manual reason: {item['manualReason']}")
        print(f"   Posting key: {item['postingKey']}")
        print(f"   Job: {item['jobLink']}")
        print(f"   Resume: {item['resumePdf']}")
    print("")


def print_text(queues: dict[str, list[dict[str, Any]]]) -> None:
    print("Ready Unapplied Applications")
    print("============================")
    print("")
    print_section("Agent-submit Queue", queues["ready"])
    print_section("Manual Workday Queue", queues["manualWorkday"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a queue of tailored, unapplied applications.")
    parser.add_argument("--root", default=None, help="Optional repo root override")
    parser.add_argument("--limit", type=int, default=10, help="Maximum applications to list")
    parser.add_argument("--min-fit", type=int, default=8, help="Minimum fit score unless --include-low-fit is set")
    parser.add_argument("--include-low-fit", action="store_true", help="Include fit scores below --min-fit")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--mark-workday-manual",
        action="store_true",
        help="Append a manual-apply note to matching Workday rows in the markdown tracker",
    )
    parser.add_argument("--date", default=date.today().isoformat(), help="Date for manual Workday notes, in YYYY-MM-DD")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve() if args.root else ROOT
    queues = build_queues(load_cache(root), args.limit, args.min_fit, args.include_low_fit)
    marked = []
    if args.mark_workday_manual:
        marked = mark_manual_workday(root, queues["manualWorkday"], args.date)
        if args.format == "text":
            print(f"Marked {len(marked)} Workday row(s) for manual application.")
            print("")
    if args.format == "json":
        print(json.dumps({**queues, "markedManualWorkday": marked}, indent=2))
    else:
        print_text(queues)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
