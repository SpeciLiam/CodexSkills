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
import fcntl
import functools
import hashlib
import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import commute_origins as commute_geo  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
TRACKER_DIR = Path(os.environ.get("HOUSING_TRACKER_DIR", ROOT / "housing-trackers"))
LOCK_FILE = Path(os.environ.get("HOUSING_LOCK_FILE", "/tmp/codexskills-housing-hunt/pipeline.lock"))
CONDUCTOR_LOCK_FILE = Path(
    os.environ.get("HOUSING_CONDUCTOR_LOCK_FILE", "/tmp/codexskills-housing-hunt/conductor.lock")
)
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
    "Lat",
    "Lng",
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

# Group 5+ lane (household.json "group" profile: 5 people x $2,650 = $13,250/mo).
# Value for a 5+ bed house is judged on the PER-PERSON split, not the total —
# value_score(13000) = 0 was zeroing out every group listing.
GROUP_MIN_BEDS = 5
GROUP_BUDGET_PER_PERSON = 2650

# Door-to-door estimates above are the morning (to-work) leg. The evening (from-work)
# leg runs a bit longer: Caltrain headways widen off-peak and the PM drive hits more
# traffic. These are added to the to-work time to report an honest from-work time.
TRANSIT_PM_EXTRA = 8
CAR_PM_EXTRA = 7
# Rents below this (after k-expansion) are implausible and treated as "no rent
# parsed" so the listing is flagged for verification rather than scored as a steal.
MIN_PLAUSIBLE_RENT = 300
NEED_START = date(2026, 7, 16)
MIN_STAY_DAYS = 60
TOP_OVERALL_MIN_END = NEED_START + timedelta(days=30)


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


def parse_float(value: Any) -> float | None:
    text = clean(value)
    if not text:
        return None
    try:
        return float(text)
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
            row = {column: padded[index].strip() for index, column in enumerate(header)}
            for column in LISTING_COLUMNS:
                row.setdefault(column, "")
            rows.append(row)
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
    atomic_write_text(LISTINGS_MD, "\n".join(parts).rstrip() + "\n")


def atomic_write_text(path: Path, text: str) -> None:
    """Write a generated artifact atomically so interruption cannot truncate it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_name = tmp.name
        os.replace(tmp_name, path)
    finally:
        if tmp_name:
            try:
                Path(tmp_name).unlink(missing_ok=True)
            except OSError:
                pass


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


# A 1-2 digit bedroom count (optionally a tight range like "1-2" / "2/3") immediately
# before a bedroom token. The negative lookbehind prevents price bleed:
# "$5,200 / 6br" reads 6 beds, while "$5200 2bd" reads 2 beds.
BED_COUNT_RE = re.compile(
    r"(?<![\d,.$])(\d{1,2})(?:\s?[-/]\s?(\d{1,2}))?\s*(?:bd|br|beds?|bedrooms?|hab\b|habitaci\w*|室|卧)",
    re.I,
)
WORD_BEDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
WORD_BED_RE = re.compile(r"\b(" + "|".join(WORD_BEDS) + r")\b[\s-]+(?:bed|bd|br)", re.I)
BED_COUNT_MAX = 12


def parse_bed_count(text: str):
    """Whole-unit bedroom count from explicit bed text/title; None when absent."""
    t = clean(text).lower()
    if not t:
        return None
    m = BED_COUNT_RE.search(t)
    if m:
        cands = [int(g) for g in m.groups() if g is not None and int(g) <= BED_COUNT_MAX]
        if cands:
            return max(cands)
    w = WORD_BED_RE.search(t)
    if w:
        return WORD_BEDS[w.group(1)]
    if ("studio" in t) or ("estudio" in t) or ("monoambiente" in t):
        return 0
    return None


MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


def detect_cadence(text: str) -> str:
    norm = normalize(text)
    if re.search(r"\b(weekly|per week|a week|/wk|wkly)\b", norm):
        return "weekly"
    if re.search(r"\b(nightly|per night|/night|a day|daily|per day)\b", norm):
        return "nightly"
    return ""


def _window_date(month: str, day: str, year: str = "") -> date | None:
    month_num = MONTHS.get(normalize(month)[:3]) if len(normalize(month)) > 3 else MONTHS.get(normalize(month))
    if not month_num:
        return None
    yr = int(year) if year else NEED_START.year
    try:
        return date(yr, month_num, int(day))
    except ValueError:
        return None


def parse_stay_window(text: str) -> tuple[date | None, date | None]:
    raw = clean(text)
    if not raw:
        return None, None
    month_names = "|".join(sorted(MONTHS, key=len, reverse=True))
    pattern = re.compile(
        rf"\b({month_names})\.?\s+(\d{{1,2}})(?:,\s*(\d{{4}}))?\s*(?:-|–|—|to|through)\s*"
        rf"(?:(?:({month_names})\.?\s+)?(\d{{1,2}})(?:,\s*(\d{{4}}))?)",
        re.IGNORECASE,
    )
    match = pattern.search(raw)
    if match:
        start_month, start_day, start_year, end_month, end_day, end_year = match.groups()
        start = _window_date(start_month, start_day, start_year or end_year or "")
        end = _window_date(end_month or start_month, end_day, end_year or start_year or "")
    else:
        # Numeric M/D windows ("8/6 - 9/6", "7/15-9/30") — common in classifieds
        # titles and previously invisible to the term-fit gate.
        numeric = re.search(
            r"\b(\d{1,2})/(\d{1,2})\s*(?:-|–|—|to|through)\s*(\d{1,2})/(\d{1,2})\b", raw)
        if not numeric:
            return None, None
        sm, sd, em, ed = (int(g) for g in numeric.groups())
        if not (1 <= sm <= 12 and 1 <= em <= 12 and 1 <= sd <= 31 and 1 <= ed <= 31):
            return None, None
        try:
            start = date(NEED_START.year, sm, sd)
            end = date(NEED_START.year, em, ed)
        except ValueError:
            return None, None
    if start and end and end < start:
        try:
            end = date(end.year + 1, end.month, end.day)
        except ValueError:
            pass
    return start, end


def normalize_rent_amount(
    rent_text: str,
    title: str,
    description: str,
    *,
    allow_title_fallback: bool = True,
) -> tuple[int, list[str], bool, date | None]:
    amount = parse_money(rent_text)
    if not amount and title and allow_title_fallback:
        # Classifieds commonly lead with the monthly rent ("$3,200 / 1br").
        # Do not grab arbitrary promotional/deposit amounts from later in a title,
        # and do not treat a leading "$1,200 off" concession as monthly rent.
        lead = re.match(r"\s*\$\s*[0-9][0-9,]*(?:\.\d+)?\s*[kKmM]?", title)
        trailer = title[lead.end():lead.end() + 48] if lead else ""
        promotional = bool(re.search(
            r"^\s*(?:off\b|discount\b|credit\b|deposit\b|special\b|concession\b|move[- ]?in\b)",
            trailer,
            re.I,
        ))
        if lead and not promotional:
            amount = parse_money(lead.group(0))
            rent_text = lead.group(0)
    if not amount:
        return 0, [], False, None

    title_cadence = detect_cadence(" ".join([title, description]))
    field_cadence = detect_cadence(rent_text)
    cadence = title_cadence or field_cadence
    notes: list[str] = []
    needs_verification = bool(title_cadence and field_cadence != title_cadence)
    normalized = amount

    if cadence == "weekly":
        normalized = int(round(amount * 4.33))
        notes.append(f"raw rent ${amount}/wk normalized to ${normalized}/mo")
    elif cadence == "nightly":
        normalized = int(round(amount * 30))
        notes.append(f"raw rent ${amount}/night normalized to ${normalized}/mo")

    start, end = parse_stay_window(" ".join([title, description]))
    if start and end:
        days = max(1, (end - start).days)
        notes.append(f"availability window {start.isoformat()} to {end.isoformat()}")
        if days < 30 and not cadence:
            normalized = int(round(amount * 30 / days))
            notes.append(f"raw rent ${amount} total-for-term normalized to ${normalized}/mo")
    return normalized, notes, needs_verification, end


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


def source_from_url(url: str) -> str:
    host = (urlparse(clean(url)).netloc or "").lower()
    for token, source in [
        ("facebook.com", "Facebook Marketplace"),
        ("zillow.com", "Zillow"),
        ("hotpads.com", "HotPads"),
        ("trulia.com", "Trulia"),
        ("realtor.com", "Realtor.com"),
        ("redfin.com", "Redfin"),
        ("apartments.com", "Apartments.com"),
        ("furnishedfinder.com", "Furnished Finder"),
        ("craigslist.org", "Craigslist"),
        ("zumper.com", "Zumper"),
        ("rent.com", "Rent.com"),
        ("reddit.com", "Reddit"),
    ]:
        if token in host:
            return source
    return ""


MARKET_BBOXES = {
    "SF Mission/Valencia": [(37.735, 37.775, -122.430, -122.400)],
    "SF Dogpatch/Potrero/Showplace": [(37.740, 37.775, -122.405, -122.380)],
    "SF SoMa/South Beach/Mission Bay": [(37.770, 37.795, -122.410, -122.380)],
    "SF Hayes/Lower Haight/Castro/Duboce": [(37.750, 37.782, -122.445, -122.420)],
    "SF Sunset/Richmond/Marina/North Beach": [
        (37.760, 37.785, -122.515, -122.445),
        (37.785, 37.810, -122.505, -122.390),
    ],
    "Mountain View": [(37.350, 37.435, -122.120, -122.035)],
    "Sunnyvale": [(37.335, 37.425, -122.065, -121.965)],
    "Santa Clara": [(37.320, 37.430, -122.020, -121.925)],
    "North San Jose": [(37.340, 37.445, -121.950, -121.820)],
    "Palo Alto/Menlo Park": [(37.420, 37.510, -122.230, -122.090)],
    "Redwood City/San Carlos/Belmont": [(37.480, 37.545, -122.310, -122.185)],
    "San Mateo/Burlingame/Millbrae": [(37.545, 37.640, -122.430, -122.270)],
    "Oakland/Berkeley": [(37.765, 37.900, -122.330, -122.220)],
}

OUT_OF_AREA_TERMS = {
    "santa cruz", "sacramento", "stockton", "modesto", "tracy", "vallejo", "santa rosa",
    # Marin / North Bay: no realistic commute to Santa Clara (2026-07-02 board had a
    # Woodacre cottage ranked in an SF market table).
    "woodacre", "san anselmo", "san rafael", "mill valley", "novato", "petaluma",
    "sausalito", "larkspur", "corte madera", "tiburon", "fairfax ca", "napa",
    "vacaville", "fairfield ca", "american canyon", "benicia", "martinez",
}

CITY_MARKET_TERMS = [
    ("mountain view", "Mountain View"),
    ("sunnyvale", "Sunnyvale"),
    ("santa clara", "Santa Clara"),
    ("north san jose", "North San Jose"),
    ("palo alto", "Palo Alto/Menlo Park"),
    ("menlo park", "Palo Alto/Menlo Park"),
    ("redwood city", "Redwood City/San Carlos/Belmont"),
    ("san carlos", "Redwood City/San Carlos/Belmont"),
    ("belmont", "Redwood City/San Carlos/Belmont"),
    ("san mateo", "San Mateo/Burlingame/Millbrae"),
    ("burlingame", "San Mateo/Burlingame/Millbrae"),
    ("millbrae", "San Mateo/Burlingame/Millbrae"),
    ("oakland", "Oakland/Berkeley"),
    ("berkeley", "Oakland/Berkeley"),
    ("emeryville", "Oakland/Berkeley"),
]

SF_NEIGHBORHOOD_MARKETS = [
    (("mission", "valencia", "bernal"), "SF Mission/Valencia"),
    (("dogpatch", "potrero", "showplace"), "SF Dogpatch/Potrero/Showplace"),
    (("soma", "south beach", "mission bay", "4th king", "4th & king"), "SF SoMa/South Beach/Mission Bay"),
    (("hayes", "lower haight", "castro", "duboce", "noe"), "SF Hayes/Lower Haight/Castro/Duboce"),
    (("usf", "panhandle", "nopa", "sunset", "richmond", "marina", "north beach"), "SF Sunset/Richmond/Marina/North Beach"),
    (("nob hill", "russian hill", "pacific heights", "pac heights", "cow hollow"), "SF Sunset/Richmond/Marina/North Beach"),
]


def market_from_point(lat: Any, lng: Any) -> str:
    lat_f = parse_float(lat)
    lng_f = parse_float(lng)
    if lat_f is None or lng_f is None:
        return ""
    for market in MARKET_ORDER:
        for min_lat, max_lat, min_lng, max_lng in MARKET_BBOXES.get(market, []):
            if min_lat <= lat_f <= max_lat and min_lng <= lng_f <= max_lng:
                return market
    return ""


def explicit_market_from_text(text: str) -> str:
    haystack = normalize(text.replace("-", " "))
    if any(term in haystack for term in OUT_OF_AREA_TERMS):
        return "Other Bay Area"
    if ("san francisco" in haystack or re.search(r"\bsf\b", haystack)) and not any(term in haystack for term in NON_SF_EXPLICIT_TERMS):
        for terms, market in SF_NEIGHBORHOOD_MARKETS:
            if any(term in haystack for term in terms):
                return market
        return "SF SoMa/South Beach/Mission Bay"
    for term, market in CITY_MARKET_TERMS:
        if term in haystack:
            return market
    return ""


def has_sf_context(text: str) -> bool:
    haystack = normalize(text.replace("-", " "))
    if "san francisco" in haystack or re.search(r"\bsf\b", haystack):
        return True
    return bool(re.search(r"https?://sfbay\.craigslist\.org/sfc(?:/|$)", text or "", re.IGNORECASE))


def has_non_sf_explicit_term(text: str) -> bool:
    haystack = normalize(text.replace("-", " "))
    return any(term in haystack for term in NON_SF_EXPLICIT_TERMS)


def neighborhood_market_from_text(text: str) -> str:
    haystack = normalize(text)
    if not has_sf_context(text) or has_non_sf_explicit_term(text):
        return ""
    for terms, market in SF_NEIGHBORHOOD_MARKETS:
        if any(term in haystack for term in terms):
            return market
    return ""


def out_of_area_reason(text: str) -> str:
    haystack = normalize(text.replace("-", " "))
    for term in sorted(OUT_OF_AREA_TERMS):
        if term in haystack:
            return "location out of search area"
    return ""


def infer_market(city: str, neighborhood: str, title: str, description: str, lat: Any = "", lng: Any = "", url: str = "") -> str:
    point_market = market_from_point(lat, lng)
    if point_market:
        return point_market
    haystack = normalize(" ".join(str(part or "") for part in [city, neighborhood, title, description, url]))
    explicit = explicit_market_from_text(" ".join(str(part or "") for part in [city, title, url]))
    if explicit:
        return explicit
    nhood_text = " ".join(str(part or "") for part in [city, neighborhood, title, description, url])
    nhood_market = neighborhood_market_from_text(nhood_text)
    if nhood_market:
        return nhood_market
    city_norm = normalize(city)
    if "san francisco" in haystack or city_norm in {"sf", "san francisco"}:
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


NON_SF_EXPLICIT_TERMS = {
    "alameda",
    "berkeley",
    "campbell",
    "cupertino",
    "daly city",
    "davis",
    "east bay",
    "emeryville",
    "fremont",
    "hayward",
    "los altos",
    "los gatos",
    "menlo park",
    "milpitas",
    "mountain view",
    "newark",
    "oakland",
    "palo alto",
    "redwood city",
    "sacramento",
    "san carlos",
    "san jose",
    "san leandro",
    "san luis obispo",
    "san mateo",
    "santa clara",
    "santa cruz",
    "south bay",
    "sunnyvale",
    "union city",
}


def reconcile_market(market: str, city: str, neighborhood: str, title: str, description: str, lat: Any = "", lng: Any = "", url: str = "") -> str:
    """Respect an explicit listing location over the configured search bucket.

    Craigslist section searches are intentionally broad: the SF section can return
    Oakland, Davis, Santa Cruz, and other spillover posts. Keeping the configured
    `market_hint` as-is makes the dashboard over-count "SF 5+" inventory, so only
    use it as a fallback when the listing itself does not name a conflicting city.
    """
    point_market = market_from_point(lat, lng)
    if point_market:
        return point_market
    explicit = explicit_market_from_text(" ".join(str(part or "") for part in [city, title, url]))
    if explicit:
        return explicit
    nhood_text = " ".join(str(part or "") for part in [city, neighborhood, title, description, url])
    nhood_market = neighborhood_market_from_text(nhood_text)
    if nhood_market:
        return nhood_market
    current = clean(market) or infer_market(city, neighborhood, title, description, lat, lng, url)
    city_text = normalize(city)
    if not city_text:
        return current
    city_market = infer_market(city, "", "", "")
    if city_market and city_market != "Other Bay Area":
        return city_market
    if any(term in city_text for term in NON_SF_EXPLICIT_TERMS):
        return "Other Bay Area"
    if current == "Other Bay Area" and city_market != "Other Bay Area":
        return city_market
    return current


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


def parse_beds_count(value: Any) -> int:
    """Bedroom count from the Beds cell in any captured shape: '5', '5 bd',
    '1-3' (range → max), 'studio' → 0."""
    text = normalize(value)
    if not text:
        return 0
    nums = [int(n) for n in re.findall(r"\d{1,2}", text)]
    return max(nums) if nums else 0


def parse_beds_exact(value: Any) -> int:
    """Bedroom count only when the Beds cell states ONE number ('5', '5 bd').
    A range like '0-8 bd' is an apartment complex's unit mix, not a single
    house — splitting its (lowest-unit) rent per bedroom would be nonsense."""
    text = normalize(value)
    nums = re.findall(r"\d{1,2}", text)
    return int(nums[0]) if len(nums) == 1 else 0


def group_value_score(per_person_rent: int) -> int:
    """Value brackets for the 5+ group lane, anchored on GROUP_BUDGET_PER_PERSON."""
    if per_person_rent <= 0:
        return 2
    if per_person_rent <= 1900:
        return 18
    if per_person_rent <= 2200:
        return 17
    if per_person_rent <= 2450:
        return 16
    if per_person_rent <= GROUP_BUDGET_PER_PERSON:
        return 14
    if per_person_rent <= 2900:
        return 10
    if per_person_rent <= 3200:
        return 5
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


# Classifieds sections leak non-housing posts (a "Third floor office in cow hollow"
# sublease ranked in an SF top-5 on 2026-07-02). A title whose SUBJECT is one of
# these spaces — and that contains no housing token — is not a place to live.
# Patterns are subject-shaped ("office space", "floor office") rather than bare
# words so "sublease near office" / "parking included" stay untouched.
NON_HOUSING_PATTERNS = [
    r"\b(?:floor|private|shared|small|large|sunny|quiet|furnished|downtown)\s+office\b",
    r"\boffice\s+(?:space|suite|for|in|available|sublet|sublease)\b",
    r"\bparking\s+(?:space|spot|stall)\b",
    r"\bgarage\s+(?:space|for\s+rent|for\s+lease)\b",
    r"\bstorage\s+(?:space|unit)\b",
    r"\b(?:commercial|retail|desk|warehouse|event|coworking)\s+space\b",
    r"\bsalon\s+(?:suite|space|chair|station)\b",
    r"\bkitchen\s+rental\b",
]
HOUSING_CONTEXT_RE = re.compile(
    r"\b(?:\d+\s*(?:br|bd|bed|beds|bedroom|bedrooms)|bedroom|bedrooms|room|rooms|"
    r"apartment|apt|house|home|flat|condo|townhouse|townhome|cottage|duplex|"
    r"in law|studio|loft|bungalow|casita|unit)\b")

# Reddit search is useful for actual community sublets, but its search feeds also
# return rent-policy debates, moving sales, tickets, cars, and generic housing
# advice. Only offer-shaped titles belong in the listing ledger. Seeker/advice
# posts are intentionally excluded unless they are recruiting roommates for a
# specific shared home.
REDDIT_HOUSING_OFFER_PATTERNS = [
    r"\b(?:sublet|sublease|lease\s+(?:takeover|assignment)|take\s+over\s+(?:my\s+)?lease)\b",
    r"\b(?:room|bedroom|apartment|apt|studio|house|home|unit)\s+(?:is\s+)?(?:for\s+rent|available)\b",
    r"\b(?:available|offering|renting\s+out)\b.{0,70}\b(?:room|bedroom|apartment|apt|studio|house|home|unit)\b",
    r"\b(?:looking|seeking|iso)\b.{0,90}\b(?:roommates?|housemates?|interns?\s+to\s+share|people\s+to\s+share)\b",
    r"\b(?:to\s+)?share\b.{0,50}\b(?:house|apartment|apt|home)\b",
]


def is_housing_offer_title(title: str) -> bool:
    text = normalize(str(title or "").replace("-", " ").replace("/", " "))
    return any(re.search(pattern, text) for pattern in REDDIT_HOUSING_OFFER_PATTERNS)


def non_housing_reason(title: str) -> str:
    text = normalize(str(title or "").replace("-", " ").replace("/", " "))
    if not text or HOUSING_CONTEXT_RE.search(text):
        return ""
    for pattern in NON_HOUSING_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return f"non-housing listing ({match.group(0)})"
    return ""


def apply_non_housing(rows: list[dict[str, str]], run_date: str) -> None:
    for row in rows:
        if row.get("Status") not in ACTIVE_STATUSES | VERIFY_STATUSES:
            continue
        if "reddit" in normalize(row.get("Source", "")) and not is_housing_offer_title(row.get("Title", "")):
            row["Status"] = "Rejected"
            record_lifecycle(row, f"Rejected {run_date}: non-listing Reddit discussion")
            continue
        if parse_beds_count(row.get("Beds")) >= 1:
            continue  # a real bedroom count means it's housing, whatever the title
            # says ('studio' parses to 0 — sapi buckets office posts as studios)
        if HOUSING_CONTEXT_RE.search(normalize(clean(row.get("Notes", "")))):
            continue  # housing words in the description get the benefit of the doubt
        reason = non_housing_reason(row.get("Title", ""))
        if reason:
            row["Status"] = "Rejected"
            record_lifecycle(row, f"Rejected {run_date}: {reason}")


def repair_all_in_floor(rows: list[dict[str, str]]) -> None:
    """All-in cost cannot be lower than base rent; repair legacy promo parses."""
    for row in rows:
        rent = to_int(row.get("Rent", ""))
        all_in = to_int(row.get("All-In Estimate", ""))
        if rent and (not all_in or all_in < rent):
            row["All-In Estimate"] = money_cell(rent)


def repair_source_provenance(rows: list[dict[str, str]]) -> None:
    """Recover portal names for legacy browser captures stored as `manual`."""
    for row in rows:
        if normalize(row.get("Source", "")) not in {"", "manual"}:
            continue
        inferred = source_from_url(row.get("URL", ""))
        if inferred:
            row["Source"] = inferred


def scam_reasons_for_row(row: dict[str, str]) -> list[str]:
    text = normalize(" ".join(clean(row.get(key, "")) for key in ["Title", "Notes", "Lease"]))
    reasons: list[str] = []
    for term in ["state-of-the-art", "whatsapp", "text only", "hold the unit", "no viewing"]:
        if term in text:
            reasons.append(term)
    if "weekly" in text and ("apartment" in text or "1br" in text or "1 bedroom" in text or "residence" in text):
        reasons.append("weekly price in monthly housing context")
    return reasons


def term_end(row: dict[str, str]) -> date | None:
    for piece in re.split(r"\s*;\s*", clean(row.get("Notes", ""))):
        match = re.search(r"availability window \d{4}-\d{2}-\d{2} to (\d{4}-\d{2}-\d{2})", piece)
        if match:
            return parse_date(match.group(1))
    _start, end = parse_stay_window(" ".join(clean(row.get(key, "")) for key in ["Title", "Notes", "Available"]))
    return end


def ends_before_need_window(row: dict[str, str]) -> bool:
    end = term_end(row)
    if end and end < TOP_OVERALL_MIN_END:
        return True
    return 0 < short_stay_days(" ".join(clean(row.get(key, "")) for key in ["Title", "Notes"])) < 30


_WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def short_stay_days(text: str) -> int:
    """Explicit '<N> week/day sublet' duration in days (0 = none stated).
    Catches date-less short stays like 'Two Week Sublet Available' that the
    stay-window parser cannot see."""
    t = normalize(text)
    match = re.search(
        r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*[- ]\s*"
        r"(weeks?|wks?|days?|nights?)\s*[- ]?\s*(?:only\s+)?(sublet|sublease|stay|rental)\b", t)
    if not match:
        match = re.search(
            r"\b(?:sublet|sublease|stay|available)\s+(?:for\s+)?"
            r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*[- ]\s*(weeks?|wks?|days?|nights?)\b", t)
        if not match:
            return 0
        number, unit = match.group(1), match.group(2)
    else:
        number, unit = match.group(1), match.group(2)
    count = _WORD_NUMBERS.get(number, 0) or (int(number) if number.isdigit() else 0)
    if not count:
        return 0
    return count * 7 if unit.startswith("w") else count


def mark_needs_verification(row: dict[str, str], note: str) -> None:
    if row.get("Status") in TERMINAL_STATUSES:
        return
    row["Status"] = "Needs Verification"
    row["Notes"] = merge_notes(row.get("Notes", ""), note)


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


def sf_no_car_first_mile(neighborhood: str, title: str, lat: Any = "", lng: Any = "") -> tuple[int, str]:
    """Bike minutes from an SF listing to its nearest Caltrain station, plus a label.
    Defaults to 15 (a mid bike) when the neighborhood is unknown/generic."""
    station = commute_geo.nearest_caltrain_station(lat, lng)
    if station:
        minutes = int(round(station["distanceKm"] / 12 * 60 + 3))
        return minutes, f"~{minutes}m bike to {station['name']} Caltrain (geo est)"
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
            row.get("Neighborhood", ""), row.get("Title", ""), row.get("Lat", ""), row.get("Lng", "")
        )
        commute = {
            "no_car": SF_TRAIN_PLUS_LAST_MILE + bike,  # bike + Caltrain + last mile
            "car": commute["car"],
            "summary": f"bike+Caltrain ({bike_note})",
        }
    flex, flex_reason = flexibility_score(row.get("Lease", ""), row.get("Title", ""), row.get("Notes", ""))
    beds = parse_beds_exact(row.get("Beds"))
    per_person = int(round(rent / beds)) if (rent and beds >= GROUP_MIN_BEDS) else 0
    if 0 < per_person < 500:
        # A Bay Area whole house can't rent for <$500/bedroom — the price is a
        # per-room price carrying the house's bed count (e.g. $1,295 room in an
        # "8 bd" home). Score it as the room it is, not a $162/person house.
        per_person = 0
    return {
        "rent": rent,
        "market": market,
        "commute": commute,
        "flex": flex,
        "flex_reason": flex_reason,
        "beds": beds,
        "per_person": per_person,
        "value": group_value_score(per_person) if per_person else value_score(rent),
        "quality": quality_score(row.get("Title", ""), row.get("Notes", ""), row.get("Lease", "")),
        "confidence": confidence_score(row),
        "nhood": neighborhood_score(market, row.get("Title", ""), row.get("Notes", "")),
    }


def score_row(row: dict[str, str]) -> dict[str, str]:
    row["Market"] = reconcile_market(
        row.get("Market", ""),
        row.get("City", ""),
        row.get("Neighborhood", ""),
        row.get("Title", ""),
        row.get("Notes", ""),
        row.get("Lat", ""),
        row.get("Lng", ""),
        row.get("URL", ""),
    )
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
    if c["per_person"]:
        car_value = group_value_score(int(round((rent + CAR_MONTHLY_BURDEN) / c["beds"]))) if rent else 2
    else:
        car_value = value_score(rent + CAR_MONTHLY_BURDEN if rent else 0)
    car = car_value + commute_component(commute["car"]) + c["flex"] + c["quality"] + c["confidence"] + c["nhood"]
    overall = max(no_car, car - 3)

    if status in VERIFY_STATUSES:
        overall = max(0, overall - 8)
    if c["market"] == "Other Bay Area" and "location out of search area" not in normalize(row.get("Notes", "")):
        # Legacy rows bucketed out-of-area before ingest-time tagging existed.
        if out_of_area_reason(" ".join(clean(row.get(key, "")) for key in ["City", "Title", "URL", "Notes"])):
            row["Notes"] = merge_notes(row.get("Notes", ""), "location out of search area")
    if "location out of search area" in normalize(row.get("Notes", "")):
        overall = max(0, overall - 18)
    end = term_end(row)
    if end and end < TOP_OVERALL_MIN_END:
        overall = max(0, overall - 25)
        row["Notes"] = merge_notes(row.get("Notes", ""), f"term ends {end.isoformat()} — before need window")
    else:
        stay = short_stay_days(" ".join(clean(row.get(key, "")) for key in ["Title", "Notes"]))
        if 0 < stay < 30:
            overall = max(0, overall - 25)
            row["Notes"] = merge_notes(row.get("Notes", ""), f"short stay ~{stay}d — below need window")

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
    if c["per_person"]:
        reason_bits.append(f"${c['per_person']}/person split {c['beds']} ways")
    if car - 3 > no_car:
        reason_bits.append("car scenario drives rank (costs ~$900/mo)")
    row["Why"] = "; ".join(bit for bit in reason_bits if bit)
    return row


FIT_TIERS = [(70, "Great"), (55, "Good"), (40, "Fair")]


def fit_tier(score: Any) -> str:
    """Organize scores into named fit bands so the board reads as a decision aid
    (Great = tour-worthy now, Good = strong backup, Fair = situational, Weak = filler)."""
    value = to_int(score)
    for floor, label in FIT_TIERS:
        if value >= floor:
            return label
    return "Weak"


def score_breakdown(row: dict[str, str]) -> dict[str, Any]:
    """Per-component fit-score breakdown for the dashboard, computed the same way
    score_row computes the total (terminal rows return an empty dict)."""
    if row.get("Status") in TERMINAL_STATUSES:
        return {}
    c = _components(row)
    return {
        "value": c["value"],
        "flexibility": c["flex"],
        "flexibilityReason": c["flex_reason"],
        "quality": c["quality"],
        "confidence": c["confidence"],
        "neighborhood": c["nhood"],
        "commuteNoCar": commute_component(c["commute"]["no_car"]),
        "commuteCar": commute_component(c["commute"]["car"]),
        "perPersonRent": c["per_person"] or None,
        "fitTier": fit_tier(row.get("Score", "")),
    }


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
    if normalize(source) in {"", "manual"}:
        source = source_from_url(url) or source
    city = first_value(record, ["city", "municipality", "location_city"])
    neighborhood = first_value(record, ["neighborhood", "area", "district"])
    address = first_value(record, ["address", "street", "location"])
    description = first_value(record, ["description", "notes", "body", "summary", "details"])
    lease = first_value(record, ["lease", "lease_term", "term", "availability_terms"])
    available = first_value(record, ["available", "available_date", "move_in", "move_in_date"])
    lat = first_value(record, ["lat", "latitude"])
    lng = first_value(record, ["lng", "lon", "longitude"])
    # Base rent and all-in are sourced from DISTINCT key sets so a capture that
    # provides both keeps the base-vs-all-in spread instead of overwriting one.
    rent_text = first_value(record, ["rent", "price", "monthly_rent", "base_rent"])
    all_in_text = first_value(record, ["all_in", "all_in_estimate", "monthly_total", "estimated_total"])
    rent, rent_notes, rent_needs_verification, _term = normalize_rent_amount(rent_text, title, description)
    all_in, all_in_notes, all_in_needs_verification, _term2 = normalize_rent_amount(
        all_in_text,
        title,
        description,
        allow_title_fallback=False,
    )
    rent_notes.extend(note for note in all_in_notes if note not in rent_notes)
    rent_needs_verification = rent_needs_verification or all_in_needs_verification
    if not rent:
        rent = all_in
    if not all_in:
        all_in = rent
    market = first_value(record, ["market", "bucket"])
    if not market:
        market = infer_market(city, neighborhood, title, " ".join([description, address]), lat, lng, url)
    if not city:
        city = infer_city(market, city, " ".join([title, neighborhood, address, description]))
    market = reconcile_market(market, city, neighborhood, title, " ".join([description, address]), lat, lng, url)
    status = infer_status(first_value(record, ["status", "availability_status"]), rent, url, title)
    if rent_needs_verification and status == "Active":
        status = "Needs Verification"
    key = first_value(record, ["listing_key", "key", "id"])
    if not key:
        key = listing_key(source, title, url, city, neighborhood, rent)
    notes = merge_notes(description, "; ".join(rent_notes))
    if address and normalize(address) not in normalize(notes):
        notes = "; ".join(p for p in [notes, f"addr: {address}"] if p)
    out_reason = out_of_area_reason(" ".join([city, title, url, description, address]))
    if market == "Other Bay Area" and out_reason:
        notes = merge_notes(notes, out_reason)
    for reason in scam_reasons_for_row({"Title": title, "Notes": notes, "Lease": lease}):
        notes = merge_notes(notes, f"scam-risk: {reason}")
        if status == "Active":
            status = "Needs Verification"

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
        "Lat": lat,
        "Lng": lng,
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


def source_family(source: str) -> str:
    """Normalize portal variants so one covered capture can safely age its rows."""
    text = normalize(source)
    for token, family in [
        ("facebook", "facebook"),
        ("craigslist", "craigslist"),
        ("apartments.com", "apartments.com"),
        ("apartments com", "apartments.com"),
        ("furnished finder", "furnished finder"),
        ("rent.com", "rent.com"),
        ("rent com", "rent.com"),
        ("zillow", "zillow"),
        ("zumper", "zumper"),
        ("redfin", "redfin"),
        ("reddit", "reddit"),
        ("rentcast", "rentcast"),
    ]:
        if token in text:
            return family
    return text


def mark_stale(
    rows: list[dict[str, str]],
    run_date: str,
    stale_days: int,
    retire_days: int,
    covered_sources: set[str] | None = None,
) -> None:
    current = parse_date(run_date) or date.today()
    covered_families = {source_family(source) for source in covered_sources or set() if clean(source)}
    for row in rows:
        if covered_sources is not None and source_family(row.get("Source", "")) not in covered_families:
            continue
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
        identifier_is_url = ident_url.startswith(("http://", "https://"))
        for row in rows:
            key_matches = row.get("Listing Key") == ident
            url_matches = identifier_is_url and canonical_url(row.get("URL", "")) == ident_url
            if key_matches or url_matches:
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


def content_fingerprint(row: dict[str, str]) -> str:
    rent = to_int(row.get("All-In Estimate") or row.get("Rent"))
    rent_bucket = int(round(rent / 50.0) * 50) if rent else 0
    title_slug = slug(row.get("Title", ""))[:60]
    beds = normalize(row.get("Beds", ""))
    market = normalize(row.get("Market", ""))
    return "|".join([title_slug, str(rent_bucket), beds, market])


def _first_seen_sort_value(row: dict[str, str]) -> str:
    return clean(row.get("First Seen")) or "9999-12-31"


_TITLE_STOPWORDS = {"a", "an", "the", "in", "of", "for", "with", "and", "or", "to",
                    "at", "on", "by", "w", "available", "now"}


def _title_token_set(title: str) -> set[str]:
    return {tok for tok in slug(title).split("-")
            if tok and not tok.isdigit() and tok not in _TITLE_STOPWORDS}


def _stay_window_fingerprint(row: dict[str, str]) -> str:
    """Same source + market + rent + identical stay window is a repost even when
    the poster reworded the title ('(8/6 - 9/6) Sublet in beautiful NOPA' vs
    '1b/1b Sublet in NOPA (8/6 - 9/6)' held two top-5 slots on 2026-07-02)."""
    start, end = parse_stay_window(" ".join(clean(row.get(key, "")) for key in ["Title", "Available"]))
    if not (start and end):
        return ""
    rent = to_int(row.get("All-In Estimate") or row.get("Rent"))
    if not rent:
        return ""
    rent_bucket = int(round(rent / 50.0) * 50)
    return "|".join([start.isoformat(), end.isoformat(), str(rent_bucket), normalize(row.get("Market", ""))])


def _mark_duplicate_group(group: list[dict[str, str]]) -> None:
    keys = {row.get("Listing Key", "") for row in group}
    if len(group) < 2 or len(keys) < 2:
        return
    winner = sorted(group, key=lambda r: (clean(r.get("Last Seen")), clean(r.get("URL"))), reverse=True)[0]
    first_seen = min((_first_seen_sort_value(row) for row in group), default=winner.get("First Seen", ""))
    if first_seen != "9999-12-31":
        winner["First Seen"] = first_seen
    for row in group:
        if row is winner:
            if row.get("Status") == "Duplicate":
                row["Status"] = "Active"
            continue
        row["Status"] = "Duplicate"
        record_lifecycle(row, f"Duplicate {row.get('Last Seen')}: repost of {winner.get('Listing Key')}")


def apply_content_dedupe(rows: list[dict[str, str]]) -> None:
    same_source: dict[tuple[str, str], list[dict[str, str]]] = {}
    same_window: dict[tuple[str, str], list[dict[str, str]]] = {}
    cross_source: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        if row.get("Status") in TERMINAL_STATUSES:
            continue
        fp = content_fingerprint(row)
        if not fp.strip("|0"):
            continue
        same_source.setdefault((normalize(row.get("Source", "")), fp), []).append(row)
        cross_source.setdefault(fp, []).append(row)
        window_fp = _stay_window_fingerprint(row)
        if window_fp:
            same_window.setdefault((normalize(row.get("Source", "")), window_fp), []).append(row)

    for group in same_source.values():
        _mark_duplicate_group(group)

    for group in same_window.values():
        live = [row for row in group if row.get("Status") not in TERMINAL_STATUSES]
        if len(live) < 2:
            continue
        # Reworded reposts still share most title words; unrelated listings that
        # coincidentally share a window/rent do not — require token overlap.
        anchor = _title_token_set(live[0].get("Title", ""))
        cluster = [live[0]]
        for row in live[1:]:
            tokens = _title_token_set(row.get("Title", ""))
            union = anchor | tokens
            if union and len(anchor & tokens) / len(union) >= 0.34:
                cluster.append(row)
        _mark_duplicate_group(cluster)

    for group in cross_source.values():
        sources = {normalize(row.get("Source", "")) for row in group}
        if len(group) < 2 or len(sources) < 2:
            continue
        canonical = sorted(group, key=lambda r: (clean(r.get("First Seen")), clean(r.get("Listing Key"))))[0]
        for row in group:
            if row is canonical or row.get("Status") in TERMINAL_STATUSES:
                continue
            row["Notes"] = merge_notes(row.get("Notes", ""), f"possible cross-post of {canonical.get('Listing Key')}")


def median(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return int(round((ordered[mid - 1] + ordered[mid]) / 2))


def title_cluster_key(row: dict[str, str]) -> str:
    words = slug(row.get("Title", "")).split("-")
    return "-".join(words[:4])


def apply_scam_quality(rows: list[dict[str, str]]) -> None:
    buckets: dict[tuple[str, str], list[int]] = {}
    clusters: dict[tuple[str, str, int, str], list[dict[str, str]]] = {}
    for row in rows:
        if row.get("Status") not in ACTIVE_STATUSES | VERIFY_STATUSES:
            continue
        rent = to_int(row.get("All-In Estimate") or row.get("Rent"))
        if rent:
            buckets.setdefault((row.get("Market", ""), normalize(row.get("Beds", ""))), []).append(rent)
            clusters.setdefault((normalize(row.get("Source", "")), row.get("Market", ""), rent, title_cluster_key(row)), []).append(row)

    for row in rows:
        if row.get("Status") not in ACTIVE_STATUSES | VERIFY_STATUSES:
            continue
        for reason in scam_reasons_for_row(row):
            mark_needs_verification(row, f"scam-risk: {reason}")
        rent = to_int(row.get("All-In Estimate") or row.get("Rent"))
        med = median(buckets.get((row.get("Market", ""), normalize(row.get("Beds", ""))), []))
        if rent and med and len(buckets.get((row.get("Market", ""), normalize(row.get("Beds", ""))), [])) >= 2 and rent < med * 0.4:
            mark_needs_verification(row, f"scam-risk: rent below 40% of {row.get('Market')} {row.get('Beds') or 'unknown beds'} median")

    for group in clusters.values():
        if len(group) < 3:
            continue
        for row in group:
            mark_needs_verification(row, "scam-risk: repeated same-poster rent/title cluster")


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
    # Header-derived so an added/removed column in RANK_HEADERS cannot silently
    # misread the previous board (delta continuity relies on this parser).
    title_idx = 7
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
        if cells and cells[0] == "Rank" and "Listing" in cells:
            title_idx = cells.index("Listing")
            continue
        if not cells or not re.fullmatch(r"\d+", cells[0]):
            continue
        rank = int(cells[0])
        url = ""
        match = re.search(r"\((https?://[^)]+)\)", cells[-1])
        if match:
            url = canonical_url(match.group(1))
        title = cells[title_idx] if len(cells) > title_idx else ""
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


RANK_HEADERS = ["Rank", "Delta", "Score", "Fit", "No-Car", "Car", "Rent", "Market", "Listing", "Lease", "Commute", "Why", "Status", "Link"]
RANK_SEPARATOR = "| ---: | --- | ---: | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- | --- | --- |"


def ranking_table(rows: list[dict[str, str]], previous: dict[tuple[str, str], int], scope: str) -> list[str]:
    lines = [
        "| " + " | ".join(RANK_HEADERS) + " |",
        RANK_SEPARATOR,
    ]
    for index, row in enumerate(rows, start=1):
        cells = {
            "Rank": str(index),
            "Delta": delta_cell(previous, scope, row, index),
            "Score": row.get("Score", ""),
            "Fit": fit_tier(row.get("Score", "")),
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
        RANK_SEPARATOR,
    ]


def build_rankings(rows: list[dict[str, str]], run_date: str) -> None:
    previous = parse_previous_rankings()
    active = sorted(active_rows(rows), key=rank_sort_key)
    needs = sorted(needs_rows(rows), key=rank_sort_key)
    replaced = sorted(replaced_rows(rows), key=lambda r: (r.get("Last Seen", ""), r.get("Market", ""), r.get("Title", "")), reverse=True)

    overall_top = [row for row in active if not ends_before_need_window(row)][:5]
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

    atomic_write_text(RANKINGS_MD, "\n".join(lines).rstrip() + "\n")


def ingest(
    inputs: list[Path],
    default_source: str,
    run_date: str,
    rows: list[dict[str, str]],
) -> tuple[int, int, list[str], set[str]]:
    by_key = {row.get("Listing Key", ""): row for row in rows if row.get("Listing Key")}
    by_url = {canonical_url(row.get("URL", "")): row for row in rows if canonical_url(row.get("URL", ""))}
    created = 0
    updated = 0
    warnings: list[str] = []
    covered_sources: set[str] = set()
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
            if incoming.get("Status") != "Source Blocked" and incoming.get("Source"):
                covered_sources.add(incoming["Source"])
            key = incoming.get("Listing Key", "")
            url = canonical_url(incoming.get("URL", ""))
            explicit_key = bool(first_value(record, ["listing_key", "key", "id"]))
            # An explicit upstream key identifies a unit/floorplan even when a
            # property portal reuses one building URL for every result. Only use
            # URL fallback for records that lack their own stable identity.
            existing = by_key.get(key) or (by_url.get(url) if url and not explicit_key else None)
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
    return created, updated, warnings, covered_sources


def serialized_tracker_update(func):
    """Serialize the short ledger read/modify/write transaction across agents."""
    @functools.wraps(func)
    def wrapped(*args, **kwargs):
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOCK_FILE.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                return func(*args, **kwargs)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return wrapped


class HousingConductorBusy(RuntimeError):
    """Raised when another capture-to-health housing run owns the conductor lock."""


@contextmanager
def conductor_lock(*, blocking: bool = False):
    """Serialize the full housing transaction, not only the ledger write.

    `run.py` takes this non-blocking so two browser conductors never compete.
    Exporters may take it in blocking mode to wait for a coherent tracker/health
    snapshot after a run already in progress.
    """
    CONDUCTOR_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CONDUCTOR_LOCK_FILE.open("a+", encoding="utf-8") as lock:
        flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
        try:
            fcntl.flock(lock.fileno(), flags)
        except BlockingIOError as exc:
            raise HousingConductorBusy(
                f"another housing conductor is active (lock: {CONDUCTOR_LOCK_FILE})"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


@serialized_tracker_update
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
    decay_scope: str = "covered",
    observed_sources: set[str] | None = None,
) -> dict[str, Any]:
    run_date = run_date or today_iso()
    inputs = inputs or []
    rows = load_listing_rows()
    created = updated = 0
    warnings: list[str] = []
    covered_sources: set[str] = set(observed_sources or set())
    if inputs and not refresh_only:
        created, updated, warnings, ingested_sources = ingest(inputs, default_source, run_date, rows)
        # A conductor-supplied observation set has already checked every lane in
        # a source family. Do not let one successfully ingested partial lane
        # bypass that check and age unrelated inventory from the same portal.
        if observed_sources is None:
            covered_sources.update(ingested_sources)

    apply_marks(rows, marks or [], run_date)
    mark_expired(rows, expire_keys or [], expire_urls or [], run_date)
    repair_all_in_floor(rows)
    repair_source_provenance(rows)
    apply_non_housing(rows, run_date)
    if decay_scope not in {"all", "covered", "none"}:
        raise ValueError(f"unknown decay_scope {decay_scope!r}")
    decay_sources = None if decay_scope == "all" else covered_sources
    if decay_scope != "none" and not refresh_only:
        mark_stale(rows, run_date, stale_days, retire_days, decay_sources)
    apply_content_dedupe(rows)
    apply_scam_quality(rows)
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
        "decay_scope": decay_scope,
        "sources_covered": sorted(covered_sources),
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
    parser.add_argument("--decay-scope", choices=("covered", "all", "none"), default="covered",
                        help="Age only sources observed by this run (default), every source, or none")
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
        decay_scope=args.decay_scope,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
