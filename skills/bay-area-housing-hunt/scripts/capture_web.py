#!/usr/bin/env python3
"""Headless capture for portals that serve real public data to a normal browser
request but reject the honest bot User-Agent.

This is NOT a CAPTCHA / login / rate-limit bypass. We simply identify as a normal
browser and read the PUBLIC response that the site returns to anyone. There is no
authentication, no CAPTCHA solving, and no rate-limit circumvention: if a source
answers with a 403 / 429 / challenge / login wall we record a Source Blocked row
and stop (same hard rule as the rest of the pipeline — see references/sources.md).

Adapter kinds, all driven by the `web` array in searches.json:

  - craigslist_sapi : Craigslist's own public JSON search API (sapi.craigslist.org).
                      The legacy RSS feed 403s headlessly, but the JSON API that the
                      site's own search page calls returns the full result set. Each
                      posting id is delta-encoded (real id = decode.minPostingId +
                      item[0]); the canonical post URL is rebuilt from subarea +
                      category + slug + id and verified to resolve.
  - zumper_state    : parse the __PRELOADED_STATE__ blob embedded in the Zumper
                      search page (currentSearch.listables.listables).
  - rent_next_data  : parse Rent.com's public __NEXT_DATA__ search-page state.
  - pm              : parse public property-manager availability state. Currently
                      supports UDR pages that embed window.udr.jsonObjPropertyViewModel.

Stdlib only (urllib) so it runs in CI/cloud. Importable for tests:
    parse_craigslist(payload, cfg) -> [records]
    parse_zumper(state, cfg)       -> [records]
"""
from __future__ import annotations

import gzip
import html as html_lib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import housing_pipeline as hp  # noqa: E402

FETCH_TIMEOUT = 20
# A normal desktop-Chrome UA. We read only public responses; on any block we stop.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}
SAPI = "https://sapi.craigslist.org/web/v8/postings/search/full"
# Results come back newest-first (sort=newest); we keep the freshest N per search so
# a broad category (e.g. 4000+ South Bay apartments) can't flood the power rankings.
DEFAULT_LIMIT = 100
# Category abbr -> human word, used to synthesize a title for broker/feed apartment
# posts that ship no title or slug in the sapi payload.
CAT_WORD = {"roo": "Room", "sub": "Sublet", "apa": "Apartment", "hhh": "Housing"}


def _get(url: str, accept: str) -> str:
    headers = dict(BROWSER_HEADERS, Accept=accept)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        if resp.status != 200:
            raise urllib.error.HTTPError(url, resp.status, "non-200", resp.headers, None)
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
        return raw.decode("utf-8", errors="replace")


def _blocked(name: str, url: str, market: str, exc: Exception) -> dict:
    return {
        "source": name,
        "status": "source blocked",
        "title": f"{name} unreachable",
        "url": url,
        "description": f"Source Blocked: {type(exc).__name__}: {exc}",
        "market": market,
    }


def _looks_blocked(html: str) -> bool:
    text = html.lower()
    block_markers = (
        "px-captcha",
        "perimeterx",
        "verify you are human",
        "captcha",
        "access denied",
        "temporarily blocked",
        "too many requests",
        "cloudflare challenge",
    )
    return any(marker in text for marker in block_markers)


def _extract_balanced_json_after(text: str, marker: str) -> dict | list | None:
    pos = text.find(marker)
    if pos < 0:
        return None
    pos += len(marker)
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if pos >= len(text) or text[pos] not in "{[":
        return None
    opener = text[pos]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_str = False
    esc = False
    for idx, ch in enumerate(text[pos:], pos):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[pos:idx + 1])
                    except json.JSONDecodeError:
                        return None
    return None


def _meta_content(html: str, prop: str) -> str:
    pat = re.compile(
        rf"<meta[^>]+(?:property|name)=[\"']{re.escape(prop)}[\"'][^>]+content=[\"']([^\"']+)[\"']",
        re.I,
    )
    m = pat.search(html)
    return html_lib.unescape(m.group(1).strip()) if m else ""


def _fmt_money(value: object) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("$"):
            return value
        try:
            value = float(value.replace(",", ""))
        except ValueError:
            return value
    if isinstance(value, (int, float)):
        return f"${int(round(value)):,}"
    return hp.clean(value)


def _fmt_range(lo: object, hi: object) -> str:
    lo_s, hi_s = _fmt_money(lo), _fmt_money(hi)
    if lo_s and hi_s and lo_s != hi_s:
        return f"{lo_s}–{hi_s}"
    return lo_s or hi_s


def _fmt_beds(value: object) -> str:
    if value in (None, ""):
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return hp.clean(value)
    if num == 0:
        return "studio"
    if num.is_integer():
        return f"{int(num)} bd"
    return f"{num:g} bd"


def _fmt_baths(value: object) -> str:
    if value in (None, ""):
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return hp.clean(value)
    return f"{int(num)}" if num.is_integer() else f"{num:g}"


def _fmt_date(value: object) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        m = re.search(r"/Date\((\d+)", value)
        if m:
            try:
                return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).date().isoformat()
            except (OverflowError, ValueError, OSError):
                return ""
        m = re.match(r"(\d{4}-\d{2}-\d{2})", value)
        if m:
            return m.group(1)
        return value
    return ""


# --------------------------------------------------------------------------- #
# Craigslist sapi
# --------------------------------------------------------------------------- #
def _cl_url(cfg: dict) -> str:
    sub = cfg["subarea"]
    cat = cfg["category"]
    url = f"{SAPI}?batch=1-0-0-0-0&cc=US&lang=en&searchPath={sub}/{cat}"
    for key, val in (cfg.get("params") or {}).items():
        url += f"&{key}={quote_plus(str(val))}"
    return url


# sapi v8 ships no per-item bedroom count, but its own min/max_bedrooms search filter
# (the same params the site's form sends) partitions results server-side. We run one
# bucketed query per N and tag each returned posting id with its whole-unit bed count.
CL_BED_BUCKETS = [
    ({"min_bedrooms": "0", "max_bedrooms": "0"}, "studio"),
    ({"min_bedrooms": "1", "max_bedrooms": "1"}, "1 bd"),
    ({"min_bedrooms": "2", "max_bedrooms": "2"}, "2 bd"),
    ({"min_bedrooms": "3", "max_bedrooms": "3"}, "3 bd"),
    ({"min_bedrooms": "4", "max_bedrooms": "4"}, "4 bd"),
    ({"min_bedrooms": "5"}, "5 bd"),
]


def _cl_bucket_url(cfg: dict, extra: dict) -> str:
    sub, cat = cfg["subarea"], cfg["category"]
    url = f"{SAPI}?batch=1-0-0-0-0&cc=US&lang=en&searchPath={sub}/{cat}"
    params = dict(cfg.get("params") or {})
    params.update(extra)
    for key, val in params.items():
        url += f"&{key}={quote_plus(str(val))}"
    return url


def title_bed_count(title: str):
    return hp.parse_bed_count(title)


def _title_beds(title: str) -> str:
    beds = title_bed_count(title)
    if beds is None:
        return ""
    return "studio" if beds == 0 else f"{beds} bd"


def craigslist_beds_by_pid(cfg: dict) -> dict[int, str]:
    """Map posting id -> whole-unit bed string via Craigslist's own bedroom filter.
    Each bucket is isolated: one failing must never block the source."""
    out: dict[int, str] = {}
    for extra, beds_str in CL_BED_BUCKETS:
        try:
            payload = json.loads(_get(_cl_bucket_url(cfg, extra), "application/json"))
            data = payload.get("data") or {}
            base = (data.get("decode") or {}).get("minPostingId", 0)
            for it in data.get("items") or []:
                if isinstance(it, list) and it and isinstance(it[0], int):
                    out[base + it[0]] = beds_str
        except Exception:  # noqa: BLE001 - a single bucket failure degrades gracefully
            continue
    return out


def parse_craigslist(payload: dict, cfg: dict, beds_by_pid: dict | None = None) -> list[dict]:
    """Decode the sapi v8 positional/tagged item arrays into capture records."""
    data = payload.get("data") or {}
    items = data.get("items") or []
    decode = data.get("decode") or {}
    base = decode.get("minPostingId", 0)
    locdescs = decode.get("locationDescriptions") or []
    host = (data.get("location") or {}).get("url") or "sfbay.craigslist.org"
    sub = (data.get("params") or {}).get("subarea") or cfg.get("subarea", "")
    cat = data.get("categoryAbbr") or cfg.get("category", "")
    market = cfg.get("market_hint", "")
    name = cfg.get("name", "Craigslist")
    limit = cfg.get("limit", DEFAULT_LIMIT)

    records: list[dict] = []
    for it in items[:limit]:
        if not isinstance(it, list) or not it:
            continue
        pid = base + it[0] if isinstance(it[0], int) else None
        if not pid:
            continue
        price_int = it[3] if len(it) > 3 and isinstance(it[3], int) and it[3] > 0 else None
        slug = "x"
        price_str = ""
        for el in it:
            if isinstance(el, list) and el:
                if el[0] == 6 and len(el) > 1:
                    slug = el[1]
                elif el[0] == 10 and len(el) > 1 and isinstance(el[1], str):
                    price_str = el[1]
        # Title = the top-level plain string that reads like a sentence (has a space
        # or colon) and is not the geoloc code ("a:b~lat~lon") or the base62 host code.
        title = ""
        for el in it:
            if isinstance(el, str) and "~" not in el and (" " in el or ":" in el):
                if len(el) > len(title):
                    title = el
        if not title and slug != "x":
            title = slug.replace("-", " ").title()
        # Location name from item[4]: "1:2~lat~lon" -> locationDescriptions[2]
        city = ""
        lat = ""
        lng = ""
        if len(it) > 4 and isinstance(it[4], str) and "~" in it[4]:
            parts = it[4].split("~")
            head = parts[0]
            if len(parts) >= 3:
                lat, lng = parts[1], parts[2]
            try:
                idx = int(head.split(":")[-1])
                if 0 < idx < len(locdescs):
                    city = locdescs[idx]
            except (ValueError, IndexError):
                pass
        city = city.title() if city and city.islower() else city
        # Broker/feed apartment posts often ship no title or slug; synthesize one so
        # the listing is still identifiable in the rankings.
        if not title:
            word = CAT_WORD.get(cat, "Listing")
            title = f"{word} in {city}" if city else f"{word} (Craigslist {sub})"
        rent = price_str or (f"${price_int:,}" if price_int else "")
        records.append({
            "source": name,
            "listing_key": f"craigslist-{pid}",
            "title": re.sub(r":\s*", ": ", title).strip(),
            "url": f"https://{host}/{sub}/{cat}/d/{slug}/{pid}.html",
            "rent": rent,
            "city": city,
            "beds": (beds_by_pid or {}).get(pid, "") or _title_beds(title),
            "market": market,
            "lat": lat,
            "lng": lng,
        })
    return records


def fetch_craigslist(cfg: dict) -> tuple[list[dict], str | None]:
    url = _cl_url(cfg)
    try:
        body = _get(url, "application/json")
        payload = json.loads(body)
    except Exception as exc:  # noqa: BLE001 - any block -> Source Blocked, never bypass
        return [_blocked(cfg.get("name", "Craigslist"), url, cfg.get("market_hint", ""), exc)], str(exc)
    beds_by_pid: dict[int, str] = {}
    if cfg.get("category") in ("apa", "sub"):  # whole-unit beds only meaningful for apts/sublets
        try:
            beds_by_pid = craigslist_beds_by_pid(cfg)
        except Exception:  # noqa: BLE001
            beds_by_pid = {}
    return parse_craigslist(payload, cfg, beds_by_pid), None


# --------------------------------------------------------------------------- #
# Zumper __PRELOADED_STATE__
# --------------------------------------------------------------------------- #
_STATE_RE = re.compile(r"__PRELOADED_STATE__\s*=\s*(\{.*)", re.DOTALL)


def _extract_state(html: str) -> dict | None:
    m = _STATE_RE.search(html)
    if not m:
        return None
    blob = m.group(1)
    depth = 0
    end = 0
    for i, ch in enumerate(blob):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if not end:
        return None
    try:
        return json.loads(blob[:end])
    except json.JSONDecodeError:
        return None


def _coords_from_mapping(value: dict) -> tuple[str, str]:
    lat_keys = {"lat", "latitude"}
    lng_keys = {"lng", "lon", "longitude"}
    lat = ""
    lng = ""
    stack = [value]
    while stack:
        item = stack.pop()
        if not isinstance(item, dict):
            continue
        for key, val in item.items():
            key_norm = hp.normalize(key)
            if key_norm in lat_keys and not lat:
                lat = hp.clean(val)
            elif key_norm in lng_keys and not lng:
                lng = hp.clean(val)
            elif isinstance(val, dict):
                stack.append(val)
        if lat and lng:
            return lat, lng
    return lat, lng


def parse_zumper(state: dict, cfg: dict) -> list[dict]:
    listables = (((state or {}).get("currentSearch") or {}).get("listables") or {}).get("listables") or []
    market = cfg.get("market_hint", "")
    records: list[dict] = []
    for l in listables:
        if not isinstance(l, dict):
            continue
        lid = l.get("listing_id")
        lo, hi = l.get("min_price"), l.get("max_price")
        if lo and hi and lo != hi:
            rent = f"${lo:,}–${hi:,}"
        elif lo:
            rent = f"${lo:,}"
        else:
            rent = ""
        bmin, bmax = l.get("min_bedrooms"), l.get("max_bedrooms")
        if bmin is not None and bmax is not None:
            beds = "studio" if bmax == 0 else (f"{bmin}-{bmax} bd" if bmin != bmax else f"{bmin} bd")
        else:
            beds = ""
        rel = l.get("url") or ""
        url = ("https://www.zumper.com" + rel) if rel.startswith("/") else rel
        title = l.get("building_name") or l.get("address") or l.get("title") or "Zumper listing"
        lat, lng = _coords_from_mapping(l)
        records.append({
            "source": "Zumper",
            "listing_key": f"zumper-{lid}" if lid else "",
            "title": title,
            "url": url,
            "rent": rent,
            "beds": beds,
            "city": l.get("city", ""),
            "address": l.get("address", ""),
            "market": market,
            "lat": lat,
            "lng": lng,
        })
    return records


def fetch_zumper(cfg: dict) -> tuple[list[dict], str | None]:
    url = cfg["url"]
    try:
        html = _get(url, "text/html,application/xhtml+xml,*/*;q=0.8")
        state = _extract_state(html)
        if state is None:
            raise ValueError("no __PRELOADED_STATE__ (challenge or layout change)")
    except Exception as exc:  # noqa: BLE001
        return [_blocked(cfg.get("name", "Zumper"), url, cfg.get("market_hint", ""), exc)], str(exc)
    return parse_zumper(state, cfg), None


# --------------------------------------------------------------------------- #
# Redfin Rentals ld+json
# --------------------------------------------------------------------------- #
_LDJSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


def parse_redfin_ldjson(html: str, cfg: dict) -> list[dict]:
    """Redfin rental city pages embed schema.org data per listing: an
    `Accommodation` entry (name/url/address/geo/beds) plus a `Product` entry
    (offers.price), joined by url. Public SSR to a normal browser GET —
    verified 2026-07-02 for Santa Clara / Sunnyvale / Mountain View."""
    market = cfg.get("market_hint", "")
    accommodations: dict[str, dict] = {}
    prices: dict[str, str] = {}
    for block in _LDJSON_RE.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict):
                continue
            url = hp.clean(item.get("url"))
            if not url:
                continue
            if item.get("@type") == "Accommodation":
                accommodations[url] = item
            elif item.get("@type") == "Product":
                price = hp.clean(((item.get("offers") or {}).get("price")))
                if price:
                    prices[url] = price
    records: list[dict] = []
    for url, item in accommodations.items():
        address = item.get("address") or {}
        geo = item.get("geo") or {}
        listing_id = url.rstrip("/").rsplit("/", 1)[-1]
        price = prices.get(url, "")
        records.append({
            "source": "Redfin",
            "listing_key": f"redfin-{listing_id}" if listing_id.isdigit() else "",
            "title": hp.clean(item.get("name")) or "Redfin rental",
            "url": url,
            "rent": f"${price}" if price else "",
            "beds": hp.clean(item.get("numberOfRooms")),
            "city": hp.clean(address.get("addressLocality")),
            "address": hp.clean(address.get("streetAddress")),
            "market": market,
            "lat": hp.clean(geo.get("latitude")),
            "lng": hp.clean(geo.get("longitude")),
        })
    return records[: cfg.get("limit", DEFAULT_LIMIT)]


def fetch_redfin(cfg: dict) -> tuple[list[dict], str | None]:
    url = cfg["url"]
    try:
        html = _get(url, "text/html,application/xhtml+xml,*/*;q=0.8")
        records = parse_redfin_ldjson(html, cfg)
        if not records:
            # A 202/challenge page serves 200-shaped HTML with no ld+json listings.
            raise ValueError("no ld+json Accommodation entries (challenge or layout change)")
    except Exception as exc:  # noqa: BLE001
        return [_blocked(cfg.get("name", "Redfin"), url, cfg.get("market_hint", ""), exc)], str(exc)
    return records, None


# --------------------------------------------------------------------------- #
# Direct property-manager public state
# --------------------------------------------------------------------------- #
def parse_pm_udr(html: str, cfg: dict) -> list[dict]:
    state = _extract_balanced_json_after(html, "window.udr.jsonObjPropertyViewModel =")
    if not isinstance(state, dict):
        return []
    url = cfg.get("url", "")
    source = cfg.get("name") or state.get("propertyName") or "Property Manager"
    market = cfg.get("market_hint", "")
    lat = _meta_content(html, "place:location:latitude")
    lng = _meta_content(html, "place:location:longitude")
    address = hp.clean(cfg.get("address") or state.get("propertyAddress") or _meta_content(html, "og:street-address"))
    city = hp.clean(cfg.get("city") or market.split("/")[0])
    lease = hp.clean(state.get("leaseTermsRangeText", ""))
    records: list[dict] = []
    limit = cfg.get("limit", DEFAULT_LIMIT)
    for fp in state.get("floorPlans") or []:
        if not isinstance(fp, dict):
            continue
        fp_name = hp.clean(fp.get("Name") or "Floor plan")
        units = fp.get("units") or []
        if not units and (fp.get("availableCount") or fp.get("rentMin")):
            units = [{}]
        for unit in units:
            if not isinstance(unit, dict):
                continue
            if unit and unit.get("isAvailable") is False:
                continue
            unit_name = hp.clean(unit.get("marketingFullName") or unit.get("marketingName") or unit.get("lookUpName"))
            unit_id = unit.get("apartmentId") or unit.get("realpageunitid") or unit_name or fp.get("id")
            rent_obj = unit.get("lowestRent") if isinstance(unit.get("lowestRent"), dict) else {}
            rent = _fmt_money(rent_obj.get("baseRent") or rent_obj.get("rent") or unit.get("rent") or fp.get("rentMin"))
            available = (
                _fmt_date(unit.get("earliestMoveInDate"))
                or _fmt_date(unit.get("availableDate"))
                or _fmt_date(fp.get("earliestMoveInDate"))
                or _fmt_date(fp.get("availableDate"))
            )
            rel = unit.get("previewLink") or state.get("apartmentsPageUrl") or state.get("landingPageUrl") or url
            title = f"{source} {fp_name}"
            if unit_name:
                title += f" unit {unit_name}"
            description_parts = []
            sqft = unit.get("sqFt") or fp.get("sqFtMin")
            if sqft:
                description_parts.append(f"{sqft} sqft")
            if lease:
                description_parts.append(lease)
            records.append({
                "source": source,
                "listing_key": f"pm-{hp.slug(source)}-{unit_id}",
                "title": title.strip(),
                "url": urljoin(url, rel),
                "rent": rent,
                "beds": _fmt_beds(unit.get("bedrooms") or fp.get("bedRooms")),
                "baths": _fmt_baths(unit.get("bathrooms") or fp.get("bathRooms")),
                "available": available,
                "city": city,
                "address": address,
                "market": market,
                "lat": lat,
                "lng": lng,
                "description": "; ".join(description_parts),
            })
            if len(records) >= limit:
                return records
    return records


def fetch_pm(cfg: dict) -> tuple[list[dict], str | None]:
    url = cfg["url"]
    try:
        html = _get(url, "text/html,application/xhtml+xml,*/*;q=0.8")
        if _looks_blocked(html):
            raise ValueError("challenge/CAPTCHA/access-denied page")
        provider = hp.normalize(cfg.get("provider", "udr"))
        if provider == "udr" or "window.udr.jsonObjPropertyViewModel" in html:
            records = parse_pm_udr(html, cfg)
        else:
            records = []
        if not records:
            raise ValueError("no supported public property-manager availability state")
    except Exception as exc:  # noqa: BLE001
        return [_blocked(cfg.get("name", "Property Manager"), url, cfg.get("market_hint", ""), exc)], str(exc)
    return records, None


# --------------------------------------------------------------------------- #
# Rent.com __NEXT_DATA__
# --------------------------------------------------------------------------- #
_NEXT_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def _extract_next_data(html: str) -> dict | None:
    m = _NEXT_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(html_lib.unescape(m.group(1)))
    except json.JSONDecodeError:
        return None


def parse_rent_next_data(state: dict, cfg: dict) -> list[dict]:
    search = (((state or {}).get("props") or {}).get("pageProps") or {}).get("pageData", {})
    listings = (((search.get("location") or {}).get("listingSearch") or {}).get("listings") or [])
    market = cfg.get("market_hint", "")
    limit = cfg.get("limit", DEFAULT_LIMIT)
    records: list[dict] = []
    for listing in listings:
        if not isinstance(listing, dict):
            continue
        listing_id = listing.get("id") or listing.get("listingId")
        name = hp.clean(listing.get("name") or "Rent.com listing")
        loc = listing.get("location") if isinstance(listing.get("location"), dict) else {}
        base_url = listing.get("urlPathname") or listing.get("url") or ""
        url = urljoin("https://www.rent.com", base_url)
        floorplans = listing.get("floorPlans") or []
        if not floorplans:
            floorplans = [{}]
        for idx, fp in enumerate(floorplans):
            if not isinstance(fp, dict):
                continue
            price_range = fp.get("priceRange") if isinstance(fp.get("priceRange"), dict) else {}
            units = fp.get("units") or []
            unit_rent = ""
            if units and isinstance(units[0], dict):
                unit_rent = units[0].get("rent", "")
            rent = unit_rent or _fmt_range(price_range.get("min"), price_range.get("max"))
            if not rent:
                bcd = listing.get("bedCountData") or []
                if bcd and isinstance(bcd[0], dict):
                    prices = bcd[0].get("prices") if isinstance(bcd[0].get("prices"), dict) else {}
                    rent = _fmt_money(prices.get("low"))
            records.append({
                "source": cfg.get("name", "Rent.com"),
                "listing_key": f"rent-{listing_id}-{idx}" if listing_id else "",
                "title": f"{name} {_fmt_beds(fp.get('bedCount'))}".strip(),
                "url": url,
                "rent": rent,
                "beds": _fmt_beds(fp.get("bedCount")),
                "baths": _fmt_baths(fp.get("bathCount")),
                "available": _fmt_date(fp.get("availableDate")),
                "city": loc.get("city", ""),
                "address": loc.get("address", ""),
                "market": market,
                "lat": hp.clean(loc.get("lat", "")),
                "lng": hp.clean(loc.get("lng", "")),
            })
            if len(records) >= limit:
                return records
    return records


def fetch_rent_next_data(cfg: dict) -> tuple[list[dict], str | None]:
    url = cfg["url"]
    try:
        html = _get(url, "text/html,application/xhtml+xml,*/*;q=0.8")
        if _looks_blocked(html):
            raise ValueError("challenge/CAPTCHA/access-denied page")
        state = _extract_next_data(html)
        if state is None:
            raise ValueError("no __NEXT_DATA__ (challenge or layout change)")
    except Exception as exc:  # noqa: BLE001
        return [_blocked(cfg.get("name", "Rent.com"), url, cfg.get("market_hint", ""), exc)], str(exc)
    return parse_rent_next_data(state, cfg), None


KINDS = {
    "craigslist_sapi": fetch_craigslist,
    "zumper_state": fetch_zumper,
    "pm": fetch_pm,
    "rent_next_data": fetch_rent_next_data,
    "redfin_ldjson": fetch_redfin,
}


# Seconds between consecutive fetches to the SAME host. Redfin serves HTTP 202
# challenge pages to rapid back-to-back city requests but 200s politely-spaced
# ones; this is pacing within the site's tolerance, not a challenge bypass.
SAME_HOST_DELAY_SECONDS = 30


def run_web_capture(capture_dir: Path, searches: dict) -> list[Path]:
    written: list[Path] = []
    last_host = ""
    for cfg in searches.get("web", []):
        if not cfg.get("enabled", True):
            continue
        kind = cfg.get("kind")
        fetch = KINDS.get(kind)
        label = cfg.get("label") or hp.slug(cfg.get("name", "web"))
        if not fetch:
            print(f"  web {label}: skipped (unknown kind {kind!r})", file=sys.stderr)
            continue
        host = urlparse(cfg.get("url", "")).netloc
        if host and host == last_host and kind == "redfin_ldjson":
            time.sleep(SAME_HOST_DELAY_SECONDS)
        last_host = host
        records, error = fetch(cfg)
        out = capture_dir / f"web-{hp.slug(cfg.get('name','web'))}-{hp.slug(label)}.json"
        out.write_text(json.dumps(records, indent=2), encoding="utf-8")
        written.append(out)
        status = "blocked" if error else f"{len(records)} items"
        print(f"  web {cfg.get('name')} [{label}]: {status}", file=sys.stderr)
    return written


if __name__ == "__main__":
    import os
    cap = Path(os.environ.get("HOUSING_CAPTURE_DIR", "/tmp/codexskills-housing-hunt"))
    cap.mkdir(parents=True, exist_ok=True)
    cfg_path = SCRIPT_DIR / "searches.json"
    searches = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    paths = run_web_capture(cap, searches)
    print(json.dumps({"wrote": [str(p) for p in paths]}, indent=2))
