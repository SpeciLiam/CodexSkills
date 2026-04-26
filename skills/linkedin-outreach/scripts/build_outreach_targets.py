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
from tracker_data_cache import load_cached_application_rows  # type: ignore


DEFAULT_EXCLUDED_STATUSES = {"rejected", "archived"}
OUTREACH_MARKERS = (
    "linkedin invite sent",
    "linkedin invites sent",
    "connection invite sent",
    "connection invites sent",
    "reached out",
    "connect request sent",
    "connect requests sent",
)
CONTACT_TYPES = ("recruiter", "engineer")


def load_rows(repo_root: Path) -> list[dict[str, str]]:
    cached_rows = load_cached_application_rows(repo_root)
    if cached_rows:
        return cached_rows

    tracker = tracker_path(repo_root)
    lines = tracker.read_text().splitlines()
    _, rows = parse_rows(lines)

    parsed_rows: list[dict[str, str]] = []
    for row_line in rows:
        row = row_from_cells(split_row(row_line))
        if row is not None:
            parsed_rows.append(row)
    return parsed_rows


def has_contact_type_record(row: dict[str, str], contact_type: str) -> bool:
    notes = normalize(row.get("Notes", ""))
    if contact_type == "recruiter":
        if row.get("Recruiter Contact", "").strip():
            return True
        if row.get("Recruiter Profile", "").strip():
            return True
        return any(marker in notes and "recruiter" in notes for marker in OUTREACH_MARKERS)

    if contact_type == "engineer":
        if row.get("Engineer Contact", "").strip():
            return True
        if row.get("Engineer Profile", "").strip():
            return True
        return any(marker in notes and "engineer" in notes for marker in OUTREACH_MARKERS)

    if any(marker in notes for marker in OUTREACH_MARKERS):
        return True
    if row.get("Recruiter Contact", "").strip() or row.get("Recruiter Profile", "").strip():
        return True
    if row.get("Engineer Contact", "").strip() or row.get("Engineer Profile", "").strip():
        return True
    return False


def has_outreach_record(row: dict[str, str]) -> bool:
    return any(has_contact_type_record(row, contact_type) for contact_type in CONTACT_TYPES)


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
    contact_types: tuple[str, ...],
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
        for contact_type in contact_types:
            if not include_contacted and has_contact_type_record(row, contact_type):
                continue
            target = row.copy()
            target["Contact Type"] = contact_type
            target["Recruiter Done"] = "Yes" if has_contact_type_record(row, "recruiter") else ""
            target["Engineer Done"] = "Yes" if has_contact_type_record(row, "engineer") else ""
            filtered.append(target)

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
        "contact_type": row.get("Contact Type", ""),
        "status": row["Status"],
        "fit_score": row["Fit Score"],
        "reach_out": row["Reach Out"],
        "location": row["Location"],
        "source": row["Source"],
        "job_link": row["Job Link"],
        "posting_key": row["Posting Key"],
        "recruiter_contact": row["Recruiter Contact"],
        "recruiter_profile": row["Recruiter Profile"],
        "engineer_contact": row.get("Engineer Contact", ""),
        "engineer_profile": row.get("Engineer Profile", ""),
        "recruiter_done": row.get("Recruiter Done", ""),
        "engineer_done": row.get("Engineer Done", ""),
        "notes": row["Notes"],
    }


def print_text(rows: list[dict[str, str]]) -> None:
    print(f"Outreach targets: {len(rows)}")
    print("")
    for index, row in enumerate(rows, start=1):
        print(
            f"{index}. [{row.get('Contact Type', 'contact').title()}] {row['Company']} | {row['Role']} | "
            f"Fit {row['Fit Score'] or '?'} | {row['Status']}"
        )
        print(f"   Recruiter done: {row.get('Recruiter Done') or 'No'} | Engineer done: {row.get('Engineer Done') or 'No'}")
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
        help="Include recruiter/engineer lanes that already show outreach in tracker notes or contact fields.",
    )
    parser.add_argument(
        "--contact-type",
        choices=("both", "recruiter", "engineer"),
        default="both",
        help="Which outreach lane to emit. Default emits one recruiter and one engineer lane where missing.",
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
    contact_types = CONTACT_TYPES if args.contact_type == "both" else (args.contact_type,)

    filtered = filter_rows(
        rows,
        company=args.company,
        posting_key=args.posting_key,
        include_statuses=include_statuses,
        exclude_statuses=exclude_statuses,
        include_contacted=args.include_contacted,
        contact_types=contact_types,
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
