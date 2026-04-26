#!/usr/bin/env python3

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_PROFILE = {
    "reach_out_threshold": 9,
    "base_score": 3,
    "weights": {
        "preferred_location": 2,
        "acceptable_location": 1,
        "strong_role": 2,
        "level_fit": 1,
        "worthwhile_company": 3,
        "avoid_company": -4,
        "preferred_source": 1,
        "avoid_status": -4,
        "referral": 1,
    },
    "preferred_location_terms": [
        "new york",
        "new york city",
        "nyc",
        "brooklyn",
        "manhattan",
    ],
    "acceptable_location_terms": [
        "hybrid",
        "remote",
        "united states",
    ],
    "strong_role_terms": [
        "software engineer",
        "backend",
        "full stack",
        "fullstack",
        "platform",
        "product engineer",
        "generalist",
    ],
    "level_fit_terms": [
        "early career",
        "new grad",
        "junior",
        "associate",
        "engineer i",
        "software engineer i",
    ],
    "worthwhile_company_terms": [
        "plaid",
        "spotify",
        "notion",
        "the new york times",
        "disney",
        "anrok",
        "warp",
        "morgan stanley",
        "navan",
        "scale ai",
        "linkedin",
        "lyft",
        "tinder",
        "intuit",
        "warner bros",
        "microsoft",
        "cadence",
    ],
    "avoid_company_terms": [
        "recruiters",
        "recruiter",
        "talent acquisition",
        "advisors",
        "staffing",
    ],
    "preferred_sources": [
        "ashby",
        "greenhouse",
        "lever",
        "company site",
        "workday",
    ],
    "avoid_statuses": [
        "rejected",
        "archived",
    ],
}


def normalize(value: str) -> str:
    return " ".join(value.strip().lower().split())


def profile_path(repo_root: Path) -> Path:
    return repo_root / "application-trackers" / "scoring-profile.json"


def load_profile(repo_root: Path) -> dict:
    path = profile_path(repo_root)
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_PROFILE, indent=2) + "\n")
        return dict(DEFAULT_PROFILE)

    loaded = json.loads(path.read_text())
    profile = dict(DEFAULT_PROFILE)
    profile.update(loaded)
    return profile


def contains_any(text: str, terms: list[str]) -> bool:
    normalized_text = normalize(text)
    return any(normalize(term) in normalized_text for term in terms if term.strip())


def score_application(row: dict[str, str], profile: dict) -> int:
    score = int(profile.get("base_score", 5))
    weights = profile.get("weights", {})
    company = row.get("Company", "")
    role = row.get("Role", "")
    location = row.get("Location", "")
    source = row.get("Source", "")
    status = row.get("Status", "")
    referral = row.get("Referral", "")

    if contains_any(location, profile.get("preferred_location_terms", [])):
        score += int(weights.get("preferred_location", 2))
    elif contains_any(location, profile.get("acceptable_location_terms", [])):
        score += int(weights.get("acceptable_location", 1))

    if contains_any(role, profile.get("strong_role_terms", [])):
        score += int(weights.get("strong_role", 1))

    if contains_any(role, profile.get("level_fit_terms", [])):
        score += int(weights.get("level_fit", 1))

    if contains_any(company, profile.get("worthwhile_company_terms", [])):
        score += int(weights.get("worthwhile_company", 1))

    if contains_any(company, profile.get("avoid_company_terms", [])):
        score += int(weights.get("avoid_company", -3))

    if contains_any(source, profile.get("preferred_sources", [])):
        score += int(weights.get("preferred_source", 1))

    if contains_any(status, profile.get("avoid_statuses", [])):
        score += int(weights.get("avoid_status", -4))

    if normalize(referral) in {"yes", "true"} or referral.strip():
        score += int(weights.get("referral", 1))

    return max(1, min(10, score))


def should_reach_out(score: int, profile: dict) -> bool:
    return score >= int(profile.get("reach_out_threshold", 8))
