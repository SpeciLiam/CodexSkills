#!/usr/bin/env python3
"""Recompute every listing's office commute with real Google Maps routing.

Listings usually have only approximate location, so we group them by rounded
coordinates when present, else by a normalized origin string
(commute_origins.origin_key), and route each UNIQUE origin once to each office.
Routing goes through the already-deployed Vercel function `/api/commute`, which
holds GOOGLE_MAPS_API_KEY server-side — so this script never touches the secret
and the exact same Routes logic (real Caltrain/BART schedules) is reused.

Results land in scripts/commute_cache.json (durations + the transit summary only —
no secret, safe to commit). export_housing_data.py reads that cache and overwrites
each listing's commuteMin / carCommuteMin / commuteHomeMin / officeCommutes, so the
~1,300 active listings get real numbers without re-billing Google on every export.

The cache is incremental: reruns only call Google for origins not already present
(or stale beyond --max-age-days, or all with --force). Stdlib only.

Usage:
    python3 recompute_commutes.py [--force] [--limit N] [--max-age-days 30]
                                  [--workers 10] [--endpoint URL]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import commute_origins as co  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "housing-visualizer" / "src" / "data" / "housing-data.json"
CACHE = SCRIPT_DIR / "commute_cache.json"
DEFAULT_ENDPOINT = "https://housing-visualizer.vercel.app/api/commute"

# Only route origins for listings the dashboard might show; skip expired/dup/blocked
# to keep Google spend down.
LIVE_STATUSES = {"Active", "New", "Available", "Needs Verification"}

# Plausibility envelope (minutes, one-way) used only to FLAG suspect geocodes; the
# value is still stored. Anything to a Bay Area office should sit well inside this.
TRANSIT_BOUNDS = (8, 220)
DRIVE_BOUNDS = (4, 150)


def next_weekday_arrival(hour: int = 9) -> str:
    """Next Monday at `hour`:00 Pacific, RFC3339. A stable weekday-rush baseline
    (Date.now() is unavailable in workflow land but fine here in a plain script)."""
    today = dt.date.today()
    days = (7 - today.weekday()) % 7 or 7  # Monday == 0
    d = today + dt.timedelta(days=days)
    # Pacific Daylight Time = -07:00 (Bay Area, summer). Good enough for a baseline.
    return f"{d.isoformat()}T{hour:02d}:00:00-07:00"


def fetch_commute(endpoint: str, origin: str, dest: str, arrival: str, timeout: int = 40) -> dict:
    qs = urllib.parse.urlencode({"origin": origin, "dest": dest, "arrival": arrival})
    req = urllib.request.Request(f"{endpoint}?{qs}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def transit_summary(transit: dict) -> str:
    """Short human path from the transit legs, e.g. 'Caltrain + bus' / 'BART + bus'."""
    legs = (transit or {}).get("legs") or []
    parts = []
    for leg in legs:
        line = (leg.get("line") or "").strip()
        veh = (leg.get("vehicle") or "").upper()
        if "RAIL" in veh or leg.get("rail"):
            label = "Caltrain" if "caltrain" in line.lower() else (line.split(" - ")[0] or "rail")
        elif veh == "SUBWAY" or "bart" in line.lower():
            label = "BART"
        elif veh == "BUS":
            label = "bus"
        else:
            label = veh.lower() or "transit"
        if not parts or parts[-1] != label:
            parts.append(label)
    return " + ".join(parts[:3])


def route_origin(endpoint: str, origin_addr: str, arrival: str) -> dict:
    """Route ONE origin to every office (to-work) plus the primary office's
    from-work transit. Returns the cache entry for this origin."""
    entry: dict = {"origin": origin_addr, "office": {}, "computedAt": _now_iso()}
    for label, dest in co.OFFICE_ADDRESSES.items():
        try:
            j = fetch_commute(endpoint, origin_addr, dest, arrival)
        except Exception as e:  # network / 5xx — log only, never persist into the cache
            print(f"  ! {origin_addr} -> {label}: {str(e)[:160]}", file=sys.stderr, flush=True)
            continue
        t = j.get("transit") or {}
        d = j.get("drive") or {}
        b = j.get("bike") or {}
        rec = {
            "transit": t.get("durationMin") if t.get("ok") else None,
            "drive": d.get("durationMin") if d.get("ok") else None,
            "bike": b.get("durationMin") if b.get("ok") else None,
        }
        if label == co.PRIMARY_OFFICE:
            rec["transitSummary"] = transit_summary(t)
            entry["suspect"] = _suspect(rec)
        entry["office"][label] = rec

    # from-work transit for the primary office (evening departure ~17:30 PT).
    try:
        eve = arrival.replace("T09:00:00", "T17:30:00")
        jr = fetch_commute(endpoint, co.OFFICE_ADDRESSES[co.PRIMARY_OFFICE], origin_addr, eve)
        rt = jr.get("transit") or {}
        entry["homeTransit"] = rt.get("durationMin") if rt.get("ok") else None
    except Exception:
        entry["homeTransit"] = None
    return entry


def _suspect(rec: dict) -> bool:
    t, d = rec.get("transit"), rec.get("drive")
    if t is not None and not (TRANSIT_BOUNDS[0] <= t <= TRANSIT_BOUNDS[1]):
        return True
    if d is not None and not (DRIVE_BOUNDS[0] <= d <= DRIVE_BOUNDS[1]):
        return True
    return False


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_cache() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"meta": {}, "origins": {}}


def entry_has_numbers(entry: dict) -> bool:
    """True when the primary-office record carries at least one real duration.
    A quota-exhausted run (Google 429) yields all-null records — those must
    never count as fresh or they poison the cache for max_age_days AND shadow
    the legacy address-key fallback in export_housing_data.py."""
    prim = (entry.get("office") or {}).get(co.PRIMARY_OFFICE) or {}
    return any(isinstance(prim.get(k), (int, float)) for k in ("transit", "drive", "bike"))


def is_fresh(entry: dict, max_age_days: int) -> bool:
    """A cached origin is fresh if it routed at least the primary office recently
    and actually got numbers back."""
    if not entry or not entry_has_numbers(entry):
        return False
    ts = entry.get("computedAt")
    if not ts:
        return False
    try:
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(ts)
        return age <= dt.timedelta(days=max_age_days)
    except ValueError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="recompute every origin")
    ap.add_argument("--limit", type=int, default=0, help="cap origins (testing)")
    ap.add_argument("--max-age-days", type=int, default=30)
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    args = ap.parse_args()

    data = json.loads(DATA.read_text(encoding="utf-8"))
    listings = data.get("listings", [])

    # Unique live origins, keyed by rounded coordinates when present, else
    # normalized address. Old address-keyed cache entries remain in the cache and
    # are still read by export_housing_data.py as a fallback.
    origins: dict[str, str] = {}
    for x in listings:
        if x.get("status") not in LIVE_STATUSES:
            continue
        key = co.origin_key(
            x.get("market", ""),
            x.get("city", ""),
            x.get("neighborhood", ""),
            x.get("lat", ""),
            x.get("lng", ""),
        )
        if key not in origins:
            origins[key] = (
                co.coordinate_origin(x.get("lat", ""), x.get("lng", ""))
                or co.origin_address(x.get("market", ""), x.get("city", ""), x.get("neighborhood", ""))
            )

    cache = load_cache()
    cache.setdefault("origins", {})
    arrival = next_weekday_arrival()

    # Self-heal: drop all-null entries from prior quota-exhausted runs so they
    # get re-routed AND stop shadowing the export's address-key fallback.
    nulls = [k for k, v in cache["origins"].items() if not entry_has_numbers(v)]
    for k in nulls:
        del cache["origins"][k]
    if nulls:
        print(f"purged {len(nulls)} all-null cache entries (quota-exhausted runs)", flush=True)

    todo = [(k, a) for k, a in origins.items()
            if args.force or not is_fresh(cache["origins"].get(k, {}), args.max_age_days)]
    todo.sort(key=lambda ka: ka[1])
    if args.limit:
        todo = todo[: args.limit]

    print(f"live origins: {len(origins)}  |  to route: {len(todo)}  "
          f"|  cached fresh: {len(origins) - len(todo)}  |  arrival: {arrival}", flush=True)

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(route_origin, args.endpoint, addr, arrival): key for key, addr in todo}
        for fut in as_completed(futs):
            key = futs[fut]
            try:
                entry = fut.result()
            except Exception as e:
                print(f"  ! {origins[key]}: {e}", flush=True)
                continue
            if not entry_has_numbers(entry):
                # Google refused every mode (quota/geocode) — do not cache the
                # failure or it would mask the address-key fallback until purged.
                print(f"  ! {origins[key]}: no durations returned (quota?), not cached", flush=True)
                continue
            cache["origins"][key] = entry
            done += 1
            prim = (entry.get("office") or {}).get(co.PRIMARY_OFFICE, {})
            flag = " ⚠suspect" if entry.get("suspect") else ""
            if done % 10 == 0 or done == len(todo):
                print(f"  [{done}/{len(todo)}] {entry['origin']}  "
                      f"transit={prim.get('transit')}m drive={prim.get('drive')}m{flag}", flush=True)

    cache["meta"] = {
        "generatedAt": _now_iso(),
        "arrival": arrival,
        "endpoint": args.endpoint,
        "primaryOffice": co.PRIMARY_OFFICE,
        "officeAddresses": co.OFFICE_ADDRESSES,
        "originCount": len(cache["origins"]),
    }
    CACHE.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")

    suspects = [k for k, v in cache["origins"].items() if v.get("suspect")]
    print(f"\nwrote {CACHE.relative_to(ROOT)}  | origins cached: {len(cache['origins'])}  "
          f"| routed now: {done}  | suspect: {len(suspects)}", flush=True)
    for k in suspects[:15]:
        o = cache["origins"][k]
        prim = (o.get("office") or {}).get(co.PRIMARY_OFFICE, {})
        print(f"   suspect: {o['origin']}  transit={prim.get('transit')} drive={prim.get('drive')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
