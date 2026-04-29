#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
TRACKER_JSON = ROOT / "application-visualizer" / "src" / "data" / "tracker-data.json"
MAX_NOTE_LENGTH = 300


CONTACT_CONFIG = {
    "recruiter": {
        "output": ROOT / "application-trackers" / "linkedin-recruiter-batches.md",
        "batch_prefix": "recruiter",
        "title": "LinkedIn Recruiter Batch Tracker",
        "heading": "Recruiter Batch",
        "row_label": "recruiter",
        "ready_label": "Labeled recruiters",
        "missing_approval": "Needs recruiter",
        "name_column": "Recruiter Name",
        "profile_column": "Recruiter Profile",
        "position_column": "Position",
        "app_name_field": "recruiterContact",
        "app_profile_field": "recruiterProfile",
    },
    "engineer": {
        "output": ROOT / "application-trackers" / "linkedin-engineer-batches.md",
        "batch_prefix": "engineer",
        "title": "LinkedIn Engineer Batch Tracker",
        "heading": "Engineer Batch",
        "row_label": "engineer",
        "ready_label": "Labeled engineers",
        "missing_approval": "Needs engineer",
        "name_column": "Engineer Name",
        "profile_column": "Engineer Profile",
        "position_column": "Position",
        "app_name_field": "engineerContact",
        "app_profile_field": "engineerProfile",
    },
}


def columns_for(config: dict[str, str | Path]) -> list[str]:
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


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


SKIP_NOTE_PATTERNS = (
    "no outreach planned",
    "asks applicants not to contact employees",
)


def split_markdown_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip().replace("\\|", "|") for cell in line.split("|")]


def extract_table(markdown: str, heading: str) -> list[dict[str, str]]:
    lines = markdown.splitlines()
    active_heading = "Main"
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line.startswith("## "):
            active_heading = line.removeprefix("## ").strip()
        if (
            active_heading == heading
            and line.startswith("|")
            and index + 1 < len(lines)
            and re.match(r"^\|\s*:?-{3,}:?", lines[index + 1].strip())
        ):
            headers = split_markdown_row(line)
            rows: list[dict[str, str]] = []
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = split_markdown_row(lines[index])
                if len(cells) < len(headers):
                    cells += [""] * (len(headers) - len(cells))
                rows.append(dict(zip(headers, cells[: len(headers)])))
                index += 1
            return rows
        index += 1
    return []


def escape_cell(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", " ").strip()


def markdown_link(label: str, url: str) -> str:
    label = (label or "Profile").strip()
    url = (url or "").strip()
    return f"[{label}]({url})" if url else ""


def first_link(value: str) -> str:
    match = re.search(r"\[[^\]]+\]\(([^)]+)\)", value or "")
    return match.group(1) if match else (value or "").strip()


def clean_link_label(value: str) -> str:
    match = re.search(r"\[([^\]]+)\]\([^)]+\)", value or "")
    return match.group(1) if match else (value or "").strip()


def render_table(rows: list[dict[str, str]], columns: list[str]) -> str:
    output = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(escape_cell(row.get(column, "")) for column in columns) + " |")
    return "\n".join(output)


def existing_rows(path: Path, heading: str) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows = extract_table(path.read_text(encoding="utf-8"), heading)
    return {row.get("Posting Key", ""): row for row in rows if row.get("Posting Key")}


def load_applications(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("applications", [])


def needs_contact(app: dict[str, Any], config: dict[str, str | Path]) -> bool:
    if app.get(str(config["app_name_field"])) or app.get(str(config["app_profile_field"])):
        return False
    if str(app.get("status", "")).lower() in {"rejected", "archived"}:
        return False
    notes = str(app.get("notes", "")).lower()
    return not any(pattern in notes for pattern in SKIP_NOTE_PATTERNS)


def first_name(name: str) -> str:
    cleaned = " ".join(name.split()).strip()
    return cleaned.split(" ", 1)[0] if cleaned else ""


def compact_role(role: str) -> str:
    value = " ".join((role or "").split())
    replacements = [
        ("Software Engineer", "SWE"),
        ("Forward Deployed Engineer", "FDE"),
        ("Full Stack", "Full-Stack"),
        ("New College Grad", "New Grad"),
        ("University Graduate", "New Grad"),
        ("Engineer", "Eng"),
    ]
    for before, after in replacements:
        value = value.replace(before, after)
    return value


def generate_note(company: str, role: str, recruiter_name: str) -> str:
    greeting = f"Hi {first_name(recruiter_name)}," if recruiter_name else "Hi,"
    templates = [
        (
            f"{greeting} I'm Liam Van, and I have experience at Oracle Cloud Infrastructure "
            f"working on the GCP integration team. I'd love to connect and learn more about "
            f"{company}'s {role} role, and I'm also open to other software roles that may be a fit. Thanks, Liam"
        ),
        (
            f"{greeting} I'm Liam Van, with experience at OCI on the GCP integration team. "
            f"I'd love to connect and learn about {company}'s {compact_role(role)} role, "
            "and I'm open to other software roles that may fit. Thanks, Liam"
        ),
        (
            f"{greeting} I'm Liam Van, with experience at OCI on the GCP integration team. "
            f"I'd love to learn about {company}'s {compact_role(role)} role or other software roles that may fit. Thanks, Liam"
        ),
    ]
    for note in templates:
        if len(note) <= MAX_NOTE_LENGTH:
            return note
    return templates[-1][: MAX_NOTE_LENGTH - 1].rstrip() + "…"


def merge_row(
    app: dict[str, Any],
    existing: dict[str, str] | None,
    batch: str,
    config: dict[str, str | Path],
) -> dict[str, str]:
    existing = existing or {}
    name_column = str(config["name_column"])
    profile_column = str(config["profile_column"])
    position_column = str(config["position_column"])
    contact_name = existing.get(name_column, "")
    contact_profile = existing.get(profile_column, "")
    contact_position = existing.get(position_column, "")
    route = existing.get("Route", "") or "try-free-inmail-then-connect-note"
    approval = existing.get("Approval", "") or ("Needs approval" if contact_name and contact_profile else str(config["missing_approval"]))
    outcome = existing.get("Outcome", "") or "Not reached out"
    note = existing.get("Connection Note", "")
    if not note or note == "TBD after recruiter is selected":
        note = generate_note(str(app["company"]), str(app["role"]), contact_name) if contact_name else "TBD after contact is selected"
    return {
        "Batch": existing.get("Batch", "") or batch,
        "Company": str(app["company"]),
        "Role": str(app["role"]),
        "Posting Key": str(app["postingKey"]),
        "Fit Score": str(app.get("fitScore", "")),
        "Status": str(app.get("status", "")),
        name_column: contact_name,
        profile_column: contact_profile,
        position_column: contact_position,
        "Route": route,
        "Connection Note": note,
        "Approval": approval,
        "Outcome": outcome,
        "Last Checked": existing.get("Last Checked", ""),
        "Notes": existing.get("Notes", ""),
    }


def sort_key(row: dict[str, str], config: dict[str, str | Path]) -> tuple[int, int, str, str]:
    fit = int(row["Fit Score"]) if row.get("Fit Score", "").isdigit() else 0
    ready = 1 if row.get(str(config["name_column"])) and row.get(str(config["profile_column"])) else 0
    return (-fit, -ready, row.get("Company", "").lower(), row.get("Role", "").lower())


def render_document(rows: list[dict[str, str]], batch: str, config: dict[str, str | Path]) -> str:
    ready = sum(1 for row in rows if row.get(str(config["name_column"])) and row.get(str(config["profile_column"])))
    approved = sum(1 for row in rows if row.get("Approval", "").lower() == "approved")
    sent = sum(1 for row in rows if row.get("Outcome", "").lower() == "sent")
    return "\n\n".join(
        [
            f"# {config['title']}",
            (
                f"Generated: {date.today().isoformat()} | Batch: {batch} | "
                f"Rows: {len(rows)} | {config['ready_label']}: {ready} | Approved: {approved} | Sent: {sent}"
            ),
            f"## {config['heading']}",
            render_table(rows, columns_for(config)),
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or refresh a LinkedIn outreach batch tracker.")
    parser.add_argument("--tracker-json", type=Path, default=TRACKER_JSON)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--contact-type", choices=sorted(CONTACT_CONFIG), default="recruiter")
    parser.add_argument("--batch")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-fit", type=int, default=0)
    parser.add_argument("--ready-only", action="store_true", help="Only keep rows with a contact name and profile.")
    args = parser.parse_args()

    config = CONTACT_CONFIG[args.contact_type]
    output = args.output or Path(config["output"])
    batch = args.batch or f"{config['batch_prefix']}-{date.today().isoformat()}"

    existing = existing_rows(output, str(config["heading"]))
    apps = [app for app in load_applications(args.tracker_json) if needs_contact(app, config)]
    apps = [app for app in apps if int(app.get("fitScore") or 0) >= args.min_fit]
    apps.sort(key=lambda app: (int(app.get("fitScore") or 0), str(app.get("company", "")).lower()), reverse=True)
    if args.limit > 0:
        apps = apps[: args.limit]

    rows = [merge_row(app, existing.get(str(app["postingKey"])), batch, config) for app in apps]
    if args.ready_only:
        rows = [row for row in rows if row.get(str(config["name_column"])) and row.get(str(config["profile_column"]))]
    rows.sort(key=lambda row: sort_key(row, config))

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_document(rows, batch, config), encoding="utf-8")
    print(f"Wrote {display_path(output)} with {len(rows)} {config['row_label']} batch rows.")
    print(f"{config['ready_label']}: {sum(1 for row in rows if row.get(str(config['name_column'])) and row.get(str(config['profile_column'])))}")
    print(f"Approved: {sum(1 for row in rows if row.get('Approval', '').lower() == 'approved')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
