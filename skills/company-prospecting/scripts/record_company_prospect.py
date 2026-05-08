#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.append(str(SCRIPT_DIR))

from sync_company_prospect_tracker import (  # type: ignore
    PROSPECT_COLUMNS,
    QUEUE_COLUMNS,
    company_key,
    outreach_tracker_path,
    parse_sections,
    render_tracker,
    repo_root_from_args,
)


def normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())


def find_queue_row(queue_rows: list[dict[str, str]], company: str, posting_key: str) -> dict[str, str] | None:
    key = company_key(company, posting_key)
    for row in queue_rows:
        if company_key(row["Company"], row["Posting Key"]) == key:
            return row
    return None


def update_counts(queue_rows: list[dict[str, str]], prospect_rows: list[dict[str, str]]) -> None:
    for queue_row in queue_rows:
        key = company_key(queue_row["Company"], queue_row["Posting Key"])
        matching = [row for row in prospect_rows if company_key(row["Company"], row["Posting Key"]) == key]
        queue_row["Prospect Count"] = str(len(matching)) if matching else ""
        ready = sum(1 for row in matching if normalize(row.get("Email Status", "")) == "ready")
        queue_row["Ready Emails"] = str(ready) if ready else ""


def refresh_visualizer_data(repo_root: Path) -> None:
    subprocess.run(
        ["python3", "skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py"],
        cwd=repo_root,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record or update one company prospect row in outreach-prospects.md."
    )
    parser.add_argument("--company", required=True, help="Company name")
    parser.add_argument("--posting-key", required=True, help="Posting key from the application tracker")
    parser.add_argument("--priority", required=True, help="Priority rank such as 1, 2, or 3")
    parser.add_argument("--target-type", default="", help="recruiter, alumni, engineer, or general")
    parser.add_argument("--name", required=True, help="Prospect name")
    parser.add_argument("--title", default="", help="Prospect job title")
    parser.add_argument("--linkedin-url", default="", help="LinkedIn profile URL")
    parser.add_argument("--apollo-email", default="", help="Apollo email result")
    parser.add_argument("--email-status", default="", help="Needs Apollo, Ready, Bounced, Sent, etc.")
    parser.add_argument("--notes", default="", help="Optional notes")
    parser.add_argument("--root", default=None, help="Optional repo root override")
    args = parser.parse_args()

    repo_root = repo_root_from_args(args.root)
    tracker = outreach_tracker_path(repo_root)
    if not tracker.exists():
        raise SystemExit(f"Prospect tracker does not exist yet: {tracker}")

    queue_rows, prospect_rows = parse_sections(tracker.read_text().splitlines())
    queue_row = find_queue_row(queue_rows, args.company, args.posting_key)
    if queue_row is None:
        raise SystemExit("Could not find the company in the company queue. Run sync_company_prospect_tracker.py first.")

    key = company_key(args.company, args.posting_key)
    target_priority = normalize(args.priority)
    target_name = normalize(args.name)
    existing = None
    for row in prospect_rows:
        same_key = company_key(row["Company"], row["Posting Key"]) == key
        if not same_key:
            continue
        if normalize(row.get("Priority", "")) == target_priority:
            existing = row
            break
        if normalize(row.get("Name", "")) == target_name:
            existing = row
            break

    if existing is None:
        existing = {column: "" for column in PROSPECT_COLUMNS}
        existing["Company"] = queue_row["Company"]
        existing["Posting Key"] = queue_row["Posting Key"]
        existing["Priority"] = args.priority
        prospect_rows.append(existing)

    updates = {
        "Target Type": args.target_type,
        "Name": args.name,
        "Title": args.title,
        "LinkedIn": args.linkedin_url,
        "Apollo Email": args.apollo_email,
        "Email Status": args.email_status,
        "Notes": args.notes,
    }

    for column, value in updates.items():
        if value.strip():
            existing[column] = value

    existing["Priority"] = args.priority
    prospect_rows.sort(
        key=lambda row: (
            row.get("Company", "").lower(),
            row.get("Posting Key", "").lower(),
            int(row["Priority"]) if row.get("Priority", "").isdigit() else 999,
            row.get("Name", "").lower(),
        )
    )
    update_counts(queue_rows, prospect_rows)
    tracker.write_text(render_tracker(queue_rows, prospect_rows))
    refresh_visualizer_data(repo_root)
    print(f"Recorded prospect {args.name} for {args.company} ({args.posting_key}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
