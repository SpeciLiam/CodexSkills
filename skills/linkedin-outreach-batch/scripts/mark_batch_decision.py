#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BATCH_MD = ROOT / "application-trackers" / "linkedin-recruiter-batches.md"
COLUMNS = [
    "Batch",
    "Company",
    "Role",
    "Posting Key",
    "Fit Score",
    "Status",
    "Recruiter Name",
    "Recruiter Profile",
    "Route",
    "Connection Note",
    "Approval",
    "Outcome",
    "Last Checked",
    "Notes",
]


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip().replace("\\|", "|") for cell in line.split("|")]


def extract_rows(markdown: str) -> list[dict[str, str]]:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "## Recruiter Batch":
            header_index = index + 1
            while header_index < len(lines) and not lines[header_index].strip().startswith("|"):
                header_index += 1
            headers = split_row(lines[header_index])
            row_index = header_index + 2
            rows: list[dict[str, str]] = []
            while row_index < len(lines) and lines[row_index].strip().startswith("|"):
                cells = split_row(lines[row_index])
                if len(cells) < len(headers):
                    cells += [""] * (len(headers) - len(cells))
                rows.append(dict(zip(headers, cells[: len(headers)])))
                row_index += 1
            return rows
    return []


def escape_cell(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ").strip()


def render_table(rows: list[dict[str, str]]) -> str:
    table = [
        "| " + " | ".join(COLUMNS) + " |",
        "| " + " | ".join("---" for _ in COLUMNS) + " |",
    ]
    for row in rows:
        table.append("| " + " | ".join(escape_cell(row.get(column, "")) for column in COLUMNS) + " |")
    return "\n".join(table)


def replace_table(markdown: str, rows: list[dict[str, str]]) -> str:
    pattern = re.compile(r"(## Recruiter Batch\n)(?:\n?)(\|.*?(?:\n\|.*?)*)(?:\n\n|$)", re.DOTALL)
    replacement = "\\1" + render_table(rows) + "\n\n"
    if pattern.search(markdown):
        return pattern.sub(replacement, markdown, count=1)
    return markdown.rstrip() + "\n\n## Recruiter Batch\n" + render_table(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Update recruiter batch approval/outcome fields.")
    parser.add_argument("--posting-key", required=True)
    parser.add_argument("--recruiter-name", default=None)
    parser.add_argument("--recruiter-profile", default=None)
    parser.add_argument("--approval", choices=("Needs recruiter", "Needs approval", "Approved", "Rejected"), default=None)
    parser.add_argument("--outcome", choices=("Not reached out", "Sent", "Skipped", "Blocked"), default=None)
    parser.add_argument("--notes", default=None)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--path", type=Path, default=BATCH_MD)
    args = parser.parse_args()

    markdown = args.path.read_text(encoding="utf-8")
    rows = extract_rows(markdown)
    for row in rows:
        if row.get("Posting Key") != args.posting_key:
            continue
        if args.recruiter_name is not None:
            row["Recruiter Name"] = args.recruiter_name
        if args.recruiter_profile is not None:
            row["Recruiter Profile"] = args.recruiter_profile
        if args.approval is not None:
            row["Approval"] = args.approval
        if args.outcome is not None:
            row["Outcome"] = args.outcome
        if args.notes is not None:
            existing = row.get("Notes", "").strip()
            row["Notes"] = f"{existing}; {args.notes}".strip("; ") if existing else args.notes
        row["Last Checked"] = args.date
        break
    else:
        raise SystemExit(f"No batch row found for posting key {args.posting_key}")

    args.path.write_text(replace_table(markdown, rows), encoding="utf-8")
    print(f"Updated batch row {args.posting_key}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
