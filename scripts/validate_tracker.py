#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from tracker_table import clean_text, extract_table, first_link_or_text, parse_int


ROOT = Path(__file__).resolve().parents[1]
TRACKERS = {
    "applications.md": ROOT / "application-trackers" / "applications.md",
    "job-intake.md": ROOT / "application-trackers" / "job-intake.md",
}
APPLICATION_REQUIRED = [
    "Company",
    "Role",
    "Location",
    "Source",
    "Job Link",
    "Date Added",
    "Resume Folder",
    "Resume PDF",
    "Status",
    "Applied",
    "Fit Score",
    "Reach Out",
    "Posting Key",
    "Notes",
]
INTAKE_REQUIRED = [
    "Source",
    "Company",
    "Role",
    "Location",
    "Posting Key",
    "Job URL",
    "Discovered At",
    "Posted Age",
    "Fit Score",
    "Status",
    "Reason",
    "Tracker Posting Key",
]
APPLICATION_STATUSES = {
    "Resume Tailored",
    "Ready to Apply",
    "Manual Apply Needed",
    "Applied",
    "Rejected",
    "Archived",
    "Online Assessment",
    "Interviewing",
    "Offer",
}
INTAKE_STATUSES = {"", "New", "Queued", "Tailored", "Manual", "Skipped", "Duplicate", "Expired", "Archived"}
RESUME_REQUIRED_STATUSES = {"Resume Tailored", "Ready to Apply", "Applied"}


def report(path: Path, line_number: int, reason: str, violations: list[str]) -> None:
    violations.append(f"{path}:{line_number}: {reason}")


def validate(path: Path, kind: str) -> list[str]:
    required = APPLICATION_REQUIRED if kind == "applications.md" else INTAKE_REQUIRED
    violations: list[str] = []
    try:
        table = extract_table(path, set(required[:2]))
    except ValueError as exc:
        return [f"{path}:1: {exc}"]

    for column in required:
        if column not in table.header:
            report(path, table.header_line, f"missing required column {column!r}", violations)

    posting_keys: dict[str, list[int]] = defaultdict(list)
    for row in table.rows:
        if len(row.cells) != len(table.header):
            report(
                path,
                row.line_number,
                f"cell count {len(row.cells)} does not match header count {len(table.header)}",
                violations,
            )
            continue

        status = clean_text(row.row.get("Status", ""))
        allowed_statuses = APPLICATION_STATUSES if kind == "applications.md" else INTAKE_STATUSES
        if status not in allowed_statuses:
            report(path, row.line_number, f"invalid Status {status!r}", violations)

        applied = clean_text(row.row.get("Applied", ""))
        if "Applied" in table.header and applied not in {"Yes", "No", ""}:
            report(path, row.line_number, f"invalid Applied {applied!r}", violations)

        fit = parse_int(row.row.get("Fit Score", ""))
        if clean_text(row.row.get("Fit Score", "")) and (fit is None or fit < 1 or fit > 10):
            report(path, row.line_number, f"Fit Score must be an integer 1-10, got {row.row.get('Fit Score', '')!r}", violations)

        posting_key = clean_text(row.row.get("Posting Key", ""))
        if posting_key:
            posting_keys[posting_key].append(row.line_number)

        url_field = "Job Link" if kind == "applications.md" else "Job URL"
        job_link = first_link_or_text(row.row.get(url_field, ""))
        if job_link and not job_link.startswith("http"):
            report(path, row.line_number, f"{url_field} must start with http, got {job_link!r}", violations)

        if kind == "applications.md" and status in RESUME_REQUIRED_STATUSES:
            resume_pdf = first_link_or_text(row.row.get("Resume PDF", ""))
            if not resume_pdf:
                report(path, row.line_number, f"Resume PDF is required when Status is {status!r}", violations)
            elif not Path(resume_pdf).expanduser().exists():
                report(path, row.line_number, f"Resume PDF path does not exist: {resume_pdf}", violations)

    for posting_key, lines in sorted(posting_keys.items()):
        if len(lines) > 1:
            joined = ", ".join(str(line) for line in lines)
            for line in lines:
                report(path, line, f"duplicate Posting Key {posting_key!r}; also appears on lines {joined}", violations)

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate application tracker markdown table schema and row values.")
    parser.add_argument("--file", choices=sorted(TRACKERS), help="Validate one tracker file; defaults to both.")
    args = parser.parse_args()

    paths = [args.file] if args.file else list(TRACKERS)
    violations: list[str] = []
    for name in paths:
        violations.extend(validate(TRACKERS[name], name))

    for violation in violations:
        print(violation)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
