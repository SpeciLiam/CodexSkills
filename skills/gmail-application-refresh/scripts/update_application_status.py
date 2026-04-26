#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
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
    if posting_key and normalize(row.get("Posting Key", "")) == normalize(posting_key):
        return True
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
            updated_rows.append(build_row(row))
        else:
            updated_rows.append(build_row(row))

    if not matched:
        key_hint = target_posting_key or f"{args.company} / {args.role}"
        raise SystemExit(f"Could not find existing tracker row for {key_hint}")

    tracker.write_text(render_tracker(updated_rows))
    print(tracker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
