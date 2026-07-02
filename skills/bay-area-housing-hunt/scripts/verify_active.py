#!/usr/bin/env python3
"""Liveness checker for active listings: is each posting still up?

Fetches each active listing's own public page headlessly and classifies it:
  - live        : page loads and shows no removed/expired marker
  - expired     : the site says the posting expired ("This posting has expired")
  - deleted     : the site says the poster removed it
  - gone        : HTTP 404/410 on the canonical URL
  - unverifiable: the source blocks headless reads (Facebook, Zillow,
                  Apartments.com, Furnished Finder…) — left untouched

Only sources whose PUBLIC post pages serve a normal browser GET are checked
(currently Craigslist). This reads public pages politely (paced, no retries on
blocks) — the same access policy as capture_web.py; on 403/429 the row is
reported unverifiable, never fought.

Dead rows are marked through the pipeline's own lifecycle (--apply →
housing_pipeline.run(marks=...)) so decisions stay sticky and the board moves
them to the expired/replaced lane instead of deleting them.

Usage:
    python3 verify_active.py                 # dry-run report (top 150 by score)
    python3 verify_active.py --apply         # apply Expired/Unavailable marks
    python3 verify_active.py --limit 300     # check more rows
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import housing_pipeline as hp  # noqa: E402
import capture_web as cw  # noqa: E402

FETCH_TIMEOUT = 15
PACE_SECONDS = 2.0  # between requests to the same site

CRAIGSLIST_DELETED = "this posting has been deleted by its author"
CRAIGSLIST_EXPIRED = "this posting has expired"
CRAIGSLIST_FLAGGED = "this posting has been flagged for removal"


def classify_craigslist(url: str) -> str:
    req = urllib.request.Request(url, headers=cw.BROWSER_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            body = resp.read(200_000).decode("utf-8", errors="replace").lower()
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            return "gone"
        return "unverifiable"  # 403/429/5xx: do not fight, do not conclude
    except Exception:  # noqa: BLE001 - network hiccup is not evidence of death
        return "unverifiable"
    if CRAIGSLIST_DELETED in body:
        return "deleted"
    if CRAIGSLIST_EXPIRED in body:
        return "expired"
    if CRAIGSLIST_FLAGGED in body:
        return "deleted"
    return "live"


CHECKERS = {
    "craigslist.org": classify_craigslist,
}

# status mark applied per verdict (verdict -> pipeline status)
MARK_FOR = {"expired": "Expired", "deleted": "Unavailable", "gone": "Expired"}


def checker_for(url: str):
    for host, fn in CHECKERS.items():
        if host in url:
            return fn
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify active listings are still posted.")
    parser.add_argument("--limit", type=int, default=150, help="Max rows to check (highest score first)")
    parser.add_argument("--apply", action="store_true", help="Apply Expired/Unavailable marks and rebuild the board")
    parser.add_argument("--pace", type=float, default=PACE_SECONDS, help="Seconds between requests")
    args = parser.parse_args()

    rows = hp.load_listing_rows()
    candidates = [
        row for row in rows
        if row.get("Status") in ("Active", "Needs Verification") and hp.clean(row.get("URL"))
    ]
    candidates.sort(key=lambda r: -hp.to_int(r.get("Score")))

    checked = 0
    verdicts: dict[str, list[dict[str, str]]] = {}
    marks: list[tuple[str, str]] = []
    for row in candidates:
        if checked >= args.limit:
            break
        url = hp.clean(row.get("URL"))
        check = checker_for(url)
        if not check:
            continue
        if checked:
            time.sleep(args.pace)
        verdict = check(url)
        checked += 1
        verdicts.setdefault(verdict, []).append(row)
        print(f"  {verdict:12s} {hp.to_int(row.get('Score')):3d}  {hp.clean(row.get('Title'))[:60]}", file=sys.stderr)
        if verdict in MARK_FOR:
            marks.append((MARK_FOR[verdict], url))

    summary = {
        "checked": checked,
        "live": len(verdicts.get("live", [])),
        "expired": len(verdicts.get("expired", [])),
        "deleted": len(verdicts.get("deleted", [])),
        "gone": len(verdicts.get("gone", [])),
        "unverifiable": len(verdicts.get("unverifiable", [])),
        "marks": len(marks),
        "applied": False,
    }
    if args.apply and marks:
        result = hp.run(marks=marks, refresh_only=True)
        summary["applied"] = True
        summary["active_after"] = result["active"]
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
