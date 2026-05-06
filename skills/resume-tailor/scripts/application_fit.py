#!/usr/bin/env python3

from __future__ import annotations

import json
import re
from pathlib import Path


DEFAULT_PROFILE = {
    "reach_out_threshold": 8,
    "base_score": 3,
    "weights": {
        "nyc_location": 3,
        "sf_bay_location": 2,
        "remote_us_location": 1,
        "early_career": 3,
        "one_to_two_yoe": 2,
        "swe_family": 2,
        "backend_fullstack_platform": 2,
        "product_or_generalist": 1,
        "stack_match": 2,
        "worthwhile_company": 2,
        "preferred_source": 1,
        "referral": 1,
        "three_to_four_yoe": -2,
        "five_plus_yoe": -4,
        "senior_title": -3,
        "staff_principal_manager": -5,
        "non_swe_role": -4,
        "avoid_company": -3,
        "clearance_or_hard_gate": -3,
        "avoid_status": -8,
    },
    "nyc_location_terms": [
        "new york",
        "new york city",
        "nyc",
        "brooklyn",
        "manhattan",
    ],
    "sf_bay_location_terms": [
        "san francisco",
        "bay area",
        "palo alto",
        "redwood city",
        "mountain view",
        "san mateo",
        "san jose",
    ],
    "remote_us_location_terms": [
        "hybrid",
        "remote",
        "united states",
        "seattle",
        "washington, dc",
        "district of columbia",
    ],
    "swe_family_terms": [
        "software engineer",
        "software developer",
        "developer",
        "forward deployed engineer",
        "applications developer",
    ],
    "backend_fullstack_platform_terms": [
        "backend",
        "full stack",
        "fullstack",
        "platform",
        "infrastructure",
        "api",
        "cloud",
    ],
    "product_or_generalist_terms": [
        "product engineer",
        "generalist",
        "founding engineer",
    ],
    "early_career_terms": [
        "early career",
        "new grad",
        "new graduate",
        "junior",
        "associate",
        "engineer i",
        "software engineer i",
        "entry level",
        "university grad",
    ],
    "one_to_two_yoe_terms": [
        "0-1 years",
        "0-2 years",
        "1+ years",
        "1 year",
        "1-2 years",
        "2+ years",
        "2 years",
    ],
    "stack_match_terms": [
        "java",
        "python",
        "typescript",
        "javascript",
        "react",
        "node",
        "nestjs",
        "spring boot",
        "sql",
        "mysql",
        "rest api",
        "restful",
        "aws",
        "gcp",
        "oci",
        "docker",
        "ci/cd",
        "distributed systems",
        "cloud",
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
    "senior_title_terms": [
        "senior software engineer",
        "software engineer iii",
        "engineer iii",
        "lead software engineer",
    ],
    "staff_principal_manager_terms": [
        "staff",
        "principal",
        "manager",
        "director",
        "architect",
    ],
    "non_swe_role_terms": [
        "sales",
        "account executive",
        "customer success",
        "recruiter",
        "talent",
        "data analyst",
        "business analyst",
    ],
    "clearance_or_hard_gate_terms": [
        "security clearance",
        "active clearance",
        "top secret",
        "ts/sci",
        "us citizen",
        "u.s. citizen",
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

LEGACY_KEYS = {
    "preferred_location_terms": "nyc_location_terms",
    "acceptable_location_terms": "remote_us_location_terms",
    "strong_role_terms": "swe_family_terms",
    "level_fit_terms": "early_career_terms",
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
    profile = merge_profile(DEFAULT_PROFILE, loaded)
    return profile


def merge_profile(default: dict, loaded: dict) -> dict:
    profile = dict(default)
    for key, value in loaded.items():
        if isinstance(value, dict) and isinstance(profile.get(key), dict):
            merged = dict(profile[key])
            merged.update(value)
            profile[key] = merged
        else:
            profile[key] = value

    for legacy_key, replacement_key in LEGACY_KEYS.items():
        if legacy_key in loaded and replacement_key not in loaded:
            profile[replacement_key] = loaded[legacy_key]
    return profile


def contains_any(text: str, terms: list[str]) -> bool:
    normalized_text = normalize(text)
    return any(normalize(term) in normalized_text for term in terms if term.strip())


def matched_terms(text: str, terms: list[str]) -> list[str]:
    normalized_text = normalize(text)
    return [term for term in terms if term.strip() and normalize(term) in normalized_text]


def years_required(text: str) -> int | None:
    normalized_text = normalize(text)
    matches = re.finditer(r"\b(\d{1,2})\s*(?:\+|-\s*(\d{1,2}))?\s*(?:years?|yrs?)\b", normalized_text)
    years = []
    for match in matches:
        years.append(int(match.group(2) or match.group(1)))
    return max(years) if years else None


def score_application_detail(row: dict[str, str], profile: dict) -> dict:
    score = int(profile.get("base_score", 5))
    weights = profile.get("weights", {})
    company = row.get("Company", "")
    role = row.get("Role", "")
    location = row.get("Location", "")
    source = row.get("Source", "")
    status = row.get("Status", "")
    referral = row.get("Referral", "")
    description = row.get("Description", "") or row.get("Reason", "") or row.get("Notes", "")
    combined = " ".join([company, role, location, source, status, description])
    signals: list[dict[str, object]] = []

    def add_signal(key: str, label: str, evidence: list[str] | None = None) -> None:
        nonlocal score
        delta = int(weights.get(key, 0))
        if delta == 0:
            return
        score += delta
        signals.append({"key": key, "delta": delta, "label": label, "evidence": evidence or []})

    if matched := matched_terms(location, profile.get("nyc_location_terms", [])):
        add_signal("nyc_location", "NYC or nearby location", matched)
    elif matched := matched_terms(location, profile.get("sf_bay_location_terms", [])):
        add_signal("sf_bay_location", "SF/Bay Area location", matched)
    elif matched := matched_terms(location, profile.get("remote_us_location_terms", [])):
        add_signal("remote_us_location", "Remote, hybrid, or preferred US location", matched)

    if matched := matched_terms(combined, profile.get("early_career_terms", [])):
        add_signal("early_career", "Early-career/new-grad level", matched)

    required_years = years_required(combined)
    if required_years is not None:
        if required_years <= 2:
            add_signal("one_to_two_yoe", "0-2 YOE requirement", [f"{required_years} years"])
        elif required_years <= 4:
            add_signal("three_to_four_yoe", "3-4 YOE requirement", [f"{required_years} years"])
        else:
            add_signal("five_plus_yoe", "5+ YOE requirement", [f"{required_years} years"])
    elif matched := matched_terms(combined, profile.get("one_to_two_yoe_terms", [])):
        add_signal("one_to_two_yoe", "1-2 YOE signal", matched)

    if matched := matched_terms(role, profile.get("swe_family_terms", [])):
        add_signal("swe_family", "Software-engineering role family", matched)
    if matched := matched_terms(combined, profile.get("backend_fullstack_platform_terms", [])):
        add_signal("backend_fullstack_platform", "Backend/full-stack/platform alignment", matched)
    if matched := matched_terms(combined, profile.get("product_or_generalist_terms", [])):
        add_signal("product_or_generalist", "Product/generalist alignment", matched)
    if matched := matched_terms(combined, profile.get("stack_match_terms", [])):
        add_signal("stack_match", "Resume stack match", matched[:5])

    if matched := matched_terms(company, profile.get("worthwhile_company_terms", [])):
        add_signal("worthwhile_company", "High-value target company", matched)
    if matched := matched_terms(source, profile.get("preferred_sources", [])):
        add_signal("preferred_source", "Preferred application source", matched)
    if normalize(referral) in {"yes", "true"} or referral.strip():
        add_signal("referral", "Referral/contact present")

    if matched := matched_terms(company, profile.get("avoid_company_terms", [])):
        add_signal("avoid_company", "Staffing/recruiting company", matched)
    if matched := matched_terms(role, profile.get("senior_title_terms", [])):
        add_signal("senior_title", "Senior-level title", matched)
    if matched := matched_terms(role, profile.get("staff_principal_manager_terms", [])):
        add_signal("staff_principal_manager", "Staff/principal/manager title", matched)
    if matched := matched_terms(role, profile.get("non_swe_role_terms", [])):
        add_signal("non_swe_role", "Not a core SWE target", matched)
    if matched := matched_terms(combined, profile.get("clearance_or_hard_gate_terms", [])):
        add_signal("clearance_or_hard_gate", "Hard requirement gate", matched)
    if matched := matched_terms(status, profile.get("avoid_statuses", [])):
        add_signal("avoid_status", "Rejected/archived status", matched)

    clamped = max(1, min(10, score))
    return {"score": clamped, "raw_score": score, "signals": signals}


def score_application(row: dict[str, str], profile: dict) -> int:
    return int(score_application_detail(row, profile)["score"])


def should_reach_out(score: int, profile: dict, row: dict[str, str] | None = None) -> bool:
    if row is not None and contains_any(row.get("Status", ""), profile.get("avoid_statuses", [])):
        return False
    return score >= int(profile.get("reach_out_threshold", 1))
