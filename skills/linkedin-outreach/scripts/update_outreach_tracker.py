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
    render_tracker,
    repo_root_from_args,
    row_from_cells,
    split_row,
    tracker_path,
)


def format_contact(name: str, profile_url: str) -> str:
    if profile_url.strip():
        return f"[{name}]({profile_url})"
    return name


def append_note(existing: str, addition: str) -> str:
    existing = existing.strip()
    addition = addition.strip()
    if not existing:
        return addition
    if addition in existing:
        return existing
    separator = "; " if not existing.endswith((".", "!", "?")) else " "
    return existing + separator + addition


def find_row(
    rows: list[dict[str, str]],
    *,
    company: str,
    role: str,
    posting_key: str,
) -> dict[str, str] | None:
    posting_key_norm = normalize(posting_key)
    company_norm = normalize(company)
    role_norm = normalize(role)

    if posting_key_norm:
        for row in rows:
            if normalize(row.get("Posting Key", "")) == posting_key_norm:
                return row

    for row in rows:
        if normalize(row.get("Company", "")) == company_norm and normalize(row.get("Role", "")) == role_norm:
            return row

    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record completed LinkedIn outreach in the markdown tracker."
    )
    parser.add_argument("--company", required=True, help="Company name")
    parser.add_argument("--role", default="", help="Role title, used when posting key is not available")
    parser.add_argument("--posting-key", default="", help="Posting key, preferred row identifier")
    parser.add_argument("--contact-name", required=True, help="Name of the person contacted")
    parser.add_argument("--profile-url", default="", help="LinkedIn profile URL")
    parser.add_argument(
        "--contact-type",
        choices=("recruiter", "engineer", "general"),
        default="recruiter",
        help="Type of contact that was reached out to",
    )
    parser.add_argument("--date", required=True, help="Date outreach was sent, in YYYY-MM-DD")
    parser.add_argument("--root", default=None, help="Optional repo root override")
    args = parser.parse_args()

    repo_root = repo_root_from_args(args.root)
    tracker = tracker_path(repo_root)
    lines = tracker.read_text().splitlines()
    _, row_lines = parse_rows(lines)

    rows: list[dict[str, str]] = []
    for row_line in row_lines:
        row = row_from_cells(split_row(row_line))
        if row is not None:
            rows.append(row)

    row = find_row(rows, company=args.company, role=args.role, posting_key=args.posting_key)
    if row is None:
        raise SystemExit("Could not find matching tracker row.")

    contact_label = args.contact_type.capitalize()
    contact_text = format_contact(args.contact_name, args.profile_url)
    addition = f"LinkedIn invite sent to {contact_text} ({contact_label}) {args.date}"

    if contact_text in row.get("Notes", "") and args.date in row.get("Notes", ""):
        print("Tracker already includes this outreach note.")
        return 0

    row["Notes"] = append_note(row.get("Notes", ""), addition)

    if args.contact_type == "recruiter":
        if not row.get("Recruiter Contact", "").strip():
            row["Recruiter Contact"] = args.contact_name
        if args.profile_url.strip() and not row.get("Recruiter Profile", "").strip():
            row["Recruiter Profile"] = f"[Profile]({args.profile_url})"

    new_lines = [build_row(row) for row in rows]
    tracker.write_text(render_tracker(new_lines))

    print(
        f"Updated tracker for {row['Company']} | {row['Role']} with "
        f"{args.contact_type} outreach to {args.contact_name}."
    )
    return 0


def build_row(data: dict[str, str]) -> str:
    columns = [
        "Company",
        "Role",
        "Applied",
        "Status",
        "Fit Score",
        "Reach Out",
        "Company Resume",
        "Referral",
        "Date Added",
        "Location",
        "Source",
        "Job Link",
        "Posting Key",
        "Resume Folder",
        "Resume PDF",
        "Recruiter Contact",
        "Recruiter Profile",
        "Notes",
    ]

    def escape_cell(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ").strip()

    return "| " + " | ".join(escape_cell(data.get(column, "")) for column in columns) + " |"


if __name__ == "__main__":
    raise SystemExit(main())
