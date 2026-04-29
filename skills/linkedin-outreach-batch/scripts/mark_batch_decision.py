#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CONTACT_CONFIG = {
    "recruiter": {
        "path": ROOT / "application-trackers" / "linkedin-recruiter-batches.md",
        "heading": "Recruiter Batch",
        "verified_heading": "Verified Recruiter Contacts (Needs approval)",
        "needs_heading": "Needs Recruiter",
        "needs_approval": "Needs recruiter",
        "name_column": "Recruiter Name",
        "profile_column": "Recruiter Profile",
        "position_column": "Position",
        "approval_choices": ("Needs recruiter", "Needs approval", "Approved", "Rejected"),
    },
    "engineer": {
        "path": ROOT / "application-trackers" / "linkedin-engineer-batches.md",
        "heading": "Engineer Batch",
        "verified_heading": "Verified Engineer Contacts (Needs approval)",
        "needs_heading": "Needs Engineer",
        "needs_approval": "Needs engineer",
        "name_column": "Engineer Name",
        "profile_column": "Engineer Profile",
        "position_column": "Position",
        "approval_choices": ("Needs engineer", "Needs approval", "Approved", "Rejected"),
    },
}


def columns_for(config: dict[str, object]) -> list[str]:
    return [
        "Batch",
        "Company",
        "Role",
        "Posting Key",
        "Fit Score",
        "Status",
        str(config["name_column"]),
        str(config["profile_column"]),
        str(config["position_column"]),
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


def extract_rows(markdown: str, heading: str) -> list[dict[str, str]]:
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.strip() == f"## {heading}":
            rows: list[dict[str, str]] = []
            row_index = index + 1
            while row_index < len(lines) and not lines[row_index].strip().startswith("## "):
                if (
                    lines[row_index].strip().startswith("|")
                    and row_index + 1 < len(lines)
                    and re.match(r"^\|\s*:?-{3,}:?", lines[row_index + 1].strip())
                ):
                    headers = split_row(lines[row_index])
                    row_index += 2
                    while row_index < len(lines) and lines[row_index].strip().startswith("|"):
                        cells = split_row(lines[row_index])
                        if len(cells) < len(headers):
                            cells += [""] * (len(headers) - len(cells))
                        rows.append(dict(zip(headers, cells[: len(headers)])))
                        row_index += 1
                    continue
                row_index += 1
            return rows
    return []


def escape_cell(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ").strip()


def render_table(rows: list[dict[str, str]], columns: list[str]) -> str:
    table = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        table.append("| " + " | ".join(escape_cell(row.get(column, "")) for column in columns) + " |")
    return "\n".join(table)


def replace_table(markdown: str, rows: list[dict[str, str]], config: dict[str, object]) -> str:
    heading = str(config["heading"])
    columns = columns_for(config)
    verified_rows = [row for row in rows if row.get("Approval") == "Needs approval"]
    needs_rows = [row for row in rows if row.get("Approval") == str(config["needs_approval"])]
    other_rows = [
        row
        for row in rows
        if row.get("Approval") not in {"Needs approval", str(config["needs_approval"])}
    ]
    section_parts = [
        f"## {heading}",
        "",
        f"### {config['verified_heading']}",
        render_table(verified_rows, columns),
        "",
        f"### {config['needs_heading']}",
        render_table(needs_rows, columns),
    ]
    if other_rows:
        section_parts.extend(["", "### Other Decisions", render_table(other_rows, columns)])
    replacement = "\n".join(section_parts).rstrip() + "\n"

    pattern = re.compile(
        rf"## {re.escape(heading)}\n.*?(?=\n## |\Z)",
        re.DOTALL,
    )
    if pattern.search(markdown):
        return pattern.sub(replacement, markdown, count=1)
    return markdown.rstrip() + "\n\n" + replacement


def main() -> int:
    parser = argparse.ArgumentParser(description="Update LinkedIn batch approval/outcome fields.")
    parser.add_argument("--posting-key", required=True)
    parser.add_argument("--contact-type", choices=sorted(CONTACT_CONFIG), default="recruiter")
    parser.add_argument("--contact-name", default=None)
    parser.add_argument("--contact-profile", default=None)
    parser.add_argument("--contact-position", default=None)
    parser.add_argument("--recruiter-name", default=None)
    parser.add_argument("--recruiter-profile", default=None)
    parser.add_argument("--approval", choices=("Needs recruiter", "Needs engineer", "Needs approval", "Approved", "Rejected"), default=None)
    parser.add_argument("--outcome", choices=("Not reached out", "Sent", "Skipped", "Blocked"), default=None)
    parser.add_argument("--notes", default=None)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--path", type=Path)
    args = parser.parse_args()

    config = CONTACT_CONFIG[args.contact_type]
    path = args.path or Path(config["path"])
    markdown = path.read_text(encoding="utf-8")
    rows = extract_rows(markdown, str(config["heading"]))
    for row in rows:
        if row.get("Posting Key") != args.posting_key:
            continue
        contact_name = args.contact_name if args.contact_name is not None else args.recruiter_name
        contact_profile = args.contact_profile if args.contact_profile is not None else args.recruiter_profile
        if contact_name is not None:
            row[str(config["name_column"])] = contact_name
        if contact_profile is not None:
            row[str(config["profile_column"])] = contact_profile
        if args.contact_position is not None:
            row[str(config["position_column"])] = args.contact_position
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

    path.write_text(replace_table(markdown, rows, config), encoding="utf-8")
    print(f"Updated batch row {args.posting_key}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
