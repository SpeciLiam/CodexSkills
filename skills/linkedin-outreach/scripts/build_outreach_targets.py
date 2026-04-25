#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
RESUME_TAILOR_SCRIPTS = SCRIPT_DIR.parents[1] / "resume-tailor" / "scripts"
if str(RESUME_TAILOR_SCRIPTS) not in sys.path:
    sys.path.append(str(RESUME_TAILOR_SCRIPTS))

from update_application_tracker import (  # type: ignore
    normalize,
    parse_rows,
    repo_root_from_args,
    row_from_cells,
    split_row,
    tracker_path,
    truthy,
)


DEFAULT_EXCLUDED_STATUSES = {"rejected", "archived"}
OUTREACH_MARKERS = (
    "linkedin invite sent",
    "connection invite sent",
    "reached out",
    "connect request sent",
)


def load_rows(repo_root: Path) -> list[dict[str, str]]:
    tracker = tracker_path(repo_root)
    lines = tracker.read_text().splitlines()
    _, rows = parse_rows(lines)

    parsed_rows: list[dict[str, str]] = []
    for row_line in rows:
        row = row_from_cells(split_row(row_line))
        if row is not None:
            parsed_rows.append(row)
    return parsed_rows


def has_outreach_record(row: dict[str, str]) -> bool:
    notes = normalize(row.get("Notes", ""))
    if any(marker in notes for marker in OUTREACH_MARKERS):
        return True
    if row.get("Recruiter Contact", "").strip():
        return True
    if row.get("Recruiter Profile", "").strip():
        return True
    return False


def fit_score_value(row: dict[str, str]) -> int:
    value = row.get("Fit Score", "").strip()
    if value.isdigit():
        return int(value)
    return -1


def filter_rows(
    rows: list[dict[str, str]],
    *,
    company: str,
    posting_key: str,
    include_statuses: set[str],
    exclude_statuses: set[str],
    include_contacted: bool,
) -> list[dict[str, str]]:
    filtered: list[dict[str, str]] = []
    company_norm = normalize(company)
    posting_key_norm = normalize(posting_key)

    for row in rows:
        status = normalize(row.get("Status", ""))
        if include_statuses and status not in include_statuses:
            continue
        if status in exclude_statuses:
            continue
        if not truthy(row.get("Reach Out", "")):
            continue
        if company_norm and normalize(row.get("Company", "")) != company_norm:
            continue
        if posting_key_norm and normalize(row.get("Posting Key", "")) != posting_key_norm:
            continue
        if not include_contacted and has_outreach_record(row):
            continue
        filtered.append(row)

    filtered.sort(
        key=lambda row: (
            fit_score_value(row),
            row.get("Date Added", ""),
            row.get("Company", "").lower(),
            row.get("Role", "").lower(),
        ),
        reverse=True,
    )
    return filtered


def row_summary(row: dict[str, str]) -> dict[str, str]:
    return {
        "company": row["Company"],
        "role": row["Role"],
        "status": row["Status"],
        "fit_score": row["Fit Score"],
        "reach_out": row["Reach Out"],
        "location": row["Location"],
        "source": row["Source"],
        "job_link": row["Job Link"],
        "posting_key": row["Posting Key"],
        "recruiter_contact": row["Recruiter Contact"],
        "recruiter_profile": row["Recruiter Profile"],
        "notes": row["Notes"],
    }


def print_text(rows: list[dict[str, str]]) -> None:
    print(f"Outreach targets: {len(rows)}")
    print("")
    for index, row in enumerate(rows, start=1):
        print(
            f"{index}. {row['Company']} | {row['Role']} | "
            f"Fit {row['Fit Score'] or '?'} | {row['Status']}"
        )
        print(f"   Location: {row['Location'] or 'Unknown'}")
        print(f"   Source: {row['Source'] or 'Unknown'}")
        print(f"   Posting Key: {row['Posting Key']}")
        print(f"   Job Link: {row['Job Link']}")
        if row["Notes"].strip():
            print(f"   Notes: {row['Notes']}")
        print("")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List tracker rows that still need LinkedIn outreach."
    )
    parser.add_argument("--root", default=None, help="Optional repo root override")
    parser.add_argument("--company", default="", help="Only include a specific company")
    parser.add_argument("--posting-key", default="", help="Only include a specific posting key")
    parser.add_argument(
        "--include-status",
        action="append",
        default=[],
        help="Only include rows with one of these statuses. Can be passed multiple times.",
    )
    parser.add_argument(
        "--exclude-status",
        action="append",
        default=[],
        help="Exclude rows with one of these statuses. Can be passed multiple times.",
    )
    parser.add_argument(
        "--include-contacted",
        action="store_true",
        help="Include rows that already show outreach in tracker notes or recruiter fields.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of rows to emit.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    args = parser.parse_args()

    repo_root = repo_root_from_args(args.root)
    rows = load_rows(repo_root)
    include_statuses = {normalize(value) for value in args.include_status if value.strip()}
    exclude_statuses = DEFAULT_EXCLUDED_STATUSES | {
        normalize(value) for value in args.exclude_status if value.strip()
    }

    filtered = filter_rows(
        rows,
        company=args.company,
        posting_key=args.posting_key,
        include_statuses=include_statuses,
        exclude_statuses=exclude_statuses,
        include_contacted=args.include_contacted,
    )

    if args.limit > 0:
        filtered = filtered[: args.limit]

    if args.format == "json":
        print(json.dumps([row_summary(row) for row in filtered], indent=2))
        return 0

    print_text(filtered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
