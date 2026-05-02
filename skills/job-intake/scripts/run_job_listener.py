#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[3]
APPLICATIONS_MD = ROOT / "application-trackers" / "applications.md"
INTAKE_MD = ROOT / "application-trackers" / "job-intake.md"
LOCK_PATH = Path("/tmp/codexskills-job-listener.lock")
RESUME_SCRIPTS = ROOT / "skills" / "resume-tailor" / "scripts"
sys.path.insert(0, str(RESUME_SCRIPTS))

from application_fit import load_profile, score_application  # noqa: E402
from update_application_tracker import parse_rows, row_from_cells, split_row  # noqa: E402


INTAKE_COLUMNS = [
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

EARLY_CAREER_TERMS = [
    "early career",
    "new grad",
    "new graduate",
    "university grad",
    "university graduate",
    "entry level",
    "junior",
    "associate",
    "software engineer i",
    "software engineer 1",
    "software engineer ii",
    "software engineer 2",
    "swe i",
    "swe ii",
    "engineer i",
    "engineer ii",
]

ROLE_TERMS = [
    "software engineer",
    "software developer",
    "backend",
    "back end",
    "full stack",
    "fullstack",
    "frontend",
    "front end",
    "platform",
    "infrastructure",
    "product engineer",
    "generalist",
    "founding engineer",
    "forward deployed",
    "applied ai",
    "ai engineer",
    "member of technical staff",
]

SKIP_TITLE_TERMS = [
    "senior",
    "staff",
    "principal",
    "manager",
    "director",
    "intern",
    "internship",
    "recruiter",
    "sales",
    "customer success",
    "solutions consultant",
    "technical support",
]

US_LOCATION_TERMS = [
    "united states",
    " usa",
    " u.s.",
    " us ",
    "remote",
    "new york",
    "nyc",
    "san francisco",
    "bay area",
    "seattle",
    "washington",
    "california",
    "texas",
    "massachusetts",
    "georgia",
    "illinois",
    "colorado",
    "virginia",
    "district of columbia",
]


def normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(clean(item) for item in value if clean(item))
    if isinstance(value, dict):
        for key in ("title", "name", "value", "label", "text"):
            if clean(value.get(key)):
                return clean(value[key])
        return " ".join(clean(item) for item in value.values() if clean(item))
    return str(value).strip()


def contains_any(text: str, terms: list[str]) -> bool:
    normalized = normalize(text)
    for term in terms:
        cleaned = normalize(term)
        if not cleaned:
            continue
        pattern = re.escape(cleaned).replace(r"\ ", r"[\s,/\-]+")
        if re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", normalized):
            return True
    return False


def escape_cell(value: str) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def split_markdown_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip().replace("\\|", "|") for cell in line.split("|")]


def markdown_row(row: dict[str, str]) -> str:
    return "| " + " | ".join(escape_cell(row.get(column, "")) for column in INTAKE_COLUMNS) + " |"


def first_value(record: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        if key in record and clean(record[key]):
            return clean(record[key])
    lowered = {normalize(key).replace(" ", "_"): value for key, value in record.items()}
    for key in keys:
        normalized = normalize(key).replace(" ", "_")
        if normalized in lowered and clean(lowered[normalized]):
            return clean(lowered[normalized])
    return ""


def flatten_jobs(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list):
        jobs: list[dict[str, Any]] = []
        for item in value:
            jobs.extend(flatten_jobs(item))
        return jobs
    if not isinstance(value, dict):
        return []
    keys = {normalize(key).replace(" ", "_") for key in value}
    if keys & {"title", "job_title", "role", "name", "absolute_url", "url", "job_url", "location", "company", "company_name"}:
        return [value]
    jobs = []
    for key in ("jobs", "results", "data", "items", "postings", "elements"):
        if key in value:
            jobs.extend(flatten_jobs(value[key]))
    return jobs


def load_jobs(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix.lower() in {".csv", ".tsv"}:
        dialect = "excel-tab" if path.suffix.lower() == ".tsv" else "excel"
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle, dialect=dialect)]
    try:
        return flatten_jobs(json.loads(text))
    except json.JSONDecodeError:
        jobs = []
        for line in text.splitlines():
            if line.strip():
                jobs.extend(flatten_jobs(json.loads(line)))
        return jobs


def posting_key(url: str, title: str) -> str:
    parsed = urlparse(url or "")
    query = parse_qs(parsed.query)
    for field in ("currentJobId", "jobId", "job_id", "gh_jid", "jk"):
        if query.get(field):
            return query[field][0].strip()
    for part in reversed([part for part in parsed.path.split("/") if part]):
        if re.fullmatch(r"\d{5,}", part):
            return part
    for part in reversed([part for part in parsed.path.split("/") if part]):
        if part.lower() not in {"jobs", "job", "view", "application", "apply"}:
            return part
    fallback = re.sub(r"[^a-zA-Z0-9]+", "_", title or "").strip("_")
    return fallback or normalize(url)


def infer_company(url: str) -> str:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower()
    path = [part for part in parsed.path.split("/") if part]
    if ("greenhouse.io" in host or "job-boards.greenhouse.io" in host) and path:
        return path[0].replace("-", " ").replace("_", " ").title()
    return ""


def canonical_job(record: dict[str, Any], source: str) -> dict[str, str]:
    title = first_value(record, ["title", "job_title", "role", "name", "jobTitle"])
    company = first_value(record, ["company", "company_name", "organization", "employer", "department"])
    location = first_value(record, ["location", "locations", "office", "offices", "city"])
    url = first_value(record, ["url", "absolute_url", "job_url", "apply_url", "external_url", "href", "link"])
    posted = first_value(record, ["posted_at", "date_posted", "posted", "listedAt", "created_at"])
    description = first_value(record, ["description", "content", "body", "summary", "snippet"])
    if not company:
        company = infer_company(url)
    key = first_value(record, ["posting_key", "postingKey", "job_id", "jobId", "id"]) or posting_key(url, title)
    return {
        "source": source,
        "company": company,
        "role": title,
        "location": location,
        "url": url,
        "postedAge": posted,
        "description": description,
        "postingKey": key,
    }


def link_url(markdown_link: str) -> str:
    match = re.search(r"\(([^)]+)\)", markdown_link or "")
    return match.group(1) if match else markdown_link


def existing_application_keys() -> set[str]:
    if not APPLICATIONS_MD.exists():
        return set()
    _, rows = parse_rows(APPLICATIONS_MD.read_text(encoding="utf-8").splitlines())
    keys = set()
    for row_line in rows:
        row = row_from_cells(split_row(row_line))
        if not row:
            continue
        company = normalize(row.get("Company", ""))
        role = normalize(row.get("Role", ""))
        key = normalize(row.get("Posting Key", ""))
        url = normalize(link_url(row.get("Job Link", "")))
        if key:
            keys.add(f"key:{key}")
        if url:
            keys.add(f"url:{url}")
        if company and role:
            keys.add(f"title:{company}:{role}")
    return keys


def parse_intake_rows() -> list[dict[str, str]]:
    if not INTAKE_MD.exists():
        return []
    lines = INTAKE_MD.read_text(encoding="utf-8").splitlines()
    rows = []
    header_seen = False
    for index, line in enumerate(lines):
        if line.startswith("| Source |") and "Posting Key" in line:
            header_seen = True
            continue
        if not header_seen or index == 0 or not line.startswith("| "):
            continue
        if set(line.replace("|", "").replace("-", "").strip()) == set():
            continue
        cells = split_markdown_row(line)
        if len(cells) < len(INTAKE_COLUMNS):
            cells += [""] * (len(INTAKE_COLUMNS) - len(cells))
        rows.append(dict(zip(INTAKE_COLUMNS, cells[: len(INTAKE_COLUMNS)])))
    return rows


def intake_keys(rows: list[dict[str, str]]) -> set[str]:
    keys = set()
    for row in rows:
        company = normalize(row.get("Company", ""))
        role = normalize(row.get("Role", ""))
        key = normalize(row.get("Posting Key", ""))
        url = normalize(row.get("Job URL", ""))
        if key:
            keys.add(f"key:{key}")
        if url:
            keys.add(f"url:{url}")
        if company and role:
            keys.add(f"title:{company}:{role}")
    return keys


def render_intake(rows: list[dict[str, str]]) -> str:
    counts = Counter(row.get("Status", "") or "New" for row in rows)
    parts = [
        "# Job Intake Tracker",
        "",
        "This file tracks fresh jobs discovered by scheduled LinkedIn and Greenhouse intake before they become tailored applications.",
        "",
        f"Jobs discovered: {len(rows)}",
        (
            f"New: {counts.get('New', 0)} | Queued: {counts.get('Queued', 0)} | "
            f"Tailored: {counts.get('Tailored', 0)} | Applied: {counts.get('Applied', 0)} | "
            f"Manual: {counts.get('Manual', 0)} | Skipped: {counts.get('Skipped', 0)} | "
            f"Duplicate: {counts.get('Duplicate', 0)} | Expired: {counts.get('Expired', 0)}"
        ),
        "",
        "| " + " | ".join(INTAKE_COLUMNS) + " |",
        "| " + " | ".join("---" for _ in INTAKE_COLUMNS) + " |",
    ]
    parts.extend(markdown_row(row) for row in rows)
    return "\n".join(parts) + "\n"


def score_job(job: dict[str, str], profile: dict) -> tuple[int, list[str], bool]:
    text = " ".join([job["role"], job["company"], job["location"], job.get("description", "")])
    title = job["role"]
    reasons = []
    penalty = 0

    if contains_any(text, ROLE_TERMS):
        reasons.append("SWE-family role")
    if contains_any(text, EARLY_CAREER_TERMS):
        reasons.append("early-career signal")
    if contains_any(title, SKIP_TITLE_TERMS):
        reasons.append("skip-title signal")
        penalty += 5

    location = normalize(job["location"])
    if "new york" in location or "nyc" in location:
        reasons.append("NYC preference")
        location_boost = 2
    elif "san francisco" in location or "bay area" in location:
        reasons.append("SF/Bay Area preference")
        location_boost = 1
    elif any(term in location for term in ("remote", "united states", "seattle", "washington, dc", "district of columbia")):
        reasons.append("preferred/remote US location")
        location_boost = 1
    elif contains_any(f" {job['location']} ", US_LOCATION_TERMS):
        reasons.append("other US location")
        location_boost = 0
    else:
        reasons.append("location needs review")
        location_boost = -1

    row = {
        "Company": job["company"],
        "Role": job["role"],
        "Location": job["location"],
        "Source": job["source"],
        "Status": "Sourced",
        "Referral": "",
    }
    score = score_application(row, profile) + location_boost - penalty
    if contains_any(text, EARLY_CAREER_TERMS):
        score += 1
    keep = bool(job["role"] and job["url"] and contains_any(text, ROLE_TERMS)) and penalty == 0 and score >= 5
    return max(1, min(10, score)), reasons, keep


def is_duplicate(job: dict[str, str], keys: set[str]) -> bool:
    company = normalize(job["company"])
    role = normalize(job["role"])
    key = normalize(job["postingKey"])
    url = normalize(job["url"])
    return (
        (key and f"key:{key}" in keys)
        or (url and f"url:{url}" in keys)
        or (company and role and f"title:{company}:{role}" in keys)
    )


def build_new_rows(jobs: list[dict[str, str]], existing_keys: set[str], discovered_at: str, profile: dict) -> tuple[list[dict[str, str]], dict[str, int]]:
    rows = []
    stats = Counter()
    seen: set[str] = set()
    for job in jobs:
        unique = normalize(job["postingKey"] or job["url"] or f"{job['company']}:{job['role']}")
        if not unique or unique in seen:
            stats["duplicate_in_capture"] += 1
            continue
        seen.add(unique)
        if is_duplicate(job, existing_keys):
            stats["duplicate_existing"] += 1
            continue
        score, reasons, keep = score_job(job, profile)
        status = "Queued" if keep and score >= 8 else ("New" if keep else "Skipped")
        rows.append(
            {
                "Source": job["source"],
                "Company": job["company"],
                "Role": job["role"],
                "Location": job["location"],
                "Posting Key": job["postingKey"],
                "Job URL": job["url"],
                "Discovered At": discovered_at,
                "Posted Age": job["postedAge"],
                "Fit Score": str(score),
                "Status": status,
                "Reason": ", ".join(reasons),
                "Tracker Posting Key": "",
            }
        )
        stats[status.lower()] += 1
    return rows, dict(stats)


def load_source_jobs(args: argparse.Namespace) -> list[dict[str, str]]:
    jobs = []
    default_dir = Path(args.capture_dir).expanduser()
    linkedin_paths = args.linkedin_input or ([str(default_dir / "linkedin_jobs.json")] if (default_dir / "linkedin_jobs.json").exists() else [])
    greenhouse_paths = args.greenhouse_input or ([str(default_dir / "greenhouse_jobs.json")] if (default_dir / "greenhouse_jobs.json").exists() else [])
    for source, paths in (("LinkedIn", linkedin_paths), ("Greenhouse", greenhouse_paths)):
        for path_text in paths:
            path = Path(path_text).expanduser()
            jobs.extend(canonical_job(record, source) for record in load_jobs(path))
    return jobs


def acquire_lock(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit(f"Job listener already running or stale lock exists: {path}")
    with os.fdopen(fd, "w") as handle:
        handle.write(f"{os.getpid()}\n{datetime.now(timezone.utc).isoformat()}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LinkedIn/Greenhouse job intake and update the intake ledger.")
    parser.add_argument("--duration-minutes", type=int, default=0, help="Keep the listener alive for this many minutes.")
    parser.add_argument("--scan-interval-minutes", type=int, default=15, help="Delay between scans during a listener window.")
    parser.add_argument("--sources", nargs="+", default=["linkedin", "greenhouse"], choices=["linkedin", "greenhouse"])
    parser.add_argument("--linkedin-input", action="append", default=[], help="Captured LinkedIn jobs as JSON/JSONL/CSV/TSV.")
    parser.add_argument("--greenhouse-input", action="append", default=[], help="Captured Greenhouse jobs as JSON/JSONL/CSV/TSV.")
    parser.add_argument("--capture-dir", default="/tmp/codexskills-job-intake", help="Default directory for linkedin_jobs.json and greenhouse_jobs.json captures.")
    parser.add_argument("--dry-run", action="store_true", help="Print the intake changes without writing job-intake.md.")
    parser.add_argument("--no-lock", action="store_true", help="Skip the /tmp listener lock.")
    args = parser.parse_args()

    if not args.no_lock:
        acquire_lock(LOCK_PATH)
    try:
        deadline = time.time() + args.duration_minutes * 60 if args.duration_minutes else time.time()
        wrote = False
        while True:
            existing_rows = parse_intake_rows()
            keys = existing_application_keys() | intake_keys(existing_rows)
            discovered_at = datetime.now(timezone.utc).isoformat()
            profile = load_profile(ROOT)
            jobs = load_source_jobs(args)
            new_rows, stats = build_new_rows(jobs, keys, discovered_at, profile)
            combined = sorted(
                existing_rows + new_rows,
                key=lambda row: (
                    int(row["Fit Score"]) if row.get("Fit Score", "").isdigit() else 0,
                    row.get("Discovered At", ""),
                    row.get("Company", "").lower(),
                ),
                reverse=True,
            )
            print(json.dumps({"captured": len(jobs), "newRows": len(new_rows), "stats": stats}, indent=2))
            if not args.dry_run and new_rows:
                INTAKE_MD.parent.mkdir(parents=True, exist_ok=True)
                INTAKE_MD.write_text(render_intake(combined), encoding="utf-8")
                wrote = True
            if args.duration_minutes <= 0 or time.time() >= deadline:
                break
            remaining = max(0, deadline - time.time())
            if remaining <= 0:
                break
            time.sleep(min(max(args.scan_interval_minutes, 1) * 60, remaining))
        if args.dry_run:
            print("Dry run: no files written.")
        elif wrote:
            print(f"Updated {INTAKE_MD.relative_to(ROOT)}")
        elif not load_source_jobs(args):
            print("No captured input files were provided. Capture LinkedIn/Greenhouse results, then rerun with --linkedin-input/--greenhouse-input.")
        else:
            print("No new intake rows.")
    finally:
        if not args.no_lock:
            try:
                LOCK_PATH.unlink()
            except FileNotFoundError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
