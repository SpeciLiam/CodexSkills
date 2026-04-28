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
MANUAL_STATUS = "manual apply needed"
READY_STATUS = "resume tailored"
TRUE_MANUAL_BLOCKERS = (
    "account creation",
    "account login",
    "account sign-in",
    "anti-ai",
    "ashby verification",
    "background-check",
    "bot",
    "captcha",
    "custom",
    "cover letter",
    "declaration",
    "embedded",
    "email application",
    "experience-level",
    "final application submission confirmation",
    "final submit confirmation",
    "free response",
    "free-response",
    "hcaptcha",
    "hiring network",
    "honeypot",
    "legal signature",
    "login",
    "non-compete",
    "not automation-accessible",
    "otp",
    "partner sharing",
    "preference",
    "profile",
    "recaptcha",
    "repeat application limit",
    "salary",
    "signature",
    "start date",
    "verification",
    "workday",
)
RETRYABLE_MANUAL_BLOCKERS = (
    "linkedin login",
)
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


def passes_basic_filters(app: dict[str, Any], min_fit: int, include_low_fit: bool) -> bool:
    if app.get("applied"):
        return False
    status = norm(app.get("status", ""))
    if status in ACTIVE_SKIP_STATUSES:
        return False
    if not app.get("jobLink") or not app.get("resumePdf"):
        return False
    fit = int(app.get("fitScore") or 0)
    return include_low_fit or fit >= min_fit


def is_ready(app: dict[str, Any], min_fit: int, include_low_fit: bool) -> bool:
    if not passes_basic_filters(app, min_fit=min_fit, include_low_fit=include_low_fit):
        return False
    if is_workday(app):
        return False
    return norm(app.get("status", "")) == READY_STATUS


def manual_reason_from_notes(notes: str) -> str:
    for part in reversed([part.strip() for part in notes.split(";") if part.strip()]):
        if part.lower().startswith("manual apply needed:"):
            return part
    return ""


def is_retryable_manual(app: dict[str, Any]) -> bool:
    reason = norm(manual_reason_from_notes(str(app.get("notes") or "")))
    return any(blocker in reason for blocker in RETRYABLE_MANUAL_BLOCKERS)


def true_manual_reason(app: dict[str, Any]) -> str:
    if is_workday(app):
        return "Workday posting; Liam should submit manually."
    reason = manual_reason_from_notes(str(app.get("notes") or ""))
    normalized = norm(reason)
    if not reason:
        return "Manual follow-up required; no specific reason recorded yet."
    if is_retryable_manual(app):
        return ""
    if any(blocker in normalized for blocker in TRUE_MANUAL_BLOCKERS):
        return reason.replace("Manual apply needed:", "").strip()
    return ""


def is_queue_candidate(app: dict[str, Any], min_fit: int, include_low_fit: bool) -> bool:
    if not passes_basic_filters(app, min_fit=min_fit, include_low_fit=include_low_fit):
        return False
    return norm(app.get("status", "")) in {READY_STATUS, MANUAL_STATUS}


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
    manual_reason = true_manual_reason(app) if norm(app.get("status", "")) == MANUAL_STATUS else ""
    if norm(app.get("status", "")) == READY_STATUS:
        action = "apply"
    elif manual_reason:
        action = "manual"
    else:
        action = "retry/apply"
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
        "action": action,
        "manualReason": manual_reason,
    }


def manual_item(app: dict[str, Any]) -> dict[str, Any]:
    item = queue_item(app)
    item["manualReason"] = "Workday posting; Liam should submit manually."
    return item


def build_queues(data: dict[str, Any], limit: int, min_fit: int, include_low_fit: bool) -> dict[str, list[dict[str, Any]]]:
    applications = [app for app in data.get("applications", []) if isinstance(app, dict)]
    ready = [app for app in applications if is_ready(app, min_fit=min_fit, include_low_fit=include_low_fit)]
    all_candidates = [
        app
        for app in applications
        if is_queue_candidate(app, min_fit=min_fit, include_low_fit=include_low_fit)
    ]
    manual_workday = [app for app in applications if is_manual_workday(app, min_fit=min_fit, include_low_fit=include_low_fit)]
    unified = [queue_item(app) for app in sorted(all_candidates, key=score, reverse=True)[:limit]]
    return {
        "queue": unified,
        "ready": [queue_item(app) for app in sorted(ready, key=score, reverse=True)[:limit]],
        "manual": [item for item in unified if item.get("action") == "manual"],
        "retry": [item for item in unified if item.get("action") == "retry/apply"],
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
            f"Fit {item['fitScore']} | {item['source']} | Action: {item.get('action', 'apply')} | Resume: {exists}"
        )
        if item.get("manualReason"):
            print(f"   Manual reason: {item['manualReason']}")
        print(f"   Posting key: {item['postingKey']}")
        print(f"   Job: {item['jobLink']}")
        print(f"   Resume: {item['resumePdf']}")
    print("")


def print_text(queues: dict[str, list[dict[str, Any]]]) -> None:
    print("Application Queue")
    print("=================")
    print("")
    print_section("All Open Applications", queues["queue"])
    print_section("Agent-submit Queue", queues["ready"] + queues["retry"])
    print_section("True Manual Queue", queues["manual"])
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
