#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
RESUME_TAILOR_SCRIPTS = SCRIPT_DIR.parents[1] / "resume-tailor" / "scripts"
if str(RESUME_TAILOR_SCRIPTS) not in sys.path:
    sys.path.append(str(RESUME_TAILOR_SCRIPTS))

from update_application_tracker import (  # type: ignore
    normalize,
    parse_rows,
    refresh_visualizer_data,
    repo_root_from_args,
    row_from_cells,
    split_row,
    tracker_path,
)
from tracker_data_cache import load_cached_application_rows  # type: ignore

TITLE_LINE = "# Outreach Prospect Tracker"
DESCRIPTION_LINE = (
    "This file tracks company-level prospecting and Apollo email lookup separately "
    "from `application-trackers/applications.md`."
)
QUEUE_COLUMNS = [
    "Company",
    "Role",
    "Posting Key",
    "Fit Score",
    "Status",
    "Reach Out",
    "Job Link",
    "Prospect Count",
    "Ready Emails",
    "Last Updated",
    "Notes",
]
PROSPECT_COLUMNS = [
    "Company",
    "Posting Key",
    "Priority",
    "Target Type",
    "Name",
    "Title",
    "LinkedIn",
    "Apollo Email",
    "Email Status",
    "Notes",
]
EXCLUDED_STATUSES = {"rejected", "archived"}


def escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def split_md_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def build_row(columns: list[str], row: dict[str, str]) -> str:
    return "| " + " | ".join(escape_cell(row.get(column, "")) for column in columns) + " |"


def company_key(company: str, posting_key: str) -> tuple[str, str]:
    return normalize(company), normalize(posting_key)


def load_application_rows(repo_root: Path) -> list[dict[str, str]]:
    cached_rows = load_cached_application_rows(repo_root)
    if cached_rows:
        return cached_rows

    lines = tracker_path(repo_root).read_text().splitlines()
    _, row_lines = parse_rows(lines)
    rows: list[dict[str, str]] = []
    for row_line in row_lines:
        row = row_from_cells(split_row(row_line))
        if row is not None:
            rows.append(row)
    return rows


def outreach_tracker_path(repo_root: Path) -> Path:
    return repo_root / "application-trackers" / "outreach-prospects.md"


def parse_sections(lines: list[str]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    queue_rows: list[dict[str, str]] = []
    prospect_rows: list[dict[str, str]] = []
    section = None

    for line in lines:
        if line.strip() == "## Company Queue":
            section = "queue"
            continue
        if line.strip() == "## Prospect Details":
            section = "prospects"
            continue
        if not line.startswith("| "):
            continue
        if "Company" in line and "Posting Key" in line and "Prospect Count" in line:
            continue
        if "Company" in line and "Posting Key" in line and "Target Type" in line:
            continue
        if set(line.replace("|", "").replace("-", "").strip()) == set():
            continue

        cells = split_md_row(line)
        if section == "queue" and len(cells) == len(QUEUE_COLUMNS):
            queue_rows.append(dict(zip(QUEUE_COLUMNS, cells)))
        elif section == "prospects" and len(cells) == len(PROSPECT_COLUMNS):
            prospect_rows.append(dict(zip(PROSPECT_COLUMNS, cells)))

    return queue_rows, prospect_rows


def render_tracker(queue_rows: list[dict[str, str]], prospect_rows: list[dict[str, str]]) -> str:
    total_companies = len(queue_rows)
    total_prospects = len(prospect_rows)
    ready_emails = sum(1 for row in prospect_rows if normalize(row.get("Email Status", "")) == "ready")
    missing_emails = sum(1 for row in prospect_rows if normalize(row.get("Email Status", "")) in {"", "needs apollo"})

    parts = [
        TITLE_LINE,
        "",
        DESCRIPTION_LINE,
        "",
        f"Companies queued: {total_companies}",
        f"Prospects recorded: {total_prospects} | Ready emails: {ready_emails} | Pending Apollo: {missing_emails}",
        "",
        "## Company Queue",
        "",
        "| " + " | ".join(QUEUE_COLUMNS) + " |",
        "| " + " | ".join(["---"] * len(QUEUE_COLUMNS)) + " |",
    ]
    parts.extend(build_row(QUEUE_COLUMNS, row) for row in queue_rows)
    parts.extend(
        [
            "",
            "## Prospect Details",
            "",
            "| " + " | ".join(PROSPECT_COLUMNS) + " |",
            "| " + " | ".join(["---"] * len(PROSPECT_COLUMNS)) + " |",
        ]
    )
    parts.extend(build_row(PROSPECT_COLUMNS, row) for row in prospect_rows)
    return "\n".join(parts) + "\n"


def count_prospects(prospect_rows: list[dict[str, str]], company: str, posting_key: str) -> tuple[int, int]:
    total = 0
    ready = 0
    key = company_key(company, posting_key)
    for row in prospect_rows:
        if company_key(row["Company"], row["Posting Key"]) != key:
            continue
        total += 1
        if normalize(row.get("Email Status", "")) == "ready":
            ready += 1
    return total, ready


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed or refresh the separate company prospect tracker from the application tracker."
    )
    parser.add_argument("--root", default=None, help="Optional repo root override")
    parser.add_argument("--company", default="", help="Only sync one company")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit after filtering")
    args = parser.parse_args()

    repo_root = repo_root_from_args(args.root)
    source_rows = load_application_rows(repo_root)
    target_path = outreach_tracker_path(repo_root)
    existing_queue: list[dict[str, str]] = []
    existing_prospects: list[dict[str, str]] = []
    if target_path.exists():
        existing_queue, existing_prospects = parse_sections(target_path.read_text().splitlines())

    queue_by_key = {
        company_key(row["Company"], row["Posting Key"]): row.copy()
        for row in existing_queue
    }

    company_filter = normalize(args.company)
    selected_rows: list[dict[str, str]] = []
    for row in source_rows:
        if normalize(row.get("Status", "")) in EXCLUDED_STATUSES:
            continue
        if company_filter and normalize(row.get("Company", "")) != company_filter:
            continue
        selected_rows.append(row)

    selected_rows.sort(
        key=lambda row: (
            int(row["Fit Score"]) if row.get("Fit Score", "").isdigit() else -1,
            row.get("Date Added", ""),
            row.get("Company", "").lower(),
        ),
        reverse=True,
    )

    if args.limit > 0:
        selected_rows = selected_rows[: args.limit]

    queue_rows: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()
    for source in selected_rows:
        key = company_key(source["Company"], source["Posting Key"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        total, ready = count_prospects(existing_prospects, source["Company"], source["Posting Key"])
        existing = queue_by_key.get(key, {})
        queue_rows.append(
            {
                "Company": source["Company"],
                "Role": source["Role"],
                "Posting Key": source["Posting Key"],
                "Fit Score": source["Fit Score"],
                "Status": source["Status"],
                "Reach Out": source["Reach Out"],
                "Job Link": source["Job Link"],
                "Prospect Count": str(total) if total else "",
                "Ready Emails": str(ready) if ready else "",
                "Last Updated": existing.get("Last Updated", ""),
                "Notes": existing.get("Notes", ""),
            }
        )

    queue_rows.sort(
        key=lambda row: (
            int(row["Fit Score"]) if row.get("Fit Score", "").isdigit() else -1,
            row.get("Company", "").lower(),
        ),
        reverse=True,
    )

    target_path.write_text(render_tracker(queue_rows, existing_prospects))
    refresh_visualizer_data(repo_root)
    print(f"Wrote {target_path} with {len(queue_rows)} queued companies and {len(existing_prospects)} prospects.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
