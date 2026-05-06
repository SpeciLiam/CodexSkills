#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
RESUME_TAILOR_SCRIPTS = SCRIPT_DIR.parents[1] / "resume-tailor" / "scripts"
if str(RESUME_TAILOR_SCRIPTS) not in sys.path:
    sys.path.append(str(RESUME_TAILOR_SCRIPTS))

from update_application_tracker import (
    DEFAULT_COLUMNS,
    build_row,
    ensure_tracker,
    normalize,
    parse_rows,
    posting_key as build_posting_key,
    render_tracker,
    repo_root_from_args,
    row_from_cells,
    split_row,
    tracker_path,
)


def refresh_sqlite_mirror(repo_root: Path) -> None:
    subprocess.run(["python3", "scripts/mirror_to_sqlite.py"], cwd=repo_root, check=False)


def outcome_for_status(status: str | None) -> str | None:
    normalized = normalize(status or "")
    return {
        "applied": "submitted",
        "manual apply needed": "manual",
        "archived": "archived",
        "rejected": "rejected_after_apply",
        "online assessment": "oa",
        "interviewing": "interview",
        "offer": "offer",
    }.get(normalized)


def predicted_confidence(posting_key: str) -> int:
    for path in (Path("/tmp/apply_pipeline/run_state.json"), Path("/tmp/fa_run_state.json")):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for item in data.get("items", []):
            if not isinstance(item, dict):
                continue
            if normalize(item.get("postingKey", "")) == normalize(posting_key):
                try:
                    return int(item.get("confidenceScore") or 0)
                except (TypeError, ValueError):
                    return 0
    return 0


def log_outcome(repo_root: Path, row: dict[str, str], status: str | None) -> None:
    outcome = outcome_for_status(status)
    posting_key = row.get("Posting Key", "").strip()
    if not outcome or not posting_key:
        return
    subprocess.run(
        [
            "python3",
            "scripts/log_outcome.py",
            "--posting-key",
            posting_key,
            "--company",
            row.get("Company", ""),
            "--role",
            row.get("Role", ""),
            "--source",
            row.get("Source", ""),
            "--predicted-confidence-score",
            str(predicted_confidence(posting_key)),
            "--outcome",
            outcome,
        ],
        cwd=repo_root,
        check=False,
    )


def append_note(existing: str, new_note: str) -> str:
    existing = existing.strip()
    new_note = new_note.strip()
    if not new_note:
        return existing
    if not existing:
        return new_note
    if new_note in existing:
        return existing
    return f"{existing}; {new_note}"


def row_matches(row: dict[str, str], posting_key: str, company: str, role: str) -> bool:
    if posting_key:
        return normalize(row.get("Posting Key", "")) == normalize(posting_key)
    return (
        normalize(row.get("Company", "")) == normalize(company)
        and normalize(row.get("Role", "")) == normalize(role)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Update status fields for an existing application tracker row.")
    parser.add_argument("--job-link", default="", help="Job posting URL used to derive the posting key")
    parser.add_argument("--posting-key", default="", help="Explicit posting key override")
    parser.add_argument("--company", required=True, help="Company name")
    parser.add_argument("--role", required=True, help="Role title")
    parser.add_argument("--status", default=None, help="New status value")
    parser.add_argument("--applied", default=None, help="Applied value, usually Yes or blank")
    parser.add_argument("--referral", default=None, help="Referral value or name")
    parser.add_argument("--fit-score", default=None, help="Fit score override from 1 to 10")
    parser.add_argument("--reach-out", default=None, help="Whether the role deserves recruiter outreach, usually Yes or blank")
    parser.add_argument("--notes", default=None, help="Note to append or replace")
    parser.add_argument(
        "--notes-mode",
        choices=("append", "replace"),
        default="append",
        help="How to apply the notes field",
    )
    parser.add_argument("--root", default=None, help="Optional repo root override")
    args = parser.parse_args()

    repo_root = repo_root_from_args(args.root)
    tracker = tracker_path(repo_root)
    ensure_tracker(tracker)

    lines = tracker.read_text().splitlines()
    header_index, rows = parse_rows(lines)
    if header_index < 0:
        raise SystemExit(f"Could not find tracker table in {tracker}")

    target_posting_key = args.posting_key.strip()
    if not target_posting_key and args.job_link:
        target_posting_key = build_posting_key(args.job_link, args.role)

    updated_rows: list[str] = []
    matched = False
    outcome_row: dict[str, str] | None = None

    for row_line in rows:
        cells = split_row(row_line)
        row = row_from_cells(cells)
        if row is None:
            updated_rows.append(row_line)
            continue

        if row_matches(row, target_posting_key, args.company, args.role):
            matched = True
            if args.status is not None:
                row["Status"] = args.status
            if args.applied is not None:
                row["Applied"] = args.applied
            if args.referral is not None:
                row["Referral"] = args.referral
            if args.fit_score is not None:
                row["Fit Score"] = args.fit_score
            if args.reach_out is not None:
                row["Reach Out"] = args.reach_out
            if args.notes is not None:
                if args.notes_mode == "replace":
                    row["Notes"] = args.notes.strip()
                else:
                    row["Notes"] = append_note(row.get("Notes", ""), args.notes)
            outcome_row = dict(row)
            updated_rows.append(build_row(row))
        else:
            updated_rows.append(build_row(row))

    if not matched:
        key_hint = target_posting_key or f"{args.company} / {args.role}"
        raise SystemExit(f"Could not find existing tracker row for {key_hint}")

    tracker.write_text(render_tracker(updated_rows))
    if outcome_row is not None:
        log_outcome(repo_root, outcome_row, args.status)
    refresh_sqlite_mirror(repo_root)
    print(tracker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
