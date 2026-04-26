#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
TRACKER_DATA = ROOT / "application-visualizer" / "src" / "data" / "tracker-data.json"

OUTREACH_RE = re.compile(r"linkedin (?:invite|inmail|message).*?\((recruiter|engineer)\)", re.IGNORECASE)

MODE_CHOICES = (
    "all",
    "status",
    "resume",
    "apply",
    "linkedin",
    "recruiter",
    "engineer",
    "prospecting",
    "prep",
    "dashboard",
    "notion",
)


def load_data(root: Path) -> dict[str, Any]:
    path = root / "application-visualizer" / "src" / "data" / "tracker-data.json"
    if not path.exists():
        raise SystemExit(
            f"Missing generated tracker cache: {path}\n"
            "Run: python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def norm(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def has_lane(app: dict[str, Any], lane: str) -> bool:
    if lane == "recruiter":
        if app.get("recruiterContact") or app.get("recruiterProfile"):
            return True
    if lane == "engineer":
        if app.get("engineerContact") or app.get("engineerProfile"):
            return True
    return lane in {match.group(1).lower() for match in OUTREACH_RE.finditer(app.get("notes", "") or "")}


def active(app: dict[str, Any]) -> bool:
    return norm(app.get("status", "")) not in {"rejected", "archived"}


def score(app: dict[str, Any]) -> tuple[int, str]:
    fit = int(app.get("fitScore") or 0)
    status = norm(app.get("status", ""))
    urgency = 0
    if status == "interviewing":
        urgency += 40
    elif "assessment" in status:
        urgency += 34
    elif app.get("reachOut"):
        urgency += 12
    if not app.get("applied"):
        urgency += 10
    return fit * 10 + urgency, str(app.get("dateAdded", ""))


def app_item(app: dict[str, Any], lane: str = "") -> dict[str, Any]:
    item = {
        "company": app.get("company", ""),
        "role": app.get("role", ""),
        "status": app.get("status", ""),
        "fitScore": app.get("fitScore", 0),
        "applied": app.get("applied", False),
        "reachOut": app.get("reachOut", False),
        "postingKey": app.get("postingKey", ""),
        "jobLink": app.get("jobLink", ""),
        "notes": app.get("notes", ""),
    }
    if lane:
        item["lane"] = lane
    return item


def build_plan(data: dict[str, Any], limit: int, mode: str = "all") -> dict[str, Any]:
    apps = [app for app in data.get("applications", []) if isinstance(app, dict)]
    queue = [row for row in data.get("outreachQueue", []) if isinstance(row, dict)]

    active_apps = [app for app in apps if active(app)]
    sorted_active = sorted(active_apps, key=score, reverse=True)

    apply_now = [
        app_item(app)
        for app in sorted_active
        if not app.get("applied") and norm(app.get("status", "")) == "resume tailored" and int(app.get("fitScore") or 0) >= 8
    ][:limit]

    recruiter_outreach = [
        app_item(app, "recruiter")
        for app in sorted_active
        if app.get("reachOut") and not has_lane(app, "recruiter")
    ][:limit]

    engineer_outreach = [
        app_item(app, "engineer")
        for app in sorted_active
        if app.get("reachOut") and not has_lane(app, "engineer")
    ][:limit]

    prep = [
        app_item(app)
        for app in sorted_active
        if norm(app.get("status", "")) == "interviewing" or "assessment" in norm(app.get("status", ""))
    ][:limit]

    prospect_gaps = sorted(
        [
            {
                "company": row.get("company", ""),
                "role": row.get("role", ""),
                "fitScore": row.get("fitScore", 0),
                "status": row.get("status", ""),
                "prospectCount": row.get("prospectCount", 0),
                "readyEmails": row.get("readyEmails", 0),
                "jobLink": row.get("jobLink", ""),
            }
            for row in queue
            if row.get("reachOut") and (int(row.get("prospectCount") or 0) < 3 or int(row.get("readyEmails") or 0) == 0)
        ],
        key=lambda row: (int(row.get("fitScore") or 0), -int(row.get("prospectCount") or 0)),
        reverse=True,
    )[:limit]

    steps_by_key = {
        "status": {
            "name": "Refresh inbox statuses",
            "command": "python3 skills/gmail-application-refresh/scripts/build_refresh_targets.py --limit 20",
            "why": "Catch confirmations, rejections, assessments, and interviews before doing more outbound.",
        },
        "resume": {
            "name": "Tailor a new resume",
            "command": "Use the resume-tailor skill with a job URL or pasted posting.",
            "why": "Create the role-specific resume, update the tracker, then let fit score decide whether outreach should follow.",
        },
        "apply": {
            "name": "Apply now",
            "count": len(apply_now),
            "items": apply_now,
        },
        "recruiter": {
            "name": "LinkedIn recruiter lane",
            "command": "python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type recruiter --limit 20",
            "count": len(recruiter_outreach),
            "items": recruiter_outreach,
        },
        "engineer": {
            "name": "LinkedIn engineer lane",
            "command": "python3 skills/linkedin-outreach/scripts/build_outreach_targets.py --contact-type engineer --limit 20",
            "count": len(engineer_outreach),
            "items": engineer_outreach,
        },
        "prospecting": {
            "name": "Company prospecting and Apollo",
            "command": "python3 skills/company-prospecting/scripts/build_company_prospect_targets.py --limit 20",
            "count": len(prospect_gaps),
            "items": prospect_gaps,
        },
        "prep": {
            "name": "Interview and assessment prep",
            "count": len(prep),
            "items": prep,
        },
        "dashboard": {
            "name": "Refresh dashboard",
            "command": "python3 skills/application-visualizer-refresh/scripts/refresh_visualizer_data.py && cd application-visualizer && npm run build",
            "why": "Update the website after tracker or outreach changes.",
        },
        "notion": {
            "name": "Optional Notion mirror",
            "command": "python3 skills/notion-application-sync/scripts/sync_applications_to_notion.py --dry-run",
            "why": "Preview or run the slower Notion mirror separately from the normal recruiting loop.",
        },
    }

    mode_steps = {
        "all": ["status", "resume", "apply", "recruiter", "engineer", "prospecting", "prep", "dashboard"],
        "status": ["status", "prep", "dashboard"],
        "resume": ["status", "resume", "apply", "recruiter", "engineer", "dashboard"],
        "apply": ["status", "apply", "recruiter", "engineer", "dashboard"],
        "linkedin": ["status", "recruiter", "engineer", "prospecting", "dashboard"],
        "recruiter": ["status", "recruiter", "prospecting", "dashboard"],
        "engineer": ["status", "engineer", "prospecting", "dashboard"],
        "prospecting": ["status", "prospecting", "recruiter", "engineer", "dashboard"],
        "prep": ["status", "prep", "dashboard"],
        "dashboard": ["dashboard"],
        "notion": ["dashboard", "notion"],
    }

    return {
        "generatedAt": data.get("generatedAt", ""),
        "mode": mode,
        "summary": data.get("stats", {}).get("kpis", {}),
        "steps": [steps_by_key[key] for key in mode_steps[mode]],
    }


def print_text(plan: dict[str, Any]) -> None:
    summary = plan.get("summary", {})
    print("Recruiting Daily Plan")
    print("=====================")
    print(
        f"Tracked: {summary.get('total', '?')} | Active: {summary.get('active', '?')} | "
        f"Applied: {summary.get('applied', '?')} | High fit: {summary.get('highFit', '?')}"
    )
    if plan.get("generatedAt"):
        print(f"Cache generated: {plan['generatedAt']}")
    if plan.get("mode"):
        print(f"Mode: {plan['mode']}")
    print("")

    for index, step in enumerate(plan["steps"], start=1):
        print(f"{index}. {step['name']}")
        if step.get("command"):
            print(f"   Command: {step['command']}")
        if step.get("why"):
            print(f"   Why: {step['why']}")
        items = step.get("items") or []
        if items:
            print(f"   Top {len(items)}:")
            for item in items:
                lane = f" [{item['lane']}]" if item.get("lane") else ""
                print(
                    f"   -{lane} {item.get('company')} | {item.get('role')} | "
                    f"Fit {item.get('fitScore', '?')} | {item.get('status')}"
                )
        print("")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an ordered daily recruiting workflow from tracker data.")
    parser.add_argument("--root", default=None, help="Optional repo root override")
    parser.add_argument("--limit", type=int, default=5, help="Items per section")
    parser.add_argument("--mode", choices=MODE_CHOICES, default="all", help="Focused workflow to run")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve() if args.root else ROOT
    plan = build_plan(load_data(root), args.limit, args.mode)
    if args.format == "json":
        print(json.dumps(plan, indent=2))
    else:
        print_text(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
