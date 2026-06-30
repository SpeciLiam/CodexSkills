#!/usr/bin/env python3
"""Shared origin-address logic for the Google-Maps commute recompute.

Both `recompute_commutes.py` (which calls Google) and `export_housing_data.py`
(which reads the resulting cache) build a listing's geocodable origin string and
its cache key from THIS module, so the two can never drift. Listings carry only a
messy `city` (often itself a neighborhood, e.g. "Nob hill, San Francisco, CA" or
"Castro / Upper Market"), an optional `neighborhood`, and a `market`. We distill
those into one Google-geocodable address and a normalized key for de-duplication.

Stdlib only.
"""
from __future__ import annotations

import re

# Office destinations the recompute routes every origin to. Keys MUST match the
# office labels emitted by export_housing_data.OFFICES / officeCommutes.
HACKERRANK = "HackerRank (Santa Clara)"
GOOGLE_SF = "Google (San Francisco)"
OFFICE_ADDRESSES = {
    HACKERRANK: "2350 Mission College Blvd #750, Santa Clara, CA 95054",
    # Google's SF office (Hills Plaza, Embarcadero — Caltrain + BART reachable).
    GOOGLE_SF: "345 Spear Street, San Francisco, CA 94105",
}
# The "primary" office whose transit/drive populate the listing's headline
# commuteMin/carCommuteMin (mirrors housing_pipeline's Santa-Clara COMMUTE_DEFAULTS
# and the always-HackerRank Liam profile).
PRIMARY_OFFICE = HACKERRANK


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _first_alt(s: str) -> str:
    """A geocoder dislikes "a / b" combo localities; keep the first alternative."""
    s = _clean(s)
    return s.split("/")[0].strip() if "/" in s else s


def _has_locality(s: str) -> bool:
    """True if `s` carries a real place name (>=3 letters), not just digits/punct
    like a stray "1050" street fragment."""
    return bool(re.search(r"[A-Za-z]{3,}", s or ""))


# Unambiguously NON-SF localities that the scraper sometimes mis-buckets into an
# SF market. When the locality leads with one of these we anchor ", CA" (trust the
# city) instead of forcing "San Francisco". Deliberately EXCLUDES names that are
# real SF neighborhoods too (Richmond, Sunset, Marina, Bayview, Portola, ...), which
# in an SF market really do mean the SF district.
DISTINCT_CITIES = {
    "berkeley", "oakland", "alameda", "san leandro", "hayward", "fremont",
    "concord", "walnut creek", "antioch", "tracy", "vallejo", "pleasanton", "dublin",
    "sunnyvale", "santa clara", "mountain view", "palo alto", "menlo park", "east palo alto",
    "los altos", "cupertino", "campbell", "los gatos", "saratoga", "milpitas", "morgan hill",
    "gilroy", "san jose", "redwood city", "san carlos", "belmont", "san mateo", "foster city",
    "burlingame", "millbrae", "san bruno", "south san francisco", "daly city", "colma",
    "brisbane", "pacifica", "santa rosa", "petaluma", "novato", "san rafael", "caspar",
    "prunedale", "santa cruz", "watsonville", "redwood shores",
}


def _is_distinct_city(base: str) -> bool:
    lead = _clean(base).split(",")[0].lower()
    return any(lead == c or lead.startswith(c + " ") for c in DISTINCT_CITIES)


def _is_sf_market(market: str) -> bool:
    # The scraper emits both neighborhood buckets ("SF SoMa/...") and a bare "SF".
    market = market or ""
    return market == "SF" or market.startswith("SF ")


def _market_center(market: str) -> str:
    """Fallback geocodable center when a listing's locality is blank/garbage."""
    if _is_sf_market(market):
        return "San Francisco, CA"
    lead = _first_alt(market or "")
    return f"{lead}, CA" if _has_locality(lead) else "San Jose, CA"


def origin_address(market: str, city: str, neighborhood: str) -> str:
    """Best Google-geocodable address for a listing's (market, city, neighborhood).

    A city/neighborhood that is ALREADY a fully-anchored address ("..., CA") is
    trusted verbatim — the explicit place beats the (sometimes mis-bucketed)
    market region. Otherwise SF markets anchor to "..., San Francisco, CA" and the
    rest to "..., CA". Garbage localities (no real place name) fall back to the
    market center. Always returns a non-empty geocodable string."""
    city = _first_alt(city)
    nb = _first_alt(neighborhood)
    market = market or ""
    sf = _is_sf_market(market)

    base = city
    if nb and nb.lower() not in city.lower():
        base = f"{nb}, {city}" if city else nb
    base = base.strip().rstrip(",").strip()
    low = base.lower()

    # Already anchored ("..., CA" / "California") -> trust the explicit place as-is.
    if ", ca" in low or "california" in low:
        return base if _has_locality(base) else _market_center(market)
    if not _has_locality(base):
        return _market_center(market)
    # SF market but the locality names a different real city -> trust the city.
    if sf and _is_distinct_city(base):
        return f"{base}, CA"
    return f"{base}, San Francisco, CA" if sf else f"{base}, CA"


def origin_key(market: str, city: str, neighborhood: str) -> str:
    """Normalized de-dup key for an origin (case/space-insensitive address)."""
    return _clean(origin_address(market, city, neighborhood)).lower()
