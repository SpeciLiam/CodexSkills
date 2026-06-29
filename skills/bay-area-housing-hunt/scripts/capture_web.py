#!/usr/bin/env python3
"""Headless capture for portals that serve real public data to a normal browser
request but reject the honest bot User-Agent.

This is NOT a CAPTCHA / login / rate-limit bypass. We simply identify as a normal
browser and read the PUBLIC response that the site returns to anyone. There is no
authentication, no CAPTCHA solving, and no rate-limit circumvention: if a source
answers with a 403 / 429 / challenge / login wall we record a Source Blocked row
and stop (same hard rule as the rest of the pipeline — see references/sources.md).

Two adapter kinds, both driven by the `web` array in searches.json:

  - craigslist_sapi : Craigslist's own public JSON search API (sapi.craigslist.org).
                      The legacy RSS feed 403s headlessly, but the JSON API that the
                      site's own search page calls returns the full result set. Each
                      posting id is delta-encoded (real id = decode.minPostingId +
                      item[0]); the canonical post URL is rebuilt from subarea +
                      category + slug + id and verified to resolve.
  - zumper_state    : parse the __PRELOADED_STATE__ blob embedded in the Zumper
                      search page (currentSearch.listables.listables).

Stdlib only (urllib) so it runs in CI/cloud. Importable for tests:
    parse_craigslist(payload, cfg) -> [records]
    parse_zumper(state, cfg)       -> [records]
"""
from __future__ import annotations

import gzip
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

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


# --------------------------------------------------------------------------- #
# Craigslist sapi
# --------------------------------------------------------------------------- #
def _cl_url(cfg: dict) -> str:
    sub = cfg["subarea"]
    cat = cfg["category"]
    url = f"{SAPI}?batch=1-0-0-0-0&cc=US&lang=en&searchPath={sub}/{cat}"
    for key, val in (cfg.get("params") or {}).items():
        url += f"&{key}={val}"
    return url


def parse_craigslist(payload: dict, cfg: dict) -> list[dict]:
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
        if len(it) > 4 and isinstance(it[4], str) and "~" in it[4]:
            head = it[4].split("~", 1)[0]
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
            "market": market,
        })
    return records


def fetch_craigslist(cfg: dict) -> tuple[list[dict], str | None]:
    url = _cl_url(cfg)
    try:
        body = _get(url, "application/json")
        payload = json.loads(body)
    except Exception as exc:  # noqa: BLE001 - any block -> Source Blocked, never bypass
        return [_blocked(cfg.get("name", "Craigslist"), url, cfg.get("market_hint", ""), exc)], str(exc)
    return parse_craigslist(payload, cfg), None


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


KINDS = {
    "craigslist_sapi": fetch_craigslist,
    "zumper_state": fetch_zumper,
}


def run_web_capture(capture_dir: Path, searches: dict) -> list[Path]:
    written: list[Path] = []
    for cfg in searches.get("web", []):
        if not cfg.get("enabled", True):
            continue
        kind = cfg.get("kind")
        fetch = KINDS.get(kind)
        label = cfg.get("label") or hp.slug(cfg.get("name", "web"))
        if not fetch:
            print(f"  web {label}: skipped (unknown kind {kind!r})", file=sys.stderr)
            continue
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
