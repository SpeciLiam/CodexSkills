#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
APPLICATIONS_MD = ROOT / "application-trackers" / "applications.md"
OUTREACH_MD = ROOT / "application-trackers" / "outreach-prospects.md"
OUTPUT_JSON = ROOT / "application-visualizer" / "src" / "data" / "tracker-data.json"

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def split_markdown_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def extract_tables(markdown: str) -> dict[str, list[dict[str, str]]]:
    lines = markdown.splitlines()
    tables: dict[str, list[dict[str, str]]] = {}
    current_heading = "Main"
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("## "):
            current_heading = line.removeprefix("## ").strip()
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|\s*:?-{3,}:?", lines[i + 1].strip()):
            headers = split_markdown_row(line)
            rows: list[dict[str, str]] = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = split_markdown_row(lines[i])
                if len(cells) < len(headers):
                    cells += [""] * (len(headers) - len(cells))
                rows.append(dict(zip(headers, cells[: len(headers)])))
                i += 1
            tables[current_heading] = rows
            continue
        i += 1
    return tables


def clean_text(value: str) -> str:
    return LINK_RE.sub(lambda m: m.group(1), value or "").replace("<br>", " ").strip()


def first_link(value: str) -> str:
    match = LINK_RE.search(value or "")
    return match.group(2) if match else ""


def all_links(value: str) -> list[dict[str, str]]:
    return [{"label": m.group(1), "url": m.group(2)} for m in LINK_RE.finditer(value or "")]


def truthy(value: str) -> bool:
    return clean_text(value).lower() in {"yes", "y", "true", "1", "sent"}


def parse_int(value: str, default: int = 0) -> int:
    try:
        return int(clean_text(value))
    except ValueError:
        return default


def normalize_application(row: dict[str, str]) -> dict[str, Any]:
    notes = clean_text(row.get("Notes", ""))
    return {
        "company": clean_text(row.get("Company", "")),
        "role": clean_text(row.get("Role", "")),
        "applied": truthy(row.get("Applied", "")),
        "status": clean_text(row.get("Status", "")) or "Unknown",
        "fitScore": parse_int(row.get("Fit Score", "")),
        "reachOut": truthy(row.get("Reach Out", "")),
        "referral": clean_text(row.get("Referral", "")),
        "dateAdded": clean_text(row.get("Date Added", "")),
        "location": clean_text(row.get("Location", "")) or "Unknown",
        "source": clean_text(row.get("Source", "")) or "Unknown",
        "jobLink": first_link(row.get("Job Link", "")),
        "postingKey": clean_text(row.get("Posting Key", "")),
        "resumeFolder": first_link(row.get("Resume Folder", "")),
        "resumePdf": first_link(row.get("Resume PDF", "")) or first_link(row.get("Company Resume", "")),
        "recruiterContact": clean_text(row.get("Recruiter Contact", "")),
        "recruiterProfile": first_link(row.get("Recruiter Profile", "")),
        "engineerContact": clean_text(row.get("Engineer Contact", "")),
        "engineerProfile": first_link(row.get("Engineer Profile", "")),
        "notes": notes,
        "noteLinks": all_links(row.get("Notes", "")),
        "activityDates": DATE_RE.findall(row.get("Notes", "")),
    }


def normalize_prospect(row: dict[str, str]) -> dict[str, Any]:
    return {
        "company": clean_text(row.get("Company", "")),
        "postingKey": clean_text(row.get("Posting Key", "")),
        "priority": parse_int(row.get("Priority", "")),
        "targetType": clean_text(row.get("Target Type", "")) or "unknown",
        "name": clean_text(row.get("Name", "")),
        "title": clean_text(row.get("Title", "")),
        "linkedin": first_link(row.get("LinkedIn", "")) or clean_text(row.get("LinkedIn", "")),
        "apolloEmail": clean_text(row.get("Apollo Email", "")),
        "emailStatus": clean_text(row.get("Email Status", "")) or "Unknown",
        "notes": clean_text(row.get("Notes", "")),
    }


def normalize_queue(row: dict[str, str]) -> dict[str, Any]:
    return {
        "company": clean_text(row.get("Company", "")),
        "role": clean_text(row.get("Role", "")),
        "postingKey": clean_text(row.get("Posting Key", "")),
        "fitScore": parse_int(row.get("Fit Score", "")),
        "status": clean_text(row.get("Status", "")) or "Unknown",
        "reachOut": truthy(row.get("Reach Out", "")),
        "jobLink": first_link(row.get("Job Link", "")),
        "prospectCount": parse_int(row.get("Prospect Count", "")),
        "readyEmails": parse_int(row.get("Ready Emails", "")),
        "lastUpdated": clean_text(row.get("Last Updated", "")),
        "notes": clean_text(row.get("Notes", "")),
    }


def location_bucket(location: str) -> str:
    text = location.lower()
    if "remote" in text:
        return "Remote"
    if "new york" in text or "ny" in text:
        return "New York"
    if "san francisco" in text or "bay area" in text or "palo alto" in text:
        return "Bay Area"
    if "seattle" in text:
        return "Seattle"
    if "atlanta" in text or "georgia" in text:
        return "Georgia"
    if "unknown" in text or not text.strip():
        return "Unknown"
    return "Other"


def role_family(role: str) -> str:
    text = role.lower()
    if "backend" in text or "back end" in text:
        return "Backend"
    if "frontend" in text or "front end" in text:
        return "Frontend"
    if "full" in text:
        return "Full Stack"
    if "ai" in text or "ml" in text or "machine learning" in text:
        return "AI/ML"
    if "data" in text:
        return "Data"
    if "infrastructure" in text or "platform" in text:
        return "Infra/Platform"
    if "forward deployed" in text or "deployed" in text:
        return "Forward Deployed"
    return "General SWE"


def build_stats(applications: list[dict[str, Any]], prospects: list[dict[str, Any]], queues: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(applications)
    applied = sum(1 for app in applications if app["applied"])
    rejected = sum(1 for app in applications if app["status"].lower() == "rejected")
    active = total - rejected - sum(1 for app in applications if app["status"].lower() == "archived")
    interviewing = sum(1 for app in applications if app["status"].lower() == "interviewing")
    assessments = sum(1 for app in applications if "assessment" in app["status"].lower())
    high_fit = sum(1 for app in applications if app["fitScore"] >= 8)
    reach_out = sum(1 for app in applications if app["reachOut"])
    recruiter_rows = sum(1 for app in applications if app["recruiterContact"] or app["recruiterProfile"])
    ready_emails = sum(1 for p in prospects if p["emailStatus"].lower() == "ready")

    status_counts = Counter(app["status"] for app in applications)
    source_counts = Counter(app["source"] for app in applications)
    location_counts = Counter(location_bucket(app["location"]) for app in applications)
    role_counts = Counter(role_family(app["role"]) for app in applications)
    fit_counts = Counter(str(app["fitScore"]) for app in applications if app["fitScore"])
    target_counts = Counter(p["targetType"] for p in prospects)
    email_counts = Counter(p["emailStatus"] for p in prospects)

    by_date: dict[str, dict[str, int]] = defaultdict(lambda: {"added": 0, "applied": 0, "rejected": 0, "interviewing": 0})
    for app in applications:
        date = app["dateAdded"] or "Unknown"
        by_date[date]["added"] += 1
        if app["applied"]:
            by_date[date]["applied"] += 1
        if app["status"].lower() == "rejected":
            by_date[date]["rejected"] += 1
        if app["status"].lower() == "interviewing":
            by_date[date]["interviewing"] += 1

    cumulative = 0
    timeline = []
    for date in sorted(d for d in by_date if d != "Unknown"):
        cumulative += by_date[date]["added"]
        timeline.append({"date": date, "cumulative": cumulative, **by_date[date]})

    company_scores = defaultdict(list)
    for app in applications:
        company_scores[app["company"]].append(app["fitScore"])
    top_companies = sorted(
        (
            {"company": company, "roles": len(scores), "avgFit": round(sum(scores) / len(scores), 2), "bestFit": max(scores)}
            for company, scores in company_scores.items()
            if scores
        ),
        key=lambda item: (item["bestFit"], item["roles"], item["avgFit"]),
        reverse=True,
    )[:24]

    outreach_gaps = sorted(
        (
            {
                "company": q["company"],
                "role": q["role"],
                "fitScore": q["fitScore"],
                "status": q["status"],
                "prospectCount": q["prospectCount"],
                "readyEmails": q["readyEmails"],
                "jobLink": q["jobLink"],
            }
            for q in queues
            if q["prospectCount"] < 3 or q["readyEmails"] == 0
        ),
        key=lambda item: (item["fitScore"], -item["prospectCount"], item["readyEmails"]),
        reverse=True,
    )[:36]

    return {
        "kpis": {
            "total": total,
            "applied": applied,
            "unapplied": total - applied,
            "active": active,
            "rejected": rejected,
            "interviewing": interviewing,
            "assessments": assessments,
            "highFit": high_fit,
            "reachOut": reach_out,
            "recruiterRows": recruiter_rows,
            "prospects": len(prospects),
            "readyEmails": ready_emails,
            "applyRate": round(applied / total * 100, 1) if total else 0,
            "rejectionRate": round(rejected / applied * 100, 1) if applied else 0,
        },
        "statusCounts": [{"name": k, "value": v} for k, v in status_counts.most_common()],
        "sourceCounts": [{"name": k, "value": v} for k, v in source_counts.most_common()],
        "locationCounts": [{"name": k, "value": v} for k, v in location_counts.most_common()],
        "roleCounts": [{"name": k, "value": v} for k, v in role_counts.most_common()],
        "fitCounts": [{"score": k, "count": v} for k, v in sorted(fit_counts.items(), key=lambda kv: int(kv[0]))],
        "targetCounts": [{"name": k, "value": v} for k, v in target_counts.most_common()],
        "emailCounts": [{"name": k, "value": v} for k, v in email_counts.most_common()],
        "timeline": timeline,
        "topCompanies": top_companies,
        "outreachGaps": outreach_gaps,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh application visualizer JSON data.")
    parser.add_argument("--applications", type=Path, default=APPLICATIONS_MD)
    parser.add_argument("--outreach", type=Path, default=OUTREACH_MD)
    parser.add_argument("--output", type=Path, default=OUTPUT_JSON)
    args = parser.parse_args()

    if not args.applications.exists():
        if args.output.exists():
            print(
                f"Source tracker {args.applications} is missing; "
                f"leaving existing {args.output.relative_to(ROOT)} in place."
            )
            return
        raise FileNotFoundError(
            f"Source tracker {args.applications} is missing and no generated JSON exists at {args.output}."
        )

    app_tables = extract_tables(args.applications.read_text(encoding="utf-8"))
    outreach_tables = extract_tables(args.outreach.read_text(encoding="utf-8")) if args.outreach.exists() else {}

    applications = [normalize_application(row) for row in app_tables.get("Main", [])]
    queues = [normalize_queue(row) for row in outreach_tables.get("Company Queue", [])]
    prospects = [normalize_prospect(row) for row in outreach_tables.get("Prospect Details", [])]

    applications = [app for app in applications if app["company"] and app["role"]]
    queues = [q for q in queues if q["company"]]
    prospects = [p for p in prospects if p["company"] and p["name"]]

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceFiles": {
            "applications": str(args.applications.relative_to(ROOT)),
            "outreach": str(args.outreach.relative_to(ROOT)) if args.outreach.exists() else "",
        },
        "stats": build_stats(applications, prospects, queues),
        "applications": applications,
        "outreachQueue": queues,
        "prospects": prospects,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {args.output.relative_to(ROOT)} with {len(applications)} applications, {len(queues)} outreach rows, {len(prospects)} prospects.")


if __name__ == "__main__":
    main()
