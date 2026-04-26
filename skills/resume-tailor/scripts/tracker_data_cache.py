#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from update_application_tracker import DEFAULT_COLUMNS


def tracker_data_path(repo_root: Path) -> Path:
    return repo_root / "application-visualizer" / "src" / "data" / "tracker-data.json"


def markdown_link(label: str, url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    return f"[{label}]({url})"


def application_to_tracker_row(application: dict[str, Any]) -> dict[str, str]:
    resume_pdf = str(application.get("resumePdf", "") or "")
    resume_folder = str(application.get("resumeFolder", "") or "")
    job_link = str(application.get("jobLink", "") or "")
    recruiter_profile = str(application.get("recruiterProfile", "") or "")
    company = str(application.get("company", "") or "")
    role = str(application.get("role", "") or "")

    row = {
        "Company": company,
        "Role": role,
        "Applied": "Yes" if application.get("applied") else "",
        "Status": str(application.get("status", "") or ""),
        "Fit Score": str(application.get("fitScore", "") or ""),
        "Reach Out": "Yes" if application.get("reachOut") else "",
        "Company Resume": markdown_link(f"{company} - {role}", resume_pdf),
        "Referral": str(application.get("referral", "") or ""),
        "Date Added": str(application.get("dateAdded", "") or ""),
        "Location": str(application.get("location", "") or ""),
        "Source": str(application.get("source", "") or ""),
        "Job Link": markdown_link("Posting", job_link),
        "Posting Key": str(application.get("postingKey", "") or ""),
        "Resume Folder": markdown_link("Folder", resume_folder),
        "Resume PDF": markdown_link("PDF", resume_pdf),
        "Recruiter Contact": str(application.get("recruiterContact", "") or ""),
        "Recruiter Profile": markdown_link("Profile", recruiter_profile),
        "Engineer Contact": str(application.get("engineerContact", "") or ""),
        "Engineer Profile": markdown_link("Profile", str(application.get("engineerProfile", "") or "")),
        "Notes": str(application.get("notes", "") or ""),
    }
    return {column: row.get(column, "") for column in DEFAULT_COLUMNS}


def load_cached_application_rows(repo_root: Path) -> list[dict[str, str]]:
    path = tracker_data_path(repo_root)
    if not path.exists():
        return []

    payload = json.loads(path.read_text(encoding="utf-8"))
    applications = payload.get("applications", [])
    if not isinstance(applications, list):
        return []

    rows = []
    for application in applications:
        if isinstance(application, dict):
            row = application_to_tracker_row(application)
            if row["Company"] and row["Role"]:
                rows.append(row)
    return rows
