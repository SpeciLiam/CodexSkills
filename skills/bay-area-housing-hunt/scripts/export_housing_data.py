#!/usr/bin/env python3
"""Export the housing ledger into housing-visualizer/src/data/housing-data.json.

Reuses housing_pipeline (ledger load) + sync_housing_to_notion (rank/commute logic)
so the website, the Notion mirror, and the markdown board all agree. Stdlib only.
Run directly, or via the visualizer's `npm run dev/build`.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import housing_pipeline as hp  # noqa: E402
import sync_housing_to_notion as sync  # noqa: E402
import commute_origins as co  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "housing-visualizer" / "src" / "data" / "housing-data.json"

# Real Google-Maps commute cache (durations only; written by recompute_commutes.py).
# Reading it here costs nothing — Google was billed once when the cache was built —
# and lets every export ship real per-office routing instead of the static tables.
COMMUTE_CACHE = SCRIPT_DIR / "commute_cache.json"
# Acceptance envelope (one-way minutes). A geocode error makes the DRIVE absurd, so the
# primary-office drive is the geocode-sanity gate: once it is in range we trust the
# origin geocoded to a real point, and a transit FROM that same point is therefore real
# too — even when it is huge (e.g. Santa Cruz ~483m: genuinely terrible transit, not a
# bug). So transit is accepted across a wide band rather than rejected-and-clamped, which
# is what used to fabricate a fast 43m transit for those far listings. The low floor
# admits genuine sub-10m inner-city transit; the high ceiling still drops pure artifacts.
_DRIVE_OK = (3, 180)
_TRANSIT_OK = (2, 600)

# Pre-configured offices (no manual input). HackerRank commute reuses the board's
# Santa Clara table; Google SF (downtown / 345 Spear St, Caltrain + BART reachable)
# uses the hand table below. (transit_min, drive_min) per market. Swap in a Maps API
# later for exact door-to-door routing.
HACKERRANK = "HackerRank (Santa Clara)"
GOOGLE_SF = "Google (San Francisco)"
OFFICES = [HACKERRANK, GOOGLE_SF]

GOOGLE_SF_COMMUTE = {
    "SF SoMa/South Beach/Mission Bay": (12, 8),
    "SF Dogpatch/Potrero/Showplace": (18, 12),
    "SF Mission/Valencia": (20, 15),
    "SF Hayes/Lower Haight/Castro/Duboce": (22, 15),
    "SF Sunset/Richmond/Marina/North Beach": (32, 22),
    "Oakland/Berkeley": (35, 30),
    "San Mateo/Burlingame/Millbrae": (42, 30),
    "Redwood City/San Carlos/Belmont": (48, 35),
    "Palo Alto/Menlo Park": (58, 42),
    "Mountain View": (70, 52),
    "Sunnyvale": (75, 55),
    "Santa Clara": (80, 60),
    "North San Jose": (85, 62),
    "Other Bay Area": (60, 45),
}


HOUSEHOLD_FILE = SCRIPT_DIR / "household.json"


LIAM_DEFAULT = {"name": "Liam", "company": "HackerRank", "address": "2350 Mission College Blvd #750, Santa Clara, CA 95054", "arrival": "09:00", "car": True, "bike": True}


def _norm_person(p: dict) -> dict:
    return {
        "name": p.get("name", ""), "company": p.get("company", ""), "address": p.get("address", ""),
        "arrival": p.get("arrival", "09:00"), "car": p.get("car", True), "bike": p.get("bike", True),
    }


def load_household() -> dict:
    """The shared roommate config (scripts/household.json) — seeds the dashboard's two
    profiles. Returns {'liam': <person>, 'group': [<person>...]}. Solo HackerRank fallback."""
    out = {"liam": dict(LIAM_DEFAULT), "group": [dict(LIAM_DEFAULT)]}
    try:
        cfg = json.loads(HOUSEHOLD_FILE.read_text(encoding="utf-8"))
        liam_people = ((cfg.get("liam") or {}).get("people")) or []
        group_people = ((cfg.get("group") or {}).get("people")) or cfg.get("people") or []  # back-compat
        if liam_people and isinstance(liam_people[0], dict):
            out["liam"] = _norm_person(liam_people[0])
        group = [_norm_person(p) for p in group_people if isinstance(p, dict)]
        if group:
            out["group"] = group
    except (OSError, json.JSONDecodeError, TypeError, AttributeError):
        pass
    return out


def office_commutes(market: str) -> dict:
    hr = hp.COMMUTE_DEFAULTS.get(market, hp.COMMUTE_DEFAULTS["Other Bay Area"])
    sf = GOOGLE_SF_COMMUTE.get(market, GOOGLE_SF_COMMUTE["Other Bay Area"])
    return {
        HACKERRANK: {"transit": hr["no_car"], "drive": hr["car"]},
        GOOGLE_SF: {"transit": sf[0], "drive": sf[1]},
    }


def load_commute_cache() -> dict:
    """origin_key -> cache entry (or {} if the cache is missing/unbuilt)."""
    try:
        return (json.loads(COMMUTE_CACHE.read_text(encoding="utf-8")) or {}).get("origins", {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return {}


def _ok(v, lo_hi) -> bool:
    return isinstance(v, (int, float)) and lo_hi[0] <= v <= lo_hi[1]


def apply_google_commute(listing: dict, cache: dict) -> bool:
    """Overwrite a listing's office routing with real Google numbers when we have a
    trustworthy cache entry for its origin. Per-field gating keeps a static fallback
    for any value that looks like a geocode error. Returns True if anything changed."""
    entry = cache.get(co.origin_key(listing.get("market", ""), listing.get("city", ""),
                                    listing.get("neighborhood", "")))
    if not entry:
        return False
    offices = entry.get("office") or {}
    prim = offices.get(co.PRIMARY_OFFICE) or {}
    # Origin is only trusted when its primary-office drive is in range (geocode sanity).
    if not _ok(prim.get("drive"), _DRIVE_OK):
        return False

    oc = dict(listing.get("officeCommutes") or {})
    for label, rec in offices.items():
        cell = dict(oc.get(label) or {})
        if _ok(rec.get("transit"), _TRANSIT_OK):
            cell["transit"] = round(rec["transit"])  # real google transit, any magnitude
        if _ok(rec.get("drive"), _DRIVE_OK):
            cell["drive"] = round(rec["drive"])
        oc[label] = cell
    listing["officeCommutes"] = oc

    # Legacy scalar fields (Notion mirror / markdown board) read FROM the same primary
    # cell so they can never diverge from what the dashboard shows.
    sc = oc.get(co.PRIMARY_OFFICE) or {}
    listing["carCommuteMin"] = sc.get("drive")
    listing["commuteMin"] = sc.get("transit")
    if _ok(entry.get("homeTransit"), _TRANSIT_OK):
        listing["commuteHomeMin"] = round(entry["homeTransit"])
    # Provenance-honest summary: only claim a Google transit/route when it was accepted.
    transit_google = _ok(prim.get("transit"), _TRANSIT_OK)
    summ = (prim.get("transitSummary") or "").strip()
    dr = sc.get("drive")
    if transit_google:
        listing["howToGetThere"] = (
            f"Transit ~{sc.get('transit')}m" + (f" via {summ}" if summ else "") + f" · drive ~{dr}m (Google Maps)"
        )
    else:
        listing["howToGetThere"] = f"Drive ~{dr}m (Google Maps; transit estimated)"
    listing["commuteSource"] = "google"
    return True


def num(value: str):
    n = hp.to_int(value)
    return n if value not in (None, "") and n != 0 else (0 if value in ("0",) else None)


# A 1-2 digit bedroom count (optionally a tight range like "1-2" / "2/3") immediately
# before a bedroom token (EN/ES/ZH). The negative lookbehind stops a price digit gluing
# in: "$1,500 / 1br" must read 1, not 500. Bathrooms ("ba"/"baño"/"卫") never match.
_BED_RE = re.compile(
    r"(?<![\d,.$])(\d{1,2})(?:\s?[-/]\s?(\d{1,2}))?\s*(?:bd|br|beds?|bedrooms?|hab\b|habitaci\w*|室|卧)",
    re.I,
)
# Spelled-out counts ("Three Bedrooms for Rent"); 'studio' is handled separately as 0.
_WORD_BEDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
              "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_WORD_BED_RE = re.compile(r"\b(" + "|".join(_WORD_BEDS) + r")\b[\s-]+(?:bed|bd|br)", re.I)
_BED_MAX = 12  # a parsed "bedroom" above this is a misparse (price, cross-street, etc.)

SF_NEIGHBORHOOD_HINTS = {
    "bernal",
    "castro",
    "dogpatch",
    "duboce",
    "embarcadero",
    "excelsior",
    "glen park",
    "haight",
    "hayes",
    "ingleside",
    "inner richmond",
    "inner sunset",
    "lower haight",
    "marina",
    "mission bay",
    "mission district",
    "nob hill",
    "noe valley",
    "north beach",
    "outer mission",
    "outer richmond",
    "outer sunset",
    "pac heights",
    "pacific heights",
    "potrero",
    "richmond",
    "russian hill",
    "soma",
    "south beach",
    "sunset",
    "tenderloin",
}


def source_tier(source: str) -> str:
    text = hp.normalize(source)
    if "craigslist" in text or "zumper" in text:
        return "headless"
    if any(term in text for term in ["facebook", "zillow", "apartments", "furnished"]):
        return "browser"
    if "reddit" in text or "rentcast" in text:
        return "api"
    return "manual"


def source_health(source: str) -> str:
    text = hp.normalize(source)
    if "zillow" in text:
        return "human-verification-gated for exact 5+"
    if "apartments" in text:
        return "browser card scrape; 5+ route may label as 4+"
    if "facebook" in text:
        return "logged-in browser only"
    if "craigslist" in text:
        return "structured headless; section spillover possible"
    if "zumper" in text:
        return "structured headless SSR"
    return "capture source"


def unit_scope(row: dict, parsed_beds) -> str:
    text = hp.normalize(" ".join([row.get("Title", ""), row.get("Beds", ""), row.get("Lease", ""), row.get("Notes", "")]))
    if any(term in text for term in ["roommate", "shared room", "private room", "single bedroom", "room in", "one bed in"]):
        return "room"
    if parsed_beds is not None and parsed_beds >= 2 and any(term in text for term in ["house for rent", "apartment for rent", "entire", "whole house", "unit "]):
        return "whole"
    return "unknown"


def location_meta(row: dict) -> dict:
    market = row.get("Market", "")
    city = row.get("City", "")
    neighborhood = row.get("Neighborhood", "")
    title = row.get("Title", "")
    city_norm = hp.normalize(city)
    text = hp.normalize(" ".join([city, neighborhood, title, row.get("Notes", "")]))
    sf_market = market == "SF" or market.startswith("SF ")
    city_says_other = bool(city_norm and any(term in city_norm for term in hp.NON_SF_EXPLICIT_TERMS))
    strict_sf = "san francisco" in city_norm
    sf_neighborhood = any(term in text for term in SF_NEIGHBORHOOD_HINTS)
    exact_sf = sf_market and not city_says_other and (strict_sf or sf_neighborhood or not city_norm)
    if sf_market and city_says_other:
        confidence = "spillover"
    elif strict_sf:
        confidence = "city"
    elif sf_market and sf_neighborhood:
        confidence = "neighborhood"
    elif sf_market:
        confidence = "bucket"
    else:
        confidence = "city" if city_norm else "unknown"
    return {
        "sfMarket": sf_market,
        "exactSf": exact_sf,
        "strictSfCity": strict_sf,
        "locationConfidence": confidence,
    }


def _parse_beds(text: str):
    """Whole-unit bedroom count from a beds/title string. Uses the FIRST explicit bedroom
    mention — the advertised unit (so "1 Bed in a 2 Bed apt" -> 1) — taking MAX only within
    a single range token ("1-2 bd" -> 2). Reads spelled-out counts ("Three Bedrooms" -> 3);
    'studio' -> 0; None when there's no bedroom signal (e.g. a bare room share)."""
    t = (text or "").lower()
    if not t.strip():
        return None
    m = _BED_RE.search(t)
    if m:
        cands = [int(g) for g in m.groups() if g is not None and int(g) <= _BED_MAX]
        if cands:
            return max(cands)
    w = _WORD_BED_RE.search(t)
    if w:
        return _WORD_BEDS[w.group(1)]
    if ("studio" in t) or ("estudio" in t) or ("monoambiente" in t):
        return 0
    return None


def beds_num(beds: str, title: str):
    """Bedroom count for the unit. The scraper's Beds bucket is often wrong (a room in a
    5-bed house tagged '5 bd', or a price misparsed), so when the TITLE states an explicit
    count that CONFLICTS with the Beds column, the poster's title wins. Otherwise the Beds
    column (authoritative for Zumper/Zillow) is used, then the title as a fallback."""
    b = _parse_beds(beds)
    t = _parse_beds(title)
    if b is not None and t is not None and b != t:
        return t  # the title is what's advertised; the structured bucket is unreliable
    return b if b is not None else t


def export() -> dict:
    rows = hp.load_listing_rows()
    overall_ranks, city_ranks = sync.compute_ranks(rows)

    listings = []
    for row in rows:
        lk = row.get("Listing Key", "")
        how, nc_to, nc_from, car_to = sync.commute_fields(row.get("Commute", ""), row.get("Market", ""))
        parsed_beds = beds_num(row.get("Beds", ""), row.get("Title", ""))
        loc = location_meta(row)
        listings.append({
            "listingKey": lk,
            "title": row.get("Title", ""),
            "market": row.get("Market", ""),
            "city": row.get("City", ""),
            "neighborhood": row.get("Neighborhood", ""),
            # The exact geocodable origin used for this listing's cached commute, so the
            # browser's live "Optimal departure" routes from the SAME point (no divergence).
            "commuteOrigin": co.origin_address(row.get("Market", ""), row.get("City", ""), row.get("Neighborhood", "")),
            "rent": num(row.get("Rent", "")),
            "allIn": num(row.get("All-In Estimate", "")),
            "beds": row.get("Beds", ""),
            "bedsNum": parsed_beds,
            "isFivePlus": parsed_beds is not None and parsed_beds >= 5,
            "unitScope": unit_scope(row, parsed_beds),
            "baths": row.get("Baths", ""),
            "lease": row.get("Lease", ""),
            "available": row.get("Available", ""),
            "status": row.get("Status", ""),
            "score": hp.to_int(row.get("Score", "")),
            "noCarScore": hp.to_int(row.get("No-Car Score", "")),
            "carScore": hp.to_int(row.get("Car Score", "")),
            "overallRank": overall_ranks.get(lk),
            "cityRank": city_ranks.get(lk),
            "commuteMin": nc_to,
            "commuteHomeMin": nc_from,
            "carCommuteMin": car_to,
            "howToGetThere": how,
            "officeCommutes": office_commutes(row.get("Market", "")),
            "why": sync.hp.clean(row.get("Why", "")),
            "source": row.get("Source", ""),
            "sourceTier": source_tier(row.get("Source", "")),
            "sourceHealth": source_health(row.get("Source", "")),
            **loc,
            "firstSeen": row.get("First Seen", ""),
            "lastSeen": row.get("Last Seen", ""),
            "url": row.get("URL", ""),
            "notes": row.get("Notes", ""),
        })

    # Overlay real Google-Maps routing where the cache covers a listing's origin.
    cache = load_commute_cache()
    google_n = 0
    for x in listings:
        x.setdefault("commuteSource", "static")
        if apply_google_commute(x, cache):
            google_n += 1

    active = [x for x in listings if x["status"] in hp.ACTIVE_STATUSES]
    needs = [x for x in listings if x["status"] == "Needs Verification"]
    replaced = [x for x in listings if x["status"] in hp.REPLACED_STATUSES]
    markets = sorted({x["market"] for x in active if x["market"]}, key=hp.market_sort_key)
    five_plus = [x for x in active if x.get("isFivePlus")]
    sf_market_five_plus = [x for x in five_plus if x.get("sfMarket")]
    strict_sf_five_plus = [x for x in five_plus if x.get("strictSfCity")]
    exact_sf_five_plus = [x for x in five_plus if x.get("exactSf")]
    _hh = load_household()

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total": len(listings),
            "active": len(active),
            "needsVerification": len(needs),
            "replaced": len(replaced),
            "markets": len(markets),
            "googleCommutes": google_n,
            "activeFivePlus": len(five_plus),
            "sfMarketFivePlus": len(sf_market_five_plus),
            "strictSfCityFivePlus": len(strict_sf_five_plus),
            "exactSfFivePlus": len(exact_sf_five_plus),
        },
        # Ordered markets first, then any market present in the data but missing from
        # MARKET_ORDER (e.g. a bare "SF" / "South Bay") so the Area dropdown can reach them.
        "marketOrder": [m for m in hp.MARKET_ORDER if m in markets] + sorted(set(markets) - set(hp.MARKET_ORDER)),
        "offices": OFFICES,
        "defaultPeople": _hh["group"],
        "defaultLiam": _hh["liam"],
        "listings": listings,
    }


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = export()
    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), **data["stats"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
