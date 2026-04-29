#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from application_fit import load_profile, score_application, should_reach_out

CURRENT_COLUMNS = [
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
    "Engineer Contact",
    "Engineer Profile",
    "Notes",
]

PRE_ENGINEER_COLUMNS = [column for column in CURRENT_COLUMNS if column not in {"Engineer Contact", "Engineer Profile"}]
PRE_RECRUITER_COLUMNS = [
    column
    for column in CURRENT_COLUMNS
    if column not in {"Recruiter Contact", "Recruiter Profile", "Engineer Contact", "Engineer Profile"}
]

LEGACY_COLUMNS = [
    "Company",
    "Role",
    "Applied",
    "Status",
    "Company Resume",
    "Referral",
    "Date Added",
    "Location",
    "Source",
    "Job Link",
    "Posting Key",
    "Resume Folder",
    "Resume PDF",
    "Notes",
]

DEFAULT_COLUMNS = CURRENT_COLUMNS

TITLE_LINE = "# Application Tracker"
DESCRIPTION_LINE = (
    "This file tracks roles that have had a tailored resume created from the "
    "`resume-tailor` workflow."
)


def truthy(value: str) -> bool:
    return normalize(value) in {"yes", "true", "1", "x"}


def row_from_cells(cells: list[str]) -> dict[str, str] | None:
    if len(cells) == len(DEFAULT_COLUMNS):
        return dict(zip(DEFAULT_COLUMNS, cells))
    if len(cells) == len(PRE_ENGINEER_COLUMNS):
        row = dict(zip(PRE_ENGINEER_COLUMNS, cells))
        row["Engineer Contact"] = ""
        row["Engineer Profile"] = ""
        return {column: row.get(column, "") for column in DEFAULT_COLUMNS}
    if len(cells) == len(PRE_RECRUITER_COLUMNS):
        row = dict(zip(PRE_RECRUITER_COLUMNS, cells))
        row["Recruiter Contact"] = ""
        row["Recruiter Profile"] = ""
        row["Engineer Contact"] = ""
        row["Engineer Profile"] = ""
        return {column: row.get(column, "") for column in DEFAULT_COLUMNS}
    if len(cells) == len(LEGACY_COLUMNS):
        row = dict(zip(LEGACY_COLUMNS, cells))
        row["Fit Score"] = ""
        row["Reach Out"] = ""
        row["Recruiter Contact"] = ""
        row["Recruiter Profile"] = ""
        row["Engineer Contact"] = ""
        row["Engineer Profile"] = ""
        return {column: row.get(column, "") for column in DEFAULT_COLUMNS}
    return None


def repo_root_from_args(root: str | None) -> Path:
    if root:
        return Path(root).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def tracker_path(repo_root: Path) -> Path:
    return repo_root / "application-trackers" / "applications.md"


def escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())


def posting_key(job_link: str, role: str) -> str:
    parsed = urlparse(job_link)
    query = parse_qs(parsed.query)
    key_candidates = []

    for field in ("currentJobId", "jobId", "gh_jid", "jk"):
        if field in query and query[field]:
            key_candidates.append(query[field][0])

    path_parts = [part for part in parsed.path.split("/") if part]
    if path_parts:
        last_part = path_parts[-1].strip().strip("/")
        if last_part and last_part.lower() not in {"application", "apply"}:
            key_candidates.append(last_part)
    if len(path_parts) > 1:
        prev_part = path_parts[-2].strip().strip("/")
        if prev_part:
            key_candidates.append(prev_part)

    for candidate in key_candidates:
        cleaned = candidate.strip().strip("/")
        if cleaned:
            return cleaned

    fallback = "".join(char if char.isalnum() else "_" for char in role.strip())
    return "_".join(part for part in fallback.split("_") if part) or "unknown-posting"


def ensure_tracker(tracker: Path) -> None:
    tracker.parent.mkdir(parents=True, exist_ok=True)
    if tracker.exists():
        return

    tracker.write_text(render_tracker([]))


def render_tracker(rows: list[str]) -> str:
    parsed_rows = []
    for row_line in rows:
        row = row_from_cells(split_row(row_line))
        if row is not None:
            parsed_rows.append(row)

    total_count = len(parsed_rows)
    applied_count = sum(1 for row in parsed_rows if truthy(row.get("Applied", "")))
    rejected_count = sum(1 for row in parsed_rows if normalize(row.get("Status", "")) == "rejected")
    archived_count = sum(1 for row in parsed_rows if normalize(row.get("Status", "")) == "archived")
    offer_count = sum(1 for row in parsed_rows if normalize(row.get("Status", "")) == "offer")
    interviewing_count = sum(1 for row in parsed_rows if normalize(row.get("Status", "")) == "interviewing")
    assessment_count = sum(1 for row in parsed_rows if normalize(row.get("Status", "")) == "online assessment")
    unapplied_count = total_count - applied_count
    active_count = total_count - rejected_count - archived_count
    reach_out_count = sum(1 for row in parsed_rows if truthy(row.get("Reach Out", "")))
    high_fit_count = sum(
        1
        for row in parsed_rows
        if row.get("Fit Score", "").strip().isdigit() and int(row["Fit Score"]) >= 8
    )

    count_line = f"Total applications tracked: {total_count}"
    summary_line = (
        f"Applied: {applied_count} | Unapplied: {unapplied_count} | "
        f"Active: {active_count} | Rejected: {rejected_count} | Archived: {archived_count}"
    )
    pipeline_line = (
        f"Interviewing: {interviewing_count} | Online Assessment: {assessment_count} | "
        f"Offer: {offer_count} | Reach Out: {reach_out_count} | Fit >= 8: {high_fit_count}"
    )
    table_header = "| " + " | ".join(DEFAULT_COLUMNS) + " |"
    table_divider = "| " + " | ".join(["---"] * len(DEFAULT_COLUMNS)) + " |"
    parts = [
        TITLE_LINE,
        "",
        DESCRIPTION_LINE,
        "",
        count_line,
        summary_line,
        pipeline_line,
        "",
        table_header,
        table_divider,
    ]
    parts.extend(rows)
    return "\n".join(parts) + "\n"


def parse_rows(lines: list[str]) -> tuple[int, list[str]]:
    header_index = -1
    rows: list[str] = []
    for index, line in enumerate(lines):
        if line.startswith("| ") and "Date Added" in line and "Company" in line:
            header_index = index
            continue
        if header_index >= 0 and index > header_index + 1 and line.startswith("| "):
            rows.append(line)
    return header_index, rows


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def row_key(row: dict[str, str]) -> tuple[str, str]:
    return (
        normalize(row["Company"]),
        normalize(row["Posting Key"]),
    )


def build_row(data: dict[str, str]) -> str:
    return "| " + " | ".join(escape_cell(data[column]) for column in DEFAULT_COLUMNS) + " |"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update the markdown application tracker.")
    parser.add_argument("--company", required=True, help="Company name")
    parser.add_argument("--role", required=True, help="Role title")
    parser.add_argument("--job-link", required=True, help="Job posting URL")
    parser.add_argument("--resume-folder", required=True, help="Path to the tailored resume folder")
    parser.add_argument("--resume-pdf", required=True, help="Path to the tailored resume PDF")
    parser.add_argument("--date-added", required=True, help="Date the role was added, in YYYY-MM-DD")
    parser.add_argument("--location", default="", help="Role location")
    parser.add_argument("--source", default="", help="Job board or source, such as Ashby or LinkedIn")
    parser.add_argument("--applied", default="", help="Applied status, such as Yes or No")
    parser.add_argument("--referral", default="", help="Referral status or referrer name")
    parser.add_argument("--fit-score", default="", help="Manual fit score override from 1 to 10")
    parser.add_argument("--reach-out", default="", help="Whether this role deserves direct recruiter outreach, such as Yes")
    parser.add_argument("--status", default="Resume Tailored", help="Current application stage")
    parser.add_argument("--notes", default="", help="Freeform notes")
    parser.add_argument("--sync-notion", action="store_true", help="Also sync Fit Score and Reach Out for this row to Notion")
    parser.add_argument("--notion-token-env", default="NOTION_TOKEN", help="Environment variable holding the Notion integration token")
    parser.add_argument("--update-notion-title", action="store_true", help="Also update the Notion database title count when syncing")
    parser.add_argument("--root", default=None, help="Optional repo root override")
    args = parser.parse_args()

    repo_root = repo_root_from_args(args.root)
    profile = load_profile(repo_root)
    tracker = tracker_path(repo_root)
    ensure_tracker(tracker)

    lines = tracker.read_text().splitlines()
    header_index, rows = parse_rows(lines)
    if header_index < 0:
        raise SystemExit(f"Could not find tracker table in {tracker}")

    new_row = {
        "Company": args.company,
        "Role": args.role,
        "Applied": args.applied,
        "Status": args.status,
        "Fit Score": args.fit_score,
        "Reach Out": args.reach_out,
        "Company Resume": f"[{args.company} - {args.role}]({args.resume_pdf})",
        "Referral": args.referral,
        "Date Added": args.date_added,
        "Location": args.location,
        "Source": args.source,
        "Job Link": f"[Posting]({args.job_link})",
        "Posting Key": posting_key(args.job_link, args.role),
        "Resume Folder": f"[Folder]({args.resume_folder})",
        "Resume PDF": f"[PDF]({args.resume_pdf})",
        "Recruiter Contact": "",
        "Recruiter Profile": "",
        "Engineer Contact": "",
        "Engineer Profile": "",
        "Notes": args.notes,
    }

    if not new_row["Fit Score"]:
        new_row["Fit Score"] = str(score_application(new_row, profile))

    if not new_row["Reach Out"]:
        new_row["Reach Out"] = "Yes" if should_reach_out(int(new_row["Fit Score"]), profile, new_row) else ""

    updated_rows: list[str] = []
    target_key = row_key(new_row)
    replaced = False

    for row_line in rows:
        cells = split_row(row_line)
        row = row_from_cells(cells)
        if row is None:
            updated_rows.append(row_line)
            continue

        if row_key(row) == target_key:
            updated_rows.append(build_row(new_row))
            replaced = True
        else:
            updated_rows.append(build_row(row))

    if not replaced:
        updated_rows.append(build_row(new_row))

    tracker.write_text(render_tracker(updated_rows))

    if args.sync_notion:
        from notion_sync import sync_tracker_to_notion, token_from_env

        token = token_from_env(args.notion_token_env)
        sync_tracker_to_notion(
            repo_root=repo_root,
            token=token,
            posting_key=new_row["Posting Key"],
            update_title=args.update_notion_title,
        )

    print(tracker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
