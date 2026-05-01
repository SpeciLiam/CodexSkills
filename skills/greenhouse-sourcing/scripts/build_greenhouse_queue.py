#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


REPO_ROOT = Path(__file__).resolve().parents[3]
RESUME_SCRIPTS = REPO_ROOT / "skills" / "resume-tailor" / "scripts"
sys.path.insert(0, str(RESUME_SCRIPTS))

from application_fit import load_profile, score_application  # noqa: E402
from update_application_tracker import parse_rows, row_from_cells, split_row  # noqa: E402


STRONG_ROLE_TERMS = [
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
    "deployed engineer",
    "member of technical staff",
    "applied ai",
    "ai engineer",
]

LEVEL_FIT_TERMS = [
    "new grad",
    "university grad",
    "early career",
    "entry level",
    "junior",
    "associate",
    "engineer i",
    "engineer 1",
    "engineer ii",
    "engineer 2",
    "swe i",
    "swe ii",
]

STRETCH_TERMS = [
    "all levels",
    "2+ years",
    "3+ years",
    "4+ years",
    "startup",
    "founding",
]

DEFAULT_ALLOWED_LOCATION_TERMS = [
    "remote",
    "washington, dc",
    "washington dc",
    "district of columbia",
    "new york",
    "new york city",
    "nyc",
    "san francisco",
    "bay area",
    "palo alto",
    "menlo park",
    "mountain view",
    "sunnyvale",
    "san mateo",
    "redwood city",
    "san jose",
    "oakland",
    "berkeley",
    "seattle",
]

SKIP_TERMS = [
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


def normalize(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(clean(item) for item in value if clean(item))
    if isinstance(value, dict):
        for key in ("name", "title", "value", "label"):
            if key in value:
                return clean(value[key])
        return " ".join(clean(item) for item in value.values() if clean(item))
    return str(value).strip()


def first_value(record: dict, keys: list[str]) -> str:
    for key in keys:
        if key in record and clean(record[key]):
            return clean(record[key])
    lowered = {normalize(key).replace(" ", "_"): value for key, value in record.items()}
    for key in keys:
        normalized = normalize(key).replace(" ", "_")
        if normalized in lowered and clean(lowered[normalized]):
            return clean(lowered[normalized])
    return ""


def flatten_jobs(value: object) -> list[dict]:
    if isinstance(value, list):
        jobs: list[dict] = []
        for item in value:
            jobs.extend(flatten_jobs(item))
        return jobs
    if not isinstance(value, dict):
        return []

    if looks_like_job(value):
        return [value]

    jobs = []
    for key in ("jobs", "results", "data", "items", "postings"):
        if key in value:
            jobs.extend(flatten_jobs(value[key]))
    return jobs


def looks_like_job(record: dict) -> bool:
    keys = {normalize(key).replace(" ", "_") for key in record}
    return bool(
        keys
        & {
            "title",
            "job_title",
            "role",
            "name",
            "absolute_url",
            "url",
            "job_url",
            "location",
            "company",
            "company_name",
        }
    )


def load_input(path: Path) -> list[dict]:
    text = path.read_text().strip()
    if not text:
        return []

    if path.suffix.lower() in {".csv", ".tsv"}:
        dialect = "excel-tab" if path.suffix.lower() == ".tsv" else "excel"
        with path.open(newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle, dialect=dialect)]

    try:
        parsed = json.loads(text)
        return flatten_jobs(parsed)
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                rows.extend(flatten_jobs(json.loads(line)))
        return rows


def posting_key(url: str, title: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for field in ("gh_jid", "job_id", "jobId", "currentJobId"):
        if query.get(field):
            return query[field][0].strip()

    path_parts = [part for part in parsed.path.split("/") if part]
    for part in reversed(path_parts):
        if re.fullmatch(r"\d{5,}", part):
            return part
    for part in reversed(path_parts):
        if part.lower() not in {"application", "apply", "jobs", "job"}:
            return part

    fallback = re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_")
    return fallback or normalize(url)


def canonical_job(record: dict) -> dict[str, str]:
    title = first_value(record, ["title", "job_title", "role", "name"])
    company = first_value(record, ["company", "company_name", "organization", "department"])
    location = first_value(record, ["location", "locations", "office", "offices", "city"])
    url = first_value(record, ["url", "absolute_url", "job_url", "apply_url", "external_url", "href"])
    description = first_value(record, ["description", "content", "body", "summary"])
    posted = first_value(record, ["posted_at", "date_posted", "updated_at", "created_at"])

    if not company:
        company = infer_company_from_url(url)

    return {
        "company": company,
        "title": title,
        "location": location,
        "url": url,
        "description": description,
        "posted": posted,
        "posting_key": posting_key(url, title) if url or title else "",
    }


def infer_company_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = [part for part in parsed.path.split("/") if part]
    if "job-boards.greenhouse.io" in host and path:
        return path[0].replace("-", " ").replace("_", " ").title()
    if "boards.greenhouse.io" in host and path:
        return path[0].replace("-", " ").replace("_", " ").title()
    return ""


def tracker_rows(repo_root: Path) -> list[dict[str, str]]:
    tracker = repo_root / "application-trackers" / "applications.md"
    if not tracker.exists():
        return []
    _, rows = parse_rows(tracker.read_text().splitlines())
    parsed = []
    for row_line in rows:
        row = row_from_cells(split_row(row_line))
        if row is not None:
            parsed.append(row)
    return parsed


def link_url(markdown_link: str) -> str:
    match = re.search(r"\(([^)]+)\)", markdown_link or "")
    return match.group(1) if match else markdown_link


def existing_keys(rows: list[dict[str, str]]) -> set[str]:
    keys = set()
    for row in rows:
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


def is_existing(job: dict[str, str], keys: set[str]) -> bool:
    company = normalize(job["company"])
    title = normalize(job["title"])
    url = normalize(job["url"])
    key = normalize(job["posting_key"])
    return (
        (key and f"key:{key}" in keys)
        or (url and f"url:{url}" in keys)
        or (company and title and f"title:{company}:{title}" in keys)
    )


def contains_any(text: str, terms: list[str]) -> bool:
    normalized = normalize(text)
    for term in terms:
        cleaned = normalize(term)
        pattern = re.escape(cleaned).replace(r"\ ", r"\s+")
        if re.search(rf"(?<![a-z0-9]){pattern}(?![a-z0-9])", normalized):
            return True
    return False


def allowed_location(job: dict[str, str], allowed_terms: list[str]) -> bool:
    if not allowed_terms:
        return True
    location_text = " ".join([job.get("location", ""), job.get("description", "")])
    return contains_any(location_text, allowed_terms)


def years_required(text: str) -> int | None:
    matches = re.findall(r"(\d+)\s*\+?\s*(?:years|yrs)", normalize(text))
    if not matches:
        return None
    return min(int(match) for match in matches)


def evaluate(job: dict[str, str], include_stretch: bool, profile: dict) -> dict[str, object]:
    text = " ".join([job["title"], job["company"], job["location"], job["description"]])
    title_text = normalize(job["title"])
    reasons: list[str] = []
    penalties: list[str] = []

    if contains_any(text, STRONG_ROLE_TERMS):
        reasons.append("SWE-family role")
    if contains_any(text, LEVEL_FIT_TERMS):
        reasons.append("level fit")
    if contains_any(text, STRETCH_TERMS):
        reasons.append("plausible stretch")

    if contains_any(title_text, SKIP_TERMS):
        penalties.append("skip-title")
    elif contains_any(text, ["senior software engineer", "staff software engineer", "principal software engineer"]):
        penalties.append("senior-only signal")

    years = years_required(text)
    if years is not None:
        if years <= 3:
            reasons.append(f"{years}+ years acceptable")
        elif include_stretch and years <= 4:
            reasons.append(f"{years}+ years stretch")
        else:
            penalties.append(f"{years}+ years required")

    row = {
        "Company": job["company"],
        "Role": job["title"],
        "Location": job["location"],
        "Source": "Greenhouse",
        "Status": "Sourced",
        "Referral": "",
    }
    score = score_application(row, profile)
    score += 1 if reasons else 0
    score -= 3 if penalties else 0
    score = max(1, min(10, score))

    keep = bool(reasons) and not penalties
    if include_stretch and reasons and not any("skip-title" == penalty for penalty in penalties):
        keep = True

    return {
        "score": score,
        "keep": keep,
        "reasons": reasons,
        "penalties": penalties,
    }


def render_markdown(items: list[dict[str, object]]) -> str:
    lines = [
        "| Score | Company | Role | Location | URL | Reasons |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in items:
        job = item["job"]
        assert isinstance(job, dict)
        labels = list(item.get("reasons", [])) + list(item.get("penalties", []))
        reasons = ", ".join(labels)
        lines.append(
            "| {score} | {company} | {title} | {location} | {url} | {reasons} |".format(
                score=item["score"],
                company=escape_md(str(job.get("company", ""))),
                title=escape_md(str(job.get("title", ""))),
                location=escape_md(str(job.get("location", ""))),
                url=str(job.get("url", "")),
                reasons=escape_md(reasons),
            )
        )
    return "\n".join(lines)


def escape_md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a ranked Greenhouse sourcing queue.")
    parser.add_argument("--input", required=True, help="Greenhouse export as JSON, JSONL, CSV, or TSV")
    parser.add_argument("--limit", type=int, default=50, help="Maximum rows to print")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--include-stretch", action="store_true", help="Include plausible all-levels and 4-year stretch roles")
    parser.add_argument("--show-skipped", action="store_true", help="Include skipped roles with penalties")
    parser.add_argument(
        "--allowed-location",
        action="append",
        default=[],
        help="Allowed location term. Repeat to override the default DC/Bay Area/Seattle/remote/NYC filter.",
    )
    parser.add_argument(
        "--no-location-filter",
        action="store_true",
        help="Do not filter by location.",
    )
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repository root")
    args = parser.parse_args()

    repo_root = Path(args.root).expanduser().resolve()
    profile = load_profile(repo_root)
    rows = tracker_rows(repo_root)
    keys = existing_keys(rows)

    jobs = [canonical_job(record) for record in load_input(Path(args.input).expanduser())]
    allowed_terms = [] if args.no_location_filter else (args.allowed_location or DEFAULT_ALLOWED_LOCATION_TERMS)
    seen: set[str] = set()
    queue = []

    for job in jobs:
        if not job["title"] and not job["url"]:
            continue
        unique = job["posting_key"] or f"{normalize(job['company'])}:{normalize(job['title'])}:{normalize(job['url'])}"
        if unique in seen:
            continue
        seen.add(unique)
        if is_existing(job, keys):
            continue

        evaluation = evaluate(job, args.include_stretch, profile)
        if not allowed_location(job, allowed_terms):
            evaluation["keep"] = False
            evaluation["penalties"].append("outside allowed locations")
        if evaluation["keep"] or args.show_skipped:
            queue.append({"job": job, **evaluation})

    queue.sort(
        key=lambda item: (
            int(item["score"]),
            bool(item.get("keep")),
            normalize(item["job"].get("company", "")),
        ),
        reverse=True,
    )
    queue = queue[: args.limit]

    if args.format == "json":
        print(json.dumps(queue, indent=2))
    else:
        print(render_markdown(queue))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
