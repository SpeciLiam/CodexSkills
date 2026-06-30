#!/usr/bin/env python3
"""Bay Area housing ledger + power-rankings engine.

Pure, deterministic, and offline. It never touches the network or a browser; it
only ingests capture files (JSON/CSV) and rebuilds the markdown trackers. Browser
/ AI capture is the conductor's job (see run.py and the SKILL capture adapter).

Tracker location can be overridden with HOUSING_TRACKER_DIR (used by tests and by
run.py so a dry run never clobbers the real trackers)."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[3]
TRACKER_DIR = Path(os.environ.get("HOUSING_TRACKER_DIR", ROOT / "housing-trackers"))
LISTINGS_MD = TRACKER_DIR / "listings.md"
RANKINGS_MD = TRACKER_DIR / "power-rankings.md"

# Generated table lives between these markers so human prose outside them survives
# a rewrite. Statuses are managed via housing_pipeline.py --mark, not by hand-editing rows.
LEDGER_BEGIN = "<!-- housing-ledger:begin (generated — set statuses via housing_pipeline.py --mark, do not hand-edit rows) -->"
LEDGER_END = "<!-- housing-ledger:end -->"
DEFAULT_LEDGER_PREAMBLE = (
    "# Housing Listings\n\n"
    "Source of truth for Bay Area housing candidates. Expired listings are kept, "
    "not deleted. The table below is generated — set statuses via `housing_pipeline.py --mark`, "
    "and add any of your own prose OUTSIDE the generated block."
)

LISTING_COLUMNS = [
    "Listing Key",
    "Source",
    "Title",
    "Market",
    "City",
    "Neighborhood",
    "Rent",
    "All-In Estimate",
    "Beds",
    "Baths",
    "Lease",
    "Available",
    "Commute",
    "Score",
    "No-Car Score",
    "Car Score",
    "Status",
    "First Seen",
    "Last Seen",
    "URL",
    "Why",
    "Notes",
]

# Columns recomputed by score_row every run — never carried over from an incoming
# capture during a merge (they would be stale).
DERIVED_COLUMNS = {"Commute", "Score", "No-Car Score", "Car Score", "Why"}

ACTIVE_STATUSES = {"Active"}
VERIFY_STATUSES = {"Needs Verification", "Stale"}
TERMINAL_STATUSES = {"Expired", "Unavailable", "Duplicate", "Rejected", "Source Blocked"}
# Decisions a human/automation made about a still-live listing. A plain re-capture
# must NOT silently flip these back to Active.
STICKY_STATUSES = {"Rejected", "Duplicate", "Source Blocked"}
# Statuses that mean "was available, now gone" — a genuine reappearance may revive.
GONE_STATUSES = {"Expired", "Unavailable"}
# Rows shown in the expired/replaced lane of the board.
REPLACED_STATUSES = TERMINAL_STATUSES | {"Stale"}
ALL_STATUSES = ACTIVE_STATUSES | VERIFY_STATUSES | TERMINAL_STATUSES

# Lifecycle events are recorded in Notes with one of these leading tokens so the
# replaced-lane "Reason" cell can recover why/when a listing was retired.
LIFECYCLE_TOKENS = (
    "Expired", "Unavailable", "Duplicate", "Rejected", "Source Blocked",
    "Stale", "Reappeared", "Seen again", "Active",
)

MARKET_ORDER = [
    "SF Mission/Valencia",
    "SF Dogpatch/Potrero/Showplace",
    "SF SoMa/South Beach/Mission Bay",
    "SF Hayes/Lower Haight/Castro/Duboce",
    "SF Sunset/Richmond/Marina/North Beach",
    "Mountain View",
    "Sunnyvale",
    "Santa Clara",
    "North San Jose",
    "Palo Alto/Menlo Park",
    "Redwood City/San Carlos/Belmont",
    "San Mateo/Burlingame/Millbrae",
    "Oakland/Berkeley",
    "Other Bay Area",
]

COMMUTE_DEFAULTS = {
    "Santa Clara": {"no_car": 22, "car": 12, "summary": "near office; local bus/bike/drive likely strongest"},
    "North San Jose": {"no_car": 35, "car": 18, "summary": "short South Bay commute; car or VTA can work"},
    "Sunnyvale": {"no_car": 45, "car": 22, "summary": "Caltrain/VTA or short drive; strong commute fit"},
    "Mountain View": {"no_car": 58, "car": 25, "summary": "Caltrain/VTA Orange connection; productive but transfer-heavy"},
    "Palo Alto/Menlo Park": {"no_car": 70, "car": 32, "summary": "Caltrain corridor; check station distance"},
    "Redwood City/San Carlos/Belmont": {"no_car": 80, "car": 45, "summary": "Caltrain corridor; commute is tolerable only near station"},
    "San Mateo/Burlingame/Millbrae": {"no_car": 90, "car": 55, "summary": "longer Caltrain corridor; check express timing"},
    "SF Mission/Valencia": {"no_car": 88, "car": 65, "summary": "SF lifestyle upside; needs easy Caltrain access"},
    "SF Dogpatch/Potrero/Showplace": {"no_car": 82, "car": 62, "summary": "best SF commute if close to 22nd St/4th & King"},
    "SF SoMa/South Beach/Mission Bay": {"no_car": 85, "car": 65, "summary": "best SF commute if close to 4th & King"},
    "SF Hayes/Lower Haight/Castro/Duboce": {"no_car": 100, "car": 75, "summary": "SF lifestyle upside, longer first mile to Caltrain"},
    "SF Sunset/Richmond/Marina/North Beach": {"no_car": 115, "car": 85, "summary": "usually too far unless listing is exceptional"},
    "Oakland/Berkeley": {"no_car": 115, "car": 70, "summary": "long and transfer-heavy to Santa Clara"},
    "Other Bay Area": {"no_car": 75, "car": 45, "summary": "needs manual commute verification"},
}

CAR_MONTHLY_BURDEN = 900

# Door-to-door estimates above are the morning (to-work) leg. The evening (from-work)
# leg runs a bit longer: Caltrain headways widen off-peak and the PM drive hits more
# traffic. These are added to the to-work time to report an honest from-work time.
TRANSIT_PM_EXTRA = 8
CAR_PM_EXTRA = 7
# Rents below this (after k-expansion) are implausible and treated as "no rent
# parsed" so the listing is flagged for verification rather than scored as a steal.
MIN_PLAUSIBLE_RENT = 300


def normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def clean(value: Any) -> str:
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


def today_iso() -> str:
    # Local date — the daily cron runs in America/Los_Angeles, and a UTC date can
    # be a day ahead late in the evening.
    return date.today().isoformat()


def parse_date(value: str) -> date | None:
    text = clean(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def split_markdown_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def escape_cell(value: Any) -> str:
    # Escape backslash FIRST, then pipe, so split_markdown_row round-trips both.
    return (
        clean(value)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\n", " ")
        .strip()
    )


def markdown_row(row: dict[str, str], columns: list[str]) -> str:
    return "| " + " | ".join(escape_cell(row.get(column, "")) for column in columns) + " |"


def _ledger_markers(text: str) -> tuple[list[str], int | None, int | None]:
    """Locate the begin/end markers ONLY as standalone lines. A marker string that
    appears inside a `| … |` table cell is never a standalone line, so it cannot be
    mistaken for the real delimiter (guards against marker-injection corruption)."""
    lines = text.splitlines()
    begin = end = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped == LEDGER_BEGIN and begin is None:
            begin = index
        elif stripped == LEDGER_END:
            end = index
    return lines, begin, end


def load_listing_rows() -> list[dict[str, str]]:
    if not LISTINGS_MD.exists():
        return []
    text = LISTINGS_MD.read_text(encoding="utf-8")
    lines, begin, end = _ledger_markers(text)
    # Only parse rows inside the generated block, so a human table added elsewhere
    # in the file is not mistaken for listings.
    if begin is not None:
        stop = end if (end is not None and end > begin) else len(lines)
        scan_lines = lines[begin + 1:stop]
    else:
        scan_lines = lines
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for line in scan_lines:
        if not line.strip().startswith("|"):
            continue
        cells = split_markdown_row(line)
        if "Listing Key" in cells:
            header = cells
            continue
        if header and cells and not all(re.fullmatch(r":?-{3,}:?", c or "") for c in cells):
            padded = cells + [""] * max(0, len(header) - len(cells))
            rows.append({column: padded[index].strip() for index, column in enumerate(header)})
    return rows


def write_listing_rows(rows: list[dict[str, str]]) -> None:
    TRACKER_DIR.mkdir(parents=True, exist_ok=True)
    table = [
        markdown_row({column: column for column in LISTING_COLUMNS}, LISTING_COLUMNS),
        "| " + " | ".join("---" for _ in LISTING_COLUMNS) + " |",
    ]
    for row in sorted(rows, key=lambda r: (market_sort_key(r.get("Market", "")), -to_int(r.get("Score")), r.get("Title", ""))):
        table.append(markdown_row(row, LISTING_COLUMNS))
    block = "\n".join([LEDGER_BEGIN, "", *table, "", LEDGER_END])

    existing = LISTINGS_MD.read_text(encoding="utf-8") if LISTINGS_MD.exists() else ""
    lines, begin, end = _ledger_markers(existing)
    # Preserve human prose before the begin marker and after the end marker. If a
    # marker is missing/dangling (corrupted or partly hand-deleted), keep whatever
    # is on the safe side rather than rebuilding from the template and nuking content.
    before_text = "\n".join(lines[:begin]).rstrip() if begin is not None else DEFAULT_LEDGER_PREAMBLE
    if end is not None and (begin is None or end > begin):
        after_text = "\n".join(lines[end + 1:]).strip()
    else:
        after_text = ""
    parts = [before_text, "", block]
    if after_text:
        parts += ["", after_text]
    LISTINGS_MD.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")


def first_value(record: dict[str, Any], keys: list[str]) -> str:
    lowered = {normalize(key).replace(" ", "_"): value for key, value in record.items()}
    for key in keys:
        if key in record and clean(record[key]):
            return clean(record[key])
        normalized = normalize(key).replace(" ", "_")
        if normalized in lowered and clean(lowered[normalized]):
            return clean(lowered[normalized])
    return ""


CONTAINER_KEYS = ("listings", "results", "items", "data", "posts", "apartments", "records")
LISTING_HINT_KEYS = {
    "title", "name", "url", "link", "price", "rent",
    "address", "city", "neighborhood", "description",
}


def flatten_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        records: list[dict[str, Any]] = []
        for item in value:
            records.extend(flatten_records(item))
        return records
    if not isinstance(value, dict):
        return []
    # Recurse into any container keys first. This fixes the case where a wrapper
    # dict carries both listing-ish keys AND a nested listings/data array — the old
    # code returned the wrapper and silently dropped the nested listings.
    nested: list[dict[str, Any]] = []
    for key in CONTAINER_KEYS:
        if key in value and value[key] is not None:
            nested.extend(flatten_records(value[key]))
    if nested:
        return nested
    keys = {normalize(key).replace(" ", "_") for key in value}
    if keys & LISTING_HINT_KEYS:
        return [value]
    return []


def load_capture(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix.lower() in {".csv", ".tsv"}:
        dialect = "excel-tab" if path.suffix.lower() == ".tsv" else "excel"
        return [dict(row) for row in csv.DictReader(text.splitlines(), dialect=dialect)]
    data = json.loads(text)
    return flatten_records(data)


def parse_money(value: str) -> int:
    """Parse a rent figure robustly.

    - Prefer $-anchored amounts ("750 sqft $3200" -> 3200, not 750).
    - Handle digit-glued k shorthand ("$3.2k" -> 3200, "2.5k" -> 2500).
    - For ranges, take the higher figure (conservative all-in, not the teaser low).
    - Reject implausibly small numbers ("2 bed" -> 0) so they flag for verification
      instead of scoring as a $2/mo steal.
    """
    text = clean(value)
    if not text:
        return 0
    dollar: list[float] = []
    suffixed: list[float] = []  # "k"-expanded, no $ anchor
    bare: list[float] = []
    for match in re.finditer(r"(\$)?\s*([0-9][0-9,]*(?:\.\d+)?)\s*([kKmM])?", text):
        has_dollar, number, suffix = match.group(1), match.group(2), match.group(3)
        if not number:
            continue
        amount = float(number.replace(",", ""))
        if suffix and suffix.lower() == "k":
            amount *= 1000
        elif suffix and suffix.lower() == "m":
            amount *= 1_000_000
        if has_dollar:
            dollar.append(amount)
        elif suffix:
            suffixed.append(amount)
        else:
            bare.append(amount)
    for bucket in (dollar, suffixed):
        plausible = [a for a in bucket if a >= MIN_PLAUSIBLE_RENT]
        if plausible:
            return int(round(max(plausible)))
    plausible_bare = [a for a in bare if a >= MIN_PLAUSIBLE_RENT]
    if plausible_bare:
        return int(round(max(plausible_bare)))
    return 0


def money_cell(value: int) -> str:
    return str(value) if value else ""


def canonical_url(url: str) -> str:
    text = clean(url)
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return text.rstrip("/")
    keep_params = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        if key.lower().startswith("utm_") or key.lower() in {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "referrer"}:
            continue
        keep_params.append((key, value))
    keep_params.sort()
    query = urlencode(keep_params)
    path = parsed.path.rstrip("/") or parsed.path
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", query, ""))


def slug(value: str) -> str:
    text = normalize(value)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:80] or "listing"


def listing_key(source: str, title: str, url: str, city: str, neighborhood: str, rent: int) -> str:
    if url:
        parsed = urlparse(url)
        # Include the (canonicalised) query so two distinct listings whose ids live
        # in the query string do not collide onto the same key.
        stable = f"{parsed.netloc}{parsed.path}?{parsed.query}"
        if stable.strip("/?"):
            return f"{slug(source)}-{hashlib.sha1(stable.encode()).hexdigest()[:10]}"
    fallback = "|".join([source, title, city, neighborhood, str(rent)])
    return f"{slug(source)}-{hashlib.sha1(normalize(fallback).encode()).hexdigest()[:10]}"


def infer_market(city: str, neighborhood: str, title: str, description: str) -> str:
    haystack = normalize(" ".join(str(part or "") for part in [city, neighborhood, title, description]))
    city_norm = normalize(city)
    if "san francisco" in haystack or city_norm in {"sf", "san francisco"}:
        if any(term in haystack for term in ["mission", "valencia", "bernal"]):
            return "SF Mission/Valencia"
        if any(term in haystack for term in ["dogpatch", "potrero", "showplace", "mission bay"]):
            return "SF Dogpatch/Potrero/Showplace"
        if any(term in haystack for term in ["soma", "south beach", "4th king", "4th & king"]):
            return "SF SoMa/South Beach/Mission Bay"
        if any(term in haystack for term in ["hayes", "lower haight", "castro", "duboce", "noe"]):
            return "SF Hayes/Lower Haight/Castro/Duboce"
        if any(term in haystack for term in ["sunset", "richmond", "marina", "north beach", "russian hill", "nob hill"]):
            return "SF Sunset/Richmond/Marina/North Beach"
        return "SF SoMa/South Beach/Mission Bay"
    if "mountain view" in haystack:
        return "Mountain View"
    if "sunnyvale" in haystack:
        return "Sunnyvale"
    if "santa clara" in haystack:
        return "Santa Clara"
    if "north san jose" in haystack or ("san jose" in haystack and any(term in haystack for term in ["north", "tasman", "first", "zanker", "river oaks"])):
        return "North San Jose"
    if "palo alto" in haystack or "menlo park" in haystack:
        return "Palo Alto/Menlo Park"
    if "redwood city" in haystack or "san carlos" in haystack or "belmont" in haystack:
        return "Redwood City/San Carlos/Belmont"
    if "san mateo" in haystack or "burlingame" in haystack or "millbrae" in haystack:
        return "San Mateo/Burlingame/Millbrae"
    if "oakland" in haystack or "berkeley" in haystack or "emeryville" in haystack:
        return "Oakland/Berkeley"
    return "Other Bay Area"


def infer_city(market: str, city: str, text: str) -> str:
    if city:
        return city
    haystack = normalize(text)
    for candidate in ["San Francisco", "Mountain View", "Sunnyvale", "Santa Clara", "San Jose", "Palo Alto", "Menlo Park", "Redwood City", "San Mateo", "Oakland", "Berkeley"]:
        if normalize(candidate) in haystack:
            return candidate
    if market.startswith("SF "):
        return "San Francisco"
    return ""


def infer_status(record_status: str, rent: int, url: str, title: str) -> str:
    status_text = normalize(record_status)
    if any(term in status_text for term in ["source blocked", "blocked", "captcha", "rate limit", "forbidden", "403", "429", "login wall", "paywall"]):
        return "Source Blocked"
    if any(term in status_text for term in ["expired", "deleted", "rented", "no longer", "removed", "taken"]):
        return "Expired"
    if any(term in status_text for term in ["unavailable", "not available", "off market", "off-market", "on hold", "pending", "waitlist"]):
        return "Unavailable"
    if any(term in status_text for term in ["duplicate", "dupe"]):
        return "Duplicate"
    if any(term in status_text for term in ["rejected", "skip", "scam"]):
        return "Rejected"
    if not title or not rent or not url:
        return "Needs Verification"
    return "Active"


def flexibility_score(lease: str, title: str, description: str) -> tuple[int, str]:
    """Flexibility is the #1 stated priority, so it carries the largest swing."""
    text = normalize(" ".join(str(part or "") for part in [lease, title, description]))
    score = 2
    reasons: list[str] = []
    if "sublease" in text or "sublet" in text:
        score += 14
        reasons.append("sublease")
    if "month to month" in text or "month-to-month" in text or "m2m" in text or "mtm" in text:
        score += 12
        reasons.append("month-to-month")
    if "furnished" in text:
        score += 5
        reasons.append("furnished")
    if "short term" in text or "short-term" in text or re.search(r"\b[1-6]\s*month", text):
        score += 5
        reasons.append("short-term")
    if "flexible lease" in text or "flexible term" in text or "any term" in text:
        score += 4
        reasons.append("flexible term")
    if "12 month" in text or "12-month" in text or "one year" in text or "1 year" in text or "annual lease" in text:
        score -= 10
        reasons.append("12-month")
    return max(0, min(30, score)), ", ".join(reasons) or "lease unclear"


def value_score(rent: int) -> int:
    if rent <= 0:
        return 2  # unknown rent must not out-score an honestly-priced listing (it is also flagged Needs Verification)
    if rent <= 1800:
        return 18
    if rent <= 2400:
        return 17
    if rent <= 2800:
        return 16
    if rent <= 3300:
        return 15
    if rent <= 3750:
        return 13
    if rent <= 4200:
        return 10
    if rent <= 4500:
        return 7
    if rent <= 5000:
        return 3
    return 0


def commute_component(minutes: int) -> int:
    if minutes <= 0:
        return 8  # unknown commute is neutral, not "excellent"
    if minutes <= 25:
        return 22
    if minutes <= 40:
        return 19
    if minutes <= 55:
        return 15
    if minutes <= 70:
        return 11
    if minutes <= 90:
        return 7
    if minutes <= 110:
        return 3
    return 1


def quality_score(title: str, description: str, lease: str) -> int:
    text = normalize(" ".join(str(part or "") for part in [title, description, lease]))
    score = 5
    for term in ["laundry", "washer", "dryer", "parking", "gym", "balcony", "ac", "air conditioning", "utilities included", "private bathroom", "caltrain", "vta"]:
        if term in text:
            score += 1
    for term in ["shared room", "no kitchen", "no laundry", "scam", "wire", "deposit before viewing", "zelle only", "cashapp"]:
        if term in text:
            score -= 2
    return max(0, min(10, score))


def confidence_score(row: dict[str, str]) -> int:
    score = 10
    for field in ["URL", "Rent", "Market", "Lease", "Available"]:
        if not clean(row.get(field)):
            score -= 1
    status = row.get("Status", "")
    if status == "Needs Verification":
        score -= 3
    if status in TERMINAL_STATUSES:
        score = 0
    return max(0, min(10, score))


def neighborhood_score(market: str, title: str, description: str) -> int:
    """Reward transit/office proximity rather than the market itself, so SF is not
    double-penalised (it already pays in the commute component)."""
    text = normalize(" ".join(str(part or "") for part in [market, title, description]))
    score = 3
    if any(term in text for term in ["caltrain", "near station", "walk to train", "walk to caltrain", "near bart", "vta"]):
        score += 1
    if any(term in text for term in ["mission college", "great america", "old ironsides", "santa clara square"]):
        score += 1
    if any(term in text for term in ["walkable", "walk score", "downtown"]):
        score += 1
    return max(0, min(5, score))


# Caltrain is the only realistic SF -> Santa Clara link and the train leg alone is
# ~63 min, plus a ~12 min last mile from Santa Clara station to the office, so every
# SF no-car commute is anchored at ~75 min. What actually separates SF listings is the
# *first mile to a station* (4th & King, or 22nd St). Crucially that first mile can be
# BIKED (Caltrain takes bikes), which is much faster than walking/Muni, so even "far"
# SF neighborhoods stay viable - we model bike-minutes-to-station, not walk.
SF_TRAIN_PLUS_LAST_MILE = 75  # 4th & King -> Santa Clara station -> office, fixed leg

# Bike minutes from the neighborhood to its nearest Caltrain station (4th & King / 22nd St).
SF_BIKE_FIRST_MILE = [
    (("mission bay", "south beach", "east cut", "4th & king", "4th and king",
      "fourth and king", "22nd st", "22nd street", "near caltrain", "walk to caltrain",
      "at caltrain"), 4),
    (("soma", "south of market", "rincon", "dogpatch", "potrero", "showplace"), 7),
    (("mission district", "mission /", "valencia", "mission dolores"), 9),
    (("hayes", "duboce", "lower haight", "civic center", "tenderloin", "castro",
      "noe valley", "bernal", "glen park", "nob hill", "russian hill"), 13),
    (("marina", "pacific heights", "cow hollow", "north beach", "usf", "panhandle",
      "inner richmond", "inner sunset", "haight", "twin peaks", "excelsior",
      "outer mission", "ingleside", "balboa"), 18),
    (("outer richmond", "seacliff", "outer sunset", "sunset", "richmond", "presidio"), 25),
]


def sf_no_car_first_mile(neighborhood: str, title: str) -> tuple[int, str]:
    """Bike minutes from an SF listing to its nearest Caltrain station, plus a label.
    Defaults to 15 (a mid bike) when the neighborhood is unknown/generic."""
    text = normalize(" ".join(str(p or "") for p in [neighborhood, title]))
    for terms, minutes in SF_BIKE_FIRST_MILE:
        if any(t in text for t in terms):
            return minutes, f"~{minutes}m bike to Caltrain"
    return 15, "~15m bike to Caltrain (est)"


def _components(row: dict[str, str]) -> dict[str, Any]:
    rent = parse_money(row.get("All-In Estimate") or row.get("Rent", ""))
    market = row.get("Market", "") or "Other Bay Area"
    commute = COMMUTE_DEFAULTS.get(market, COMMUTE_DEFAULTS["Other Bay Area"])
    if market.startswith("SF"):
        bike, bike_note = sf_no_car_first_mile(
            row.get("Neighborhood", ""), row.get("Title", "")
        )
        commute = {
            "no_car": SF_TRAIN_PLUS_LAST_MILE + bike,  # bike + Caltrain + last mile
            "car": commute["car"],
            "summary": f"bike+Caltrain ({bike_note})",
        }
    flex, flex_reason = flexibility_score(row.get("Lease", ""), row.get("Title", ""), row.get("Notes", ""))
    return {
        "rent": rent,
        "market": market,
        "commute": commute,
        "flex": flex,
        "flex_reason": flex_reason,
        "value": value_score(rent),
        "quality": quality_score(row.get("Title", ""), row.get("Notes", ""), row.get("Lease", "")),
        "confidence": confidence_score(row),
        "nhood": neighborhood_score(market, row.get("Title", ""), row.get("Notes", "")),
    }


def score_row(row: dict[str, str]) -> dict[str, str]:
    status = row.get("Status", "")
    if status in TERMINAL_STATUSES:
        row["Score"] = row["No-Car Score"] = row["Car Score"] = "0"
        if not clean(row.get("Why")):
            row["Why"] = reason_from_notes(row) or status
        return row

    c = _components(row)
    rent = c["rent"]
    commute = c["commute"]
    base = c["value"] + c["flex"] + c["quality"] + c["confidence"] + c["nhood"]
    no_car = base + commute_component(commute["no_car"])
    car_value = value_score(rent + CAR_MONTHLY_BURDEN if rent else 0)
    car = car_value + commute_component(commute["car"]) + c["flex"] + c["quality"] + c["confidence"] + c["nhood"]
    overall = max(no_car, car - 3)

    if status in VERIFY_STATUSES:
        overall = max(0, overall - 8)

    row["Score"] = str(max(0, min(100, int(round(overall)))))
    row["No-Car Score"] = str(max(0, min(100, int(round(no_car)))))
    row["Car Score"] = str(max(0, min(100, int(round(car)))))

    nc_to = commute["no_car"]
    nc_from = nc_to + TRANSIT_PM_EXTRA
    car_to = commute["car"]
    car_from = car_to + CAR_PM_EXTRA
    row["Commute"] = (
        f"{commute['summary']}; no-car ~{nc_to}m to work / ~{nc_from}m home, "
        f"car ~{car_to}m / ~{car_from}m"
    )

    reason_bits = [c["flex_reason"], f"to work ~{nc_to}m / home ~{nc_from}m (no-car)"]
    if rent:
        reason_bits.append(f"${rent}/mo all-in")
    if car - 3 > no_car:
        reason_bits.append("car scenario drives rank (costs ~$900/mo)")
    row["Why"] = "; ".join(bit for bit in reason_bits if bit)
    return row


def merge_notes(existing: str, addition: str) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for chunk in (existing, addition):
        for piece in re.split(r"\s*;\s*", clean(chunk)):
            if piece and piece not in seen:
                parts.append(piece)
                seen.add(piece)
    return "; ".join(parts)


def record_lifecycle(row: dict[str, str], reason: str) -> None:
    row["Notes"] = merge_notes(row.get("Notes", ""), reason)
    row["Why"] = reason


def reason_from_notes(row: dict[str, str]) -> str:
    """Most recent lifecycle event recorded in Notes (for the replaced lane)."""
    pieces = [p.strip() for p in re.split(r"\s*;\s*", clean(row.get("Notes", ""))) if p.strip()]
    for piece in reversed(pieces):
        if any(piece.startswith(token) for token in LIFECYCLE_TOKENS):
            return piece
    return ""


def row_from_record(record: dict[str, Any], default_source: str, run_date: str) -> dict[str, str]:
    source = first_value(record, ["source", "site", "platform"]) or default_source
    title = first_value(record, ["title", "name", "listing", "headline"])
    url = canonical_url(first_value(record, ["url", "link", "listing_url", "href"]))
    city = first_value(record, ["city", "municipality", "location_city"])
    neighborhood = first_value(record, ["neighborhood", "area", "district"])
    address = first_value(record, ["address", "street", "location"])
    description = first_value(record, ["description", "notes", "body", "summary", "details"])
    lease = first_value(record, ["lease", "lease_term", "term", "availability_terms"])
    available = first_value(record, ["available", "available_date", "move_in", "move_in_date"])
    # Base rent and all-in are sourced from DISTINCT key sets so a capture that
    # provides both keeps the base-vs-all-in spread instead of overwriting one.
    rent = parse_money(first_value(record, ["rent", "price", "monthly_rent", "base_rent"]))
    all_in = parse_money(first_value(record, ["all_in", "all_in_estimate", "monthly_total", "estimated_total"]))
    if not rent and not all_in and title:
        # Classifieds (Craigslist/FB) lead the title with the price, e.g.
        # "$2,400 / 1br Sunnyvale sublease". Reading that visible leading $ amount is
        # capture, not invention. Anchored on $ so "1br"/"2 bed" never parse as rent.
        lead = re.search(r"\$\s*[0-9][0-9,]*(?:\.\d+)?\s*[kKmM]?", title)
        if lead:
            rent = parse_money(lead.group(0))
    if not rent:
        rent = all_in
    if not all_in:
        all_in = rent
    market = first_value(record, ["market", "bucket"])
    if not market:
        market = infer_market(city, neighborhood, title, " ".join([description, address]))
    if not city:
        city = infer_city(market, city, " ".join([title, neighborhood, address, description]))
    status = infer_status(first_value(record, ["status", "availability_status"]), rent, url, title)
    key = first_value(record, ["listing_key", "key", "id"])
    if not key:
        key = listing_key(source, title, url, city, neighborhood, rent)
    notes = description
    if address and normalize(address) not in normalize(notes):
        notes = "; ".join(p for p in [notes, f"addr: {address}"] if p)

    row = {
        "Listing Key": key,
        "Source": source,
        "Title": title,
        "Market": market,
        "City": city,
        "Neighborhood": neighborhood,
        "Rent": money_cell(rent),
        "All-In Estimate": money_cell(all_in),
        "Beds": first_value(record, ["beds", "bedrooms", "br"]),
        "Baths": first_value(record, ["baths", "bathrooms", "ba"]),
        "Lease": lease,
        "Available": available,
        "Commute": "",
        "Score": "",
        "No-Car Score": "",
        "Car Score": "",
        "Status": status,
        "First Seen": run_date,
        "Last Seen": run_date,
        "URL": url,
        "Why": "",
        "Notes": notes,
    }
    return score_row(row)


def merge_row(existing: dict[str, str], incoming: dict[str, str], run_date: str) -> dict[str, str]:
    merged = existing.copy()
    for column in LISTING_COLUMNS:
        if column in {"Listing Key", "First Seen", "Status", "Notes"} or column in DERIVED_COLUMNS:
            continue
        incoming_value = clean(incoming.get(column, ""))
        if incoming_value:
            merged[column] = incoming_value
    merged["Last Seen"] = run_date

    existing_status = clean(existing.get("Status", ""))
    incoming_status = clean(incoming.get("Status", "")) or "Active"
    if existing_status in STICKY_STATUSES:
        # A human/automation decision about a still-live listing — do not auto-revive.
        # Last Seen already records that it is still around; we deliberately do NOT
        # append a per-run note (that would grow one line per day).
        merged["Status"] = existing_status
    elif existing_status in (GONE_STATUSES | {"Stale"}) and incoming_status == "Active":
        merged["Status"] = "Active"
        record_lifecycle(merged, f"Reappeared {run_date}")
    else:
        merged["Status"] = incoming_status
    return score_row(merged)


def _fast_decay_source(source: str) -> bool:
    src = normalize(source)
    return any(token in src for token in ["facebook", "fb", "craigslist", "marketplace", "sublet", "roommate", "gypsy", "nextdoor", "reddit"])


def mark_stale(rows: list[dict[str, str]], run_date: str, stale_days: int, retire_days: int) -> None:
    current = parse_date(run_date) or date.today()
    for row in rows:
        status = row.get("Status", "")
        last_seen = parse_date(row.get("Last Seen", ""))
        if not last_seen:
            continue
        age = (current - last_seen).days
        if status in ACTIVE_STATUSES:
            fast = _fast_decay_source(row.get("Source", ""))
            stale = age >= 2 if fast else age > stale_days
            if stale:
                row["Status"] = "Stale"
                record_lifecycle(row, f"Stale {run_date}: last seen {age}d ago")
                score_row(row)
        elif status in {"Needs Verification", "Stale"} and retire_days > 0 and age >= retire_days:
            # Long-unseen verify/stale rows exit the board to the replaced lane.
            row["Status"] = "Unavailable"
            record_lifecycle(row, f"Unavailable {run_date}: not re-seen for {age}d")
            score_row(row)


def apply_marks(rows: list[dict[str, str]], marks: list[tuple[str, str]], run_date: str) -> int:
    """marks: list of (status, identifier) where identifier is a listing key or URL."""
    changed = 0
    for status, ident in marks:
        status = status.strip()
        if status not in ALL_STATUSES:
            print(f"WARNING: unknown status '{status}' (skipped)", file=sys.stderr)
            continue
        ident_url = canonical_url(ident)
        for row in rows:
            if row.get("Listing Key") == ident or canonical_url(row.get("URL", "")) == ident_url and ident_url:
                row["Status"] = status
                row["Last Seen"] = run_date
                record_lifecycle(row, f"{status} {run_date}: set manually")
                score_row(row)
                changed += 1
    return changed


def mark_expired(rows: list[dict[str, str]], keys: list[str], urls: list[str], run_date: str) -> None:
    marks = [("Expired", k) for k in keys] + [("Expired", u) for u in urls]
    apply_marks(rows, marks, run_date)


def to_int(value: Any) -> int:
    try:
        return int(float(clean(value) or "0"))
    except ValueError:
        return 0


def market_sort_key(market: str) -> tuple[int, str]:
    try:
        return (MARKET_ORDER.index(market), market)
    except ValueError:
        return (len(MARKET_ORDER), market)


def detail_count(row: dict[str, str]) -> int:
    return sum(1 for f in ["URL", "Rent", "Lease", "Available", "Beds", "Neighborhood"] if clean(row.get(f)))


def rank_sort_key(row: dict[str, str]) -> tuple:
    """Implements the documented tie-breaker order after Score:
    flexibility -> commute -> all-in cost -> no-car transit -> availability
    confidence -> neighborhood -> source detail."""
    c = _components(row)
    all_in = to_int(row.get("All-In Estimate") or row.get("Rent")) or 10 ** 7
    return (
        -to_int(row.get("Score")),
        -c["flex"],
        c["commute"]["no_car"],
        all_in,
        -commute_component(c["commute"]["no_car"]),
        -c["confidence"],
        -c["nhood"],
        -detail_count(row),
        row.get("Title", ""),
    )


def active_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("Status") in ACTIVE_STATUSES]


def needs_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("Status") == "Needs Verification"]


def replaced_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("Status") in REPLACED_STATUSES]


def link_cell(row: dict[str, str]) -> str:
    url = clean(row.get("URL", ""))
    return f"[Open]({url})" if url else ""


def compact_title(title: str) -> str:
    text = clean(title)
    if len(text) <= 72:
        return text
    return text[:69].rstrip() + "..."


def rent_value(row: dict[str, str]) -> str:
    rent = to_int(row.get("All-In Estimate") or row.get("Rent"))
    return str(rent) if rent else ""


def why_cell(row: dict[str, str]) -> str:
    why = clean(row.get("Why", ""))
    if why:
        bits = [bit.strip() for bit in why.split(";") if bit.strip()]
        return "; ".join(bits[:3])
    notes = clean(row.get("Notes", ""))
    bits = [bit.strip() for bit in notes.split(";") if bit.strip()]
    return "; ".join(bits[:2])


def reason_cell(row: dict[str, str]) -> str:
    return reason_from_notes(row) or row.get("Status", "")


def delta_key(row: dict[str, str]) -> str:
    # Fall back to the COMPACT title so it matches what the previous board stored
    # (titles are truncated for display); otherwise URL-less rows always read "New".
    return canonical_url(row.get("URL", "")) or normalize(compact_title(row.get("Title", "")))


def parse_previous_rankings() -> dict[tuple[str, str], int]:
    if not RANKINGS_MD.exists():
        return {}
    previous: dict[tuple[str, str], int] = {}
    section = ""
    current_market = ""
    for raw in RANKINGS_MD.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("### "):
            current_market = line.removeprefix("### ").split(" (", 1)[0].strip()
            section = "market"
            continue
        if line.startswith("## Top 5 Overall"):
            section = "overall"
            current_market = ""
            continue
        if line.startswith("## ") and not line.startswith("## Top 5 Overall"):
            section = ""
        if not line.startswith("|"):
            continue
        cells = split_markdown_row(line)
        if not cells or not re.fullmatch(r"\d+", cells[0]):
            continue
        rank = int(cells[0])
        url = ""
        match = re.search(r"\((https?://[^)]+)\)", cells[-1])
        if match:
            url = canonical_url(match.group(1))
        title = cells[7] if len(cells) > 7 else ""
        key = url or normalize(title)
        if not key:
            continue
        if section == "overall":
            previous[("overall", key)] = rank
            previous[("any", key)] = rank
        elif section == "market":
            previous[(current_market, key)] = rank
            previous[("any", key)] = rank
    return previous


def delta_cell(previous: dict[tuple[str, str], int], scope: str, row: dict[str, str], rank: int) -> str:
    if scope == "new":
        # The New Entrants section only holds rows first seen today (First Seen ==
        # run_date), so cross-board delta is meaningless — they are genuinely new.
        return "New"
    key = delta_key(row)
    old = previous.get((scope, key))
    if old is None:
        if previous.get(("any", key)) is not None:
            return "Re-entered"
        return "New"
    change = old - rank
    if change == 0:
        return "Same"
    if change > 0:
        return f"+{change}"
    return str(change)


RANK_HEADERS = ["Rank", "Delta", "Score", "No-Car", "Car", "Rent", "Market", "Listing", "Lease", "Commute", "Why", "Status", "Link"]


def ranking_table(rows: list[dict[str, str]], previous: dict[tuple[str, str], int], scope: str) -> list[str]:
    lines = [
        "| " + " | ".join(RANK_HEADERS) + " |",
        "| ---: | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, row in enumerate(rows, start=1):
        cells = {
            "Rank": str(index),
            "Delta": delta_cell(previous, scope, row, index),
            "Score": row.get("Score", ""),
            "No-Car": row.get("No-Car Score", ""),
            "Car": row.get("Car Score", ""),
            "Rent": rent_value(row),
            "Market": row.get("Market", ""),
            "Listing": compact_title(row.get("Title", "")),
            "Lease": row.get("Lease", ""),
            "Commute": row.get("Commute", ""),
            "Why": why_cell(row),
            "Status": row.get("Status", ""),
            "Link": link_cell(row),
        }
        lines.append(markdown_row(cells, RANK_HEADERS))
    return lines


def empty_rank_table() -> list[str]:
    return [
        "| " + " | ".join(RANK_HEADERS) + " |",
        "| ---: | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]


def build_rankings(rows: list[dict[str, str]], run_date: str) -> None:
    previous = parse_previous_rankings()
    active = sorted(active_rows(rows), key=rank_sort_key)
    needs = sorted(needs_rows(rows), key=rank_sort_key)
    replaced = sorted(replaced_rows(rows), key=lambda r: (r.get("Last Seen", ""), r.get("Market", ""), r.get("Title", "")), reverse=True)

    overall_top = active[:5]
    new_entrants = [row for row in active if row.get("First Seen") == run_date][:20]

    lines = [
        "# Bay Area Housing Power Rankings",
        "",
        "Generated board for daily review. The canonical listing ledger is `housing-trackers/listings.md`.",
        "",
        f"Last refreshed: {run_date}",
        "",
        "## Daily Summary",
        "",
        f"- Active listings: {len(active)}",
        f"- Needs verification: {len(needs)}",
        f"- Expired/unavailable/stale/replaced: {len(replaced)}",
        f"- New top-5 entrants: {sum(1 for i, row in enumerate(overall_top, 1) if delta_cell(previous, 'overall', row, i) == 'New')}",
        "",
        "## Top 5 Overall Active",
        "",
    ]
    lines.extend(ranking_table(overall_top, previous, "overall") if overall_top else empty_rank_table())

    lines.extend(["", "## Top 5 By Market", ""])
    by_market: dict[str, list[dict[str, str]]] = {}
    for row in active:
        by_market.setdefault(row.get("Market") or "Other Bay Area", []).append(row)
    if by_market:
        for market in sorted(by_market, key=market_sort_key):
            market_rows = sorted(by_market[market], key=rank_sort_key)[:5]
            label = "Top 5" if len(by_market[market]) >= 5 else "Underfilled"
            lines.extend([f"### {market} ({label})", ""])
            lines.extend(ranking_table(market_rows, previous, market))
            lines.append("")
    else:
        lines.append("No active listings yet.")

    lines.extend(["", "## New Entrants", ""])
    if new_entrants:
        lines.extend(ranking_table(new_entrants[:10], previous, "new"))
    else:
        lines.append("No new entrants yet.")

    lines.extend(["", "## Expired / Unavailable / Stale / Replaced", ""])
    if replaced:
        lines.extend([
            "| Status | Last Seen | Market | Listing | Rent | Reason | Link |",
            "| --- | --- | --- | --- | ---: | --- | --- |",
        ])
        for row in replaced[:60]:
            cells = {
                "Status": row.get("Status", ""),
                "Last Seen": row.get("Last Seen", ""),
                "Market": row.get("Market", ""),
                "Listing": compact_title(row.get("Title", "")),
                "Rent": rent_value(row),
                "Reason": reason_cell(row),
                "Link": link_cell(row),
            }
            lines.append(markdown_row(cells, ["Status", "Last Seen", "Market", "Listing", "Rent", "Reason", "Link"]))
    else:
        lines.append("No expired or replaced listings yet.")

    lines.extend(["", "## Needs Manual Verification", ""])
    if needs:
        lines.extend(ranking_table(needs[:25], previous, "needs"))
    else:
        lines.append("No listings need manual verification yet.")

    lines.extend(["", "## Source Blockers", ""])
    blockers = [row for row in rows if row.get("Status") == "Source Blocked"]
    if blockers:
        for row in blockers:
            lines.append(f"- {row.get('Source', 'Unknown source')}: {reason_cell(row)} ({link_cell(row) or 'no link'})")
    else:
        lines.append("No blockers recorded yet.")

    RANKINGS_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def ingest(inputs: list[Path], default_source: str, run_date: str, rows: list[dict[str, str]]) -> tuple[int, int, list[str]]:
    by_key = {row.get("Listing Key", ""): row for row in rows if row.get("Listing Key")}
    by_url = {canonical_url(row.get("URL", "")): row for row in rows if canonical_url(row.get("URL", ""))}
    created = 0
    updated = 0
    warnings: list[str] = []
    for input_path in inputs:
        try:
            records = load_capture(input_path)
        except (json.JSONDecodeError, UnicodeDecodeError, csv.Error, OSError) as exc:
            # One malformed capture must not abort the whole run or discard good data.
            warnings.append(f"skipped {input_path.name}: {type(exc).__name__}: {exc}")
            print(f"WARNING: skipped malformed capture {input_path}: {exc}", file=sys.stderr)
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            incoming = row_from_record(record, default_source, run_date)
            key = incoming.get("Listing Key", "")
            url = canonical_url(incoming.get("URL", ""))
            existing = by_key.get(key) or (by_url.get(url) if url else None)
            if existing:
                merged = merge_row(existing, incoming, run_date)
                existing.clear()
                existing.update(merged)
                updated += 1
            else:
                rows.append(incoming)
                by_key[incoming["Listing Key"]] = incoming
                if url:
                    by_url[url] = incoming
                created += 1
    return created, updated, warnings


def run(
    inputs: list[Path] | None = None,
    default_source: str = "manual",
    run_date: str | None = None,
    marks: list[tuple[str, str]] | None = None,
    expire_keys: list[str] | None = None,
    expire_urls: list[str] | None = None,
    stale_days: int = 3,
    retire_days: int = 14,
    refresh_only: bool = False,
) -> dict[str, Any]:
    run_date = run_date or today_iso()
    inputs = inputs or []
    rows = load_listing_rows()
    created = updated = 0
    warnings: list[str] = []
    if inputs and not refresh_only:
        created, updated, warnings = ingest(inputs, default_source, run_date, rows)

    apply_marks(rows, marks or [], run_date)
    mark_expired(rows, expire_keys or [], expire_urls or [], run_date)
    mark_stale(rows, run_date, stale_days, retire_days)
    for row in rows:
        score_row(row)

    write_listing_rows(rows)
    build_rankings(rows, run_date)

    return {
        "created": created,
        "updated": updated,
        "total": len(rows),
        "active": len(active_rows(rows)),
        "needs_verification": len(needs_rows(rows)),
        "replaced": len(replaced_rows(rows)),
        "warnings": warnings,
        "listings": str(LISTINGS_MD),
        "rankings": str(RANKINGS_MD),
    }


def parse_mark(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected STATUS=IDENTIFIER (e.g. Rejected=https://...)")
    status, ident = value.split("=", 1)
    return status.strip(), ident.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Bay Area housing captures and rebuild power rankings.")
    parser.add_argument("--input", nargs="*", type=Path, default=[], help="JSON/CSV/TSV capture file(s)")
    parser.add_argument("--source", default="manual", help="Default source label for captures")
    parser.add_argument("--refresh-only", action="store_true", help="Re-score and rebuild rankings without ingesting new captures")
    parser.add_argument("--mark", action="append", type=parse_mark, default=[], metavar="STATUS=IDENTIFIER",
                        help="Set a listing's status by key or URL, e.g. --mark Rejected=https://... or --mark Unavailable=<key>")
    parser.add_argument("--expire-key", action="append", default=[], help="Listing key to mark expired (alias for --mark Expired=<key>)")
    parser.add_argument("--expire-url", action="append", default=[], help="Listing URL to mark expired")
    parser.add_argument("--stale-days", type=int, default=3, help="Mark active listings stale after this many days without seeing them")
    parser.add_argument("--retire-days", type=int, default=14, help="Move long-unseen needs-verification/stale rows to the replaced lane after this many days (0 disables)")
    parser.add_argument("--date", default=today_iso(), help="Run date YYYY-MM-DD")
    args = parser.parse_args()

    missing = [path for path in args.input if not path.exists()]
    if missing:
        for path in missing:
            print(f"ERROR: input not found: {path}", file=sys.stderr)
        return 2

    summary = run(
        inputs=args.input,
        default_source=args.source,
        run_date=args.date,
        marks=args.mark,
        expire_keys=args.expire_key,
        expire_urls=args.expire_url,
        stale_days=args.stale_days,
        retire_days=args.retire_days,
        refresh_only=args.refresh_only,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
