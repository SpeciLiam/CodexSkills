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
)


DEFAULT_EXCLUDED_STATUSES = {"rejected", "archived"}


def shell_escape_double_quotes(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_search_query(company: str, role: str, source: str) -> str:
    terms = [f'"{company}"']
    if role:
        terms.append(f'"{role}"')
    company_role = " OR ".join(terms)

    source_filters = {
        "linkedin": "from:(jobs-listings@linkedin.com OR jobs-noreply@linkedin.com OR linkedin-noreply@linkedin.com)",
        "ashby": "from:(ashbyhq.com OR jobs@ashbyhq.com)",
        "company site": '("application" OR "interview" OR "assessment" OR "next steps")',
    }

    source_filter = source_filters.get(normalize(source), "")
    parts = ["newer_than:30d", f"({company_role})"]
    if source_filter:
        parts.insert(0, source_filter)
    return " ".join(parts)


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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the active application target list and Gmail search plan for tracker refreshes."
    )
    parser.add_argument("--root", default=None, help="Optional repo root override")
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
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional maximum number of active rows to emit",
    )
    args = parser.parse_args()

    repo_root = repo_root_from_args(args.root)
    rows = load_rows(repo_root)

    include_statuses = {normalize(value) for value in args.include_status if value.strip()}
    exclude_statuses = DEFAULT_EXCLUDED_STATUSES | {
        normalize(value) for value in args.exclude_status if value.strip()
    }

    active_rows = []
    for row in rows:
        status = normalize(row.get("Status", ""))
        if include_statuses and status not in include_statuses:
            continue
        if status in exclude_statuses:
            continue
        active_rows.append(
            {
                "company": row["Company"],
                "role": row["Role"],
                "status": row["Status"],
                "posting_key": row["Posting Key"],
                "job_link": row["Job Link"],
                "source": row["Source"],
                "query": build_search_query(row["Company"], row["Role"], row["Source"]),
            }
        )

    if args.limit > 0:
        active_rows = active_rows[: args.limit]

    if args.format == "json":
        print(json.dumps(active_rows, indent=2))
        return 0

    print(f"Active application targets: {len(active_rows)}")
    print("")
    for index, row in enumerate(active_rows, start=1):
        print(f"{index}. {row['company']} | {row['role']} | {row['status']}")
        print(f"   Posting Key: {row['posting_key']}")
        print(f"   Gmail Query: {row['query']}")
        print("")

    if active_rows:
        joined_queries = " OR ".join(f'("{shell_escape_double_quotes(row["company"])}")' for row in active_rows[:8])
        print("Broad backup query:")
        print(f'newer_than:30d ({joined_queries}) ("application" OR "interview" OR "assessment" OR "next steps")')

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
