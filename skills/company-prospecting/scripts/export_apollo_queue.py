#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from sync_company_prospect_tracker import (  # type: ignore
    company_key,
    outreach_tracker_path,
    parse_sections,
    repo_root_from_args,
)


def normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export the prospect rows that still need Apollo email lookup."
    )
    parser.add_argument("--root", default=None, help="Optional repo root override")
    parser.add_argument("--company", default="", help="Only include one company")
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum number of rows")
    parser.add_argument(
        "--format",
        choices=("text", "csv"),
        default="text",
        help="Output format",
    )
    args = parser.parse_args()

    repo_root = repo_root_from_args(args.root)
    tracker = outreach_tracker_path(repo_root)
    if not tracker.exists():
        raise SystemExit(f"Prospect tracker does not exist yet: {tracker}")

    queue_rows, prospect_rows = parse_sections(tracker.read_text().splitlines())
    queue_map = {
        company_key(row["Company"], row["Posting Key"]): row
        for row in queue_rows
    }
    company_filter = normalize(args.company)

    pending_rows = []
    for row in prospect_rows:
        if company_filter and normalize(row.get("Company", "")) != company_filter:
            continue
        status = normalize(row.get("Email Status", ""))
        email = row.get("Apollo Email", "").strip()
        if email and status == "ready":
            continue
        if status not in {"", "needs apollo", "needs review"}:
            continue

        queue_row = queue_map.get(company_key(row["Company"], row["Posting Key"]), {})
        pending_rows.append(
            {
                "company": row["Company"],
                "posting_key": row["Posting Key"],
                "priority": row["Priority"],
                "target_type": row["Target Type"],
                "name": row["Name"],
                "title": row["Title"],
                "linkedin": row["LinkedIn"],
                "apollo_email": row["Apollo Email"],
                "email_status": row["Email Status"] or "Needs Apollo",
                "role": queue_row.get("Role", ""),
                "fit_score": queue_row.get("Fit Score", ""),
                "job_link": queue_row.get("Job Link", ""),
                "notes": row["Notes"],
            }
        )

    pending_rows.sort(
        key=lambda row: (
            -(int(row["fit_score"]) if str(row.get("fit_score", "")).isdigit() else -1),
            row.get("company", "").lower(),
            int(row["priority"]) if str(row.get("priority", "")).isdigit() else 999,
            row.get("name", "").lower(),
        )
    )

    if args.limit > 0:
        pending_rows = pending_rows[: args.limit]

    if args.format == "csv":
        writer_output = io.StringIO()
        writer = csv.DictWriter(
            writer_output,
            fieldnames=[
                "company",
                "role",
                "posting_key",
                "priority",
                "target_type",
                "name",
                "title",
                "linkedin",
                "apollo_email",
                "email_status",
                "fit_score",
                "job_link",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(pending_rows)
        print(writer_output.getvalue().rstrip())
        return 0

    print(f"Apollo lookup targets: {len(pending_rows)}")
    print("")
    for index, row in enumerate(pending_rows, start=1):
        print(
            f"{index}. {row['company']} | {row['name']} | {row['target_type'] or 'unknown'} | "
            f"Priority {row['priority'] or '?'} | Fit {row['fit_score'] or '?'}"
        )
        print(f"   Role: {row['role'] or 'Unknown'}")
        print(f"   Title: {row['title'] or 'Unknown'}")
        print(f"   Email Status: {row['email_status']}")
        if row["linkedin"]:
            print(f"   LinkedIn: {row['linkedin']}")
        if row["job_link"]:
            print(f"   Job Link: {row['job_link']}")
        if row["notes"]:
            print(f"   Notes: {row['notes']}")
        print("")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
